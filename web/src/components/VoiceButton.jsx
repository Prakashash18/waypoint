import { Mic } from './Icons'

/** Push-to-talk. Hold to speak, release to send. */
export default function VoiceButton({ voice, onTranscript, disabled, compact = false, big = false }) {
  const { recording, thinking, level, start, stopAndTranscribe } = voice

  async function begin(e) {
    e.preventDefault()
    if (disabled || thinking) return
    await start()
  }

  async function end(e) {
    e.preventDefault()
    if (!recording) return
    const text = await stopAndTranscribe()
    if (text) onTranscript(text)
  }

  const label = thinking ? 'Transcribing…'
    : recording ? 'Listening — release to send'
    : 'Hold to speak'

  const button = (
    <button
      type="button"
      className={`mic${big ? ' is-big' : ''}${compact ? ' is-compact' : ''}` +
                 `${recording ? ' is-recording' : ''}${thinking ? ' is-thinking' : ''}`}
      onPointerDown={begin}
      onPointerUp={end}
      onPointerLeave={end}
      onPointerCancel={end}
      disabled={disabled}
      aria-label={label}
      title={label}
      style={{ '--level': recording ? level : 0 }}
    >
      <span className="mic-ring" aria-hidden="true" />
      <span className="mic-ring is-outer" aria-hidden="true" />
      <span className="mic-face">{thinking ? <span className="spinner" /> : <Mic size={big ? 38 : 20} />}</span>
      {!compact && !big && <span className="mic-label">{label}</span>}
    </button>
  )

  return big ? (
    <span className="mic-stack">
      {button}
      <span className="mic-caption">{label}</span>
    </span>
  ) : button
}
