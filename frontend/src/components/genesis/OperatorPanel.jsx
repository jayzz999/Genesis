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

const DEFAULT_GOAL = 'Persistently improve Genesis using only internal, reversible actions and strict evaluation gates.'
const DEFAULT_CONSTRAINTS = `Only perform internal, reversible actions.
Do not send messages, upload files, delete data, or deploy changes.
Use self-improvement gates before marking anything promotable.`

function StatusPill({ value }) {
  const active = value === 'active'
  const done = value === 'completed'
  const paused = value === 'paused'
  return (
    <span className={`rounded border px-2 py-0.5 text-[10px] ${
      active
        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
        : done
          ? 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300'
          : paused
            ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
            : 'border-red-500/30 bg-red-500/10 text-red-300'
    }`}>
      {value || 'unknown'}
    </span>
  )
}

function OperatorHistory({ operators, selectedId, onSelect }) {
  return (
    <div className="space-y-2">
      {operators.length ? operators.map(operator => (
        <button
          key={operator.id}
          onClick={() => onSelect(operator)}
          className={`w-full rounded-lg border p-3 text-left transition-colors ${
            selectedId === operator.id
              ? 'border-purple-400/60 bg-purple-500/15'
              : 'border-forge-border bg-forge-panel/40 hover:bg-forge-border/30'
          }`}
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-mono text-[10px] text-forge-muted">{operator.id}</span>
            <StatusPill value={operator.status} />
          </div>
          <div className="line-clamp-2 text-xs text-forge-text">{operator.goal}</div>
          <div className="mt-2 text-[10px] text-forge-muted">
            ticks {operator.ticks?.length || 0} · cadence {operator.cadence_s}s
          </div>
        </button>
      )) : (
        <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
          No operators yet.
        </div>
      )}
    </div>
  )
}

function TickCard({ tick }) {
  const chosen = tick.chosen_action || {}
  const result = tick.result || {}
  return (
    <article className="rounded-lg border border-forge-border bg-forge-panel/50 p-3">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <div className="font-mono text-[10px] text-forge-muted">{tick.id}</div>
          <div className="text-xs font-medium text-forge-text">{chosen.action || 'unknown action'}</div>
        </div>
        <span className={`rounded border px-2 py-0.5 text-[10px] ${
          result.ok ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-red-500/30 bg-red-500/10 text-red-300'
        }`}>
          {result.ok ? 'ok' : 'error'}
        </span>
      </div>
      <p className="mb-2 text-xs leading-relaxed text-forge-text">{chosen.rationale}</p>
      <pre className="max-h-40 overflow-auto rounded bg-forge-bg/70 p-2 text-[10px] text-forge-text">
        {JSON.stringify(result, null, 2)}
      </pre>
    </article>
  )
}

export default function OperatorPanel({ eventLog }) {
  const [name, setName] = useState('guardian_operator')
  const [goal, setGoal] = useState(DEFAULT_GOAL)
  const [constraintsText, setConstraintsText] = useState(DEFAULT_CONSTRAINTS)
  const [cadence, setCadence] = useState(60)
  const [maxTicks, setMaxTicks] = useState(5)
  const [operators, setOperators] = useState([])
  const [activeOperator, setActiveOperator] = useState(null)
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const statusText = useMemo(() => {
    if (busy) return 'working'
    if (latestEvent?.type?.startsWith('operator.')) return latestEvent.type.replace('operator.', '')
    return activeOperator?.status || 'ready'
  }, [activeOperator, busy, latestEvent])

  const loadOperators = async () => {
    try {
      const data = await apiRequest('/api/genesis/operators?limit=20')
      setOperators(data.operators || [])
      setStatus(data.status || null)
      setError(null)
      if (!activeOperator && data.operators?.[0]) setActiveOperator(data.operators[0])
    } catch (e) {
      setError(e.message || 'Failed to load operators')
    }
  }

  useEffect(() => {
    loadOperators()
    const t = setInterval(loadOperators, 5000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (latestEvent?.type?.startsWith('operator.')) {
      loadOperators()
    }
  }, [latestEvent])

  const createOperator = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/operators', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          goal,
          cadence_s: Number(cadence),
          max_ticks: Number(maxTicks),
          constraints: constraintsText.split('\n').map(s => s.trim()).filter(Boolean),
          start_active: true,
        }),
      })
      setActiveOperator(data.operator)
      await loadOperators()
    } catch (e) {
      setError(e.message || 'Failed to create operator')
    } finally {
      setBusy(false)
    }
  }

  const command = async (path) => {
    if (!activeOperator) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/operators/${activeOperator.id}/${path}`, {
        method: 'POST',
      })
      setActiveOperator(data.operator)
      await loadOperators()
    } catch (e) {
      setError(e.message || 'Operator command failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Autonomous Operator</h3>
          <p className="text-[10px] text-forge-muted">
            Persistent operator goals wake on cadence, choose bounded internal actions, and write every tick to an audit log.
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
            <label className="block text-xs text-forge-muted">Operator name</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <label className="mt-3 block text-xs text-forge-muted">Persistent goal</label>
            <textarea
              value={goal}
              onChange={e => setGoal(e.target.value)}
              rows={5}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <label className="mt-3 block text-xs text-forge-muted">Constraints</label>
            <textarea
              value={constraintsText}
              onChange={e => setConstraintsText(e.target.value)}
              rows={5}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <div className="mt-3 grid grid-cols-2 gap-3">
              <label className="block text-xs text-forge-muted">
                Cadence seconds
                <input
                  type="number"
                  min="10"
                  max="86400"
                  value={cadence}
                  onChange={e => setCadence(e.target.value)}
                  className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
                />
              </label>
              <label className="block text-xs text-forge-muted">
                Max ticks
                <input
                  type="number"
                  min="1"
                  max="1000"
                  value={maxTicks}
                  onChange={e => setMaxTicks(e.target.value)}
                  className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
                />
              </label>
            </div>

            <button
              onClick={createOperator}
              disabled={busy || !goal.trim()}
              className="mt-3 w-full rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? 'Working...' : 'Create persistent operator'}
            </button>
          </div>

          <div className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs font-medium text-forge-text">Operators</div>
              <div className="font-mono text-[10px] text-forge-muted">{operators.length}</div>
            </div>
            <OperatorHistory operators={operators} selectedId={activeOperator?.id} onSelect={setActiveOperator} />
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[10px] text-forge-muted">{activeOperator?.id || 'no operator selected'}</div>
                <h4 className="text-base font-medium text-forge-text">{activeOperator?.name || 'Operator detail'}</h4>
              </div>
              <StatusPill value={activeOperator?.status} />
            </div>
            {activeOperator ? (
              <>
                <p className="rounded-lg border border-forge-border bg-forge-panel/40 p-3 text-sm leading-relaxed text-forge-text">
                  {activeOperator.goal}
                </p>
                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">ticks</div>
                    <div className="font-mono text-lg text-forge-text">{activeOperator.ticks?.length || 0}</div>
                  </div>
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">cadence</div>
                    <div className="font-mono text-lg text-forge-text">{activeOperator.cadence_s}s</div>
                  </div>
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">supervisor</div>
                    <div className="font-mono text-lg text-forge-text">{status?.supervisor_running ? 'on' : 'off'}</div>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    onClick={() => command('tick')}
                    disabled={busy}
                    className="rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-3 py-2 text-xs text-emerald-100 hover:bg-emerald-500/30 disabled:opacity-40"
                  >
                    Manual tick
                  </button>
                  <button
                    onClick={() => command('pause')}
                    disabled={busy || activeOperator.status !== 'active'}
                    className="rounded-lg border border-amber-400/40 bg-amber-500/20 px-3 py-2 text-xs text-amber-100 hover:bg-amber-500/30 disabled:opacity-40"
                  >
                    Pause
                  </button>
                  <button
                    onClick={() => command('resume')}
                    disabled={busy || activeOperator.status === 'active'}
                    className="rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-xs text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
                  >
                    Resume
                  </button>
                </div>
              </>
            ) : (
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                Create an operator to start persistent autonomous mode.
              </div>
            )}
          </section>

          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 text-xs font-medium text-forge-text">Tick audit</div>
            <div className="space-y-3">
              {(activeOperator?.ticks || []).slice().reverse().map(tick => (
                <TickCard key={tick.id} tick={tick} />
              ))}
              {!activeOperator?.ticks?.length && (
                <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                  No ticks yet. Use manual tick or wait for the cadence.
                </div>
              )}
            </div>
          </section>
        </div>
      </section>
    </div>
  )
}
