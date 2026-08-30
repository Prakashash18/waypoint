import { money, clockTime, shortDate, duration, dateRange } from '../lib/format'
import { Back, External, Mic, Plane } from './Icons'

/** Step 2: the one trip being considered, opened up.
 *
 *  Only what this trip is and what it costs — the other options and the
 *  workings are folded away, and the dates come after this, not beside it.
 */
export default function ChosenTrip({ combo, onBack, onBookFlight, onOpenStay, otherCount }) {
  const { hotel, flight, currency } = combo

  return (
    <section className="chosen">
      <button type="button" className="chosen-back" onClick={onBack}>
        <Back /> {otherCount ? `All ${otherCount} options` : 'Back'}
      </button>

      <div className="chosen-card">
        {hotel.image_url && (
          <button type="button" className="chosen-media" onClick={() => onOpenStay(hotel)}
                  aria-label={`More about ${hotel.name}`}>
            <img src={hotel.image_url} alt={hotel.name} />
          </button>
        )}

        <div className="chosen-body">
          <div className="chosen-head">
            <div>
              <span className="combo-label">{combo.label}</span>
              <h2 className="serif">{hotel.name}{hotel.area ? `, ${hotel.area}` : ''}</h2>
              <p className={hotel.review_score > 0 ? 'chosen-score' : 'chosen-score is-none'}>
                {hotel.review_score > 0
                  ? `${hotel.review_score} / 10 · ${hotel.review_count} reviews`
                  : 'No reviews yet'}
              </p>
            </div>
            <p className="chosen-total">
              <span className="serif">{money(combo.total, currency, { round: true })}</span>
              <span>
                {combo.passengers > 1 ? `for ${combo.passengers}` : ''}
                {combo.nights ? `${combo.passengers > 1 ? ' · ' : ''}${combo.nights} nights` : ''}
              </span>
              <span className="chosen-dates">
                {dateRange(combo.check_in || hotel.check_in, combo.check_out || hotel.check_out)}
              </span>
            </p>
          </div>

          <div className="chosen-split">
            {combo.includes_flight && (
              <div>
                <p className="chosen-split-label">Flights, both fares</p>
                <p className="chosen-split-figure">{money(combo.flight_price, currency, { round: true })}</p>
                <p className="chosen-split-note">
                  {flight?.airline_name || 'Flight'}
                  {flight?.price_per_passenger ? ` · ${money(flight.price_per_passenger, currency, { round: true })} each` : ''}
                </p>
              </div>
            )}
            <div>
              <p className="chosen-split-label">Stay{combo.nights ? `, ${combo.nights} nights` : ''}</p>
              <p className="chosen-split-figure">{money(combo.hotel_price, currency, { round: true })}</p>
              {hotel.price_per_night && (
                <p className="chosen-split-note">{money(hotel.price_per_night, currency, { round: true })} a night</p>
              )}
            </div>
          </div>

          {flight && (
            <div className="chosen-legs">
              {[flight.outbound, flight.return_leg].filter(Boolean).map((leg, i) => (
                <p key={i} className="chosen-leg">
                  <Plane size={14} />
                  <span className="mono">{leg.flight_code}</span>
                  <strong>{clockTime(leg.depart)}</strong><span>{leg.origin}</span>
                  <span className="dash" aria-hidden="true">—</span>
                  <strong>{clockTime(leg.arrive)}</strong><span>{leg.destination}</span>
                  <span className="when">{shortDate(leg.depart)} · {duration(leg.duration_minutes)}</span>
                </p>
              ))}
            </div>
          )}

          <div className="chosen-actions">
            {flight && (
              <button type="button" className="btn-primary" onClick={() => onBookFlight(flight)}>
                <Mic size={17} /> Book this flight
              </button>
            )}
            <a className="btn-secondary" href={hotel.booking_url || hotel.website || '#'}
               target="_blank" rel="noreferrer noopener">
              Book the stay <External />
            </a>
          </div>
        </div>
      </div>
    </section>
  )
}
