/** One hotel. Shows a real image or explains why there is none, and never
 *  shows a price the providers did not return. */
export default function HotelCard({ hotel }) {
  const prov = hotel.provenance || {}
  const hasPrice = hotel.total_price != null

  const imageBadge = {
    provider_photo: ['real photo', 'ok'],
    website: ['live screenshot', 'shot'],
    map: ['map of location', 'shot'],
    photo: ['geotagged photo', 'shot'],
  }[hotel.image_source]

  return (
    <article className="hotel">
      <div className="hotel-media">
        {hotel.image_url ? (
          <img src={hotel.image_url} alt={hotel.name} loading="lazy" decoding="async" />
        ) : (
          <p className="hotel-noimage">
            {hotel.image_note || 'No authentic image available. None was invented.'}
          </p>
        )}
      </div>

      <div className="hotel-body">
        <h3 className="hotel-name">{hotel.name}</h3>

        <p className="hotel-meta">
          {hotel.stars ? <span>{hotel.stars}★</span> : null}
          {hotel.review_score ? (
            <span>
              {hotel.review_score}/10
              {hotel.review_count ? ` · ${hotel.review_count} reviews` : ''}
            </span>
          ) : null}
          {hotel.area ? <span>{hotel.area}</span> : null}
          {hotel.distance_km != null ? <span>{hotel.distance_km} km from centre</span> : null}
        </p>

        {hasPrice ? (
          <p className="hotel-price">
            {hotel.currency || 'USD'} {Math.round(hotel.total_price)}
            <span className="hotel-price-unit">
              total{hotel.nights ? ` · ${hotel.nights} nights` : ''}
            </span>
          </p>
        ) : (
          <p className="hotel-noprice">Price not available from any configured source</p>
        )}

        <ul className="badges">
          <li className={`badge ${prov.status === 'live' ? 'ok' : prov.status === 'cached' ? 'info' : ''}`}>
            {prov.label || hotel.source || 'unknown source'}
          </li>
          {imageBadge && <li className={`badge ${imageBadge[1]}`}>{imageBadge[0]}</li>}
          {hotel.website && (
            <li className="badge">
              <a href={hotel.website} target="_blank" rel="noreferrer noopener">official site</a>
            </li>
          )}
        </ul>
      </div>
    </article>
  )
}
