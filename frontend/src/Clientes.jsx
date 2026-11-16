import { useCallback, useEffect, useState } from 'react'
import { aCentavos, api, dinero } from './api'

export default function Clientes({ rol }) {
  const [clientes, setClientes] = useState([])
  const [sel, setSel] = useState(null) // cuenta del cliente elegido
  const [nuevo, setNuevo] = useState({ nombre: '', telefono: '', limite: '' })
  const [abono, setAbono] = useState('')
  const [error, setError] = useState('')

  const cargar = useCallback(async () => setClientes(await api('/clientes')), [])
  useEffect(() => { cargar().catch((e) => setError(e.mensaje)) }, [cargar])

  const abrir = async (id) => setSel(await api(`/clientes/${id}/cuenta`))
  const intentar = (fn) => async (e) => {
    e.preventDefault(); setError('')
    try { await fn() } catch (err) { setError(err.mensaje) }
  }

  const crear = intentar(async () => {
    await api('/clientes', { method: 'POST', body: {
      nombre: nuevo.nombre, telefono: nuevo.telefono || null,
      limite_fiado_centavos: rol === 'dueno' && nuevo.limite ? aCentavos(nuevo.limite) : 0 } })
    setNuevo({ nombre: '', telefono: '', limite: '' })
    await cargar()
  })
  const abonar = intentar(async () => {
    await api(`/clientes/${sel.id}/abonos`, { method: 'POST', body: { monto_centavos: aCentavos(abono) } })
    setAbono('')
    await Promise.all([cargar(), abrir(sel.id)])
  })

  return (
    <div className="clientes">
      <section>
        <h2>Clientes</h2>
        <table>
          <thead><tr><th>Nombre</th><th>Debe</th><th>Limite</th></tr></thead>
          <tbody>
            {clientes.map((c) => (
              <tr key={c.id} onClick={() => abrir(c.id)} className={sel?.id === c.id ? 'activa' : ''}>
                <td>{c.nombre}</td><td>{dinero(c.saldo_centavos)}</td><td>{dinero(c.limite_fiado_centavos)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <form onSubmit={crear} className="fila">
          <input required placeholder="Nombre" value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} />
          <input placeholder="Telefono" value={nuevo.telefono} onChange={(e) => setNuevo({ ...nuevo, telefono: e.target.value })} />
          {rol === 'dueno' && <input type="number" min="0" placeholder="Limite RD$" value={nuevo.limite} onChange={(e) => setNuevo({ ...nuevo, limite: e.target.value })} />}
          <button>Agregar</button>
        </form>
        {error && <p className="error">{error}</p>}
      </section>

      {sel && (
        <aside>
          <h2>{sel.nombre}</h2>
          <p className="total">Debe {dinero(sel.saldo_centavos)}</p>
          <form onSubmit={abonar} className="fila">
            <input required type="number" min="0.01" step="0.01" placeholder="Abono RD$" value={abono} onChange={(e) => setAbono(e.target.value)} />
            <button className="primario">Abonar</button>
          </form>
          <h3>Fiados</h3>
          {sel.ventas_fiadas.map((v) => (
            <p key={v.id}>#{v.id} {new Date(v.fecha).toLocaleDateString('es-DO')} {dinero(v.total_centavos)} {v.estado === 'anulada' && '(anulada)'}</p>
          ))}
          <h3>Abonos</h3>
          {sel.abonos.map((a) => <p key={a.id}>{new Date(a.fecha).toLocaleDateString('es-DO')} {dinero(a.monto_centavos)}</p>)}
        </aside>
      )}
    </div>
  )
}
