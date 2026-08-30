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
import ChatThread from './components/ChatThread'
import ChosenTrip from './components/ChosenTrip'
import TripStrip from './components/TripStrip'
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
  // The visible conversation. The agent keeps its own history server-side;
  // this is what the traveller can actually read.
  const [messages, setMessages] = useState([])
  // One decision per step: choose a trip, refine it, then talk about it.
  // 'choose' shows only the options; 'refine' opens the one picked and only
  // then offers the dates; 'ask' folds it to a strip so the reply has room.
  const [stage, setStage] = useState('choose')
  const [chosen, setChosen] = useState(null)

  const voice = useVoice({ enabled: voiceOut })
  const { locale, origin, airports } = useLocale()
  const inputRef = useRef(null)
  const resultsRef = useRef(null)
  const composeRef = useRef(null)

  useEffect(() => {
    const bar = composeRef.current
    if (!bar || !conversing) {
      document.documentElement.style.removeProperty('--dock-h')
      return undefined
    }
    const measure = () => document.documentElement.style
      .setProperty('--dock-h', `${Math.ceil(bar.getBoundingClientRect().height)}px`)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(bar)
    return () => { observer.disconnect() }
  }, [conversing, needs.length, busy])

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
    if (chosen) setStage('ask')
    setMessages((prev) => [...prev, { role: 'user', text: request }])
    setBrief('')
    if (!chosen) setStage('choose')
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
        // Which trip is open. Without this, "that hotel" is ambiguous the
        // moment more than one option has been found, and the agent has to
        // stop and ask which one.
        looking_at: chosen ? {
          label: chosen.label,
          hotel: chosen.hotel?.name,
          hotel_id: chosen.hotel?.hotel_id,
          lat: chosen.hotel?.lat,
          lon: chosen.hotel?.lon,
          total: chosen.total,
          currency: chosen.currency,
          flight: chosen.flight?.flight_code,
          airline: chosen.flight?.airline_name,
        } : null,
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
      setMessages((prev) => [...prev, {
        role: 'assistant', text: data.answer,
        lookups: data.tool_calls, cards: data.cards || [],
      }])
      if (spoken && voiceOut) voice.say(spokenSummary(data))

    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setBusy(false)
      setStopping(false)
      abortRef.current = null
    }
  }, [brief, busy, voice, voiceOut, locale, origin, sessionId, needs, result, chosen])

  /** Ask a follow-up. Clears the box so the thread is the record, not the input. */
  const ask = useCallback((question) => {
    run(question, { spoken: voiceOut })
  }, [run, voiceOut])

  const choose = useCallback((combo) => {
    setChosen(combo)
    setStage('refine')
  }, [])

  const stepBack = useCallback(() => {
    if (stage === 'ask') { setStage('refine'); return }
    setChosen(null)
    setStage('choose')
  }, [stage])

  /** Bring a just-expanded panel out from behind the docked bar.
   *
   *  Expanding happens in place, so the content it reveals lands underneath
   *  the overlay. The page can be scrolled, but nothing says so — it simply
   *  looks cut off. This scrolls just far enough to clear the bar.
   */
  const revealBelowDock = useCallback((el) => {
    if (!el) return
    requestAnimationFrame(() => {
      const dockTop = composeRef.current?.getBoundingClientRect().top ?? window.innerHeight
      const hidden = el.getBoundingClientRect().bottom - dockTop
      if (hidden <= 0) return
      // Never scroll past the element's own top; seeing the start of it
      // matters more than seeing the end.
      const room = Math.max(0, el.getBoundingClientRect().top - 80)
      window.scrollBy({ top: Math.min(hidden + 16, room + hidden), behavior: 'smooth' })
    })
  }, [])

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
    setMessages([])
    setChosen(null)
    setStage('choose')
  }, [sessionId])

  const onTranscript = useCallback((text) => {
    // No need to put it in the box first — run() clears it, and the thread
    // shows what was heard.
    run(text, { spoken: true })
  }, [run])

  const trip = result?.trip
  const anchorDate = trip?.flight?.outbound?.depart?.slice(0, 10)

  // With an answer on screen the box prompts the next question rather than
  // repeating a generic hint — the agent already worked out what is worth
  // asking, so the input may as well say it.
  const suggested = result?.follow_ups?.[0]
  const nextPrompt = !conversing
    ? 'A few quiet nights in Bali, under $900, whenever is cheapest…'
    : busy
      ? 'Ask something else while this runs…'
      : suggested
        ? `Ask anything — e.g. “${suggested}”`
        : 'Ask anything — “somewhere quieter?”, “what about the 26th?”'

  // Previewing a date re-prices the options on screen from windows we already
  // paid for, so comparing dates costs nothing.
  const repriced = (c) => {
    if (!previewDate || previewDate === anchorDate) return c
    const w = (trip?.windows || []).find((x) => x.depart === previewDate)
    if (!w || !c.includes_flight) return c
    return { ...c, flight_price: w.price_total,
             total: Math.round((w.price_total + c.hotel_price) * 100) / 100,
             previewing: previewDate }
  }
  const combos = (result?.combos || []).map(repriced)

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
        <section ref={composeRef} className={`compose${conversing ? ' is-answered' : ''}`}>
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
              onKeyDown={(e) => {
                if (e.key !== 'Enter') return
                // In conversation this is a chat box: Enter sends, Shift+Enter
                // starts a new line. Before that, only the deliberate
                // Cmd/Ctrl+Enter submits, so a long brief can be typed freely.
                if (conversing ? !e.shiftKey : (e.metaKey || e.ctrlKey)) {
                  e.preventDefault()
                  run()
                }
              }}
              placeholder={nextPrompt}
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
                  {conversing ? 'Enter' : 'Plan trip'}
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
            {/* Step 1 — which trip? Nothing else competes with the question. */}
            {stage === 'choose' && combos.length > 0 && (
              <>
                <div className="step-head">
                  <p className="mono eyebrow">
                    Step 1 of 3{trip?.nights ? ` · ${trip.nights} nights` : ''}
                    {trip?.passengers > 1 ? `, ${trip.passengers} adults` : ''}
                  </p>
                  <h2 className="serif step-question">Which trip?</h2>
                  <p className="step-note">
                    Every price is the whole trip — {combos[0]?.includes_flight
                      ? 'both fares and every night' : 'the stay in full'}.
                  </p>
                </div>
                <div className="combos">
                  {combos.map((c) => (
                    <ComboCard key={c.label} combo={c}
                               onOpen={() => choose(c)}
                               onChoose={() => choose(c)}
                               onAsk={ask} />
                  ))}
                </div>
              </>
            )}

            {/* Step 2 — the one picked, and only now the dates. */}
            {stage === 'refine' && chosen && (
              <>
                <ChosenTrip combo={repriced(chosen)} otherCount={combos.length}
                            onBack={stepBack}
                            onBookFlight={(f) => setBooking(f)}
                            onOpenStay={(h) => setOpenHotel(h)} />

                {trip?.windows?.length > 0 && (
                  <DateWindows
                    windows={trip.windows}
                    anchor={anchorDate}
                    hotelPrice={chosen.hotel_price || 0}
                    selected={previewDate || anchorDate}
                    onPreview={(w) => setPreviewDate(w.depart)}
                    onUse={(w) => ask(`Use ${w.depart}${w.return_date ? ` to ${w.return_date}` : ''} instead`)}
                  />
                )}
              </>
            )}

            {/* Step 3 — the conversation, with the trip out of the way. */}
            {stage === 'ask' && chosen && <TripStrip combo={repriced(chosen)} onBack={stepBack} />}

            {(stage === 'ask' || messages.length > 2) && (
              <ChatThread messages={messages} busy={busy} onAsk={ask}
                          onBookFlight={() => { if (trip?.flight) setBooking(trip.flight) }}
                          onOpenStay={(card) => {
                            const full = (result.artifacts?.hotels || [])
                              .find((h) => h.hotel_id === card.hotel_id)
                            if (full) setOpenHotel(full)
                          }}
                          suggestions={result.follow_ups?.length
                            ? result.follow_ups : followUps(combos, trip)} />
            )}

            <details className="work" open={showWork}
                     onToggle={(e) => {
                       setShowWork(e.currentTarget.open)
                       if (e.currentTarget.open) revealBelowDock(e.currentTarget)
                     }}>
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
          <KeepTalking voice={voice} onAsk={(t) => run(t, { spoken: true })}
                       disabled={busy} />
        </footer>
      )}

      {openHotel && (
        <HotelDetail hotel={openHotel} onClose={() => setOpenHotel(null)}
                     onAsk={(t) => { setOpenHotel(null); run(t, { spoken: true }) }} />
      )}
      {openCombo && (
        <TripDetail combo={openCombo} onClose={() => setOpenCombo(null)}
                    onAsk={(q) => run(q, { spoken: true })}
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

/** Questions worth asking about these specific results. */
function followUps(combos, trip) {
  const out = []
  if (combos.length > 1) out.push(`What is the real difference between ${combos[0].label.toLowerCase()} and ${combos[1].label.toLowerCase()}?`)
  const named = combos[0]?.hotel?.name
  if (named) out.push(`Is ${named} quiet at night?`)
  if (named) out.push(`What is within walking distance of ${named}?`)
  if ((trip?.windows || []).length > 1) out.push('Which dates would save the most?')
  return out.slice(0, 4)
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
    parts.push(`Flying ${trip.flight.airline_name || trip.flight.flight_code}`
      + ` from ${trip.flight.origin}.`)
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
