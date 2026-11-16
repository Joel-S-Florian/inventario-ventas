// Dictado: se graba con el microfono del navegador y se convierte a WAV mono de 16 kHz (liviano: ~32 KB/s) para que el servidor lo transcriba con Gemini.
// Se dejo de usar el reconocimiento de voz del navegador (Web Speech) porque depende de un servicio de Google que a veces responde 'network'.
export const MAX_SEGUNDOS = 30

export const hayDictado = () => !!(typeof navigator !== 'undefined' && navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined')

const MENSAJES = {
  NotAllowedError: 'El navegador no tiene permiso para usar el microfono. Permitelo en el candado de la barra de direcciones.',
  SecurityError: 'El navegador no permite usar el microfono en esta pagina.',
  NotFoundError: 'No se encontro un microfono.',
  NotReadableError: 'El microfono esta en uso por otra aplicacion.',
}
export const mensajeError = (e) => MENSAJES[e?.name] ?? 'No se pudo usar el microfono.'

function aWav(pcm, tasa) {
  const buf = new ArrayBuffer(44 + pcm.length * 2)
  const v = new DataView(buf)
  const texto = (pos, s) => [...s].forEach((c, i) => v.setUint8(pos + i, c.charCodeAt(0)))
  texto(0, 'RIFF'); v.setUint32(4, 36 + pcm.length * 2, true); texto(8, 'WAVE'); texto(12, 'fmt ')
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true) // PCM, mono
  v.setUint32(24, tasa, true); v.setUint32(28, tasa * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true)
  texto(36, 'data'); v.setUint32(40, pcm.length * 2, true)
  pcm.forEach((x, i) => v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, x)) * 0x7fff, true))
  return buf
}

async function aWavBase64(blob) {
  const ctx = new AudioContext()
  const original = await ctx.decodeAudioData(await blob.arrayBuffer())
  ctx.close()
  const fuera = new OfflineAudioContext(1, Math.max(1, Math.ceil(original.duration * 16000)), 16000) // remuestrea y mezcla a mono
  const fuente = fuera.createBufferSource()
  fuente.buffer = original; fuente.connect(fuera.destination); fuente.start()
  const pcm = (await fuera.startRendering()).getChannelData(0)
  const datos = await new Promise((ok) => { const fr = new FileReader(); fr.onload = () => ok(String(fr.result)); fr.readAsDataURL(new Blob([aWav(pcm, 16000)], { type: 'audio/wav' })) })
  return datos.split(',')[1]
}

// Empieza a grabar. Devuelve { detener(): Promise<base64 de un WAV>, cancelar() }. Lanza si no hay permiso o microfono.
export async function iniciarGrabacion() {
  const flujo = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } })
  const liberar = () => flujo.getTracks().forEach((t) => t.stop()) // apaga el microfono (la luz del navegador)
  const rec = new MediaRecorder(flujo)
  const trozos = []
  rec.ondataavailable = (e) => { if (e.data?.size) trozos.push(e.data) }
  rec.start()
  return {
    cancelar() { try { rec.stop() } catch { /* ya estaba parado */ } liberar() },
    detener: () => new Promise((ok, fallo) => {
      rec.onstop = async () => {
        liberar()
        try { ok(await aWavBase64(new Blob(trozos, { type: rec.mimeType }))) } catch { fallo(new Error('No se pudo procesar el audio grabado.')) }
      }
      rec.stop()
    }),
  }
}
