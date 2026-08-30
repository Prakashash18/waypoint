import { useEffect, useRef } from 'react'
import Answer from './Answer'
import { Mic } from './Icons'
import ReplyCards from './ReplyCards'

/** The conversation, kept visible.
 *
 *  Replies used to land inside a collapsed disclosure, so asking a follow-up
 *  looked like nothing happened. Every exchange now stays on the page.
 */
export default function ChatThread({ messages, busy, onAsk, onOpenStay, suggestions = [] }) {
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages.length, busy])

  if (!messages.length) return null

  return (
    <section className="thread" aria-label="Conversation">
      {messages.map((m, i) => (
        <div key={i} className={`turn is-${m.role}`}>
          {m.role === 'user' ? (
            <p className="turn-said">{m.text}</p>
          ) : (
            <div className="turn-reply">
              <Answer text={m.text} busy={false} />
              <ReplyCards cards={m.cards} onOpen={onOpenStay} />
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
