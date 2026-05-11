import React, { useState, useEffect, useRef } from 'react'

const API = (path) => path
const API_TOKEN = import.meta.env.VITE_GENESIS_API_TOKEN
  || (typeof window !== 'undefined' ? window.localStorage.getItem('GENESIS_API_TOKEN') : '')
  || ''

function authHeaders(headers = {}) {
  return API_TOKEN ? { ...headers, 'X-Genesis-Token': API_TOKEN } : headers
}

async function apiRequest(path, options = {}) {
  const response = await fetch(API(path), {
    ...options,
    headers: authHeaders(options.headers),
  })
  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { detail: text }
    }
  }
  if (!response.ok) {
    const detail = data?.detail || data?.error || response.statusText || 'Request failed'
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data || {}
}

// ── Fitness bar ──────────────────────────────────────────────────────
function FitnessBar({ value, size = 'md' }) {
  const pct = Math.round((value || 0) * 100)
  const color = pct >= 70 ? 'bg-emerald-500' : pct >= 40 ? 'bg-amber-500' : 'bg-red-500'
  const h = size === 'sm' ? 'h-1.5' : 'h-2'
  return (
    <div className={`w-full bg-forge-border rounded-full ${h} overflow-hidden`}>
      <div
        className={`${h} rounded-full transition-all duration-700 ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

// ── Score badge ──────────────────────────────────────────────────────
function FitnessBadge({ value }) {
  const pct = Math.round((value || 0) * 100)
  const cls = pct >= 70
    ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
    : pct >= 40
      ? 'text-amber-400 bg-amber-500/10 border-amber-500/30'
      : 'text-red-400 bg-red-500/10 border-red-500/30'
  return (
    <span className={`text-xs font-mono px-2 py-0.5 rounded-full border ${cls}`}>
      {pct}%
    </span>
  )
}

// ── Organism card inside a generation ───────────────────────────────
function OrganismCard({ score, rank, survived }) {
  const alignment = score.benchmark_alignment
  const alignmentPct = alignment ? Math.round(alignment.score * 100) : null
  return (
    <div className={`p-3 rounded-lg border transition-all ${
      survived
        ? 'border-emerald-500/40 bg-emerald-500/5'
        : 'border-forge-border/50 bg-forge-panel/50 opacity-60'
    }`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-forge-muted font-mono">#{rank}</span>
          <span className="text-xs text-forge-text truncate max-w-[100px]" title={score.name}>
            {score.name}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {survived
            ? <span className="text-[10px] text-emerald-400">✓ survived</span>
            : <span className="text-[10px] text-red-400/60">✗ culled</span>}
          <FitnessBadge value={score.fitness} />
        </div>
      </div>
      <FitnessBar value={score.fitness} />
      <div className="flex gap-3 mt-1.5 text-[10px] text-forge-muted">
        <span>quality {Math.round(score.reasoning_quality_avg * 100)}%</span>
        <span>efficiency {Math.round(score.action_efficiency_avg * 100)}%</span>
        <span>{score.decision_count} decisions</span>
      </div>
      {alignment && (
        <div className="mt-2 rounded-lg border border-forge-border/80 bg-forge-bg/50 p-2">
          <div className="mb-1 flex items-center justify-between text-[10px]">
            <span className="uppercase tracking-widest text-forge-muted">benchmark alignment</span>
            <span className={alignmentPct >= 70 ? 'text-emerald-300' : alignmentPct >= 40 ? 'text-amber-300' : 'text-red-300'}>
              {alignmentPct}%
            </span>
          </div>
          <div className="grid gap-1">
            {(alignment.criteria || []).map(item => (
              <div key={item.id} className="flex items-center justify-between gap-2 text-[10px]">
                <span className="truncate text-forge-muted" title={item.label}>{item.label}</span>
                <span className={item.score > 0 ? 'text-emerald-300' : 'text-red-300/80'}>
                  {item.score > 0 ? 'hit' : 'miss'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Generation block ─────────────────────────────────────────────────
function GenerationBlock({ gen, isLatest }) {
  const [open, setOpen] = useState(isLatest)
  const survivorSet = new Set(gen.survivor_ids || [])

  return (
    <div className={`rounded-xl border ${isLatest ? 'border-purple-500/40' : 'border-forge-border'}`}>
      {/* Header */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-white/5 transition-colors rounded-xl"
      >
        <div className="flex items-center gap-3">
          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
            isLatest ? 'bg-purple-500/20 text-purple-300' : 'bg-forge-border text-forge-muted'
          }`}>
            {gen.generation}
          </div>
          <span className="text-sm font-medium">Generation {gen.generation}</span>
          {gen.skills_distilled?.length > 0 && (
            <span className="text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full">
              🧬 {gen.skills_distilled.length} skill{gen.skills_distilled.length > 1 ? 's' : ''} distilled
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-xs text-forge-muted">best fitness</div>
            <div className="text-sm font-mono text-forge-text">{Math.round(gen.best_fitness * 100)}%</div>
          </div>
          <div className="text-right">
            <div className="text-xs text-forge-muted">mean</div>
            <div className="text-sm font-mono text-forge-text">{Math.round(gen.mean_fitness * 100)}%</div>
          </div>
          <span className="text-forge-muted text-sm">{open ? '▲' : '▼'}</span>
        </div>
      </button>

      {/* Organism grid */}
      {open && (
        <div className="px-4 pb-4 grid grid-cols-2 gap-2">
          {(gen.scores || []).map((score, i) => (
            <OrganismCard
              key={score.organism_id}
              score={score}
              rank={i + 1}
              survived={survivorSet.has(score.organism_id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Fitness sparkline ────────────────────────────────────────────────
function FitnessChart({ generations }) {
  if (!generations?.length) return null
  const points = generations.map(g => ({
    gen: g.generation,
    best: g.best_fitness,
    mean: g.mean_fitness,
  }))

  const W = 300, H = 80, PAD = 10
  const maxY = 1
  const xScale = (i) => PAD + (i / Math.max(points.length - 1, 1)) * (W - PAD * 2)
  const yScale = (v) => H - PAD - (v / maxY) * (H - PAD * 2)

  const pathFor = (key) =>
    points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yScale(p[key])}`).join(' ')

  return (
    <div>
      <div className="text-xs text-forge-muted mb-2">Fitness over generations</div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 80 }}>
        {/* Grid lines */}
        {[0.25, 0.5, 0.75, 1].map(v => (
          <line key={v} x1={PAD} x2={W - PAD} y1={yScale(v)} y2={yScale(v)}
            stroke="#1a1a2e" strokeWidth="1" />
        ))}
        {/* Mean line */}
        <path d={pathFor('mean')} fill="none" stroke="#6366f1" strokeWidth="1.5"
          strokeDasharray="4 2" opacity="0.6" />
        {/* Best line */}
        <path d={pathFor('best')} fill="none" stroke="#22c55e" strokeWidth="2" />
        {/* Dots for best */}
        {points.map((p, i) => (
          <circle key={i} cx={xScale(i)} cy={yScale(p.best)} r="3"
            fill="#22c55e" stroke="#06060b" strokeWidth="1.5" />
        ))}
        {/* X labels */}
        {points.map((p, i) => (
          <text key={i} x={xScale(i)} y={H - 1} textAnchor="middle"
            fill="#64748b" fontSize="8">
            G{p.gen}
          </text>
        ))}
      </svg>
      <div className="flex gap-4 mt-1 text-[10px] text-forge-muted">
        <span><span className="text-emerald-400">—</span> best</span>
        <span><span className="text-indigo-400">- -</span> mean</span>
      </div>
    </div>
  )
}

// ── Evidence report ─────────────────────────────────────────────────
function EvidenceReport({ report }) {
  if (!report) return null

  const bestDelta = Math.round((report.fitness?.best_delta || 0) * 100)
  const meanDelta = Math.round((report.fitness?.mean_delta || 0) * 100)
  const verdictStyle = {
    improved: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30',
    skills_distilled: 'text-amber-300 bg-amber-500/10 border-amber-500/30',
    regressed: 'text-red-300 bg-red-500/10 border-red-500/30',
    inconclusive: 'text-forge-muted bg-forge-border/40 border-forge-border',
    not_started: 'text-indigo-300 bg-indigo-500/10 border-indigo-500/30',
  }[report.verdict] || 'text-forge-muted bg-forge-border/40 border-forge-border'
  const regression = report.regression
  const regressionDelta = regression?.delta_vs_previous_best == null
    ? null
    : Math.round(regression.delta_vs_previous_best * 100)

  const exportReport = () => {
    const text = [
      `Genesis Benchmark Arena Report`,
      ``,
      `Task: ${report.task}`,
      `Verdict: ${report.verdict}`,
      `Summary: ${report.summary}`,
      ``,
      `Generations run: ${report.generations_run}`,
      `Best fitness: ${Math.round(report.fitness.first_best * 100)}% -> ${Math.round(report.fitness.last_best * 100)}% (${bestDelta >= 0 ? '+' : ''}${bestDelta} pts)`,
      `Mean fitness: ${Math.round(report.fitness.first_mean * 100)}% -> ${Math.round(report.fitness.last_mean * 100)}% (${meanDelta >= 0 ? '+' : ''}${meanDelta} pts)`,
      `Skills distilled: ${report.skills.total_distilled}`,
      regression ? `Benchmark: ${regression.benchmark_name || regression.benchmark_id}` : null,
      regression && regression.previous_best_fitness != null
        ? `Previous best: ${Math.round(regression.previous_best_fitness * 100)}% (${regressionDelta >= 0 ? '+' : ''}${regressionDelta} pts)`
        : null,
      report.best_organism ? `Best organism: ${report.best_organism.name} (${Math.round(report.best_organism.fitness * 100)}%)` : `Best organism: none yet`,
      ``,
      report.claim,
    ].filter(Boolean).join('\n')
    navigator.clipboard?.writeText(text)
  }

  return (
    <div className="rounded-xl border border-forge-border p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-forge-muted">Evidence of Learning</div>
          <div className="text-sm text-forge-text mt-1">{report.summary}</div>
        </div>
        <span className={`text-xs px-2 py-1 rounded-full border ${verdictStyle}`}>
          {report.verdict.replace('_', ' ')}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="bg-forge-panel rounded-lg p-2">
          <div className="text-xs text-forge-muted">best delta</div>
          <div className={`text-lg font-bold ${bestDelta > 0 ? 'text-emerald-400' : bestDelta < 0 ? 'text-red-400' : 'text-forge-text'}`}>
            {bestDelta >= 0 ? '+' : ''}{bestDelta}
          </div>
        </div>
        <div className="bg-forge-panel rounded-lg p-2">
          <div className="text-xs text-forge-muted">mean delta</div>
          <div className={`text-lg font-bold ${meanDelta > 0 ? 'text-emerald-400' : meanDelta < 0 ? 'text-red-400' : 'text-forge-text'}`}>
            {meanDelta >= 0 ? '+' : ''}{meanDelta}
          </div>
        </div>
        <div className="bg-forge-panel rounded-lg p-2">
          <div className="text-xs text-forge-muted">skills</div>
          <div className="text-lg font-bold text-amber-400">{report.skills.total_distilled}</div>
        </div>
      </div>

      {report.best_organism && (
        <div className="text-xs text-forge-muted">
          Best organism: <span className="text-forge-text">{report.best_organism.name}</span>
          {' '}at <span className="text-emerald-300">{Math.round(report.best_organism.fitness * 100)}%</span> fitness.
        </div>
      )}

      {regression && (
        <div className="rounded-lg border border-forge-border bg-forge-panel/60 p-3 text-xs">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-forge-muted">benchmark</div>
              <div className="text-forge-text">{regression.benchmark_name || regression.benchmark_id}</div>
            </div>
            <div className="text-right">
              <div className="text-forge-muted">previous runs</div>
              <div className="text-forge-text font-mono">{regression.previous_completed_runs}</div>
            </div>
            <div className="text-right">
              <div className="text-forge-muted">vs previous best</div>
              <div className={`font-mono ${
                regressionDelta == null
                  ? 'text-forge-muted'
                  : regressionDelta >= 0
                    ? 'text-emerald-300'
                    : 'text-red-300'
              }`}>
                {regressionDelta == null ? 'baseline' : `${regressionDelta >= 0 ? '+' : ''}${regressionDelta} pts`}
              </div>
            </div>
          </div>
        </div>
      )}

      <button
        onClick={exportReport}
        className="w-full text-xs px-3 py-1.5 rounded-lg bg-forge-border/40 hover:bg-forge-border border border-forge-border text-forge-text"
      >
        Copy report
      </button>
    </div>
  )
}

// ── Start form ───────────────────────────────────────────────────────
function StartForm({ onStart }) {
  const [benchmarks, setBenchmarks] = useState([])
  const [benchmarkId, setBenchmarkId] = useState('repo_triage')
  const [task, setTask] = useState('Analyze the state of an open-source repository and suggest the most impactful contribution.')
  const [nOrganisms, setNOrganisms] = useState(4)
  const [maxGenerations, setMaxGenerations] = useState(3)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    apiRequest('/api/genesis/population/benchmarks')
      .then(data => {
        if (!active) return
        const next = data.benchmarks || []
        setBenchmarks(next)
        const selected = next.find(b => b.benchmark?.id === benchmarkId)
        if (selected?.benchmark?.task) setTask(selected.benchmark.task)
      })
      .catch(() => {})
    return () => { active = false }
  }, [])

  const handleBenchmarkChange = (id) => {
    setBenchmarkId(id)
    const selected = benchmarks.find(b => b.benchmark?.id === id)
    if (selected?.benchmark?.task) setTask(selected.benchmark.task)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/population/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task,
          perception: benchmarkId ? {} : { type: 'task', description: task },
          benchmark_id: benchmarkId || null,
          n_organisms: nOrganisms,
          max_generations: maxGenerations,
        }),
      })
      onStart(data.run)
    } catch (e) {
      setError(e.message || 'Failed to start evolution')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-xs text-forge-muted mb-1">Benchmark arena task</label>
        <select
          value={benchmarkId}
          onChange={e => handleBenchmarkChange(e.target.value)}
          className="w-full bg-forge-panel border border-forge-border rounded-lg px-3 py-2 text-sm text-forge-text focus:outline-none focus:border-purple-500/60"
        >
          <option value="">Custom task</option>
          {benchmarks.map(item => (
            <option key={item.benchmark.id} value={item.benchmark.id}>
              {item.benchmark.name}
              {item.completed_runs ? ` · ${item.completed_runs} prior` : ''}
            </option>
          ))}
          </select>
        {benchmarkId && (
          <div className="mt-2 grid grid-cols-3 gap-2 text-center">
            {(() => {
              const selected = benchmarks.find(b => b.benchmark?.id === benchmarkId)
              return [
                ['prior runs', selected?.completed_runs ?? 0],
                ['best', selected?.best_fitness == null ? '—' : `${Math.round(selected.best_fitness * 100)}%`],
                ['latest', selected?.latest_best_fitness == null ? '—' : `${Math.round(selected.latest_best_fitness * 100)}%`],
              ].map(([label, value]) => (
                <div key={label} className="bg-forge-panel/70 border border-forge-border rounded-lg py-2">
                  <div className="text-[10px] text-forge-muted">{label}</div>
                  <div className="text-xs font-mono text-forge-text">{value}</div>
                </div>
              ))
            })()}
          </div>
        )}
        {benchmarkId && (() => {
          const selected = benchmarks.find(b => b.benchmark?.id === benchmarkId)
          const rubric = selected?.benchmark?.rubric || []
          return rubric.length ? (
            <div className="mt-2 rounded-lg border border-forge-border bg-forge-panel/50 p-3">
              <div className="mb-2 text-[10px] uppercase tracking-widest text-forge-muted">Rubric</div>
              <div className="space-y-1">
                {rubric.map(item => (
                  <div key={item.id} className="text-xs text-forge-text">
                    {item.label}
                    <span className="ml-2 text-[10px] text-forge-muted">
                      {item.signals.slice(0, 3).join(', ')}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : null
        })()}
      </div>
      <div>
        <label className="block text-xs text-forge-muted mb-1">Task (shared goal for all organisms)</label>
        <textarea
          value={task}
          onChange={e => setTask(e.target.value)}
          rows={3}
          className="w-full bg-forge-panel border border-forge-border rounded-lg px-3 py-2 text-sm text-forge-text resize-none focus:outline-none focus:border-purple-500/60"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-forge-muted mb-1">Population size</label>
          <input
            type="number" min={2} max={12} value={nOrganisms}
            onChange={e => setNOrganisms(+e.target.value)}
            className="w-full bg-forge-panel border border-forge-border rounded-lg px-3 py-2 text-sm text-forge-text focus:outline-none focus:border-purple-500/60"
          />
        </div>
        <div>
          <label className="block text-xs text-forge-muted mb-1">Generations</label>
          <input
            type="number" min={1} max={10} value={maxGenerations}
            onChange={e => setMaxGenerations(+e.target.value)}
            className="w-full bg-forge-panel border border-forge-border rounded-lg px-3 py-2 text-sm text-forge-text focus:outline-none focus:border-purple-500/60"
          />
        </div>
      </div>
      <button
        type="submit" disabled={loading || !task.trim()}
        className="w-full py-2 rounded-lg bg-gradient-to-r from-fuchsia-500/20 to-indigo-500/20 hover:from-fuchsia-500/40 hover:to-indigo-500/40 border border-purple-500/40 text-purple-200 text-sm disabled:opacity-40 disabled:cursor-not-allowed transition-all"
      >
        {loading ? 'Starting...' : 'Start benchmark run'}
      </button>
      {error && (
        <div className="text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded p-2">
          {error}
        </div>
      )}
    </form>
  )
}

// ── Run detail view ──────────────────────────────────────────────────
function RunDetail({ runId, onBack, eventLog }) {
  const [run, setRun] = useState(null)
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

  const fetchRun = async () => {
    try {
      setRun(await apiRequest(`/api/genesis/population/${runId}`))
      setReport(await apiRequest(`/api/genesis/population/${runId}/report`))
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load run')
    }
  }

  useEffect(() => {
    fetchRun()
    pollRef.current = setInterval(fetchRun, 3000)
    return () => clearInterval(pollRef.current)
  }, [runId])

  // Also refresh on relevant WS events
  useEffect(() => {
    const last = eventLog?.[0]
    if (last?.run_id === runId) fetchRun()
  }, [eventLog])

  const handleStop = async () => {
    try {
      await apiRequest(`/api/genesis/population/${runId}/stop`, { method: 'POST' })
    } catch (e) {
      setError(e.message || 'Failed to stop run')
    }
    fetchRun()
  }

  if (!run) return (
    <div className="flex items-center justify-center h-40 text-forge-muted text-sm">
      Loading…
    </div>
  )

  const statusColor = {
    running: 'text-amber-400',
    complete: 'text-emerald-400',
    stopped: 'text-forge-muted',
    error: 'text-red-400',
    pending: 'text-indigo-400',
  }[run.status] || 'text-forge-muted'

  const bestEver = run.generations?.length
    ? Math.max(...run.generations.map(g => g.best_fitness))
    : null

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="text-xs text-forge-muted hover:text-forge-text">
          ← All runs
        </button>
        <div className="flex items-center gap-2">
          {run.is_running && (
            <button
              onClick={handleStop}
              className="text-xs px-2 py-1 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10"
            >
              Stop
            </button>
          )}
        </div>
      </div>

      {/* Summary */}
      {error && (
        <div className="text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded p-2">
          {error}
        </div>
      )}

      {/* Summary */}
      <div className="rounded-xl border border-forge-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium truncate max-w-[240px]" title={run.task}>
            {run.benchmark_name || run.task}
          </h3>
          <span className={`text-xs font-medium ${statusColor}`}>
            {run.is_running && <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse mr-1.5 mb-0.5" />}
            {run.status}
          </span>
        </div>

        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="bg-forge-panel rounded-lg p-2">
            <div className="text-xs text-forge-muted">generation</div>
            <div className="text-lg font-bold text-forge-text">
              {run.current_generation}/{run.max_generations}
            </div>
          </div>
          <div className="bg-forge-panel rounded-lg p-2">
            <div className="text-xs text-forge-muted">population</div>
            <div className="text-lg font-bold text-forge-text">{run.n_organisms}</div>
          </div>
          <div className="bg-forge-panel rounded-lg p-2">
            <div className="text-xs text-forge-muted">best fitness</div>
            <div className="text-lg font-bold text-emerald-400">
              {bestEver != null ? `${Math.round(bestEver * 100)}%` : '—'}
            </div>
          </div>
        </div>

        {/* Generation progress bar */}
        <div>
          <div className="flex justify-between text-[10px] text-forge-muted mb-1">
            <span>Progress</span>
            <span>{run.current_generation}/{run.max_generations} generations</span>
          </div>
          <FitnessBar
            value={run.max_generations > 0 ? run.current_generation / run.max_generations : 0}
            size="sm"
          />
        </div>

        {/* Chart */}
        {run.generations?.length >= 2 && (
          <FitnessChart generations={run.generations} />
        )}
      </div>

      <EvidenceReport report={report} />

      {/* Generation blocks */}
      <div className="space-y-2">
        {[...(run.generations || [])].reverse().map((gen, i) => (
          <GenerationBlock
            key={gen.generation}
            gen={gen}
            isLatest={i === 0}
          />
        ))}
        {run.is_running && !run.generations?.length && (
          <div className="text-center text-forge-muted text-sm py-8 animate-pulse">
            Seeding generation 1…
          </div>
        )}
      </div>
    </div>
  )
}

// ── Run list ─────────────────────────────────────────────────────────
function RunList({ onSelect, onNew }) {
  const [runs, setRuns] = useState([])
  const [error, setError] = useState(null)

  const fetchRuns = async () => {
    try {
      const data = await apiRequest('/api/genesis/population')
      setRuns(data.runs || [])
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load evolution runs')
    }
  }

  useEffect(() => {
    fetchRuns()
    const t = setInterval(fetchRuns, 4000)
    return () => clearInterval(t)
  }, [])

  const handleDelete = async (e, runId) => {
    e.stopPropagation()
    try {
      await apiRequest(`/api/genesis/population/${runId}`, { method: 'DELETE' })
    } catch (err) {
      setError(err.message || 'Failed to delete run')
    }
    fetchRuns()
  }

  const statusDot = {
    running: 'bg-amber-400 animate-pulse',
    complete: 'bg-emerald-400',
    stopped: 'bg-forge-muted',
    error: 'bg-red-400',
    pending: 'bg-indigo-400 animate-pulse',
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Benchmark Arena</h3>
          <p className="text-[10px] text-forge-muted">Repeatable tasks, rubric scores, regression baselines.</p>
        </div>
        <button
          onClick={onNew}
          className="text-xs px-3 py-1.5 rounded-lg bg-gradient-to-r from-fuchsia-500/20 to-indigo-500/20 hover:from-fuchsia-500/40 hover:to-indigo-500/40 border border-purple-500/40 text-purple-200"
        >
          + New Benchmark
        </button>
      </div>

      {error && (
        <div className="text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded p-2">
          {error}
        </div>
      )}

      {runs.length === 0 && (
        <div className="text-center text-forge-muted text-sm py-12">
          <div className="text-3xl mb-3">Benchmarks</div>
          <div>No benchmark runs yet.</div>
          <div className="text-xs mt-1">Start one to measure organism learning.</div>
        </div>
      )}

      {runs.map(run => (
        <div
          key={run.id}
          onClick={() => onSelect(run.id)}
          role="button"
          tabIndex={0}
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ' ') onSelect(run.id)
          }}
          className="w-full cursor-pointer text-left p-3 rounded-xl border border-forge-border hover:border-purple-500/40 hover:bg-white/5 transition-all"
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${statusDot[run.status] || 'bg-forge-muted'}`} />
              <span className="text-xs text-forge-text font-medium">
                {run.n_organisms} organisms · {run.max_generations} generations
              </span>
            </div>
            <div className="flex items-center gap-2">
              {run.best_fitness != null && (
                <FitnessBadge value={run.best_fitness} />
              )}
              <button
                onClick={e => handleDelete(e, run.id)}
                className="text-[10px] text-forge-muted hover:text-red-400 px-1"
                title="Delete"
              >✕</button>
            </div>
          </div>
          <p className="text-xs text-forge-muted line-clamp-2">{run.task}</p>
          {run.benchmark_name && (
            <div className="mt-1 text-[10px] text-purple-300">
              benchmark · {run.benchmark_name}
            </div>
          )}
          <div className="mt-2">
            <FitnessBar
              value={run.max_generations > 0 ? (run.current_generation / run.max_generations) : 0}
              size="sm"
            />
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Root component ───────────────────────────────────────────────────
export default function PopulationRunner({ eventLog }) {
  const [view, setView] = useState('list') // 'list' | 'new' | 'detail'
  const [activeRunId, setActiveRunId] = useState(null)

  const handleStart = (run) => {
    setActiveRunId(run.id)
    setView('detail')
  }

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      {view === 'list' && (
        <RunList
          onSelect={id => { setActiveRunId(id); setView('detail') }}
          onNew={() => setView('new')}
        />
      )}

      {view === 'new' && (
        <div className="space-y-4">
          <button onClick={() => setView('list')} className="text-xs text-forge-muted hover:text-forge-text">
            ← Back
          </button>
          <div>
            <h3 className="text-sm font-medium mb-1">New Benchmark Run</h3>
            <p className="text-xs text-forge-muted mb-4">
              All organisms share the same task. They are scored by meta-cognition plus
              benchmark-specific rubric alignment. Top performers breed the next generation.
            </p>
          </div>
          <StartForm onStart={handleStart} />
        </div>
      )}

      {view === 'detail' && activeRunId && (
        <RunDetail
          runId={activeRunId}
          onBack={() => setView('list')}
          eventLog={eventLog}
        />
      )}
    </div>
  )
}
