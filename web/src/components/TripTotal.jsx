import { money } from '../lib/format'

/** The number the traveller actually decides on. */
export default function TripTotal({ trip }) {
  if (!trip) return null
  const { currency } = trip

  return (
    <section className="card total-card">
      <div>
        <p className="mono eyebrow">Projected total</p>
        {trip.total != null ? (
          <p className="total-figure">
            <span className="serif">{money(trip.total, currency)}</span>
            <span className="total-for">
              {trip.passengers > 1 ? `for ${trip.passengers}` : ''}
              {trip.nights ? `${trip.passengers > 1 ? ' · ' : ''}${trip.nights} nights` : ''}
            </span>
          </p>
        ) : (
          <p className="total-missing">
            {trip.mixed_currency
              ? `Quoted in ${trip.currencies.join(' and ')} — we don't convert, so there is no single total.`
              : 'Not enough priced pieces to total yet.'}
          </p>
        )}
      </div>

      <div className="total-split">
        {trip.flight_price != null && (
          <p><span>Flights</span><strong>{money(trip.flight_price, trip.flight?.currency || currency)}</strong></p>
        )}
        {trip.flight_price != null && trip.hotel_price != null && <em aria-hidden="true">+</em>}
        {trip.hotel_price != null && (
          <p><span>Stay</span><strong>{money(trip.hotel_price, trip.hotel?.currency || currency)}</strong></p>
        )}
      </div>
    </section>
  )
}
