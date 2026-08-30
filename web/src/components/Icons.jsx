/** Stroke icons on a 24px grid, sized by prop so they scale with their row. */
const base = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.7,
               strokeLinecap: 'round', strokeLinejoin: 'round' }

export const Pin = ({ size = 20 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} {...base} aria-hidden="true">
    <path d="M12 21s7-6.3 7-11.4A7 7 0 0 0 5 9.6C5 14.7 12 21 12 21z" />
    <circle cx="12" cy="9.5" r="2.4" />
  </svg>
)

export const Mic = ({ size = 20 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} {...base} aria-hidden="true">
    <rect x="9" y="2.5" width="6" height="11.5" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3.5" />
  </svg>
)

export const Plane = ({ size = 18 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} {...base} aria-hidden="true">
    <path d="M17.8 19.2 16 11l3.5-3.5a2.1 2.1 0 0 0-3-3L13 8 4.8 6.2a.6.6 0 0 0-.6.9l3 4.5-2.4 2.4-2-.4a.6.6 0 0 0-.5 1l2 2 2 2a.6.6 0 0 0 1-.5l-.4-2 2.4-2.4 4.5 3a.6.6 0 0 0 .9-.6z" />
  </svg>
)

export const External = ({ size = 15 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} {...base} strokeWidth={1.9} aria-hidden="true">
    <path d="M8 16 16 8M9 8h7v7" />
  </svg>
)

export const Back = ({ size = 16 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} {...base} strokeWidth={2} aria-hidden="true">
    <path d="M14 6l-6 6 6 6" />
  </svg>
)

export const Crosshair = ({ size = 15 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} {...base} strokeWidth={1.8} aria-hidden="true">
    <circle cx="12" cy="12" r="3.2" /><circle cx="12" cy="12" r="8" />
    <path d="M12 1.5v2.5M12 20v2.5M1.5 12H4M20 12h2.5" />
  </svg>
)

export const Info = ({ size = 14 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} {...base} strokeWidth={1.9} aria-hidden="true">
    <circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 7.6v.1" />
  </svg>
)

export const Close = ({ size = 18 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} {...base} strokeWidth={1.9} aria-hidden="true">
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
)

export const Traveller = ({ size = 14 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} {...base} aria-hidden="true">
    <circle cx="12" cy="7.5" r="3.6" />
    <path d="M4.5 20.5a7.5 7.5 0 0 1 15 0" />
  </svg>
)

export const Night = ({ size = 14 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} {...base} aria-hidden="true">
    <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />
  </svg>
)
