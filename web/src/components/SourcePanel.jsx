/** Which providers answered this run, and what could not be found out. */
export default function SourcePanel({ sources }) {
  const used = sources?.sources || []
  const missing = sources?.missing || []
  const attributions = sources?.attributions || []

  if (!used.length && !missing.length) return <p className="muted">—</p>

  return (
    <>
      <ul className="srclist">
        {used.map((s, i) => (
          <li key={i}>
            <span>{s.label}</span>
            <span className={`badge ${s.status === 'live' ? 'ok' : s.status === 'cached' ? 'info' : 'warn'}`}>
              {s.status}
            </span>
          </li>
        ))}
      </ul>
      {missing.length > 0 && (
        <ul className="missing">
          {missing.map((m, i) => <li key={i}>{m}</li>)}
        </ul>
      )}
      {attributions.length > 0 && (
        <p className="attribution">{attributions.join(' · ')}</p>
      )}
    </>
  )
}
