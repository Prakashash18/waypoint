import { useCallback, useEffect, useMemo, useState } from 'react'
import { money, clockTime, shortDate, duration } from '../lib/format'
import { Close, Mic } from './Icons'
import PassportDrop from './PassportDrop'

/** Confirming a flight, by voice or by keyboard.
 *
 *  Booking is the one irreversible thing here, so the sheet states the exact
 *  fare and party before anything happens, and every step it claims to have
 *  run really ran against the airline.
 */

// Atlas wants FAMILY/GIVEN, "M"/"F", an ISO birthday and a 00<cc>-<number>
// mobile. Rather than let the airline reject the form, say so here.
const NAME_RE = /^[A-Za-z][A-Za-z .'-]*\/[A-Za-z][A-Za-z .'-]*$/
const MOBILE_RE = /^00[1-9][0-9]{0,2}-[0-9]{6,14}$/
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/

const YES = /\b(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|book it|confirm|please do)\b/i
const NO = /\b(no|nope|not yet|cancel|stop|wait|don'?t|hold on)\b/i

const blankPassenger = () => ({ name: '', gender: '', birthday: '',
                                nationality: '', document: null })

export default function BookingSheet({ flight, onClose, voice }) {
  const [spoken, setSpoken] = useState(false)
  const [steps, setSteps] = useState(null)
  const [checking, setChecking] = useState(false)
  const [prep, setPrep] = useState(null)

  // Confirming out loud and confirming by typing are the same act; some
  // people are in a quiet room, and some just prefer a keyboard.
  const [typed, setTyped] = useState('')
  const [reply, setReply] = useState(null)

  // choosing → details → ordered
  const [phase, setPhase] = useState('choosing')
  const [bagKg, setBagKg] = useState(null)
  const [bagBusy, setBagBusy] = useState(false)
  const [bagNote, setBagNote] = useState(null)

  const [people, setPeople] = useState([])
  const [contact, setContact] = useState({ name: '', email: '', mobile: '' })
  const [badFields, setBadFields] = useState([])
  const [placing, setPlacing] = useState(false)
  const [order, setOrder] = useState(null)
  const [failed, setFailed] = useState(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!flight?.offer_id) return undefined
    let live = true
    setChecking(true)
    fetch('/api/booking/prepare', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ offer_id: flight.offer_id, currency: flight.currency,
                             quoted_total: flight.price_total }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (!live) return
        setSteps(d.steps || [])
        setPrep(d)
        const n = (d.travelers || []).length || flight.passengers || 1
        setPeople(Array.from({ length: n }, blankPassenger))
      })
      .catch(() => { if (live) { setSteps([]); setFailed('Could not reach the airline.') } })
      .finally(() => { if (live) setChecking(false) })
    return () => { live = false }
  }, [flight])

  const bagStep = (steps || []).find((s) => s.key === 'baggage')
  const bagOptions = bagStep?.options || []
  const travellers = prep?.travelers || []
  const currency = flight?.currency || ''

  const chosenBag = useMemo(
    () => bagOptions.find((o) => o.weight_kg === bagKg) || null,
    [bagOptions, bagKg])

  // The fare Atlas re-confirmed beats whatever the card was showing.
  const fare = prep?.confirmed_total ?? flight?.price_total ?? 0
  const bagsTotal = chosenBag ? (chosenBag.price || 0) * (travellers.length || 1) : 0
  const runningTotal = fare + bagsTotal

  const priceLine = flight && (
    `${money(fare, currency)} with ${flight.airline_name || 'the airline'} for ` +
    `${flight.passengers > 1 ? `${flight.passengers} passengers` : 'one passenger'}. Shall I book it?`
  )

  useEffect(() => {
    if (flight && !spoken && voice?.say && !checking && steps) {
      setSpoken(true)
      voice.say(priceLine)
    }
  }, [flight, spoken, voice, priceLine, checking, steps])

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  /** Pick a bag — one call per leg, because that is how it is sold. */
  const pickBag = useCallback(async (opt) => {
    if (!prep?.booking_id || bagBusy) return
    const clearing = !opt || opt.weight_kg === bagKg
    setBagBusy(true)
    setBagNote(null)
    try {
      const legs = clearing ? (chosenBag?.legs || []) : opt.legs
      const results = []
      for (const t of (travellers.length ? travellers : [{ traveler_id: null }])) {
        for (const leg of legs) {
          const r = await fetch('/api/booking/baggage', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              booking_id: prep.booking_id,
              traveler_id: t.traveler_id,
              segment_id: leg.segment_id,
              baggage_id: clearing ? '' : leg.baggage_id,
            }),
          }).then((x) => x.json())
          results.push(r)
        }
      }
      const bad = results.find((r) => !r.success)
      if (bad) {
        setBagNote(bad.error || 'The airline would not take that bag.')
      } else {
        setBagKg(clearing ? null : opt.weight_kg)
      }
    } catch {
      setBagNote('Could not reach the airline to add that bag.')
    } finally {
      setBagBusy(false)
    }
  }, [prep, bagBusy, bagKg, chosenBag, travellers])

  /** An answer, however it arrived. */
  const answer = useCallback((said) => {
    const text = (said || '').trim()
    if (!text) return
    setTyped('')
    if (NO.test(text) && !YES.test(text)) {
      setReply('Nothing booked. The fare stays held until you close this.')
      voice?.say?.('Alright, nothing booked.')
      return
    }
    if (YES.test(text)) {
      setReply(null)
      setPhase('details')
      voice?.say?.('I need each traveller’s full name, date of birth and a contact.')
      return
    }
    setReply('I only understand “yes” or “no” here — everything else, ask me in the chat.')
  }, [voice])

  const localProblems = useMemo(() => {
    const bad = []
    people.forEach((p, i) => {
      if (!NAME_RE.test(p.name.trim())) bad.push(`passengers[${i}].name`)
      if (p.gender !== 'M' && p.gender !== 'F') bad.push(`passengers[${i}].gender`)
      if (!ISO_DATE_RE.test(p.birthday)) bad.push(`passengers[${i}].birthday`)
    })
    if (!NAME_RE.test(contact.name.trim())) bad.push('contact.name')
    if (contact.email && !EMAIL_RE.test(contact.email)) bad.push('contact.email')
    if (contact.mobile && !MOBILE_RE.test(contact.mobile)) bad.push('contact.mobile')
    return bad
  }, [people, contact])

  const placeOrder = useCallback(async () => {
    if (localProblems.length) { setBadFields(localProblems); return }
    setPlacing(true)
    setBadFields([])
    setFailed(null)
    try {
      const r = await fetch('/api/booking/order', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          booking_id: prep.booking_id,
          passengers: people.map((p, i) => ({
            traveler_id: travellers[i]?.traveler_id,
            name: p.name.trim().toUpperCase(),
            passenger_type: 'adult',
            gender: p.gender,
            birthday: p.birthday,
            // Only sent when a passport actually supplied them.
            ...(p.nationality ? { nationality: p.nationality } : {}),
            ...(p.document?.number ? { document: p.document } : {}),
          })),
          contact: {
            name: contact.name.trim().toUpperCase(),
            email: contact.email || undefined,
            mobile: contact.mobile || undefined,
          },
        }),
      }).then((x) => x.json())

      if (!r.success) {
        setBadFields(r.fields || [])
        setFailed(r.error || 'The airline would not accept these details.')
        return
      }
      setOrder(r)
      setPhase('ordered')
      voice?.say?.('Your order is created and held. The last step is payment.')
    } catch {
      setFailed('Could not reach the airline to create the order.')
    } finally {
      setPlacing(false)
    }
  }, [localProblems, prep, people, contact, travellers, voice])

  const deadline = order?.payment_deadline ? new Date(order.payment_deadline) : null
  const overdue = deadline ? deadline.getTime() < Date.now() : false

  if (!flight) return null

  const legs = [flight.outbound, flight.return_leg].filter(Boolean)
  const marks = (f) => (badFields.includes(f) ? ' is-bad' : '')

  // Turn Atlas's field paths into something a traveller can act on, and single
  // out the ones with no input to correct.
  const FIELD_WORDS = {
    name: 'the name, as FAMILY/GIVEN',
    gender: 'the gender',
    birthday: 'the date of birth',
    'document.expires': 'the passport expiry — this document has expired',
    'document.number': 'the passport number',
    'document.issuing_country': 'the country that issued the passport',
    nationality: 'the nationality',
  }
  const describeField = (path) => {
    const who = path.match(/^passengers\[(\d+)\]\./)
    const tail = path.replace(/^passengers\[\d+\]\./, '').replace(/^contact\./, '')
    const words = FIELD_WORDS[tail] || tail
    return who ? `Traveller ${Number(who[1]) + 1}: ${words}` : `Contact: ${words}`
  }
  const unmapped = badFields.filter(
    (f) => !/\.(name|gender|birthday)$/.test(f) && !f.startsWith('contact.'))

  return (
    <div className="sheet-backdrop" onClick={onClose} role="presentation">
      <section className="sheet is-booking" onClick={(e) => e.stopPropagation()}
               role="dialog" aria-modal="true" aria-label="Confirm this booking">
        <button type="button" className="sheet-close" onClick={onClose} aria-label="Close">
          <Close />
        </button>

        <div className="sheet-body">
          <p className="mono eyebrow">
            Booking with {flight.airline_name || flight.airline || 'the airline'}
          </p>

          <div className="booking-legs">
            {legs.map((leg, i) => (
              <div className="leg" key={i}>
                <span className="mono leg-code">{leg.flight_code || leg.flight_number}</span>
                <div className="leg-times">
                  <div><p className="leg-clock">{clockTime(leg.depart)}</p><p className="leg-port">{leg.origin}</p></div>
                  <div className="leg-rule"><span /><em>{duration(leg.duration_minutes)}</em><span /></div>
                  <div className="leg-end"><p className="leg-clock">{clockTime(leg.arrive)}</p><p className="leg-port">{leg.destination}</p></div>
                </div>
                <span className="leg-date">{shortDate(leg.depart)}</span>
              </div>
            ))}
          </div>

          <div className="booking-total">
            <div>
              <p>{flight.passengers > 1 ? `${flight.passengers} passengers` : 'One passenger'}</p>
              <p className="fine">
                {chosenBag
                  ? `Fare ${money(fare, currency)} + ${chosenBag.weight_kg}kg bags ${money(bagsTotal, currency)}`
                  : 'Seats assigned at check-in'}
              </p>
            </div>
            <strong>{money(runningTotal, currency)}</strong>
          </div>

          {/* ── choose ─────────────────────────────────────────── */}
          {phase === 'choosing' && (
            <>
              {bagOptions.length > 0 && (
                <div className="bagpick">
                  <p className="mono eyebrow">Checked baggage</p>
                  <p className="fine">
                    Priced per traveller for the whole trip. Pick one, or fly with
                    cabin baggage only.
                  </p>
                  <div className="bagpick-row" role="group" aria-label="Checked baggage">
                    {bagOptions.map((o) => (
                      <button
                        key={o.weight_kg}
                        type="button"
                        className={`bagopt${bagKg === o.weight_kg ? ' is-on' : ''}`}
                        aria-pressed={bagKg === o.weight_kg}
                        disabled={bagBusy}
                        onClick={() => pickBag(o)}
                      >
                        <strong>{o.weight_kg}kg</strong>
                        <span>{o.currency} {Number(o.price).toFixed(2)}</span>
                      </button>
                    ))}
                  </div>
                  {bagBusy && <p className="fine">Telling the airline…</p>}
                  {bagNote && <p className="warn-line">{bagNote}</p>}
                  {bagKg && !bagBusy && (
                    <p className="fine">
                      {bagKg}kg added for {travellers.length || 1}
                      {(travellers.length || 1) > 1 ? ' travellers' : ' traveller'}.
                      Tap it again to remove.
                    </p>
                  )}
                </div>
              )}

              <p className="serif booking-ask">“{priceLine}”</p>

              <div className="booking-reply">
                <button type="button" className="btn-secondary booking-hold"
                        onPointerDown={() => voice?.start?.()}
                        onPointerUp={async () => {
                          const said = await voice?.stopAndTranscribe?.()
                          if (said) answer(said)
                        }}>
                  <Mic size={16} /> Hold to answer
                </button>
                <span className="booking-or">or</span>
                <form className="booking-typed"
                      onSubmit={(e) => { e.preventDefault(); answer(typed) }}>
                  <input
                    type="text"
                    className="booking-type"
                    value={typed}
                    onChange={(e) => setTyped(e.target.value)}
                    placeholder="type yes or no…"
                    aria-label="Answer by typing instead of speaking"
                  />
                  <button type="submit" className="btn-primary" disabled={!typed.trim()}>
                    Enter
                  </button>
                </form>
              </div>
              {reply && <p className="booking-said">{reply}</p>}
            </>
          )}

          {/* ── who is flying ──────────────────────────────────── */}
          {phase === 'details' && (
            <div className="paxform">
              <p className="mono eyebrow">Who is flying</p>
              <p className="fine">
                Names must match the passport, in the airline's own format:
                family name, a slash, then given names — <code>TAN/WEI MING</code>.
              </p>

              {people.map((p, i) => (
                <fieldset className="paxrow" key={i}>
                  <legend>Traveller {i + 1}</legend>

                  {/* A passport already holds every one of these fields, in a
                      form that can be checked rather than trusted. */}
                  <PassportDrop onRead={(f) => setPeople((ps) => ps.map((x, j) => (
                    j === i ? {
                      ...x,
                      name: f.name || x.name,
                      gender: f.gender || x.gender,
                      birthday: f.birthday || x.birthday,
                      nationality: f.nationality || x.nationality || '',
                      document: f.document_number ? {
                        type: f.document_type === 'PP' ? 'PP' : 'PP',
                        number: f.document_number,
                        issuing_country: f.issuing_country || undefined,
                        expires: f.expires || undefined,
                      } : x.document,
                    } : x))) } />

                  <label>
                    <span>Name as in passport</span>
                    <input type="text" value={p.name} placeholder="TAN/WEI MING"
                           className={marks(`passengers[${i}].name`)}
                           onChange={(e) => setPeople((ps) => ps.map((x, j) =>
                             j === i ? { ...x, name: e.target.value } : x))} />
                  </label>
                  <div className="paxrow-pair">
                    <label>
                      <span>Date of birth</span>
                      <input type="date" value={p.birthday}
                             className={marks(`passengers[${i}].birthday`)}
                             onChange={(e) => setPeople((ps) => ps.map((x, j) =>
                               j === i ? { ...x, birthday: e.target.value } : x))} />
                    </label>
                    <label>
                      <span>Gender on passport</span>
                      <select value={p.gender}
                              className={marks(`passengers[${i}].gender`)}
                              onChange={(e) => setPeople((ps) => ps.map((x, j) =>
                                j === i ? { ...x, gender: e.target.value } : x))}>
                        <option value="">Choose…</option>
                        <option value="F">F</option>
                        <option value="M">M</option>
                      </select>
                    </label>
                  </div>
                </fieldset>
              ))}

              <fieldset className="paxrow">
                <legend>Where the airline reaches you</legend>
                <label>
                  <span>Contact name</span>
                  <input type="text" value={contact.name} placeholder="TAN/WEI MING"
                         className={marks('contact.name')}
                         onChange={(e) => setContact((c) => ({ ...c, name: e.target.value }))} />
                </label>
                <div className="paxrow-pair">
                  <label>
                    <span>Email</span>
                    <input type="email" value={contact.email} placeholder="you@example.com"
                           className={marks('contact.email')}
                           onChange={(e) => setContact((c) => ({ ...c, email: e.target.value }))} />
                  </label>
                  <label>
                    <span>Mobile</span>
                    <input type="tel" value={contact.mobile} placeholder="0065-91234567"
                           className={marks('contact.mobile')}
                           onChange={(e) => setContact((c) => ({ ...c, mobile: e.target.value }))} />
                  </label>
                </div>
              </fieldset>

              {badFields.length > 0 && (
                <div className="warn-line">
                  <p>{failed || 'The airline would not accept some of these details.'}</p>
                  <ul className="badlist">
                    {badFields.map((f) => <li key={f}>{describeField(f)}</li>)}
                  </ul>
                  {unmapped.length > 0 && (
                    <p className="fine">
                      There is no box here for that — it came from the scanned
                      passport. Use a document that is still valid, or clear the
                      scan and type the details in.
                    </p>
                  )}
                </div>
              )}
              {failed && badFields.length === 0 && <p className="warn-line">{failed}</p>}

              <div className="sheet-actions">
                <button type="button" className="btn-primary is-wide"
                        onClick={placeOrder} disabled={placing}>
                  {placing ? 'Creating the order…' : `Create the order · ${money(runningTotal, currency)}`}
                </button>
                <button type="button" className="btn-secondary"
                        onClick={() => setPhase('choosing')}>Back</button>
              </div>
              <p className="fine">
                This creates an order held in your name. It does not pay for it,
                and nothing is charged.
              </p>
            </div>
          )}

          {/* ── held, awaiting payment ─────────────────────────── */}
          {phase === 'ordered' && order && (
            <div className="ordered">
              <p className="mono eyebrow">Order created</p>
              <h3 className="serif">{order.order_no}</h3>
              <ul className="srclist">
                <li><span>Fare</span><span>{money(order.payment_summary?.ticket_price ?? fare, order.currency || currency)}</span></li>
                {order.payment_summary?.baggage_total > 0 && (
                  <li><span>Baggage</span><span>{money(order.payment_summary.baggage_total, order.currency || currency)}</span></li>
                )}
                <li><span><strong>To pay</strong></span>
                    <span><strong>{money(order.total_price, order.currency || currency)}</strong></span></li>
                {order.payment_deadline && (
                  <li><span>Hold expires</span><span>{new Date(order.payment_deadline).toLocaleString()}</span></li>
                )}
              </ul>
              <p className="fine booking-truth">
                <strong>This order is real and is holding your seats.</strong> The last
                step is payment, and Waypoint does not take it. Paying is yours to
                authorise on the airline's own site, where your card details go to
                them and to nobody else — not to us, and not through an agent.
              </p>

              <div className="payoff">
                <p className="mono eyebrow">Paying, in your own hands</p>
                <ol className="paysteps">
                  <li>
                    <span>Copy your booking reference</span>
                    <button type="button" className="btn-secondary btn-copy"
                            onClick={() => {
                              navigator.clipboard?.writeText(order.order_no)
                                .then(() => setCopied(true)).catch(() => {})
                            }}>
                      {copied ? 'Copied' : `Copy ${order.order_no}`}
                    </button>
                  </li>
                  <li>
                    <span>Open {flight.airline_name || 'the airline'}'s own booking page
                          and pay {money(order.total_price, order.currency || currency)}</span>
                    {/* A guessed airline URL is exactly the kind of confident
                        wrong answer this app avoids, so this searches rather
                        than pretending to know the address. */}
                    <a className="btn-primary" target="_blank" rel="noopener noreferrer"
                       href={`https://duckduckgo.com/?q=${encodeURIComponent(
                         `${flight.airline_name || flight.airline || ''} manage my booking pay`)}`}>
                      Find the airline's payment page
                    </a>
                  </li>
                </ol>
                {deadline && (
                  <p className={`fine${overdue ? ' warn-line' : ''}`}>
                    {overdue
                      ? 'The hold has expired — the airline may have released these seats.'
                      : `Seats are held until ${deadline.toLocaleString()}. After that the fare is released.`}
                  </p>
                )}
              </div>

              <div className="sheet-actions">
                <button type="button" className="btn-secondary" onClick={onClose}>Done</button>
              </div>
            </div>
          )}

          {/* ── what really ran ────────────────────────────────── */}
          <div className="booking-steps">
            <p className="mono eyebrow">
              {checking ? 'Checking with the airline…' : 'Checked with the airline'}
            </p>
            <p className="fine booking-intro">
              Each of these ran against the airline's own system just now. You can
              close this at any point — until you pay, the fare is held, not bought.
            </p>
            <ol>
              {(steps || []).map((st) => (
                <li key={st.key} className={st.status === 'ok' ? 'is-ok' : 'is-failed'}>
                  <span className="booking-mark" aria-hidden="true">
                    {st.status === 'ok' ? '✓' : '✕'}
                  </span>
                  <div>
                    <p className="booking-label">{st.label}</p>
                    <p className="booking-detail">{st.detail}</p>
                  </div>
                </li>
              ))}
              {checking && !steps && <li className="is-pending"><span className="spinner" /> Verifying the fare…</li>}
            </ol>
          </div>
        </div>
      </section>
    </div>
  )
}
