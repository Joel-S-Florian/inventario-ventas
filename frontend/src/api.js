let alExpirar = () => {}
export const onExpirar = (fn) => { alExpirar = fn }

export const guardarSesion = (s) => sessionStorage.setItem('sesion', JSON.stringify(s))
export const leerSesion = () => { try { return JSON.parse(sessionStorage.getItem('sesion')) } catch { return null } }
export const borrarSesion = () => sessionStorage.removeItem('sesion')

export async function api(ruta, { method = 'GET', body } = {}) {
  const token = leerSesion()?.token
  const r = await fetch('/api' + ruta, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token && { Authorization: `Bearer ${token}` }) },
    body: body && JSON.stringify(body),
  })
  if (r.status === 204) return null
  const datos = await r.json().catch(() => null)
  if (!r.ok) {
    if (r.status === 401 && ruta !== '/login') alExpirar()
    const mensaje = typeof datos?.detail === 'string' ? datos.detail : 'Datos invalidos'
    throw { status: r.status, codigo: datos?.codigo, mensaje }
  }
  return datos
}

const fmt = new Intl.NumberFormat('es-DO', { style: 'currency', currency: 'DOP' })
export const dinero = (centavos) => fmt.format(centavos / 100)
export const fechaLocal = (d = new Date()) => d.toLocaleDateString('en-CA') // AAAA-MM-DD en hora local
export const aCentavos = (pesos) => Math.round(parseFloat(pesos) * 100)
