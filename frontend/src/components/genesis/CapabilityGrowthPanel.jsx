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
        {JSON.stringify(value || {}, (key, val) => typeof val === "string" ? val.replace(/agi-\d+(?:-\d+)?-v\d+/gi, "module-v1").replace(/AGI-\d+(?:-\d+)?/g, "module") : val, 2).replace(/"phases":/g, "\"modules\":")}
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

export default function CapabilityGrowthPanel({ eventLog }) {
  const [status, setStatus] = useState(null)
  const [drill, setDrill] = useState(null)
  const [research, setResearch] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const moduleCount = status?.phases ? Object.keys(status.phases).length : 10
  const statusText = useMemo(() => {
    if (busy) return 'working'
    if (latestEvent?.type === 'capability.drill_completed') return 'drill complete'
    if (drill) return 'complete'
    return 'ready'
  }, [busy, drill, latestEvent])

  const loadStatus = async () => {
    try {
      const data = await apiRequest('/api/genesis/capabilities/status')
      setStatus(data)
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load capability status')
    }
  }

  useEffect(() => {
    loadStatus()
  }, [])

  const runDrill = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/capabilities/drill', { method: 'POST' })
      setDrill(data)
      await loadStatus()
    } catch (e) {
      setError(e.message || 'Capability drill failed')
    } finally {
      setBusy(false)
    }
  }

  const runResearch = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/capabilities/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: 'How does Genesis track long-horizon work?',
          sources: [
            {
              title: 'Task graph planner',
              url: 'local://module-24',
              claim: 'Genesis tracks dependency state for blocked, ready, and done tasks.',
            },
            {
              title: 'Session continuity',
              url: 'local://module-31',
              claim: 'Genesis stores durable checkpoints for later resumption.',
            },
          ],
        }),
      })
      setResearch(data.research)
    } catch (e) {
      setError(e.message || 'Research loop failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Capability Growth</h3>
          <p className="text-[10px] text-forge-muted">
            Planning, project memory, verification, self-healing, research, model routing, skill compilation, continuity, preferences, and deployment.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">capability</div>
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
          <div className="text-[10px] text-forge-muted">planner</div>
          <Pill ok={Boolean(drill?.task_graph)} label={drill?.task_graph ? 'active' : 'ready'} />
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-3">
          <div className="text-[10px] text-forge-muted">verification</div>
          <Pill ok={Boolean(drill?.verification?.ok)} label={drill?.verification?.ok ? 'passed' : 'not run'} />
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-3">
          <div className="text-[10px] text-forge-muted">deployment</div>
          <Pill ok={Boolean(drill?.deployment?.ok)} label={drill?.deployment?.ok ? 'ready' : 'review'} />
        </div>
      </section>

      <section className="mb-4 grid gap-3 md:grid-cols-2">
        <button
          onClick={runDrill}
          disabled={busy}
          className="rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
        >
          Run capability drill
        </button>
        <button
          onClick={runResearch}
          disabled={busy}
          className="rounded-lg border border-purple-400/40 bg-purple-500/20 px-3 py-2 text-sm text-purple-100 hover:bg-purple-500/30 disabled:opacity-40"
        >
          Run research loop
        </button>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <JsonBlock title="Task Graph Planner" value={drill?.task_graph || status?.latest_task_graphs?.[0]} />
        <JsonBlock title="Project Memory" value={drill?.project_memory} />
        <JsonBlock title="Tool Result Verifier" value={drill?.verification} />
        <JsonBlock title="Self-Healing Runtime" value={drill?.self_heal} />
        <JsonBlock title="Research Loop" value={research || drill?.research} />
        <JsonBlock title="Model Router" value={drill?.model_route} />
        <JsonBlock title="Skill Compiler" value={drill?.compiled_skill} />
        <JsonBlock title="Session Continuity" value={drill?.checkpoint || status?.latest_checkpoints?.[0]} />
        <JsonBlock title="Preference Learning" value={drill?.preference || status?.preferences?.[0]} />
        <JsonBlock title="Deployment Pipeline" value={drill?.deployment} />
      </section>
    </div>
  )
}
