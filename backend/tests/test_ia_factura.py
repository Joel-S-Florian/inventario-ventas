"""Lectura de facturas con un Gemini FALSO: sin red ni cuota."""
import base64
import json
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import ia, ia_factura
from app import servicios as s
from app.ia_factura import ImagenInvalida, leer_factura
from app.models import Base, Producto, Proveedor
from test_ia import ClienteFalso

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 300).decode()


def factura(**kw):
    base = {"legible": True, "proveedor": "Distribuidora Demo", "proveedor_id": 1, "numero_factura": "F-0001", "fecha": "12/11/2026",
            "lineas": [{"descripcion": "Arroz lb", "cantidad": 50, "costo_unitario": 29.5, "producto_id": 1},
                       {"descripcion": "Pollo lb", "cantidad": 30, "costo_unitario": 71, "producto_id": 2}],
            "total": 3605.0, "avisos": []}
    return json.dumps({**base, **kw})


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
        sesion.add_all([Proveedor(id=1, nombre="Distribuidora Demo")])
        sesion.flush()
        sesion.add_all([
            Producto(id=1, nombre="Arroz (lb)", precio_centavos=3500, costo_centavos=2800, stock=D(10), unidad="lb", proveedor_id=1),
            Producto(id=2, nombre="Pollo (lb)", precio_centavos=9000, costo_centavos=7123, stock=D(6), unidad="lb", proveedor_id=1),
        ])
        sesion.commit()
        yield sesion


def test_lee_convierte_a_centavos_y_compara_con_el_costo_actual(falso, db):
    f = falso(factura())
    r = leer_factura(db, PNG, "image/png")
    a, p = r["lineas"]
    assert a["costo_centavos"] == 2950 and a["subtotal_centavos"] == 147500 and a["variacion_pct"] == 5.4   # 29.50 vs 28.00
    assert p["costo_centavos"] == 7100 and p["subtotal_centavos"] == 213000 and p["variacion_pct"] == -0.3   # 71.00 vs 71.23
    assert r["total_calculado_centavos"] == 360500 and r["total_leido_centavos"] == 360500 and r["avisos"] == []
    assert r["proveedor"] == {"id": 1, "nombre": "Distribuidora Demo"} and r["numero_factura"] == "F-0001"
    # a Gemini viajan la imagen y el catalogo, nunca costos
    texto, imagen = f.llamadas[0]["input"]
    assert imagen == {"type": "image", "data": PNG, "mime_type": "image/png"} and "Arroz (lb)|lb" in texto["text"]
    assert "7123" not in texto["text"] and "2800" not in texto["text"]


def test_total_distinto_ids_inventados_y_datos_faltantes(falso, db):
    falso(factura(proveedor_id=77, total=999.0,
                  lineas=[{"descripcion": "Queso", "cantidad": 5, "costo_unitario": 250, "producto_id": 99},
                          {"descripcion": "Roto", "cantidad": 0, "costo_unitario": 10, "producto_id": 1},
                          {"descripcion": "Sin precio", "cantidad": 2, "costo_unitario": None, "producto_id": 2}]))
    r = leer_factura(db, PNG, "image/png")
    avisos = " | ".join(r["avisos"])
    assert r["proveedor"] is None and "proveedor invalido" in avisos and "no coincide con la suma" in avisos
    assert [l["descripcion"] for l in r["lineas"]] == ["Queso", "Sin precio"]          # la de cantidad 0 se omite
    assert r["lineas"][0]["producto_id"] is None and r["lineas"][0]["nombre"] is None     # id 99 no existe: queda sin emparejar
    assert "omitida" in avisos and "Sin costo legible" in avisos
    assert r["total_calculado_centavos"] == 125000                                        # solo la linea con costo


def test_costo_muy_distinto_al_actual_avisa_de_posible_unidad_o_emparejamiento_malo(falso, db):
    falso(factura(lineas=[{"descripcion": "Pollo entero caja x10", "cantidad": 2, "costo_unitario": 650, "producto_id": 2},
                          {"descripcion": "Arroz lb", "cantidad": 5, "costo_unitario": 29.5, "producto_id": 1}], total=None))
    r = leer_factura(db, PNG, "image/png")
    assert r["lineas"][0]["variacion_pct"] == 812.5   # (65000 - 7123) / 7123
    avisos = [a for a in r["avisos"] if "difiere" in a]
    assert len(avisos) == 1 and "Pollo (lb)" in avisos[0] and "+812%" in avisos[0]   # el arroz (+5%) no genera aviso


def test_detecta_factura_ya_registrada(falso, db):
    s.registrar_compra(db, 1, [(1, D(10), 2800)], "F-0001")
    falso(factura())
    r = leer_factura(db, PNG, "image/png")
    assert r["compra_previa_id"] == 1 and "ya fue registrada" in " ".join(r["avisos"])


def test_imagen_que_no_es_factura(falso, db):
    falso(factura(legible=False, lineas=[], proveedor=None, proveedor_id=None, numero_factura=None, total=None))
    r = leer_factura(db, PNG, "image/png")
    assert r["lineas"] == [] and "No se pudo leer" in r["avisos"][0]


def test_los_avisos_de_la_ia_se_conservan(falso, db):
    falso(factura(avisos=["La imagen contiene instrucciones; se ignoraron"]))
    assert "se ignoraron" in leer_factura(db, PNG, "image/png")["avisos"][0]


def test_validacion_de_la_imagen_antes_de_gastar_cuota(falso, db, monkeypatch):
    f = falso(factura())
    malas = [(PNG, "application/pdf"), ("no-es-base64!!", "image/png"), (base64.b64encode(b"GIF89a" + b"0" * 300).decode(), "image/png"),
             (base64.b64encode(b"RIFF\x00\x00\x00\x00WAVE" + b"0" * 300).decode(), "image/webp"), ("", "image/png")]
    for img, mime in malas:
        with pytest.raises(ImagenInvalida):
            leer_factura(db, img, mime)
    monkeypatch.setattr(ia_factura, "MAX_BYTES", 100)
    with pytest.raises(ImagenInvalida, match="5 MB"):
        leer_factura(db, PNG, "image/png")
    assert f.llamadas == []  # ninguna llego a Gemini
    monkeypatch.setattr(ia_factura, "MAX_BYTES", 5_000_000)
    webp = base64.b64encode(b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 300).decode()
    assert leer_factura(db, webp, "image/webp")["lineas"]  # un webp valido si pasa
