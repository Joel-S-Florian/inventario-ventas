"""Resumen del dia con un Gemini FALSO: sin red ni cuota. Las cifras salen de la app, no del modelo."""
import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import ia
from app import servicios as s
from app.ia_resumen import datos_resumen, poner_cifras, resumir
from app.models import Base, Cliente, Producto, Proveedor, Venta
from test_ia import ClienteFalso

SALIDA = json.dumps({
    "titular": "Hoy vendiste {total} en {ventas_n} ventas",
    "hallazgos": ["Las ventas cambiaron {cambio_total} contra el periodo anterior.", "Lo mas vendido fue {top1_nombre} con {top1_ingreso}."],
    "atencion": ["Hay {bajo_minimo_n} producto(s) bajo el minimo: {bajo_minimo_nombres}."],
    "sugerencias": ["Cobra el fiado pendiente de {fiado_por_cobrar}."]})


@pytest.fixture
def falso(monkeypatch):
    def poner(*respuestas):
        f = ClienteFalso(list(respuestas))
        monkeypatch.setattr(ia, "cliente", lambda: f)
        return f
    return poner


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as sesion:
        sesion.add(Proveedor(id=1, nombre="Distribuidora Demo"))
        sesion.flush()
        sesion.add_all([
            Producto(id=1, nombre="Arroz (lb)", precio_centavos=3500, costo_centavos=2800, stock=D(40), stock_minimo=D(5), unidad="lb", proveedor_id=1),
            Producto(id=2, nombre="Pollo (lb)", precio_centavos=9000, costo_centavos=7000, stock=D(8), stock_minimo=D(10), unidad="lb", proveedor_id=1),
            Producto(id=3, nombre="Refresco 2L", precio_centavos=11000, costo_centavos=8500, stock=D(10), stock_minimo=D(2), proveedor_id=1),
            Cliente(id=1, nombre="Juan Secreto", limite_fiado_centavos=50000),
        ])
        sesion.commit()
        ayer = s.registrar_venta(sesion, [(1, D(2))], "efectivo")                  # 7000 (margen 1400)
        hoy = [s.registrar_venta(sesion, [(1, D("2.5"))], "efectivo"),             # 8750 (margen 1750)
               s.registrar_venta(sesion, [(2, D(1))], "tarjeta"),                  # 9000 (margen 2000)
               s.registrar_venta(sesion, [(2, D(1))], "fiado", cliente_id=1)]      # 9000 (margen 2000)
        s.registrar_abono(sesion, 1, 3000)
        ayer.fecha = datetime.combine(date.today() - timedelta(days=1), time(10, 0))
        for v in hoy:
            v.fecha = datetime.combine(date.today(), time(15, 30))
        sesion.commit()
        yield sesion


def _d(db, periodo="dia"):
    datos, kpis = datos_resumen(db, periodo)
    return {k: v for k, v, _ in datos}, kpis


def test_las_cifras_las_calcula_la_app(db):
    d, kpis = _d(db)
    assert d["total"] == "RD$267.50" and d["ventas_n"] == "3" and d["ticket"] == "RD$89.16"          # 26750 / 3
    assert (d["efectivo"], d["tarjeta"], d["fiado"], d["abonos"]) == ("RD$87.50", "RD$90.00", "RD$90.00", "RD$30.00")
    assert d["margen"] == "RD$57.50" and d["margen_pct"] == "21%"
    assert d["anterior_total"] == "RD$70.00" and d["cambio_total"] == "+282%"                         # (26750 - 7000) / 7000
    assert d["hora_pico"] == "3 p. m." and d["hora_pico_total"] == "RD$267.50"
    assert d["top1_nombre"] == "Pollo (lb)" and d["top1_ingreso"] == "RD$180.00" and d["top2_nombre"] == "Arroz (lb)"
    assert d["fiado_por_cobrar"] == "RD$60.00" and d["deudores_n"] == "1" and d["mayor_deuda"] == "RD$60.00"
    assert d["bajo_minimo_n"] == "1" and d["bajo_minimo_nombres"] == "Pollo (lb)"                     # pollo: 8 - 3 vendidos... queda bajo 10
    assert kpis[0] == {"etiqueta": "Ventas", "valor": "RD$267.50", "detalle": "3 ventas"}


def test_semana_incluye_ayer_y_compara_con_la_semana_anterior(db):
    d, _ = _d(db, "semana")
    assert d["total"] == "RD$337.50" and d["ventas_n"] == "4"                                          # 26750 + 7000
    assert d["anterior_total"] == "RD$0.00" and d["cambio_total"].startswith("n/d")                    # sin datos previos: no inventa un %


def test_el_modelo_escribe_marcadores_y_la_app_pone_las_cifras(falso, db):
    f = falso(SALIDA)
    r = resumir(db, "dia")
    assert r["titular"] == "Hoy vendiste RD$267.50 en 3 ventas"
    assert r["hallazgos"][0] == {"texto": "Las ventas cambiaron +282% contra el periodo anterior.", "verificado": True}
    assert r["atencion"][0]["texto"] == "Hay 1 producto(s) bajo el minimo: Pollo (lb)." and r["avisos"] == []
    assert not re.search(r"\{[a-z0-9_]+\}", json.dumps(r))   # ningun marcador quedo sin sustituir
    entrada = f.llamadas[0]["input"]
    assert "{total} = RD$267.50" in entrada
    assert "Juan Secreto" not in entrada and "RD$28.00" not in entrada and "RD$70.00 (costo" not in entrada   # ni clientes ni costos unitarios


def test_cifras_escritas_por_el_modelo_o_claves_inventadas_se_marcan(falso, db):
    falso(json.dumps({"titular": "Vendiste {total}", "hallazgos": ["Vendiste unos 500 pesos mas que ayer.", "Mira {dato_inventado}.", "Refresco 2L se vendio bien."],
                      "atencion": [], "sugerencias": []}))
    r = resumir(db, "dia")
    assert [h["verificado"] for h in r["hallazgos"]] == [False, False, True]    # "500" suelto y clave inexistente; el '2' de Refresco 2L es inocente
    assert "[dato no disponible]" in r["hallazgos"][1]["texto"] and "no pudo verificar" in r["avisos"][0]


def test_poner_cifras_directo():
    d = {"a": "RD$1.00"}
    assert poner_cifras("Total {a}.", d) == ("Total RD$1.00.", True)
    assert poner_cifras("Total 5.", d)[1] is False
    assert poner_cifras("Pollo 10kg {a}", d, ("Pollo 10kg",)) == ("Pollo 10kg RD$1.00", True)


def test_sin_ventas_no_gasta_cuota(falso):
    f = falso()  # sin respuestas: si llamara al modelo, fallaria
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as vacia:
        r = resumir(vacia, "dia")
    assert "Sin ventas" in r["titular"] and r["modelo"] is None and f.llamadas == []
