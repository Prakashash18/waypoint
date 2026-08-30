/** Who is travelling, in the provider's own terms.
 *
 *  Each of these maps to a real Booking.com filter, so switching one on
 *  narrows the actual search rather than re-ranking what we already had.
 */
const NEEDS = [
  { id: 'kids',          label: 'Travelling with kids' },
  { id: 'wheelchair',    label: 'Wheelchair access' },
  { id: 'step_free',     label: 'Ground floor' },
  { id: 'elderly',       label: 'Lift, not stairs' },
  { id: 'pool',          label: 'Pool' },
  { id: 'breakfast',     label: 'Breakfast included' },
  { id: 'well_reviewed', label: 'Well reviewed' },
]

export default function NeedsBar({ selected, onToggle, disabled }) {
  return (
    <div className={`needs${selected.length ? ' has-selection' : ''}`}>
      <span className="mono needs-label">
        Needs{selected.length ? ` · ${selected.length}` : ''}
      </span>
      <ul>
        {NEEDS.map((need) => {
          const on = selected.includes(need.id)
          return (
            <li key={need.id}>
              <button type="button" className={`need${on ? ' is-on' : ''}`}
                      aria-pressed={on} disabled={disabled}
                      onClick={() => onToggle(need.id)}>
                <span className="need-tick" aria-hidden="true">
                  {on ? (
                    <svg viewBox="0 0 24 24" width="13" height="13" fill="none"
                         stroke="currentColor" strokeWidth="2.6" strokeLinecap="round"
                         strokeLinejoin="round"><path d="M4 12.5l5.5 5.5L20 6.5" /></svg>
                  ) : null}
                </span>
                {need.label}
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export { NEEDS }
