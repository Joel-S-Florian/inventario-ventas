import { useCallback, useEffect, useState } from 'react'
import { api, dinero, fechaLocal } from './api'
import ResumenIA from './ResumenIA'

export default function Reportes() {
  const [desde, setDesde] = useState(() => fechaLocal(new Date(Date.now() - 6 * 864e5)))
  const [hasta, setHasta] = useState(() => fechaLocal())
  const [rep, setRep] = useState(null)
  const [error, setError] = useState('')

  const cargar = useCallback(async () => {
    setError('')
    try { setRep(await api(`/reportes?desde=${desde}&hasta=${hasta}`)) } catch (e) { setError(e.mensaje); setRep(null) }
  }, [desde, hasta])
  useEffect(() => { cargar() }, [cargar])

  const suma = (k) => rep.dias.reduce((s, d) => s + d[k], 0)
  return (
    <div style={{ maxWidth: 760 }}>
      <ResumenIA />
      <h2>Reportes</h2>
      <div className="fila">
        <label>Desde <input type="date" value={desde} max={hasta} onChange={(e) => setDesde(e.target.value)} /></label>
        <label>Hasta <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} /></label>
      </div>
      {error && <p className="error">{error}</p>}
      {rep && (
        <>
          <div className="kpis">
            <div><small>Ventas</small><b>{dinero(suma('total_centavos'))}</b></div>
            <div><small>Margen</small><b>{dinero(suma('margen_centavos'))}</b></div>
            <div><small>Fiado por cobrar</small><b>{dinero(rep.fiado_por_cobrar_centavos)}</b></div>
          </div>
          <h3>Ventas por dia</h3>
          {!rep.dias.length ? <p>Sin ventas en este rango.</p> : (
            <table>
              <thead><tr><th>Dia</th><th>Ventas</th><th>Total</th><th>Margen</th></tr></thead>
              <tbody>
                {rep.dias.map((d) => <tr key={d.dia} style={{ cursor: 'default' }}><td>{d.dia}</td><td>{d.ventas}</td><td>{dinero(d.total_centavos)}</td><td>{dinero(d.margen_centavos)}</td></tr>)}
                <tr style={{ cursor: 'default' }}><th>Total</th><th>{suma('ventas')}</th><th>{dinero(suma('total_centavos'))}</th><th>{dinero(suma('margen_centavos'))}</th></tr>
              </tbody>
            </table>
          )}
          <h3>Mas vendidos</h3>
          {rep.mas_vendidos.map((p) => <p key={p.producto_id}>{p.nombre}: {Number(p.cantidad)} ({dinero(p.ingreso_centavos)})</p>)}
        </>
      )}
    </div>
  )
}
