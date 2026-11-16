from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import Base, Cliente, Producto, Proveedor, Usuario
from app.seguridad import hashear


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(engine)
    with Sesion() as db:
        db.add_all([
            Usuario(nombre="dueno", rol="dueno", hash_clave=hashear("clave-demo")),
            Usuario(nombre="cajero", rol="cajero", hash_clave=hashear("1234")),
            Proveedor(id=1, nombre="Distribuidora Demo"),
            Cliente(id=1, nombre="Juan Demo", limite_fiado_centavos=20000),
        ])
        db.flush()
        db.add(Producto(id=1, nombre="Arroz (lb)", precio_centavos=3500, costo_centavos=2800, stock=D(10), unidad="lb"))
        db.commit()

    def _db():
        with Sesion() as db:
            yield db

    app.dependency_overrides[get_db] = _db
    yield TestClient(app)
    app.dependency_overrides.clear()


def entrar(client, nombre, clave):
    token = client.post("/login", json={"nombre": nombre, "clave": clave}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_malo_y_sin_token(client):
    assert client.post("/login", json={"nombre": "dueno", "clave": "mala"}).status_code == 401
    assert client.get("/productos").status_code == 401
    assert client.get("/productos", headers={"Authorization": "Bearer basura"}).status_code == 401


def test_cajero_no_ve_costos_ni_edita_precios(client):
    caj, due = entrar(client, "cajero", "1234"), entrar(client, "dueno", "clave-demo")
    assert "costo_centavos" not in client.get("/productos", headers=caj).json()[0]
    assert client.get("/productos", headers=due).json()[0]["costo_centavos"] == 2800
    nuevo = {"nombre": "X", "precio_centavos": 1, "costo_centavos": 1}
    assert client.post("/productos", json=nuevo, headers=caj).status_code == 403
    assert client.post("/compras", json={"proveedor_id": 1, "items": []}, headers=caj).status_code == 403
    assert client.post("/ventas/1/anular", headers=caj).status_code == 403
    assert client.post("/productos", json=nuevo, headers=due).status_code == 201


def test_venta_efectivo_y_stock(client):
    caj = entrar(client, "cajero", "1234")
    r = client.post("/ventas", json={"items": [{"producto_id": 1, "cantidad": "2.5"}], "metodo": "efectivo"}, headers=caj)
    assert r.status_code == 201 and r.json()["total_centavos"] == 8750
    assert "costo_centavos" not in r.json()["items"][0]
    assert float(client.get("/productos", headers=caj).json()[0]["stock"]) == 7.5


def test_stock_insuficiente_y_lineas_repetidas(client):
    caj = entrar(client, "cajero", "1234")
    dos_lineas = {"items": [{"producto_id": 1, "cantidad": 6}, {"producto_id": 1, "cantidad": 6}], "metodo": "efectivo"}
    r = client.post("/ventas", json=dos_lineas, headers=caj)  # 12 > 10: no debe esquivar el control
    assert r.status_code == 409 and r.json()["codigo"] == "stock_insuficiente"


def test_fiado_limite_y_autorizacion_del_dueno(client):
    caj, due = entrar(client, "cajero", "1234"), entrar(client, "dueno", "clave-demo")
    venta = {"items": [{"producto_id": 1, "cantidad": 7}], "metodo": "fiado", "cliente_id": 1}  # 24500 > 20000
    r = client.post("/ventas", json=venta, headers=caj)
    assert r.status_code == 409 and r.json()["codigo"] == "limite_fiado"
    assert client.post("/ventas", json={**venta, "autoriza_exceso": True}, headers=caj).status_code == 403
    assert client.post("/ventas", json={**venta, "autoriza_exceso": True}, headers=due).status_code == 201
    assert client.post("/clientes/1/abonos", json={"monto_centavos": 5000}, headers=caj).json()["saldo_centavos"] == 19500
    assert client.get("/clientes/1/cuenta", headers=caj).json()["saldo_centavos"] == 19500


def test_validaciones(client):
    caj = entrar(client, "cajero", "1234")
    assert client.post("/ventas", json={"items": [], "metodo": "efectivo"}, headers=caj).status_code == 422
    malo = {"items": [{"producto_id": 1, "cantidad": -1}], "metodo": "efectivo"}
    assert client.post("/ventas", json=malo, headers=caj).status_code == 422
    sin_cliente = {"items": [{"producto_id": 1, "cantidad": 1}], "metodo": "fiado"}
    assert client.post("/ventas", json=sin_cliente, headers=caj).status_code == 422
    assert client.post("/clientes", json={"nombre": "Ana", "limite_fiado_centavos": 999}, headers=caj).status_code == 403


def test_ia_venta_api(client, monkeypatch):
    from types import SimpleNamespace
    from app import ia
    assert client.post("/ia/venta", json={"texto": "dos arroz"}).status_code == 401
    caj = entrar(client, "cajero", "1234")
    salida = '{"items":[{"producto_id":1,"cantidad":2}],"no_encontrados":[],"metodo":"efectivo","cliente_id":null,"cliente_no_encontrado":null,"avisos":[]}'
    falso = SimpleNamespace(interactions=SimpleNamespace(create=lambda **kw: SimpleNamespace(output_text=salida)))
    monkeypatch.setattr(ia, "cliente", lambda: falso)
    r = client.post("/ia/venta", json={"texto": "dos de arroz, cash"}, headers=caj)
    assert r.status_code == 200 and r.json()["total_centavos"] == 7000 and "costo_centavos" not in r.json()["items"][0]
    assert client.get("/productos", headers=caj).json()[0]["stock"] == 10  # el borrador NO descuenta stock
    assert client.post("/ia/venta", json={"texto": "x"}, headers=caj).status_code == 422  # validacion de entrada
    monkeypatch.setattr(ia, "cliente", lambda: (_ for _ in ()).throw(ia.IANoDisponible("sin clave")))
    assert client.post("/ia/venta", json={"texto": "dos de arroz"}, headers=caj).status_code == 503


def test_ia_compras_api_solo_dueno(client, monkeypatch):
    from types import SimpleNamespace
    from app import ia
    pasos = [SimpleNamespace(type="function_call", name="proponer_compra", id="c1",
                             arguments={"proveedor_id": 1, "lineas": [{"producto_id": 1, "cantidad": 20}]})]
    turnos = [SimpleNamespace(id="i1", steps=pasos, output_text=""), SimpleNamespace(id="i2", steps=[], output_text="Compra arroz.")]
    falso = SimpleNamespace(interactions=SimpleNamespace(create=lambda **kw: turnos.pop(0)))
    monkeypatch.setattr(ia, "cliente", lambda: falso)
    caj, due = entrar(client, "cajero", "1234"), entrar(client, "dueno", "clave-demo")
    assert client.post("/ia/compras", json={}).status_code == 401
    assert client.post("/ia/compras", json={}, headers=caj).status_code == 403
    r = client.post("/ia/compras", json={"nota": "para la semana"}, headers=due)
    assert r.status_code == 200 and r.json()["propuestas"][0]["total_centavos"] == 56000  # 20 x 2800
    assert client.get("/productos", headers=due).json()[0]["stock"] == 10  # nada se escribio
    assert client.post("/ia/compras", json={"nota": "x" * 201}, headers=due).status_code == 422


def test_ia_factura_api(client, monkeypatch):
    import base64
    from types import SimpleNamespace
    from app import ia
    salida = ('{"legible":true,"proveedor":"Distribuidora Demo","proveedor_id":1,"numero_factura":"F-9","fecha":null,'
              '"lineas":[{"descripcion":"Arroz","cantidad":10,"costo_unitario":30,"producto_id":1}],"total":300.0,"avisos":[]}')
    monkeypatch.setattr(ia, "cliente", lambda: SimpleNamespace(interactions=SimpleNamespace(create=lambda **kw: SimpleNamespace(output_text=salida))))
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 300).decode()
    cuerpo = {"imagen": png, "mime_type": "image/png"}
    caj, due = entrar(client, "cajero", "1234"), entrar(client, "dueno", "clave-demo")
    assert client.post("/ia/factura", json=cuerpo).status_code == 401
    assert client.post("/ia/factura", json=cuerpo, headers=caj).status_code == 403
    r = client.post("/ia/factura", json=cuerpo, headers=due)
    assert r.status_code == 200 and r.json()["total_calculado_centavos"] == 30000 and r.json()["lineas"][0]["variacion_pct"] == 7.1
    assert client.get("/productos", headers=due).json()[0]["stock"] == 10  # leer no escribe nada
    assert client.post("/ia/factura", json={**cuerpo, "mime_type": "application/pdf"}, headers=due).status_code == 422
    falsa = {"imagen": base64.b64encode(b"GIF89a" + b"0" * 300).decode(), "mime_type": "image/png"}
    assert client.post("/ia/factura", json=falsa, headers=due).status_code == 422


def test_ia_resumen_api_solo_dueno(client, monkeypatch):
    from types import SimpleNamespace
    from app import ia
    salida = '{"titular":"Vendiste {total}","hallazgos":["{ventas_n} venta(s)."],"atencion":[],"sugerencias":[]}'
    monkeypatch.setattr(ia, "cliente", lambda: SimpleNamespace(interactions=SimpleNamespace(create=lambda **kw: SimpleNamespace(output_text=salida))))
    caj, due = entrar(client, "cajero", "1234"), entrar(client, "dueno", "clave-demo")
    assert client.post("/ia/resumen", json={}).status_code == 401
    assert client.post("/ia/resumen", json={}, headers=caj).status_code == 403
    assert client.post("/ia/resumen", json={"periodo": "mes"}, headers=due).status_code == 422
    assert client.post("/ia/resumen", json={}, headers=due).json()["modelo"] is None   # sin ventas: no llama al modelo
    client.post("/ventas", json={"items": [{"producto_id": 1, "cantidad": 2}], "metodo": "efectivo"}, headers=caj)
    r = client.post("/ia/resumen", json={"periodo": "dia"}, headers=due).json()
    assert r["titular"] == "Vendiste RD$70.00" and r["hallazgos"][0]["texto"] == "1 venta(s)." and r["kpis"][0]["valor"] == "RD$70.00"


def test_ia_transcribir_api(client, monkeypatch):
    import base64
    from types import SimpleNamespace
    from app import ia
    salida = '{"escuchado":true,"texto":"dos arroz cash"}'
    monkeypatch.setattr(ia, "cliente", lambda: SimpleNamespace(interactions=SimpleNamespace(create=lambda **kw: SimpleNamespace(output_text=salida))))
    wav = base64.b64encode(b"RIFF\x00\x00\x00\x00WAVE" + b"0" * 300).decode()
    caj = entrar(client, "cajero", "1234")
    assert client.post("/ia/transcribir", json={"audio": wav}).status_code == 401
    r = client.post("/ia/transcribir", json={"audio": wav}, headers=caj)   # el cajero tambien dicta ventas
    assert r.status_code == 200 and r.json()["texto"] == "dos arroz cash"
    assert client.post("/ia/transcribir", json={"audio": base64.b64encode(b"ID3" + b"0" * 300).decode()}, headers=caj).status_code == 422
    assert client.post("/ia/transcribir", json={"audio": "corto"}, headers=caj).status_code == 422


def test_recibo_de_venta(client):
    caj = entrar(client, "cajero", "1234")
    assert client.get("/ventas/1").status_code == 401
    client.post("/ventas", json={"items": [{"producto_id": 1, "cantidad": "2.5"}], "metodo": "efectivo"}, headers=caj)
    r = client.get("/ventas/1", headers=caj).json()
    assert r["numero"] == 1 and r["total_centavos"] == 8750 and r["atendido_por"] == "cajero" and r["saldo_fiado_centavos"] is None
    assert r["items"] == [{"nombre": "Arroz (lb)", "cantidad": 2.5, "precio_centavos": 3500, "subtotal_centavos": 8750}]  # sin costos
    client.post("/ventas", json={"items": [{"producto_id": 1, "cantidad": 1}], "metodo": "fiado", "cliente_id": 1}, headers=caj)
    f = client.get("/ventas/2", headers=caj).json()
    assert f["cliente"] == "Juan Demo" and f["saldo_fiado_centavos"] == 3500
    assert client.get("/ventas/99", headers=caj).status_code == 404


def test_caja_reportes_y_roles(client):
    from datetime import date
    caj, due = entrar(client, "cajero", "1234"), entrar(client, "dueno", "clave-demo")
    client.post("/ventas", json={"items": [{"producto_id": 1, "cantidad": 2}], "metodo": "efectivo"}, headers=caj)  # 7000
    assert "margen_centavos" not in client.get("/caja", headers=caj).json()
    r = client.get("/caja", headers=due).json()
    assert r["margen_centavos"] == 1400 and r["esperado_efectivo_centavos"] == 7000
    assert len(client.get("/ventas", headers=caj).json()) == 1
    cierre = client.post("/caja/cierre", json={"contado_centavos": 6900}, headers=caj)
    assert cierre.status_code == 201 and cierre.json()["diferencia_centavos"] == -100
    assert client.post("/caja/cierre", json={"contado_centavos": 6900}, headers=caj).status_code == 422
    hoy = date.today().isoformat()
    assert client.get(f"/reportes?desde={hoy}&hasta={hoy}", headers=caj).status_code == 403
    rep = client.get(f"/reportes?desde={hoy}&hasta={hoy}", headers=due).json()
    assert rep["dias"][0]["total_centavos"] == 7000
    assert client.get(f"/reportes?desde={hoy}&hasta=2000-01-01", headers=due).status_code == 422


def test_compra_reposicion_y_codigo_duplicado(client):
    due = entrar(client, "dueno", "clave-demo")
    assert [p["id"] for p in client.get("/reposicion", headers=due).json()] == []
    p = {"nombre": "Pollo", "precio_centavos": 9000, "costo_centavos": 7000, "stock_minimo": 5, "codigo_barras": "123"}
    nid = client.post("/productos", json=p, headers=due).json()["id"]
    assert [x["id"] for x in client.get("/reposicion", headers=due).json()] == [nid]  # stock 0 <= minimo 5
    assert client.post("/productos", json=p, headers=due).status_code == 409  # codigo repetido
    c = client.post("/compras", json={"proveedor_id": 1, "items": [{"producto_id": nid, "cantidad": 20, "costo_centavos": 7200}]}, headers=due)
    assert c.status_code == 201 and c.json()["total_centavos"] == 144000
    assert client.get("/reposicion", headers=due).json() == []
    cuerpo = {"proveedor_id": 1, "numero_factura": "F-77", "items": [{"producto_id": nid, "cantidad": 1, "costo_centavos": 100}]}
    assert client.post("/compras", json=cuerpo, headers=due).json()["numero_factura"] == "F-77"
    repetida = client.post("/compras", json=cuerpo, headers=due)
    assert repetida.status_code == 422 and "ya esta registrada" in repetida.json()["detail"]
