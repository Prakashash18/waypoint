import { money, clockTime, shortDate, duration } from '../lib/format'
import { External, Plane, Mic } from './Icons'

/** The parts of a reply worth seeing rather than reading.
 *
 *  A price that moved should look like it moved; a stay being discussed should
 *  have a face and a rate. The prose stays, but it stops carrying the numbers
 *  on its own.
 */
export default function ReplyCards({ cards, onOpen, onBookFlight }) {
  if (!cards?.length) return null

  return (
    <div className="reply-cards">
      {cards.map((card, i) => {
        if (card.kind === 'price_change') return <PriceChange key={i} card={card} />
        if (card.kind === 'flight') return <FlightCardInline key={i} card={card} onBook={onBookFlight} />
        return <StayCard key={i} card={card} onOpen={onOpen} />
      })}
    </div>
  )
}

function PriceChange({ card }) {
  const cheaper = card.delta < 0
  return (
    <div className={`rcard is-price ${cheaper ? 'is-down' : 'is-up'}`}>
      <p className="rcard-title">{card.title}</p>
      <p className="rcard-move">
        <span className="was">{money(card.from, card.currency, { round: true })}</span>
        <span className="arrow" aria-hidden="true">→</span>
        <strong>{money(card.to, card.currency, { round: true })}</strong>
      </p>
      <p className="rcard-delta">
        {cheaper ? 'saves ' : 'costs '}
        {money(Math.abs(card.delta), card.currency, { round: true })}
        {card.detail ? ` · ${card.detail}` : ''}
      </p>
    </div>
  )
}

function StayCard({ card, onOpen }) {
  return (
    <div className="rcard is-stay">
      {card.image_url && (
        <button type="button" className="rcard-img" onClick={() => onOpen?.(card)}
                aria-label={`Open ${card.name}`}>
          <img src={card.image_url} alt={card.name} loading="lazy" />
        </button>
      )}
      <div className="rcard-body">
        <p className="rcard-title">{card.name}</p>
        <p className="rcard-sub">
          {card.review_score > 0
            ? `${card.review_score}/10${card.review_count ? ` · ${card.review_count} reviews` : ''}`
            : 'no reviews yet'}
          {card.area ? ` · ${card.area}` : ''}
        </p>
        {card.total_price != null && (
          <p className="rcard-price">
            <strong>{money(card.total_price, card.currency)}</strong>
            <span>
              {card.nights ? `${card.nights} nights` : 'total'}
              {card.price_per_night ? ` · ${money(card.price_per_night, card.currency)} a night` : ''}
            </span>
          </p>
        )}
        {card.booking_url && (
          <a className="rcard-link" href={card.booking_url}
             target="_blank" rel="noreferrer noopener">
            Book the stay <External size={12} />
          </a>
        )}
      </div>
    </div>
  )
}


/** The flight, as a card rather than a paragraph of times and codes. */
function FlightCardInline({ card, onBook }) {
  const legs = [card.outbound, card.return_leg].filter(Boolean)
  return (
    <div className="rcard is-flight">
      <p className="rcard-title">
        <Plane size={14} /> {card.airline_name || card.flight_code}
      </p>
      <p className="rcard-sub">
        {card.origin}→{card.destination}
        {legs.length > 1 ? ' · return' : ' · one way'}
      </p>

      <div className="rcard-legs">
        {legs.map((leg, i) => (
          <p key={i} className="rcard-leg">
            <span className="mono">{leg.flight_code}</span>
            <strong>{clockTime(leg.depart)}</strong>
            <span className="port">{leg.origin}</span>
            <span className="dash" aria-hidden="true">—</span>
            <strong>{clockTime(leg.arrive)}</strong>
            <span className="port">{leg.destination}</span>
            <span className="when">{shortDate(leg.depart)}
              {leg.duration_minutes ? ` · ${duration(leg.duration_minutes)}` : ''}</span>
          </p>
        ))}
      </div>

      {card.price_total != null && (
        <p className="rcard-price">
          <strong>{money(card.price_total, card.currency)}</strong>
          <span>
            {card.passengers > 1
              ? `all ${card.passengers} fares · ${money(card.price_per_passenger, card.currency)} each`
              : 'one fare'}
          </span>
        </p>
      )}

      {onBook && (
        <button type="button" className="rcard-book" onClick={() => onBook(card)}>
          <Mic size={13} /> Book by voice
        </button>
      )}
    </div>
  )
}
