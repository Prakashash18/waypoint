import { useEffect, useRef } from 'react'
import Answer from './Answer'
import { Mic } from './Icons'
import ReplyCards from './ReplyCards'
import { NEEDS } from './NeedsBar'

const NEED_LABELS = Object.fromEntries(NEEDS.map((n) => [n.id, n.label]))

/** The conversation, kept visible.
 *
 *  Replies used to land inside a collapsed disclosure, so asking a follow-up
 *  looked like nothing happened. Every exchange now stays on the page.
 */
export default function ChatThread({ messages, busy, onAsk, onOpenStay, onBookFlight, suggestions = [] }) {
  const endRef = useRef(null)

  // Follow the conversation only when the reader is already at the bottom.
  // Scrolling someone who has deliberately gone back up is worse than making
  // them scroll down themselves.
  useEffect(() => {
    const nearBottom =
      window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 220
    if (nearBottom) endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages.length, busy])

  if (!messages.length) return null

  return (
    <section className="thread" aria-label="Conversation">
      {messages.map((m, i) => (
        <div key={i} className={`turn is-${m.role}`}>
          {m.role === 'user' ? (
            <div className="turn-said">
              <p>{m.text}</p>
              {m.needs?.length > 0 && (
                <ul className="turn-needs" aria-label="Filtered for">
                  {m.needs.map((n) => <li key={n}>{NEED_LABELS[n] || n}</li>)}
                </ul>
              )}
            </div>
          ) : (
            <div className="turn-reply">
              <Answer text={m.text} busy={false} />
              <ReplyCards cards={m.cards} onOpen={onOpenStay} onBookFlight={onBookFlight} />
              {m.lookups > 0 && (
                <p className="turn-meta">{m.lookups} lookup{m.lookups > 1 ? 's' : ''}</p>
              )}
            </div>
          )}
        </div>
      ))}

      {busy && (
        <div className="turn is-assistant">
          <p className="turn-meta"><span className="spinner" /> thinking…</p>
        </div>
      )}

      {!busy && suggestions.length > 0 && (
        <ul className="turn-suggestions">
          {suggestions.map((q) => (
            <li key={q}>
              <button type="button" onClick={() => onAsk(q)}>
                <Mic size={13} /> {q}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div ref={endRef} />
    </section>
  )
}
