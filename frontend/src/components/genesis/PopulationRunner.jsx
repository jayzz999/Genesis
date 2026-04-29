import React, { useState, useEffect, useRef } from 'react'

const API = (path) => path

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

// ── Start form ───────────────────────────────────────────────────────
function StartForm({ onStart }) {
  const [task, setTask] = useState('Analyze the state of an open-source repository and suggest the most impactful contribution.')
  const [nOrganisms, setNOrganisms] = useState(4)
  const [maxGenerations, setMaxGenerations] = useState(3)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await fetch(API('/api/genesis/population/start'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task,
          perception: { type: 'task', description: task },
          n_organisms: nOrganisms,
          max_generations: maxGenerations,
        }),
      })
      const data = await res.json()
      onStart(data.run)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
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
        {loading ? 'Starting…' : '🧬 Start Evolution'}
      </button>
    </form>
  )
}

// ── Run detail view ──────────────────────────────────────────────────
function RunDetail({ runId, onBack, eventLog }) {
  const [run, setRun] = useState(null)
  const pollRef = useRef(null)

  const fetchRun = async () => {
    try {
      const res = await fetch(API(`/api/genesis/population/${runId}`))
      const data = await res.json()
      setRun(data)
    } catch { /* ignore */ }
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
    await fetch(API(`/api/genesis/population/${runId}/stop`), { method: 'POST' })
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
      <div className="rounded-xl border border-forge-border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium truncate max-w-[240px]" title={run.task}>
            {run.task}
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

  const fetchRuns = async () => {
    try {
      const res = await fetch(API('/api/genesis/population'))
      const data = await res.json()
      setRuns(data.runs || [])
    } catch { /* ignore */ }
  }

  useEffect(() => {
    fetchRuns()
    const t = setInterval(fetchRuns, 4000)
    return () => clearInterval(t)
  }, [])

  const handleDelete = async (e, runId) => {
    e.stopPropagation()
    await fetch(API(`/api/genesis/population/${runId}`), { method: 'DELETE' })
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
        <h3 className="text-sm font-medium text-forge-text">Evolution Runs</h3>
        <button
          onClick={onNew}
          className="text-xs px-3 py-1.5 rounded-lg bg-gradient-to-r from-fuchsia-500/20 to-indigo-500/20 hover:from-fuchsia-500/40 hover:to-indigo-500/40 border border-purple-500/40 text-purple-200"
        >
          + New Run
        </button>
      </div>

      {runs.length === 0 && (
        <div className="text-center text-forge-muted text-sm py-12">
          <div className="text-3xl mb-3">🧬</div>
          <div>No evolution runs yet.</div>
          <div className="text-xs mt-1">Start one to watch organisms evolve.</div>
        </div>
      )}

      {runs.map(run => (
        <button
          key={run.id}
          onClick={() => onSelect(run.id)}
          className="w-full text-left p-3 rounded-xl border border-forge-border hover:border-purple-500/40 hover:bg-white/5 transition-all"
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
          <div className="mt-2">
            <FitnessBar
              value={run.max_generations > 0 ? (run.current_generation / run.max_generations) : 0}
              size="sm"
            />
          </div>
        </button>
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
            <h3 className="text-sm font-medium mb-1">New Evolution Run</h3>
            <p className="text-xs text-forge-muted mb-4">
              All organisms share the same goal. They are scored by the meta-cognitive critic
              after each generation. Top performers breed the next generation.
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
