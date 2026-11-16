from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .db import get_db
from .ia import IAError, IANoDisponible
from .ia_compras import sugerir_compra
from .ia_factura import ImagenInvalida, leer_factura
from .ia_resumen import resumir
from .ia_voz import AudioInvalido, transcribir
from .ia_venta import interpretar_venta
from .models import Usuario
from .seguridad import solo_dueno, usuario_actual

router = APIRouter(prefix="/ia")


class TextoIn(BaseModel):
    texto: str = Field(min_length=2, max_length=500)


class NotaIn(BaseModel):
    nota: str | None = Field(default=None, max_length=200)


@router.post("/compras")
def compras_sugeridas(d: NotaIn, db: Session = Depends(get_db), _: Usuario = Depends(solo_dueno)):
    """Propuestas de compra por proveedor (nada se escribe). El dueno las revisa y las registra en Compras."""
    try:
        return sugerir_compra(db, d.nota)
    except IANoDisponible as e:
        raise HTTPException(503, str(e))
    except IAError as e:
        raise HTTPException(502, str(e))


class AudioIn(BaseModel):
    audio: str = Field(min_length=100, max_length=4_200_000)  # WAV en base64 (el audio real pesa hasta 3 MB)


@router.post("/transcribir")
def transcribir_voz(d: AudioIn, db: Session = Depends(get_db), _: Usuario = Depends(usuario_actual)):
    """Voz -> texto para la caja 'Armar venta'. No escribe nada; la persona revisa el texto antes de seguir."""
    try:
        return transcribir(db, d.audio)
    except AudioInvalido as e:
        raise HTTPException(422, str(e))
    except IANoDisponible as e:
        raise HTTPException(503, str(e))
    except IAError as e:
        raise HTTPException(502, str(e))


class ResumenIn(BaseModel):
    periodo: Literal["dia", "semana"] = "dia"


@router.post("/resumen")
def resumen_con_ia(d: ResumenIn, db: Session = Depends(get_db), _: Usuario = Depends(solo_dueno)):
    """Resumen del dia o de los ultimos 7 dias: cifras de la app, redaccion de la IA. Nada se escribe."""
    try:
        return resumir(db, d.periodo)
    except IANoDisponible as e:
        raise HTTPException(503, str(e))
    except IAError as e:
        raise HTTPException(502, str(e))


class FacturaIn(BaseModel):
    imagen: str = Field(min_length=100, max_length=7_000_000)  # base64 (la imagen real pesa hasta 5 MB)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]


@router.post("/factura")
def factura_por_foto(d: FacturaIn, db: Session = Depends(get_db), _: Usuario = Depends(solo_dueno)):
    """Lee la foto de una factura de proveedor y devuelve un BORRADOR (nada se escribe). La persona revisa y registra en Compras."""
    try:
        return leer_factura(db, d.imagen, d.mime_type)
    except ImagenInvalida as e:
        raise HTTPException(422, str(e))
    except IANoDisponible as e:
        raise HTTPException(503, str(e))
    except IAError as e:
        raise HTTPException(502, str(e))


@router.post("/venta")
def venta_por_texto(d: TextoIn, db: Session = Depends(get_db), _: Usuario = Depends(usuario_actual)):
    """Devuelve un BORRADOR de venta (nada se escribe). La persona confirma cobrando con POST /ventas."""
    try:
        return interpretar_venta(db, d.texto)
    except IANoDisponible as e:
        raise HTTPException(503, str(e))
    except IAError as e:
        raise HTTPException(502, str(e))
