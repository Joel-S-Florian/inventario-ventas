# Inventario y ventas (con IA) - contexto de arranque

Para quien empiece el desarrollo (otra sesion de chat). Lee esto entero antes de escribir codigo.

## Que es
App web de **inventario y ventas para un colmado / tienda pequena** (contexto: Republica Dominicana). Se construye **desde cero, en este repo propio**, y en DOS etapas:
1. **Primero la app completa, sin IA.** Tiene que ser util por si sola.
2. **Despues la IA**, sobre una app que ya funciona.

Es el segundo de tres proyectos con IA de Joel (1: Gemini Code, hecho, falta refinarlo; 3: revisor de codigo / PRs).

## Reglas de Joel
- Espanol. Explicar paso a paso, un tema a la vez, marcando lo no verificado. Antes de construir: plan con sus ideas y propuestas; que el decida.
- **No commit ni push hasta que lo pida.** Mensajes `feat:/docs:/fix:`.
- Avisar (con tamano) antes de instalar o descargar cualquier cosa.
- **Nunca desplegar nada.** No usar datos reales ni secretos (datos demo inventados). La clave de Gemini va en `GEMINI_API_KEY` (variable de entorno), nunca en archivos ni commits.
- Confirmar antes de borrar. Mostrarle las salidas generadas.

## Aviso importante: solapamiento con Factos
Joel ya tiene **Factos** (punto de venta multiempresa con inventario por lotes, cierre de caja y facturacion DGII; React 19, Vite, Node, Express, Prisma, PostgreSQL; repo publico `Factos`, privado `Factos-app`). Este proyecto **no debe ser una copia**. Diferenciarlo: foco en el colmado pequeno (un solo local, ventas rapidas, **fiado** a clientes, reposicion simple) y, sobre todo, en la capa de IA. No juntar con EmpleadosSolution.

## Alcance propuesto de la app (sin IA) - MVP a confirmar con Joel
- Productos (precio, costo, stock, minimo, categoria, codigo de barras opcional), proveedores.
- Ventas rapidas (carrito, efectivo/tarjeta/**fiado**), clientes con saldo de fiado y abonos.
- Entradas de mercancia (compras a proveedores) y ajustes de inventario.
- Cierre de caja diario, reporte de ventas y de productos por agotarse.
- Usuarios con rol (dueno / cajero).

## Stack (PROPUESTA, confirmar al inicio)
Para ampliar el CV mas alla de Factos y porque el SDK de Gemini es mas completo en Python: **FastAPI + SQLAlchemy + PostgreSQL (SQLite en desarrollo) + React con Vite**, pruebas con pytest. Alternativa: repetir el stack de Factos (mas rapido, menos nuevo). Decidir con Joel antes de instalar nada.

## Etapa 2: ideas de IA (despues de que la app funcione)
- Registrar una venta en lenguaje natural o por voz ("dos pollos y una funda de arroz a Juan, fiado").
- "Que me falta comprar?" con razonamiento sobre ventas y minimos (preguntas sobre los datos con funciones propias, sin que el modelo calcule montos: llama a la app).
- Leer facturas de proveedores desde una foto (multimodal + salida estructurada) y proponer la entrada de mercancia para que el usuario la apruebe.
- Resumen del dia o de la semana. Probable: analisis con ejecucion de codigo.
- Reglas: la IA propone, la persona confirma antes de escribir datos; nunca montos inventados.

## Lo ya aprendido de la API de Gemini (repo `gemini-chat-prueba`, solo lectura)
Ruta: `C:\Users\Joel S. Florian\Documents\Desarrollo\gemini-chat-prueba` (remoto publico `LearnAboutGeminiAPI`). Leer `AGENTS.md`, `BITACORA.md` y `07-herramientas/manual-herramientas-t1-t7.md`. SDK Python `google-genai` 3.2.0. Lo mas util aqui:
- Salida estructurada con esquemas (`06-salida-estructurada`), entrada de imagenes (`02-multimodal-entendimiento`), funciones propias (`08-funciones-propias`).
- Combinar herramientas integradas con funciones: sin `signature` en la llamada de vuelta da 400.
- Cache implicito: `gemini-3.5-flash-lite` solo cachea con estado (`previous_interaction_id`).
- Nivel gratuito: algunas herramientas dan 429 / cuota 0 (Maps, `google_search` en Gemini 3, Batch). Verificar antes de depender de ellas.
- Consola de Windows (cp1252): forzar UTF-8 para imprimir simbolos.

## Primer paso en el chat nuevo
Plan antes de codigo: confirmar el stack, el MVP y el modelo de datos (diagrama Mermaid de tablas). Sin instalar nada hasta que Joel apruebe.
