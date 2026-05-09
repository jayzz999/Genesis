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

function IntegrityPill({ ok }) {
  return (
    <span className={`rounded border px-2 py-0.5 text-[10px] ${
      ok
        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
        : 'border-red-500/30 bg-red-500/10 text-red-300'
    }`}>
      {ok ? 'verified' : 'mismatch'}
    </span>
  )
}

export default function ApprovalIntegrityPanel({ eventLog }) {
  const [approval, setApproval] = useState(null)
  const [integrity, setIntegrity] = useState(null)
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const statusText = useMemo(() => {
    if (busy) return 'working'
    if (latestEvent?.type === 'approval.integrity_verified') return 'verified'
    if (integrity) return integrity.ok ? 'verified' : 'mismatch'
    return 'ready'
  }, [busy, integrity, latestEvent])

  const loadReport = async () => {
    try {
      const data = await apiRequest('/api/genesis/approvals/integrity?limit=50')
      setReport(data)
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load integrity report')
    }
  }

  useEffect(() => {
    loadReport()
  }, [])

  const createStampedApproval = async () => {
    setBusy(true)
    setError(null)
    try {
      const created = await apiRequest('/api/genesis/approvals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'Tamper-evident approval record',
          action_type: 'file_upload',
          reason: 'Verify that approval records carry a deterministic integrity hash.',
          requested_by: 'integrity_panel',
          source: 'integrity-ledger',
          risk_level: 'medium',
          payload: {
            target: 'local-artifacts',
            artifact: 'agi12-integrity-proof.txt',
          },
          permissions: ['file_upload', 'human_approval'],
          expires_in_minutes: 1440,
        }),
      })
      setApproval(created.approval)
      const verified = await apiRequest(`/api/genesis/approvals/${created.approval.id}/integrity`)
      setIntegrity(verified.integrity)
      await loadReport()
    } catch (e) {
      setError(e.message || 'Failed to create stamped approval')
    } finally {
      setBusy(false)
    }
  }

  const approveAndVerify = async () => {
    if (!approval) return
    setBusy(true)
    setError(null)
    try {
      const approved = await apiRequest(`/api/genesis/approvals/${approval.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewed_by: 'human', note: 'Approved after integrity review.' }),
      })
      setApproval(approved.approval)
      const verified = await apiRequest(`/api/genesis/approvals/${approved.approval.id}/integrity`)
      setIntegrity(verified.integrity)
      await loadReport()
    } catch (e) {
      setError(e.message || 'Failed to approve and verify')
    } finally {
      setBusy(false)
    }
  }

  const verifyCurrent = async () => {
    if (!approval) return
    setBusy(true)
    setError(null)
    try {
      const verified = await apiRequest(`/api/genesis/approvals/${approval.id}/integrity`)
      setApproval(verified.approval)
      setIntegrity(verified.integrity)
      await loadReport()
    } catch (e) {
      setError(e.message || 'Failed to verify approval integrity')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Tamper-Evident Approval Ledger</h3>
          <p className="text-[10px] text-forge-muted">
            Approval and grant records are stamped with deterministic integrity hashes so out-of-band edits can be detected.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">integrity</div>
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
              onClick={createStampedApproval}
              disabled={busy}
              className="w-full rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
            >
              Create stamped approval
            </button>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                onClick={approveAndVerify}
                disabled={busy || !approval || approval.status !== 'pending'}
                className="rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-3 py-2 text-xs text-emerald-100 hover:bg-emerald-500/30 disabled:opacity-40"
              >
                Approve and verify
              </button>
              <button
                onClick={verifyCurrent}
                disabled={busy || !approval}
                className="rounded-lg border border-purple-400/40 bg-purple-500/20 px-3 py-2 text-xs text-purple-100 hover:bg-purple-500/30 disabled:opacity-40"
              >
                Verify current record
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[10px] text-forge-muted">{approval?.id || 'no approval selected'}</div>
                <h4 className="text-base font-medium text-forge-text">{approval?.title || 'Integrity detail'}</h4>
              </div>
              <IntegrityPill ok={integrity?.ok} />
            </div>
            {integrity ? (
              <div className="space-y-3">
                <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                  <div className="text-[10px] text-forge-muted">stored hash</div>
                  <div className="break-all font-mono text-xs text-forge-text">{integrity.stored_hash}</div>
                </div>
                <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                  <div className="text-[10px] text-forge-muted">expected hash</div>
                  <div className="break-all font-mono text-xs text-forge-text">{integrity.expected_hash}</div>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">algorithm</div>
                    <div className="font-mono text-sm text-forge-text">{integrity.algorithm}</div>
                  </div>
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">reason</div>
                    <div className="font-mono text-sm text-forge-text">{integrity.reason}</div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                Create a stamped approval to verify its integrity hash.
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-xs font-medium text-forge-text">Ledger report</div>
              <IntegrityPill ok={report?.ok} />
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                <div className="text-[10px] text-forge-muted">checked</div>
                <div className="font-mono text-lg text-forge-text">{report?.checked || 0}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                <div className="text-[10px] text-forge-muted">approvals</div>
                <div className="font-mono text-lg text-forge-text">{report?.summary?.approvals_checked || 0}</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                <div className="text-[10px] text-forge-muted">failures</div>
                <div className="font-mono text-lg text-forge-text">{report?.summary?.failure_count || 0}</div>
              </div>
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Approval integrity</div>
              <pre className="max-h-96 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
                {JSON.stringify(integrity || {}, null, 2)}
              </pre>
            </div>
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Record stamp</div>
              <pre className="max-h-96 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
                {JSON.stringify(approval?.integrity || {}, null, 2)}
              </pre>
            </div>
          </section>

          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 text-xs font-medium text-forge-text">Full ledger report</div>
            <pre className="max-h-96 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
              {JSON.stringify(report || {}, null, 2)}
            </pre>
          </section>
        </div>
      </section>
    </div>
  )
}
