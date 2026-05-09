import React, { useEffect, useState } from 'react'

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

const DEFAULT_CODE = `values = input_data.get("values", [])
result = {
    "count": len(values),
    "sum": sum(values),
    "mean": round(sum(values) / len(values), 3) if values else None,
}`

function RunCard({ run }) {
  const ok = run.ok === true
  return (
    <article className="rounded-lg border border-forge-border bg-forge-panel/50 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-mono text-forge-text">{run.id}</div>
          <div className="text-[10px] text-forge-muted">{run.purpose || 'sandbox run'}</div>
        </div>
        <span className={`rounded border px-2 py-0.5 text-[10px] ${
          ok
            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
            : 'border-red-500/30 bg-red-500/10 text-red-300'
        }`}>
          {run.status}
        </span>
      </div>
      {run.result !== undefined && (
        <pre className="max-h-32 overflow-auto rounded bg-forge-bg/70 p-2 text-[10px] text-forge-text">
          {JSON.stringify(run.result, null, 2)}
        </pre>
      )}
      {run.error && (
        <div className="mt-2 rounded border border-red-500/30 bg-red-500/10 p-2 text-[10px] text-red-300">
          {run.error}
        </div>
      )}
    </article>
  )
}

export default function ToolSandboxPanel({ eventLog }) {
  const [code, setCode] = useState(DEFAULT_CODE)
  const [inputJson, setInputJson] = useState('{\n  "values": [3, 5, 8, 13]\n}')
  const [purpose, setPurpose] = useState('Analyze a small numeric payload.')
  const [runs, setRuns] = useState([])
  const [activeRun, setActiveRun] = useState(null)
  const [error, setError] = useState(null)
  const [running, setRunning] = useState(false)

  const loadRuns = async () => {
    try {
      const data = await apiRequest('/api/genesis/tools/sandbox/runs?limit=20')
      setRuns(data.runs || [])
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load sandbox runs')
    }
  }

  useEffect(() => {
    loadRuns()
    const t = setInterval(loadRuns, 5000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (eventLog?.[0]?.type === 'tool_sandbox.completed') {
      loadRuns()
    }
  }, [eventLog])

  const runSandbox = async () => {
    let inputData
    try {
      inputData = JSON.parse(inputJson || '{}')
    } catch (e) {
      setError(`Input JSON error: ${e.message}`)
      return
    }
    setRunning(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/tools/sandbox/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code,
          input_data: inputData,
          purpose,
          timeout_s: 8,
          memory_mb: 128,
        }),
      })
      setActiveRun(data.run)
      await loadRuns()
    } catch (e) {
      setError(e.message || 'Sandbox run failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Tool Sandbox</h3>
          <p className="text-[10px] text-forge-muted">
            Bounded tool execution with isolated workspace, stripped environment, timeouts, and audit logs.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">runs</div>
          <div className="text-sm font-mono text-forge-text">{runs.length}</div>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <section className="grid gap-4 lg:grid-cols-[1fr_0.8fr]">
        <div className="space-y-3 rounded-xl border border-forge-border p-4">
          <label className="block text-xs text-forge-muted">Purpose</label>
          <input
            value={purpose}
            onChange={e => setPurpose(e.target.value)}
            className="w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
          />

          <label className="block text-xs text-forge-muted">Input JSON</label>
          <textarea
            value={inputJson}
            onChange={e => setInputJson(e.target.value)}
            rows={5}
            className="w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 font-mono text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
          />

          <label className="block text-xs text-forge-muted">Python code</label>
          <textarea
            value={code}
            onChange={e => setCode(e.target.value)}
            rows={11}
            className="w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 font-mono text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
          />

          <button
            onClick={runSandbox}
            disabled={running || !code.trim()}
            className="w-full rounded-lg border border-cyan-400/40 bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {running ? 'Running sandbox...' : 'Run sandbox trial'}
          </button>
        </div>

        <div className="space-y-3">
          <div className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 text-xs font-medium text-forge-text">Latest output</div>
            {activeRun ? (
              <RunCard run={activeRun} />
            ) : (
              <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                Run a trial to see sandbox output.
              </div>
            )}
          </div>

          <div className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 text-xs font-medium text-forge-text">Audit history</div>
            <div className="space-y-2">
              {runs.length ? runs.map(run => (
                <RunCard key={run.id} run={run} />
              )) : (
                <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                  No sandbox runs yet.
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
