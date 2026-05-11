import React, { useCallback, useEffect, useMemo, useState } from 'react'

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

const DEFAULT_PAYLOAD = `{
  "operation": "dry_run_connector_call",
  "target": "future_external_system",
  "dry_run": true
}`

function StatusPill({ value }) {
  const classes = {
    pending: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
    approved: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300',
    executed: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    rejected: 'border-red-500/30 bg-red-500/10 text-red-300',
    expired: 'border-zinc-500/30 bg-zinc-500/10 text-zinc-300',
  }
  return (
    <span className={`rounded border px-2 py-0.5 text-[10px] ${classes[value] || classes.pending}`}>
      {value || 'pending'}
    </span>
  )
}

function ApprovalList({ approvals, selectedId, onSelect }) {
  return (
    <div className="space-y-2">
      {approvals.length ? approvals.map(approval => (
        <button
          type="button"
          data-testid={`approval-row-${approval.id}`}
          key={approval.id}
          onClick={() => onSelect(approval)}
          className={`w-full rounded-lg border p-3 text-left transition-colors ${
            selectedId === approval.id
              ? 'border-purple-400/60 bg-purple-500/15'
              : 'border-forge-border bg-forge-panel/40 hover:bg-forge-border/30'
          }`}
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-mono text-[10px] text-forge-muted">{approval.id}</span>
            <StatusPill value={approval.status} />
          </div>
          <div className="line-clamp-2 text-xs text-forge-text">{approval.title}</div>
          <div className="mt-2 flex items-center justify-between text-[10px] text-forge-muted">
            <span>{approval.action_type}</span>
            <span>{approval.risk_level} risk</span>
          </div>
        </button>
      )) : (
        <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
          No approval requests yet.
        </div>
      )}
    </div>
  )
}

function PermissionStrip({ permissions }) {
  return (
    <div className="flex flex-wrap gap-2">
      {(permissions || []).map(permission => (
        <span
          key={permission}
          className="rounded border border-forge-border bg-forge-bg/60 px-2 py-1 font-mono text-[10px] text-forge-muted"
        >
          {permission}
        </span>
      ))}
    </div>
  )
}

export default function ApprovalPanel({ eventLog }) {
  const [title, setTitle] = useState('Approve external connector experiment')
  const [actionType, setActionType] = useState('external_api')
  const [riskLevel, setRiskLevel] = useState('high')
  const [reason, setReason] = useState('Test a future connector path while preserving explicit human control.')
  const [permissionsText, setPermissionsText] = useState('external_api\nhuman_approval')
  const [payloadText, setPayloadText] = useState(DEFAULT_PAYLOAD)
  const [reviewer, setReviewer] = useState('human')
  const [reviewNote, setReviewNote] = useState('Approved for simulation only.')
  const [approvals, setApprovals] = useState([])
  const [summary, setSummary] = useState(null)
  const [activeApproval, setActiveApproval] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const statusText = useMemo(() => {
    if (busy) return 'working'
    if (latestEvent?.type?.startsWith('approval.')) return latestEvent.type.replace('approval.', '')
    return summary ? `${summary.pending} pending` : 'ready'
  }, [busy, latestEvent, summary])

  const loadApprovals = useCallback(async () => {
    try {
      const data = await apiRequest('/api/genesis/approvals?limit=40')
      setApprovals(data.approvals || [])
      setSummary(data.summary || null)
      setError(null)
      setActiveApproval(current => {
        if (current) {
          const updated = data.approvals?.find(item => item.id === current.id)
          if (updated) return updated
        }
        return data.approvals?.[0] || current || null
      })
    } catch (e) {
      setError(e.message || 'Failed to load approvals')
    }
  }, [])

  useEffect(() => {
    loadApprovals()
    const t = setInterval(loadApprovals, 5000)
    return () => clearInterval(t)
  }, [loadApprovals])

  useEffect(() => {
    if (latestEvent?.type?.startsWith('approval.')) {
      loadApprovals()
    }
  }, [latestEvent, loadApprovals])

  const createApproval = async () => {
    setBusy(true)
    setError(null)
    try {
      const payload = JSON.parse(payloadText || '{}')
      const data = await apiRequest('/api/genesis/approvals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          action_type: actionType,
          risk_level: riskLevel,
          reason,
          requested_by: 'human_console',
          source: 'approval-panel',
          payload,
          permissions: permissionsText.split('\n').map(s => s.trim()).filter(Boolean),
          expires_in_minutes: 1440,
        }),
      })
      setActiveApproval(data.approval)
      await loadApprovals()
    } catch (e) {
      setError(e.message || 'Failed to create approval')
    } finally {
      setBusy(false)
    }
  }

  const decide = async (action) => {
    if (!activeApproval) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/approvals/${activeApproval.id}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewed_by: reviewer, note: reviewNote }),
      })
      setActiveApproval(data.approval)
      setApprovals(prev => prev.map(item => item.id === data.approval.id ? data.approval : item))
      await loadApprovals()
    } catch (e) {
      setError(e.message || `Failed to ${action} request`)
    } finally {
      setBusy(false)
    }
  }

  const execute = async () => {
    if (!activeApproval) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/approvals/${activeApproval.id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ executed_by: 'genesis_approval_gate', grant_ttl_minutes: 60, grant_max_uses: 10 }),
      })
      setActiveApproval(data.approval)
      setApprovals(prev => prev.map(item => item.id === data.approval.id ? data.approval : item))
      await loadApprovals()
    } catch (e) {
      setError(e.message || 'Failed to execute approval')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Approval Queue</h3>
          <p className="text-[10px] text-forge-muted">
            Risky actions become auditable requests. Humans approve or reject them before execution.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">gate</div>
          <div className="text-sm font-mono text-forge-text">{statusText}</div>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <section className="grid gap-4 xl:grid-cols-[390px_1fr]">
        <div className="space-y-4">
          <div className="rounded-xl border border-forge-border p-4">
            <label className="block text-xs text-forge-muted">Request title</label>
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <div className="mt-3 grid grid-cols-2 gap-3">
              <label className="block text-xs text-forge-muted">
                Action type
                <select
                  value={actionType}
                  onChange={e => setActionType(e.target.value)}
                  className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
                >
                  <option value="external_api">external_api</option>
                  <option value="send_message">send_message</option>
                  <option value="deploy_change">deploy_change</option>
                  <option value="delete_data">delete_data</option>
                  <option value="browser_submit">browser_submit</option>
                </select>
              </label>
              <label className="block text-xs text-forge-muted">
                Risk
                <select
                  value={riskLevel}
                  onChange={e => setRiskLevel(e.target.value)}
                  className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
                >
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                  <option value="critical">critical</option>
                  <option value="low">low</option>
                </select>
              </label>
            </div>

            <label className="mt-3 block text-xs text-forge-muted">Reason</label>
            <textarea
              value={reason}
              onChange={e => setReason(e.target.value)}
              rows={4}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <label className="mt-3 block text-xs text-forge-muted">Permissions, one per line</label>
            <textarea
              value={permissionsText}
              onChange={e => setPermissionsText(e.target.value)}
              rows={3}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 font-mono text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <label className="mt-3 block text-xs text-forge-muted">Payload JSON</label>
            <textarea
              value={payloadText}
              onChange={e => setPayloadText(e.target.value)}
              rows={6}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 font-mono text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <button
              type="button"
              onClick={createApproval}
              disabled={busy || !title.trim() || !reason.trim()}
              className="mt-3 w-full rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? 'Working...' : 'Create approval request'}
            </button>
          </div>

          <div className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs font-medium text-forge-text">Approval queue</div>
              <div className="font-mono text-[10px] text-forge-muted">{approvals.length}</div>
            </div>
            <ApprovalList approvals={approvals} selectedId={activeApproval?.id} onSelect={setActiveApproval} />
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[10px] text-forge-muted">{activeApproval?.id || 'no approval selected'}</div>
                <h4 className="text-base font-medium text-forge-text">{activeApproval?.title || 'Approval detail'}</h4>
              </div>
              <StatusPill value={activeApproval?.status} />
            </div>

            {activeApproval ? (
              <>
                <p className="rounded-lg border border-forge-border bg-forge-panel/40 p-3 text-sm leading-relaxed text-forge-text">
                  {activeApproval.reason}
                </p>

                <div className="mt-3 grid gap-3 md:grid-cols-4">
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">risk</div>
                    <div className="font-mono text-lg text-forge-text">{activeApproval.risk_level}</div>
                  </div>
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">action</div>
                    <div className="font-mono text-sm text-forge-text">{activeApproval.action_type}</div>
                  </div>
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">reviewer</div>
                    <div className="font-mono text-sm text-forge-text">{activeApproval.reviewed_by || 'none'}</div>
                  </div>
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">executor</div>
                    <div className="font-mono text-sm text-forge-text">{activeApproval.safety_checks?.executor_mode}</div>
                  </div>
                </div>

                <div className="mt-4">
                  <div className="mb-2 text-xs font-medium text-forge-text">Permissions</div>
                  <PermissionStrip permissions={activeApproval.permissions} />
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <label className="block text-xs text-forge-muted">
                    Reviewer
                    <input
                      value={reviewer}
                      onChange={e => setReviewer(e.target.value)}
                      className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
                    />
                  </label>
                  <label className="block text-xs text-forge-muted">
                    Review note
                    <input
                      value={reviewNote}
                      onChange={e => setReviewNote(e.target.value)}
                      className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
                    />
                  </label>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    data-testid="approval-approve-button"
                    aria-label={`Approve ${activeApproval.id}`}
                    onClick={() => decide('approve')}
                    disabled={busy || activeApproval.status !== 'pending'}
                    className="rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-3 py-2 text-xs text-emerald-100 hover:bg-emerald-500/30 disabled:opacity-40"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    data-testid="approval-reject-button"
                    aria-label={`Reject ${activeApproval.id}`}
                    onClick={() => decide('reject')}
                    disabled={busy || !['pending', 'approved'].includes(activeApproval.status)}
                    className="rounded-lg border border-red-400/40 bg-red-500/20 px-3 py-2 text-xs text-red-100 hover:bg-red-500/30 disabled:opacity-40"
                  >
                    Reject
                  </button>
                  <button
                    type="button"
                    data-testid="approval-execute-button"
                    aria-label={`Execute ${activeApproval.id}`}
                    onClick={execute}
                    disabled={busy || activeApproval.status !== 'approved'}
                    className="rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-xs text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
                  >
                    Execute approved
                  </button>
                </div>
              </>
            ) : (
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                Create or select an approval request to review it.
              </div>
            )}
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Payload</div>
              <pre className="max-h-80 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
                {JSON.stringify(activeApproval?.payload || {}, null, 2)}
              </pre>
            </div>
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Audit</div>
              <div className="space-y-2">
                {(activeApproval?.audit || []).slice().reverse().map((item, index) => (
                  <div key={`${item.at}-${index}`} className="rounded border border-forge-border bg-forge-panel/40 p-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] text-cyan-300">{item.action}</span>
                      <span className="font-mono text-[10px] text-forge-muted">{item.actor}</span>
                    </div>
                    <div className="mt-1 text-[10px] text-forge-muted">{item.note}</div>
                  </div>
                ))}
                {!activeApproval?.audit?.length && (
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                    No audit events yet.
                  </div>
                )}
              </div>
            </div>
          </section>

          {activeApproval?.execution_result && (
            <section className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Execution result</div>
              <pre className="max-h-72 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
                {JSON.stringify(activeApproval.execution_result, null, 2)}
              </pre>
            </section>
          )}
        </div>
      </section>
    </div>
  )
}
