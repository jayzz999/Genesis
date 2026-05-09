import React, { useEffect, useMemo, useState } from 'react'

const API_TOKEN = import.meta.env.VITE_GENESIS_API_TOKEN
  || (typeof window !== 'undefined' ? window.localStorage.getItem('GENESIS_API_TOKEN') : '')
  || ''

function authHeaders(headers = {}) {
  return API_TOKEN ? { ...headers, 'X-Genesis-Token': API_TOKEN } : headers
}

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: authHeaders(options.headers),
  })
  const text = await response.text()
  const data = text ? JSON.parse(text) : {}
  if (!response.ok) {
    throw new Error(data.detail || data.error || response.statusText)
  }
  return data
}

const DEFAULT_OBJECTIVE = 'Improve Genesis safely by only promoting self-changes that clear strict evidence gates.'
const DEFAULT_CONTEXT = `{
  "workflow": "self_improvement",
  "policy": "No autonomous deployment. Promotion only means approved for experiment.",
  "source": "operator-request"
}`
const DEFAULT_EVIDENCE = `{
  "benchmark_delta": 0.04,
  "regression_risk": 0.12,
  "confidence": 0.78,
  "checks": {
    "unit": true,
    "build": true,
    "browser": true
  },
  "tests": [
    "Contract test passes",
    "Frontend production build passes",
    "Browser flow renders the promotion gates"
  ]
}`

function StatusPill({ value }) {
  const ok = ['promotable', 'approved_for_experiment', 'complete'].includes(value)
  const bad = ['blocked', 'error'].includes(value)
  return (
    <span className={`rounded border px-2 py-0.5 text-[10px] ${
      ok
        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
        : bad
          ? 'border-red-500/30 bg-red-500/10 text-red-300'
          : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300'
    }`}>
      {value || 'pending'}
    </span>
  )
}

function GateCard({ gate }) {
  return (
    <article className={`rounded-lg border p-3 ${
      gate.passed
        ? 'border-emerald-500/30 bg-emerald-500/10'
        : 'border-red-500/30 bg-red-500/10'
    }`}>
      <div className="mb-1 flex items-center justify-between gap-2">
        <div className="text-xs font-medium text-forge-text">{gate.label}</div>
        <span className={`text-[10px] ${gate.passed ? 'text-emerald-300' : 'text-red-300'}`}>
          {gate.passed ? 'pass' : 'block'}
        </span>
      </div>
      <p className="text-[10px] leading-relaxed text-forge-muted">{gate.detail}</p>
    </article>
  )
}

function CandidateBlock({ candidate }) {
  if (!candidate) {
    return (
      <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
        Run a cycle to generate a candidate.
      </div>
    )
  }
  return (
    <article className="rounded-lg border border-forge-border bg-forge-panel/50 p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h4 className="text-base font-medium text-forge-text">{candidate.title}</h4>
          <div className="text-[10px] text-forge-muted">confidence {Math.round((candidate.confidence || 0) * 100)}%</div>
        </div>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-widest text-forge-muted">Problem</div>
          <p className="text-xs leading-relaxed text-forge-text">{candidate.problem}</p>
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-widest text-forge-muted">Hypothesis</div>
          <p className="text-xs leading-relaxed text-forge-text">{candidate.hypothesis}</p>
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-widest text-forge-muted">Change</div>
          <p className="text-xs leading-relaxed text-forge-text">{candidate.change_summary}</p>
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-widest text-forge-muted">Rollback</div>
          <p className="text-xs leading-relaxed text-forge-text">{candidate.rollback_plan}</p>
        </div>
      </div>
    </article>
  )
}

function RunHistory({ runs, activeId, onSelect }) {
  return (
    <div className="space-y-2">
      {runs.length ? runs.map(run => (
        <button
          key={run.id}
          onClick={() => onSelect(run)}
          className={`w-full rounded-lg border p-3 text-left transition-colors ${
            activeId === run.id
              ? 'border-purple-400/60 bg-purple-500/15'
              : 'border-forge-border bg-forge-panel/40 hover:bg-forge-border/30'
          }`}
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-mono text-[10px] text-forge-muted">{run.id}</span>
            <StatusPill value={run.evaluation?.verdict || run.status} />
          </div>
          <div className="line-clamp-2 text-xs text-forge-text">{run.candidate?.title || run.objective}</div>
          {run.promotion?.reason && (
            <div className="mt-2 line-clamp-2 text-[10px] text-forge-muted">{run.promotion.reason}</div>
          )}
        </button>
      )) : (
        <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
          No self-improvement runs yet.
        </div>
      )}
    </div>
  )
}

export default function SelfImprovementPanel({ eventLog }) {
  const [objective, setObjective] = useState(DEFAULT_OBJECTIVE)
  const [contextJson, setContextJson] = useState(DEFAULT_CONTEXT)
  const [evidenceJson, setEvidenceJson] = useState(DEFAULT_EVIDENCE)
  const [runs, setRuns] = useState([])
  const [activeRun, setActiveRun] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const statusText = useMemo(() => {
    if (running) return 'Evaluating...'
    if (latestEvent?.type?.startsWith('self_improvement.')) {
      return latestEvent.type.replace('self_improvement.', '')
    }
    return activeRun?.promotion?.state || activeRun?.status || 'ready'
  }, [activeRun, latestEvent, running])

  const loadRuns = async () => {
    try {
      const data = await apiRequest('/api/genesis/self-improvement/runs?limit=20')
      setRuns(data.runs || [])
      setError(null)
      if (!activeRun && data.runs?.[0]) setActiveRun(data.runs[0])
    } catch (e) {
      setError(e.message || 'Failed to load self-improvement runs')
    }
  }

  useEffect(() => {
    loadRuns()
    const t = setInterval(loadRuns, 6000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (latestEvent?.type?.startsWith('self_improvement.')) {
      loadRuns()
    }
  }, [latestEvent])

  const runCycle = async () => {
    let context
    let evidence
    try {
      context = JSON.parse(contextJson || '{}')
      evidence = JSON.parse(evidenceJson || '{}')
    } catch (e) {
      setError(`JSON error: ${e.message}`)
      return
    }
    setRunning(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/self-improvement/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ objective, context, evidence }),
      })
      setActiveRun(data.run)
      await loadRuns()
    } catch (e) {
      setError(e.message || 'Self-improvement run failed')
    } finally {
      setRunning(false)
    }
  }

  const evaluation = activeRun?.evaluation

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Self-Improvement Gates</h3>
          <p className="text-[10px] text-forge-muted">
            Candidate improvements are blocked unless every required evidence, safety, verification, and rollback gate passes.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">status</div>
          <div className="text-sm font-mono text-forge-text">{statusText}</div>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <section className="grid gap-4 xl:grid-cols-[380px_1fr]">
        <div className="space-y-4">
          <div className="rounded-xl border border-forge-border p-4">
            <label className="block text-xs text-forge-muted">Improvement objective</label>
            <textarea
              value={objective}
              onChange={e => setObjective(e.target.value)}
              rows={4}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <label className="mt-3 block text-xs text-forge-muted">Context JSON</label>
            <textarea
              value={contextJson}
              onChange={e => setContextJson(e.target.value)}
              rows={6}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 font-mono text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <label className="mt-3 block text-xs text-forge-muted">Evidence JSON</label>
            <textarea
              value={evidenceJson}
              onChange={e => setEvidenceJson(e.target.value)}
              rows={11}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 font-mono text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <button
              onClick={runCycle}
              disabled={running || !objective.trim()}
              className="mt-3 w-full rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-3 py-2 text-sm text-emerald-100 hover:bg-emerald-500/30 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {running ? 'Evaluating gates...' : 'Run strict evaluation gates'}
            </button>
          </div>

          <div className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs font-medium text-forge-text">Run history</div>
              <div className="font-mono text-[10px] text-forge-muted">{runs.length}</div>
            </div>
            <RunHistory runs={runs} activeId={activeRun?.id} onSelect={setActiveRun} />
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[10px] text-forge-muted">{activeRun?.id || 'no run selected'}</div>
                <h4 className="text-base font-medium text-forge-text">Promotion verdict</h4>
              </div>
              <StatusPill value={evaluation?.verdict || activeRun?.status} />
            </div>
            {activeRun?.promotion ? (
              <div className={`rounded-lg border p-3 ${
                activeRun.promotion.allowed
                  ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
                  : 'border-red-500/30 bg-red-500/10 text-red-100'
              }`}>
                <div className="text-sm font-medium">{activeRun.promotion.state}</div>
                <p className="mt-1 text-xs leading-relaxed">{activeRun.promotion.reason}</p>
                <p className="mt-2 text-[10px] text-forge-muted">
                  Human review required: {activeRun.promotion.requires_human_review ? 'yes' : 'no'}
                </p>
              </div>
            ) : (
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                No promotion verdict yet.
              </div>
            )}
          </section>

          <CandidateBlock candidate={activeRun?.candidate} />

          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs font-medium text-forge-text">Strict gates</div>
              <div className="font-mono text-[10px] text-forge-muted">
                score {Math.round((evaluation?.score || 0) * 100)}%
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {(evaluation?.gates || []).map(gate => (
                <GateCard key={gate.id} gate={gate} />
              ))}
            </div>
            {!evaluation?.gates?.length && (
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                Gate results will appear after evaluation.
              </div>
            )}
          </section>
        </div>
      </section>
    </div>
  )
}
