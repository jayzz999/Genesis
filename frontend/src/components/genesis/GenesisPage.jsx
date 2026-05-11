import React, { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { useGenesis } from '../../hooks/useGenesis'
import OrganismNucleus from './OrganismNucleus'
import CausalGraph from './CausalGraph'
import DecisionInspector from './DecisionInspector'
import DreamStream from './DreamStream'
import SkillLibrary from './SkillLibrary'
import Tour from './Tour'
import { ORGANISM_TEMPLATES } from './templates'
import InheritancePicker from './InheritancePicker'
import MetaCognitionPanel from './MetaCognitionPanel'
const PopulationRunner = lazy(() => import('./PopulationRunner'))
const MemoryPanel = lazy(() => import('./MemoryPanel'))
const ToolSandboxPanel = lazy(() => import('./ToolSandboxPanel'))
const DebateRoomPanel = lazy(() => import('./DebateRoomPanel'))
const SelfImprovementPanel = lazy(() => import('./SelfImprovementPanel'))
const OperatorPanel = lazy(() => import('./OperatorPanel'))
const ApprovalPanel = lazy(() => import('./ApprovalPanel'))
const PermissionPanel = lazy(() => import('./PermissionPanel'))
const ConnectorPanel = lazy(() => import('./ConnectorPanel'))
const LocalConnectorPanel = lazy(() => import('./LocalConnectorPanel'))
const ApprovalPolicyPanel = lazy(() => import('./ApprovalPolicyPanel'))
const ApprovalIntegrityPanel = lazy(() => import('./ApprovalIntegrityPanel'))
const ApprovalGovernancePanel = lazy(() => import('./ApprovalGovernancePanel'))
const AssuranceOpsPanel = lazy(() => import('./AssuranceOpsPanel'))
const CapabilityGrowthPanel = lazy(() => import('./CapabilityGrowthPanel'))
const ProductIntelligencePanel = lazy(() => import('./ProductIntelligencePanel'))
const ReliabilityMissionPanel = lazy(() => import('./ReliabilityMissionPanel'))
const WorldModelPanel = lazy(() => import('./WorldModelPanel'))
const NervousSystemPanel = lazy(() => import('./NervousSystemPanel'))

const API_TOKEN = import.meta.env.VITE_GENESIS_API_TOKEN
  || (typeof window !== 'undefined' ? window.localStorage.getItem('GENESIS_API_TOKEN') : '')
  || ''

function sessionToken() {
  return typeof window !== 'undefined' ? window.localStorage.getItem('GENESIS_SESSION_TOKEN') || '' : ''
}

function authHeaders(headers = {}) {
  const session = sessionToken()
  return {
    ...headers,
    ...(API_TOKEN ? { 'X-Genesis-Token': API_TOKEN } : {}),
    ...(session ? { 'X-Genesis-Session': session } : {}),
  }
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

function PanelSuspense({ children }) {
  return (
    <Suspense fallback={<div className="h-full p-4 text-xs text-forge-muted">Loading workspace...</div>}>
      {children}
    </Suspense>
  )
}

export default function GenesisPage() {
  const g = useGenesis()
  const {
    connected, organisms, activeId, setActiveId, graph, branches, eventLog,
    acting, dreaming, seed, perceive, dream, editDecision, promoteBranch, killOrganism,
    addSource, removeSource,
    skills, getSkill, getSkillLineage, deleteSkill,
    metaCognition, switchStrategy, toggleMetaCognition, lastError,
    runtimeStatus, pendingActions, refreshStatus,
  } = g

  const [selectedDecision, setSelectedDecision] = useState(null)
  const [showSeedModal, setShowSeedModal] = useState(false)
  const [showLibrary, setShowLibrary] = useState(false)
  const [tourOpen, setTourOpen] = useState(false)
  const [seedFromSkillId, setSeedFromSkillId] = useState(null)
  const [perceiveJson, setPerceiveJson] = useState('{\n  "type": "test_event",\n  "payload": {}\n}')
  const [perceiveError, setPerceiveError] = useState(null)
  const [centerTab, setCenterTab] = useState('home')
  const [showAdvancedRail, setShowAdvancedRail] = useState(false)
  const [showAdvancedWorkspace, setShowAdvancedWorkspace] = useState(false)
  const [organismQuery, setOrganismQuery] = useState('')
  const [organismPage, setOrganismPage] = useState(0)

  const activeOrganism = organisms.find(o => o.id === activeId)
  const organismBusy = acting || dreaming || pendingActions.perceive || pendingActions.dream
  const backendOnline = Boolean(runtimeStatus && !lastError)
  const connectionOnline = connected || backendOnline
  const coreNavigationSections = [
    {
      id: 'home',
      label: 'Home',
      defaultTab: 'home',
      items: [
        { id: 'home', label: 'Dashboard' },
      ],
    },
    {
      id: 'work',
      label: 'Operations',
      defaultTab: 'connector',
      items: [
        { id: 'connector', label: 'Integrations' },
        { id: 'approval', label: 'Approvals' },
        { id: 'operator', label: 'Automation' },
      ],
    },
    {
      id: 'organism',
      label: 'Organism',
      defaultTab: 'graph',
      items: [
        { id: 'graph', label: 'Memory Graph' },
        { id: 'nervous', label: 'Life Systems' },
        { id: 'memory', label: 'Memory' },
      ],
    },
    {
      id: 'measure',
      label: 'Analytics',
      defaultTab: 'population',
      items: [
        { id: 'population', label: 'Benchmarks' },
        { id: 'reliability', label: 'Reliability' },
        { id: 'world', label: 'World Model' },
      ],
    },
    {
      id: 'settings',
      label: 'Settings',
      defaultTab: 'settings',
      items: [
        { id: 'settings', label: 'Runtime' },
      ],
    },
  ]
  const advancedNavigationSection = {
    id: 'advanced',
    label: 'Advanced',
    defaultTab: 'permission',
    items: [
      { id: 'permission', label: 'Permissions' },
      { id: 'policy', label: 'Policy Gate' },
      { id: 'integrity', label: 'Integrity' },
      { id: 'governance', label: 'Governance' },
      { id: 'tools', label: 'Execution Sandbox' },
      { id: 'local_connector', label: 'Local Artifacts' },
      { id: 'debate', label: 'Review Board' },
      { id: 'improve', label: 'Improvement Gates' },
      { id: 'assurance', label: 'Assurance' },
      { id: 'intelligence', label: 'Product Intelligence' },
      { id: 'capability', label: 'Capabilities' },
    ],
  }
  const navigationSections = showAdvancedWorkspace
    ? [...coreNavigationSections, advancedNavigationSection]
    : coreNavigationSections
  const visibleTabIds = new Set(navigationSections.flatMap(section => section.items.map(item => item.id)))
  const safeCenterTab = visibleTabIds.has(centerTab) ? centerTab : 'home'
  const activeTab = safeCenterTab
  useEffect(() => {
    if (safeCenterTab !== centerTab) setCenterTab(safeCenterTab)
  }, [safeCenterTab, centerTab])
  const activeSection = navigationSections.find(section => section.items.some(item => item.id === activeTab)) || navigationSections[0]
  const hiddenLeftRailTabs = new Set(navigationSections.flatMap(section => section.items.map(item => item.id)).filter(id => !['home', 'graph'].includes(id)))
  const organismPageSize = 25
  const filteredOrganisms = useMemo(() => {
    const query = organismQuery.trim().toLowerCase()
    if (!query) return organisms
    return organisms.filter(o => {
      const haystack = [
        o.id,
        o.name,
        o.intent?.goal,
        ...(o.intent?.constraints || []),
      ].filter(Boolean).join(' ').toLowerCase()
      return haystack.includes(query)
    })
  }, [organismQuery, organisms])
  const organismPageCount = Math.max(1, Math.ceil(filteredOrganisms.length / organismPageSize))
  const safeOrganismPage = Math.min(organismPage, organismPageCount - 1)
  const visibleOrganisms = filteredOrganisms.slice(
    safeOrganismPage * organismPageSize,
    safeOrganismPage * organismPageSize + organismPageSize,
  )

  useEffect(() => {
    if (safeOrganismPage !== organismPage) setOrganismPage(safeOrganismPage)
  }, [safeOrganismPage, organismPage])
  useEffect(() => {
    setOrganismPage(0)
  }, [organismQuery])

  const handleEdit = async (decisionId, payload) => {
    await editDecision(activeId, decisionId, payload)
    // graph auto-refreshes via WS event
  }
  const handlePromote = async (branchId) => {
    await promoteBranch(activeId, branchId)
  }

  const sendPerceive = async () => {
    setPerceiveError(null)
    let parsed
    try { parsed = JSON.parse(perceiveJson) }
    catch (e) { setPerceiveError(e.message); return }
    try {
      await perceive(activeId, parsed)
    } catch (e) {
      setPerceiveError(e.message || 'Perception failed')
    }
  }

  return (
    <div className="h-screen flex flex-col bg-forge-bg text-forge-text overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-forge-border glass">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-fuchsia-500 via-purple-500 to-indigo-500 flex items-center justify-center font-bold text-sm shadow-lg shadow-purple-500/30">
            G
          </div>
          <h1 className="text-lg font-semibold tracking-tight">Genesis</h1>
          <span className="text-xs text-forge-muted px-2 py-0.5 rounded-full bg-purple-500/10 border border-purple-500/30 text-purple-300">
            Living Digital Organisms
          </span>
        </div>
        <div className="flex items-center gap-3">
          {lastError && (
            <div
              className="max-w-[320px] truncate text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded px-2 py-1"
              title={lastError}
            >
              {lastError}
            </div>
          )}
          {runtimeStatus?.llm && (
            <button
              onClick={refreshStatus}
              className="text-xs px-2 py-1 rounded border border-forge-border bg-forge-border/30 text-forge-muted hover:text-forge-text"
              title={`Model: ${runtimeStatus.llm.model}`}
            >
              {runtimeStatus.llm.provider === 'mock' ? 'development provider' : runtimeStatus.llm.provider}
              {runtimeStatus.lifecycle?.enabled ? ' · live' : ' · manual'}
            </button>
          )}
          <div
            className={`flex items-center gap-2 text-xs ${connectionOnline ? 'text-forge-success' : 'text-forge-error'}`}
            title={connected ? 'Backend API and realtime stream connected' : backendOnline ? 'Backend API connected; realtime stream reconnecting' : 'Backend API disconnected'}
          >
            <div className={`w-2 h-2 rounded-full ${connectionOnline ? 'bg-forge-success animate-pulse' : 'bg-forge-error'}`} />
            {connectionOnline ? 'Connected' : 'Disconnected'}
          </div>
          <button
            onClick={() => setShowLibrary(true)}
            className="text-xs px-3 py-1.5 rounded-lg bg-forge-border/50 hover:bg-purple-500/20 border border-forge-border"
            title="Browse the Skill pool"
          >Skills ({skills.length})</button>
          <button
            onClick={() => setTourOpen(true)}
            className="text-xs px-3 py-1.5 rounded-lg bg-purple-500/20 hover:bg-purple-500/40 border border-purple-500/40 text-purple-200"
          >Tour</button>
          <button
            onClick={() => setShowAdvancedWorkspace(v => !v)}
            className="text-xs px-3 py-1.5 rounded-lg bg-forge-border/40 hover:bg-forge-border/70 border border-forge-border text-forge-muted hover:text-forge-text"
          >
            {showAdvancedWorkspace ? 'Hide advanced' : 'Show advanced'}
          </button>
          <button
            onClick={() => setShowSeedModal(true)}
            className="text-xs px-3 py-1.5 rounded-lg bg-gradient-to-r from-fuchsia-500/20 to-indigo-500/20 hover:from-fuchsia-500/40 hover:to-indigo-500/40 border border-purple-500/40 text-purple-200"
          >
            Create organism
          </button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden relative">
        {/* Left rail: organism list + nucleus + controls */}
        <div className={`${hiddenLeftRailTabs.has(activeTab) ? 'hidden' : 'flex'} w-[340px] min-w-[300px] border-r border-forge-border flex-col overflow-y-auto overflow-x-hidden`}>
          <div className="p-3 border-b border-forge-border">
            <div className="text-[10px] uppercase tracking-widest text-forge-muted mb-2">Organisms ({organisms.length})</div>
            <input
              value={organismQuery}
              onChange={e => setOrganismQuery(e.target.value)}
              placeholder="Filter organisms"
              className="mb-2 w-full rounded border border-forge-border bg-forge-panel/60 px-2 py-1.5 text-xs text-forge-text outline-none focus:border-purple-400"
            />
            <div className="space-y-1 max-h-40 overflow-auto">
              {visibleOrganisms.map(o => (
                <button
                  key={o.id}
                  onClick={() => setActiveId(o.id)}
                  className={`w-full text-left px-2 py-1.5 rounded text-xs flex items-center justify-between group ${
                    o.id === activeId ? 'bg-purple-500/20 border border-purple-400/40' : 'hover:bg-forge-border/40'
                  }`}
                >
                  <div className="truncate">
                    <div className="font-medium truncate">{o.name || o.id}</div>
                    <div className="text-[10px] text-forge-muted truncate italic">{o.intent?.goal}</div>
                  </div>
                  <span
                    className={`text-forge-muted ml-2 ${pendingActions.kill ? 'opacity-30' : 'hover:text-red-400 opacity-0 group-hover:opacity-100'}`}
                    onClick={(e) => {
                      e.stopPropagation()
                      if (!pendingActions.kill && confirm('Let this organism die?')) killOrganism(o.id)
                    }}
                  >Delete</span>
                </button>
              ))}
              {organisms.length === 0 && (
                <div className="text-xs text-forge-muted italic text-center py-4">No organisms yet. Create one.</div>
              )}
              {organisms.length > 0 && filteredOrganisms.length === 0 && (
                <div className="text-xs text-forge-muted italic text-center py-4">No organisms match this filter.</div>
              )}
            </div>
            {filteredOrganisms.length > organismPageSize && (
              <div className="mt-2 flex items-center justify-between gap-2 text-[10px] text-forge-muted">
                <button
                  type="button"
                  onClick={() => setOrganismPage(page => Math.max(0, page - 1))}
                  disabled={safeOrganismPage === 0}
                  className="rounded border border-forge-border bg-forge-panel/60 px-2 py-1 hover:text-forge-text disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Prev
                </button>
                <span className="font-mono">
                  {safeOrganismPage + 1}/{organismPageCount} · {filteredOrganisms.length} shown
                </span>
                <button
                  type="button"
                  onClick={() => setOrganismPage(page => Math.min(organismPageCount - 1, page + 1))}
                  disabled={safeOrganismPage >= organismPageCount - 1}
                  className="rounded border border-forge-border bg-forge-panel/60 px-2 py-1 hover:text-forge-text disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            )}
          </div>

          <div className="p-3 border-b border-forge-border">
            <OrganismNucleus
              organism={activeOrganism}
              acting={acting}
              dreaming={dreaming}
              connected={connected}
            />
          </div>

          <div className="p-3 border-b border-forge-border">
            <button
              onClick={() => setShowAdvancedRail(v => !v)}
              className="w-full rounded-lg border border-forge-border bg-forge-panel/40 px-3 py-2 text-xs text-forge-text hover:bg-forge-border/40"
            >
              {showAdvancedRail ? 'Hide advanced organism controls' : 'Show advanced organism controls'}
            </button>
          </div>

          {activeOrganism && showAdvancedRail && (
            <SourceRail
              organism={activeOrganism}
              onAdd={(s) => addSource(activeId, s)}
              onRemove={(i) => removeSource(activeId, i)}
              busy={pendingActions.source}
            />
          )}

          {activeOrganism && showAdvancedRail && (
            <div className="p-3 border-b border-forge-border space-y-2">
              <div className="text-[10px] uppercase tracking-widest text-forge-muted">Inject perception</div>
              <textarea
                className="w-full h-24 bg-forge-border/30 rounded p-2 text-[11px] font-mono border border-forge-border focus:outline-none focus:border-purple-400"
                value={perceiveJson}
                onChange={e => setPerceiveJson(e.target.value)}
              />
              {perceiveError && <div className="text-[10px] text-red-400">{perceiveError}</div>}
              <div className="flex gap-2">
                <button
                  onClick={sendPerceive}
                  disabled={organismBusy}
                  className="flex-1 px-2 py-1.5 rounded bg-cyan-500/20 hover:bg-cyan-500/40 border border-cyan-400/40 text-cyan-200 text-xs disabled:opacity-40 disabled:cursor-not-allowed"
                >{pendingActions.perceive ? 'Perceiving...' : '👁 Perceive'}</button>
                <button
                  onClick={async () => {
                    try { await dream(activeId, 2) }
                    catch (e) { setPerceiveError(e.message || 'Dream failed') }
                  }}
                  disabled={organismBusy}
                  className="flex-1 px-2 py-1.5 rounded bg-fuchsia-500/20 hover:bg-fuchsia-500/40 border border-fuchsia-400/40 text-fuchsia-200 text-xs disabled:opacity-40 disabled:cursor-not-allowed"
                >{pendingActions.dream ? 'Dreaming...' : '💭 Dream ×2'}</button>
              </div>
            </div>
          )}

          {showAdvancedRail && (
          <div className="flex-1 overflow-hidden flex flex-col">
            <div className="flex-1 overflow-hidden border-b border-forge-border">
              <DreamStream events={eventLog} />
            </div>
            
            {/* Phase 5A: Meta-Cognition Panel */}
            <div className="flex-1 overflow-hidden">
              <div className="h-full overflow-y-auto p-2">
                <MetaCognitionPanel 
                  metaCognition={metaCognition} 
                  activeId={activeId}
                  switchStrategy={switchStrategy}
                  toggleMetaCognition={toggleMetaCognition}
                />
              </div>
            </div>
          </div>
          )}
        </div>

        {/* Center: tab bar + panel */}
        <div className="flex-1 flex flex-col bg-forge-bg/40 overflow-hidden">
          {/* Tab bar */}
          <div className="border-b border-forge-border shrink-0">
            <div className="flex items-center gap-1 px-3 pt-2">
              {navigationSections.map(section => (
                <button
                  key={section.id}
                  onClick={() => setCenterTab(section.defaultTab)}
                  className={`text-xs px-3 py-1.5 rounded-t-lg border-b-2 transition-colors ${
                    activeSection.id === section.id
                      ? 'border-purple-400 text-purple-200 bg-purple-500/10'
                      : 'border-transparent text-forge-muted hover:text-forge-text'
                  }`}
                >
                  {section.label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1 px-3 py-2 bg-forge-bg/30 overflow-x-auto">
              {activeSection.items.map(tab => (
              <button
                key={tab.id}
                onClick={() => setCenterTab(tab.id)}
                className={`text-[11px] px-2.5 py-1 rounded border transition-colors whitespace-nowrap ${
                  activeTab === tab.id
                    ? 'border-purple-400/60 text-purple-100 bg-purple-500/20'
                    : 'border-forge-border text-forge-muted hover:text-forge-text hover:bg-forge-border/30'
                }`}
              >
                {tab.label}
              </button>
              ))}
            </div>
          </div>

          {/* Home panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'home' ? 'hidden' : ''}`}>
            <MissionHomePanel
              activeOrganism={activeOrganism}
              organisms={organisms}
              runtimeStatus={runtimeStatus}
              connectionOnline={connectionOnline}
              eventLog={eventLog}
              onSeed={() => setShowSeedModal(true)}
              onNavigate={setCenterTab}
              refreshStatus={refreshStatus}
            />
          </div>

          {/* Graph panel */}
          <div className={`flex-1 relative ${activeTab !== 'graph' ? 'hidden' : ''}`}>
          {activeId ? (
            <CausalGraph graph={graph} onSelectDecision={setSelectedDecision} />
          ) : (
            <div className="h-full flex items-center justify-center text-forge-muted">
              <div className="text-center">
                <div className="text-4xl mb-3">🧬</div>
                <div className="text-sm">Select or create an organism to see its causal graph</div>
              </div>
            </div>
          )}

          {/* Branch counter */}
          {branches.length > 0 && (
            <div className="absolute top-3 left-3 px-3 py-1.5 rounded-full bg-purple-500/20 border border-purple-400/40 text-purple-200 text-xs">
              🌌 {branches.length} counterfactual branch{branches.length === 1 ? '' : 'es'}
            </div>
          )}

          {/* Inspector slide-in */}
          {selectedDecision && (
            <DecisionInspector
              decision={selectedDecision}
              branches={branches}
              onClose={() => setSelectedDecision(null)}
              onEdit={handleEdit}
              onPromoteBranch={handlePromote}
              editPending={pendingActions.edit}
              promotePending={pendingActions.promote}
            />
          )}
          </div>

          {/* Population panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'population' ? 'hidden' : ''}`}>
            {activeTab === 'population' && <PanelSuspense><PopulationRunner eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Memory panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'memory' ? 'hidden' : ''}`}>
            {activeTab === 'memory' && <PanelSuspense><MemoryPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Organism nervous system panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'nervous' ? 'hidden' : ''}`}>
            {activeTab === 'nervous' && <PanelSuspense><NervousSystemPanel activeOrganism={activeOrganism} eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Tool sandbox panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'tools' ? 'hidden' : ''}`}>
            {activeTab === 'tools' && <PanelSuspense><ToolSandboxPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Debate room panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'debate' ? 'hidden' : ''}`}>
            {activeTab === 'debate' && <PanelSuspense><DebateRoomPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Self-improvement panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'improve' ? 'hidden' : ''}`}>
            {activeTab === 'improve' && <PanelSuspense><SelfImprovementPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Autonomous operator panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'operator' ? 'hidden' : ''}`}>
            {activeTab === 'operator' && <PanelSuspense><OperatorPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Human approval panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'approval' ? 'hidden' : ''}`}>
            {activeTab === 'approval' && <PanelSuspense><ApprovalPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Scoped permission grants panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'permission' ? 'hidden' : ''}`}>
            {activeTab === 'permission' && <PanelSuspense><PermissionPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Permission-gated connector adapters panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'connector' ? 'hidden' : ''}`}>
            {activeTab === 'connector' && <PanelSuspense><ConnectorPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Permission-gated local artifact connector panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'local_connector' ? 'hidden' : ''}`}>
            {activeTab === 'local_connector' && <PanelSuspense><LocalConnectorPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Strict policy review and execution confirmation panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'policy' ? 'hidden' : ''}`}>
            {activeTab === 'policy' && <PanelSuspense><ApprovalPolicyPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Tamper-evident approval ledger panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'integrity' ? 'hidden' : ''}`}>
            {activeTab === 'integrity' && <PanelSuspense><ApprovalIntegrityPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Dual-control approval governance panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'governance' ? 'hidden' : ''}`}>
            {activeTab === 'governance' && <PanelSuspense><ApprovalGovernancePanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Assurance and operations control plane */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'assurance' ? 'hidden' : ''}`}>
            {activeTab === 'assurance' && <PanelSuspense><AssuranceOpsPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Capability growth control plane */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'capability' ? 'hidden' : ''}`}>
            {activeTab === 'capability' && <PanelSuspense><CapabilityGrowthPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Product intelligence and release management panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'intelligence' ? 'hidden' : ''}`}>
            {activeTab === 'intelligence' && <PanelSuspense><ProductIntelligencePanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Reliability and mission execution panel */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'reliability' ? 'hidden' : ''}`}>
            {activeTab === 'reliability' && <PanelSuspense><ReliabilityMissionPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* World model and mission learning */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'world' ? 'hidden' : ''}`}>
            {activeTab === 'world' && <PanelSuspense><WorldModelPanel eventLog={eventLog} /></PanelSuspense>}
          </div>

          {/* Runtime settings and readiness */}
          <div className={`flex-1 overflow-hidden ${activeTab !== 'settings' ? 'hidden' : ''}`}>
            <RuntimeSettingsPanel runtimeStatus={runtimeStatus} lastError={lastError} refreshStatus={refreshStatus} />
          </div>
        </div>
      </div>

      {showSeedModal && (
        <SeedModal
          skills={skills}
          prefillSkillId={seedFromSkillId}
          onClose={() => { setShowSeedModal(false); setSeedFromSkillId(null) }}
          onSeed={async (data) => { await seed(data); setShowSeedModal(false); setSeedFromSkillId(null) }}
          busy={pendingActions.seed}
        />
      )}

      {showLibrary && (
        <SkillLibrary
          skills={skills}
          getSkill={getSkill}
          getSkillLineage={getSkillLineage}
          deleteSkill={deleteSkill}
          deleting={pendingActions.skill}
          onClose={() => setShowLibrary(false)}
          onSeedFromSkill={(id) => { setSeedFromSkillId(id); setShowLibrary(false); setShowSeedModal(true) }}
        />
      )}

      <Tour open={tourOpen} onClose={() => setTourOpen(false)} g={g} />
    </div>
  )
}

function MissionHomePanel({
  activeOrganism,
  organisms,
  runtimeStatus,
  connectionOnline,
  eventLog,
  onSeed,
  onNavigate,
  refreshStatus,
}) {
  const latestEvent = eventLog?.[0]
  const lifecycle = runtimeStatus?.lifecycle || {}
  const llm = runtimeStatus?.llm || {}
  const organismCount = organisms.length
  const activeGoal = activeOrganism?.intent?.goal || 'No organism selected'
  const providerLabel = llm.provider === 'mock' ? 'Development provider' : llm.provider || 'Not configured'

  const statusItems = [
    { label: 'Backend', value: connectionOnline ? 'Connected' : 'Offline', tone: connectionOnline ? 'good' : 'bad' },
    { label: 'Mode', value: lifecycle.enabled ? 'Autonomous' : 'Manual', tone: lifecycle.enabled ? 'good' : 'neutral' },
    { label: 'AI Provider', value: providerLabel, tone: llm.provider === 'mock' ? 'warn' : 'good' },
    { label: 'Organisms', value: String(organismCount), tone: organismCount ? 'good' : 'neutral' },
  ]

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-6xl">
        <section className="mb-5 border-b border-forge-border pb-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-widest text-forge-muted">Genesis operations dashboard</div>
              <h2 className="mt-2 text-2xl font-semibold text-forge-text">Operate autonomous digital workers.</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-forge-muted">
                Connect real systems, review proposed actions, and measure outcomes before scaling automation.
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={onSeed}
                className="rounded-lg border border-purple-400/50 bg-purple-500/20 px-4 py-2 text-sm text-purple-100 hover:bg-purple-500/30"
              >
                Create organism
              </button>
              <button
                onClick={() => onNavigate('connector')}
                className="rounded-lg border border-cyan-400/40 bg-cyan-500/15 px-4 py-2 text-sm text-cyan-100 hover:bg-cyan-500/25"
              >
                Configure integrations
              </button>
            </div>
          </div>
        </section>

        <section className="mb-5 grid gap-3 md:grid-cols-4">
          {statusItems.map(item => (
            <div key={item.label} className="border-b border-forge-border pb-3">
              <div className="text-[10px] uppercase tracking-widest text-forge-muted">{item.label}</div>
              <div className={`mt-1 font-mono text-sm ${
                item.tone === 'good' ? 'text-emerald-300' : item.tone === 'bad' ? 'text-red-300' : item.tone === 'warn' ? 'text-amber-200' : 'text-forge-text'
              }`}>
                {item.value}
              </div>
            </div>
          ))}
        </section>

        <section className="grid gap-5 xl:grid-cols-[1fr_360px]">
          <div className="space-y-5">
            <div className="border border-forge-border bg-forge-panel/30 p-5">
              <div className="mb-1 text-[10px] uppercase tracking-widest text-forge-muted">Current organism</div>
              <h3 className="text-lg font-medium text-forge-text">{activeOrganism?.name || 'No organism selected'}</h3>
              <p className="mt-2 line-clamp-3 text-sm leading-6 text-forge-muted">{activeGoal}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  onClick={() => onNavigate('graph')}
                  disabled={!activeOrganism}
                  className="rounded border border-forge-border bg-forge-bg/60 px-3 py-1.5 text-xs text-forge-text hover:bg-forge-border/40 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Memory graph
                </button>
                <button
                  onClick={() => onNavigate('nervous')}
                  disabled={!activeOrganism}
                  className="rounded border border-forge-border bg-forge-bg/60 px-3 py-1.5 text-xs text-forge-text hover:bg-forge-border/40 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Life systems
                </button>
                <button
                  onClick={() => onNavigate('population')}
                  className="rounded border border-forge-border bg-forge-bg/60 px-3 py-1.5 text-xs text-forge-text hover:bg-forge-border/40"
                >
                  Benchmark
                </button>
              </div>
            </div>

            <div className="border border-forge-border bg-forge-panel/30 p-5">
              <div className="mb-3 text-sm font-medium text-forge-text">Operating workflow</div>
              <div className="divide-y divide-forge-border text-sm">
                {[
                  ['Connect systems', 'Verify GitHub, Slack, and API credentials before automation acts.', 'connector'],
                  ['Review action queue', 'Approve, deny, or refine external actions before execution.', 'approval'],
                  ['Measure outcomes', 'Track success rates, regressions, and reliability over time.', 'reliability'],
                ].map(([title, detail, tab]) => (
                  <button
                    key={title}
                    onClick={() => onNavigate(tab)}
                    className="flex w-full items-center justify-between gap-4 py-3 text-left hover:text-purple-100"
                  >
                    <span>
                      <span className="block text-forge-text">{title}</span>
                      <span className="mt-1 block text-xs leading-5 text-forge-muted">{detail}</span>
                    </span>
                    <span className="text-forge-muted">Open</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <aside className="border border-forge-border bg-forge-panel/30 p-5">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-forge-text">System snapshot</div>
              <div className="text-[10px] text-forge-muted">What is live right now</div>
              </div>
              <button
                onClick={refreshStatus}
                className="rounded border border-forge-border bg-forge-bg/60 px-2 py-1 text-[10px] text-forge-muted hover:text-forge-text"
              >
                Refresh
              </button>
            </div>
            <div className="divide-y divide-forge-border text-xs">
              <SnapshotRow label="Backend API" value={connectionOnline ? 'connected' : 'disconnected'} good={connectionOnline} />
              <SnapshotRow label="AI provider" value={providerLabel} good={llm.provider && llm.provider !== 'mock'} warn={llm.provider === 'mock'} />
              <SnapshotRow label="Model" value={llm.model || 'unknown'} />
              <SnapshotRow label="Latest event" value={latestEvent?.type || 'none'} />
            </div>
          </aside>
        </section>
      </div>
    </div>
  )
}

function SnapshotRow({ label, value, good, warn }) {
  return (
    <div className="flex items-center justify-between gap-3 py-3">
      <span className="text-forge-muted">{label}</span>
      <span className={`truncate text-right font-mono ${
        good ? 'text-emerald-300' : warn ? 'text-amber-200' : 'text-forge-text'
      }`}>
        {value}
      </span>
    </div>
  )
}

function RuntimeSettingsPanel({ runtimeStatus, lastError, refreshStatus }) {
  const llm = runtimeStatus?.llm || {}
  const lifecycle = runtimeStatus?.lifecycle || {}
  const longTerm = runtimeStatus?.long_term || {}
  const database = longTerm?.database || {}
  const auth = longTerm?.auth || {}
  const health = runtimeStatus && !lastError ? 'ready' : 'needs attention'
  const [username, setUsername] = useState('owner')
  const [password, setPassword] = useState('')
  const [authMessage, setAuthMessage] = useState('')
  const [authBusy, setAuthBusy] = useState(false)
  const [reconciliation, setReconciliation] = useState(null)
  const [reconciliationBusy, setReconciliationBusy] = useState(false)
  const [reconciliationMessage, setReconciliationMessage] = useState('')

  const authHeaders = () => {
    const staticToken = window.localStorage.getItem('GENESIS_API_TOKEN') || ''
    const sessionToken = window.localStorage.getItem('GENESIS_SESSION_TOKEN') || ''
    return {
      'Content-Type': 'application/json',
      ...(staticToken ? { 'X-Genesis-Token': staticToken } : {}),
      ...(sessionToken ? { 'X-Genesis-Session': sessionToken } : {}),
    }
  }

  const callAuth = async (path, body) => {
    setAuthBusy(true)
    setAuthMessage('')
    try {
      const response = await fetch(path, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(body),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || data.error || 'Auth request failed')
      if (data.token) window.localStorage.setItem('GENESIS_SESSION_TOKEN', data.token)
      setAuthMessage(data.token ? `signed in as ${data.user?.username}` : `created ${data.user?.username}`)
      await refreshStatus()
    } catch (e) {
      setAuthMessage(e.message)
    } finally {
      setAuthBusy(false)
    }
  }

  const checkReconciliation = async () => {
    setReconciliationBusy(true)
    setReconciliationMessage('')
    try {
      const data = await apiRequest('/api/genesis/long-term/reconciliation')
      setReconciliation(data)
      setReconciliationMessage(data.ok ? 'mirror is current' : 'mirror drift detected')
    } catch (e) {
      setReconciliationMessage(e.message || 'Reconciliation check failed')
    } finally {
      setReconciliationBusy(false)
    }
  }

  const repairReconciliation = async () => {
    const missing = reconciliation?.summary?.missing_total ?? 0
    if (!window.confirm(`Repair SQLite mirror from JSON source of truth? ${missing} missing record(s) may be written.`)) {
      return
    }
    setReconciliationBusy(true)
    setReconciliationMessage('')
    try {
      const data = await apiRequest('/api/genesis/long-term/reconciliation/repair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: true }),
      })
      setReconciliation(data)
      setReconciliationMessage(`repaired ${data.summary?.repaired_total ?? 0} record(s)`)
      await refreshStatus()
    } catch (e) {
      setReconciliationMessage(e.message || 'Reconciliation repair failed')
    } finally {
      setReconciliationBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-forge-text">Runtime Settings</h3>
          <p className="text-[10px] text-forge-muted">
            Provider status, lifecycle mode, health, and deployment readiness.
          </p>
        </div>
        <button
          onClick={refreshStatus}
          className="rounded border border-forge-border bg-forge-panel/60 px-3 py-1.5 text-xs text-forge-text hover:bg-forge-border/40"
        >
          Refresh status
        </button>
      </div>

      {lastError && (
        <div className="mb-4 rounded border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
          {lastError}
        </div>
      )}

      <section className="grid gap-3 md:grid-cols-3">
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-4">
          <div className="text-[10px] text-forge-muted">health</div>
          <div className="mt-1 text-sm font-mono text-forge-text">{health}</div>
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-4">
          <div className="text-[10px] text-forge-muted">provider</div>
          <div className="mt-1 text-sm font-mono text-forge-text">{llm.provider === 'mock' ? 'development provider' : llm.provider || 'unknown'}</div>
        </div>
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-4">
          <div className="text-[10px] text-forge-muted">lifecycle</div>
          <div className="mt-1 text-sm font-mono text-forge-text">{lifecycle.enabled ? 'live' : 'manual'}</div>
        </div>
      </section>

      <section className="mt-4 grid gap-3 lg:grid-cols-2">
        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-4">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <div className="text-xs font-medium text-forge-text">Long-Term Database</div>
              <div className="text-[10px] text-forge-muted">SQLite identity, audit, organism, and decision records.</div>
            </div>
            <span className={`rounded border px-2 py-1 text-[10px] ${database.connected ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-red-500/30 bg-red-500/10 text-red-300'}`}>
              {longTerm.readiness || 'unknown'}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <div className="rounded border border-forge-border bg-forge-bg/50 p-2">
              <div className="text-forge-muted">engine</div>
              <div className="mt-1 font-mono text-forge-text">{database.engine || 'unknown'}</div>
            </div>
            <div className="rounded border border-forge-border bg-forge-bg/50 p-2">
              <div className="text-forge-muted">journal</div>
              <div className="mt-1 font-mono text-forge-text">{database.journal_mode || 'n/a'}</div>
            </div>
            <div className="rounded border border-forge-border bg-forge-bg/50 p-2">
              <div className="text-forge-muted">organisms</div>
              <div className="mt-1 font-mono text-forge-text">{database.tables?.organism_records ?? 0}</div>
            </div>
            <div className="rounded border border-forge-border bg-forge-bg/50 p-2">
              <div className="text-forge-muted">decisions</div>
              <div className="mt-1 font-mono text-forge-text">{database.tables?.decision_records ?? 0}</div>
            </div>
          </div>
          <div className="mt-3 truncate text-[10px] text-forge-muted" title={database.path}>{database.path || 'no database path'}</div>
          <div className="mt-3 border-t border-forge-border pt-3">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-forge-text">JSON mirror reconciliation</div>
                <div className="text-[10px] text-forge-muted">JSON remains authoritative; repair only backfills SQLite mirror rows.</div>
              </div>
              <span className={`rounded border px-2 py-1 text-[10px] ${
                reconciliation?.ok
                  ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                  : reconciliation
                    ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                    : 'border-forge-border bg-forge-bg/60 text-forge-muted'
              }`}>
                {reconciliation ? (reconciliation.ok ? 'current' : 'drift') : 'unchecked'}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[10px]">
              <div className="rounded border border-forge-border bg-forge-bg/50 p-2">
                <div className="text-forge-muted">missing rows</div>
                <div className="mt-1 font-mono text-forge-text">{reconciliation?.summary?.missing_total ?? 'n/a'}</div>
              </div>
              <div className="rounded border border-forge-border bg-forge-bg/50 p-2">
                <div className="text-forge-muted">repaired rows</div>
                <div className="mt-1 font-mono text-forge-text">{reconciliation?.summary?.repaired_total ?? 0}</div>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={reconciliationBusy}
                onClick={checkReconciliation}
                className="rounded border border-forge-border bg-forge-bg/70 px-3 py-1.5 text-xs text-forge-text hover:bg-forge-border/40 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Check mirror
              </button>
              <button
                type="button"
                disabled={reconciliationBusy || !reconciliation || reconciliation.ok}
                onClick={repairReconciliation}
                className="rounded border border-amber-400/40 bg-amber-500/20 px-3 py-1.5 text-xs text-amber-100 hover:bg-amber-500/30 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Repair mirror
              </button>
            </div>
            {reconciliationMessage && (
              <div className="mt-3 rounded border border-forge-border bg-forge-bg/60 p-2 text-[10px] text-forge-muted">
                {reconciliationMessage}
              </div>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-forge-border bg-forge-panel/40 p-4">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <div className="text-xs font-medium text-forge-text">Auth And Sessions</div>
              <div className="text-[10px] text-forge-muted">Bootstrap one owner, then use session tokens for protected actions.</div>
            </div>
            <span className="rounded border border-forge-border bg-forge-bg/60 px-2 py-1 text-[10px] text-forge-muted">
              {auth.active_sessions ?? 0} active
            </span>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <input
              className="rounded border border-forge-border bg-forge-bg/60 px-2 py-1.5 text-xs text-forge-text outline-none focus:border-purple-400"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="username"
            />
            <input
              className="rounded border border-forge-border bg-forge-bg/60 px-2 py-1.5 text-xs text-forge-text outline-none focus:border-purple-400"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="password"
              type="password"
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              disabled={authBusy || auth.users > 0 || password.length < 10}
              onClick={() => callAuth('/api/genesis/auth/bootstrap', { username, password, display_name: 'Genesis Operator' })}
              className="rounded border border-forge-border bg-forge-bg/70 px-3 py-1.5 text-xs text-forge-text hover:bg-forge-border/40 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Bootstrap owner
            </button>
            <button
              disabled={authBusy || password.length < 1}
              onClick={() => callAuth('/api/genesis/auth/login', { username, password, ttl_hours: 24 })}
              className="rounded border border-purple-500/40 bg-purple-500/20 px-3 py-1.5 text-xs text-purple-100 hover:bg-purple-500/30 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Sign in
            </button>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-[10px]">
            <div className="rounded border border-forge-border bg-forge-bg/50 p-2">
              <div className="text-forge-muted">users</div>
              <div className="mt-1 font-mono text-forge-text">{auth.users ?? 0}</div>
            </div>
            <div className="rounded border border-forge-border bg-forge-bg/50 p-2">
              <div className="text-forge-muted">token required</div>
              <div className="mt-1 font-mono text-forge-text">{auth.api_token_required ? 'yes' : 'no'}</div>
            </div>
          </div>
          {authMessage && <div className="mt-3 rounded border border-forge-border bg-forge-bg/60 p-2 text-[10px] text-forge-muted">{authMessage}</div>}
        </div>
      </section>

      <section className="mt-4 rounded-xl border border-forge-border p-4">
        <div className="mb-3 text-xs font-medium text-forge-text">Runtime snapshot</div>
        <pre className="max-h-[520px] overflow-auto rounded bg-forge-bg/70 p-3 text-[10px] text-forge-text">
          {JSON.stringify(runtimeStatus || {}, null, 2)}
        </pre>
      </section>
    </div>
  )
}

// ── Seed Modal ──────────────────────────────────────────────
function SeedModal({ onClose, onSeed, skills, prefillSkillId, busy }) {
  const [name, setName] = useState('')
  const [goal, setGoal] = useState('')
  const [constraintsText, setConstraintsText] = useState('')
  const [forbiddenText, setForbiddenText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [template, setTemplate] = useState(null)
  const [inheritIds, setInheritIds] = useState(prefillSkillId ? [prefillSkillId] : [])

  const applyTemplate = (t) => {
    setTemplate(t.id)
    setName(t.id === 'blank' ? '' : (t.seedName || t.name))
    setGoal(t.goal)
    setConstraintsText((t.constraints || []).join('\n'))
    setForbiddenText((t.forbidden || []).join('\n'))
  }

  const submit = async () => {
    if (!goal.trim()) return
    setError(null)
    setSubmitting(true)
    try {
      await onSeed({
        name: name.trim(),
        goal: goal.trim(),
        constraints: constraintsText.split('\n').map(s => s.trim()).filter(Boolean),
        forbidden: forbiddenText.split('\n').map(s => s.trim()).filter(Boolean),
        inherit_from: inheritIds,
      })
    } catch (e) {
      setError(e.message || 'Failed to seed organism')
    } finally { setSubmitting(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-forge-bg border border-purple-500/40 rounded-2xl p-6 w-[480px] shadow-2xl shadow-purple-500/20">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-2xl">🌱</span>
          <h2 className="text-lg font-semibold">Create organism</h2>
        </div>
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-2 mb-3">
            {ORGANISM_TEMPLATES.map(t => (
              <button key={t.id} type="button" onClick={() => applyTemplate(t)}
                      className={`text-xs px-2 py-1 rounded-full border ${
                        template===t.id ? 'bg-purple-500/30 border-purple-400 text-purple-100'
                                        : 'bg-forge-border/40 border-forge-border hover:bg-forge-border/60'
                      }`}>
                {t.icon} {t.name}
              </button>
            ))}
          </div>
          <Field label="Name (optional)">
            <input
              className="w-full bg-forge-border/30 rounded p-2 border border-forge-border focus:outline-none focus:border-purple-400"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. customer_pulse"
            />
          </Field>
          <Field label="Primary objective">
            <textarea
              className="w-full h-20 bg-forge-border/30 rounded p-2 border border-forge-border focus:outline-none focus:border-purple-400"
              value={goal}
              onChange={e => setGoal(e.target.value)}
              placeholder="Watch every customer email and act helpfully without ever spamming."
            />
          </Field>
          <Field label="Constraints (one per line)">
            <textarea
              className="w-full h-16 bg-forge-border/30 rounded p-2 border border-forge-border focus:outline-none focus:border-purple-400 font-mono text-xs"
              value={constraintsText}
              onChange={e => setConstraintsText(e.target.value)}
              placeholder="respond within 5 minutes&#10;use polite tone"
            />
          </Field>
          <Field label="Forbidden (one per line)">
            <textarea
              className="w-full h-16 bg-forge-border/30 rounded p-2 border border-forge-border focus:outline-none focus:border-purple-400 font-mono text-xs"
              value={forbiddenText}
              onChange={e => setForbiddenText(e.target.value)}
              placeholder="never share PII&#10;never make promises about pricing"
            />
          </Field>
          <Field label="Inherit skills from past organisms">
            <InheritancePicker skills={skills} selected={inheritIds} onChange={setInheritIds} />
          </Field>
          {error && (
            <div className="text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded p-2">
              {error}
            </div>
          )}
        </div>
        <div className="flex gap-2 mt-5">
          <button
            onClick={onClose}
            disabled={submitting || busy}
            className="flex-1 px-3 py-2 rounded bg-forge-border/50 hover:bg-forge-border text-sm disabled:opacity-40"
          >Cancel</button>
          <button
            onClick={submit}
            disabled={submitting || busy || !goal.trim()}
            className="flex-1 px-3 py-2 rounded bg-gradient-to-r from-fuchsia-500 to-indigo-500 hover:opacity-90 text-white text-sm font-medium disabled:opacity-30"
          >{submitting || busy ? 'Creating...' : 'Create organism'}</button>
        </div>
      </div>
    </div>
  )
}

// ── Perception Sources Rail ─────────────────────────────────
function SourceRail({ organism, onAdd, onRemove, busy }) {
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState('interval')
  const [type, setType] = useState('tick')
  const [interval, setInterval] = useState(60)
  const [url, setUrl] = useState('')

  const submit = async () => {
    const src = { kind, type, interval_s: Number(interval) || 60 }
    if (kind === 'http_poll') src.url = url
    await onAdd(src)
    setOpen(false); setUrl(''); setType('tick'); setKind('interval'); setInterval(60)
  }

  const sources = organism.perception_sources || []

  return (
    <div className="p-3 border-b border-forge-border">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] uppercase tracking-widest text-forge-muted">Perception sources ({sources.length})</div>
        <button
          onClick={() => setOpen(o => !o)}
          className="text-[10px] px-1.5 py-0.5 rounded border border-forge-border text-forge-muted hover:text-forge-text"
        >{open ? '−' : '+'}</button>
      </div>
      <div className="space-y-1">
        {sources.map((s, i) => (
          <div key={i} className="flex items-center gap-2 px-2 py-1 rounded bg-forge-border/30 text-[11px] group">
            <span className="text-cyan-300">
              {s.kind === 'interval' ? '⏱' : s.kind === 'http_poll' ? '🌐' : s.kind === 'github_repo' ? '👁' : '📬'}
            </span>
            <div className="flex-1 min-w-0">
              <div className="font-medium truncate">{s.type || s.kind}</div>
              <div className="text-[10px] text-forge-muted truncate">
                {s.kind === 'github_repo' && `${s.repo || 'configured repo'} · every ${s.interval_s || 1}s · approval gated`}
                {s.kind === 'http_poll' && s.url}
                {s.kind === 'webhook' && s.token && `POST /api/genesis/webhook/${s.token}`}
                {s.kind === 'interval' && `every ${s.interval_s}s`}
                {s.kind === 'http_poll' && ` · every ${s.interval_s}s`}
              </div>
            </div>
            <button
              onClick={() => !busy && onRemove(i)}
              className={`text-forge-muted opacity-0 group-hover:opacity-100 ${busy ? 'cursor-not-allowed' : 'hover:text-red-400'}`}
            >✕</button>
          </div>
        ))}
        {sources.length === 0 && !open && (
          <div className="text-[10px] text-forge-muted italic">No sources. Add one to run this organism autonomously.</div>
        )}
      </div>
      {open && (
        <div className="mt-2 space-y-2 text-xs">
          <select
            value={kind}
            onChange={e => setKind(e.target.value)}
            className="w-full bg-forge-border/30 rounded p-1.5 border border-forge-border focus:outline-none focus:border-purple-400"
          >
            <option value="interval">⏱ interval (heartbeat tick)</option>
            <option value="http_poll">🌐 http_poll (poll a URL)</option>
            <option value="webhook">📬 webhook (token route)</option>
          </select>
          <input
            value={type}
            onChange={e => setType(e.target.value)}
            placeholder="event type label"
            className="w-full bg-forge-border/30 rounded p-1.5 border border-forge-border focus:outline-none focus:border-purple-400"
          />
          {kind === 'http_poll' && (
            <input
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://..."
              className="w-full bg-forge-border/30 rounded p-1.5 border border-forge-border focus:outline-none focus:border-purple-400 font-mono"
            />
          )}
          {kind !== 'webhook' && (
            <input
              type="number" min={5}
              value={interval}
              onChange={e => setInterval(e.target.value)}
              placeholder="interval seconds"
              className="w-full bg-forge-border/30 rounded p-1.5 border border-forge-border focus:outline-none focus:border-purple-400"
            />
          )}
          <button
            onClick={submit}
            disabled={busy}
            className="w-full px-2 py-1.5 rounded bg-purple-500/30 hover:bg-purple-500/50 border border-purple-400 text-purple-100 disabled:opacity-40 disabled:cursor-not-allowed"
          >{busy ? 'Updating...' : 'Attach source'}</button>
        </div>
      )}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-forge-muted mb-1">{label}</div>
      {children}
    </div>
  )
}
