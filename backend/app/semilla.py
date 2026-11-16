"""Datos demo inventados. Uso: python -m app.semilla  (tras `alembic upgrade head`).
Claves: SEMILLA_CLAVE_DUENO y SEMILLA_PIN_CAJERO; si faltan se generan al azar y se imprimen una sola vez."""
import os
import secrets
from decimal import Decimal as D

from sqlalchemy import select

from . import servicios as s
from .db import SessionLocal
from .models import Categoria, Cliente, Producto, Proveedor, Usuario
from .seguridad import hashear


def main():
    clave = os.environ.get("SEMILLA_CLAVE_DUENO") or secrets.token_urlsafe(9)
    pin = os.environ.get("SEMILLA_PIN_CAJERO") or f"{secrets.randbelow(10**4):04d}"
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        raise SystemExit("El PIN del cajero debe tener 4 a 6 digitos")
    with SessionLocal() as db:
        if db.scalar(select(Usuario.id).limit(1)):
            raise SystemExit("La base ya tiene usuarios; no se siembra de nuevo")
        db.add_all([Usuario(nombre="dueno", rol="dueno", hash_clave=hashear(clave)),
                    Usuario(nombre="cajero", rol="cajero", hash_clave=hashear(pin)),
                    Categoria(id=1, nombre="Granos"), Categoria(id=2, nombre="Carnes"), Categoria(id=3, nombre="Bebidas"),
                    Proveedor(id=1, nombre="Distribuidora Demo", telefono="809-555-0100"),
                    Cliente(id=1, nombre="Juan Demo", telefono="809-555-0101", limite_fiado_centavos=100000)])
        db.flush()
        db.add_all([
            Producto(nombre="Arroz (lb)", precio_centavos=3500, costo_centavos=2800, stock_minimo=D(20), unidad="lb", categoria_id=1, proveedor_id=1),
            Producto(nombre="Pollo (lb)", precio_centavos=9000, costo_centavos=7000, stock_minimo=D(10), unidad="lb", categoria_id=2, proveedor_id=1),
            Producto(nombre="Refresco 2L", codigo_barras="0000000000017", precio_centavos=11000, costo_centavos=8500, stock_minimo=D(6), categoria_id=3, proveedor_id=1),
        ])
        db.commit()
        s.registrar_compra(db, 1, [(1, D(50), 2800), (2, D(30), 7000), (3, D(12), 8500)])  # stock inicial con historial
    print(f"Usuarios demo creados.\n  dueno  / clave: {clave}\n  cajero / PIN:   {pin}")


if __name__ == "__main__":
    main()
