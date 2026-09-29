// Phase placeholder — wired up now so it auto-populates when AutoResearch ships in Phase 7.
export default function AutoResearchStatus() {
  const phases = [
    { phase: 'A', label: 'Options flow signal', status: 'live' },
    { phase: 'B', label: 'Options execution', status: 'live' },
    { phase: 'C', label: 'Earnings strategies', status: 'live' },
    { phase: 'D', label: 'Portfolio hedging', status: 'live' },
  ]

  const systemPhases = [
    { label: 'Signals (FinBERT, technicals, HMM)', phase: 2, status: 'planned' },
    { label: 'Strategy (QLib, RL, debate)', phase: 3, status: 'planned' },
    { label: 'Validation (6-gate suite)', phase: 4, status: 'planned' },
    { label: 'Execution (Alpaca orders)', phase: 5, status: 'planned' },
    { label: 'AutoResearch loop', phase: 7, status: 'planned' },
  ]

  return (
    <div className="mb-6">
      <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>SYSTEM STATUS</div>
      <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs mb-2 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Options Engine</div>
            <div className="space-y-1.5">
              {phases.map((p) => (
                <div key={p.phase} className="flex items-center gap-2 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: 'var(--color-up)' }} />
                  <span style={{ color: 'var(--color-text-primary)' }}>Phase {p.phase}: {p.label}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs mb-2 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Artemis Roadmap</div>
            <div className="space-y-1.5">
              {systemPhases.map((p) => (
                <div key={p.phase} className="flex items-center gap-2 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: 'var(--color-border)' }} />
                  <span style={{ color: 'var(--color-text-secondary)' }}>Phase {p.phase}: {p.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
