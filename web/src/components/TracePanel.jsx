/** What the agent actually called, in order. */
export default function TracePanel({ trace, busy }) {
  if (busy && !trace.length) return <p className="muted">Working…</p>
  if (!trace.length) return <p className="muted">No calls yet.</p>

  return (
    <ol className="trace">
      {trace.map((step, i) => {
        const auto = (step.summary || '').startsWith('[auto]')
        const summary = (step.summary || '').replace('[auto] ', '')
        return (
          <li key={`${step.step}-${i}`} className="trace-step">
            <span className={`dot ${step.status}`} aria-hidden="true" />
            <div className="trace-body">
              {step.kind === 'tool_call' ? (
                <>
                  <code>{step.tool}.{step.capability}</code>
                  {auto && <span className="badge tiny">guaranteed</span>}
                </>
              ) : (
                <em>wrote the recommendation</em>
              )}
              {summary && <p className="muted small">{summary}</p>}
            </div>
            <span className="trace-ms">{step.duration_ms}ms</span>
          </li>
        )
      })}
    </ol>
  )
}
