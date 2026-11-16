import { useEffect, useState } from 'react'
import { api, dinero } from './api'
import Icon from './Icon'

export default function Reposicion({ rol, alUsar }) {
  const [lista, setLista] = useState(null)
  const [error, setError] = useState('')
  const [nota, setNota] = useState('')
  const [cargando, setCargando] = useState(false)
  const [sug, setSug] = useState(null)
  const [iaError, setIaError] = useState('')
  useEffect(() => { api('/reposicion').then(setLista).catch((e) => setError(e.mensaje)) }, [])

  // La IA solo PROPONE: el dueno revisa y confirma en Compras.
  async function sugerir(e) {
    e.preventDefault()
    setIaError(''); setSug(null); setCargando(true)
    try {
      setSug(await api('/ia/compras', { method: 'POST', body: { nota: nota.trim() || null } }))
    } catch (err) {
      setIaError(err.mensaje)
    } finally {
      setCargando(false)
    }
  }

  if (error) return <p className="error">{error}</p>
  if (!lista) return <div className="esqueleto" />
  return (
    <div className="reposicion">
      <h2>Por reponer</h2>
      {!lista.length && <p>Nada por reponer.</p>}
      {!!lista.length && (
        <table>
          <thead><tr><th>Producto</th><th>Stock</th><th>Minimo</th></tr></thead>
          <tbody>{lista.map((p) => <tr key={p.id}><td>{p.nombre}</td><td>{Number(p.stock)}</td><td>{Number(p.stock_minimo)}</td></tr>)}</tbody>
        </table>
      )}

      {rol === 'dueno' && (
        <section className="ia-compras">
          <h2>Que falta comprar</h2>
          <form className="ia-caja" onSubmit={sugerir}>
            <span className={cargando ? 'pulsa' : ''}><Icon n="chispa" /></span>
            <input aria-label="Nota para la IA" maxLength={200} value={nota} onChange={(e) => setNota(e.target.value)}
              placeholder='Opcional: "quiero cubrir 10 dias" o "esta semana hay fiesta"' />
            <button disabled={cargando}>{cargando ? 'Analizando...' : 'Sugerir compra'}</button>
          </form>
          {iaError && <p className="error" role="alert">{iaError}</p>}
          {sug && (
            <>
              <div className="ia-nota" role="status">
                <b>Analisis de la IA</b> <small>({sug.modelo}, {sug.peticiones} consultas)</small>
                {sug.resumen && <p>{sug.resumen}</p>}
                {sug.avisos.length > 0 && <ul>{sug.avisos.map((a, k) => <li key={k}>{a}</li>)}</ul>}
              </div>
              <div className="propuestas">
                {sug.propuestas.map((p) => (
                  <article className="propuesta" key={p.proveedor_id}>
                    <div><b>{p.proveedor}</b>{p.motivo && <small> {p.motivo}</small>}</div>
                    <table>
                      <thead><tr><th>Producto</th><th>Stock / min</th><th>Comprar</th><th>Costo est.</th></tr></thead>
                      <tbody>
                        {p.lineas.map((l) => (
                          <tr key={l.producto_id}>
                            <td>{l.nombre}
                              {l.sigue_bajo_minimo && <small className="error"> seguiria bajo el minimo</small>}
                              {l.otro_proveedor && <small> (suele venir de otro proveedor)</small>}
                            </td>
                            <td>{Number(l.stock)} / {Number(l.stock_minimo)}</td>
                            <td>{Number(l.cantidad)} {l.unidad}</td>
                            <td>{dinero(l.subtotal_centavos)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="fila">
                      <b style={{ flex: 1 }}>Total estimado {dinero(p.total_centavos)}</b>
                      <button className="primario" style={{ width: 'auto', margin: 0 }} onClick={() => alUsar(p)}>Cargar en Compras</button>
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}
        </section>
      )}
    </div>
  )
}
