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

function pct(value) {
  return `${Math.round((value || 0) * 100)}%`
}

function MemoryCard({ memory }) {
  return (
    <article className="rounded-lg border border-forge-border bg-forge-panel/50 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="rounded border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 text-[10px] text-purple-200">
            {memory.kind}
          </span>
          <span className="text-[10px] text-forge-muted">{memory.scope}</span>
        </div>
        <span className="text-[10px] font-mono text-emerald-300">{pct(memory.score)}</span>
      </div>
      <p className="text-sm leading-6 text-forge-text">{memory.text}</p>
      <div className="mt-3 flex flex-wrap gap-1">
        {(memory.tags || []).map(tag => (
          <span key={tag} className="rounded bg-forge-border/50 px-1.5 py-0.5 text-[10px] text-forge-muted">
            {tag}
          </span>
        ))}
        {memory.benchmark_id && (
          <span className="rounded bg-cyan-500/10 px-1.5 py-0.5 text-[10px] text-cyan-300">
            {memory.benchmark_id}
          </span>
        )}
      </div>
    </article>
  )
}

function CurriculumCard({ item, recommended }) {
  return (
    <div className={`rounded-lg border p-3 ${
      recommended
        ? 'border-amber-400/40 bg-amber-500/10'
        : 'border-forge-border bg-forge-panel/50'
    }`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-forge-text">{item.benchmark_id}</div>
          <div className="text-[10px] text-forge-muted">{item.attempts || 0} attempts</div>
        </div>
        {recommended && (
          <span className="rounded border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-200">
            next
          </span>
        )}
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div className="rounded bg-forge-bg/60 p-2">
          <div className="text-[10px] text-forge-muted">mastery</div>
          <div className="text-xs font-mono text-emerald-300">{pct(item.mastery)}</div>
        </div>
        <div className="rounded bg-forge-bg/60 p-2">
          <div className="text-[10px] text-forge-muted">weakness</div>
          <div className="text-xs font-mono text-amber-300">{pct(item.weakness)}</div>
        </div>
        <div className="rounded bg-forge-bg/60 p-2">
          <div className="text-[10px] text-forge-muted">best</div>
          <div className="text-xs font-mono text-forge-text">{pct(item.best_fitness)}</div>
        </div>
      </div>
    </div>
  )
}

export default function MemoryPanel({ eventLog }) {
  const [memories, setMemories] = useState([])
  const [curriculum, setCurriculum] = useState(null)
  const [query, setQuery] = useState('')
  const [newMemory, setNewMemory] = useState('')
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    try {
      const [memoryData, curriculumData] = await Promise.all([
        apiRequest('/api/genesis/memory?limit=80'),
        apiRequest('/api/genesis/curriculum'),
      ])
      setMemories(memoryData.memories || [])
      setCurriculum(curriculumData)
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load memory')
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    const event = eventLog?.[0]
    if (event?.type === 'memory.created' || event?.type === 'curriculum.updated') {
      load()
    }
  }, [eventLog])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return memories
    return memories.filter(memory => (
      memory.text.toLowerCase().includes(q)
      || (memory.tags || []).join(' ').toLowerCase().includes(q)
      || (memory.benchmark_id || '').toLowerCase().includes(q)
    ))
  }, [memories, query])

  const saveManualMemory = async () => {
    if (!newMemory.trim()) return
    setSaving(true)
    setError(null)
    try {
      await apiRequest('/api/genesis/memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: newMemory.trim(),
          kind: 'lesson',
          scope: 'global',
          tags: ['manual'],
          score: 0.8,
        }),
      })
      setNewMemory('')
      await load()
    } catch (e) {
      setError(e.message || 'Failed to save memory')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Memory Curriculum</h3>
          <p className="text-[10px] text-forge-muted">
            Durable lessons retrieved by future organisms, plus benchmark-driven training focus.
          </p>
        </div>
        <div className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-right">
          <div className="text-[10px] text-forge-muted">memories</div>
          <div className="text-sm font-mono text-forge-text">{curriculum?.memory_count ?? memories.length}</div>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <section className="mb-4 rounded-xl border border-forge-border p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <div className="text-xs font-medium text-forge-text">Curriculum</div>
            <div className="text-[10px] text-forge-muted">
              Recommended next: {curriculum?.recommended_next || 'waiting for benchmark data'}
            </div>
          </div>
        </div>
        <div className="grid gap-2 md:grid-cols-3">
          {(curriculum?.items || []).length ? (
            curriculum.items.map(item => (
              <CurriculumCard
                key={item.benchmark_id}
                item={item}
                recommended={item.benchmark_id === curriculum.recommended_next}
              />
            ))
          ) : (
            <div className="rounded-lg border border-forge-border bg-forge-panel/40 p-4 text-sm text-forge-muted md:col-span-3">
              Run Benchmarks benchmarks to create curriculum pressure.
            </div>
          )}
        </div>
      </section>

      <section className="mb-4 grid gap-3 md:grid-cols-[1fr_0.8fr]">
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search memory"
          className="rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
        />
        <div className="flex gap-2">
          <input
            value={newMemory}
            onChange={e => setNewMemory(e.target.value)}
            placeholder="Add durable lesson"
            className="min-w-0 flex-1 rounded-lg border border-forge-border bg-forge-panel px-3 py-2 text-sm text-forge-text focus:border-purple-500/60 focus:outline-none"
          />
          <button
            onClick={saveManualMemory}
            disabled={saving || !newMemory.trim()}
            className="rounded-lg border border-purple-500/40 bg-purple-500/20 px-3 py-2 text-xs text-purple-200 hover:bg-purple-500/30 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Save
          </button>
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-2">
        {filtered.length ? (
          filtered.map(memory => <MemoryCard key={memory.id} memory={memory} />)
        ) : (
          <div className="rounded-xl border border-forge-border p-8 text-center text-sm text-forge-muted lg:col-span-2">
            No matching memories yet.
          </div>
        )}
      </section>
    </div>
  )
}
