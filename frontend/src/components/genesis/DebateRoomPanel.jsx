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
    throw new Error(data.detail || data.error || response.statusText)
  }
  return data
}

const DEFAULT_TOPIC = 'Should Genesis promote tool-using organisms only after debate consensus?'
const DEFAULT_CONTEXT = `{
  "workflow": "debate",
  "goal": "Add multi-agent collaboration with explicit disagreement and synthesis.",
  "constraints": [
    "Keep every debate auditable",
    "Prefer small testable actions",
    "Do not overstate system autonomy"
  ]
}`

function ConfidenceBar({ value }) {
  const pct = Math.round((Number(value) || 0) * 100)
  return (
    <div className="min-w-[120px]">
      <div className="mb-1 flex items-center justify-between text-[10px] text-forge-muted">
        <span>confidence</span>
        <span>{pct}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-forge-border">
        <div
          className="h-full rounded-full bg-cyan-400"
          style={{ width: `${Math.max(4, Math.min(100, pct))}%` }}
        />
      </div>
    </div>
  )
}

function ListBlock({ title, items }) {
  const safeItems = Array.isArray(items) ? items.filter(Boolean) : []
  if (!safeItems.length) return null
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-widest text-forge-muted">{title}</div>
      <ul className="space-y-1 text-xs text-forge-text">
        {safeItems.map((item, index) => (
          <li key={`${title}-${index}`} className="rounded border border-forge-border bg-forge-bg/50 px-2 py-1">
            {String(item)}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ProposalCard({ proposal }) {
  return (
    <article className="rounded-lg border border-forge-border bg-forge-panel/50 p-3">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium text-forge-text">{proposal.agent_name}</div>
          <div className="text-[10px] text-forge-muted">{proposal.stance}</div>
        </div>
        <ConfidenceBar value={proposal.confidence} />
      </div>
      <p className="mb-3 text-sm leading-relaxed text-forge-text">{proposal.recommendation}</p>
      <div className="grid gap-3 md:grid-cols-3">
        <ListBlock title="Evidence" items={proposal.evidence} />
        <ListBlock title="Risks" items={proposal.risks} />
        <ListBlock title="Tests" items={proposal.tests} />
      </div>
    </article>
  )
}

function CritiqueCard({ critique }) {
  return (
    <article className="rounded-lg border border-forge-border bg-forge-panel/50 p-3">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium text-forge-text">{critique.critic_agent_name}</div>
          <div className="text-[10px] text-forge-muted">target: {critique.target_agent_id || 'mixed'}</div>
        </div>
        <ConfidenceBar value={critique.score} />
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-widest text-forge-muted">Strongest</div>
          <p className="text-xs text-forge-text">{critique.strongest_point || 'No strongest point recorded.'}</p>
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-widest text-forge-muted">Weakest</div>
          <p className="text-xs text-forge-text">{critique.weakest_point || 'No weak point recorded.'}</p>
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-widest text-forge-muted">Revision</div>
          <p className="text-xs text-forge-text">{critique.revision || 'No revision recorded.'}</p>
        </div>
      </div>
    </article>
  )
}

function DebateHistory({ debates, selectedId, onSelect }) {
  return (
    <div className="space-y-2">
      {debates.length ? debates.map(debate => (
        <button
          key={debate.id}
          onClick={() => onSelect(debate)}
          className={`w-full rounded-lg border p-3 text-left transition-colors ${
            selectedId === debate.id
              ? 'border-purple-400/60 bg-purple-500/15'
              : 'border-forge-border bg-forge-panel/40 hover:bg-forge-border/30'
          }`}
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-mono text-[10px] text-forge-muted">{debate.id}</span>
            <span className={`rounded border px-2 py-0.5 text-[10px] ${
              debate.status === 'complete'
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                : debate.status === 'error'
                  ? 'border-red-500/30 bg-red-500/10 text-red-300'
                  : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300'
            }`}>
              {debate.status}
            </span>
          </div>
          <div className="line-clamp-2 text-xs text-forge-text">{debate.topic}</div>
          {debate.synthesis?.decision && (
            <div className="mt-2 line-clamp-2 text-[10px] text-forge-muted">{debate.synthesis.decision}</div>
          )}
        </button>
      )) : (
        <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
          No debates yet.
        </div>
      )}
    </div>
  )
}

export default function DebateRoomPanel({ eventLog }) {
  const [topic, setTopic] = useState(DEFAULT_TOPIC)
  const [contextJson, setContextJson] = useState(DEFAULT_CONTEXT)
  const [debates, setDebates] = useState([])
  const [activeDebate, setActiveDebate] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)

  const latestEvent = eventLog?.[0]
  const statusText = useMemo(() => {
    if (running) return 'Debating...'
    if (latestEvent?.type?.startsWith('collaboration.')) return latestEvent.type.replace('collaboration.', '')
    return activeDebate?.status || 'ready'
  }, [activeDebate, latestEvent, running])

  const loadDebates = async () => {
    try {
      const data = await apiRequest('/api/genesis/collaboration/debates?limit=20')
      setDebates(data.debates || [])
      setError(null)
      if (!activeDebate && data.debates?.[0]) setActiveDebate(data.debates[0])
    } catch (e) {
      setError(e.message || 'Failed to load debates')
    }
  }

  useEffect(() => {
    loadDebates()
    const t = setInterval(loadDebates, 6000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (latestEvent?.type?.startsWith('collaboration.')) {
      loadDebates()
    }
  }, [latestEvent])

  const startDebate = async () => {
    let context
    try {
      context = JSON.parse(contextJson || '{}')
    } catch (e) {
      setError(`Context JSON error: ${e.message}`)
      return
    }
    setRunning(true)
    setError(null)
    try {
      const data = await apiRequest('/api/genesis/collaboration/debates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, context }),
      })
      setActiveDebate(data.debate)
      await loadDebates()
    } catch (e) {
      setError(e.message || 'Debate failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Debate Room</h3>
          <p className="text-[10px] text-forge-muted">
            Multi-agent proposals, adversarial critique, ranked synthesis, and durable debate memory.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">status</div>
          <div className="text-sm font-mono text-forge-text">{statusText}</div>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <section className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <div className="space-y-4">
          <div className="rounded-xl border border-forge-border p-4">
            <label className="block text-xs text-forge-muted">Debate topic</label>
            <textarea
              value={topic}
              onChange={e => setTopic(e.target.value)}
              rows={4}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <label className="mt-3 block text-xs text-forge-muted">Context JSON</label>
            <textarea
              value={contextJson}
              onChange={e => setContextJson(e.target.value)}
              rows={10}
              className="mt-2 w-full rounded-lg border border-forge-border bg-forge-panel px-3 py-2 font-mono text-xs text-forge-text focus:border-purple-500/60 focus:outline-none"
            />

            <button
              onClick={startDebate}
              disabled={running || !topic.trim()}
              className="mt-3 w-full rounded-lg border border-purple-400/40 bg-purple-500/20 px-3 py-2 text-sm text-purple-100 hover:bg-purple-500/30 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {running ? 'Running debate...' : 'Start debate'}
            </button>
          </div>

          <div className="rounded-xl border border-forge-border p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs font-medium text-forge-text">Debate history</div>
              <div className="font-mono text-[10px] text-forge-muted">{debates.length}</div>
            </div>
            <DebateHistory
              debates={debates}
              selectedId={activeDebate?.id}
              onSelect={setActiveDebate}
            />
          </div>
        </div>

        <div className="space-y-4">
          {activeDebate ? (
            <>
              <section className="rounded-xl border border-forge-border p-4">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div>
                    <div className="font-mono text-[10px] text-forge-muted">{activeDebate.id}</div>
                    <h4 className="text-base font-medium text-forge-text">{activeDebate.topic}</h4>
                  </div>
                  <ConfidenceBar value={activeDebate.synthesis?.confidence} />
                </div>
                {activeDebate.synthesis ? (
                  <div className="space-y-3">
                    <p className="rounded-lg border border-cyan-400/25 bg-cyan-500/10 p-3 text-sm leading-relaxed text-cyan-50">
                      {activeDebate.synthesis.decision}
                    </p>
                    <div className="grid gap-3 md:grid-cols-2">
                      <ListBlock title="Consensus" items={activeDebate.synthesis.consensus} />
                      <ListBlock title="Dissent" items={activeDebate.synthesis.dissent} />
                      <ListBlock title="Risks" items={activeDebate.synthesis.risks} />
                      <ListBlock title="Next actions" items={activeDebate.synthesis.next_actions} />
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted">
                    Synthesis will appear after all agents finish proposals and critiques.
                  </div>
                )}
              </section>

              <section className="rounded-xl border border-forge-border p-4">
                <div className="mb-3 text-xs font-medium text-forge-text">Agent proposals</div>
                <div className="space-y-3">
                  {(activeDebate.proposals || []).map(proposal => (
                    <ProposalCard key={proposal.agent_id} proposal={proposal} />
                  ))}
                </div>
              </section>

              <section className="rounded-xl border border-forge-border p-4">
                <div className="mb-3 text-xs font-medium text-forge-text">Cross-critiques</div>
                <div className="space-y-3">
                  {(activeDebate.critiques || []).map((critique, index) => (
                    <CritiqueCard key={`${critique.critic_agent_id}-${index}`} critique={critique} />
                  ))}
                </div>
              </section>
            </>
          ) : (
            <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-6 text-center text-sm text-forge-muted">
              Start a debate to see collaborative reasoning.
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
