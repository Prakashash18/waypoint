import { useCallback, useEffect, useRef, useState } from 'react'
import { planTripStreaming, cancelPlan, forgetSession, getVoiceStatus } from './api'
import { useVoice } from './hooks/useVoice'
import { useLocale } from './hooks/useLocale'
import { money } from './lib/format'

import VoiceButton from './components/VoiceButton'
import TripTotal from './components/TripTotal'
import FlightCard from './components/FlightCard'
import HotelCard from './components/HotelCard'
import DateWindows from './components/DateWindows'
import KeepTalking from './components/KeepTalking'
import HotelDetail from './components/HotelDetail'
import BookingSheet from './components/BookingSheet'
import Answer from './components/Answer'
import AgentHUD from './components/AgentHUD'
import Settings from './components/Settings'
import ComboCard from './components/ComboCard'
import TripDetail from './components/TripDetail'
import NeedsBar from './components/NeedsBar'
import TracePanel from './components/TracePanel'
import { Pin, Crosshair } from './components/Icons'

const EXAMPLES = [
  'A few quiet nights in Bali, under $900, whenever is cheapest',
  'Cheapest week in Bangkok next month for two',
  'Somewhere with a pool near Ubud, great reviews',
]

export default function App() {
  const [brief, setBrief] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [liveSteps, setLiveSteps] = useState([])
  // Survives a reload so the conversation is not lost by refreshing the tab.
  const [sessionId, setSessionId] = useState(() => {
    try { return localStorage.getItem('waypoint.session') || null } catch { return null }
  })
  const [stopping, setStopping] = useState(false)
  const abortRef = useRef(null)
  const [error, setError] = useState('')
  const [voiceReady, setVoiceReady] = useState(false)
  const [voiceOut, setVoiceOut] = useState(true)
  const [openHotel, setOpenHotel] = useState(null)
  const [booking, setBooking] = useState(null)
  const [showWork, setShowWork] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  // Once a trip has been asked for the page stops being a landing page: the
  // hero collapses and the compose bar docks to the bottom as an overlay.
  const [conversing, setConversing] = useState(false)
  const [needs, setNeeds] = useState([])
  const [openCombo, setOpenCombo] = useState(null)
  // A date can be previewed without spending a search: the windows were all
  // priced already, so swapping one just re-does the arithmetic on screen.
  const [previewDate, setPreviewDate] = useState(null)

  const voice = useVoice({ enabled: voiceOut })
  const { locale, origin, airports } = useLocale()
  const inputRef = useRef(null)
  const resultsRef = useRef(null)

  useEffect(() => {
    getVoiceStatus()
      .then((v) => setVoiceReady(Boolean(v?.input?.available)))
      .catch(() => setVoiceReady(false))
  }, [])

  const run = useCallback(async (text, { spoken = false } = {}) => {
    let request = (text ?? brief).trim()
    if (!request || busy) return
    if (needs.length) {
      request += `. Travelling needs: ${needs.join(', ')}.`
    }
    setBusy(true)
    setError('')
    setStopping(false)
    setLiveSteps([])
    setConversing(true)
    setPreviewDate(null)
    // The HUD used to render below the fold, so nothing appeared to happen.
    window.scrollTo({ top: 0, behavior: 'smooth' })
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const context = {
        locale,
        lat: locale?.lat, lon: locale?.lon, timezone: locale?.timezone,
        origin_airport: origin?.iata,
        // What the traveller can actually see. The server's session is held in
        // memory, so a restart or a sleeping instance loses it — this lets a
        // follow-up still refer to the results on screen.
        seen: onScreen(result),
        needs,
      }
      // Streamed so the HUD can show each lookup as it happens, rather than
      // holding a spinner for the whole 15-odd seconds.
      const data = await planTripStreaming(request, context,
        (step) => setLiveSteps((prev) => [...prev, step]),
        {
          sessionId,
          signal: controller.signal,
          onSession: (id) => {
            setSessionId(id)
            try { localStorage.setItem('waypoint.session', id) } catch { /* private mode */ }
          },
        })
      setResult(data)
      if (spoken && voiceOut) voice.say(spokenSummary(data))

    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setBusy(false)
      setStopping(false)
      abortRef.current = null
    }
  }, [brief, busy, voice, voiceOut, locale, origin, sessionId])

  /** Interrupt the run. Whatever was found so far is kept. */
  const stop = useCallback(async () => {
    setStopping(true)
    await cancelPlan(sessionId)
  }, [sessionId])

  /** Start over: the agent forgets this conversation. */
  const startOver = useCallback(async () => {
    await forgetSession(sessionId)
    try { localStorage.removeItem('waypoint.session') } catch { /* private mode */ }
    setSessionId(null)
    setResult(null)
    setLiveSteps([])
    setBrief('')
    setConversing(false)
  }, [sessionId])

  const onTranscript = useCallback((text) => {
    setBrief(text)
    run(text, { spoken: true })
  }, [run])

  const trip = result?.trip
  const anchorDate = trip?.flight?.outbound?.depart?.slice(0, 10)

  // Previewing a date re-prices the options on screen from windows we already
  // paid for, so comparing dates costs nothing.
  const combos = (result?.combos || []).map((c) => {
    if (!previewDate || previewDate === anchorDate) return c
    const w = (trip?.windows || []).find((x) => x.depart === previewDate)
    if (!w || !c.includes_flight) return c
    return { ...c, flight_price: w.price_total,
             total: Math.round((w.price_total + c.hotel_price) * 100) / 100,
             previewing: previewDate }
  })

  return (
    <div className={`app${conversing ? ' is-conversing' : ''}`}>
      <header className="topbar">
        <a className="brand" href="/app">
          <span className="brand-mark"><Pin size={19} /></span>
          <span className="serif">Waypoint</span>
        </a>

        <div className="topbar-right">
          {origin && (
            <span className="chip origin-chip" title={origin.name}>
              <Crosshair /> {origin.iata}
            </span>
          )}
          {result && (
            <button type="button" className="chip" onClick={startOver}
                    title="The agent forgets this conversation and starts fresh">
              Start over
            </button>
          )}
          <button type="button" className="chip" onClick={() => setShowSettings(true)}
                  title="Prices, saved data and today’s allowance">
            Settings
          </button>
          <button
            type="button"
            className={`chip toggle${voiceOut ? ' is-on' : ''}`}
            onClick={() => { setVoiceOut((v) => !v); voice.stopSpeaking() }}
            aria-pressed={voiceOut}
          >
            {voiceOut ? 'Voice on' : 'Voice off'}
          </button>
        </div>
      </header>

      <main className="main">
        {/* ── ask ─────────────────────────────────────────── */}
        <section className={`compose${conversing ? ' is-answered' : ''}`}>
          {!conversing && (
            <>
              <p className="mono eyebrow centred">Plan a trip</p>
              <h1 className="serif display">Where are we going?</h1>
              <p className="lede">
                Say it the way you would to a friend. Dates are optional — without them
                we'll go looking for the cheapest window.
              </p>
              {origin && (
                <p className="origin-line">
                  <Crosshair /> Flying from <strong>{originLabel(origin)}</strong>
                  {locale?.currency ? <> · prices in <strong>{locale.currency}</strong></> : null}
                </p>
              )}
            </>
          )}

          {voiceReady && !conversing && (
            <div className="mic-stage">
              <VoiceButton voice={voice} onTranscript={onTranscript} disabled={busy} big />
            </div>
          )}

          <div className="ask">
            <textarea
              id="brief"
              ref={inputRef}
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') run() }}
              placeholder="A few quiet nights in Bali, under $900, whenever is cheapest…"
              rows={conversing ? 2 : 3}
              aria-label="What kind of trip?"
            />
            <div className="ask-actions">
              {voiceReady && conversing && (
                <VoiceButton voice={voice} onTranscript={onTranscript} disabled={busy} />
              )}
              {busy ? (
                <button type="button" className="btn-secondary is-stop" onClick={stop}
                        disabled={stopping}>
                  {stopping ? 'Stopping…' : 'Stop'}
                </button>
              ) : (
                <button type="button" className="btn-primary" onClick={() => run()}
                        disabled={!brief.trim()}>
                  Plan trip
                </button>
              )}
            </div>
          </div>

          <NeedsBar selected={needs} disabled={busy}
                    onToggle={(id) => setNeeds((prev) =>
                      prev.includes(id) ? prev.filter((n) => n !== id) : [...prev, id])} />

          {!conversing && (
            <ul className="examples">
              {EXAMPLES.map((ex) => (
                <li key={ex}>
                  <button type="button" onClick={() => { setBrief(ex); inputRef.current?.focus() }}>
                    {ex}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {(voice.error || error) && <p className="error" role="alert">{voice.error || error}</p>}

        {busy && <AgentHUD steps={liveSteps} done={false} stopping={stopping} />}

        {/* ── answer ──────────────────────────────────────── */}
        {result && (
          <div className="results" ref={resultsRef}>
            {combos.length > 0 ? (
              <>
                <div className="combos">
                  {combos.map((c) => (
                    <ComboCard key={c.label} combo={c}
                               onOpen={() => setOpenCombo(c)}
                               onAsk={(q) => { setBrief(q); run(q, { spoken: true }) }} />
                  ))}
                </div>
                <p className="combos-hint">
                  Tap an option to open it, or just ask — “is there anything quieter?”,
                  “what about the 26th?”
                </p>
              </>
            ) : (
              <section className="card answer-card">
                <Answer text={result.answer} busy={false} />
              </section>
            )}

            {trip?.windows?.length > 0 && (
              <DateWindows
                windows={trip.windows}
                anchor={anchorDate}
                hotelPrice={trip.hotel_price || 0}
                selected={previewDate || anchorDate}
                onPreview={(w) => setPreviewDate(w.depart)}
                onUse={(w) => {
                  const q = `Use ${w.depart}${w.return_date ? ` to ${w.return_date}` : ''} instead`
                  setBrief(q); run(q, { spoken: false })
                }}
              />
            )}

            {combos.length > 0 && (
              <details className="work">
                <summary>What we found, in full</summary>
                <div className="work-body"><Answer text={result.answer} busy={false} /></div>
              </details>
            )}

            <details className="work" open={showWork}
                     onToggle={(e) => setShowWork(e.currentTarget.open)}>
              <summary>
                How we got this — {result.tool_calls} lookups
                {result.sources?.missing?.length ? `, ${result.sources.missing.length} gap` : ''}
                {result.sources?.missing?.length > 1 ? 's' : ''}
              </summary>
              <div className="work-body">
                <TracePanel trace={result.trace} busy={false} />
                {result.sources?.missing?.length > 0 && (
                  <ul className="missing">
                    {result.sources.missing.map((m, i) => <li key={i}>{m}</li>)}
                  </ul>
                )}
                {result.sources?.attributions?.length > 0 && (
                  <p className="attribution">{result.sources.attributions.join(' · ')}</p>
                )}
              </div>
            </details>
          </div>
        )}
      </main>

      {result && voiceReady && (
        <footer className="dock">
          <KeepTalking voice={voice} onAsk={(t) => { setBrief(t); run(t, { spoken: true }) }}
                       disabled={busy} />
        </footer>
      )}

      {openHotel && (
        <HotelDetail hotel={openHotel} onClose={() => setOpenHotel(null)}
                     onAsk={(t) => { setOpenHotel(null); setBrief(t); run(t, { spoken: true }) }} />
      )}
      {openCombo && (
        <TripDetail combo={openCombo} onClose={() => setOpenCombo(null)}
                    onAsk={(q) => { setBrief(q); run(q, { spoken: true }) }}
                    onBookFlight={(f) => { setOpenCombo(null); setBooking(f) }} />
      )}
      {showSettings && <Settings onClose={() => setShowSettings(false)} />}
      {booking && (
        <BookingSheet flight={booking} voice={voiceOut ? voice : null}
                      onClose={() => setBooking(null)} />
      )}
    </div>
  )
}

/** A compact picture of what is on screen, for follow-up questions. */
function onScreen(result) {
  const trip = result?.trip
  if (!trip) return null
  const hotels = (result.artifacts?.hotels || []).slice(0, 8).map((h) => ({
    hotel_id: h.hotel_id, name: h.name, area: h.area,
    total_price: h.total_price, price_per_night: h.price_per_night,
    currency: h.currency, nights: h.nights,
    review_score: h.review_score, review_count: h.review_count,
    lat: h.lat, lon: h.lon, website: h.website, image_url: h.image_url,
  }))
  return {
    hotels,
    flight: trip.flight || null,
    windows: (trip.windows || []).slice(0, 9),
    locale: trip.locale || null,
  }
}

function originLabel(origin) {
  const city = origin.city || origin.name?.replace(/ (International )?Airport.*$/i, '')
  return `${city || origin.name} · ${origin.iata}`
}

/** Short enough to listen to; the written answer is far too long to read out. */
function spokenSummary(result) {
  const trip = result?.trip
  const missing = result?.sources?.missing || []

  if (!trip?.hotel && !trip?.flight) {
    const first = (result?.answer || '').split('\n').find((l) => l.trim())
    return first || 'I could not find anything to recommend.'
  }

  const parts = []
  if (trip.total != null) {
    parts.push(`About ${money(trip.total, trip.currency, { round: true })} all in${
      trip.passengers > 1 ? ` for ${trip.passengers}` : ''}.`)
  }
  if (trip.hotel) {
    parts.push(`The stay is ${trip.hotel.name}${
      trip.hotel.review_score > 0 ? `, rated ${trip.hotel.review_score} out of ten`
                                  : ', though it has no reviews yet'}.`)
  }
  if (trip.flight?.flight_code) {
    parts.push(`Flying ${trip.flight.flight_code} from ${trip.flight.origin}.`)
  }
  const cheapest = (trip.windows || []).reduce(
    (best, w) => (!best || w.price_total < best.price_total ? w : best), null)
  const anchor = trip.flight?.outbound?.depart?.slice(0, 10)
  if (cheapest && anchor && cheapest.depart !== anchor) {
    parts.push(`Leaving on the ${Number(cheapest.depart.slice(8, 10))}th would be cheaper.`)
  }
  if (missing.length) parts.push(`One thing I could not check: ${missing[0]}.`)
  return parts.join(' ')
}
