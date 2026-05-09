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

function StatusPill({ ok, label }) {
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

export default function AssuranceOpsPanel({ eventLog }) {
  const [status, setStatus] = useState(null)
  const [drill, setDrill] = useState(null)
  const [risk, setRisk] = useState(null)
  const [lockdownPreview, setLockdownPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const moduleCount = status?.phases ? Object.keys(status.phases).length : 10
  const readinessOk = drill?.readiness?.ok ?? status?.readiness?.ok
  const evalRan = Boolean(drill?.evaluation)
  const evalOk = drill?.evaluation?.ok
  const statusText = useMemo(() => {
    if (busy) return 'working'
    if (latestEvent?.type === 'governance.drill_completed') return 'drill complete'
    if (drill) return 'complete'
    return 'ready'
  }, [busy, drill, latestEvent])

  const loadStatus = async () => {
    try {
      const data = await apiRequest('/api/genesis/governance/status')
      setStatus(data)
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load governance status')
    }
  }

  useEffect(() => {
    loadStatus()
  }, [])

  const runRisk = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/governance/risk-score', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_type: 'deploy_change',
          payload: {
            target: 'production-runtime',
            contains_sensitive_data: false,
          },
          permissions: ['deploy_change', 'human_approval'],
        }),
      })
      setRisk(data)
    } catch (e) {
      setError(e.message || 'Risk scoring failed')
    } finally {
      setBusy(false)
    }
  }

  const runDrill = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/governance/drill', { method: 'POST' })
      setDrill(data)
      setRisk(data.risk)
      await loadStatus()
    } catch (e) {
      setError(e.message || 'Assurance drill failed')
    } finally {
      setBusy(false)
    }
  }

  const toggleLockdownPreview = async (locked) => {
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/governance/lockdown', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          locked,
          reason: locked ? 'Benchmarks7 preview lockdown from assurance panel.' : 'Benchmarks7 preview lockdown lifted.',
          actor: 'assurance_panel',
        }),
      })
      setLockdownPreview(data.lockdown)
      await loadStatus()
    } catch (e) {
      setError(e.message || 'Lockdown control failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Assurance And Operations</h3>
          <p className="text-[10px] text-forge-muted">
            Replay, risk, capabilities, lockdown, intent binding, evidence, evals, production readiness, and accountability in one control plane.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">assurance</div>
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
          <div className="text-[10px] text-forge-muted">readiness</div>
          <StatusPill ok={Boolean(readinessOk)} label={readinessOk ? 'ready' : 'review'} />
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-3">
          <div className="text-[10px] text-forge-muted">evaluation</div>
          <StatusPill ok={Boolean(evalOk)} label={evalOk ? 'passed' : evalRan ? 'review' : 'not run'} />
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-3">
          <div className="text-[10px] text-forge-muted">lockdown</div>
          <div className="font-mono text-sm text-forge-text">{(lockdownPreview || status?.lockdown)?.locked ? 'locked' : 'open'}</div>
        </div>
      </section>

      <section className="mb-4 grid gap-3 md:grid-cols-4">
        <button
          onClick={runDrill}
          disabled={busy}
          className="rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
        >
          Run assurance drill
        </button>
        <button
          onClick={runRisk}
          disabled={busy}
          className="rounded-lg border border-purple-400/40 bg-purple-500/20 px-3 py-2 text-sm text-purple-100 hover:bg-purple-500/30 disabled:opacity-40"
        >
          Score production risk
        </button>
        <button
          onClick={() => toggleLockdownPreview(true)}
          disabled={busy}
          className="rounded-lg border border-red-400/40 bg-red-500/20 px-3 py-2 text-sm text-red-100 hover:bg-red-500/30 disabled:opacity-40"
        >
          Enable lockdown
        </button>
        <button
          onClick={() => toggleLockdownPreview(false)}
          disabled={busy}
          className="rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-3 py-2 text-sm text-emerald-100 hover:bg-emerald-500/30 disabled:opacity-40"
        >
          Lift lockdown
        </button>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <JsonBlock title="Replay" value={drill?.replay} />
        <JsonBlock title="Risk Score" value={risk || drill?.risk} />
        <JsonBlock title="Capability Registry" value={drill?.capability_registry || status?.capability_registry} />
        <JsonBlock title="Intent Binding" value={drill?.intent_binding} />
        <JsonBlock title="Evidence Bundle" value={drill?.evidence && {
          id: drill.evidence.id,
          approval_id: drill.evidence.approval_id,
          evidence_hash: drill.evidence.evidence_hash,
          created_at: drill.evidence.created_at,
        }} />
        <JsonBlock title="Connector Production Plan" value={drill?.connector_plan || status?.connector_plan} />
        <JsonBlock title="Evaluation Monitor" value={drill?.evaluation} />
        <JsonBlock title="Production Readiness" value={drill?.readiness || status?.readiness} />
        <JsonBlock title="Accountability" value={drill?.dashboard || status?.dashboard} />
        <JsonBlock title="Lockdown State" value={lockdownPreview || status?.lockdown} />
      </section>
    </div>
  )
}
