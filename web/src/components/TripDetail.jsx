import { useEffect } from 'react'
import { money, clockTime, shortDate, duration } from '../lib/format'
import { Close, External, Mic, Plane } from './Icons'

function Leg({ leg, label }) {
  if (!leg) return null
  return (
    <div className="leg">
      <span className="mono leg-code">{leg.flight_code || leg.flight_number}</span>
      <div className="leg-times">
        <div><p className="leg-clock">{clockTime(leg.depart)}</p><p className="leg-port">{leg.origin}</p></div>
        <div className="leg-rule"><span /><em>{duration(leg.duration_minutes)}</em><span /></div>
        <div className="leg-end"><p className="leg-clock">{clockTime(leg.arrive)}</p><p className="leg-port">{leg.destination}</p></div>
      </div>
      <span className="leg-date">{shortDate(leg.depart)}</span>
      <span className="sr-only">{label}</span>
    </div>
  )
}

/** The whole trip, opened up: both flights, the stay, what it costs and where
 *  each number came from. Reached by drilling into a combo. */
export default function TripDetail({ combo, onClose, onAsk, onBookFlight }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!combo) return null
  const { hotel, flight, currency } = combo
  const photos = (hotel.photos || []).slice(0, 4)

  return (
    <div className="sheet-backdrop" onClick={onClose} role="presentation">
      <section className="sheet is-wide" onClick={(e) => e.stopPropagation()}
               role="dialog" aria-modal="true" aria-label={`${combo.label} trip`}>
        <button type="button" className="sheet-close" onClick={onClose} aria-label="Close">
          <Close />
        </button>

        {hotel.image_url && (
          <div className="sheet-media"><img src={hotel.image_url} alt={hotel.name} /></div>
        )}

        <div className="sheet-body">
          <div className="sheet-head">
            <div>
              <span className="combo-label">{combo.label}</span>
              <h2 className="serif">{hotel.name}</h2>
              <p className="hotel-where">
                {[hotel.review_score > 0 ? `${hotel.review_score}/10` : 'No reviews yet',
                  hotel.review_count ? `${hotel.review_count} reviews` : null,
                  hotel.area].filter(Boolean).join(' · ')}
              </p>
            </div>
            <p className="sheet-price">
              <span className="serif">{money(combo.total, currency)}</span>
              <span>
                total{combo.passengers > 1 ? ` · ${combo.passengers} people` : ''}
                {combo.nights ? ` · ${combo.nights} nights` : ''}
              </span>
            </p>
          </div>

          <ul className="breakdown">
            {combo.includes_flight && (
              <li><span>Flights, both ways{combo.passengers > 1 ? `, ${combo.passengers} fares` : ''}</span>
                  <strong>{money(combo.flight_price, currency)}</strong></li>
            )}
            <li><span>Stay{combo.nights ? `, ${combo.nights} nights` : ''}
                {hotel.price_per_night ? ` (${money(hotel.price_per_night, currency)} a night)` : ''}</span>
                <strong>{money(combo.hotel_price, currency)}</strong></li>
            <li className="is-total"><span>Total</span><strong>{money(combo.total, currency)}</strong></li>
          </ul>

          {flight ? (
            <div className="detail-block">
              <p className="mono eyebrow">
                <Plane size={13} /> {flight.airline_name || 'Flights'}
                {flight.return_leg ? ' · return' : ' · one way'}
              </p>
              <Leg leg={flight.outbound} label="outbound" />
              {flight.return_leg && <Leg leg={flight.return_leg} label="return" />}
              <p className="fine">Times are local to each airport, as airlines publish them.</p>
            </div>
          ) : (
            <p className="fine">No flight is priced in this option — the total is the stay only.</p>
          )}

          {photos.length > 1 && (
            <div className="detail-block">
              <p className="mono eyebrow">The stay</p>
              <div className="photo-strip">
                {photos.map((src, i) => (
                  <img key={i} src={src} alt={`${hotel.name} ${i + 1}`} loading="lazy" />
                ))}
              </div>
            </div>
          )}

          <div className="sheet-actions">
            {flight && (
              <button type="button" className="btn-primary" onClick={() => onBookFlight(flight)}>
                <Mic size={16} /> Book the flight by voice
              </button>
            )}
            <a className="btn-secondary" href={hotel.booking_url || hotel.website || '#'}
               target="_blank" rel="noreferrer noopener">
              Book the stay <External />
            </a>
          </div>

          <div className="sheet-actions">
            {['Is there anything quieter?', 'What is nearby?', 'Cheaper dates for this?'].map((q) => (
              <button key={q} type="button" className="btn-secondary is-small"
                      onClick={() => { onClose(); onAsk(`${q} (about ${hotel.name})`) }}>
                {q}
              </button>
            ))}
          </div>

          <p className="fine">
            Rates and photographs from {hotel.provenance?.label || 'the rate provider'};
            fares from the Atlas CLI. We don’t hold rooms — that button opens the site
            the rate was quoted on.
          </p>
        </div>
      </section>
    </div>
  )
}
