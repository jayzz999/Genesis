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

function GrantPill({ value }) {
  const classes = {
    active: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    revoked: 'border-red-500/30 bg-red-500/10 text-red-300',
    expired: 'border-zinc-500/30 bg-zinc-500/10 text-zinc-300',
    exhausted: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  }
  return (
    <span className={`rounded border px-2 py-0.5 text-[10px] ${classes[value] || classes.active}`}>
      {value || 'active'}
    </span>
  )
}

function GrantList({ grants, selectedId, onSelect }) {
  return (
    <div className="space-y-2">
      {grants.length ? grants.map(grant => (
        <button
          key={grant.id}
          onClick={() => onSelect(grant)}
          className={`w-full rounded-lg border p-3 text-left transition-colors ${
            selectedId === grant.id
              ? 'border-purple-400/60 bg-purple-500/15'
              : 'border-forge-border bg-forge-panel/40 hover:bg-forge-border/30'
          }`}
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-mono text-[10px] text-forge-muted">{grant.id}</span>
            <GrantPill value={grant.status} />
          </div>
          <div className="text-xs text-forge-text">{grant.action_type}</div>
          <div className="mt-2 flex items-center justify-between gap-3 text-[10px] text-forge-muted">
            <span className="truncate">scope {grant.scope}</span>
            <span>{grant.uses}/{grant.max_uses} uses</span>
          </div>
        </button>
      )) : (
        <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
          No permission grants yet.
        </div>
      )}
    </div>
  )
}

export default function PermissionPanel({ eventLog }) {
  const [grants, setGrants] = useState([])
  const [summary, setSummary] = useState(null)
  const [activeGrant, setActiveGrant] = useState(null)
  const [permission, setPermission] = useState('external_api')
  const [actionType, setActionType] = useState('external_api')
  const [scope, setScope] = useState('future_external_system')
  const [actor, setActor] = useState('permissioned_tool')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const statusText = useMemo(() => {
    if (busy) return 'working'
    if (latestEvent?.type?.startsWith('permission.')) return latestEvent.type.replace('permission.', '')
    return summary?.grants ? `${summary.grants.active} active` : 'ready'
  }, [busy, latestEvent, summary])

  const loadGrants = async () => {
    try {
      const data = await apiRequest('/api/genesis/permissions/grants?limit=40')
      setGrants(data.grants || [])
      setSummary(data.summary || null)
      if (!activeGrant && data.grants?.[0]) setActiveGrant(data.grants[0])
      if (activeGrant) {
        const updated = data.grants?.find(item => item.id === activeGrant.id)
        if (updated) setActiveGrant(updated)
      }
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load permission grants')
    }
  }

  useEffect(() => {
    loadGrants()
    const t = setInterval(loadGrants, 5000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (latestEvent?.type?.startsWith('permission.') || latestEvent?.type?.startsWith('approval.')) {
      loadGrants()
    }
  }, [latestEvent])

  const mintDemoGrant = async () => {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const created = await apiRequest('/api/genesis/approvals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'Scoped connector grant',
          action_type: actionType,
          reason: 'Mint a scoped grant so a protected tool can prove permission checks.',
          requested_by: 'permission_panel',
          source: 'permissions',
          risk_level: 'high',
          payload: { target: scope, operation: 'dry_run_permissioned_action' },
          permissions: [permission, 'human_approval'],
          expires_in_minutes: 1440,
        }),
      })
      const approved = await apiRequest(`/api/genesis/approvals/${created.approval.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewed_by: 'human', note: 'Approved to mint a scoped simulation grant.' }),
      })
      const executed = await apiRequest(`/api/genesis/approvals/${approved.approval.id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ executed_by: 'permission_gate', grant_ttl_minutes: 60, grant_max_uses: 10 }),
      })
      const grant = executed.approval.execution_result.permission_grant
      setActiveGrant(grant)
      setResult({ ok: true, message: 'Scoped permission grant minted.', grant })
      await loadGrants()
    } catch (e) {
      setError(e.message || 'Failed to mint grant')
    } finally {
      setBusy(false)
    }
  }

  const simulateAction = async () => {
    if (!activeGrant) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/permissions/simulate-action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grant_id: activeGrant.id,
          permission,
          action_type: actionType,
          scope,
          actor,
          payload: { dry_run: true, checked_at: new Date().toISOString() },
        }),
      })
      setResult(data)
      setActiveGrant(data.grant)
      await loadGrants()
    } catch (e) {
      setError(e.message || 'Permission simulation failed')
    } finally {
      setBusy(false)
    }
  }

  const revokeGrant = async () => {
    if (!activeGrant) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest(`/api/genesis/permissions/grants/${activeGrant.id}/revoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revoked_by: 'human', note: 'Revoked from permissions panel.' }),
      })
      setActiveGrant(data.grant)
      setResult({ ok: true, message: 'Grant revoked.', grant: data.grant })
      await loadGrants()
    } catch (e) {
      setError(e.message || 'Failed to revoke grant')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Scoped Permission Grants</h3>
          <p className="text-[10px] text-forge-muted">
            Approved requests mint short-lived grants. Protected tools must validate permission, action, scope, and remaining uses.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">permission gate</div>
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
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs text-forge-muted">
                Permission
                <select
                  value={permission}
                  onChange={e => setPermission(e.target.value)}
                  className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
                >
                  <option value="external_api">external_api</option>
                  <option value="send_message">send_message</option>
                  <option value="deploy_change">deploy_change</option>
                  <option value="file_upload">file_upload</option>
                  <option value="browser_submit">browser_submit</option>
                </select>
              </label>
              <label className="block text-xs text-forge-muted">
                Action type
                <input
                  value={actionType}
                  onChange={e => setActionType(e.target.value)}
                  className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
                />
              </label>
            </div>

            <label className="mt-3 block text-xs text-forge-muted">Scope</label>
            <input
              value={scope}
              onChange={e => setScope(e.target.value)}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <label className="mt-3 block text-xs text-forge-muted">Actor</label>
            <input
              value={actor}
              onChange={e => setActor(e.target.value)}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                onClick={mintDemoGrant}
                disabled={busy}
                className="rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-xs text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
              >
                Mint scoped grant
              </button>
              <button
                onClick={simulateAction}
                disabled={busy || !activeGrant}
                className="rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-3 py-2 text-xs text-emerald-100 hover:bg-emerald-500/30 disabled:opacity-40"
              >
                Run protected simulation
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs font-medium text-forge-text">Permission grants</div>
              <div className="font-mono text-[10px] text-forge-muted">{grants.length}</div>
            </div>
            <GrantList grants={grants} selectedId={activeGrant?.id} onSelect={setActiveGrant} />
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[10px] text-forge-muted">{activeGrant?.id || 'no grant selected'}</div>
                <h4 className="text-base font-medium text-forge-text">{activeGrant?.action_type || 'Grant detail'}</h4>
              </div>
              <GrantPill value={activeGrant?.status} />
            </div>

            {activeGrant ? (
              <>
                <div className="grid gap-3 md:grid-cols-4">
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">scope</div>
                    <div className="truncate font-mono text-sm text-forge-text">{activeGrant.scope}</div>
                  </div>
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">uses</div>
                    <div className="font-mono text-lg text-forge-text">{activeGrant.uses}/{activeGrant.max_uses}</div>
                  </div>
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">risk</div>
                    <div className="font-mono text-lg text-forge-text">{activeGrant.risk_level}</div>
                  </div>
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="text-[10px] text-forge-muted">approval</div>
                    <div className="truncate font-mono text-sm text-forge-text">{activeGrant.approval_id}</div>
                  </div>
                </div>

                <div className="mt-4">
                  <div className="mb-2 text-xs font-medium text-forge-text">Granted permissions</div>
                  <div className="flex flex-wrap gap-2">
                    {(activeGrant.permissions || []).map(item => (
                      <span key={item} className="rounded border border-forge-border bg-forge-bg/60 px-2 py-1 font-mono text-[10px] text-forge-muted">
                        {item}
                      </span>
                    ))}
                  </div>
                </div>

                <button
                  onClick={revokeGrant}
                  disabled={busy || activeGrant.status !== 'active'}
                  className="mt-4 rounded-lg border border-red-400/40 bg-red-500/20 px-3 py-2 text-xs text-red-100 hover:bg-red-500/30 disabled:opacity-40"
                >
                  Revoke grant
                </button>
              </>
            ) : (
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                Mint or select a grant to inspect runtime permission state.
              </div>
            )}
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Last result</div>
              <pre className="max-h-96 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
                {JSON.stringify(result || {}, null, 2)}
              </pre>
            </div>
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Grant audit</div>
              <div className="space-y-2">
                {(activeGrant?.audit || []).slice().reverse().map((item, index) => (
                  <div key={`${item.at}-${index}`} className="rounded border border-forge-border bg-forge-panel/40 p-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] text-cyan-300">{item.action}</span>
                      <span className="font-mono text-[10px] text-forge-muted">{item.actor}</span>
                    </div>
                    <div className="mt-1 text-[10px] text-forge-muted">{item.note}</div>
                  </div>
                ))}
                {!activeGrant?.audit?.length && (
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                    No grant audit events yet.
                  </div>
                )}
              </div>
            </div>
          </section>
        </div>
      </section>
    </div>
  )
}
