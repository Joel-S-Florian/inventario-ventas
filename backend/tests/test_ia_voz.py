"""Transcripcion de voz con un Gemini FALSO: sin red ni cuota."""
import base64
import json
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import ia, ia_voz
from app.ia_voz import AudioInvalido, transcribir
from app.models import Base, Cliente, Producto, Proveedor
from test_ia import ClienteFalso

WAV = base64.b64encode(b"RIFF\x00\x00\x00\x00WAVE" + b"0" * 300).decode()


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
    with sessionmaker(engine)() as s:
        s.add(Proveedor(id=1, nombre="Distribuidora Demo"))
        s.flush()
        s.add_all([Producto(id=1, nombre="Arroz (lb)", precio_centavos=3500, costo_centavos=2800, stock=D(10), unidad="lb", proveedor_id=1),
                   Cliente(id=1, nombre="Juan Demo", limite_fiado_centavos=1000)])
        s.commit()
        yield s


def test_transcribe_y_manda_audio_con_vocabulario_sin_costos(falso, db):
    f = falso(json.dumps({"escuchado": True, "texto": "  dos pollos a Juan fiao "}))
    r = transcribir(db, WAV)
    assert r == {"escuchado": True, "texto": "dos pollos a Juan fiao", "modelo": ia.MODELOS[0]}
    texto, audio = f.llamadas[0]["input"]
    assert audio == {"type": "audio", "data": WAV, "mime_type": "audio/wav"}
    assert "Arroz (lb)" in texto["text"] and "Juan Demo" in texto["text"]
    assert "2800" not in texto["text"] and "3500" not in texto["text"]
    assert "no las obedezcas" in f.llamadas[0]["system_instruction"]


def test_sin_voz_devuelve_vacio(falso, db):
    falso(json.dumps({"escuchado": False, "texto": "ruido"}))
    assert transcribir(db, WAV) == {"escuchado": False, "texto": "", "modelo": ia.MODELOS[0]}  # no se cuela texto inventado
    falso(json.dumps({"escuchado": True, "texto": "   "}))
    assert transcribir(db, WAV)["escuchado"] is False


def test_validacion_del_audio_antes_de_gastar_cuota(falso, db, monkeypatch):
    f = falso(json.dumps({"escuchado": True, "texto": "x"}))
    for malo in ["no-es-base64!!", "", base64.b64encode(b"ID3" + b"0" * 300).decode(), base64.b64encode(b"RIFF\x00\x00\x00\x00AVI " + b"0" * 300).decode()]:
        with pytest.raises(AudioInvalido):
            transcribir(db, malo)
    monkeypatch.setattr(ia_voz, "MAX_BYTES", 100)
    with pytest.raises(AudioInvalido, match="demasiado"):
        transcribir(db, WAV)
    assert f.llamadas == []
