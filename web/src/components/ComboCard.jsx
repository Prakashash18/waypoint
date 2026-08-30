import { money, clockTime, duration } from '../lib/format'
import { Plane, External } from './Icons'

/** One whole trip: the flight, the stay, and what the two cost together.
 *
 *  A traveller is choosing between trips, not between components, so the total
 *  leads and the parts sit underneath. Everything else waits to be asked for.
 */
export default function ComboCard({ combo, onOpen, onAsk }) {
  const { hotel, flight, currency } = combo

  return (
    <article className="combo">
      <header className="combo-head">
        <span className="combo-label">{combo.label}</span>
        <p className="combo-total">
          <span className="serif">{money(combo.total, currency, { round: true })}</span>
          <span className="combo-unit">
            {combo.passengers > 1 ? `for ${combo.passengers}` : ''}
            {combo.nights ? `${combo.passengers > 1 ? ' · ' : ''}${combo.nights} nights` : ''}
          </span>
        </p>
      </header>

      <button type="button" className="combo-stay" onClick={() => onOpen(hotel)}>
        {hotel.image_url
          ? <img src={hotel.image_url} alt={hotel.name} loading="lazy" />
          : <span className="combo-noimg" />}
        <span className="combo-stay-text">
          <strong>{hotel.name}</strong>
          <span>
            {hotel.review_score > 0 ? `${hotel.review_score}/10` : 'no reviews yet'}
            {hotel.area ? ` · ${hotel.area}` : ''}
          </span>
        </span>
      </button>

      {flight ? (
        <p className="combo-flight">
          <Plane size={14} />
          <span>
            <strong>{flight.airline_name || flight.flight_code}</strong>
            {' · '}{flight.origin}→{flight.destination}
            {' '}{clockTime(flight.outbound?.depart)}
            {flight.return_leg ? ' · return' : ''}
            {flight.outbound?.duration_minutes ? ` · ${duration(flight.outbound.duration_minutes)}` : ''}
          </span>
        </p>
      ) : (
        <p className="combo-flight is-missing">Stay only — no flight priced</p>
      )}

      <p className="combo-split">
        {combo.includes_flight
          ? <>{money(combo.flight_price, currency, { round: true })} flights + {money(combo.hotel_price, currency, { round: true })} stay</>
          : <>{money(combo.hotel_price, currency, { round: true })} for the stay</>}
        <span className="combo-why"> · {combo.why}</span>
      </p>

      <footer className="combo-foot">
        <button type="button" className="btn-secondary is-small"
                onClick={() => onAsk(
                  `Tell me more about ${hotel.name}${hotel.area ? ` in ${hotel.area}` : ''}` +
                  ` — what is it actually like, and what is nearby?`)}>
          Ask about this
        </button>
        <a className="btn-secondary is-small" href={hotel.booking_url || hotel.website || '#'}
           target="_blank" rel="noreferrer noopener">
          Book the stay <External size={13} />
        </a>
      </footer>
    </article>
  )
}
