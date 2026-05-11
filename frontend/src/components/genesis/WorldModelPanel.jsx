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
    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data))
  }
  return data
}

function JsonBlock({ title, value }) {
  return (
    <section className="rounded-xl border border-forge-border p-4">
      <div className="mb-3 text-xs font-medium text-forge-text">{title}</div>
      <pre className="max-h-96 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
        {JSON.stringify(value || {}, null, 2)}
      </pre>
    </section>
  )
}

function Pill({ ok, label }) {
  return (
    <span className={`rounded border px-2 py-0.5 text-[10px] ${
      ok
        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
        : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
    }`}>
      {label || (ok ? 'ok' : 'review')}
    </span>
  )
}

export default function WorldModelPanel({ eventLog }) {
  const [status, setStatus] = useState(null)
  const [drill, setDrill] = useState(null)
  const [goal, setGoal] = useState('Improve Genesis mission planning through grounded learning.')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const moduleCount = status?.modules ? Object.keys(status.modules).length : 5
  const statusText = useMemo(() => {
    if (busy) return 'learning'
    if (latestEvent?.type === 'world.learning_completed') return 'learning complete'
    if (drill) return 'updated'
    return 'ready'
  }, [busy, drill, latestEvent])

  const loadStatus = async () => {
    try {
      const data = await apiRequest('/api/genesis/world/status')
      setStatus(data)
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load world model')
    }
  }

  useEffect(() => {
    loadStatus()
  }, [])

  const runLearningLoop = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/world/drill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal }),
      })
      setDrill(data)
      await loadStatus()
    } catch (e) {
      setError(e.message || 'Learning loop failed')
    } finally {
      setBusy(false)
    }
  }

  const snapshot = drill?.snapshot || status?.latest_snapshot

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">World Model</h3>
          <p className="text-[10px] text-forge-muted">
            Entities, evidence, beliefs, lessons, and reusable skill suggestions learned from missions.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">learning loop</div>
          <div className="text-sm font-mono text-forge-text">{statusText}</div>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <section className="mb-4 grid gap-3 md:grid-cols-4">
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-3">
          <div className="text-[10px] text-forge-muted">modules</div>
          <div className="font-mono text-lg text-forge-text">{moduleCount}</div>
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-3">
          <div className="text-[10px] text-forge-muted">beliefs</div>
          <Pill ok={Boolean(snapshot?.summary?.beliefs)} label={`${snapshot?.summary?.beliefs || 0}`} />
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-3">
          <div className="text-[10px] text-forge-muted">lessons</div>
          <Pill ok={Boolean(snapshot?.summary?.lessons)} label={`${snapshot?.summary?.lessons || 0}`} />
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-3">
          <div className="text-[10px] text-forge-muted">skills</div>
          <Pill ok={Boolean(snapshot?.summary?.skill_suggestions)} label={`${snapshot?.summary?.skill_suggestions || 0}`} />
        </div>
      </section>

      <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/30 p-4">
        <label htmlFor="world-learning-goal" className="mb-3 block text-xs font-medium text-forge-text">
          Learning Goal
        </label>
        <textarea
          id="world-learning-goal"
          value={goal}
          onChange={e => setGoal(e.target.value)}
          className="h-24 w-full rounded border border-forge-border bg-forge-bg/70 p-3 text-xs text-forge-text focus:border-purple-400 focus:outline-none"
        />
        <button
          onClick={runLearningLoop}
          disabled={busy || !goal.trim()}
          className="mt-3 w-full rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
        >
          Run learning loop
        </button>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <JsonBlock title="Learning Loop" value={drill} />
        <JsonBlock title="Entity" value={drill?.entity || snapshot?.entities?.[0]} />
        <JsonBlock title="Evidence" value={drill?.evidence || snapshot?.evidence?.[0]} />
        <JsonBlock title="Belief" value={drill?.belief || snapshot?.beliefs?.[0]} />
        <JsonBlock title="Lesson" value={drill?.lesson || status?.latest_lessons?.[0]} />
        <JsonBlock title="Skill Suggestion" value={drill?.skill_suggestion || status?.latest_suggestions?.[0]} />
        <JsonBlock title="World Snapshot" value={snapshot} />
      </section>
    </div>
  )
}
