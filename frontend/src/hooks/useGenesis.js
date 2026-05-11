import { useCallback, useEffect, useRef, useState } from 'react'

const defaultWsUrl = (() => {
  if (typeof window === 'undefined') return 'ws://localhost:8002'
  if (import.meta.env.DEV && window.location.hostname === '127.0.0.1') {
    return 'ws://127.0.0.1:8002'
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
})()
const WS_URL = import.meta.env.VITE_WS_URL || defaultWsUrl
const HTTP_BASE = import.meta.env.VITE_API_BASE || ''

function apiToken() {
  return import.meta.env.VITE_GENESIS_API_TOKEN
    || (typeof window !== 'undefined' ? window.localStorage.getItem('GENESIS_API_TOKEN') : '')
    || ''
}

function sessionToken() {
  return typeof window !== 'undefined' ? window.localStorage.getItem('GENESIS_SESSION_TOKEN') || '' : ''
}

function authHeaders(headers = {}) {
  const token = apiToken()
  const session = sessionToken()
  return {
    ...headers,
    ...(token ? { 'X-Genesis-Token': token } : {}),
    ...(session ? { 'X-Genesis-Session': session } : {}),
  }
}

async function apiRequest(path, options = {}) {
  const { timeoutMs = 120000, ...fetchOptions } = options
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  let response
  try {
    response = await fetch(`${HTTP_BASE}${path}`, {
      ...fetchOptions,
      headers: authHeaders(fetchOptions.headers),
      signal: fetchOptions.signal || controller.signal,
    })
  } catch (e) {
    if (e.name === 'AbortError') {
      throw new Error('Request timed out. The organism may still be working; refresh before retrying.')
    }
    throw e
  } finally {
    clearTimeout(timeout)
  }

  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { detail: text }
    }
  }

  if (!response.ok) {
    const detail = data?.detail || data?.error || response.statusText || 'Request failed'
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data || {}
}

export function useGenesis() {
  const [connected, setConnected] = useState(false)
  const [organisms, setOrganisms] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [graph, setGraph] = useState({ nodes: [], edges: [] })
  const [branches, setBranches] = useState([])
  const [eventLog, setEventLog] = useState([])
  const [lastError, setLastError] = useState(null)
  const [runtimeStatus, setRuntimeStatus] = useState(null)
  const [pendingActions, setPendingActions] = useState({})
  const [acting, setActing] = useState(false)
  const [dreaming, setDreaming] = useState(false)
  const [skills, setSkills] = useState([])
  const [metaCognition, setMetaCognition] = useState(null)
  const wsRef = useRef(null)

  const withPending = useCallback(async (key, fn) => {
    setPendingActions(prev => ({ ...prev, [key]: true }))
    try {
      return await fn()
    } finally {
      setPendingActions(prev => ({ ...prev, [key]: false }))
    }
  }, [])

  const loadStatus = useCallback(async () => {
    try {
      const j = await apiRequest('/api/genesis/status', { timeoutMs: 15000 })
      setRuntimeStatus(j)
      setLastError(null)
    } catch (e) {
      setLastError(e.message)
    }
  }, [])

  const loadOrganisms = useCallback(async () => {
    try {
      const j = await apiRequest('/api/genesis/organisms?limit=1000', { timeoutMs: 30000 })
      setOrganisms(j.organisms || [])
      setLastError(null)
    } catch (e) {
      setLastError(e.message)
    }
  }, [])

  const loadCausality = useCallback(async (id) => {
    try {
      const j = await apiRequest(`/api/genesis/organisms/${id}/causality?include_dreams=true&include_shadows=true`, { timeoutMs: 30000 })
      setGraph(j)
      setLastError(null)
    } catch (e) {
      setLastError(e.message)
    }
  }, [])

  const loadBranches = useCallback(async (id) => {
    try {
      const j = await apiRequest(`/api/genesis/organisms/${id}/branches`, { timeoutMs: 30000 })
      setBranches(j.branches || [])
      setLastError(null)
    } catch (e) {
      setLastError(e.message)
    }
  }, [])

  const loadSkills = useCallback(async () => {
    try {
      const j = await apiRequest('/api/genesis/skills', { timeoutMs: 30000 })
      setSkills(j.skills || [])
      setLastError(null)
    } catch (e) {
      setLastError(e.message)
    }
  }, [])

  const loadMetaCognition = useCallback(async (id) => {
    try {
      const j = await apiRequest(`/api/genesis/organisms/${id}/metacognition`, { timeoutMs: 30000 })
      setMetaCognition(j)
      setLastError(null)
    } catch (e) {
      setMetaCognition(null)
      setLastError(e.message)
    }
  }, [])

  const refreshActive = useCallback(async (id) => {
    if (!id) return
    await Promise.all([
      loadCausality(id),
      loadBranches(id),
      loadMetaCognition(id),
      loadStatus(),
    ])
  }, [loadBranches, loadCausality, loadMetaCognition, loadStatus])

  useEffect(() => {
    const clientId = `gen_${Date.now()}_${Math.random().toString(16).slice(2)}`
    const token = apiToken()
    const session = sessionToken()
    const wsToken = token || session ? `?token=${encodeURIComponent(token || session)}` : ''
    const ws = new WebSocket(`${WS_URL}/ws/${clientId}${wsToken}`)
    wsRef.current = ws
    ws.onopen = () => {
      if (wsRef.current === ws) setConnected(true)
    }
    ws.onclose = () => {
      if (wsRef.current === ws) setConnected(false)
    }
    ws.onerror = () => {
      if (wsRef.current === ws) setConnected(false)
    }
    ws.onmessage = (ev) => {
      try {
        const e = JSON.parse(ev.data)
        if (!e.type || !(
          e.type.startsWith('organism.')
          || e.type.startsWith('population.')
          || e.type.startsWith('memory.')
          || e.type.startsWith('curriculum.')
          || e.type.startsWith('tool_sandbox.')
          || e.type.startsWith('collaboration.')
          || e.type.startsWith('self_improvement.')
          || e.type.startsWith('operator.')
          || e.type.startsWith('approval.')
          || e.type.startsWith('permission.')
          || e.type.startsWith('connector.')
        )) return
        setEventLog(log => [e, ...log].slice(0, 100))
        if (e.type === 'organism.perceiving') setActing(true)
        if (e.type === 'organism.acted') setActing(false)
        if (e.type === 'organism.dreaming_start') setDreaming(true)
        if (e.type === 'organism.dreaming_end') setDreaming(false)
        if (activeId && e.organism_id === activeId &&
            (e.type === 'organism.acted'
             || e.type === 'organism.dreamt'
             || e.type === 'organism.branch_created'
             || e.type === 'organism.branch_promoted'
             || e.type === 'organism.meta_critique')) {
          refreshActive(activeId)
        }
        if (e.type === 'organism.seeded') loadOrganisms()
        if (e.type === 'organism.distilled') loadSkills()
      } catch {}
    }
    return () => {
      if (wsRef.current === ws) {
        wsRef.current = null
        setConnected(false)
      }
      ws.close()
    }
  }, [activeId, loadOrganisms, loadSkills, refreshActive])

  useEffect(() => {
    loadOrganisms()
    loadSkills()
    loadStatus()
    const t = setInterval(loadStatus, 15000)
    return () => clearInterval(t)
  }, [loadOrganisms, loadSkills, loadStatus])

  useEffect(() => {
    if (activeId) {
      refreshActive(activeId)
    } else {
      setGraph({ nodes: [], edges: [] })
      setBranches([])
      setMetaCognition(null)
    }
  }, [activeId, refreshActive])

  const seed = useCallback(async ({
    goal,
    name,
    constraints = [],
    forbidden = [],
    inherit_from = [],
    inherit_from_organisms = [],
    max_inherited_skills = 5,
    mcp_servers = [],
  }) => {
    const j = await withPending('seed', () => apiRequest('/api/genesis/seed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      timeoutMs: 120000,
      body: JSON.stringify({
        goal,
        name,
        constraints,
        forbidden,
        inherit_from,
        inherit_from_organisms,
        max_inherited_skills,
        mcp_servers,
      }),
    }))
    await Promise.all([loadOrganisms(), loadStatus()])
    setActiveId(j.organism.id)
    setLastError(null)
    return j.organism
  }, [loadOrganisms, loadStatus, withPending])

  const perceive = useCallback(async (id, perception) => {
    const j = await withPending('perceive', () => apiRequest(`/api/genesis/organisms/${id}/perceive`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      timeoutMs: 180000,
      body: JSON.stringify({ perception }),
    }))
    setLastError(null)
    await refreshActive(id)
    return j
  }, [refreshActive, withPending])

  const dream = useCallback(async (id, n = 2) => {
    const j = await withPending('dream', () => apiRequest(`/api/genesis/organisms/${id}/dream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      timeoutMs: 240000,
      body: JSON.stringify({ n }),
    }))
    setLastError(null)
    await refreshActive(id)
    return j
  }, [refreshActive, withPending])

  const editDecision = useCallback(async (orgId, decisionId, payload) => {
    const j = await withPending('edit', () => apiRequest(`/api/genesis/organisms/${orgId}/edit/${decisionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      timeoutMs: 240000,
      body: JSON.stringify(payload),
    }))
    setLastError(null)
    await refreshActive(orgId)
    return j
  }, [refreshActive, withPending])

  const promoteBranch = useCallback(async (orgId, branchId) => {
    const j = await withPending('promote', () => apiRequest(`/api/genesis/organisms/${orgId}/branches/${branchId}/promote`, {
      method: 'POST',
      timeoutMs: 120000,
    }))
    setLastError(null)
    await refreshActive(orgId)
    return j
  }, [refreshActive, withPending])

  const addSource = useCallback(async (orgId, source) => {
    const j = await withPending('source', () => apiRequest(`/api/genesis/organisms/${orgId}/sources`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(source),
    }))
    await Promise.all([loadOrganisms(), loadStatus()])
    setLastError(null)
    return j
  }, [loadOrganisms, loadStatus, withPending])

  const removeSource = useCallback(async (orgId, index) => {
    await withPending('source', () => apiRequest(`/api/genesis/organisms/${orgId}/sources/${index}`, {
      method: 'DELETE',
    }))
    await Promise.all([loadOrganisms(), loadStatus()])
    setLastError(null)
  }, [loadOrganisms, loadStatus, withPending])

  const getSkill = useCallback(async (id) => (
    apiRequest(`/api/genesis/skills/${id}`, { timeoutMs: 30000 })
  ), [])

  const getSkillLineage = useCallback(async (id) => (
    apiRequest(`/api/genesis/skills/${id}/lineage`, { timeoutMs: 30000 })
  ), [])

  const deleteSkill = useCallback(async (id) => {
    await withPending('skill', () => apiRequest(`/api/genesis/skills/${id}`, { method: 'DELETE' }))
    await loadSkills()
    setLastError(null)
  }, [loadSkills, withPending])

  const killOrganism = useCallback(async (id) => {
    await withPending('kill', () => apiRequest(`/api/genesis/organisms/${id}`, {
      method: 'DELETE',
      timeoutMs: 180000,
    }))
    if (activeId === id) setActiveId(null)
    await Promise.all([loadOrganisms(), loadStatus(), loadSkills()])
    setLastError(null)
  }, [activeId, loadOrganisms, loadSkills, loadStatus, withPending])

  const switchStrategy = useCallback(async (orgId, strategyName) => {
    const j = await withPending('strategy', () => apiRequest(`/api/genesis/organisms/${orgId}/metacognition/strategy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategy_name: strategyName }),
    }))
    if (j.ok) await loadMetaCognition(orgId)
    setLastError(null)
    return j
  }, [loadMetaCognition, withPending])

  const toggleMetaCognition = useCallback(async (orgId, enabled) => {
    const j = await withPending('strategy', () => apiRequest(`/api/genesis/organisms/${orgId}/metacognition/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    }))
    await loadMetaCognition(orgId)
    setLastError(null)
    return j
  }, [loadMetaCognition, withPending])

  return {
    connected,
    organisms,
    activeId,
    graph,
    branches,
    eventLog,
    acting,
    dreaming,
    skills,
    lastError,
    runtimeStatus,
    pendingActions,
    metaCognition,
    setActiveId,
    seed,
    perceive,
    dream,
    editDecision,
    promoteBranch,
    killOrganism,
    addSource,
    removeSource,
    loadSkills,
    getSkill,
    getSkillLineage,
    deleteSkill,
    switchStrategy,
    toggleMetaCognition,
    loadMetaCognition,
    refreshStatus: loadStatus,
    refreshGraph: () => activeId && loadCausality(activeId),
    refreshOrganisms: loadOrganisms,
  }
}
