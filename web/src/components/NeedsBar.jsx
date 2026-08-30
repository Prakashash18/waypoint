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
    <div className="needs">
      <span className="mono needs-label">Needs</span>
      <ul>
        {NEEDS.map((need) => {
          const on = selected.includes(need.id)
          return (
            <li key={need.id}>
              <button type="button" className={`need${on ? ' is-on' : ''}`}
                      aria-pressed={on} disabled={disabled}
                      onClick={() => onToggle(need.id)}>
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
