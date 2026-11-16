import os
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

URL = os.environ.get("DATABASE_URL", "sqlite:///inventario.db")
engine = create_engine(URL, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(engine)


@event.listens_for(Engine, "connect")
def _fk_sqlite(conn, _):
    if isinstance(conn, sqlite3.Connection):  # SQLite no valida llaves foraneas si no se pide
        conn.execute("PRAGMA foreign_keys=ON")


def get_db():
    with SessionLocal() as db:
        yield db
