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

function StatePill({ value }) {
  const colors = {
    approved: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    pending: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
    break_glass: 'border-red-500/30 bg-red-500/10 text-red-300',
  }
  return (
    <span className={`rounded border px-2 py-0.5 text-[10px] ${colors[value] || 'border-forge-border bg-forge-panel/50 text-forge-muted'}`}>
      {value || 'none'}
    </span>
  )
}

export default function ApprovalGovernancePanel({ eventLog }) {
  const [approval, setApproval] = useState(null)
  const [summary, setSummary] = useState(null)
  const [breakGlassApproval, setBreakGlassApproval] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const controls = approval?.approval_controls || {}
  const breakGlassGrant = breakGlassApproval?.execution_result?.permission_grant
  const statusText = useMemo(() => {
    if (busy) return 'working'
    if (latestEvent?.type === 'approval.break_glass') return 'break-glass'
    if (controls.quorum_satisfied) return 'quorum met'
    if (approval) return 'waiting'
    return 'ready'
  }, [approval, busy, controls.quorum_satisfied, latestEvent])

  const loadSummary = async () => {
    try {
      const data = await apiRequest('/api/genesis/approvals?limit=20')
      setSummary(data.summary)
    } catch {}
  }

  useEffect(() => {
    loadSummary()
  }, [])

  const createCritical = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/approvals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'Genesis critical dual-control approval',
          action_type: 'deploy_change',
          reason: 'Verify critical actions require two distinct human reviewers before execution.',
          requested_by: 'governance_panel',
          source: 'approval-governance',
          risk_level: 'critical',
          required_approvals: 2,
          payload: {
            target: 'production-runtime',
            change: 'simulated-policy-rollout',
          },
          permissions: ['deploy_change', 'human_approval'],
          expires_in_minutes: 1440,
        }),
      })
      setApproval(data.approval)
      await loadSummary()
    } catch (e) {
      setError(e.message || 'Failed to create critical approval')
    } finally {
      setBusy(false)
    }
  }

  const addReview = async (reviewer) => {
    if (!approval) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/approvals/${approval.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reviewed_by: reviewer,
          note: `${reviewer} reviewed Genesis quorum controls.`,
        }),
      })
      setApproval(data.approval)
      await loadSummary()
    } catch (e) {
      setError(e.message || 'Failed to add review')
    } finally {
      setBusy(false)
    }
  }

  const executeApproved = async () => {
    if (!approval) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/approvals/${approval.id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          executed_by: 'governance_gate',
          grant_ttl_minutes: 30,
          grant_max_uses: 2,
        }),
      })
      setApproval(data.approval)
      await loadSummary()
    } catch (e) {
      setError(e.message || 'Execution blocked by governance')
    } finally {
      setBusy(false)
    }
  }

  const runBreakGlass = async () => {
    setBusy(true)
    setError(null)
    try {
      const created = await apiRequest('/api/genesis/approvals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'Genesis emergency break-glass approval',
          action_type: 'external_api',
          reason: 'Verify emergency access is limited, audited, and one-use only.',
          requested_by: 'governance_panel',
          source: 'break-glass',
          risk_level: 'critical',
          payload: {
            target: 'incident-response-api',
            incident: 'simulated-prod-outage',
          },
          permissions: ['external_api', 'human_approval'],
          expires_in_minutes: 60,
        }),
      })
      const data = await apiRequest(`/api/genesis/approvals/${created.approval.id}/break-glass`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          invoked_by: 'incident_commander',
          justification: 'Simulated outage response requires immediate one-use access while quorum review continues.',
          grant_ttl_minutes: 15,
        }),
      })
      setBreakGlassApproval(data.approval)
      await loadSummary()
    } catch (e) {
      setError(e.message || 'Break-glass failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Genesis Approval Governance</h3>
          <p className="text-[10px] text-forge-muted">
            Critical permissions require distinct-reviewer quorum, while emergency access is one-use, short-lived, and fully audited.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">governance</div>
          <div className="text-sm font-mono text-forge-text">{statusText}</div>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <section className="grid gap-4 xl:grid-cols-[420px_1fr]">
        <div className="space-y-4">
          <div className="rounded-xl border border-forge-border p-4">
            <button
              onClick={createCritical}
              disabled={busy}
              className="w-full rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
            >
              Create critical quorum request
            </button>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                onClick={() => addReview('reviewer_alpha')}
                disabled={busy || !approval || approval.status !== 'pending'}
                className="rounded-lg border border-amber-400/40 bg-amber-500/20 px-3 py-2 text-xs text-amber-100 hover:bg-amber-500/30 disabled:opacity-40"
              >
                Review as alpha
              </button>
              <button
                onClick={() => addReview('reviewer_beta')}
                disabled={busy || !approval || approval.status !== 'pending'}
                className="rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-3 py-2 text-xs text-emerald-100 hover:bg-emerald-500/30 disabled:opacity-40"
              >
                Review as beta
              </button>
            </div>
            <button
              onClick={executeApproved}
              disabled={busy || !approval || approval.status !== 'approved'}
              className="mt-2 w-full rounded-lg border border-purple-400/40 bg-purple-500/20 px-3 py-2 text-xs text-purple-100 hover:bg-purple-500/30 disabled:opacity-40"
            >
              Execute after quorum
            </button>
          </div>

          <div className="rounded-xl border border-red-500/30 p-4">
            <button
              onClick={runBreakGlass}
              disabled={busy}
              className="w-full rounded-lg border border-red-400/40 bg-red-500/20 px-3 py-2 text-sm text-red-100 hover:bg-red-500/30 disabled:opacity-40"
            >
              Run break-glass drill
            </button>
            <p className="mt-2 text-[10px] text-forge-muted">
              The drill creates a critical request and mints a simulated emergency grant with a 15 minute maximum TTL and one use.
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[10px] text-forge-muted">{approval?.id || 'no quorum request selected'}</div>
                <h4 className="text-base font-medium text-forge-text">{approval?.title || 'Quorum detail'}</h4>
              </div>
              <StatePill value={approval?.status} />
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                <div className="text-[10px] text-forge-muted">required</div>
                <div className="font-mono text-lg text-forge-text">{controls.required_approvals || 0}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                <div className="text-[10px] text-forge-muted">received</div>
                <div className="font-mono text-lg text-forge-text">{controls.received_approvals || 0}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                <div className="text-[10px] text-forge-muted">remaining</div>
                <div className="font-mono text-lg text-forge-text">{controls.remaining_approvals || 0}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                <div className="text-[10px] text-forge-muted">quorum</div>
                <div className="font-mono text-sm text-forge-text">{controls.quorum_satisfied ? 'met' : 'open'}</div>
              </div>
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Review ledger</div>
              <pre className="max-h-80 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
                {JSON.stringify(approval?.approval_reviews || [], null, 2)}
              </pre>
            </div>
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Break-glass grant</div>
              <pre className="max-h-80 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
                {JSON.stringify(breakGlassGrant || {}, null, 2)}
              </pre>
            </div>
          </section>

          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 text-xs font-medium text-forge-text">Governance summary</div>
            <pre className="max-h-80 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
              {JSON.stringify(summary?.governance || {}, null, 2)}
            </pre>
          </section>
        </div>
      </section>
    </div>
  )
}
