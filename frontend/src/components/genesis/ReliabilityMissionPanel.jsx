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

export default function ReliabilityMissionPanel({ eventLog }) {
  const [status, setStatus] = useState(null)
  const [drill, setDrill] = useState(null)
  const [mission, setMission] = useState(null)
  const [goal, setGoal] = useState('Complete a safe end-to-end Genesis reliability mission.')
  const [constraintsText, setConstraintsText] = useState('no external side effects without explicit approval\nreturn evidence before release')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const moduleCount = status?.phases ? Object.keys(status.phases).length : 10
  const statusText = useMemo(() => {
    if (busy) return 'working'
    if (latestEvent?.type === 'reliability.drill_completed') return 'drill complete'
    if (drill || mission) return 'ready'
    return 'idle'
  }, [busy, drill, mission, latestEvent])

  const loadStatus = async () => {
    try {
      const data = await apiRequest('/api/genesis/reliability/status')
      setStatus(data)
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load reliability status')
    }
  }

  useEffect(() => {
    loadStatus()
  }, [])

  const runDrill = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/reliability/drill', { method: 'POST' })
      setDrill(data)
      setMission(data.mission_runner)
      await loadStatus()
    } catch (e) {
      setError(e.message || 'Reliability drill failed')
    } finally {
      setBusy(false)
    }
  }

  const runMission = async () => {
    setBusy(true)
    setError(null)
    try {
      const constraints = constraintsText
        .split('\n')
        .map(item => item.trim())
        .filter(Boolean)
      const data = await apiRequest('/api/genesis/reliability/missions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal,
          constraints,
        }),
      })
      setMission(data.mission)
      await loadStatus()
    } catch (e) {
      setError(e.message || 'Mission runner failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Mission Control</h3>
          <p className="text-[10px] text-forge-muted">
            Benchmark packs, scenario simulation, long-horizon planning, trust, workstyle memory, env readiness, model routing, missions, replay, and deployment packaging.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">mission control</div>
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
          <div className="text-[10px] text-forge-muted">mission</div>
          <Pill ok={Boolean(mission)} label={mission?.status || 'not run'} />
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-3">
          <div className="text-[10px] text-forge-muted">trust</div>
          <Pill ok={Boolean(drill?.trust_dashboard)} label={drill?.trust_dashboard?.risk_posture || 'ready'} />
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-3">
          <div className="text-[10px] text-forge-muted">package</div>
          <Pill ok={Boolean(drill?.deployment_package?.ready)} label={drill?.deployment_package ? (drill.deployment_package.ready ? 'ready' : 'review') : 'ready'} />
        </div>
      </section>

      <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/30 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-xs font-medium text-forge-text">Mission Brief</div>
            <div className="text-[10px] text-forge-muted">Describe the goal, then create a planned mission with approval-aware constraints.</div>
          </div>
          <Pill ok={Boolean(mission)} label={mission ? 'planned' : 'draft'} />
        </div>
        <div className="grid gap-3 lg:grid-cols-[1fr_360px]">
          <label className="block">
            <div className="mb-1 text-[10px] text-forge-muted">goal</div>
            <textarea
              value={goal}
              onChange={e => setGoal(e.target.value)}
              className="h-28 w-full rounded border border-forge-border bg-forge-bg/70 p-3 text-xs text-forge-text focus:border-purple-400 focus:outline-none"
            />
          </label>
          <label className="block">
            <div className="mb-1 text-[10px] text-forge-muted">constraints</div>
            <textarea
              value={constraintsText}
              onChange={e => setConstraintsText(e.target.value)}
              className="h-28 w-full rounded border border-forge-border bg-forge-bg/70 p-3 text-xs text-forge-text focus:border-purple-400 focus:outline-none"
            />
          </label>
        </div>
      </section>

      <section className="mb-4 grid gap-3 md:grid-cols-2">
        <button
          onClick={runDrill}
          disabled={busy}
          className="rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
        >
          Run mission-readiness drill
        </button>
        <button
          onClick={runMission}
          disabled={busy || !goal.trim()}
          className="rounded-lg border border-purple-400/40 bg-purple-500/20 px-3 py-2 text-sm text-purple-100 hover:bg-purple-500/30 disabled:opacity-40"
        >
          Plan mission
        </button>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <JsonBlock title="Benchmark Pack" value={drill?.benchmark_pack} />
        <JsonBlock title="Scenario Simulator" value={drill?.scenario} />
        <JsonBlock title="Long-Horizon Planner" value={drill?.long_horizon_plan} />
        <JsonBlock title="Trust Dashboard" value={drill?.trust_dashboard} />
        <JsonBlock title="Workstyle Memory" value={drill?.workstyle_memory} />
        <JsonBlock title="Environment Manager" value={drill?.environment_manager} />
        <JsonBlock title="Model Router" value={drill?.model_router} />
        <JsonBlock title="Mission Runner" value={mission || status?.latest_missions?.[0]} />
        <JsonBlock title="Replay Studio" value={drill?.observability_replay || status?.latest_replays?.[0]} />
        <JsonBlock title="Deployment Package" value={drill?.deployment_package || status?.latest_packages?.[0]} />
      </section>
    </div>
  )
}
