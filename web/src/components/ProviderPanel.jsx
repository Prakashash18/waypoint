/** Standing capability list, so the UI is honest before anything is asked. */
export default function ProviderPanel({ providers }) {
  if (!providers) return <p className="muted">loading…</p>
  return (
    <>
      <ul className="srclist">
        {providers.sources.map((s) => (
          <li key={s.id}>
            <span>
              {s.label}
              <span className="muted small block">{s.provides}</span>
            </span>
            <span className={`badge ${s.configured ? 'ok' : 'warn'}`}>
              {s.configured ? 'ready' : 'not set'}
            </span>
          </li>
        ))}
      </ul>
    </>
  )
}
