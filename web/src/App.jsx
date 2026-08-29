import { useCallback, useEffect, useRef, useState } from 'react'
import { planTrip, getVoiceStatus } from './api'
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
  const [error, setError] = useState('')
  const [voiceReady, setVoiceReady] = useState(false)
  const [voiceOut, setVoiceOut] = useState(true)
  const [openHotel, setOpenHotel] = useState(null)
  const [booking, setBooking] = useState(null)
  const [showWork, setShowWork] = useState(false)

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
    const request = (text ?? brief).trim()
    if (!request || busy) return
    setBusy(true)
    setError('')
    try {
      const context = {
        locale,
        lat: locale?.lat, lon: locale?.lon, timezone: locale?.timezone,
        origin_airport: origin?.iata,
      }
      const data = await planTrip(request, context)
      setResult(data)
      if (spoken && voiceOut) voice.say(spokenSummary(data))
      requestAnimationFrame(() =>
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }, [brief, busy, voice, voiceOut, locale, origin])

  const onTranscript = useCallback((text) => {
    setBrief(text)
    run(text, { spoken: true })
  }, [run])

  const trip = result?.trip
  const hotels = result?.artifacts?.hotels || []
  const alternatives = (trip?.alternatives || []).filter((h) => h.image_url || h.total_price != null)

  return (
    <div className="app">
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
        <section className={`compose${result ? ' is-answered' : ''}`}>
          {!result && (
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

          {voiceReady && !result && (
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
              rows={result ? 2 : 3}
              aria-label="What kind of trip?"
            />
            <div className="ask-actions">
              {voiceReady && result && (
                <VoiceButton voice={voice} onTranscript={onTranscript} disabled={busy} />
              )}
              <button type="button" className="btn-primary" onClick={() => run()}
                      disabled={busy || !brief.trim()}>
                {busy ? 'Planning…' : 'Plan trip'}
              </button>
            </div>
          </div>

          {!result && (
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

        {busy && !result && (
          <p className="working"><span className="spinner" /> Asking the airlines and the hotels…</p>
        )}

        {/* ── answer ──────────────────────────────────────── */}
        {result && (
          <div className="results" ref={resultsRef}>
            <TripTotal trip={trip} />

            <div className="pair">
              {trip?.flight && (
                <FlightCard flight={trip.flight} localeTz={locale?.timezone}
                            onBook={() => setBooking(trip.flight)} />
              )}
              {trip?.hotel && (
                <HotelCard hotel={trip.hotel} onOpen={() => setOpenHotel(trip.hotel)} />
              )}
            </div>

            {trip?.windows?.length > 0 && (
              <DateWindows
                windows={trip.windows}
                anchor={trip.flight?.outbound?.depart?.slice(0, 10)}
                hotelPrice={trip.hotel_price || 0}
                onPick={(w) => run(
                  `Use the ${w.depart}${w.return_date ? ` to ${w.return_date}` : ''} dates instead`,
                  { spoken: false })}
              />
            )}

            <section className="card answer-card">
              <div className="card-head">
                <h2>What we found</h2>
                {voiceOut && (
                  <button type="button" className="chip"
                          onClick={() => (voice.speaking ? voice.stopSpeaking() : voice.say(spokenSummary(result)))}>
                    {voice.speaking ? 'Stop' : 'Read aloud'}
                  </button>
                )}
              </div>
              <Answer text={result.answer} busy={false} />
            </section>

            {alternatives.length > 0 && (
              <section className="alts">
                <h2 className="mono eyebrow">Other places we looked at</h2>
                <div className="alt-grid">
                  {alternatives.map((h) => (
                    <HotelCard key={h.hotel_id || h.name} hotel={h} compact
                               onOpen={() => setOpenHotel(h)} />
                  ))}
                </div>
              </section>
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
      {booking && (
        <BookingSheet flight={booking} voice={voiceOut ? voice : null}
                      onClose={() => setBooking(null)} />
      )}
    </div>
  )
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
      trip.hotel.review_score ? `, rated ${trip.hotel.review_score} out of ten` : ''}.`)
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
