import { money, shortDate } from '../lib/format'

/** Real prices for nearby departure dates, so shifting is a visible choice. */
export default function DateWindows({ windows, anchor, hotelPrice = 0, selected, onPreview, onUse }) {
  if (!windows?.length) return null

  const sorted = [...windows].sort((a, b) => a.depart.localeCompare(b.depart))
  const cheapest = windows.reduce((best, w) =>
    w.price_total < best.price_total ? w : best, windows[0])
  const chosen = windows.find((w) => w.depart === anchor)
  const saving = chosen ? Math.round(chosen.price_total - cheapest.price_total) : 0

  return (
    <section className="card windows-card">
      <header className="windows-head">
        <p className="mono eyebrow">If you can shift the dates</p>
        {saving > 0 && (
          <p className="saving">
            {shortDate(cheapest.depart)} saves {money(saving, cheapest.currency, { round: true })}
          </p>
        )}
      </header>

      <ul className="windows">
        {sorted.map((w) => {
          const isCheapest = w.depart === cheapest.depart
          const isChosen = w.depart === anchor
          const delta = chosen ? Math.round(w.price_total - chosen.price_total) : null
          return (
            <li key={w.depart}>
              <button
                type="button"
                className={`window${isChosen ? ' is-chosen' : ''}${isCheapest ? ' is-cheapest' : ''}`
                  + (selected === w.depart ? ' is-selected' : '')}
                aria-pressed={selected === w.depart}
                onClick={() => onPreview?.(w)}
              >
                <span className="window-date">
                  {w.return_date ? `${shortDate(w.depart)} – ${shortDate(w.return_date)}` : shortDate(w.depart)}
                </span>
                <span className="window-price">
                  {money(w.price_total + hotelPrice, w.currency, { round: true })}
                </span>
                <span className={`mono window-tag${delta > 0 ? ' is-more' : ''}`}>
                  {isChosen ? 'your dates'
                    : isCheapest ? 'cheapest'
                    : delta == null ? ''
                    : delta > 0 ? `+${money(delta, w.currency, { round: true })}`
                    : `−${money(Math.abs(delta), w.currency, { round: true })}`}
                </span>
              </button>
            </li>
          )
        })}
      </ul>

      {selected && selected !== anchor && (
        <p className="windows-foot">
          Totals above now show {shortDate(selected)}.
          <button type="button" className="btn-secondary is-small"
                  onClick={() => onUse?.(windows.find((w) => w.depart === selected))}>
            Search these dates
          </button>
        </p>
      )}
      <p className="fine">Tap a date to see what the trip would cost. Nothing is searched until you say so.</p>
    </section>
  )
}
