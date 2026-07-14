import type { Recommendation, Severity } from '../lib/recommend'

const badge: Record<Severity, { icon: string; label: string }> = {
  warning: { icon: '⚠', label: 'Watch out' },
  suggestion: { icon: '✦', label: 'Improve' },
  info: { icon: 'ℹ', label: 'Note' },
}

export function Recommendations({ recs }: { recs: Recommendation[] }) {
  return (
    <div className="card">
      <h2>Trade check &amp; potential improvements</h2>
      <div className="recs">
        {recs.length === 0 ? (
          <p className="chart-note">No flags — the structure looks reasonable by these heuristics.</p>
        ) : (
          recs.map((r, i) => (
            <div className="rec" key={i}>
              <span className={`badge ${r.severity}`}>
                <span aria-hidden>{badge[r.severity].icon}</span>
                {badge[r.severity].label}
              </span>
              <div>
                <h3>{r.title}</h3>
                <p>{r.detail}</p>
              </div>
            </div>
          ))
        )}
      </div>
      <p className="chart-note">
        Heuristics based on common options-trading guidelines. Educational only — not
        financial advice.
      </p>
    </div>
  )
}
