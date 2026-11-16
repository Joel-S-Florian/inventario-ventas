from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

Cantidad = Numeric(12, 3)  # decimal: libras, etc. Dinero va en centavos (int).


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuario"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    rol: Mapped[str] = mapped_column(String(10))  # dueno | cajero
    hash_clave: Mapped[str] = mapped_column(String(200))  # clave (dueno) o PIN (cajero)


class Categoria(Base):
    __tablename__ = "categoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)


class Proveedor(Base):
    __tablename__ = "proveedor"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    telefono: Mapped[str | None] = mapped_column(String(30))


class Producto(Base):
    __tablename__ = "producto"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    codigo_barras: Mapped[str | None] = mapped_column(String(40), unique=True)
    precio_centavos: Mapped[int]
    costo_centavos: Mapped[int]
    stock: Mapped[Decimal] = mapped_column(Cantidad, default=Decimal(0))  # derivado de movimiento_stock
    stock_minimo: Mapped[Decimal] = mapped_column(Cantidad, default=Decimal(0))
    unidad: Mapped[str] = mapped_column(String(5), default="und")  # und | lb
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categoria.id"))
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedor.id"))
    activo: Mapped[bool] = mapped_column(default=True)


class Cliente(Base):
    __tablename__ = "cliente"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    telefono: Mapped[str | None] = mapped_column(String(30))
    limite_fiado_centavos: Mapped[int] = mapped_column(default=0)


class Venta(Base):
    __tablename__ = "venta"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[datetime] = mapped_column(default=datetime.now)
    metodo: Mapped[str] = mapped_column(String(10))  # efectivo | tarjeta | fiado
    total_centavos: Mapped[int]
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("cliente.id"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    estado: Mapped[str] = mapped_column(String(12), default="completada")  # completada | anulada
    items: Mapped[list["VentaItem"]] = relationship(back_populates="venta", cascade="all")


class VentaItem(Base):
    __tablename__ = "venta_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("venta.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    cantidad: Mapped[Decimal] = mapped_column(Cantidad)
    precio_centavos: Mapped[int]  # copia al vender
    costo_centavos: Mapped[int]  # copia al vender
    venta: Mapped[Venta] = relationship(back_populates="items")


class Abono(Base):
    __tablename__ = "abono"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"))
    monto_centavos: Mapped[int]
    metodo: Mapped[str] = mapped_column(String(10), default="efectivo")
    fecha: Mapped[datetime] = mapped_column(default=datetime.now)


class Compra(Base):
    __tablename__ = "compra"
    __table_args__ = (UniqueConstraint("proveedor_id", "numero_factura", name="uq_compra_factura"),)  # NULL se repite: solo cuenta si hay numero
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedor.id"))
    fecha: Mapped[datetime] = mapped_column(default=datetime.now)
    total_centavos: Mapped[int]
    numero_factura: Mapped[str | None] = mapped_column(String(40))  # evita registrar dos veces la misma factura
    items: Mapped[list["CompraItem"]] = relationship(cascade="all")


class CompraItem(Base):
    __tablename__ = "compra_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compra.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    cantidad: Mapped[Decimal] = mapped_column(Cantidad)
    costo_centavos: Mapped[int]


class MovimientoStock(Base):
    __tablename__ = "movimiento_stock"
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    cantidad: Mapped[Decimal] = mapped_column(Cantidad)  # + entra / - sale
    motivo: Mapped[str] = mapped_column(String(12))  # venta | compra | ajuste | anulacion
    ref_id: Mapped[int | None]  # venta/compra de origen
    fecha: Mapped[datetime] = mapped_column(default=datetime.now)


class CajaCierre(Base):
    __tablename__ = "caja_cierre"
    id: Mapped[int] = mapped_column(primary_key=True)
    dia: Mapped[date] = mapped_column(unique=True)
    esperado_centavos: Mapped[int]
    contado_centavos: Mapped[int]
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
