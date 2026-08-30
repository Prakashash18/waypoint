import { useEffect, useState } from 'react'
import { Close } from './Icons'

/** Hotel prices come from a metered provider, so what has been spent and what
 *  is held is shown plainly rather than hidden, with a deliberate reset. */
export default function Settings({ onClose }) {
  const [cache, setCache] = useState(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')

  const load = () =>
    fetch('/api/settings/cache').then((r) => r.json()).then(setCache).catch(() => {})

  useEffect(() => {
    load()
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function reset() {
    setBusy(true)
    try {
      const res = await fetch('/api/settings/cache', { method: 'DELETE' })
      const data = await res.json()
      setNote(`Cleared ${data.cleared} saved ${data.cleared === 1 ? 'response' : 'responses'}.`)
      await load()
    } finally {
      setBusy(false)
    }
  }

  const used = cache ? cache.calls_today : 0
  const limit = cache ? cache.daily_limit : 0
  const pct = limit ? Math.min(100, (used / limit) * 100) : 0

  return (
    <div className="sheet-backdrop" onClick={onClose} role="presentation">
      <section className="sheet" onClick={(e) => e.stopPropagation()}
               role="dialog" aria-modal="true" aria-label="Settings">
        <button type="button" className="sheet-close" onClick={onClose} aria-label="Close">
          <Close />
        </button>

        <div className="sheet-body">
          <h2 className="serif">Hotel prices</h2>
          <p className="fine">
            Rates come from a metered provider, so answers are reused rather than
            re-fetched. Flights, maps, places and photos are unmetered and always live.
          </p>

          {!cache ? (
            <p className="muted">loading…</p>
          ) : (
            <>
              <div className="quota">
                <div className="quota-head">
                  <span>Live lookups today</span>
                  <strong>{used} of {limit}</strong>
                </div>
                <div className="quota-bar">
                  <span style={{ width: `${pct}%` }} className={pct > 80 ? 'is-high' : ''} />
                </div>
                <p className="fine">
                  {cache.calls_left_today > 0
                    ? `${cache.calls_left_today} left. Past the limit you still get prices — the saved ones, marked stale.`
                    : 'Used up. You will still get prices, but they will be the saved ones, marked stale.'}
                </p>
              </div>

              <ul className="srclist">
                <li><span>Saved responses</span><span>{cache.cached_responses}</span></li>
                <li><span>Oldest</span><span>{cache.oldest_hours} h</span></li>
                <li><span>Prices re-fetched after</span><span>{cache.rate_ttl_hours} h</span></li>
              </ul>

              <div className="sheet-actions">
                <button type="button" className="btn-secondary" onClick={reset} disabled={busy}>
                  {busy ? 'Clearing…' : 'Clear saved prices'}
                </button>
              </div>
              {note && <p className="fine">{note}</p>}
              <p className="fine">
                Clearing means the next search fetches fresh prices and spends from
                today’s allowance.
              </p>
            </>
          )}
        </div>
      </section>
    </div>
  )
}
