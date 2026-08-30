import { useState } from 'react'
import { money, clockTime, duration, dateRange } from '../lib/format'
import { Plane, Info, Traveller, Night } from './Icons'

/** One whole trip: the flight, the stay, and what the two cost together.
 *
 *  A traveller is choosing between trips, not between components, so the total
 *  leads and the parts sit underneath. Everything else waits to be asked for.
 */
export default function ComboCard({ combo, onOpen, onChoose, onAsk }) {
  const { hotel, flight, currency } = combo
  const [explaining, setExplaining] = useState(false)

  // The label is a rule; say which one, on demand rather than in everyone's way.
  const dates = dateRange(combo.check_in || hotel.check_in,
                          combo.check_out || hotel.check_out)

  return (
    <article className="combo">
      <header className="combo-head">
        <div className="combo-label-row">
          <span className="combo-label">{combo.label}</span>
          {combo.explain && (
            <button type="button" className="combo-info"
                    aria-expanded={explaining}
                    aria-label={`What ${combo.label.toLowerCase()} means`}
                    onClick={() => setExplaining((v) => !v)}>
              <Info />
            </button>
          )}
        </div>
        <p className="combo-total">
          <span className="serif">{money(combo.total, currency, { round: true })}</span>
          {/* Each count carries its own icon and noun — "for 2 · 4 nights"
              ran the two numbers together. */}
          <span className="combo-unit">
            {combo.passengers > 0 && (
              <span className="meta-unit">
                <Traveller />
                {combo.passengers}&nbsp;{combo.passengers === 1 ? 'traveller' : 'travellers'}
              </span>
            )}
            {combo.nights > 0 && (
              <span className="meta-unit">
                <Night />
                {combo.nights}&nbsp;{combo.nights === 1 ? 'night' : 'nights'}
              </span>
            )}
          </span>
        </p>
        {dates && <p className="combo-dates">{dates}</p>}
        {explaining && combo.explain && (
          <p className="combo-explain" role="note">{combo.explain}</p>
        )}
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
        <button type="button" className="btn-primary is-choose" onClick={onChoose}>
          See this trip
        </button>
      </footer>
    </article>
  )
}
