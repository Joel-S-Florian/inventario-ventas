"""Motor de Gemini: cliente, respaldo entre modelos y reintentos.
La clave sale SOLO de la variable de entorno GEMINI_API_KEY (nunca de archivos). La IA propone; esta capa no escribe en la base."""
import json
import os
import random
import time

from pydantic import BaseModel, ValidationError

# Orden: primero los "lite" (mas cuota gratuita, ver BITACORA de gemini-chat-prueba). Se puede cambiar con GEMINI_MODELOS="a,b".
MODELOS = [m.strip() for m in os.environ.get("GEMINI_MODELOS", "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash-lite").split(",")]
TIMEOUT_MS = 45_000  # el timeout del SDK no es un tope total (reintenta por debajo): por eso hay ademas LIMITE_TOTAL_S
LIMITE_TOTAL_S = 60


class IAError(Exception):
    pass


class IANoDisponible(IAError):
    """Sin clave, sin cuota o servicio caido: el resto de la app sigue funcionando."""


_cliente = None


def cliente():
    global _cliente
    if _cliente is None:
        try:
            from google import genai
            _cliente = genai.Client(http_options={"timeout": TIMEOUT_MS})
        except Exception as e:  # sin GEMINI_API_KEY el SDK lanza al crear el cliente
            raise IANoDisponible("La IA no esta configurada (falta GEMINI_API_KEY).") from e
    return _cliente


def _con_respaldo(modelos, crear, validar=lambda r: r):
    """Prueba `crear(modelo)` en cada modelo. 429 -> siguiente modelo; 503/timeout -> reintento con espera;
    respuesta invalida -> siguiente modelo; 400 y similares -> error nuestro, no se reintenta."""
    inicio = time.monotonic()
    ultimo = "sin respuesta"
    for modelo in modelos:
        for intento in range(2):
            if time.monotonic() - inicio > LIMITE_TOTAL_S:
                raise IANoDisponible("La IA tardo demasiado. Intenta de nuevo.")
            try:
                return validar(crear(modelo)), modelo
            except ValidationError:
                ultimo = f"{modelo}: respuesta con formato invalido"
                break
            except Exception as e:
                codigo = getattr(e, "status_code", None)
                ultimo = f"{modelo}: {type(e).__name__} {codigo or ''}".strip()
                if codigo == 429:
                    break  # cuota de ese modelo agotada
                if codigo == 503 or type(e).__name__ == "APITimeoutError":
                    time.sleep(2**intento + random.random())
                    continue
                raise IAError(f"La IA rechazo la peticion ({ultimo}).") from e
    raise IANoDisponible(f"La IA no esta disponible ahora ({ultimo}).")


def generar(entrada, esquema: type[BaseModel], sistema: str) -> tuple[BaseModel, str]:
    """Una peticion que devuelve un JSON validado contra `esquema`. Devuelve (objeto, modelo que respondio)."""
    c = cliente()
    return _con_respaldo(
        MODELOS,
        lambda m: c.interactions.create(
            model=m, input=entrada, system_instruction=sistema,
            response_format={"type": "text", "mime_type": "application/json", "schema": esquema.model_json_schema()}),
        lambda r: esquema.model_validate_json(r.output_text),
    )


def bucle_funciones(entrada: str, herramientas: list[dict], ejecutar, sistema: str, max_turnos: int = 6):
    """Function calling con estado (previous_interaction_id): el modelo pide funciones, TU codigo las ejecuta (`ejecutar(nombre, argumentos) -> dict`)
    y le devuelve el resultado con el mismo call_id. Devuelve (texto final, modelo, peticiones, completo). Solo el primer turno usa respaldo de
    modelos; despues se sigue con el que respondio (la conversacion queda ligada a el)."""
    c = cliente()
    modelos, previo, peticiones = MODELOS, None, 0
    while peticiones < max_turnos:
        entrada_ahora = entrada
        r, modelo = _con_respaldo(modelos, lambda m: c.interactions.create(
            model=m, input=entrada_ahora, tools=herramientas, system_instruction=sistema, previous_interaction_id=previo))
        modelos, previo, peticiones = [modelo], r.id, peticiones + 1
        resultados = []
        for paso in r.steps:
            if paso.type == "function_call":
                salida = ejecutar(paso.name, dict(paso.arguments or {}))
                resultados.append({"type": "function_result", "name": paso.name, "call_id": paso.id,
                                   "result": [{"type": "text", "text": json.dumps(salida, default=str)}]})
        if not resultados:  # sin mas llamadas: es la respuesta final
            return r.output_text or "", modelo, peticiones, True
        entrada = resultados
    return "", modelos[0], peticiones, False  # se acabaron los turnos sin respuesta final
