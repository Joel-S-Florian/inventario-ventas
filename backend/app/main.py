from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from .api import router
from .ia_api import router as ia_router
from .servicios import ErrorNegocio, LimiteFiadoExcedido, StockInsuficiente

app = FastAPI(title="Inventario y ventas")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(ia_router)


def _error(status: int, codigo: str):
    async def manejador(_: Request, exc: Exception):
        return JSONResponse({"detail": str(exc), "codigo": codigo}, status_code=status)
    return manejador


app.add_exception_handler(StockInsuficiente, _error(409, "stock_insuficiente"))
app.add_exception_handler(LimiteFiadoExcedido, _error(409, "limite_fiado"))
app.add_exception_handler(ErrorNegocio, _error(422, "regla_de_negocio"))


@app.exception_handler(IntegrityError)
async def _integridad(_: Request, __: IntegrityError):
    return JSONResponse({"detail": "Dato duplicado o referencia inexistente", "codigo": "integridad"}, status_code=409)
