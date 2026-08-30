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

const INLINE = /(\*\*[^*]+\*\*|!?\[[^\]]*\]\([^)\s]+\))/g
const LINK = /^(!?)\[([^\]]*)\]\(([^)\s]+)\)$/

/** Bold and links become elements; everything else stays plain text.
 *  A link to anywhere we do not recognise renders as its label alone rather
 *  than spilling a raw URL into the sentence. */
function inline(text) {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    const link = part.match(LINK)
    if (link) {
      const [, bang, label, href] = link
      if (bang) return null                       // inline images belong on their own line
      if (!SAFE_SRC.test(href)) return label      // label only, never the bare URL
      return (
        <a key={i} href={href} target="_blank" rel="noreferrer noopener">
          {label || href}
        </a>
      )
    }
    return part
  })
}
