/** Push-to-talk control. Hold to speak, release to send. */
export default function VoiceButton({ voice, onTranscript, disabled }) {
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

  const label = thinking ? 'Transcribing' : recording ? 'Listening — release to send' : 'Hold to speak'

  return (
    <button
      type="button"
      className={`mic ${recording ? 'is-recording' : ''} ${thinking ? 'is-thinking' : ''}`}
      // Pointer events cover mouse, touch and pen with one path.
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
      {thinking ? <Spinner /> : <MicIcon />}
      <span className="mic-label">{label}</span>
    </button>
  )
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v4" />
    </svg>
  )
}

function Spinner() {
  return <span className="spinner" aria-hidden="true" />
}
