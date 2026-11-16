import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import Usuario

# shortcut: sin JWT_SECRET se genera uno por arranque (las sesiones caducan al reiniciar); fijarlo por variable de entorno.
SECRETO = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)


def hashear(clave: str) -> str:
    return _hasher.hash(clave)


def verificar(clave: str, hash_: str) -> bool:
    try:
        return _hasher.verify(hash_, clave)
    except (VerifyMismatchError, InvalidHashError):
        return False


def crear_token(usuario: Usuario, horas: int = 12) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=horas)
    return jwt.encode({"sub": str(usuario.id), "exp": exp}, SECRETO, algorithm="HS256")


def usuario_actual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> Usuario:
    try:
        datos = jwt.decode(cred.credentials, SECRETO, algorithms=["HS256"]) if cred else None
    except jwt.PyJWTError:
        datos = None
    usuario = db.get(Usuario, int(datos["sub"])) if datos else None
    if usuario is None:
        raise HTTPException(401, "Sesion invalida o vencida")
    return usuario


def solo_dueno(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if usuario.rol != "dueno":
        raise HTTPException(403, "Solo el dueno puede hacer esto")
    return usuario
