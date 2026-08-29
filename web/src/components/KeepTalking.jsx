import VoiceButton from './VoiceButton'

const SUGGESTIONS = [
  'What if we left two days earlier?',
  'Anything with a pool nearby?',
  'Compare the top two',
  'Book the flight',
]

/** The conversation does not end at the first answer. */
export default function KeepTalking({ voice, onAsk, disabled, suggestions = SUGGESTIONS }) {
  return (
    <div className="keep-talking">
      <VoiceButton voice={voice} onTranscript={onAsk} disabled={disabled} compact />
      <div className="keep-talking-body">
        <p className="fine">Hold to keep talking — or try</p>
        <ul className="suggestions">
          {suggestions.map((s) => (
            <li key={s}>
              <button type="button" onClick={() => onAsk(s)} disabled={disabled}>{s}</button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
