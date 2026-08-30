import { useEffect, useRef, useState } from 'react'

/** Secondary actions, folded away where the bar is too narrow for them.
 *
 *  On a phone the header wanted 401px of a 375px screen, so the voice toggle
 *  ran off the edge. These are the actions a traveller reaches for rarely;
 *  the origin and the voice state stay visible because they are status.
 */
export default function TopbarMenu({ items }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => { if (!wrapRef.current?.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  const usable = items.filter(Boolean)
  if (!usable.length) return null

  return (
    <div className="topmenu" ref={wrapRef}>
      <button type="button" className="chip topmenu-trigger"
              aria-expanded={open} aria-haspopup="menu" aria-label="More"
              onClick={() => setOpen((v) => !v)}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
          <circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" />
          <circle cx="19" cy="12" r="1.8" />
        </svg>
      </button>

      {open && (
        <ul className="topmenu-list" role="menu">
          {usable.map((item) => (
            <li key={item.label} role="none">
              <button type="button" role="menuitem"
                      onClick={() => { setOpen(false); item.onClick() }}>
                <span>{item.label}</span>
                {item.note && <span className="topmenu-note">{item.note}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
