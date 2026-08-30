import { money } from '../lib/format'
import { Back } from './Icons'

/** Step 3: the chosen trip reduced to a line, so the conversation has the room. */
export default function TripStrip({ combo, onBack }) {
  const { hotel, flight, currency } = combo
  return (
    <div className="trip-strip">
      <button type="button" className="trip-strip-back" onClick={onBack} aria-label="Back to the trip">
        <Back />
      </button>
      {hotel.image_url && <img src={hotel.image_url} alt="" />}
      <div className="trip-strip-text">
        <p className="trip-strip-name">{hotel.name}</p>
        <p className="trip-strip-sub">
          {[flight?.airline_name,
            hotel.review_score > 0 ? `${hotel.review_score} / 10` : 'no reviews yet',
            combo.nights ? `${combo.nights} nights` : null].filter(Boolean).join(' · ')}
        </p>
      </div>
      <p className="serif trip-strip-total">{money(combo.total, currency, { round: true })}</p>
    </div>
  )
}
