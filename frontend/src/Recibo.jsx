import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, dinero } from './api'

// Recibo informativo (no es comprobante fiscal). Va en un portal para poder imprimirlo solo.
export default function Recibo({ id, alCerrar }) {
  const [r, setR] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api(`/ventas/${id}`).then(setR).catch((e) => setError(e.mensaje)) }, [id])
  useEffect(() => {
    const tecla = (e) => e.key === 'Escape' && alCerrar()
    addEventListener('keydown', tecla)
    return () => removeEventListener('keydown', tecla)
  }, [alCerrar])

  return createPortal(
    <div className="modal" role="dialog" aria-modal="true" aria-label="Recibo de venta" onClick={alCerrar}>
      <div className="modal-caja" onClick={(e) => e.stopPropagation()}>
        {error && <p className="error">{error}</p>}
        {!r && !error && <div className="esqueleto" />}
        {r && (
          <article className="recibo">
            <h2>{r.negocio}</h2>
            <p className="centro">Recibo #{String(r.numero).padStart(6, '0')}</p>
            <p className="centro">{new Date(r.fecha).toLocaleString('es-DO', { dateStyle: 'short', timeStyle: 'short' })}</p>
            {r.atendido_por && <p className="centro">Atendido por {r.atendido_por}</p>}
            {r.estado === 'anulada' && <p className="sello">ANULADA</p>}
            <hr />
            {r.items.map((i, k) => (
              <div key={k}>
                <div className="r-linea"><span>{i.nombre}</span><span>{dinero(i.subtotal_centavos)}</span></div>
                <div className="r-detalle">{Number(i.cantidad)} x {dinero(i.precio_centavos)}</div>
              </div>
            ))}
            <hr />
            <div className="r-linea r-total"><span>TOTAL</span><span>{dinero(r.total_centavos)}</span></div>
            <p>Pago: {r.metodo}</p>
            {r.cliente && <p>Cliente: {r.cliente}</p>}
            {r.saldo_fiado_centavos != null && <p>Saldo pendiente: {dinero(r.saldo_fiado_centavos)}</p>}
            <hr />
            <p className="centro">Gracias por su compra</p>
            <p className="centro r-detalle">Recibo informativo, no es comprobante fiscal.</p>
          </article>
        )}
        <div className="fila no-imprimir">
          <button className="primario" autoFocus disabled={!r} onClick={() => window.print()}>Imprimir</button>
          <button onClick={alCerrar}>Cerrar</button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
