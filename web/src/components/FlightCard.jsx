import { money, clockTime, shortDate, duration } from '../lib/format'
import { Plane, Mic } from './Icons'

/** A leg, shown the way a boarding pass reads: time, code, time. */
function Leg({ leg, label }) {
  if (!leg) return null
  return (
    <div className="leg">
      <span className="mono leg-code">{leg.flight_code || leg.flight_number}</span>
      <div className="leg-times">
        <div>
          <p className="leg-clock">{clockTime(leg.depart)}</p>
          <p className="leg-port">{leg.origin}</p>
        </div>
        <div className="leg-rule">
          <span /><em>{duration(leg.duration_minutes)}</em><span />
        </div>
        <div className="leg-end">
          <p className="leg-clock">{clockTime(leg.arrive)}</p>
          <p className="leg-port">{leg.destination}</p>
        </div>
      </div>
      <span className="leg-date">{shortDate(leg.depart)}</span>
      <span className="sr-only">{label}</span>
    </div>
  )
}

export default function FlightCard({ flight, onBook, localeTz }) {
  if (!flight) return null

  const outbound = flight.outbound || {
    flight_code: flight.flight_code,
    depart: flight.departure_time,
    arrive: flight.arrival_time,
    origin: flight.origin,
    destination: flight.destination,
    duration_minutes: flight.duration_minutes,
  }

  return (
    <section className="card flight-card">
      <header className="card-top">
        <span className="card-top-title"><Plane size={16} /> Flights</span>
        <span className="mono chip">live fare</span>
      </header>

      <div className="flight-legs">
        <Leg leg={outbound} label="outbound" />
        {flight.return_leg && <Leg leg={flight.return_leg} label="return" />}
      </div>

      <div className="flight-price">
        <strong>{money(flight.price_total, flight.currency)}</strong>
        <span>
          {flight.passengers > 1
            ? `all ${flight.passengers} fares · ${money(flight.price_per_passenger, flight.currency)} each`
            : 'one fare'}
        </span>
      </div>

      <footer className="card-foot">
        <button type="button" className="btn-primary" onClick={onBook}>
          <Mic size={17} /> Book by voice
        </button>
        <p className="fine">
          You confirm the passengers and the price out loud before anything is charged
          {localeTz ? ` · times shown are local to each airport` : ''}
        </p>
      </footer>
    </section>
  )
}
