/** Renders the agent's written answer.
 *
 *  The text is model-authored, so everything is escaped by React and only a
 *  small, known subset is turned into markup: images the tools captured,
 *  bold, and headings.
 */
export default function Answer({ text, busy }) {
  if (busy) return <p className="muted"><span className="spinner" /> Calling real providers…</p>
  if (!text) return <p className="muted">Ask for a trip to begin.</p>

  return <div className="answer">{text.split('\n').map(renderLine)}</div>
}

const IMAGE = /^!\[([^\]]*)\]\(([^)\s]+)\)$/
const SAFE_SRC = /^(https:\/\/|\/static\/)/

function renderLine(line, i) {
  const trimmed = line.trim()
  if (!trimmed) return <div key={i} className="gap" />

  const image = trimmed.match(IMAGE)
  if (image) {
    const [, alt, src] = image
    if (!SAFE_SRC.test(src)) return null
    return <img key={i} className="answer-img" src={src} alt={alt} loading="lazy" />
  }

  const heading = trimmed.match(/^#{1,4}\s+(.*)$/)
  if (heading) return <h4 key={i} className="answer-h">{heading[1]}</h4>

  return <p key={i} className="answer-p">{inline(trimmed)}</p>
}

/** Turns **bold** into elements; everything else stays plain text. */
function inline(text) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : part
  )
}
