import { useEffect, useRef, useState } from 'react'

/** What the agent is doing, step by step, while it does it.
 *
 *  Every line is a real tool call: what was asked for, what came back, and how
 *  long it took. The plane advances one leg per completed call, so the motion
 *  reports progress rather than decorating a wait.
 */

// tool.capability -> how to say it to a traveller, and which glyph
const STEPS = {
  'locale.detect_locale':          ['Working out where you are', 'pin'],
  'places.nearest_airports':       ['Finding your nearest airport', 'tower'],
  'places.geocode_place':          ['Placing the destination', 'pin'],
  'places.find_hotels':            ['Looking up real places to stay', 'bed'],
  'places.match_hotel':            ['Tracing the hotel’s own website', 'link'],
  'places.describe_area':          ['Reading up on the area', 'book'],
  'atlas_flights.search_flights':  ['Checking live fares', 'plane'],
  'atlas_flights.find_date_deals': ['Pricing every nearby date', 'calendar'],
  'atlas_flights.verify_offer':    ['Re-checking that fare', 'plane'],
  'atlas_flights.confirm_price':   ['Locking the price', 'plane'],
  'hotel_rates.search_hotels':     ['Searching stays and rates', 'bed'],
  'hotel_rates.get_hotel_photos':  ['Collecting photographs', 'camera'],
  'imagery.capture_hotel_view':    ['Photographing the place', 'camera'],
  'imagery.find_photos':           ['Finding pictures nearby', 'camera'],
  'flight_status.check_delays':    ['Checking for delays', 'plane'],
}

// Which arguments are worth showing, in the order a person would say them.
const SHOW_PARAMS = ['origin', 'destination', 'place', 'query', 'name', 'around',
                     'depart', 'check_in', 'check_out', 'return_date', 'trip_nights',
                     'adults', 'needs', 'currency', 'flex_days', 'radius_m', 'lat', 'lon']

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.7,
                 strokeLinecap: 'round', strokeLinejoin: 'round' }

function Glyph({ kind, size = 15 }) {
  const paths = {
    plane: <path d="M17.8 19.2 16 11l3.5-3.5a2.1 2.1 0 0 0-3-3L13 8 4.8 6.2a.6.6 0 0 0-.6.9l3 4.5-2.4 2.4-2-.4a.6.6 0 0 0-.5 1l2 2 2 2a.6.6 0 0 0 1-.5l-.4-2 2.4-2.4 4.5 3a.6.6 0 0 0 .9-.6z" />,
    bed: <><path d="M3 18v-8h13a4 4 0 0 1 4 4v4" /><path d="M3 14h17M3 18h18" /><circle cx="7.5" cy="12.5" r="1.6" /></>,
    pin: <><path d="M12 21s6-5.4 6-9.8A6 6 0 0 0 6 11.2C6 15.6 12 21 12 21z" /><circle cx="12" cy="11" r="2" /></>,
    tower: <><path d="M12 3v18M8 21h8" /><path d="M6 9l12-3M6 6l12 3" /></>,
    camera: <><path d="M3 8h3l1.5-2h9L18 8h3v11H3z" /><circle cx="12" cy="13" r="3.4" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></>,
    link: <><path d="M10 13a4 4 0 0 0 5.7 0l2.6-2.6a4 4 0 0 0-5.7-5.7L11 6.4" /><path d="M14 11a4 4 0 0 0-5.7 0l-2.6 2.6a4 4 0 0 0 5.7 5.7L13 17.6" /></>,
    book: <><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" /><path d="M8 7h7M8 11h7" /></>,
  }
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} {...stroke} aria-hidden="true">
      {paths[kind] || paths.pin}
    </svg>
  )
}

/** The call's arguments, as a person would read them back. */
function argsOf(step) {
  const p = step.params || {}
  const parts = []
  if (p.origin && p.destination) parts.push(`${p.origin} → ${p.destination}`)
  for (const key of SHOW_PARAMS) {
    if ((key === 'origin' || key === 'destination') && p.origin && p.destination) continue
    const v = p[key]
    if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)) continue
    if (key === 'lat' || key === 'lon') continue          // shown as a pair below
    parts.push(Array.isArray(v) ? v.join(', ') : String(v))
    if (parts.length === 4) break
  }
  if (p.lat != null && p.lon != null) parts.push(`${Number(p.lat).toFixed(2)}, ${Number(p.lon).toFixed(2)}`)
  return parts.join(' · ')
}

export default function AgentHUD({ steps, done, stopping = false }) {
  const [elapsed, setElapsed] = useState(0)
  const started = useRef(Date.now())

  useEffect(() => {
    const id = setInterval(() => setElapsed((Date.now() - started.current) / 1000), 100)
    return () => clearInterval(id)
  }, [])

  const calls = steps.filter((s) => s.kind === 'tool_call')
  const failed = calls.filter((s) => s.status === 'error' || s.status === 'no_results')
  const progress = done ? 1 : 1 - 1 / (calls.length + 1.6)

  return (
    <section className="hud" aria-live="polite" aria-busy={!done}>
      <div className="hud-route" role="img" aria-label={`${calls.length} lookups so far`}>
        <span className="hud-dot is-origin" />
        <span className="hud-line"><span className="hud-trail" style={{ width: `${progress * 100}%` }} /></span>
        <span className="hud-dot is-dest" />
        <span className="hud-plane" style={{ left: `${progress * 100}%` }}><Glyph kind="plane" size={19} /></span>
      </div>

      <ol className="hud-steps">
        {calls.map((step, i) => {
          const key = `${step.tool}.${step.capability}`
          const [label, glyph] = STEPS[key] || [key.replace(/[._]/g, ' '), 'pin']
          const live = i === calls.length - 1 && !done
          const bad = step.status === 'error' || step.status === 'no_results'
          const args = argsOf(step)
          const auto = (step.summary || '').startsWith('[auto]')
          const said = (step.summary || '').replace('[auto] ', '')

          return (
            <li key={`${key}-${i}`} className={`hud-step${live ? ' is-live' : ''}${bad ? ' is-empty' : ''}`}>
              <span className="hud-glyph"><Glyph kind={glyph} /></span>
              <div className="hud-detail">
                <p className="hud-line-1">
                  <span className="hud-label">{label}</span>
                  {auto && <span className="badge tiny">guaranteed</span>}
                  <span className="hud-ms">{(step.duration_ms / 1000).toFixed(1)}s</span>
                </p>
                <p className="mono hud-call">
                  {step.tool}.{step.capability}{args ? ` — ${args}` : ''}
                </p>
                {said && <p className="hud-said">{said}</p>}
              </div>
            </li>
          )
        })}

        {!done && (
          <li className={`hud-step is-pending${stopping ? ' is-stopping' : ''}`}>
            <span className="hud-glyph"><span className="hud-pulse" /></span>
            <div className="hud-detail">
              <p className="hud-line-1">
                <span className="hud-label">
                  {stopping ? 'Stopping — finishing the call already in flight'
                    : calls.length ? 'Working out what to recommend'
                    : 'Getting started'}
                </span>
                <span className="hud-ms">{elapsed.toFixed(1)}s</span>
              </p>
            </div>
          </li>
        )}
      </ol>

      {failed.length > 0 && (
        <p className="hud-note">
          {failed.length} source{failed.length > 1 ? 's' : ''} had nothing — you'll see exactly which.
        </p>
      )}
    </section>
  )
}
