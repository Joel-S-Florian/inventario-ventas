import { useCallback, useEffect, useState } from 'react'
import { aCentavos, api, dinero } from './api'
import Icon from './Icon'
import Recibo from './Recibo'

export default function Caja({ rol }) {
  const [r, setR] = useState(null)
  const [ventas, setVentas] = useState([])
  const [contado, setContado] = useState('')
  const [error, setError] = useState('')
  const [recibo, setRecibo] = useState(null)

  const cargar = useCallback(async () => {
    const [resumen, lista] = await Promise.all([api('/caja'), api('/ventas')])
    setR(resumen); setVentas(lista)
  }, [])
  useEffect(() => { cargar().catch((e) => setError(e.mensaje)) }, [cargar])

  const intentar = (fn) => async () => {
    setError('')
    try { await fn(); await cargar() } catch (e) { setError(e.mensaje) }
  }
  const cerrar = intentar(async () => {
    if (!confirm(`Cerrar la caja de hoy con ${dinero(aCentavos(contado))} contados? No se puede deshacer.`)) return
    await api('/caja/cierre', { method: 'POST', body: { contado_centavos: aCentavos(contado) } })
  })
  const anular = (v) => intentar(async () => {
    if (confirm(`Anular la venta #${v.id} de ${dinero(v.total_centavos)}? Devuelve el stock.`)) await api(`/ventas/${v.id}/anular`, { method: 'POST' })
  })()

  if (!r) return error ? <p className="error">{error}</p> : <div className="esqueleto" />
  const c = r.cierre
  return (
    <div className="clientes">
      <section>
        <h2>Ventas de hoy</h2>
        <table>
          <thead><tr><th>#</th><th>Hora</th><th>Pago</th><th>Cliente</th><th>Total</th><th></th></tr></thead>
          <tbody>
            {ventas.map((v) => (
              <tr key={v.id} style={{ cursor: 'default', opacity: v.estado === 'anulada' ? 0.5 : 1 }}>
                <td>{v.id}</td><td>{new Date(v.fecha).toLocaleTimeString('es-DO', { hour: '2-digit', minute: '2-digit' })}</td>
                <td>{v.metodo}</td><td>{v.cliente ?? ''}</td><td>{dinero(v.total_centavos)}</td>
                <td className="fila-acciones">
                  <button onClick={() => setRecibo(v.id)}><Icon n="recibo" size={15} />Recibo</button>
                  {v.estado === 'anulada' ? <span>anulada</span> : rol === 'dueno' && <button onClick={() => anular(v)}>Anular</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!ventas.length && <p>Aun no hay ventas hoy.</p>}
        {error && <p className="error">{error}</p>}
      </section>

      <aside>
        <h2>Caja</h2>
        <div className="kpis">
          <div><small>Ventas ({r.ventas}{r.anuladas > 0 && `, ${r.anuladas} anuladas`})</small><b>{dinero(r.total_centavos)}</b></div>
          <div><small>Efectivo</small><b>{dinero(r.por_metodo.efectivo)}</b></div>
          <div><small>Tarjeta</small><b>{dinero(r.por_metodo.tarjeta)}</b></div>
          <div><small>Fiado</small><b>{dinero(r.por_metodo.fiado)}</b></div>
          <div><small>Abonos</small><b>{dinero(r.abonos.efectivo + r.abonos.tarjeta)}</b></div>
          {r.margen_centavos !== undefined && <div><small>Margen</small><b>{dinero(r.margen_centavos)}</b></div>}
        </div>
        <p className="total">Efectivo esperado {dinero(r.esperado_efectivo_centavos)}</p>
        {c ? (
          <p className={c.diferencia_centavos === 0 ? 'ok' : 'error'}>
            Caja cerrada. Contado {dinero(c.contado_centavos)}: {c.diferencia_centavos === 0 ? 'cuadra' : c.diferencia_centavos > 0 ? `sobran ${dinero(c.diferencia_centavos)}` : `faltan ${dinero(-c.diferencia_centavos)}`}.
          </p>
        ) : (
          <>
            <label>Efectivo contado (RD$)
              <input type="number" min="0" step="0.01" value={contado} onChange={(e) => setContado(e.target.value)} />
            </label>
            <button className="primario" disabled={contado === ''} onClick={cerrar}>Cerrar caja</button>
          </>
        )}
      </aside>
      {recibo && <Recibo id={recibo} alCerrar={() => setRecibo(null)} />}
    </div>
  )
}
