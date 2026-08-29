import { useCallback, useEffect, useRef, useState } from 'react'
import { planTrip, getProviders, getVoiceStatus } from './api'
import { useVoice } from './hooks/useVoice'
import VoiceButton from './components/VoiceButton'
import HotelCard from './components/HotelCard'
import TracePanel from './components/TracePanel'
import SourcePanel from './components/SourcePanel'
import ProviderPanel from './components/ProviderPanel'
import Answer from './components/Answer'

const EXAMPLES = [
  '4 nights in Ubud, Bali from Kuala Lumpur, 28 Sep to 2 Oct 2026, two adults, under $900 total. Somewhere quiet with great reviews.',
  'Cheapest decent hotel in Singapore for 2 nights from 28 Sep 2026, one adult.',
  'Find real hotels near Ubud from OpenStreetMap and show me their actual websites.',
]

const TABS = [
  { id: 'stay', label: 'Stays' },
  { id: 'trace', label: 'What it did' },
  { id: 'sources', label: 'Sources' },
]

export default function App() {
  const [brief, setBrief] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [providers, setProviders] = useState(null)
  const [voiceReady, setVoiceReady] = useState(false)
  const [voiceOut, setVoiceOut] = useState(true)
  const [tab, setTab] = useState('stay')

  const voice = useVoice({ enabled: voiceOut })
  const inputRef = useRef(null)

  useEffect(() => {
    getProviders().then(setProviders).catch(() => {})
    getVoiceStatus()
      .then((v) => setVoiceReady(Boolean(v?.input?.available)))
      .catch(() => setVoiceReady(false))
  }, [])

  const run = useCallback(async (text, { spoken = false } = {}) => {
    const request = (text ?? brief).trim()
    if (!request || busy) return
    setBusy(true)
    setError('')
    setResult(null)
    setTab('stay')
    try {
      const data = await planTrip(request)
      setResult(data)
      // Only talk back when the traveller talked to us first.
      if (spoken && voiceOut) voice.say(spokenSummary(data))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }, [brief, busy, voice, voiceOut])

  const onTranscript = useCallback((text) => {
    setBrief(text)
    run(text, { spoken: true })
  }, [run])

  const hotels = result?.artifacts?.hotels || []
  const trace = result?.trace || []
  const counts = {
    stay: hotels.length,
    trace: trace.length,
    sources: (result?.sources?.sources || []).length,
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden="true" />
          <h1>Waypoint</h1>
        </div>
        <div className="topbar-right">
          <button
            type="button"
            className={`pill toggle ${voiceOut ? 'on' : ''}`}
            onClick={() => { setVoiceOut((v) => !v); voice.stopSpeaking() }}
            aria-pressed={voiceOut}
          >
            {voiceOut ? 'voice on' : 'voice off'}
          </button>
        </div>
      </header>

      <main className="main">
        <section className="ask" aria-label="Trip request">
          <label className="sr-only" htmlFor="brief">What kind of trip?</label>
          <textarea
            id="brief"
            ref={inputRef}
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') run()
            }}
            placeholder="Ask in your own words — dates, budget, what matters to you."
            rows={3}
          />
          <div className="ask-actions">
            {voiceReady && (
              <VoiceButton voice={voice} onTranscript={onTranscript} disabled={busy} />
            )}
            <button type="button" className="primary" onClick={() => run()} disabled={busy || !brief.trim()}>
              {busy ? 'Planning…' : 'Plan trip'}
            </button>
          </div>
        </section>

        {(voice.error || error) && (
          <p className="error" role="alert">{voice.error || error}</p>
        )}

        <ul className="examples">
          {EXAMPLES.map((ex) => (
            <li key={ex}>
              <button type="button" onClick={() => { setBrief(ex); inputRef.current?.focus() }}>
                {ex.length > 58 ? `${ex.slice(0, 58)}…` : ex}
              </button>
            </li>
          ))}
        </ul>

        <div className="layout">
          <section className="card answer-card" aria-label="Recommendation">
            <div className="card-head">
              <h2>Recommendation</h2>
              {result && voiceOut && (
                <button
                  type="button"
                  className="pill"
                  onClick={() => (voice.speaking ? voice.stopSpeaking() : voice.say(spokenSummary(result)))}
                >
                  {voice.speaking ? 'stop' : 'read aloud'}
                </button>
              )}
            </div>
            <Answer text={result?.answer} busy={busy} />
          </section>

          <div className="side">
            <nav className="tabs" role="tablist">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  role="tab"
                  aria-selected={tab === t.id}
                  className={tab === t.id ? 'active' : ''}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                  {counts[t.id] > 0 && <span className="count">{counts[t.id]}</span>}
                </button>
              ))}
            </nav>

            {tab === 'stay' && (
              <div className="card" role="tabpanel">
                <h2>Stays found</h2>
                {hotels.length ? (
                  <div className="hotels">
                    {hotels.slice(0, 12).map((h) => (
                      <HotelCard key={h.hotel_id || h.name} hotel={h} />
                    ))}
                  </div>
                ) : (
                  <p className="muted">{busy ? 'Searching…' : 'Nothing yet.'}</p>
                )}
              </div>
            )}

            {tab === 'trace' && (
              <div className="card" role="tabpanel">
                <h2>What the agent did</h2>
                <TracePanel trace={trace} busy={busy} />
              </div>
            )}

            {tab === 'sources' && (
              <div role="tabpanel">
                <div className="card">
                  <h2>Sources this run</h2>
                  <SourcePanel sources={result?.sources} />
                </div>
                <div className="card">
                  <h2>Providers configured</h2>
                  <ProviderPanel providers={providers} />
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}

/** A short thing to say out loud — the written answer is far too long to read. */
function spokenSummary(result) {
  const hotels = (result?.artifacts?.hotels || []).filter((h) => h.total_price != null)
  const missing = result?.sources?.missing || []

  if (!hotels.length) {
    const first = (result?.answer || '').split('\n').find((l) => l.trim())
    return first || 'I could not find anything to recommend.'
  }

  const best = hotels[0]
  const parts = [
    `I found ${hotels.length} option${hotels.length === 1 ? '' : 's'}.`,
    `The best value is ${best.name}, ${Math.round(best.total_price)} ${best.currency || 'dollars'} total` +
      (best.review_score ? `, rated ${best.review_score} out of ten.` : '.'),
  ]
  if (missing.length) parts.push(`One thing I could not check: ${missing[0]}.`)
  return parts.join(' ')
}
