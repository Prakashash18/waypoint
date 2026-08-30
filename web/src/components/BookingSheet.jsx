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

          <div className="sheet-actions">
            <button type="button" className="btn-primary is-wide">Confirm and book</button>
            <button type="button" className="btn-secondary" onClick={onClose}>Not yet</button>
          </div>

          <p className="fine">
            Nothing is charged until you confirm. This screen is a preview of the booking
            flow — the fare shown is the live quote for this offer.
          </p>
        </div>
      </section>
    </div>
  )
}
