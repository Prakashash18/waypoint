import { useEffect, useState } from 'react'
import { money, clockTime, shortDate, duration } from '../lib/format'
import { Close } from './Icons'

/** Confirming a flight out loud.
 *
 *  Booking is the one irreversible thing here, so the sheet states the exact
 *  fare and party before anything happens, and the confirm is deliberate.
 */
export default function BookingSheet({ flight, onClose, voice }) {
  const [spoken, setSpoken] = useState(false)
  // The steps below are real: the offer is re-verified, the price re-confirmed
  // and the baggage priced against the airline before anything is shown.
  const [steps, setSteps] = useState(null)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    if (!flight?.offer_id) return
    let live = true
    setChecking(true)
    fetch('/api/booking/prepare', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ offer_id: flight.offer_id, currency: flight.currency,
                             quoted_total: flight.price_total }),
    })
      .then((r) => r.json())
      .then((d) => { if (live) setSteps(d.steps || []) })
      .catch(() => { if (live) setSteps([]) })
      .finally(() => { if (live) setChecking(false) })
    return () => { live = false }
  }, [flight])

  const priceLine = flight && (
    `${money(flight.price_total, flight.currency)} with ` +
    `${flight.airline_name || 'the airline'} for ` +
    `${flight.passengers > 1 ? `${flight.passengers} passengers` : 'one passenger'}. Shall I book it?`
  )

  useEffect(() => {
    if (flight && !spoken && voice?.say) {
      setSpoken(true)
      voice.say(priceLine)
    }
  }, [flight, spoken, voice, priceLine])

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!flight) return null

  const legs = [flight.outbound, flight.return_leg].filter(Boolean)

  return (
    <div className="sheet-backdrop" onClick={onClose} role="presentation">
      <section className="sheet is-booking" onClick={(e) => e.stopPropagation()}
               role="dialog" aria-modal="true" aria-label="Confirm this booking">
        <button type="button" className="sheet-close" onClick={onClose} aria-label="Close">
          <Close />
        </button>

        <div className="sheet-body">
          <p className="mono eyebrow">
            Booking with {flight.airline_name || flight.airline || 'the airline'}
          </p>

          <div className="booking-legs">
            {legs.map((leg, i) => (
              <div className="leg" key={i}>
                <span className="mono leg-code">{leg.flight_code || leg.flight_number}</span>
                <div className="leg-times">
                  <div><p className="leg-clock">{clockTime(leg.depart)}</p><p className="leg-port">{leg.origin}</p></div>
                  <div className="leg-rule"><span /><em>{duration(leg.duration_minutes)}</em><span /></div>
                  <div className="leg-end"><p className="leg-clock">{clockTime(leg.arrive)}</p><p className="leg-port">{leg.destination}</p></div>
                </div>
                <span className="leg-date">{shortDate(leg.depart)}</span>
              </div>
            ))}
          </div>

          <div className="booking-total">
            <div>
              <p>{flight.passengers > 1 ? `${flight.passengers} passengers` : 'One passenger'}</p>
              <p className="fine">Seats assigned at check-in</p>
            </div>
            <strong>{money(flight.price_total, flight.currency)}</strong>
          </div>

          <p className="serif booking-ask">“{priceLine}”</p>

          <div className="booking-steps">
            <p className="mono eyebrow">
              {checking ? 'Checking with the airline…' : 'Checked with the airline'}
            </p>
            <ol>
              {(steps || []).map((st) => (
                <li key={st.key} className={st.status === 'ok' ? 'is-ok' : 'is-failed'}>
                  <span className="booking-mark" aria-hidden="true">
                    {st.status === 'ok' ? '✓' : '✕'}
                  </span>
                  <div>
                    <p className="booking-label">{st.label}</p>
                    <p className="booking-detail">{st.detail}</p>
                    {st.options?.length > 0 && (
                      <ul className="booking-bags">
                        {st.options.slice(0, 4).map((o) => (
                          <li key={o.weight_kg}>
                            {o.weight_kg}kg · {o.currency} {Number(o.price).toFixed(2)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </li>
              ))}
              {checking && !steps && <li className="is-pending"><span className="spinner" /> Verifying the fare…</li>}
            </ol>
          </div>

          <div className="sheet-actions">
            <button type="button" className="btn-primary is-wide" disabled>
              Confirm and book
            </button>
            <button type="button" className="btn-secondary" onClick={onClose}>Not yet</button>
          </div>

          <p className="fine">
            The steps above really ran against the airline just now. Passenger details
            and payment are not wired up, so the final button is inactive — nothing can
            be charged from here.
          </p>
        </div>
      </section>
    </div>
  )
}
