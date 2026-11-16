import { useCallback, useEffect, useState } from 'react'
import { aCentavos, api, dinero } from './api'

const VACIO = { id: null, nombre: '', codigo_barras: '', precio: '', costo: '', stock_minimo: '0', unidad: 'und', proveedor_id: '', categoria_id: '' }
const aId = (v) => (v === '' ? null : Number(v))

export default function Productos() {
  const [productos, setProductos] = useState([])
  const [proveedores, setProveedores] = useState([])
  const [categorias, setCategorias] = useState([])
  const [f, setF] = useState(VACIO)
  const [ajuste, setAjuste] = useState({ id: null, cantidad: '' })
  const [error, setError] = useState('')

  const cargar = useCallback(async () => {
    const [p, pr, c] = await Promise.all([api('/productos'), api('/proveedores'), api('/categorias')])
    setProductos(p); setProveedores(pr); setCategorias(c)
  }, [])
  useEffect(() => { cargar().catch((e) => setError(e.mensaje)) }, [cargar])

  const intentar = (fn) => async (e) => {
    e?.preventDefault(); setError('')
    try { await fn(); await cargar() } catch (err) { setError(err.mensaje) }
  }

  const guardar = intentar(async () => {
    const body = {
      nombre: f.nombre, codigo_barras: f.codigo_barras || null, precio_centavos: aCentavos(f.precio), costo_centavos: aCentavos(f.costo),
      stock_minimo: f.stock_minimo || '0', unidad: f.unidad, proveedor_id: aId(f.proveedor_id), categoria_id: aId(f.categoria_id),
    }
    await api(f.id ? `/productos/${f.id}` : '/productos', { method: f.id ? 'PUT' : 'POST', body })
    setF(VACIO)
  })
  const ajustar = intentar(async () => {
    await api(`/productos/${ajuste.id}/ajuste`, { method: 'POST', body: { cantidad: ajuste.cantidad } })
    setAjuste({ id: null, cantidad: '' })
  })
  const desactivar = (p) => intentar(async () => {
    if (confirm(`Desactivar "${p.nombre}"? Su historial se conserva.`)) await api(`/productos/${p.id}`, { method: 'DELETE' })
  })()
  const editar = (p) => setF({ id: p.id, nombre: p.nombre, codigo_barras: p.codigo_barras ?? '', precio: p.precio_centavos / 100, costo: p.costo_centavos / 100,
    stock_minimo: String(Number(p.stock_minimo)), unidad: p.unidad, proveedor_id: p.proveedor_id ?? '', categoria_id: p.categoria_id ?? '' })
  const campo = (k) => ({ value: f[k], onChange: (e) => setF({ ...f, [k]: e.target.value }) })

  return (
    <div className="clientes">
      <section>
        <h2>Productos</h2>
        <table>
          <thead><tr><th>Producto</th><th>Precio</th><th>Costo</th><th>Stock</th><th></th></tr></thead>
          <tbody>
            {productos.map((p) => (
              <tr key={p.id}>
                <td>{p.nombre}</td><td>{dinero(p.precio_centavos)}</td><td>{dinero(p.costo_centavos)}</td>
                <td className={Number(p.stock) <= Number(p.stock_minimo) ? 'error' : ''}>{Number(p.stock)} {p.unidad}</td>
                <td className="fila">
                  <button onClick={() => editar(p)}>Editar</button>
                  <button onClick={() => setAjuste({ id: p.id, cantidad: '' })}>Ajustar</button>
                  <button onClick={() => desactivar(p)}>Quitar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {error && <p className="error">{error}</p>}
      </section>

      <aside>
        {ajuste.id && (
          <form onSubmit={ajustar} className="fila">
            <b>Ajuste de {productos.find((p) => p.id === ajuste.id)?.nombre}</b>
            <input required type="number" step="0.001" placeholder="+ entra / - merma" value={ajuste.cantidad}
              onChange={(e) => setAjuste({ ...ajuste, cantidad: e.target.value })} />
            <button className="primario">Aplicar</button>
            <button type="button" onClick={() => setAjuste({ id: null, cantidad: '' })}>Cancelar</button>
          </form>
        )}
        <h2>{f.id ? 'Editar producto' : 'Nuevo producto'}</h2>
        <form onSubmit={guardar} style={{ display: 'grid', gap: 8 }}>
          <input required placeholder="Nombre" {...campo('nombre')} />
          <input placeholder="Codigo de barras (opcional)" {...campo('codigo_barras')} />
          <input required type="number" min="0" step="0.01" placeholder="Precio RD$" {...campo('precio')} />
          <input required type="number" min="0" step="0.01" placeholder="Costo RD$" {...campo('costo')} />
          <input type="number" min="0" step="0.001" placeholder="Stock minimo" {...campo('stock_minimo')} />
          <select {...campo('unidad')}><option value="und">Unidad</option><option value="lb">Libra</option></select>
          <select {...campo('proveedor_id')}><option value="">Sin proveedor</option>{proveedores.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}</select>
          <select {...campo('categoria_id')}><option value="">Sin categoria</option>{categorias.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}</select>
          <button className="primario">{f.id ? 'Guardar cambios' : 'Crear producto'}</button>
          {f.id && <button type="button" onClick={() => setF(VACIO)}>Cancelar</button>}
          {!f.id && <small>El stock inicial se carga desde Compras o con Ajustar.</small>}
        </form>
      </aside>
    </div>
  )
}
