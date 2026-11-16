// El tema lo fija index.html antes de pintar; aqui solo se lee y se alterna.
export const temaInicial = () => document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'

export const ACENTOS = ['morado', 'azul', 'verde', 'ambar']
export const acentoInicial = () => document.documentElement.dataset.acento || 'morado'

export function siguienteAcento(actual) {
  const siguiente = ACENTOS[(ACENTOS.indexOf(actual) + 1) % ACENTOS.length]
  document.documentElement.classList.add('tema-anim')
  document.documentElement.dataset.acento = siguiente
  try { localStorage.setItem('acento', siguiente) } catch { /* sin almacenamiento: no se recuerda */ }
  setTimeout(() => document.documentElement.classList.remove('tema-anim'), 350)
  return siguiente
}

export function alternarTema(actual) {
  const siguiente = actual === 'dark' ? 'light' : 'dark'
  const raiz = document.documentElement
  raiz.classList.add('tema-anim') // activa la transicion suave solo durante el cambio
  raiz.dataset.theme = siguiente
  try { localStorage.setItem('tema', siguiente) } catch { /* modo privado: el tema no se recuerda */ }
  setTimeout(() => raiz.classList.remove('tema-anim'), 350)
  return siguiente
}
