import { useEffect, useState } from 'react'
import { api, dinero } from './api'
import Icon from './Icon'

// Reduce la foto en el navegador (maximo 1600 px, JPEG): sube mas rapido y evita pasar el limite de tamano.
async function reducirImagen(archivo, max = 1600) {
  const bmp = await createImageBitmap(archivo)
  const esc = Math.min(1, max / Math.max(bmp.width, bmp.height))
  const c = document.createElement('canvas')
  c.width = Math.round(bmp.width * esc); c.height = Math.round(bmp.height * esc)
  const ctx = c.getContext('2d')
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height) // un PNG transparente saldria negro en JPEG
  ctx.drawImage(bmp, 0, 0, c.width, c.height)
  const blob = await new Promise((ok) => c.toBlob(ok, 'image/jpeg', 0.88))
  const b64 = await new Promise((ok) => { const fr = new FileReader(); fr.onload = () => ok(String(fr.result).split(',')[1]); fr.readAsDataURL(blob) })
  return { b64, url: URL.createObjectURL(blob) }
}

// La IA solo LEE la factura y propone; el dueno revisa y la compra se registra en el formulario de Compras.
export default function FacturaFoto({ alUsar }) {
  const [productos, setProductos] = useState([])
  const [foto, setFoto] = useState(null) // {b64, url}
  const [cargando, setCargando] = useState(false)
  const [lectura, setLectura] = useState(null)
  const [lineas, setLineas] = useState([]) // editable: [{...linea, elegido: 'id' | ''}]
  const [error, setError] = useState('')
  useEffect(() => { api('/productos').then(setProductos).catch(() => {}) }, [])
  useEffect(() => () => foto && URL.revokeObjectURL(foto.url), [foto])

  async function elegir(e) {
    const archivo = e.target.files[0]
    e.target.value = ''
    if (!archivo) return
    setError(''); setLectura(null)
    try { setFoto(await reducirImagen(archivo)) } catch { setError('No se pudo abrir esa imagen. Usa JPG, PNG o WEBP.') }
  }

  async function leer() {
    setError(''); setLectura(null); setCargando(true)
    try {
      const r = await api('/ia/factura', { method: 'POST', body: { imagen: foto.b64, mime_type: 'image/jpeg' } })
      setLectura(r)
      setLineas(r.lineas.map((l) => ({ ...l, elegido: l.producto_id ? String(l.producto_id) : '' })))
    } catch (err) {
      setError(err.mensaje)
    } finally {
      setCargando(false)
    }
  }

  const usables = lineas.filter((l) => l.elegido && l.costo_centavos != null)
  const bloqueada = !!lectura?.compra_previa_id

  function pasar() {
    alUsar({
      proveedor_id: lectura.proveedor?.id ?? null,
      numero_factura: lectura.numero_factura,
      lineas: usables.map((l) => ({ producto_id: Number(l.elegido), cantidad: l.cantidad, costo_centavos: l.costo_centavos })),
    })
    setFoto(null); setLectura(null); setLineas([])
  }

  return (
    <section className="factura-foto">
      <h2>Leer factura con foto</h2>
      <div className="fila" style={{ marginTop: 0 }}>
        <label className="boton-archivo">
          <Icon n="recibo" size={16} /> {foto ? 'Cambiar foto' : 'Elegir foto de la factura'}
          <input type="file" accept="image/*" onChange={elegir} hidden />
        </label>
        {foto && <button className="primario" style={{ width: 'auto', margin: 0 }} disabled={cargando} onClick={leer}>{cargando ? 'Leyendo...' : 'Leer factura'}</button>}
      </div>
      <small>La foto se envia a Gemini (Google) para leerla. Usa solo facturas de prueba o sin datos sensibles.</small>
      {error && <p className="error" role="alert">{error}</p>}
      {foto && <img className="vista-factura" src={foto.url} alt="Foto de la factura elegida" />}
      {cargando && <div className="esqueleto" style={{ height: 120 }} />}

      {lectura && (
        <div className="ia-nota" role="status">
          <b>Lectura de la IA</b> <small>({lectura.modelo})</small>: revisa antes de pasar a la compra.
          <p>Proveedor: <b>{lectura.proveedor?.nombre ?? 'no reconocido'}</b>{lectura.proveedor_leido && <small> (en la factura: {lectura.proveedor_leido})</small>}
            {' · '}Factura: <b>{lectura.numero_factura ?? 'sin numero'}</b>{lectura.fecha && <> · Fecha: {lectura.fecha}</>}</p>
          {lectura.avisos.length > 0 && <ul>{lectura.avisos.map((a, k) => <li key={k}>{a}</li>)}</ul>}
          {lineas.length > 0 && (
            <table>
              <thead><tr><th>En la factura</th><th>Producto</th><th>Cant.</th><th>Costo</th><th>vs actual</th></tr></thead>
              <tbody>
                {lineas.map((l, i) => (
                  <tr key={i} style={{ cursor: 'default' }}>
                    <td>{l.descripcion}</td>
                    <td>
                      <select aria-label={`Producto para ${l.descripcion}`} value={l.elegido}
                        onChange={(e) => setLineas(lineas.map((x, k) => (k === i ? { ...x, elegido: e.target.value } : x)))}>
                        <option value="">Sin emparejar (no se carga)</option>
                        {productos.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                      </select>
                    </td>
                    <td>{Number(l.cantidad)}</td>
                    <td>{l.costo_centavos != null ? dinero(l.costo_centavos) : '?'}</td>
                    <td className={Math.abs(l.variacion_pct) >= 15 ? 'error' : ''}>{l.variacion_pct != null ? `${l.variacion_pct > 0 ? '+' : ''}${l.variacion_pct}%` : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p>Suma de las lineas: <b>{dinero(lectura.total_calculado_centavos)}</b>
            {lectura.total_leido_centavos != null && <> · Total impreso: <b>{dinero(lectura.total_leido_centavos)}</b></>}</p>
          {lineas.length > usables.length && <p>{lineas.length - usables.length} linea(s) sin producto o sin costo no se cargaran.</p>}
          <button className="primario" style={{ width: 'auto', margin: 0 }} disabled={!usables.length || bloqueada} onClick={pasar}>
            {bloqueada ? 'Factura ya registrada' : 'Pasar a la compra'}
          </button>
        </div>
      )}
    </section>
  )
}
