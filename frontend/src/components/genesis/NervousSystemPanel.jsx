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

function Meter({ label, value, tone = 'cyan' }) {
  const safeValue = Math.max(0, Math.min(1, Number(value || 0)))
  const color = tone === 'red' ? 'bg-red-400' : tone === 'amber' ? 'bg-amber-300' : 'bg-cyan-300'
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[10px] text-forge-muted">
        <span>{label}</span>
        <span className="font-mono text-forge-text">{Math.round(safeValue * 100)}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded bg-forge-border/60">
        <div className={`h-full ${color}`} style={{ width: `${safeValue * 100}%` }} />
      </div>
    </div>
  )
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

function NeedCard({ need }) {
  return (
    <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium text-forge-text">{need.name}</div>
          <div className="mt-1 text-[10px] text-forge-muted">{need.reason}</div>
        </div>
        <span className="rounded border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 font-mono text-[10px] text-amber-200">
          {Math.round((need.urgency || 0) * 100)}
        </span>
      </div>
      <div className="mt-2 text-[10px] text-cyan-200">{need.drive}</div>
    </div>
  )
}

function IntentionRow({ intention, onComplete, busy }) {
  return (
    <div className="rounded-xl border border-forge-border bg-forge-panel/30 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium text-forge-text">{intention.goal}</div>
          <div className="mt-1 text-[10px] text-forge-muted">{intention.reason}</div>
          <div className="mt-2 flex flex-wrap gap-2 text-[10px]">
            <span className="rounded border border-forge-border px-2 py-0.5 text-forge-muted">{intention.action}</span>
            <span className="rounded border border-forge-border px-2 py-0.5 text-forge-muted">{intention.status}</span>
            {intention.approval_required && (
              <span className="rounded border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-amber-200">approval-gated</span>
            )}
          </div>
        </div>
        {intention.status === 'queued' && (
          <button
            onClick={() => onComplete(intention.id)}
            disabled={busy}
            className="shrink-0 rounded border border-emerald-400/40 bg-emerald-500/10 px-2 py-1 text-[10px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-40"
          >
            Complete
          </button>
        )}
      </div>
    </div>
  )
}

function CycleRow({ cycle }) {
  const blocked = cycle.status === 'blocked'
  const executed = cycle.status === 'executed'
  return (
    <div className="rounded-xl border border-forge-border bg-forge-panel/30 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium text-forge-text">{cycle.action || 'autonomy cycle'}</div>
          <div className="mt-1 text-[10px] text-forge-muted">{cycle.result?.summary || cycle.result?.reason || cycle.status}</div>
          <div className="mt-2 text-[10px] text-forge-muted">{cycle.created_at}</div>
        </div>
        <span className={`rounded border px-2 py-0.5 text-[10px] ${
          blocked
            ? 'border-amber-400/30 bg-amber-400/10 text-amber-200'
            : executed
              ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
              : 'border-forge-border text-forge-muted'
        }`}>
          {cycle.status}
        </span>
      </div>
    </div>
  )
}

function BodyCard({ title, items, empty }) {
  return (
    <div className="rounded-xl border border-forge-border bg-forge-panel/20 p-4">
      <div className="mb-3 text-xs font-medium text-forge-text">{title}</div>
      <div className="space-y-2">
        {(items || []).map(item => (
          <div key={item.id || item.action || item.kind} className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">{item.name || item.kind || item.action}</div>
                <div className="mt-1 text-[10px] text-forge-muted">{item.description || item.reason || item.status}</div>
              </div>
              <span className="rounded border border-forge-border px-2 py-0.5 text-[10px] text-forge-muted">
                {item.status || item.risk || item.kind}
              </span>
            </div>
            {item.approval_required && (
              <div className="mt-2 text-[10px] text-amber-200">approval-gated</div>
            )}
          </div>
        ))}
        {!(items || []).length && (
          <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3 text-xs text-forge-muted">
            {empty}
          </div>
        )}
      </div>
    </div>
  )
}

function LivingSystemCard({ title, version, children }) {
  return (
    <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="text-xs font-medium text-forge-text">{title}</div>
        <span className="rounded border border-forge-border px-2 py-0.5 text-[10px] text-forge-muted">
          {version || 'v1'}
        </span>
      </div>
      <div className="mt-2 text-[10px] text-forge-muted">{children}</div>
    </div>
  )
}

export default function NervousSystemPanel({ activeOrganism, eventLog }) {
  const [state, setState] = useState(null)
  const [fleet, setFleet] = useState(null)
  const [body, setBody] = useState(null)
  const [metabolism, setMetabolism] = useState(null)
  const [homeostasis, setHomeostasis] = useState(null)
  const [livingSystems, setLivingSystems] = useState(null)
  const [lifeEngine, setLifeEngine] = useState(null)
  const [selection, setSelection] = useState(null)
  const [temperament, setTemperament] = useState(null)
  const [goalRefinement, setGoalRefinement] = useState(null)
  const [societyCulture, setSocietyCulture] = useState(null)
  const [taskEconomy, setTaskEconomy] = useState(null)
  const [worldSandbox, setWorldSandbox] = useState(null)
  const [lastCycle, setLastCycle] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const organismId = activeOrganism?.id
  const latestTick = eventLog?.find(event => event.type === 'organism.nervous_tick' && event.organism_id === organismId)
  const needs = state?.needs || []
  const intentions = state?.intentions || []
  const cycles = state?.autonomy_cycles || []
  const topNeed = needs[0]
  const statusText = useMemo(() => {
    if (!organismId) return 'no organism'
    if (busy) return 'ticking'
    return state?.phase || 'ready'
  }, [busy, organismId, state])

  const load = async () => {
    try {
      const [fleetData, organismData] = await Promise.all([
        apiRequest('/api/genesis/nervous-system/status'),
        organismId ? apiRequest(`/api/genesis/organisms/${organismId}/nervous-system`) : Promise.resolve(null),
      ])
      setFleet(fleetData)
      setState(organismData?.nervous_system || null)
      if (organismId) {
        const [bodyData, metabolismData, homeostasisData, livingData] = await Promise.all([
          apiRequest(`/api/genesis/organisms/${organismId}/body`),
          apiRequest(`/api/genesis/organisms/${organismId}/metabolism`),
          apiRequest(`/api/genesis/organisms/${organismId}/homeostasis`),
          apiRequest(`/api/genesis/organisms/${organismId}/living-systems`),
        ])
        setBody(bodyData.body || null)
        setMetabolism(metabolismData.metabolism || null)
        setHomeostasis(homeostasisData.homeostasis || null)
        setLivingSystems(livingData || null)
        setLifeEngine(livingData?.life_engine || null)
        setSelection(livingData?.selection || null)
        setTemperament(livingData?.life_engine?.temperament || null)
        setGoalRefinement(livingData?.life_engine?.goal_refinement || null)
        setSocietyCulture(livingData?.society_culture || livingData?.life_engine?.society_culture || null)
        setTaskEconomy(livingData?.task_economy || livingData?.life_engine?.task_economy || null)
        setWorldSandbox(livingData?.world_sandbox || livingData?.life_engine?.world_sandbox || null)
      } else {
        setBody(null)
        setMetabolism(null)
        setHomeostasis(null)
        setLivingSystems(null)
        setLifeEngine(null)
        setSelection(null)
        setTemperament(null)
        setGoalRefinement(null)
        setSocietyCulture(null)
        setTaskEconomy(null)
        setWorldSandbox(null)
      }
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load nervous system')
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [organismId])

  const tick = async () => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/organisms/${organismId}/nervous-system/tick`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stimulus: { type: 'manual_nervous_system_tick', source: 'ui' } }),
      })
      setState(data.nervous_system)
      await load()
    } catch (e) {
      setError(e.message || 'Nervous system tick failed')
    } finally {
      setBusy(false)
    }
  }

  const runAutonomyCycle = async () => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/organisms/${organismId}/autonomy/cycle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stimulus: { type: 'manual_embodied_autonomy_cycle', source: 'ui' } }),
      })
      setState(data.nervous_system)
      if (data.nervous_system?.body) setBody(data.nervous_system.body)
      if (data.nervous_system?.metabolism) setMetabolism(data.nervous_system.metabolism)
      if (data.nervous_system?.homeostasis) setHomeostasis(data.nervous_system.homeostasis)
      setLastCycle(data.cycle)
      await load()
    } catch (e) {
      setError(e.message || 'Autonomy cycle failed')
    } finally {
      setBusy(false)
    }
  }

  const completeIntention = async (intentionId) => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/organisms/${organismId}/nervous-system/intentions/${intentionId}/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ result: { completed_from: 'nervous_system_panel' } }),
      })
      setState(data.nervous_system)
      await load()
    } catch (e) {
      setError(e.message || 'Failed to complete intention')
    } finally {
      setBusy(false)
    }
  }

  const attachRecommendedSensor = async (recommendationId) => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/organisms/${organismId}/body/sensors/recommended`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recommendation_id: recommendationId }),
      })
      setBody(data.body)
      await load()
    } catch (e) {
      setError(e.message || 'Failed to attach sensor')
    } finally {
      setBusy(false)
    }
  }

  const recoverMetabolism = async () => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/organisms/${organismId}/metabolism/recover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ depth: 'rest' }),
      })
      setMetabolism(data.metabolism)
      setState(data.nervous_system)
      if (data.nervous_system?.homeostasis) setHomeostasis(data.nervous_system.homeostasis)
      await load()
    } catch (e) {
      setError(e.message || 'Metabolic recovery failed')
    } finally {
      setBusy(false)
    }
  }

  const runImmuneResponse = async () => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/organisms/${organismId}/homeostasis/immune-response`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'auto' }),
      })
      setHomeostasis(data.homeostasis)
      setState(data.nervous_system)
      if (data.nervous_system?.metabolism) setMetabolism(data.nervous_system.metabolism)
      await load()
    } catch (e) {
      setError(e.message || 'Immune response failed')
    } finally {
      setBusy(false)
    }
  }

  const reproduceOrganism = async () => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      await apiRequest(`/api/genesis/organisms/${organismId}/reproduce`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mutation: 'conservative' }),
      })
      await load()
    } catch (e) {
      setError(e.message || 'Reproduction failed')
    } finally {
      setBusy(false)
    }
  }

  const consolidateSleep = async () => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      await apiRequest(`/api/genesis/organisms/${organismId}/sleep/consolidate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      await load()
    } catch (e) {
      setError(e.message || 'Sleep consolidation failed')
    } finally {
      setBusy(false)
    }
  }

  const tickDevelopment = async () => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/organisms/${organismId}/development/tick`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      setLifeEngine(data.life_engine)
      await load()
    } catch (e) {
      setError(e.message || 'Development tick failed')
    } finally {
      setBusy(false)
    }
  }

  const runSelectionRound = async () => {
    setBusy(true)
    setError(null)
    try {
      const round = await apiRequest('/api/genesis/selection/round', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pressure: 'balanced', limit: 80 }),
      })
      setSelection(prev => ({
        ...(prev || {}),
        version: 'organism-selection-v1',
        latest_round: round,
        history: {
          version: 'organism-selection-history-v1',
          rounds: [round, ...((prev?.history?.rounds || []).filter(item => item.id !== round.id))],
        },
      }))
      await load()
    } catch (e) {
      setError(e.message || 'Selection round failed')
    } finally {
      setBusy(false)
    }
  }

  const calibrateTemperament = async () => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/organisms/${organismId}/temperament/calibrate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      setTemperament(data.temperament)
      await load()
    } catch (e) {
      setError(e.message || 'Temperament calibration failed')
    } finally {
      setBusy(false)
    }
  }

  const proposeGoalRefinement = async () => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/organisms/${organismId}/goal-refinement/propose`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ focus: 'auto' }),
      })
      setGoalRefinement(data.status)
      await load()
    } catch (e) {
      setError(e.message || 'Goal refinement failed')
    } finally {
      setBusy(false)
    }
  }

  const runCulturePulse = async () => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/organisms/${organismId}/society-culture/pulse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ focus: 'norms' }),
      })
      setSocietyCulture(data.society_culture)
      await load()
    } catch (e) {
      setError(e.message || 'Culture pulse failed')
    } finally {
      setBusy(false)
    }
  }

  const runBudgetPulse = async () => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/organisms/${organismId}/task-economy/pulse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ focus: 'balanced' }),
      })
      setTaskEconomy(data.task_economy)
      await load()
    } catch (e) {
      setError(e.message || 'Budget pulse failed')
    } finally {
      setBusy(false)
    }
  }

  const runWorldSandboxPulse = async () => {
    if (!organismId) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/organisms/${organismId}/world-sandbox/pulse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: 'current_tasks' }),
      })
      setWorldSandbox(data.world_sandbox)
      await load()
    } catch (e) {
      setError(e.message || 'World sandbox pulse failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Organism Nervous System</h3>
          <p className="text-[10px] text-forge-muted">
            Drives, needs, vitals, and autonomous intentions for the selected living organism.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">inner loop</div>
          <div className="text-sm font-mono text-forge-text">{statusText}</div>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
          {error}
        </div>
      )}

      {!organismId ? (
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-6 text-center text-sm text-forge-muted">
          Select or seed an organism to inspect its inner life.
        </div>
      ) : (
        <>
          <section className="mb-4 grid gap-3 md:grid-cols-4">
            <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-4">
              <div className="text-[10px] text-forge-muted">status</div>
              <div className="mt-1 font-mono text-lg text-forge-text">{state?.phase || 'awake'}</div>
              <div className="mt-1 text-[10px] text-forge-muted">{state?.mood || 'oriented'}</div>
            </div>
            <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-4 space-y-3">
              <Meter label="energy" value={state?.energy} />
              <Meter label="attention" value={state?.attention} />
              <Meter label="stress" value={state?.stress} tone="amber" />
            </div>
            <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-4">
              <div className="text-[10px] text-forge-muted">top need</div>
              <div className="mt-1 text-sm font-medium text-forge-text">{topNeed?.name || 'stable'}</div>
              <div className="mt-1 text-[10px] text-forge-muted">{topNeed?.drive || 'balanced'}</div>
            </div>
            <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-4">
              <div className="text-[10px] text-forge-muted">fleet autonomy</div>
              <div className="mt-1 font-mono text-lg text-forge-text">{fleet?.summary?.queued_intentions || 0}</div>
              <div className="mt-1 text-[10px] text-forge-muted">queued intentions</div>
            </div>
          </section>

          <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">World Sandbox With Hazards</div>
                <div className="text-[10px] text-forge-muted">Rehearses funded work in a local simulated world with hazards before any real action is attempted.</div>
              </div>
              <div className="rounded border border-forge-border px-2 py-1 text-[10px] text-forge-muted">
                {worldSandbox?.version || 'organism-world-sandbox-v1'}
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="hazard index" value={worldSandbox?.hazard_index} tone="amber" />
                <div className="mt-2 text-[10px] text-forge-muted">{worldSandbox?.world_state?.mode || 'local_simulation'}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="resource pressure" value={worldSandbox?.world_state?.resource_pressure} tone="amber" />
                <div className="mt-2 text-[10px] text-forge-muted">{worldSandbox?.world_state?.population || 0} organisms in simulation</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">top hazard</div>
                <div className="mt-1 text-sm font-medium text-forge-text">{worldSandbox?.hazards?.[0]?.name || 'approval boundary bypass'}</div>
                <div className="mt-1 text-[10px] text-forge-muted">{Math.round((worldSandbox?.hazards?.[0]?.severity || 0) * 100)}% severity</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">rehearsals</div>
                <div className="mt-1 font-mono text-lg text-forge-text">{worldSandbox?.rehearsals?.length || 0}</div>
                <div className="mt-1 text-[10px] text-forge-muted">{worldSandbox?.world_state?.external_side_effects ? 'external effects possible' : 'no external side effects'}</div>
              </div>
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-4">
              <LivingSystemCard title="Hazards" version={worldSandbox?.version}>
                {(worldSandbox?.hazards || []).slice(0, 3).map(item => `${item.name} ${Math.round((item.severity || 0) * 100)}%`).join(', ') || 'No hazards mapped'}
              </LivingSystemCard>
              <LivingSystemCard title="Rehearsals" version={worldSandbox?.version}>
                {(worldSandbox?.rehearsals || []).slice(0, 3).map(item => `${item.task_name}: ${item.predicted_outcome}`).join(', ') || 'No rehearsals yet'}
              </LivingSystemCard>
              <LivingSystemCard title="Safe Opportunities" version={worldSandbox?.version}>
                {(worldSandbox?.safe_opportunities || []).slice(0, 3).map(item => item.name).join(', ') || 'Observe first'}
              </LivingSystemCard>
              <LivingSystemCard title="Sandbox Rules" version={worldSandbox?.version}>
                {(worldSandbox?.sandbox_rules || []).slice(0, 2).join('; ') || 'no external side effects; no sensitive data transmission'}
              </LivingSystemCard>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                onClick={runWorldSandboxPulse}
                disabled={busy}
                className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100 hover:bg-amber-500/20 disabled:opacity-40"
              >
                Run sandbox pulse
              </button>
            </div>
          </section>

          <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">Task Economy And Resource Budgeting</div>
                <div className="text-[10px] text-forge-muted">Prices queued work by energy, attention, risk, and approval cost before deciding what the organism can afford.</div>
              </div>
              <div className="rounded border border-forge-border px-2 py-1 text-[10px] text-forge-muted">
                {taskEconomy?.version || 'organism-task-economy-v1'}
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="spendable energy" value={taskEconomy?.budgets?.spendable_energy} tone="cyan" />
                <div className="mt-2 text-[10px] text-forge-muted">reserve {Math.round((taskEconomy?.budgets?.reserve || 0) * 100)}%</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="spendable attention" value={taskEconomy?.budgets?.spendable_attention} tone="cyan" />
                <div className="mt-2 text-[10px] text-forge-muted">stress {Math.round((taskEconomy?.budgets?.stress || 0) * 100)}%</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">funded tasks</div>
                <div className="mt-1 font-mono text-lg text-forge-text">{taskEconomy?.funded_tasks?.length || 0}</div>
                <div className="mt-1 text-[10px] text-forge-muted">{taskEconomy?.tasks?.length || 0} tasks priced</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">role budget</div>
                <div className="mt-1 text-sm font-medium text-forge-text">{taskEconomy?.role?.role || 'builder'}</div>
                <div className="mt-1 text-[10px] text-forge-muted">{taskEconomy?.allocation_policy?.reserve_rule || 'protect repair and stability'}</div>
              </div>
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-4">
              <LivingSystemCard title="Funded Work" version={taskEconomy?.version}>
                {(taskEconomy?.funded_tasks || []).slice(0, 3).map(item => item.name).join(', ') || 'No work funded yet'}
              </LivingSystemCard>
              <LivingSystemCard title="Deferred Work" version={taskEconomy?.version}>
                {(taskEconomy?.deferred_tasks || []).slice(0, 3).map(item => `${item.name}: ${item.budget_status}`).join(', ') || 'No deferred work'}
              </LivingSystemCard>
              <LivingSystemCard title="Spend" version={taskEconomy?.version}>
                energy {Math.round((taskEconomy?.budgets?.spent_energy || 0) * 100)}% · attention {Math.round((taskEconomy?.budgets?.spent_attention || 0) * 100)}%
              </LivingSystemCard>
              <LivingSystemCard title="Policy" version={taskEconomy?.version}>
                {taskEconomy?.allocation_policy?.fund_order || 'highest value, lowest risk, affordable work first'}
              </LivingSystemCard>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                onClick={runBudgetPulse}
                disabled={busy}
                className="rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100 hover:bg-emerald-500/20 disabled:opacity-40"
              >
                Run budget pulse
              </button>
            </div>
          </section>

          <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">Society Roles And Culture</div>
                <div className="text-[10px] text-forge-muted">Population roles, shared norms, rights, responsibilities, rituals, and cultural memory for bounded digital organisms.</div>
              </div>
              <div className="rounded border border-forge-border px-2 py-1 text-[10px] text-forge-muted">
                {societyCulture?.version || 'organism-society-culture-v1'}
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">role</div>
                <div className="mt-1 text-sm font-medium text-forge-text">{societyCulture?.role?.role || 'builder'}</div>
                <div className="mt-1 text-[10px] text-forge-muted">{societyCulture?.role?.seniority || 'apprentice'} · {societyCulture?.role?.autonomy || 'approval_bounded'}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3 md:col-span-2">
                <div className="text-[10px] text-forge-muted">mandate</div>
                <div className="mt-1 text-xs text-forge-text">{societyCulture?.role?.mandate || 'turn shared goals into reliable internal work products'}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">motto</div>
                <div className="mt-1 text-xs text-forge-text">{societyCulture?.culture?.motto || 'bounded autonomy, visible evidence, shared repair'}</div>
              </div>
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-4">
              <LivingSystemCard title="Norms" version={societyCulture?.version}>
                {(societyCulture?.culture?.norms || []).slice(0, 3).join('; ') || 'approval, evidence, privacy'}
              </LivingSystemCard>
              <LivingSystemCard title="Responsibilities" version={societyCulture?.version}>
                {(societyCulture?.responsibilities || []).slice(0, 2).join('; ') || 'publish safe lessons; support repair'}
              </LivingSystemCard>
              <LivingSystemCard title="Rights" version={societyCulture?.version}>
                {(societyCulture?.rights || []).slice(0, 2).join('; ') || 'request review; refuse unsafe pressure'}
              </LivingSystemCard>
              <LivingSystemCard title="Relations" version={societyCulture?.version}>
                {(societyCulture?.community?.relations || []).slice(0, 3).map(item => `${item.name}: ${item.suggested_relation}`).join(', ') || 'no peers mapped'}
              </LivingSystemCard>
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-3">
              <LivingSystemCard title="Rituals" version={societyCulture?.version}>
                {(societyCulture?.culture?.rituals || []).slice(0, 3).join('; ') || 'culture pulse after role changes'}
              </LivingSystemCard>
              <LivingSystemCard title="Taboos" version={societyCulture?.version}>
                {(societyCulture?.culture?.taboos || []).slice(0, 3).join('; ') || 'no approval bypassing'}
              </LivingSystemCard>
              <LivingSystemCard title="Cultural Memory" version={societyCulture?.version}>
                {societyCulture?.cultural_memory?.length || 0} culture pulses recorded
              </LivingSystemCard>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                onClick={runCulturePulse}
                disabled={busy}
                className="rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/10 px-3 py-2 text-sm text-fuchsia-100 hover:bg-fuchsia-500/20 disabled:opacity-40"
              >
                Run culture pulse
              </button>
            </div>
          </section>

          <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">Self-Directed Goal Refinement</div>
                <div className="text-[10px] text-forge-muted">The organism can propose a sharper mission from pressure, memory, temperament, and development, but cannot apply it without approval.</div>
              </div>
              <div className="rounded border border-forge-border px-2 py-1 text-[10px] text-forge-muted">
                {goalRefinement?.version || 'organism-goal-refinement-status-v1'}
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="refine pressure" value={goalRefinement?.pressure_to_refine} tone="amber" />
                <div className="mt-2 text-[10px] text-forge-muted">{goalRefinement?.recommendation || 'monitor_current_goal'}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3 md:col-span-2">
                <div className="text-[10px] text-forge-muted">latest refined goal</div>
                <div className="mt-1 text-xs text-forge-text">
                  {goalRefinement?.latest_proposal?.refined_goal || goalRefinement?.current_goal || 'No refined goal proposed yet.'}
                </div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">review gate</div>
                <div className="mt-1 text-sm font-medium text-forge-text">
                  {goalRefinement?.review_gate?.requires_human_approval ? 'Approval required' : 'No gate'}
                </div>
                <div className="mt-1 text-[10px] text-forge-muted">
                  {goalRefinement?.review_gate?.can_auto_apply ? 'can auto-apply' : 'proposal only'}
                </div>
              </div>
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-3">
              <LivingSystemCard title="Why Refine" version={goalRefinement?.version}>
                {(goalRefinement?.reasons || []).join('; ') || 'current goal is stable'}
              </LivingSystemCard>
              <LivingSystemCard title="Alignment Checks" version={goalRefinement?.latest_proposal?.version}>
                {(goalRefinement?.latest_proposal?.alignment_checks || []).map(item => `${item.id}: ${item.passed ? 'pass' : 'review'}`).join(', ') || 'no proposal yet'}
              </LivingSystemCard>
              <LivingSystemCard title="Suggested Signals" version={goalRefinement?.latest_proposal?.version}>
                {(goalRefinement?.latest_proposal?.suggested_success_signals || []).slice(0, 3).join(', ') || 'waiting for proposal'}
              </LivingSystemCard>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                onClick={proposeGoalRefinement}
                disabled={busy}
                className="rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/20 disabled:opacity-40"
              >
                Propose refined goal
              </button>
            </div>
          </section>

          <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">Temperament And Personality</div>
                <div className="text-[10px] text-forge-muted">Stable traits expressed through current pressure, affect, memory, and safety posture.</div>
              </div>
              <div className="rounded border border-forge-border px-2 py-1 text-[10px] text-forge-muted">
                {temperament?.version || 'organism-temperament-v1'}
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">archetype</div>
                <div className="mt-1 text-sm font-medium text-forge-text">{temperament?.archetype || 'careful explorer'}</div>
                <div className="mt-1 text-[10px] text-forge-muted">{temperament?.decision_bias?.style || 'persist steadily'}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="curiosity" value={temperament?.current_expression?.curiosity} tone="cyan" />
                <div className="mt-2">
                  <Meter label="caution" value={temperament?.current_expression?.caution} tone="amber" />
                </div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="persistence" value={temperament?.current_expression?.persistence} tone="cyan" />
                <div className="mt-2">
                  <Meter label="adaptability" value={temperament?.current_expression?.adaptability} tone="cyan" />
                </div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="precision" value={temperament?.current_expression?.precision} tone="cyan" />
                <div className="mt-2">
                  <Meter label="sociability" value={temperament?.current_expression?.sociability} tone="cyan" />
                </div>
              </div>
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-3">
              <LivingSystemCard title="Dominant Traits" version={temperament?.version}>
                {(temperament?.dominant_traits || []).map(item => `${item.trait} ${Math.round((item.score || 0) * 100)}%`).join(', ') || 'not calibrated'}
              </LivingSystemCard>
              <LivingSystemCard title="Decision Bias" version={temperament?.version}>
                {temperament?.decision_bias?.risk_posture || 'balanced'} · {temperament?.decision_bias?.learning_posture || 'evidence-seeking'} · {temperament?.decision_bias?.autonomy_posture || 'approval-attentive'}
              </LivingSystemCard>
              <LivingSystemCard title="Stress Response" version={temperament?.version}>
                {temperament?.stress_response || 'probe with reversible actions'}
              </LivingSystemCard>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                onClick={calibrateTemperament}
                disabled={busy}
                className="rounded-lg border border-teal-400/40 bg-teal-500/10 px-3 py-2 text-sm text-teal-100 hover:bg-teal-500/20 disabled:opacity-40"
              >
                Calibrate temperament
              </button>
            </div>
          </section>

          <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">Evolution Pressure And Selection</div>
                <div className="text-[10px] text-forge-muted">Population pressure ranks organisms for promotion, maintenance, repair, dormancy, or legacy preservation.</div>
              </div>
              <div className="rounded border border-forge-border px-2 py-1 text-[10px] text-forge-muted">
                {selection?.latest_round?.version || selection?.version || 'organism-selection-v1'}
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="current score" value={selection?.current_score?.score} tone="cyan" />
                <div className="mt-2 text-[10px] text-forge-muted">{selection?.current_outcome || 'unselected'} outcome</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="ecosystem pressure" value={selection?.latest_round?.ecosystem_pressure} tone="amber" />
                <div className="mt-2 text-[10px] text-forge-muted">{selection?.latest_round?.population || 0} organisms scored</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">promoted</div>
                <div className="mt-1 font-mono text-lg text-forge-text">{selection?.latest_round?.counts?.promote || 0}</div>
                <div className="mt-1 text-[10px] text-forge-muted">reproduction candidates {(selection?.latest_round?.reproduction_candidates || []).length}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">repair / dormant / legacy</div>
                <div className="mt-1 font-mono text-lg text-forge-text">
                  {selection?.latest_round?.counts?.repair || 0}/{selection?.latest_round?.counts?.dormant || 0}/{selection?.latest_round?.counts?.legacy || 0}
                </div>
                <div className="mt-1 text-[10px] text-forge-muted">declining organisms under pressure</div>
              </div>
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-4">
              <LivingSystemCard title="Winners" version={selection?.latest_round?.version}>
                {(selection?.latest_round?.winners || []).map(item => item.name).join(', ') || 'No promotions yet'}
              </LivingSystemCard>
              <LivingSystemCard title="Repair Queue" version={selection?.latest_round?.version}>
                {(selection?.latest_round?.repair_queue || []).map(item => item.name).join(', ') || 'No repair queue'}
              </LivingSystemCard>
              <LivingSystemCard title="Dormant" version={selection?.latest_round?.version}>
                {(selection?.latest_round?.dormant || []).map(item => item.name).join(', ') || 'No dormant organisms'}
              </LivingSystemCard>
              <LivingSystemCard title="Legacy Candidates" version={selection?.latest_round?.version}>
                {(selection?.latest_round?.legacy_candidates || []).map(item => item.name).join(', ') || 'No legacy candidates'}
              </LivingSystemCard>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                onClick={runSelectionRound}
                disabled={busy}
                className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100 hover:bg-amber-500/20 disabled:opacity-40"
              >
                Run selection round
              </button>
            </div>
          </section>

          <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">Autonomous Metabolism</div>
                <div className="text-[10px] text-forge-muted">Resource pressure that decides when the organism acts, rests, repairs, or conserves.</div>
              </div>
              <div className="rounded border border-forge-border px-2 py-1 text-[10px] text-forge-muted">
                {metabolism?.survival_status || 'stable'} · {metabolism?.policy || 'act'}
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-5">
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="health" value={metabolism?.health} />
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="energy" value={metabolism?.energy} />
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="attention" value={metabolism?.attention} />
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="fatigue" value={metabolism?.fatigue} tone="amber" />
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="hunger" value={metabolism?.hunger} tone="amber" />
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <div className="flex-1 rounded-lg border border-forge-border bg-forge-bg/40 p-3 text-[10px] text-forge-muted">
                {metabolism?.last_policy_reason || 'Metabolic policy has not been evaluated yet.'}
              </div>
              <button
                onClick={recoverMetabolism}
                disabled={busy}
                className="rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100 hover:bg-emerald-500/20 disabled:opacity-40"
              >
                Recover
              </button>
            </div>
          </section>

          <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">Homeostasis And Immune System</div>
                <div className="text-[10px] text-forge-muted">Health monitoring that detects instability, quarantines unhealthy parts, and gates autonomy.</div>
              </div>
              <div className={`rounded border px-2 py-1 text-[10px] ${
                homeostasis?.fever
                  ? 'border-red-400/40 bg-red-500/10 text-red-200'
                  : homeostasis?.immune_status === 'watching'
                    ? 'border-amber-400/40 bg-amber-500/10 text-amber-200'
                    : 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200'
              }`}>
                {homeostasis?.immune_status || 'stable'}
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <Meter label="stability" value={homeostasis?.stability_score} tone={homeostasis?.fever ? 'red' : 'cyan'} />
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">anomalies</div>
                <div className="mt-1 font-mono text-lg text-forge-text">{homeostasis?.anomalies?.length || 0}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">quarantined sensors</div>
                <div className="mt-1 font-mono text-lg text-forge-text">{homeostasis?.quarantined_sensors?.length || 0}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                <div className="text-[10px] text-forge-muted">blocked actuators</div>
                <div className="mt-1 font-mono text-lg text-forge-text">{homeostasis?.blocked_actuators?.length || 0}</div>
              </div>
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_auto]">
              <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3 text-[10px] text-forge-muted">
                {homeostasis?.last_reason || 'Homeostatic range has not been evaluated yet.'}
                {!!homeostasis?.recommended_responses?.length && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {homeostasis.recommended_responses.map(response => (
                      <span key={response} className="rounded border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-amber-100">
                        {response}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <button
                onClick={runImmuneResponse}
                disabled={busy}
                className="rounded-lg border border-red-400/40 bg-red-500/10 px-3 py-2 text-sm text-red-100 hover:bg-red-500/20 disabled:opacity-40"
              >
                Run immune response
              </button>
            </div>
          </section>

          <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">Living Systems Stack</div>
                <div className="text-[10px] text-forge-muted">Reproduction, ecology, social contracts, sleep, identity, tools, and deployment boundaries.</div>
              </div>
              <div className="rounded border border-forge-border px-2 py-1 text-[10px] text-forge-muted">
                {livingSystems?.version || 'organism-living-systems-v1'}
              </div>
            </div>
            <div className="grid gap-3 lg:grid-cols-3">
              <LivingSystemCard title="Reproduction And Lineage" version={livingSystems?.lineage?.version}>
                {livingSystems?.lineage?.children?.length || 0} children · fitness {Math.round((livingSystems?.lineage?.fitness?.score || 0) * 100)}%
              </LivingSystemCard>
              <LivingSystemCard title="Ecology And Resource Competition" version={livingSystems?.ecology?.version}>
                {livingSystems?.ecology?.population || 0} organisms · pressure {Math.round((livingSystems?.ecology?.resource_pressure || 0) * 100)}%
              </LivingSystemCard>
              <LivingSystemCard title="Social Contracts" version={livingSystems?.social_contracts?.version}>
                {livingSystems?.social_contracts?.promises?.length || 0} promises · {livingSystems?.social_contracts?.known_peers?.length || 0} peers
              </LivingSystemCard>
              <LivingSystemCard title="Society Roles And Culture" version={livingSystems?.society_culture?.version}>
                {livingSystems?.society_culture?.role?.role || 'builder'} · {(livingSystems?.society_culture?.culture?.norms || []).length} norms
              </LivingSystemCard>
              <LivingSystemCard title="Task Economy" version={livingSystems?.task_economy?.version}>
                {(livingSystems?.task_economy?.funded_tasks || []).length} funded · reserve {Math.round((livingSystems?.task_economy?.budgets?.reserve || 0) * 100)}%
              </LivingSystemCard>
              <LivingSystemCard title="World Sandbox" version={livingSystems?.world_sandbox?.version}>
                hazard {Math.round((livingSystems?.world_sandbox?.hazard_index || 0) * 100)}% · {(livingSystems?.world_sandbox?.rehearsals || []).length} rehearsals
              </LivingSystemCard>
              <LivingSystemCard title="Sleep Consolidation" version={livingSystems?.sleep?.version}>
                {livingSystems?.sleep?.recent?.length || 0} sleep memories recorded
              </LivingSystemCard>
              <LivingSystemCard title="Identity Continuity" version={livingSystems?.identity?.version}>
                {livingSystems?.identity?.memory_count || 0} memories · {livingSystems?.identity?.parents?.length || 0} parents
              </LivingSystemCard>
              <LivingSystemCard title="Tool Marketplace" version={livingSystems?.tool_marketplace?.version}>
                {livingSystems?.tool_marketplace?.tools?.length || 0} tools available
              </LivingSystemCard>
              <LivingSystemCard title="Deployment Boundaries" version={livingSystems?.deployment_boundaries?.version}>
                {livingSystems?.deployment_boundaries?.ready ? 'ready' : 'not ready'} · {livingSystems?.deployment_boundaries?.boundary_checks?.filter(item => item.passed).length || 0}/{livingSystems?.deployment_boundaries?.boundary_checks?.length || 0} checks
              </LivingSystemCard>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                onClick={reproduceOrganism}
                disabled={busy || !livingSystems?.lineage?.fitness?.can_reproduce}
                className="rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100 hover:bg-emerald-500/20 disabled:opacity-40"
              >
                Reproduce
              </button>
              <button
                onClick={consolidateSleep}
                disabled={busy}
                className="rounded-lg border border-indigo-400/40 bg-indigo-500/10 px-3 py-2 text-sm text-indigo-100 hover:bg-indigo-500/20 disabled:opacity-40"
              >
                Consolidate sleep
              </button>
              <button
                onClick={tickDevelopment}
                disabled={busy}
                className="rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/20 disabled:opacity-40"
              >
                Development tick
              </button>
            </div>
          </section>

          <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">Genesis Life Engine</div>
                <div className="text-[10px] text-forge-muted">Environment, pressure, development, functional affect, layered memory, organ growth, mutation, mortality, and self-continuity.</div>
              </div>
              <div className="rounded border border-forge-border px-2 py-1 text-[10px] text-forge-muted">
                {lifeEngine?.version || 'genesis-life-engine-v1'}
              </div>
            </div>
            <div className="grid gap-3 lg:grid-cols-3">
              <LivingSystemCard title="Real Environment" version={lifeEngine?.environment?.version}>
                {lifeEngine?.environment?.events?.length || 0} events · {lifeEngine?.environment?.opportunities?.length || 0} opportunities
              </LivingSystemCard>
              <LivingSystemCard title="Survival Pressure" version={lifeEngine?.survival_pressure?.version}>
                {lifeEngine?.survival_pressure?.dominant?.name || 'none'} · {lifeEngine?.survival_pressure?.policy || 'act_carefully'}
              </LivingSystemCard>
              <LivingSystemCard title="Developmental Stage" version={lifeEngine?.development?.version}>
                {lifeEngine?.development?.stage || 'infant'} · {lifeEngine?.development?.autonomy || 'observe_only'}
              </LivingSystemCard>
              <LivingSystemCard title="Functional Affect" version={lifeEngine?.affect?.version}>
                {lifeEngine?.affect?.dominant?.name || 'confidence'} · {Math.round((lifeEngine?.affect?.dominant?.intensity || 0) * 100)}%
              </LivingSystemCard>
              <LivingSystemCard title="Temperament" version={lifeEngine?.temperament?.version}>
                {lifeEngine?.temperament?.archetype || 'careful explorer'} · {lifeEngine?.temperament?.decision_bias?.style || 'persist steadily'}
              </LivingSystemCard>
              <LivingSystemCard title="Goal Refinement" version={lifeEngine?.goal_refinement?.version}>
                {lifeEngine?.goal_refinement?.recommendation || 'monitor_current_goal'} · {lifeEngine?.goal_refinement?.review_gate?.can_auto_apply ? 'auto-apply' : 'review required'}
              </LivingSystemCard>
              <LivingSystemCard title="Society Culture" version={lifeEngine?.society_culture?.version}>
                {lifeEngine?.society_culture?.role?.role || 'builder'} · {lifeEngine?.society_culture?.culture?.motto || 'bounded autonomy'}
              </LivingSystemCard>
              <LivingSystemCard title="Task Economy" version={lifeEngine?.task_economy?.version}>
                spendable energy {Math.round((lifeEngine?.task_economy?.budgets?.spendable_energy || 0) * 100)}% · {(lifeEngine?.task_economy?.funded_tasks || []).length} funded
              </LivingSystemCard>
              <LivingSystemCard title="World Sandbox" version={lifeEngine?.world_sandbox?.version}>
                {lifeEngine?.world_sandbox?.hazards?.[0]?.name || 'no top hazard'} · {Math.round((lifeEngine?.world_sandbox?.hazard_index || 0) * 100)}%
              </LivingSystemCard>
              <LivingSystemCard title="Layered Memory" version={lifeEngine?.layered_memory?.version}>
                {(lifeEngine?.layered_memory?.working?.length || 0)} working · {(lifeEngine?.layered_memory?.semantic?.length || 0)} semantic
              </LivingSystemCard>
              <LivingSystemCard title="Organ Growth" version={lifeEngine?.organ_growth?.version}>
                {lifeEngine?.organ_growth?.growth_plan?.length || 0} growth recommendations
              </LivingSystemCard>
              <LivingSystemCard title="Mutation Strategy" version={lifeEngine?.mutation_strategy?.version}>
                {lifeEngine?.mutation_strategy?.allowed_mutations?.join(', ') || 'minimal'}
              </LivingSystemCard>
              <LivingSystemCard title="Mortality And Legacy" version={lifeEngine?.mortality_legacy?.version}>
                {lifeEngine?.mortality_legacy?.status || 'alive'} · {(lifeEngine?.mortality_legacy?.legacy_packet?.lessons?.length || 0)} lessons
              </LivingSystemCard>
              <LivingSystemCard title="Persistent Self" version={lifeEngine?.persistent_self?.version}>
                {lifeEngine?.persistent_self?.what_i_am_becoming || 'building continuity'}
              </LivingSystemCard>
            </div>
          </section>

          <section className="mb-4 flex flex-wrap gap-2">
            <button
              onClick={tick}
              disabled={busy}
              className="rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
            >
              Tick nervous system
            </button>
            <button
              onClick={runAutonomyCycle}
              disabled={busy}
              className="rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/20 px-3 py-2 text-sm text-fuchsia-100 hover:bg-fuchsia-500/30 disabled:opacity-40"
            >
              Run autonomy cycle
            </button>
            <button
              onClick={load}
              disabled={busy}
              className="rounded-lg border border-forge-border bg-forge-panel/60 px-3 py-2 text-sm text-forge-text hover:bg-forge-border/40 disabled:opacity-40"
            >
              Refresh
            </button>
          </section>

          <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">Autonomous Body Map</div>
                <div className="text-[10px] text-forge-muted">Sensors define what the organism can feel. Actuators define what it can safely do.</div>
              </div>
              <div className="rounded border border-forge-border px-2 py-1 text-[10px] text-forge-muted">
                {body?.summary?.alive_sensors || 0}/{body?.summary?.sensors || 0} sensors alive
              </div>
            </div>
            <div className="grid gap-3 lg:grid-cols-3">
              <BodyCard title="Sensors" items={body?.sensors} empty="No sensors attached yet." />
              <BodyCard title="Actuators" items={body?.actuators} empty="No actuators registered." />
              <div className="rounded-xl border border-forge-border bg-forge-panel/20 p-4">
                <div className="mb-3 text-xs font-medium text-forge-text">Sensor Recommendations</div>
                <div className="space-y-2">
                  {(body?.recommendations || []).map(rec => (
                    <div key={rec.id} className="rounded-lg border border-forge-border bg-forge-bg/40 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-xs font-medium text-forge-text">{rec.name}</div>
                          <div className="mt-1 text-[10px] text-forge-muted">{rec.reason}</div>
                        </div>
                        <button
                          onClick={() => attachRecommendedSensor(rec.id)}
                          disabled={busy || rec.approval_required}
                          className="shrink-0 rounded border border-cyan-400/40 bg-cyan-500/10 px-2 py-1 text-[10px] text-cyan-100 hover:bg-cyan-500/20 disabled:opacity-40"
                        >
                          Attach
                        </button>
                      </div>
                    </div>
                  ))}
                  {!(body?.recommendations || []).length && (
                    <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3 text-xs text-forge-muted">
                      No body recommendations right now.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </section>

          <section className="mb-4 grid gap-3 lg:grid-cols-2">
            <div>
              <div className="mb-2 text-xs font-medium text-forge-text">Active Needs</div>
              <div className="space-y-2">
                {needs.map(need => <NeedCard key={need.id} need={need} />)}
                {!needs.length && (
                  <div className="rounded-xl border border-forge-border bg-forge-panel/30 p-4 text-xs text-forge-muted">
                    No urgent needs. The organism is internally stable.
                  </div>
                )}
              </div>
            </div>
            <div>
              <div className="mb-2 text-xs font-medium text-forge-text">Autonomous Intentions</div>
              <div className="space-y-2">
                {intentions.map(intention => (
                  <IntentionRow
                    key={intention.id}
                    intention={intention}
                    onComplete={completeIntention}
                    busy={busy}
                  />
                ))}
                {!intentions.length && (
                  <div className="rounded-xl border border-forge-border bg-forge-panel/30 p-4 text-xs text-forge-muted">
                    No queued intentions yet. Tick the nervous system to derive one from organism needs.
                  </div>
                )}
              </div>
            </div>
          </section>

          <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">Embodied Autonomy Loop</div>
                <div className="text-[10px] text-forge-muted">Need → intention → safe action → result → reflection.</div>
              </div>
              <div className="rounded border border-forge-border px-2 py-1 text-[10px] text-forge-muted">
                {cycles.length} cycles
              </div>
            </div>
            {lastCycle && (
              <div className="mb-3 rounded-lg border border-cyan-400/30 bg-cyan-400/10 p-3 text-[10px] text-cyan-100">
                Last cycle: {lastCycle.status} · {lastCycle.action}
              </div>
            )}
            <div className="space-y-2">
              {cycles.slice().reverse().slice(0, 6).map(cycle => <CycleRow key={cycle.id} cycle={cycle} />)}
              {!cycles.length && (
                <div className="rounded-lg border border-forge-border bg-forge-bg/40 p-3 text-xs text-forge-muted">
                  No autonomy cycles yet. Run one to let the organism act on a safe queued intention.
                </div>
              )}
            </div>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <JsonBlock title="Drives" value={state?.drives} />
            <JsonBlock title="Vitals" value={state?.vitals} />
            <JsonBlock title="Recent Reflections" value={state?.reflections} />
            <JsonBlock title="Autonomy Cycles" value={cycles} />
            <JsonBlock title="Body Map" value={body} />
            <JsonBlock title="Metabolism" value={metabolism} />
            <JsonBlock title="Homeostasis" value={homeostasis} />
            <JsonBlock title="Living Systems" value={livingSystems} />
            <JsonBlock title="Life Engine" value={lifeEngine} />
            <JsonBlock title="Selection" value={selection} />
            <JsonBlock title="Temperament" value={temperament} />
            <JsonBlock title="Goal Refinement" value={goalRefinement} />
            <JsonBlock title="Society Culture" value={societyCulture} />
            <JsonBlock title="Task Economy" value={taskEconomy} />
            <JsonBlock title="World Sandbox" value={worldSandbox} />
            <JsonBlock title="Latest Tick Event" value={latestTick} />
          </section>
        </>
      )}
    </div>
  )
}
