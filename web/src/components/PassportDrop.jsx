import { useCallback, useRef, useState } from 'react'

/** Fill a traveller's details from the passport's machine-readable zone.
 *
 *  Only the two monospaced lines at the bottom of the photo page are read.
 *  Every field there carries an ICAO check digit, so a character the scanner
 *  gets wrong is caught rather than written into a ticket — anything that
 *  fails its digit is left blank for the traveller to type.
 */
export default function PassportDrop({ onRead }) {
  const [busy, setBusy] = useState(false)
  const [over, setOver] = useState(false)
  const [note, setNote] = useState(null)
  const [warn, setWarn] = useState(null)
  const inputRef = useRef(null)

  const send = useCallback(async (file) => {
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setWarn('That is not an image.'); setNote(null); return
    }
    setBusy(true); setWarn(null); setNote(null)
    try {
      const body = new FormData()
      body.append('image', file)
      const d = await fetch('/api/booking/scan-passport', { method: 'POST', body })
        .then((r) => r.json())

      if (!d.success) { setWarn(d.error || 'Could not read that image.'); return }

      const f = d.fields || {}
      onRead(f)

      const missed = (d.failed || []).filter((k) => !k.endsWith('_unreadable'))
      if (f.expired) {
        setWarn(`Read, but this passport expired on ${f.expires}. `
                + 'Most airlines will not carry you on it.')
      } else if (missed.length) {
        setWarn(`Read, but ${missed.join(' and ')} did not pass the passport's own `
                + 'check digits, so those are left blank. Please type them in.')
      } else if (!f.name_verified) {
        setNote('Filled in. The name could not be cross-checked against the '
                + 'check digit — worth a glance before you continue.')
      } else {
        setNote('Filled in, and every field matched the passport’s check digits.')
      }
    } catch {
      setWarn('Could not reach the reader. You can still type the details in.')
    } finally {
      setBusy(false)
    }
  }, [onRead])

  return (
    <div className={`ppdrop${over ? ' is-over' : ''}${busy ? ' is-busy' : ''}`}
         onDragOver={(e) => { e.preventDefault(); setOver(true) }}
         onDragLeave={() => setOver(false)}
         onDrop={(e) => {
           e.preventDefault(); setOver(false)
           send(e.dataTransfer.files?.[0])
         }}>
      <input ref={inputRef} type="file" accept="image/*" capture="environment"
             hidden onChange={(e) => { send(e.target.files?.[0]); e.target.value = '' }} />

      <button type="button" className="btn-secondary" disabled={busy}
              onClick={() => inputRef.current?.click()}>
        {busy ? 'Reading the passport…' : 'Scan or drop a passport'}
      </button>

      <p className="fine ppdrop-how">
        Drop a photo here, or take one. Point at the <strong>two lines of
        letters and numbers</strong> along the bottom of the photo page — that
        is the only part read.
      </p>
      <p className="fine ppdrop-priv">
        The photo is sent to be transcribed and is not stored, logged, or kept
        after this request. Typing the details in yourself works just as well.
      </p>

      {note && <p className="fine ppdrop-ok">{note}</p>}
      {warn && <p className="warn-line">{warn}</p>}
    </div>
  )
}
