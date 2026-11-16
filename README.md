# Inventario y ventas (colmado)

App de inventario y ventas para un colmado pequeno. Datos demo inventados. Contexto: `CONTEXTO.md`.

- `backend/`: FastAPI + SQLAlchemy 2 + Alembic + SQLite (pytest).
- `frontend/`: React + Vite (venta, fiado, reposicion). Proxy `/api` -> backend en el puerto 8000.

## Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest
```

## Probar la app (datos demo)

Terminal 1, backend (PowerShell; las claves demo las eliges tu, no se guardan en archivos):

```powershell
cd backend
$env:SEMILLA_CLAVE_DUENO="elige-una-clave"; $env:SEMILLA_PIN_CAJERO="1234"
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m app.semilla
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Terminal 2, frontend:

```bash
cd frontend
npm install
npm run dev
```

### IA (etapa 2, opcional)

Documentacion completa de la integracion, con diagramas, comparaciones y resultados: [docs/INTEGRACION_IA.md](docs/INTEGRACION_IA.md).

Necesita la variable de entorno `GEMINI_API_KEY` (nunca en archivos). Sin ella la app funciona igual y `/ia/*` responde 503.
La IA **propone y tu confirmas**: nunca escribe en la base ni calcula montos.

- Venta por texto: en Venta, caja "Armar venta" (`POST /ia/venta`) -> llena el carrito; tu pulsas Cobrar.
- Venta por voz: el boton del microfono de esa misma caja graba tu voz en el navegador, la convierte a WAV (16 kHz, mono) y el servidor la transcribe con Gemini (`POST /ia/transcribir`); el texto aparece en la caja, tu lo revisas y pulsas "Armar venta". Funciona en cualquier navegador con permiso de microfono (no usa el reconocimiento de voz del navegador, que falla con `network` en Brave, algunas VPN/firewalls y navegadores embebidos). Cuesta 1 peticion de cuota por dictado; el audio se envia a Gemini y no se guarda. Tope: 30 s. El navegador integrado de la app de escritorio bloquea el microfono: usa Chrome/Edge.
- Que falta comprar (solo dueno): en Reponer, "Sugerir compra" (`POST /ia/compras`). El modelo consulta tus datos con funciones propias (`ver_inventario`, `ventas_recientes`, `proponer_compra`); la app valida y calcula los costos; "Cargar en Compras" prellena el formulario y tu confirmas.
- Factura de proveedor por foto (solo dueno): en Compras, "Leer factura con foto" (`POST /ia/factura`, imagen JPG/PNG/WEBP de hasta 5 MB). Gemini transcribe lo impreso; la app valida, convierte a centavos, recalcula la suma y avisa de total que no cuadra, costos muy distintos al actual y facturas repetidas (el numero de factura es unico por proveedor). La foto se envia a Google: usa solo facturas de prueba. Hay dos de ejemplo en `demo/facturas/` (datos inventados).
- Resumen del dia o de los ultimos 7 dias (solo dueno): en Reportes, "Resumir" (`POST /ia/resumen`). La app calcula TODAS las cifras; la IA escribe marcadores `{clave}` que el servidor sustituye por el valor real, y cualquier cifra que el modelo escriba suelta se marca "no verificada". No se envian nombres de clientes ni costos unitarios. Sin ventas no se gasta cuota.
- Modelos (con respaldo): `gemini-3.5-flash-lite`, `3.1-flash-lite`, `2.5-flash-lite` (cambiar con `GEMINI_MODELOS="a,b"`).
- Las pruebas usan un Gemini falso (no gastan cuota).

Abrir http://localhost:5173 y entrar como `dueno` (clave) o `cajero` (PIN).
