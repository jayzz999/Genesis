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

const DEFAULT_PAYLOAD = `{
  "method": "POST",
  "endpoint": "https://api.example.com/v1/events",
  "headers": {
    "Authorization": "Bearer set-real-token-in-payload-or-env"
  },
  "json": {
    "message": "Genesis permission-gated connector call"
  }
}`

function defaultPayloadFor(adapterId, scope) {
  if (adapterId === 'github_create_issue') {
    return JSON.stringify({
      title: 'Genesis approved issue',
      body: 'Created by Genesis after human approval and scoped permission validation.',
      labels: ['genesis']
    }, null, 2)
  }
  if (adapterId === 'github_issue_comment') {
    return JSON.stringify({
      issue_number: Number((scope || '').split('#')[1] || 1),
      body: 'Genesis approved comment after scoped permission validation.'
    }, null, 2)
  }
  if (adapterId === 'slack_webhook_message' || adapterId === 'send_message') {
    return JSON.stringify({
      text: 'Genesis approved connector message.',
      metadata: { source: 'genesis_connector_control_center' }
    }, null, 2)
  }
  if (adapterId === 'deploy_change') {
    return JSON.stringify({
      version: 'approved-build',
      change: 'Permission-gated deployment webhook trigger.',
      metadata: { source: 'genesis_connector_control_center' }
    }, null, 2)
  }
  if (adapterId === 'file_upload' || adapterId === 'local_artifact_write') {
    return JSON.stringify({
      filename: 'connector-proof.txt',
      content: 'Written by a real permission-gated Genesis connector.',
      metadata: { source: 'genesis_connector_control_center' }
    }, null, 2)
  }
  if (adapterId === 'browser_submit') {
    return JSON.stringify({
      url: 'https://example.com/form',
      form: 'approved-form',
      fields: {},
      submit: true
    }, null, 2)
  }
  return DEFAULT_PAYLOAD
}

function RunPill({ value }) {
  const classes = {
    complete: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    blocked: 'border-red-500/30 bg-red-500/10 text-red-300',
    failed: 'border-red-500/30 bg-red-500/10 text-red-300',
    pending: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  }
  return (
    <span className={`rounded border px-2 py-0.5 text-[10px] ${classes[value] || classes.pending}`}>
      {value || 'pending'}
    </span>
  )
}

function RunList({ runs, selectedId, onSelect }) {
  return (
    <div className="space-y-2">
      {runs.length ? runs.map(run => (
        <button
          key={run.id}
          onClick={() => onSelect(run)}
          className={`w-full rounded-lg border p-3 text-left transition-colors ${
            selectedId === run.id
              ? 'border-purple-400/60 bg-purple-500/15'
              : 'border-forge-border bg-forge-panel/40 hover:bg-forge-border/30'
          }`}
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-mono text-[10px] text-forge-muted">{run.id}</span>
            <RunPill value={run.status} />
          </div>
          <div className="text-xs text-forge-text">{run.adapter?.name || run.adapter?.id}</div>
          <div className="mt-2 flex items-center justify-between gap-3 text-[10px] text-forge-muted">
            <span className="truncate">scope {run.scope}</span>
            <span>{run.permission_check?.reason || 'unchecked'}</span>
          </div>
        </button>
      )) : (
        <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
          No connector runs yet.
        </div>
      )}
    </div>
  )
}

export default function ConnectorPanel({ eventLog }) {
  const [adapters, setAdapters] = useState([])
  const [configuration, setConfiguration] = useState(null)
  const [runs, setRuns] = useState([])
  const [summary, setSummary] = useState(null)
  const [adapterId, setAdapterId] = useState('external_api')
  const [grantId, setGrantId] = useState('')
  const [scope, setScope] = useState('https://api.example.com')
  const [actor, setActor] = useState('connector_operator')
  const [payloadText, setPayloadText] = useState(DEFAULT_PAYLOAD)
  const [activeRun, setActiveRun] = useState(null)
  const [activeProbe, setActiveProbe] = useState(null)
  const [liveProbe, setLiveProbe] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const adapter = adapters.find(item => item.id === adapterId)
  const statusText = useMemo(() => {
    if (busy) return 'working'
    if (latestEvent?.type?.startsWith('connector.')) return latestEvent.type.replace('connector.', '')
    return summary ? `${summary.complete} complete` : 'ready'
  }, [busy, latestEvent, summary])

  const loadConnectors = async () => {
    try {
      const [adapterData, configurationData, runData] = await Promise.all([
        apiRequest('/api/genesis/connectors/adapters'),
        apiRequest('/api/genesis/connectors/configuration'),
        apiRequest('/api/genesis/connectors/runs?limit=40'),
      ])
      setAdapters(adapterData.adapters || [])
      setConfiguration(configurationData || null)
      const runsPayload = runData || {}
      setSummary(runsPayload.summary || adapterData.summary || null)
      setRuns(runsPayload.runs || [])
      if (!activeRun && runsPayload.runs?.[0]) setActiveRun(runsPayload.runs[0])
      if (activeRun) {
        const updated = runsPayload.runs?.find(item => item.id === activeRun.id)
        if (updated) setActiveRun(updated)
      }
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load connectors')
    }
  }

  useEffect(() => {
    loadConnectors()
    const t = setInterval(loadConnectors, 5000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (latestEvent?.type?.startsWith('connector.') || latestEvent?.type?.startsWith('permission.')) {
      loadConnectors()
    }
  }, [latestEvent])

  const mintGrantForAdapter = async () => {
    if (!adapter) return
    setBusy(true)
    setError(null)
    try {
      const created = await apiRequest('/api/genesis/approvals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: `${adapter.name} connector grant`,
          action_type: adapter.action_type,
          reason: `Approve a scoped grant for the real ${adapter.name} connector.`,
          requested_by: 'connector_panel',
          source: 'connectors',
          risk_level: 'high',
          payload: { target: scope, adapter_id: adapter.id },
          permissions: [adapter.permission, 'human_approval'],
          expires_in_minutes: 1440,
        }),
      })
      const approved = await apiRequest(`/api/genesis/approvals/${created.approval.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewed_by: 'human', note: 'Approved to mint a connector grant.' }),
      })
      const executed = await apiRequest(`/api/genesis/approvals/${approved.approval.id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ executed_by: 'connector_gate', grant_ttl_minutes: 60, grant_max_uses: 10 }),
      })
      setGrantId(executed.approval.execution_result.permission_grant.id)
    } catch (e) {
      setError(e.message || 'Failed to mint connector grant')
    } finally {
      setBusy(false)
    }
  }

  const runConnector = async () => {
    setBusy(true)
    setError(null)
    try {
      const payload = JSON.parse(payloadText || '{}')
      const data = await apiRequest('/api/genesis/connectors/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          adapter_id: adapterId,
          grant_id: grantId,
          scope,
          actor,
          payload,
        }),
      })
      setActiveRun(data.run)
      await loadConnectors()
    } catch (e) {
      setError(e.message || 'Connector run failed')
      await loadConnectors()
    } finally {
      setBusy(false)
    }
  }

  const probeConnector = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/connectors/probe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          adapter_id: adapterId,
          scope,
          live: liveProbe,
        }),
      })
      setActiveProbe(data.probe)
      await loadConnectors()
    } catch (e) {
      setError(e.message || 'Connector probe failed')
    } finally {
      setBusy(false)
    }
  }

  const selectAdapter = (nextId) => {
    const next = adapters.find(item => item.id === nextId)
    setAdapterId(nextId)
    setActiveProbe(null)
    if (next) {
      setScope(next.default_scope)
      setPayloadText(defaultPayloadFor(next.id, next.default_scope))
    }
  }

  const configuredCount = configuration?.configured ?? adapters.filter(item => item.configured).length
  const totalCount = configuration?.total ?? adapters.length

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Gated Connector Adapters</h3>
          <p className="text-[10px] text-forge-muted">
            Connector calls either perform real approved side effects or fail as unconfigured. Blocks, failures, and completions are written to the connector ledger.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">connector gate</div>
          <div className="text-sm font-mono text-forge-text">{configuredCount}/{totalCount} configured</div>
          <div className="text-[10px] text-forge-muted">{statusText}</div>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <section className="mb-4 rounded-xl border border-forge-border bg-forge-panel/30 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-xs font-medium text-forge-text">Integration Control Center</div>
            <div className="text-[10px] text-forge-muted">Secrets stay server-side. Missing providers fail closed instead of showing artificial success.</div>
          </div>
          <span className="rounded border border-forge-border bg-forge-bg/60 px-2 py-1 font-mono text-[10px] text-forge-muted">
            strict mode enabled
          </span>
        </div>
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {(configuration?.adapters || adapters).map(item => (
            <button
              key={item.adapter_id || item.id}
              onClick={() => selectAdapter(item.adapter_id || item.id)}
              className={`rounded-lg border p-3 text-left ${
                (item.adapter_id || item.id) === adapterId
                  ? 'border-purple-400/60 bg-purple-500/15'
                  : 'border-forge-border bg-forge-bg/40 hover:bg-forge-border/30'
              }`}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="truncate text-xs text-forge-text">{item.name}</span>
                <span className={`rounded border px-2 py-0.5 text-[10px] ${item.configured ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-amber-500/30 bg-amber-500/10 text-amber-300'}`}>
                  {item.configured ? 'configured' : 'missing'}
                </span>
              </div>
              <div className="truncate font-mono text-[10px] text-forge-muted">{item.real_side_effect || 'real connector'}</div>
              {(item.missing || []).length ? (
                <div className="mt-2 line-clamp-2 font-mono text-[10px] text-amber-200">{item.missing.join(', ')}</div>
              ) : null}
            </button>
          ))}
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[390px_1fr]">
        <div className="space-y-4">
          <div className="rounded-xl border border-forge-border p-4">
            <label className="block text-xs text-forge-muted">Adapter</label>
            <select
              value={adapterId}
              onChange={e => selectAdapter(e.target.value)}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
            >
              {adapters.map(item => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>

            <div className="mt-3 rounded-lg border border-forge-border bg-forge-panel/40 p-3 text-xs text-forge-muted">
              {adapter?.description || 'Load an adapter to see its permission contract.'}
              {adapter?.requires?.length ? (
                <div className="mt-2 font-mono text-[10px] text-amber-200">
                  requires {adapter.requires.join(', ')}
                </div>
              ) : null}
              {adapter ? (
                <div className={`mt-2 font-mono text-[10px] ${adapter.configured ? 'text-emerald-300' : 'text-amber-200'}`}>
                  {adapter.configured ? 'server configuration present' : `missing ${(adapter.missing || []).join(', ') || 'configuration'}`}
                </div>
              ) : null}
            </div>

            <label className="mt-3 block text-xs text-forge-muted">Grant id</label>
            <input
              value={grantId}
              onChange={e => setGrantId(e.target.value)}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 font-mono text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

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

            <label className="mt-3 block text-xs text-forge-muted">Payload JSON</label>
            <textarea
              value={payloadText}
              onChange={e => setPayloadText(e.target.value)}
              rows={7}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 font-mono text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <label className="mt-3 flex items-center gap-2 rounded-lg border border-forge-border bg-forge-panel/40 px-3 py-2 text-xs text-forge-muted">
              <input
                type="checkbox"
                checked={liveProbe}
                onChange={e => setLiveProbe(e.target.checked)}
                className="h-4 w-4 accent-cyan-400"
              />
              Live probe when safe. GitHub uses read-only repo checks; Slack/webhook posting stays blocked here.
            </label>

            <div className="mt-3 grid grid-cols-3 gap-2">
              <button
                onClick={probeConnector}
                disabled={busy || !adapter}
                className="rounded-lg border border-sky-400/40 bg-sky-500/20 px-3 py-2 text-xs text-sky-100 hover:bg-sky-500/30 disabled:opacity-40"
              >
                Probe selected
              </button>
              <button
                onClick={mintGrantForAdapter}
                disabled={busy || !adapter}
                className="rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-xs text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
              >
                Mint adapter grant
              </button>
              <button
                onClick={runConnector}
                disabled={busy || !adapterId}
                className="rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-3 py-2 text-xs text-emerald-100 hover:bg-emerald-500/30 disabled:opacity-40"
              >
                Run connector
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs font-medium text-forge-text">Connector runs</div>
              <div className="font-mono text-[10px] text-forge-muted">{runs.length}</div>
            </div>
            <RunList runs={runs} selectedId={activeRun?.id} onSelect={setActiveRun} />
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[10px] text-forge-muted">{activeRun?.id || 'no connector run selected'}</div>
                <h4 className="text-base font-medium text-forge-text">{activeRun?.adapter?.name || 'Connector detail'}</h4>
              </div>
              <RunPill value={activeRun?.status} />
            </div>

            {activeRun ? (
              <div className="grid gap-3 md:grid-cols-4">
                <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                  <div className="text-[10px] text-forge-muted">permission</div>
                  <div className="font-mono text-sm text-forge-text">{activeRun.adapter?.permission}</div>
                </div>
                <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                  <div className="text-[10px] text-forge-muted">scope</div>
                  <div className="truncate font-mono text-sm text-forge-text">{activeRun.scope}</div>
                </div>
                <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                  <div className="text-[10px] text-forge-muted">grant</div>
                  <div className="truncate font-mono text-sm text-forge-text">{activeRun.grant_id}</div>
                </div>
                <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                  <div className="text-[10px] text-forge-muted">check</div>
                  <div className="font-mono text-sm text-forge-text">{activeRun.permission_check?.reason}</div>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                Run an adapter to inspect the permission-enforced connector result.
              </div>
            )}
          </section>

          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[10px] text-forge-muted">{activeProbe?.adapter_id || adapterId}</div>
                <h4 className="text-base font-medium text-forge-text">Connector preflight</h4>
              </div>
              <span className={`rounded border px-2 py-0.5 text-[10px] ${
                activeProbe?.status === 'pass'
                  ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                  : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
              }`}>
                {activeProbe?.status || 'not probed'}
              </span>
            </div>
            {activeProbe ? (
              <div className="space-y-2">
                {(activeProbe.checks || []).map(check => (
                  <div key={check.name} className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] text-forge-muted">{check.name}</span>
                      <span className={check.ok ? 'text-xs text-emerald-300' : 'text-xs text-amber-200'}>
                        {check.ok ? 'pass' : 'needs setup'}
                      </span>
                    </div>
                    <div className="text-xs text-forge-text">{check.message}</div>
                    {check.missing?.length ? (
                      <div className="mt-1 font-mono text-[10px] text-amber-200">{check.missing.join(', ')}</div>
                    ) : null}
                  </div>
                ))}
                <pre className="max-h-72 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
                  {JSON.stringify(activeProbe.details || {}, null, 2)}
                </pre>
              </div>
            ) : (
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                Probe the selected adapter to check server configuration, allowlists, and safe live readiness before minting a grant.
              </div>
            )}
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Result</div>
              <pre className="max-h-96 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
                {JSON.stringify(activeRun?.result || {}, null, 2)}
              </pre>
            </div>
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Permission check</div>
              <pre className="max-h-96 overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
                {JSON.stringify(activeRun?.permission_check || {}, null, 2)}
              </pre>
            </div>
          </section>
        </div>
      </section>
    </div>
  )
}
