import { useEffect } from 'react'
import { money } from '../lib/format'
import { External, Close, Mic } from './Icons'

const SOURCE_ROWS = [
  ['Rate & reviews', (h) => h.provenance?.label],
  ['Photograph', (h) => (h.image_source === 'provider_photo' ? h.provenance?.label
    : h.image_source === 'website' ? 'Live screenshot of their site'
    : h.image_source === 'map' ? 'OpenStreetMap'
    : h.image_source === 'photo' ? 'Wikimedia Commons' : null)],
  ['Address & map', (h) => (h.osm_url ? 'OpenStreetMap' : null)],
]

/** Everything known about one stay, and where each part came from. */
/** "Check in 14:00–20:00 · out by 11:00", skipping ends the provider left open.
 *  A bare untilTime of 00:00 means midnight, so it is dropped rather than
 *  shown as if it were the hour you may arrive. */
function checkTimes(hotel) {
  const open = hotel.checkin_from && hotel.checkin_from !== '00:00' ? hotel.checkin_from : null
  const shut = hotel.checkin_until && hotel.checkin_until !== '00:00' ? hotel.checkin_until : null
  const out = hotel.checkout_until || null

  const parts = []
  if (open) parts.push(`Check in ${shut ? `${open}–${shut}` : `from ${open}`}`)
  else if (shut) parts.push(`Check in until ${shut}`)
  if (out) parts.push(`out by ${out}`)
  return parts.join(' · ') || null
}

export default function HotelDetail({ hotel, onClose, onAsk }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!hotel) return null
  const rows = SOURCE_ROWS.map(([label, get]) => [label, get(hotel)]).filter(([, v]) => v)

  return (
    <div className="sheet-backdrop" onClick={onClose} role="presentation">
      <section className="sheet" onClick={(e) => e.stopPropagation()}
               role="dialog" aria-modal="true" aria-label={hotel.name}>
        <button type="button" className="sheet-close" onClick={onClose} aria-label="Close">
          <Close />
        </button>

        {hotel.image_url && (
          <div className="sheet-media">
            <img src={hotel.image_url} alt={hotel.name} />
          </div>
        )}

        <div className="sheet-body">
          <div className="sheet-head">
            <div>
              <h2 className="serif">{hotel.name}</h2>
              <p className="hotel-where">
                {[hotel.review_score > 0 ? `${hotel.review_score}/10` : 'No reviews yet',
                  hotel.review_score > 0 ? hotel.review_word : null,
                  hotel.area || hotel.address]
                  .filter(Boolean).join(' · ')}
              </p>
            </div>
            {hotel.total_price != null && (
              <p className="sheet-price">
                <span className="serif">{money(hotel.total_price, hotel.currency)}</span>
                <span>{hotel.nights ? `${hotel.nights} nights` : 'total'}</span>
              </p>
            )}
          </div>

          <div className="sheet-actions">
            <a className="btn-primary" href={hotel.booking_url || hotel.website || '#'}
               target="_blank" rel="noreferrer noopener">
              Book on {hotel.source === 'osm' ? 'their site' : 'Booking.com'} <External />
            </a>
            <button type="button" className="btn-secondary"
                    onClick={() => onAsk?.(`Tell me more about ${hotel.name}`)}>
              <Mic size={16} /> Ask about it
            </button>
          </div>

          {checkTimes(hotel) && <p className="fine">{checkTimes(hotel)}</p>}

          {rows.length > 0 && (
            <div className="sources-block">
              <p className="mono eyebrow">Where this came from</p>
              <ul className="srclist">
                {rows.map(([label, value]) => (
                  <li key={label}><span>{label}</span><span>{value}</span></li>
                ))}
              </ul>
            </div>
          )}

          <p className="fine">
            We don't hold rooms or take payment. That button opens the site the rate was quoted on.
          </p>
        </div>
      </section>
    </div>
  )
}
