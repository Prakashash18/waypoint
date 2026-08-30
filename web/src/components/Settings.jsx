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

  // The provider's own allowance is the real one — on the BASIC plan it is 50
  // requests a month, which a local per-day cap tells you nothing about.
  const monthly = cache?.provider_limit != null
  const limit = monthly ? cache.provider_limit : cache?.daily_limit || 0
  const left = monthly ? cache.provider_remaining : cache?.calls_left_today || 0
  const used = Math.max(0, limit - left)
  const pct = limit ? Math.min(100, (used / limit) * 100) : 0
  const exhausted = Boolean(cache?.exhausted)

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
                  <span>{monthly ? 'Price lookups this month' : 'Live lookups today'}</span>
                  <strong>{used} of {limit}</strong>
                </div>
                <div className="quota-bar">
                  <span style={{ width: `${pct}%` }}
                        className={exhausted ? 'is-out' : pct > 80 ? 'is-high' : ''} />
                </div>
                <p className={exhausted ? 'warn-line' : 'fine'}>
                  {exhausted
                    ? `Used up${cache.provider_resets_in_days
                        ? `, resets in ${Math.round(cache.provider_resets_in_days)} days`
                        : ''}. Searches you have run before still work from the saved
                       prices; a new destination or new dates will say no price is
                       available rather than guessing one.`
                    : `${left} left. Past the limit you still get saved prices, marked stale.`}
                </p>
              </div>

              <ul className="srclist">
                <li><span>Saved responses</span><span>{cache.cached_responses}</span></li>
                <li><span>Oldest</span><span>{cache.oldest_hours} h</span></li>
                <li>
                  <span>Prices</span>
                  <span>{cache.prices_live
                    ? 'fetched live, every search'
                    : `re-fetched after ${cache.rate_ttl_hours} h`}</span>
                </li>
              </ul>

              <div className="sheet-actions">
                <button type="button" className="btn-secondary" disabled={busy}
                        onClick={async () => {
                          setBusy(true)
                          try {
                            await fetch('/api/settings/cache?recheck=1')
                            setNote('Allowance forgotten — the next search re-reads it.')
                            await load()
                          } finally { setBusy(false) }
                        }}
                        title="Use this after changing your plan">
                  Re-check allowance
                </button>
                <button type="button" className="btn-secondary" onClick={reset}
                        disabled={busy || exhausted}
                        title={exhausted
                          ? 'Clearing now would leave you with no prices at all'
                          : 'The next search fetches fresh prices'}>
                  {busy ? 'Clearing…' : 'Clear saved prices'}
                </button>
              </div>
              {note && <p className="fine">{note}</p>}
              <p className="fine">
                {exhausted
                  ? 'Clearing is disabled while the allowance is used up — it would '
                    + 'throw away the only prices you have.'
                  : 'Clearing means the next search fetches fresh prices and spends '
                    + 'from the allowance.'}
              </p>
            </>
          )}
        </div>
      </section>
    </div>
  )
}
