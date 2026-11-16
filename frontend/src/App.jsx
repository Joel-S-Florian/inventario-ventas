import { useEffect, useState } from 'react'
import './App.css'
import { api, borrarSesion, guardarSesion, leerSesion, onExpirar } from './api'
import Caja from './Caja'
import Clientes from './Clientes'
import Compras from './Compras'
import Icon from './Icon'
import Productos from './Productos'
import Reportes from './Reportes'
import Reposicion from './Reposicion'
import { acentoInicial, alternarTema, siguienteAcento, temaInicial } from './tema'
import Venta from './Venta'

function Marca() {
  return (
    <span className="marca">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M6 8h12l-1.2 11H7.2L6 8z" /><path d="M9 8a3 3 0 0 1 6 0" />
      </svg>
      Colmado
    </span>
  )
}

function BotonTema() {
  const [tema, setTema] = useState(temaInicial)
  const aOscuro = tema === 'light'
  return (
    <button className="icono" onClick={() => setTema(alternarTema(tema))}
      aria-label={aOscuro ? 'Cambiar a tema oscuro' : 'Cambiar a tema claro'} title={aOscuro ? 'Tema oscuro' : 'Tema claro'}>
      <span key={tema} className="giro"><Icon n={aOscuro ? 'luna' : 'sol'} /></span>
    </button>
  )
}

function BotonAcento() {
  const [acento, setAcento] = useState(acentoInicial)
  return (
    <button className="icono" onClick={() => setAcento(siguienteAcento(acento))}
      aria-label={`Color de acento: ${acento}. Pulsa para cambiar`} title={`Color: ${acento}`}>
      <span key={acento} className="punto" />
    </button>
  )
}

function Login({ alEntrar }) {
  const [nombre, setNombre] = useState('')
  const [clave, setClave] = useState('')
  const [error, setError] = useState('')

  async function enviar(e) {
    e.preventDefault()
    try {
      alEntrar(await api('/login', { method: 'POST', body: { nombre, clave } }))
    } catch (err) {
      setError(err.mensaje)
    }
  }

  return (
    <div className="centrado">
      <div className="tema-esquina"><BotonAcento /><BotonTema /></div>
      <form className="login" onSubmit={enviar}>
        <Marca />
        <h1>Bienvenido</h1>
        <p className="sub">Entra para abrir la caja.</p>
        <input aria-label="Usuario" placeholder="Usuario" value={nombre} onChange={(e) => setNombre(e.target.value)} autoFocus />
        <input aria-label="Clave o PIN" placeholder="Clave o PIN" type="password" value={clave} onChange={(e) => setClave(e.target.value)} />
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primario">Entrar</button>
      </form>
    </div>
  )
}

export default function App() {
  const [sesion, setSesion] = useState(leerSesion)
  const [pestana, setPestana] = useState('venta')
  const [borrador, setBorrador] = useState(null) // propuesta de compra de la IA, de Reponer a Compras

  const salir = () => { borrarSesion(); setSesion(null) }
  useEffect(() => onExpirar(salir), [])

  if (!sesion) return <Login alEntrar={(s) => { guardarSesion(s); setPestana('venta'); setSesion(s) }} />

  const pestanas = [['venta', 'Venta', 'venta'], ['clientes', 'Fiado', 'fiado'], ['caja', 'Caja', 'caja'], ['reposicion', 'Reponer', 'reponer'],
    ...(sesion.rol === 'dueno' ? [['productos', 'Productos', 'productos'], ['compras', 'Compras', 'compras'], ['reportes', 'Reportes', 'reportes']] : [])]
  return (
    <>
      <header>
        <Marca />
        <nav aria-label="Secciones">
          {pestanas.map(([id, texto, icono]) => (
            <button key={id} className={pestana === id ? 'activa' : ''} aria-current={pestana === id ? 'page' : undefined}
              title={texto} onClick={() => setPestana(id)}>
              <Icon n={icono} /><span>{texto}</span>
            </button>
          ))}
        </nav>
        <span className="usuario">
          <span className="avatar" aria-hidden="true">{sesion.nombre[0].toUpperCase()}</span>
          <span className="rol">{sesion.rol}</span>
          <BotonAcento />
          <BotonTema />
          <button className="icono" onClick={salir} aria-label="Salir" title="Salir"><Icon n="salir" /></button>
        </span>
      </header>
      <main key={pestana}>
        {pestana === 'venta' && <Venta rol={sesion.rol} />}
        {pestana === 'clientes' && <Clientes rol={sesion.rol} />}
        {pestana === 'reposicion' && <Reposicion rol={sesion.rol} alUsar={(p) => { setBorrador(p); setPestana('compras') }} />}
        {pestana === 'productos' && sesion.rol === 'dueno' && <Productos />}
        {pestana === 'compras' && sesion.rol === 'dueno' && <Compras borrador={borrador} alConsumir={() => setBorrador(null)} />}
        {pestana === 'caja' && <Caja rol={sesion.rol} />}
        {pestana === 'reportes' && sesion.rol === 'dueno' && <Reportes />}
      </main>
    </>
  )
}
