import { useCallback, useEffect, useState } from 'react'
import { aCentavos, api, dinero } from './api'
import FacturaFoto from './FacturaFoto'
import Icon from './Icon'

// Un borrador {proveedor_id, numero_factura, lineas:[{producto_id, cantidad, costo_centavos}]} viene de la IA (Reponer o factura por foto).
// Solo PRELLENA el formulario: la compra se registra cuando el dueno pulsa el boton.
function desdeBorrador(b) {
  const por = new Map() // dos lineas del mismo producto se fusionan (cantidad sumada, costo promedio ponderado)
  for (const l of b.lineas) {
    const cant = Number(l.cantidad)
    const previo = por.get(l.producto_id)
    por.set(l.producto_id, previo ? { cant: previo.cant + cant, importe: previo.importe + cant * l.costo_centavos } : { cant, importe: cant * l.costo_centavos })
  }
  return [...por].map(([producto_id, { cant, importe }]) => ({ producto_id, cantidad: String(cant), costo: Math.round(importe / cant) / 100 }))
}

export default function Compras({ borrador, alConsumir }) {
  const [proveedores, setProveedores] = useState([])
  const [productos, setProductos] = useState([])
  const [proveedorId, setProveedorId] = useState(() => (borrador?.proveedor_id ? String(borrador.proveedor_id) : ''))
  const [numeroFactura, setNumeroFactura] = useState(() => borrador?.numero_factura ?? '')
  const [lineas, setLineas] = useState(() => (borrador ? desdeBorrador(borrador) : [])) // [{producto_id, cantidad, costo (pesos)}]
  const [desdeIA, setDesdeIA] = useState(!!borrador)
  useEffect(() => { if (borrador) alConsumir() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const [nuevoProv, setNuevoProv] = useState('')
  const [aviso, setAviso] = useState(null)

  const cargar = useCallback(async () => {
    const [pr, p] = await Promise.all([api('/proveedores'), api('/productos')])
    setProveedores(pr); setProductos(p)
  }, [])
  useEffect(() => { cargar().catch((e) => setAviso({ tipo: 'error', texto: e.mensaje })) }, [cargar])

  const intentar = (fn) => async (e) => {
    e?.preventDefault(); setAviso(null)
    try { await fn(); await cargar() } catch (err) { setAviso({ tipo: 'error', texto: err.mensaje }) }
  }

  function usarFactura(b) {
    setProveedorId(b.proveedor_id ? String(b.proveedor_id) : '')
    setNumeroFactura(b.numero_factura ?? '')
    setLineas(desdeBorrador(b)); setDesdeIA(true); setAviso(null)
  }
  const agregarProveedor = intentar(async () => {
    const p = await api('/proveedores', { method: 'POST', body: { nombre: nuevoProv } })
    setNuevoProv(''); setProveedorId(String(p.id))
  })
  const agregarLinea = (id) => {
    const p = productos.find((x) => String(x.id) === id)
    if (p && !lineas.some((l) => l.producto_id === p.id)) setLineas([...lineas, { producto_id: p.id, cantidad: '1', costo: p.costo_centavos / 100 }])
  }
  const cambiar = (id, k, v) => setLineas(lineas.map((l) => (l.producto_id === id ? { ...l, [k]: v } : l)))
  const total = lineas.reduce((s, l) => s + Math.round(aCentavos(l.costo) * (parseFloat(l.cantidad) || 0)), 0) // vista previa

  const registrar = intentar(async () => {
    const c = await api('/compras', { method: 'POST', body: {
      proveedor_id: Number(proveedorId),
      numero_factura: numeroFactura.trim() || null,
      items: lineas.map((l) => ({ producto_id: l.producto_id, cantidad: String(l.cantidad), costo_centavos: aCentavos(l.costo) })) } })
    setLineas([]); setNumeroFactura(''); setDesdeIA(false)
    setAviso({ tipo: 'ok', texto: `Compra #${c.id}${c.numero_factura ? ` (factura ${c.numero_factura})` : ''} registrada: ${dinero(c.total_centavos)}. Stock y costos actualizados.` })
  })

  return (
    <div style={{ maxWidth: 720 }}>
      <FacturaFoto alUsar={usarFactura} />
      <h2>Entrada de mercancia</h2>
      {desdeIA && <div className="ia-nota">Borrador sugerido por la IA: revisa proveedor, cantidades y costos antes de registrar la compra.</div>}
      <div className="fila">
        <select value={proveedorId} onChange={(e) => setProveedorId(e.target.value)} aria-label="Proveedor">
          <option value="">Proveedor...</option>
          {proveedores.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
        </select>
        <input placeholder="Nuevo proveedor" value={nuevoProv} onChange={(e) => setNuevoProv(e.target.value)} />
        <button disabled={!nuevoProv.trim()} onClick={agregarProveedor}>Agregar</button>
      </div>
      <div className="fila">
        <input placeholder="Numero de factura (opcional, evita registrarla dos veces)" maxLength={40} value={numeroFactura}
          onChange={(e) => setNumeroFactura(e.target.value)} aria-label="Numero de factura" />
      </div>

      <div className="fila">
        <select value="" onChange={(e) => agregarLinea(e.target.value)}>
          <option value="">+ Agregar producto...</option>
          {productos.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
        </select>
      </div>

      {lineas.map((l) => (
        <div className="fila" key={l.producto_id}>
          <span style={{ flex: '1 1 160px' }}>{productos.find((p) => p.id === l.producto_id)?.nombre}</span>
          <input type="number" min="0" step="0.001" value={l.cantidad} onChange={(e) => cambiar(l.producto_id, 'cantidad', e.target.value)} aria-label="Cantidad" />
          <input type="number" min="0" step="0.01" value={l.costo} onChange={(e) => cambiar(l.producto_id, 'costo', e.target.value)} aria-label="Costo unitario RD$" />
          <button className="icono" aria-label="Quitar linea" onClick={() => setLineas(lineas.filter((x) => x.producto_id !== l.producto_id))}><Icon n="x" size={16} /></button>
        </div>
      ))}

      <p className="total">Total {dinero(total)}</p>
      {aviso && <p className={aviso.tipo === 'ok' ? 'ok' : 'error'}>{aviso.texto}</p>}
      <button className="primario" disabled={!proveedorId || !lineas.length} onClick={registrar}>Registrar compra</button>
    </div>
  )
}
