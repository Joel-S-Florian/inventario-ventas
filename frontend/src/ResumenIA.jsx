import { useState } from 'react'
import { api } from './api'
import Icon from './Icon'

function Lista({ titulo, items, clase }) {
  if (!items.length) return null
  return (
    <>
      <h3>{titulo}</h3>
      <ul className={clase}>
        {items.map((x, k) => (
          <li key={k}>{x.texto}{!x.verificado && <small className="error"> (cifra no verificada)</small>}</li>
        ))}
      </ul>
    </>
  )
}

// Las cifras las calcula la app y la IA solo redacta: el servidor sustituye cada {marcador} por el valor real.
export default function ResumenIA() {
  const [periodo, setPeriodo] = useState('dia')
  const [cargando, setCargando] = useState(false)
  const [r, setR] = useState(null)
  const [error, setError] = useState('')

  async function generar() {
    setError(''); setR(null); setCargando(true)
    try {
      setR(await api('/ia/resumen', { method: 'POST', body: { periodo } }))
    } catch (err) {
      setError(err.mensaje)
    } finally {
      setCargando(false)
    }
  }

  return (
    <section className="resumen-ia">
      <h2>Resumen con IA</h2>
      <div className="fila" style={{ marginTop: 0 }}>
        <div className="metodos" role="group" aria-label="Periodo" style={{ gridTemplateColumns: 'repeat(2, auto)' }}>
          {[['dia', 'Hoy'], ['semana', 'Ultimos 7 dias']].map(([id, texto]) => (
            <button key={id} className={periodo === id ? 'activa' : ''} onClick={() => { setPeriodo(id); setR(null) }}>{texto}</button>
          ))}
        </div>
        <button className="primario" style={{ width: 'auto', margin: 0 }} disabled={cargando} onClick={generar}>
          <Icon n="chispa" size={16} />{cargando ? 'Analizando...' : 'Resumir'}
        </button>
      </div>
      <small>Las cifras las calcula la app; la IA solo redacta. A Gemini se envian totales y nombres de productos, sin clientes.</small>
      {error && <p className="error" role="alert">{error}</p>}
      {cargando && <div className="esqueleto" style={{ height: 140 }} />}
      {r && (
        <div className="ia-nota" role="status">
          <b>{r.titular}</b> {r.modelo && <small>({r.modelo})</small>}
          <div className="kpis">
            {r.kpis.map((k) => <div key={k.etiqueta}><small>{k.etiqueta}</small><b>{k.valor}</b>{k.detalle && <small>{k.detalle}</small>}</div>)}
          </div>
          <Lista titulo="Hallazgos" items={r.hallazgos} />
          <Lista titulo="Requiere atencion" items={r.atencion} />
          <Lista titulo="Sugerencias" items={r.sugerencias} />
          {r.avisos.length > 0 && <p className="error">{r.avisos[0]}</p>}
        </div>
      )}
    </section>
  )
}
