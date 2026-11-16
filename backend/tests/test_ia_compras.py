"""'Que falta comprar' con un Gemini FALSO que llama funciones: sin red ni cuota."""
import json
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import ia
from app import servicios as s
from app.ia_compras import sugerir_compra
from app.models import Base, Producto, Proveedor


class ClienteFalso:
    """guion = lista de turnos: {'llamadas': [(nombre, args)], 'texto': str}. Guarda lo que recibe en cada turno."""
    def __init__(self, guion):
        self.guion, self.recibido = list(guion), []
        self.interactions = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.recibido.append(kw)
        t = self.guion.pop(0)
        pasos = [SimpleNamespace(type="function_call", name=n, arguments=a, id=f"c{len(self.recibido)}-{k}") for k, (n, a) in enumerate(t.get("llamadas", []))]
        return SimpleNamespace(id=f"i{len(self.recibido)}", steps=pasos, output_text=t.get("texto", ""))


@pytest.fixture
def falso(monkeypatch):
    def poner(guion):
        f = ClienteFalso(guion)
        monkeypatch.setattr(ia, "cliente", lambda: f)
        return f
    return poner


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as sesion:
        sesion.add_all([Proveedor(id=1, nombre="Distribuidora Demo"), Proveedor(id=2, nombre="Otro Proveedor")])
        sesion.flush()
        sesion.add_all([
            Producto(id=1, nombre="Arroz (lb)", precio_centavos=3500, costo_centavos=2800, stock=D(40), stock_minimo=D(20), unidad="lb", proveedor_id=1),
            Producto(id=2, nombre="Pollo (lb)", precio_centavos=9000, costo_centavos=7123, stock=D(6), stock_minimo=D(10), unidad="lb", proveedor_id=1),
        ])
        sesion.commit()
        s.registrar_venta(sesion, [(2, D(4))], "efectivo")  # pollo: stock 2, vendido 4 en la ventana
        yield sesion


def propuesta(prov, lineas, motivo="stock bajo"):
    return ("proponer_compra", {"proveedor_id": prov, "motivo": motivo, "lineas": lineas})


def test_el_modelo_consulta_propone_y_la_app_calcula_costos(falso, db):
    f = falso([
        {"llamadas": [("ver_inventario", {}), ("ventas_recientes", {"dias": 7})]},
        {"llamadas": [propuesta(1, [{"producto_id": 2, "cantidad": 20}])]},
        {"texto": "Hay que comprar pollo."},
    ])
    r = sugerir_compra(db, "quiero cubrir 10 dias")
    p = r["propuestas"][0]
    assert r["resumen"] == "Hay que comprar pollo." and r["peticiones"] == 3 and r["avisos"] == []
    assert p["proveedor"] == "Distribuidora Demo" and p["lineas"][0]["subtotal_centavos"] == 142460 and p["total_centavos"] == 142460  # 20 x 7123
    # turno 2 recibio los resultados de SUS llamadas, con el mismo call_id, y la conversacion sigue con previous_interaction_id
    t2 = f.recibido[1]
    assert t2["previous_interaction_id"] == "i1" and {x["call_id"] for x in t2["input"]} == {"c1-0", "c1-1"}
    datos = json.loads(t2["input"][1]["result"][0]["text"])
    assert datos["ventas"] == [{"producto_id": 2, "nombre": "Pollo (lb)", "vendido": 4.0, "promedio_diario": 0.571}]
    assert "dato" in f.recibido[0]["input"] and "10 dias" in f.recibido[0]["input"]


def test_el_modelo_nunca_ve_costos_ni_precios(falso, db):
    f = falso([{"llamadas": [("ver_inventario", {}), ("ventas_recientes", {"dias": 7})]}, {"llamadas": [propuesta(1, [{"producto_id": 2, "cantidad": 5}])]}, {"texto": "ok"}])
    sugerir_compra(db)
    visto = json.dumps([x["input"] for x in f.recibido], default=str)
    assert "7123" not in visto and "2800" not in visto and "9000" not in visto and "3500" not in visto


def test_errores_vuelven_al_modelo_y_no_entran(falso, db):
    f = falso([
        {"llamadas": [propuesta(1, [{"producto_id": 99, "cantidad": 5}]), propuesta(77, [{"producto_id": 1, "cantidad": 5}]),
                      propuesta(1, [{"producto_id": 1, "cantidad": -3}])]},
        {"llamadas": [propuesta(1, [{"producto_id": 2.0, "cantidad": 10}, {"producto_id": 2, "cantidad": 5}])]},  # id como float y linea repetida
        {"texto": "listo"},
    ])
    r = sugerir_compra(db)
    errores = [json.loads(x["result"][0]["text"]) for x in f.recibido[1]["input"]]
    assert all("error" in e for e in errores) and len(errores) == 3
    assert len(r["propuestas"]) == 1 and r["propuestas"][0]["lineas"][0]["cantidad"] == D("15")


def test_la_app_marca_si_la_compra_se_queda_corta(falso, db):
    falso([{"llamadas": [propuesta(1, [{"producto_id": 2, "cantidad": 5}, {"producto_id": 1, "cantidad": 1}])]}, {"texto": "ok"}])
    lineas = {l["producto_id"]: l for l in sugerir_compra(db)["propuestas"][0]["lineas"]}
    assert lineas[2]["sigue_bajo_minimo"] is True    # pollo: 2 + 5 = 7 < minimo 10
    assert lineas[1]["sigue_bajo_minimo"] is False   # arroz: 40 + 1 >= 20


def test_producto_de_otro_proveedor_se_marca(falso, db):
    falso([{"llamadas": [propuesta(2, [{"producto_id": 1, "cantidad": 10}])]}, {"texto": "ok"}])
    assert sugerir_compra(db)["propuestas"][0]["lineas"][0]["otro_proveedor"] is True


def test_sin_propuestas_y_con_bucle_infinito(falso, db):
    falso([{"llamadas": [("ver_inventario", {})]}, {"texto": "Todo bien."}])
    r = sugerir_compra(db)
    assert r["propuestas"] == [] and r["resumen"] == "Todo bien."
    falso([{"llamadas": [("ver_inventario", {})]}] * 6)  # el modelo no deja de llamar funciones
    r = sugerir_compra(db)
    assert r["peticiones"] == 6 and r["resumen"] == "" and "no termino" in r["avisos"][0]


def test_funcion_desconocida_no_rompe(falso, db):
    f = falso([{"llamadas": [("borrar_todo", {})]}, {"texto": "ok"}])
    sugerir_compra(db)
    assert "desconocida" in f.recibido[1]["input"][0]["result"][0]["text"]
