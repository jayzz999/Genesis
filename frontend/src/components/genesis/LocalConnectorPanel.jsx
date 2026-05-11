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
  const classes = {
    complete: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    written: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    blocked: 'border-red-500/30 bg-red-500/10 text-red-300',
    failed: 'border-red-500/30 bg-red-500/10 text-red-300',
    ready: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300',
  }
  return (
    <span className={`rounded border px-2 py-0.5 text-[10px] ${classes[value] || classes.ready}`}>
      {value || 'ready'}
    </span>
  )
}

export default function LocalConnectorPanel({ eventLog }) {
  const [artifacts, setArtifacts] = useState([])
  const [summary, setSummary] = useState(null)
  const [grantId, setGrantId] = useState('')
  const [scope, setScope] = useState('local-artifacts')
  const [filename, setFilename] = useState('agi10-proof.txt')
  const [content, setContent] = useState('Local connector proof: this file was written by a real local connector after human approval and scoped grant validation.')
  const [metadataText, setMetadataText] = useState('{\n  "workflow": "local_connector",\n  "connector": "local_artifact_write"\n}')
  const [activeRun, setActiveRun] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const statusText = useMemo(() => {
    if (busy) return 'working'
    if (activeRun?.status) return activeRun.status
    if (latestEvent?.type === 'connector.artifact_written') return 'written'
    return summary ? `${summary.local_artifacts || 0} artifacts` : 'ready'
  }, [activeRun, busy, latestEvent, summary])

  const loadArtifacts = async () => {
    try {
      const data = await apiRequest('/api/genesis/connectors/artifacts?limit=30')
      setArtifacts(data.artifacts || [])
      setSummary(data.summary || null)
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load local connector artifacts')
    }
  }

  useEffect(() => {
    loadArtifacts()
    const t = setInterval(loadArtifacts, 5000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (latestEvent?.type?.startsWith('connector.') || latestEvent?.type?.startsWith('permission.')) {
      loadArtifacts()
    }
  }, [latestEvent])

  const mintGrant = async () => {
    setBusy(true)
    setError(null)
    try {
      const created = await apiRequest('/api/genesis/approvals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'Local artifact connector grant',
          action_type: 'file_upload',
          reason: 'Approve a scoped grant for the local artifact writer connector.',
          requested_by: 'connector_panel',
          source: 'local-connector',
          risk_level: 'medium',
          payload: { target: scope, adapter_id: 'local_artifact_write' },
          permissions: ['file_upload', 'human_approval'],
          expires_in_minutes: 1440,
        }),
      })
      const approved = await apiRequest(`/api/genesis/approvals/${created.approval.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewed_by: 'human', note: 'Approved to mint a local connector grant.' }),
      })
      const executed = await apiRequest(`/api/genesis/approvals/${approved.approval.id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ executed_by: 'connector_gate', grant_ttl_minutes: 60, grant_max_uses: 10 }),
      })
      setGrantId(executed.approval.execution_result.permission_grant.id)
    } catch (e) {
      setError(e.message || 'Failed to mint local connector grant')
    } finally {
      setBusy(false)
    }
  }

  const writeArtifact = async () => {
    setBusy(true)
    setError(null)
    try {
      const metadata = JSON.parse(metadataText || '{}')
      const data = await apiRequest('/api/genesis/connectors/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          adapter_id: 'local_artifact_write',
          grant_id: grantId,
          scope,
          actor: 'local_connector',
          payload: { filename, content, metadata },
        }),
      })
      setActiveRun(data.run)
      await loadArtifacts()
    } catch (e) {
      setError(e.message || 'Local artifact write failed')
      await loadArtifacts()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Local Artifact Connector</h3>
          <p className="text-[10px] text-forge-muted">
            A real local connector writes only inside controlled artifact storage after approval and permission grant validation.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">local connector</div>
          <div className="flex items-center justify-end gap-2 text-sm font-mono text-forge-text">
            <StatePill value={statusText.includes('artifact') ? 'ready' : statusText} />
          </div>
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
            <label className="block text-xs text-forge-muted">Grant id</label>
            <input
              value={grantId}
              onChange={e => setGrantId(e.target.value)}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 font-mono text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
              placeholder="Mint a scoped grant first"
            />

            <label className="mt-3 block text-xs text-forge-muted">Scope</label>
            <input
              value={scope}
              onChange={e => setScope(e.target.value)}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <label className="mt-3 block text-xs text-forge-muted">Filename</label>
            <input
              value={filename}
              onChange={e => setFilename(e.target.value)}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <label className="mt-3 block text-xs text-forge-muted">Content</label>
            <textarea
              value={content}
              onChange={e => setContent(e.target.value)}
              rows={5}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <label className="mt-3 block text-xs text-forge-muted">Metadata JSON</label>
            <textarea
              value={metadataText}
              onChange={e => setMetadataText(e.target.value)}
              rows={5}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 font-mono text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                onClick={mintGrant}
                disabled={busy}
                className="rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-xs text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40"
              >
                Mint local grant
              </button>
              <button
                onClick={writeArtifact}
                disabled={busy || !grantId.trim()}
                className="rounded-lg border border-emerald-400/40 bg-emerald-500/20 px-3 py-2 text-xs text-emerald-100 hover:bg-emerald-500/30 disabled:opacity-40"
              >
                Write local artifact
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs font-medium text-forge-text">Local artifacts</div>
              <div className="font-mono text-[10px] text-forge-muted">{artifacts.length}</div>
            </div>
            <div className="space-y-2">
              {artifacts.length ? artifacts.map(item => (
                <div key={item.path} className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-mono text-xs text-forge-text">{item.filename}</span>
                    <StatePill value="written" />
                  </div>
                  <div className="mt-2 truncate font-mono text-[10px] text-forge-muted">{item.path}</div>
                  <div className="mt-1 text-[10px] text-forge-muted">{item.bytes} bytes · {item.updated_at}</div>
                </div>
              )) : (
                <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                  No local connector artifacts yet.
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[10px] text-forge-muted">{activeRun?.id || 'no local connector run selected'}</div>
                <h4 className="text-base font-medium text-forge-text">Artifact write result</h4>
              </div>
              <StatePill value={activeRun?.status || 'ready'} />
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                <div className="text-[10px] text-forge-muted">permission</div>
                <div className="font-mono text-sm text-forge-text">file_upload</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                <div className="text-[10px] text-forge-muted">side effect</div>
                <div className="font-mono text-sm text-forge-text">local_file_write</div>
              </div>
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-3">
                <div className="text-[10px] text-forge-muted">real connector</div>
                <div className="font-mono text-sm text-forge-text">{activeRun?.result ? (activeRun.result.simulated ? 'no' : 'yes') : 'pending'}</div>
              </div>
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-forge-border p-4">
              <div className="mb-3 text-xs font-medium text-forge-text">Run result</div>
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
