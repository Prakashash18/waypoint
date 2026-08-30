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


/** Plan a trip, receiving each tool call as the agent makes it.
 *
 *  EventSource cannot POST, so this reads the SSE body off fetch directly.
 *  onStep fires per tool call; the promise resolves with the finished plan.
 */
export async function planTripStreaming(request, context, onStep) {
  const res = await fetch('/api/agent/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ request, context }),
  })
  if (!res.ok || !res.body) throw new Error(`Request failed (${res.status})`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let done = null
  let failed = null

  while (true) {
    const { value, done: finished } = await reader.read()
    if (finished) break
    buffer += decoder.decode(value, { stream: true })

    // SSE frames are separated by a blank line.
    let split
    while ((split = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, split)
      buffer = buffer.slice(split + 2)

      let event = 'message'
      const dataLines = []
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim()
        else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
        // lines starting with ':' are keepalive comments — ignore
      }
      if (!dataLines.length) continue

      let payload
      try { payload = JSON.parse(dataLines.join('\n')) } catch { continue }

      if (event === 'step') onStep?.(payload)
      else if (event === 'done') done = payload
      else if (event === 'error') failed = payload
    }
  }

  if (failed) throw new Error(failed.error || 'The agent failed')
  if (!done) throw new Error('The connection closed before the plan finished')
  return done
}
