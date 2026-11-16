from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, Cliente, MovimientoStock, Producto, Proveedor
from app import servicios as s


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as sesion:
        sesion.add(Proveedor(id=1, nombre="Distribuidora Demo"))
        sesion.flush()  # las llaves foraneas estan activas: el proveedor va primero
        sesion.add_all([
            Producto(id=1, nombre="Arroz (lb)", precio_centavos=3500, costo_centavos=2800, stock=D(10),
                     stock_minimo=D(5), unidad="lb", proveedor_id=1),
            Producto(id=2, nombre="Pollo (lb)", precio_centavos=9000, costo_centavos=7000, stock=D(6),
                     stock_minimo=D(6), unidad="lb", proveedor_id=1),
            Cliente(id=1, nombre="Juan Demo", limite_fiado_centavos=50000),
        ])
        sesion.commit()
        yield sesion


def test_venta_descuenta_stock_y_usa_precio_del_producto(db):
    v = s.registrar_venta(db, [(1, D("2.5"))], "efectivo")
    assert v.total_centavos == 8750
    assert db.get(Producto, 1).stock == D("7.5")
    assert db.scalar(select(func.sum(MovimientoStock.cantidad)).where(MovimientoStock.motivo == "venta")) == D("-2.5")


def test_stock_insuficiente_no_escribe_nada(db):
    with pytest.raises(s.StockInsuficiente):
        s.registrar_venta(db, [(1, D(1)), (2, D(99))], "efectivo")
    db.rollback()
    assert db.get(Producto, 1).stock == D(10)


def test_fiado_saldo_abono_y_limite(db):
    s.registrar_venta(db, [(2, D(4))], "fiado", cliente_id=1)  # 36000
    assert s.saldo_cliente(db, 1) == 36000
    with pytest.raises(s.LimiteFiadoExcedido):  # 36000 + 18000 > 50000
        s.registrar_venta(db, [(1, D(5)), (2, D(1))], "fiado", cliente_id=1)
    db.rollback()
    s.registrar_venta(db, [(1, D(5)), (2, D(1))], "fiado", cliente_id=1, autoriza_exceso=True)
    s.registrar_abono(db, 1, 10000)
    assert s.saldo_cliente(db, 1) == 36000 + 26500 - 10000
    with pytest.raises(s.ErrorNegocio):
        s.registrar_abono(db, 1, 10**7)


def test_misma_linea_repetida_no_esquiva_stock(db):
    with pytest.raises(s.StockInsuficiente):
        s.registrar_venta(db, [(1, D(6)), (1, D(6))], "efectivo")  # 12 > 10


def test_fiado_sin_cliente_falla(db):
    with pytest.raises(s.ErrorNegocio):
        s.registrar_venta(db, [(1, D(1))], "fiado")


def test_anular_devuelve_stock_y_baja_saldo(db):
    v = s.registrar_venta(db, [(2, D(2))], "fiado", cliente_id=1)
    s.anular_venta(db, v.id)
    assert db.get(Producto, 2).stock == D(6)
    assert s.saldo_cliente(db, 1) == 0
    with pytest.raises(s.ErrorNegocio):
        s.anular_venta(db, v.id)


def test_compra_sube_stock_y_costo_y_reposicion(db):
    assert [p.id for p in s.por_reponer(db)] == [2]  # stock 6 <= minimo 6
    s.registrar_compra(db, 1, [(2, D(20), 7500)])
    p = db.get(Producto, 2)
    assert p.stock == D(26) and p.costo_centavos == 7500
    assert s.por_reponer(db) == []


def _dia_tipico(db):
    s.registrar_venta(db, [(1, D("2.5"))], "efectivo")                        # 8750, margen 700*2.5 = 1750
    tarjeta = s.registrar_venta(db, [(2, D(1))], "tarjeta")                   # 9000, margen 2000
    s.registrar_venta(db, [(2, D(1))], "fiado", cliente_id=1)                  # 9000, margen 2000
    s.registrar_abono(db, 1, 3000)                                             # efectivo
    return tarjeta


def test_resumen_dia_y_cierre_de_caja(db):
    from datetime import date, timedelta
    tarjeta = _dia_tipico(db)
    r = s.resumen_dia(db, date.today())
    assert r["por_metodo"] == {"efectivo": 8750, "tarjeta": 9000, "fiado": 9000}
    assert r["abonos"] == {"efectivo": 3000, "tarjeta": 0}
    assert r["esperado_efectivo_centavos"] == 11750 and r["margen_centavos"] == 5750 and r["ventas"] == 3
    s.anular_venta(db, tarjeta.id)
    r = s.resumen_dia(db, date.today())
    assert r["por_metodo"]["tarjeta"] == 0 and r["anuladas"] == 1 and r["margen_centavos"] == 3750

    c = s.cerrar_caja(db, date.today(), 11000)
    assert s.resumen_dia(db, date.today())["cierre"]["diferencia_centavos"] == 11000 - c.esperado_centavos == -750
    with pytest.raises(s.ErrorNegocio):
        s.cerrar_caja(db, date.today(), 11750)                                 # ya cerrada
    with pytest.raises(s.ErrorNegocio):
        s.cerrar_caja(db, date.today() + timedelta(days=1), 0)                 # dia futuro
    assert s.resumen_dia(db, date.today() - timedelta(days=1))["total_centavos"] == 0


def test_reporte_rango_top_y_fiado_por_cobrar(db):
    from datetime import date, timedelta
    _dia_tipico(db)
    r = s.reporte(db, date.today() - timedelta(days=7), date.today())
    assert len(r["dias"]) == 1 and r["dias"][0]["total_centavos"] == 26750 and r["dias"][0]["margen_centavos"] == 5750
    assert r["mas_vendidos"][0]["nombre"] == "Pollo (lb)" and r["mas_vendidos"][0]["ingreso_centavos"] == 18000
    assert r["fiado_por_cobrar_centavos"] == 6000                              # 9000 fiado - 3000 abono
    with pytest.raises(s.ErrorNegocio):
        s.reporte(db, date.today(), date.today() - timedelta(days=1))


def test_la_misma_factura_no_se_registra_dos_veces(db):
    s.registrar_compra(db, 1, [(1, D(10), 2800)], "F-001")
    with pytest.raises(s.ErrorNegocio, match="ya esta registrada"):
        s.registrar_compra(db, 1, [(1, D(10), 2800)], " F-001 ")  # el espacio no la hace distinta
    s.registrar_compra(db, 1, [(1, D(5), 2800)])  # sin numero se permiten varias
    s.registrar_compra(db, 1, [(1, D(5), 2800)])
    assert db.get(Producto, 1).stock == D(30)  # 10 + 10 + 5 + 5: la repetida no sumo stock


def test_ajuste_no_deja_stock_negativo(db):
    s.ajustar_stock(db, 1, D(-3))
    assert db.get(Producto, 1).stock == D(7)
    with pytest.raises(s.ErrorNegocio):
        s.ajustar_stock(db, 1, D(-100))
