"""Logica de negocio. La IA (etapa 2) llamara estas funciones: nunca calcula montos por su cuenta."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Abono, CajaCierre, Cliente, Compra, CompraItem, MovimientoStock, Producto, Proveedor, Venta, VentaItem


class ErrorNegocio(Exception):
    pass


class StockInsuficiente(ErrorNegocio):
    pass


class LimiteFiadoExcedido(ErrorNegocio):
    pass


def _mover(db: Session, producto: Producto, cantidad: Decimal, motivo: str, ref_id: int | None):
    producto.stock += cantidad
    db.add(MovimientoStock(producto_id=producto.id, cantidad=cantidad, motivo=motivo, ref_id=ref_id))


def saldo_cliente(db: Session, cliente_id: int) -> int:
    """Fiado pendiente en centavos: ventas fiadas no anuladas menos abonos."""
    fiado = db.scalar(select(func.coalesce(func.sum(Venta.total_centavos), 0)).where(
        Venta.cliente_id == cliente_id, Venta.metodo == "fiado", Venta.estado == "completada"))
    abonos = db.scalar(select(func.coalesce(func.sum(Abono.monto_centavos), 0)).where(Abono.cliente_id == cliente_id))
    return fiado - abonos


def registrar_venta(db: Session, items: list[tuple[int, Decimal]], metodo: str, usuario_id: int | None = None,
                    cliente_id: int | None = None, autoriza_exceso: bool = False) -> Venta:
    """items = [(producto_id, cantidad)]. El precio sale del producto, no del llamador."""
    if not items:
        raise ErrorNegocio("La venta no tiene productos")
    if metodo not in ("efectivo", "tarjeta", "fiado"):
        raise ErrorNegocio(f"Metodo invalido: {metodo}")
    cliente = db.get(Cliente, cliente_id) if cliente_id is not None else None
    if cliente_id is not None and cliente is None:
        raise ErrorNegocio("Cliente no existe")
    if metodo == "fiado" and cliente is None:
        raise ErrorNegocio("El fiado requiere cliente")

    # Se junta por producto: dos lineas del mismo producto no deben esquivar el control de stock.
    pedido: dict[int, Decimal] = {}
    for producto_id, cantidad in items:
        if Decimal(cantidad) <= 0:
            raise ErrorNegocio("La cantidad debe ser mayor que 0")
        pedido[producto_id] = pedido.get(producto_id, Decimal(0)) + Decimal(cantidad)

    venta = Venta(metodo=metodo, cliente_id=cliente_id, usuario_id=usuario_id, total_centavos=0)
    productos = []
    for producto_id, cantidad in pedido.items():
        p = db.get(Producto, producto_id)
        if p is None or not p.activo:
            raise ErrorNegocio(f"Producto {producto_id} no existe o esta inactivo")
        if p.stock < cantidad:
            raise StockInsuficiente(f"{p.nombre}: quedan {p.stock}, se piden {cantidad}")
        venta.items.append(VentaItem(producto_id=p.id, cantidad=cantidad,
                                     precio_centavos=p.precio_centavos, costo_centavos=p.costo_centavos))
        venta.total_centavos += round(p.precio_centavos * cantidad)
        productos.append((p, cantidad))

    if metodo == "fiado":
        if not autoriza_exceso and saldo_cliente(db, cliente_id) + venta.total_centavos > cliente.limite_fiado_centavos:
            raise LimiteFiadoExcedido(f"{cliente.nombre} pasaria su limite de fiado; requiere autorizacion del dueno")

    db.add(venta)
    db.flush()
    for p, cantidad in productos:
        _mover(db, p, -cantidad, "venta", venta.id)
    db.commit()
    return venta


def anular_venta(db: Session, venta_id: int) -> Venta:
    venta = db.get(Venta, venta_id)
    if venta is None or venta.estado == "anulada":
        raise ErrorNegocio("Venta no existe o ya esta anulada")
    venta.estado = "anulada"
    for it in venta.items:
        _mover(db, db.get(Producto, it.producto_id), it.cantidad, "anulacion", venta.id)
    db.commit()
    return venta


def registrar_abono(db: Session, cliente_id: int, monto_centavos: int, metodo: str = "efectivo") -> Abono:
    if monto_centavos <= 0:
        raise ErrorNegocio("El abono debe ser positivo")
    if monto_centavos > saldo_cliente(db, cliente_id):
        raise ErrorNegocio("El abono supera el saldo pendiente")
    abono = Abono(cliente_id=cliente_id, monto_centavos=monto_centavos, metodo=metodo)
    db.add(abono)
    db.commit()
    return abono


def registrar_compra(db: Session, proveedor_id: int, items: list[tuple[int, Decimal, int]], numero_factura: str | None = None) -> Compra:
    """items = [(producto_id, cantidad, costo_centavos)]. Actualiza stock y el ultimo costo.
    Con numero_factura, la misma factura del mismo proveedor no se registra dos veces (duplicaria el stock)."""
    if not items:
        raise ErrorNegocio("La compra no tiene productos")
    if db.get(Proveedor, proveedor_id) is None:
        raise ErrorNegocio("Proveedor no existe")
    numero_factura = (numero_factura or "").strip() or None
    if numero_factura:
        previa = db.scalar(select(Compra.id).where(Compra.proveedor_id == proveedor_id, Compra.numero_factura == numero_factura))
        if previa:
            raise ErrorNegocio(f"La factura {numero_factura} de este proveedor ya esta registrada (compra #{previa}).")
    compra = Compra(proveedor_id=proveedor_id, total_centavos=0, numero_factura=numero_factura)
    for producto_id, cantidad, costo in items:
        cantidad = Decimal(cantidad)
        if cantidad <= 0 or costo < 0:
            raise ErrorNegocio("Cantidad o costo invalidos")
        if db.get(Producto, producto_id) is None:
            raise ErrorNegocio(f"Producto {producto_id} no existe")
        compra.items.append(CompraItem(producto_id=producto_id, cantidad=cantidad, costo_centavos=costo))
        compra.total_centavos += round(costo * cantidad)
    db.add(compra)
    db.flush()
    for it in compra.items:
        p = db.get(Producto, it.producto_id)
        p.costo_centavos = it.costo_centavos
        _mover(db, p, it.cantidad, "compra", compra.id)
    db.commit()
    return compra


def ajustar_stock(db: Session, producto_id: int, cantidad: Decimal) -> None:
    """Merma o conteo: cantidad positiva o negativa."""
    p = db.get(Producto, producto_id)
    if p is None or p.stock + Decimal(cantidad) < 0:
        raise ErrorNegocio("Producto no existe o el ajuste dejaria stock negativo")
    _mover(db, p, Decimal(cantidad), "ajuste", None)
    db.commit()


def _rango(dia: date) -> tuple[datetime, datetime]:
    ini = datetime.combine(dia, time.min)
    return ini, ini + timedelta(days=1)


def _margen(v: Venta) -> int:
    return sum(round((i.precio_centavos - i.costo_centavos) * i.cantidad) for i in v.items)


def resumen_dia(db: Session, dia: date) -> dict:
    """Todo en centavos. Efectivo esperado en caja = ventas en efectivo + abonos en efectivo (sin fondo inicial ni gastos)."""
    ini, fin = _rango(dia)
    ventas = list(db.scalars(select(Venta).where(Venta.fecha >= ini, Venta.fecha < fin)))
    ok = [v for v in ventas if v.estado == "completada"]
    por_metodo = {m: sum(v.total_centavos for v in ok if v.metodo == m) for m in ("efectivo", "tarjeta", "fiado")}
    abonos = list(db.scalars(select(Abono).where(Abono.fecha >= ini, Abono.fecha < fin)))
    abonos_m = {m: sum(a.monto_centavos for a in abonos if a.metodo == m) for m in ("efectivo", "tarjeta")}
    esperado = por_metodo["efectivo"] + abonos_m["efectivo"]
    c = db.scalar(select(CajaCierre).where(CajaCierre.dia == dia))
    return {
        "dia": dia, "ventas": len(ok), "total_centavos": sum(por_metodo.values()), "por_metodo": por_metodo,
        "abonos": abonos_m, "anuladas": len(ventas) - len(ok), "esperado_efectivo_centavos": esperado,
        "margen_centavos": sum(_margen(v) for v in ok),
        "cierre": c and {"esperado_centavos": c.esperado_centavos, "contado_centavos": c.contado_centavos,
                         "diferencia_centavos": c.contado_centavos - c.esperado_centavos},
    }


def cerrar_caja(db: Session, dia: date, contado_centavos: int, usuario_id: int | None = None) -> CajaCierre:
    # shortcut: anular una venta despues del cierre no reabre la caja; el esperado guardado queda como estaba.
    if contado_centavos < 0:
        raise ErrorNegocio("El efectivo contado no puede ser negativo")
    if dia > date.today():
        raise ErrorNegocio("No se puede cerrar un dia futuro")
    if db.scalar(select(CajaCierre).where(CajaCierre.dia == dia)):
        raise ErrorNegocio("La caja de ese dia ya esta cerrada")
    c = CajaCierre(dia=dia, esperado_centavos=resumen_dia(db, dia)["esperado_efectivo_centavos"],
                   contado_centavos=contado_centavos, usuario_id=usuario_id)
    db.add(c)
    db.commit()
    return c


def reporte(db: Session, desde: date, hasta: date) -> dict:
    if desde > hasta or (hasta - desde).days > 366:
        raise ErrorNegocio("Rango de fechas invalido (maximo 1 ano)")
    ini, _ = _rango(desde)
    _, fin = _rango(hasta)
    # shortcut: agrega en Python todas las ventas del rango; si el rango crece mucho, pasar a GROUP BY en SQL.
    ventas = db.scalars(select(Venta).where(Venta.fecha >= ini, Venta.fecha < fin, Venta.estado == "completada"))
    dias: dict[date, dict] = {}
    top: dict[int, dict] = {}
    for v in ventas:
        d = dias.setdefault(v.fecha.date(), {"dia": v.fecha.date(), "ventas": 0, "total_centavos": 0, "margen_centavos": 0})
        d["ventas"] += 1
        d["total_centavos"] += v.total_centavos
        d["margen_centavos"] += _margen(v)
        for i in v.items:
            t = top.setdefault(i.producto_id, {"producto_id": i.producto_id, "cantidad": Decimal(0), "ingreso_centavos": 0})
            t["cantidad"] += i.cantidad
            t["ingreso_centavos"] += round(i.precio_centavos * i.cantidad)
    mas_vendidos = sorted(top.values(), key=lambda t: t["ingreso_centavos"], reverse=True)[:10]
    for t in mas_vendidos:
        t["nombre"] = db.get(Producto, t["producto_id"]).nombre
    por_cobrar = sum(max(saldo_cliente(db, cid), 0) for cid in db.scalars(select(Cliente.id)))
    return {"desde": desde, "hasta": hasta, "dias": [dias[k] for k in sorted(dias)], "mas_vendidos": mas_vendidos,
            "fiado_por_cobrar_centavos": por_cobrar}


def por_reponer(db: Session) -> list[Producto]:
    return list(db.scalars(select(Producto).where(Producto.activo, Producto.stock <= Producto.stock_minimo)
                           .order_by(Producto.proveedor_id, Producto.nombre)))
