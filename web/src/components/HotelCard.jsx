import { money } from '../lib/format'
import { External } from './Icons'

/** A stay. Books at the source, because we never hold the room. */
export default function HotelCard({ hotel, onOpen, compact = false }) {
  if (!hotel) return null
  const priced = hotel.total_price != null

  const imageLabel = {
    provider_photo: 'real photo',
    website: 'live screenshot',
    map: 'map of the location',
    photo: 'geotagged photo',
  }[hotel.image_source]

  return (
    <article className={`card hotel-card${compact ? ' is-compact' : ''}`}>
      <button type="button" className="hotel-media" onClick={onOpen}
              aria-label={`More about ${hotel.name}`}>
        {hotel.image_url ? (
          <img src={hotel.image_url} alt={hotel.name} loading="lazy" decoding="async" />
        ) : (
          <p className="no-image">{hotel.image_note || 'No photograph of this place was available.'}</p>
        )}
        {imageLabel && <span className="mono media-tag">{imageLabel}</span>}
      </button>

      <div className="hotel-body">
        <div className="hotel-head">
          <h3 className="serif">{hotel.name}</h3>
          {hotel.review_score != null && (
            <p className="score">
              <strong>{hotel.review_score}</strong>
              {hotel.review_count ? <span>{hotel.review_count} reviews</span> : null}
            </p>
          )}
        </div>

        {(hotel.area || hotel.address) && (
          <p className="hotel-where">{hotel.area || hotel.address}</p>
        )}

        {priced ? (
          <p className="hotel-price">
            <strong>{money(hotel.total_price, hotel.currency)}</strong>
            <span>
              {hotel.nights ? `${hotel.nights} nights` : 'total'}
              {hotel.price_per_night ? ` · ${money(hotel.price_per_night, hotel.currency)} a night` : ''}
            </span>
          </p>
        ) : (
          <p className="no-price">No rate available for this one</p>
        )}
      </div>

      {!compact && (
        <footer className="card-foot">
          <a className="btn-secondary" href={hotel.booking_url || hotel.website || '#'}
             target="_blank" rel="noreferrer noopener">
            Book on {hotel.source === 'osm' ? 'their site' : 'Booking.com'} <External />
          </a>
          <p className="fine">Rooms are held and paid for on their site, not here</p>
        </footer>
      )}
    </article>
  )
}
