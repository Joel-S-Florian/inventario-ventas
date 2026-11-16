import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { aCentavos, api, dinero } from './api'
import { hayDictado, iniciarGrabacion, MAX_SEGUNDOS, mensajeError } from './dictado'
import Icon from './Icon'
import Recibo from './Recibo'

export default function Venta({ rol }) {
  const [productos, setProductos] = useState([])
  const [clientes, setClientes] = useState([])
  const [q, setQ] = useState('')
  const [carrito, setCarrito] = useState([]) // [{p, cantidad: texto}]
  const [metodo, setMetodo] = useState('efectivo')
  const [clienteId, setClienteId] = useState('')
  const [recibido, setRecibido] = useState('')
  const [aviso, setAviso] = useState(null) // {tipo: 'ok'|'error', texto, codigo, id}
  const [recibo, setRecibo] = useState(null)
  const [iaTexto, setIaTexto] = useState('')
  const [iaCargando, setIaCargando] = useState(false)
  const [grabando, setGrabando] = useState(false)
  const [transcribiendo, setTranscribiendo] = useState(false)
  const rec = useRef(null)
  const alternarRef = useRef(null)
  useEffect(() => () => rec.current?.cancelar(), []) // al salir de la pantalla se apaga el microfono
  useEffect(() => { // tope de duracion: se detiene solo y transcribe
    if (!grabando) return undefined
    const t = setTimeout(() => alternarRef.current(), MAX_SEGUNDOS * 1000)
    return () => clearTimeout(t)
  }, [grabando])
  const [propuesta, setPropuesta] = useState(null) // borrador de la IA: {avisos, no_encontrados, cliente_no_encontrado, modelo}

  const cargar = useCallback(async () => {
    const [p, c] = await Promise.all([api('/productos'), api('/clientes')])
    setProductos(p)
    setClientes(c)
  }, [])
  useEffect(() => { cargar().catch((e) => setAviso({ tipo: 'error', texto: e.mensaje })) }, [cargar])

  const visibles = useMemo(() => {
    const t = q.trim().toLowerCase()
    return t ? productos.filter((p) => p.nombre.toLowerCase().includes(t) || p.codigo_barras === q.trim()) : productos
  }, [productos, q])

  const num = (l) => parseFloat(l.cantidad) || 0
  // Solo vista previa: el total oficial lo calcula el servidor al cobrar.
  const total = carrito.reduce((s, l) => s + Math.round(l.p.precio_centavos * num(l)), 0)
  const cliente = clientes.find((c) => String(c.id) === clienteId)
  const excede = metodo === 'fiado' && cliente && cliente.saldo_centavos + total > cliente.limite_fiado_centavos

  function agregar(p) {
    setAviso(null)
    setCarrito((c) => c.some((l) => l.p.id === p.id)
      ? c.map((l) => (l.p.id === p.id ? { ...l, cantidad: String(num(l) + 1) } : l))
      : [...c, { p, cantidad: '1' }])
    setQ('')
  }
  const cambiar = (id, cantidad) => setCarrito((c) => c.map((l) => (l.p.id === id ? { ...l, cantidad } : l)))
  const quitar = (id) => setCarrito((c) => c.filter((l) => l.p.id !== id))
  const paso = (l, d) => { // + / - del carrito; al llegar a 0 la linea se quita
    const n = Number((num(l) + d).toFixed(3))
    if (n > 0) cambiar(l.p.id, String(n)); else quitar(l.p.id)
  }

  // El dictado solo ESCRIBE en la caja de texto: la persona lo revisa y pulsa "Armar venta" (a ese paso entra la IA).
  // Primer toque: graba. Segundo toque: detiene y el servidor transcribe el audio con Gemini.
  async function alternarDictado() {
    if (grabando) {
      setGrabando(false); setTranscribiendo(true)
      try {
        const audio = await rec.current.detener()
        const r = await api('/ia/transcribir', { method: 'POST', body: { audio } })
        if (r.escuchado) setIaTexto(r.texto)
        else setAviso({ tipo: 'error', texto: 'No se entendio nada. Habla mas cerca del microfono e intenta de nuevo.' })
      } catch (err) {
        setAviso({ tipo: 'error', texto: err.mensaje ?? err.message ?? 'No se pudo transcribir el audio.' })
      } finally {
        rec.current = null; setTranscribiendo(false)
      }
      return
    }
    setAviso(null); setPropuesta(null)
    try {
      rec.current = await iniciarGrabacion()
      setGrabando(true)
    } catch (err) {
      setAviso({ tipo: 'error', texto: mensajeError(err) })
    }
  }
  alternarRef.current = alternarDictado

  // La IA solo PROPONE: llena el carrito y el pago; el dinero se mueve cuando la persona pulsa Cobrar.
  async function armarConIA(e) {
    e.preventDefault()
    setAviso(null); setPropuesta(null); setIaCargando(true)
    try {
      const r = await api('/ia/venta', { method: 'POST', body: { texto: iaTexto } })
      setCarrito(r.items.flatMap((i) => {
        const p = productos.find((x) => x.id === i.producto_id)
        return p ? [{ p, cantidad: String(Number(i.cantidad)) }] : []
      }))
      if (r.metodo) setMetodo(r.metodo)
      setClienteId(r.cliente ? String(r.cliente.id) : '')
      setRecibido('')
      setPropuesta(r)
      setIaTexto('')
    } catch (err) {
      setAviso({ tipo: 'error', texto: err.mensaje })
    } finally {
      setIaCargando(false)
    }
  }

  function alEnter(e) {
    if (e.key === 'Enter' && visibles.length) { e.preventDefault(); agregar(visibles[0]) } // escaner o primer resultado
  }

  async function cobrar(autoriza_exceso = false) {
    setAviso(null)
    try {
      const v = await api('/ventas', {
        method: 'POST',
        body: {
          items: carrito.map((l) => ({ producto_id: l.p.id, cantidad: String(num(l)) })),
          metodo,
          cliente_id: metodo === 'fiado' ? Number(clienteId) : null,
          autoriza_exceso,
        },
      })
      setAviso({ tipo: 'ok', texto: `Venta #${v.id} cobrada: ${dinero(v.total_centavos)}`, id: v.id })
      setCarrito([]); setRecibido(''); setClienteId(''); setPropuesta(null)
      await cargar()
    } catch (e) {
      setAviso({ tipo: 'error', texto: e.mensaje, codigo: e.codigo })
      if (e.codigo === 'stock_insuficiente') cargar()
    }
  }

  const vuelto = aCentavos(recibido) - total
  const listo = carrito.length > 0 && carrito.every((l) => num(l) > 0) && (metodo !== 'fiado' || clienteId)

  return (
    <div className="venta">
      <section>
        <form className="ia-caja" onSubmit={armarConIA}>
          <span className={iaCargando || transcribiendo ? 'pulsa' : ''}><Icon n="chispa" /></span>
          <input aria-label="Vender con texto" maxLength={500} value={iaTexto} onChange={(e) => setIaTexto(e.target.value)} disabled={grabando || transcribiendo}
            placeholder={grabando ? 'Escuchando... toca el microfono para terminar' : transcribiendo ? 'Transcribiendo tu voz...' : 'Dilo como siempre: "dos pollos y una funda de arroz a Juan, fiado"'} />
          {hayDictado() && (
            <button type="button" className={`icono ${grabando ? 'escuchando' : ''}`} aria-pressed={grabando} disabled={iaCargando || transcribiendo}
              aria-label={grabando ? 'Detener y transcribir' : 'Dictar la venta'} title={grabando ? 'Detener y transcribir' : 'Dictar la venta'} onClick={alternarDictado}>
              <Icon n="mic" />
            </button>
          )}
          <button disabled={iaCargando || grabando || transcribiendo || iaTexto.trim().length < 2}>{iaCargando ? 'Pensando...' : 'Armar venta'}</button>
        </form>
        {hayDictado() && <small className="nota-voz">Tu voz se graba en el navegador y se envia a Gemini (Google) solo para transcribirla; no se guarda. Revisa el texto antes de armar la venta.</small>}
        {propuesta && (
          <div className="ia-nota" role="status">
            <b>Propuesta de la IA</b> <small>({propuesta.modelo})</small>: revisa el carrito y cobra, o corrige.
            {(propuesta.avisos.length > 0 || propuesta.no_encontrados.length > 0 || propuesta.cliente_no_encontrado) && (
              <ul>
                {propuesta.avisos.map((a, k) => <li key={k}>{a}</li>)}
                {propuesta.no_encontrados.map((n, k) => <li key={'n' + k}>No encontrado en el catalogo: {n}</li>)}
                {propuesta.cliente_no_encontrado && <li>Cliente no encontrado: {propuesta.cliente_no_encontrado}</li>}
              </ul>
            )}
          </div>
        )}
        <div className="buscador">
          <Icon n="buscar" />
          <input className="buscar" autoFocus aria-label="Buscar producto" placeholder="Buscar o escanear codigo (Enter agrega)" value={q}
            onChange={(e) => setQ(e.target.value)} onKeyDown={alEnter} />
        </div>
        <div className="rejilla">
          {visibles.map((p, i) => (
            <button key={p.id} style={{ '--i': i }} disabled={Number(p.stock) <= 0} onClick={() => agregar(p)}>
              <b>{p.nombre}</b>
              <span>{dinero(p.precio_centavos)}</span>
              <small>{Number(p.stock) <= 0 ? 'Agotado' : `${Number(p.stock)} ${p.unidad}`}</small>
            </button>
          ))}
          {!visibles.length && productos.length > 0 && <p>Sin resultados.</p>}
        </div>
      </section>

      <aside>
        <h2>Cuenta</h2>
        {!carrito.length && <p>Agrega productos.</p>}
        {carrito.map((l) => (
          <div className="linea" key={l.p.id}>
            <span>{l.p.nombre}</span>
            <span className="paso">
              <button aria-label="Menos" onClick={() => paso(l, -1)}><Icon n="menos" size={16} /></button>
              <input type="number" min="0" step={l.p.unidad === 'lb' ? '0.001' : '1'} value={l.cantidad} aria-label={`Cantidad de ${l.p.nombre}`}
                onChange={(e) => cambiar(l.p.id, e.target.value)} />
              <button aria-label="Mas" onClick={() => paso(l, 1)}><Icon n="mas" size={16} /></button>
            </span>
            <span>{dinero(Math.round(l.p.precio_centavos * num(l)))}</span>
            <button className="icono" onClick={() => quitar(l.p.id)} aria-label={`Quitar ${l.p.nombre}`}><Icon n="x" size={16} /></button>
          </div>
        ))}
        <p className="total" key={total}>Total {dinero(total)}</p>

        <div className="metodos">
          {['efectivo', 'tarjeta', 'fiado'].map((m) => (
            <button key={m} className={metodo === m ? 'activa' : ''} onClick={() => setMetodo(m)}>{m}</button>
          ))}
        </div>

        {metodo === 'efectivo' && (
          <label>Recibido (RD$)
            <input type="number" min="0" value={recibido} onChange={(e) => setRecibido(e.target.value)} />
            {recibido && vuelto >= 0 && <b> Vuelto {dinero(vuelto)}</b>}
            {recibido && vuelto < 0 && <b className="error"> Faltan {dinero(-vuelto)}</b>}
          </label>
        )}
        {metodo === 'fiado' && (
          <label>Cliente
            <select value={clienteId} onChange={(e) => setClienteId(e.target.value)}>
              <option value="">Elegir...</option>
              {clientes.map((c) => <option key={c.id} value={c.id}>{c.nombre} (debe {dinero(c.saldo_centavos)})</option>)}
            </select>
            {excede && <small className="error">Pasa su limite de {dinero(cliente.limite_fiado_centavos)}.</small>}
          </label>
        )}

        {aviso && <p className={aviso.tipo === 'ok' ? 'ok' : 'error'}>{aviso.texto}</p>}
        {aviso?.id && <button onClick={() => setRecibo(aviso.id)}><Icon n="recibo" size={16} />Ver recibo</button>}
        {aviso?.codigo === 'limite_fiado' && (rol === 'dueno'
          ? <button onClick={() => cobrar(true)}>Autorizar exceso y cobrar</button>
          : <small>Pide al dueno que autorice esta venta.</small>)}

        <button className="primario" disabled={!listo} onClick={() => cobrar()}>Cobrar</button>
      </aside>
      {recibo && <Recibo id={recibo} alCerrar={() => setRecibo(null)} />}
    </div>
  )
}
