import os
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import servicios as s
from .db import get_db
from .models import Abono, Categoria, Cliente, Producto, Proveedor, Usuario, Venta
from .seguridad import crear_token, solo_dueno, usuario_actual, verificar

router = APIRouter()
Centavos = Annotated[int, Field(ge=0)]
Cantidad = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]


# ---------- sesion ----------
class LoginIn(BaseModel):
    nombre: str
    clave: str  # clave (dueno) o PIN (cajero)


@router.post("/login")
def login(d: LoginIn, db: Session = Depends(get_db)):
    # shortcut: sin limite de intentos; un PIN corto es adivinable. Poner rate limit antes de exponerlo fuera de la LAN.
    u = db.scalar(select(Usuario).where(Usuario.nombre == d.nombre))
    if u is None or not verificar(d.clave, u.hash_clave):
        raise HTTPException(401, "Usuario o clave incorrectos")
    return {"token": crear_token(u), "rol": u.rol, "nombre": u.nombre}


# ---------- catalogo ----------
class NombreIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    telefono: str | None = None


@router.get("/categorias")
def listar_categorias(db: Session = Depends(get_db), _: Usuario = Depends(usuario_actual)):
    return [{"id": c.id, "nombre": c.nombre} for c in db.scalars(select(Categoria).order_by(Categoria.nombre))]


@router.post("/categorias", status_code=201)
def crear_categoria(d: NombreIn, db: Session = Depends(get_db), _: Usuario = Depends(solo_dueno)):
    c = Categoria(nombre=d.nombre)
    db.add(c)
    db.commit()
    return {"id": c.id, "nombre": c.nombre}


@router.get("/proveedores")
def listar_proveedores(db: Session = Depends(get_db), _: Usuario = Depends(solo_dueno)):
    return [{"id": p.id, "nombre": p.nombre, "telefono": p.telefono} for p in db.scalars(select(Proveedor))]


@router.post("/proveedores", status_code=201)
def crear_proveedor(d: NombreIn, db: Session = Depends(get_db), _: Usuario = Depends(solo_dueno)):
    p = Proveedor(nombre=d.nombre, telefono=d.telefono)
    db.add(p)
    db.commit()
    return {"id": p.id, "nombre": p.nombre, "telefono": p.telefono}


class ProductoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    codigo_barras: str | None = Field(default=None, min_length=1, max_length=40)
    precio_centavos: Centavos
    costo_centavos: Centavos
    stock_minimo: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)] = Decimal(0)
    unidad: Literal["und", "lb"] = "und"
    categoria_id: int | None = None
    proveedor_id: int | None = None


def _producto(p: Producto, u: Usuario) -> dict:
    d = {k: getattr(p, k) for k in ("id", "nombre", "codigo_barras", "precio_centavos", "stock", "stock_minimo",
                                    "unidad", "categoria_id", "proveedor_id")}
    if u.rol == "dueno":  # el cajero no ve costos
        d["costo_centavos"] = p.costo_centavos
    return d


@router.get("/productos")
def listar_productos(q: str | None = None, db: Session = Depends(get_db), u: Usuario = Depends(usuario_actual)):
    cons = select(Producto).where(Producto.activo).order_by(Producto.nombre)
    if q:
        cons = cons.where(or_(Producto.nombre.ilike(f"%{q}%"), Producto.codigo_barras == q))
    return [_producto(p, u) for p in db.scalars(cons)]


@router.post("/productos", status_code=201)
def crear_producto(d: ProductoIn, db: Session = Depends(get_db), u: Usuario = Depends(solo_dueno)):
    p = Producto(**d.model_dump())  # el stock inicial entra por compra o ajuste, para que quede en el historial
    db.add(p)
    db.commit()
    return _producto(p, u)


@router.put("/productos/{producto_id}")
def editar_producto(producto_id: int, d: ProductoIn, db: Session = Depends(get_db), u: Usuario = Depends(solo_dueno)):
    p = db.get(Producto, producto_id)
    if p is None:
        raise HTTPException(404, "Producto no existe")
    for k, v in d.model_dump().items():
        setattr(p, k, v)
    db.commit()
    return _producto(p, u)


@router.delete("/productos/{producto_id}", status_code=204)
def desactivar_producto(producto_id: int, db: Session = Depends(get_db), _: Usuario = Depends(solo_dueno)):
    p = db.get(Producto, producto_id)
    if p is None:
        raise HTTPException(404, "Producto no existe")
    p.activo = False  # no se borra: el historial de ventas lo referencia
    db.commit()


class AjusteIn(BaseModel):
    cantidad: Annotated[Decimal, Field(max_digits=12, decimal_places=3)]  # + o -


@router.post("/productos/{producto_id}/ajuste", status_code=204)
def ajustar(producto_id: int, d: AjusteIn, db: Session = Depends(get_db), _: Usuario = Depends(solo_dueno)):
    s.ajustar_stock(db, producto_id, d.cantidad)


@router.get("/reposicion")
def reposicion(db: Session = Depends(get_db), u: Usuario = Depends(usuario_actual)):
    return [_producto(p, u) for p in s.por_reponer(db)]


# ---------- clientes y fiado ----------
class ClienteIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    telefono: str | None = None
    limite_fiado_centavos: Centavos = 0


def _cliente(c: Cliente, db: Session) -> dict:
    return {"id": c.id, "nombre": c.nombre, "telefono": c.telefono,
            "limite_fiado_centavos": c.limite_fiado_centavos, "saldo_centavos": s.saldo_cliente(db, c.id)}


@router.get("/clientes")
def listar_clientes(db: Session = Depends(get_db), _: Usuario = Depends(usuario_actual)):
    return [_cliente(c, db) for c in db.scalars(select(Cliente).order_by(Cliente.nombre))]


@router.post("/clientes", status_code=201)
def crear_cliente(d: ClienteIn, db: Session = Depends(get_db), u: Usuario = Depends(usuario_actual)):
    if d.limite_fiado_centavos and u.rol != "dueno":
        raise HTTPException(403, "Solo el dueno fija el limite de fiado")
    c = Cliente(**d.model_dump())
    db.add(c)
    db.commit()
    return _cliente(c, db)


@router.put("/clientes/{cliente_id}")
def editar_cliente(cliente_id: int, d: ClienteIn, db: Session = Depends(get_db), _: Usuario = Depends(solo_dueno)):
    c = db.get(Cliente, cliente_id)
    if c is None:
        raise HTTPException(404, "Cliente no existe")
    for k, v in d.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return _cliente(c, db)


@router.get("/clientes/{cliente_id}/cuenta")
def cuenta(cliente_id: int, db: Session = Depends(get_db), _: Usuario = Depends(usuario_actual)):
    c = db.get(Cliente, cliente_id)
    if c is None:
        raise HTTPException(404, "Cliente no existe")
    ventas = db.scalars(select(Venta).where(Venta.cliente_id == c.id, Venta.metodo == "fiado").order_by(Venta.fecha))
    abonos = db.scalars(select(Abono).where(Abono.cliente_id == c.id).order_by(Abono.fecha))
    return {**_cliente(c, db),
            "ventas_fiadas": [{"id": v.id, "fecha": v.fecha, "total_centavos": v.total_centavos, "estado": v.estado} for v in ventas],
            "abonos": [{"id": a.id, "fecha": a.fecha, "monto_centavos": a.monto_centavos, "metodo": a.metodo} for a in abonos]}


class AbonoIn(BaseModel):
    monto_centavos: Annotated[int, Field(gt=0)]
    metodo: Literal["efectivo", "tarjeta"] = "efectivo"


@router.post("/clientes/{cliente_id}/abonos", status_code=201)
def abonar(cliente_id: int, d: AbonoIn, db: Session = Depends(get_db), _: Usuario = Depends(usuario_actual)):
    if db.get(Cliente, cliente_id) is None:
        raise HTTPException(404, "Cliente no existe")
    a = s.registrar_abono(db, cliente_id, d.monto_centavos, d.metodo)
    return {"id": a.id, "saldo_centavos": s.saldo_cliente(db, cliente_id)}


# ---------- ventas ----------
class ItemIn(BaseModel):
    producto_id: int
    cantidad: Cantidad


class VentaIn(BaseModel):
    items: list[ItemIn] = Field(min_length=1)
    metodo: Literal["efectivo", "tarjeta", "fiado"]
    cliente_id: int | None = None
    autoriza_exceso: bool = False


def _venta(v: Venta, u: Usuario) -> dict:
    items = []
    for i in v.items:
        d = {"producto_id": i.producto_id, "cantidad": i.cantidad, "precio_centavos": i.precio_centavos}
        if u.rol == "dueno":
            d["costo_centavos"] = i.costo_centavos
        items.append(d)
    return {"id": v.id, "fecha": v.fecha, "metodo": v.metodo, "total_centavos": v.total_centavos,
            "cliente_id": v.cliente_id, "estado": v.estado, "items": items}


@router.post("/ventas", status_code=201)
def crear_venta(d: VentaIn, db: Session = Depends(get_db), u: Usuario = Depends(usuario_actual)):
    # shortcut: el cajero no puede autorizar excesos en el momento; hace falta que el dueno repita la venta con su sesion.
    if d.autoriza_exceso and u.rol != "dueno":
        raise HTTPException(403, "Solo el dueno puede autorizar exceso de fiado")
    v = s.registrar_venta(db, [(i.producto_id, i.cantidad) for i in d.items], d.metodo, u.id, d.cliente_id, d.autoriza_exceso)
    return _venta(v, u)


@router.post("/ventas/{venta_id}/anular")
def anular(venta_id: int, db: Session = Depends(get_db), u: Usuario = Depends(solo_dueno)):
    return _venta(s.anular_venta(db, venta_id), u)


@router.get("/ventas")
def ventas_del_dia(dia: date | None = None, db: Session = Depends(get_db), _: Usuario = Depends(usuario_actual)):
    ini = datetime.combine(dia or date.today(), time.min)
    lista = db.scalars(select(Venta).where(Venta.fecha >= ini, Venta.fecha < ini + timedelta(days=1)).order_by(Venta.fecha.desc()))
    return [{"id": v.id, "fecha": v.fecha, "metodo": v.metodo, "total_centavos": v.total_centavos, "estado": v.estado,
             "cliente": (db.get(Cliente, v.cliente_id).nombre if v.cliente_id else None)} for v in lista]


NEGOCIO = os.environ.get("NEGOCIO_NOMBRE", "Colmado Demo")


@router.get("/ventas/{venta_id}")
def recibo(venta_id: int, db: Session = Depends(get_db), _: Usuario = Depends(usuario_actual)):
    """Datos del recibo. Sin costos: lo puede pedir el cajero. No es comprobante fiscal (sin NCF)."""
    v = db.get(Venta, venta_id)
    if v is None:
        raise HTTPException(404, "Venta no existe")
    cliente = db.get(Cliente, v.cliente_id) if v.cliente_id else None
    usuario = db.get(Usuario, v.usuario_id) if v.usuario_id else None
    return {
        "negocio": NEGOCIO, "numero": v.id, "fecha": v.fecha, "estado": v.estado, "metodo": v.metodo,
        "total_centavos": v.total_centavos, "atendido_por": usuario.nombre if usuario else None,
        "cliente": cliente.nombre if cliente else None,
        "saldo_fiado_centavos": s.saldo_cliente(db, cliente.id) if cliente and v.metodo == "fiado" else None,
        "items": [{"nombre": db.get(Producto, i.producto_id).nombre, "cantidad": i.cantidad, "precio_centavos": i.precio_centavos,
                   "subtotal_centavos": round(i.precio_centavos * i.cantidad)} for i in v.items],
    }


# ---------- caja y reportes ----------
@router.get("/caja")
def caja(dia: date | None = None, db: Session = Depends(get_db), u: Usuario = Depends(usuario_actual)):
    r = s.resumen_dia(db, dia or date.today())
    if u.rol != "dueno":
        r.pop("margen_centavos")  # el cajero no ve costos ni margen
    return r


class CierreIn(BaseModel):
    contado_centavos: Centavos


@router.post("/caja/cierre", status_code=201)
def cerrar(d: CierreIn, db: Session = Depends(get_db), u: Usuario = Depends(usuario_actual)):
    s.cerrar_caja(db, date.today(), d.contado_centavos, u.id)
    return s.resumen_dia(db, date.today())["cierre"]


@router.get("/reportes")
def reportes(desde: date, hasta: date, db: Session = Depends(get_db), _: Usuario = Depends(solo_dueno)):
    return s.reporte(db, desde, hasta)


# ---------- compras ----------
class CompraItemIn(BaseModel):
    producto_id: int
    cantidad: Cantidad
    costo_centavos: Centavos


class CompraIn(BaseModel):
    proveedor_id: int
    numero_factura: str | None = Field(default=None, max_length=40)
    items: list[CompraItemIn] = Field(min_length=1)


@router.post("/compras", status_code=201)
def comprar(d: CompraIn, db: Session = Depends(get_db), _: Usuario = Depends(solo_dueno)):
    c = s.registrar_compra(db, d.proveedor_id, [(i.producto_id, i.cantidad, i.costo_centavos) for i in d.items], d.numero_factura)
    return {"id": c.id, "total_centavos": c.total_centavos, "numero_factura": c.numero_factura}
