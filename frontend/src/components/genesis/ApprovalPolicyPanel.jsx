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

function VerdictPill({ value }) {
  const classes = {
    allowable: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    review_required: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
    handoff_required: 'border-red-500/30 bg-red-500/10 text-red-300',
    executed: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    approved: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300',
    pending: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  }
  return (
    <span className={`rounded border px-2 py-0.5 text-[10px] ${classes[value] || classes.review_required}`}>
      {value || 'review_required'}
    </span>
  )
}

export default function ApprovalPolicyPanel({ eventLog }) {
  const [approval, setApproval] = useState(null)
  const [policy, setPolicy] = useState(null)
  const [confirmationPhrase, setConfirmationPhrase] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const statusText = useMemo(() => {
    if (busy) return 'working'
    if (latestEvent?.type === 'approval.confirmed') return 'confirmed'
    if (approval?.status) return approval.status
    return 'ready'
  }, [approval, busy, latestEvent])

  const createPolicyRequest = async () => {
    setBusy(true)
    setError(null)
    setConfirmed(false)
    try {
      const created = await apiRequest('/api/genesis/approvals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'Strict local connector review',
          action_type: 'file_upload',
          reason: 'Evaluate a real local connector side effect with a replayable policy packet and strict human confirmation.',
          requested_by: 'policy_panel',
          source: 'policy-review',
          risk_level: 'high',
          payload: {
            target: 'local-artifacts',
            adapter_id: 'local_artifact_write',
            filename: 'agi11-policy-proof.txt',
          },
          permissions: ['file_upload', 'human_approval'],
          expires_in_minutes: 1440,
        }),
      })
      const policyData = await apiRequest(`/api/genesis/approvals/${created.approval.id}/policy`)
      setApproval(policyData.approval)
      setPolicy(policyData.policy)
      setConfirmationPhrase(policyData.policy.confirmation_phrase)
    } catch (e) {
      setError(e.message || 'Failed to create policy request')
    } finally {
      setBusy(false)
    }
  }

  const approve = async () => {
    if (!approval) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/approvals/${approval.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewed_by: 'human', note: 'Policy packet reviewed.' }),
      })
      setApproval(data.approval)
      const policyData = await apiRequest(`/api/genesis/approvals/${data.approval.id}/policy`)
      setPolicy(policyData.policy)
    } catch (e) {
      setError(e.message || 'Failed to approve request')
    } finally {
      setBusy(false)
    }
  }

  const confirmExecution = async () => {
    if (!approval || !policy) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/approvals/${approval.id}/confirm-execution`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          confirmed_by: 'human',
          confirmation_phrase: confirmationPhrase,
          note: 'Strict execution confirmation bound to evidence hash.',
        }),
      })
      setApproval(data.approval)
      setPolicy(data.policy)
      setConfirmed(true)
    } catch (e) {
      setError(e.message || 'Failed to confirm execution')
    } finally {
      setBusy(false)
    }
  }

  const executeStrict = async () => {
    if (!approval) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/approvals/${approval.id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          executed_by: 'policy_gate',
          grant_ttl_minutes: 60,
          grant_max_uses: 10,
          require_confirmation: true,
        }),
      })
      setApproval(data.approval)
      setPolicy(data.approval.policy_review)
    } catch (e) {
      setError(e.message || 'Strict execution failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Policy Review And Strict Confirmation</h3>
          <p className="text-[10px] text-forge-muted">
            Approval decisions carry a replayable policy packet, evidence hash, and exact execution confirmation phrase.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">policy gate</div>
          <div className="text-sm font-mono text-forge-text">{statusText}</div>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <section className="grid gap-4 xl:grid-cols-[410px_1fr]">
        <div className="space-y-4">
          <div className="rounded-xl border border-forge-border p-4">
            <button
              onClick={createPolicyRequest}
              disabled={busy}
              className="w-full rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
            >
              Create policy request
            </button>

            <div className="mt-4 grid grid-cols-2 gap-2">
              <button
                onClick={approve}
                disabled={busy || !approval || approval.status !== 'pending'}
                className="rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-3 py-2 text-xs text-emerald-100 hover:bg-emerald-500/30 disabled:opacity-40"
              >
                Approve packet
              </button>
              <button
                onClick={confirmExecution}
                disabled={busy || !approval || !policy || !['pending', 'approved'].includes(approval.status)}
                className="rounded-lg border border-amber-400/40 bg-amber-500/20 px-3 py-2 text-xs text-amber-100 hover:bg-amber-500/30 disabled:opacity-40"
              >
                Confirm execution
              </button>
            </div>

            <label className="mt-4 block text-xs text-forge-muted">Confirmation phrase</label>
            <input
              value={confirmationPhrase}
              onChange={e => setConfirmationPhrase(e.target.value)}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 font-mono text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <button
              onClick={executeStrict}
              disabled={busy || !approval || approval.status !== 'approved' || !confirmed}
              className="mt-3 w-full rounded-lg border border-purple-400/40 bg-purple-500/20 px-3 py-2 text-sm text-purple-100 hover:bg-purple-500/30 disabled:opacity-40"
            >
              Execute with strict confirmation
            </button>
          </div>

          <div className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[10px] text-forge-muted">{approval?.id || 'no approval selected'}</div>
                <h4 className="text-base font-medium text-forge-text">{approval?.title || 'Policy packet'}</h4>
              </div>
              <VerdictPill value={approval?.status || policy?.verdict} />
            </div>
            {policy ? (
              <div className="space-y-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">verdict</div>
                    <div className="font-mono text-sm text-forge-text">{policy.verdict}</div>
                  </div>
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">target</div>
                    <div className="truncate font-mono text-sm text-forge-text">{policy.target}</div>
                  </div>
                </div>
                <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                  <div className="text-[10px] text-forge-muted">evidence hash</div>
                  <div className="break-all font-mono text-xs text-forge-text">{policy.evidence_hash}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {(policy.required_confirmations || []).map(item => (
                    <span key={item} className="rounded border border-forge-border bg-forge-bg/60 px-2 py-1 font-mono text-[10px] text-forge-muted">
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                Create a request to generate a policy review packet.
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 text-xs font-medium text-forge-text">Policy reasons</div>
            <div className="space-y-2">
              {(policy?.reasons || []).map(reason => (
                <div key={reason} className="rounded border border-forge-border bg-forge-panel/40 p-2 font-mono text-xs text-forge-text">
                  {reason}
                </div>
              ))}
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Execution confirmation</div>
              <pre className="max-h-96 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
                {JSON.stringify(approval?.execution_confirmation || {}, null, 2)}
              </pre>
            </div>
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Execution result</div>
              <pre className="max-h-96 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
                {JSON.stringify(approval?.execution_result || {}, null, 2)}
              </pre>
            </div>
          </section>

          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 text-xs font-medium text-forge-text">Full policy packet</div>
            <pre className="max-h-96 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
              {JSON.stringify(policy || {}, null, 2)}
            </pre>
          </section>
        </div>
      </section>
    </div>
  )
}
