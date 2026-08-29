// Every call the UI makes. Errors surface as thrown Errors with the server's
// own message, because the point of this app is to say what actually happened.

async function jsonOrThrow(res) {
  let body = null
  try { body = await res.json() } catch { /* non-JSON error page */ }
  if (!res.ok || (body && body.success === false)) {
    throw new Error((body && (body.error || body.detail)) || `Request failed (${res.status})`)
  }
  return body
}

export async function planTrip(request, context) {
  const res = await fetch('/api/agent/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ request, context }),
  })
  return jsonOrThrow(res)
}

export async function getProviders() {
  const res = await fetch('/api/sources')
  return jsonOrThrow(res)
}

export async function getVoiceStatus() {
  const res = await fetch('/api/voice/status')
  return jsonOrThrow(res)
}

export async function transcribe(blob) {
  const form = new FormData()
  form.append('audio', blob, 'clip.webm')
  const res = await fetch('/api/voice/transcribe', { method: 'POST', body: form })
  return jsonOrThrow(res)
}

// Returns an object URL for the spoken audio, or null when voice is off.
export async function speak(text, voiceId) {
  const res = await fetch('/api/voice/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice_id: voiceId }),
  })
  if (!res.ok) return null
  return URL.createObjectURL(await res.blob())
}
