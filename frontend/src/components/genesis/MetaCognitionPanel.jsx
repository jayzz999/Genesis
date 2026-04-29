import { useState } from 'react'

/**
 * MetaCognitionPanel — Phase 5A: Displays the organism's self-improvement state.
 *
 * Shows:
 *   - Active reasoning strategy with live success rate
 *   - Full strategy library with per-perception-type performance
 *   - Meta-critic history (lessons learned, quality scores)
 *   - Aggregate stats (avg quality, repeated mistakes, etc.)
 *   - Manual strategy override controls
 */
export default function MetaCognitionPanel({ metaCognition, activeId, switchStrategy, toggleMetaCognition }) {
  const [switching, setSwitching] = useState(false)

  if (!metaCognition) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <span style={styles.headerIcon}>🧠</span>
          <h3 style={styles.title}>Meta-Cognition</h3>
        </div>
        <p style={styles.empty}>Select an organism to view its meta-cognitive state.</p>
      </div>
    )
  }

  const { enabled, active_strategy, strategy_library, meta_history, aggregate } = metaCognition

  const handleSwitch = async (name) => {
    setSwitching(true)
    try {
      await switchStrategy(activeId, name)
    } finally {
      setSwitching(false)
    }
  }

  const handleToggle = () => {
    toggleMetaCognition(activeId, !enabled)
  }

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.headerIcon}>🧠</span>
        <h3 style={styles.title}>Meta-Cognition</h3>
        <button
          onClick={handleToggle}
          style={{
            ...styles.toggleBtn,
            background: enabled
              ? 'linear-gradient(135deg, #7ed321, #4a9e1c)'
              : 'linear-gradient(135deg, #666, #444)',
          }}
          title={enabled ? 'Disable self-evaluation' : 'Enable self-evaluation'}
        >
          {enabled ? '● Active' : '○ Paused'}
        </button>
      </div>

      {/* Active Strategy */}
      {active_strategy?.name && (
        <div style={styles.activeStrategy}>
          <div style={styles.label}>Active Strategy</div>
          <div style={styles.strategyName}>{active_strategy.name}</div>
          <div style={styles.strategyMeta}>
            <span style={styles.metaChip}>
              Success: {(active_strategy.success_rate * 100).toFixed(0)}%
            </span>
            <span style={styles.metaChip}>
              Used: {active_strategy.usage_count}×
            </span>
          </div>
        </div>
      )}

      {/* Aggregate Stats */}
      {aggregate && aggregate.total_critiques > 0 && (
        <div style={styles.aggregateRow}>
          <div style={styles.statBox}>
            <div style={styles.statValue}>{(aggregate.avg_reasoning_quality * 100).toFixed(0)}%</div>
            <div style={styles.statLabel}>Avg Quality</div>
          </div>
          <div style={styles.statBox}>
            <div style={styles.statValue}>{(aggregate.avg_action_efficiency * 100).toFixed(0)}%</div>
            <div style={styles.statLabel}>Efficiency</div>
          </div>
          <div style={styles.statBox}>
            <div style={{
              ...styles.statValue,
              color: aggregate.repeated_mistakes > 0 ? '#e94560' : '#7ed321',
            }}>
              {aggregate.repeated_mistakes}
            </div>
            <div style={styles.statLabel}>Repeated Mistakes</div>
          </div>
          <div style={styles.statBox}>
            <div style={styles.statValue}>{aggregate.total_critiques}</div>
            <div style={styles.statLabel}>Self-Reviews</div>
          </div>
        </div>
      )}

      {/* Strategy Library */}
      <div style={styles.section}>
        <div style={styles.sectionTitle}>Strategy Library</div>
        <div style={styles.strategyGrid}>
          {(strategy_library || []).map((s) => (
            <div
              key={s.id}
              style={{
                ...styles.strategyCard,
                borderColor: s.is_active ? '#f5a623' : '#333',
                boxShadow: s.is_active ? '0 0 12px rgba(245,166,35,0.3)' : 'none',
              }}
            >
              <div style={styles.stratCardHeader}>
                <span style={styles.stratCardName}>{s.name}</span>
                {s.is_active && <span style={styles.activeBadge}>ACTIVE</span>}
              </div>
              <div style={styles.stratCardDesc}>{s.description}</div>
              <div style={styles.stratCardStats}>
                <div style={styles.progressBar}>
                  <div
                    style={{
                      ...styles.progressFill,
                      width: `${(s.success_rate * 100).toFixed(0)}%`,
                      background: s.success_rate >= 0.7
                        ? 'linear-gradient(90deg, #7ed321, #4a9e1c)'
                        : s.success_rate >= 0.4
                          ? 'linear-gradient(90deg, #f5a623, #d48b0e)'
                          : 'linear-gradient(90deg, #e94560, #c4334d)',
                    }}
                  />
                </div>
                <span style={styles.progressLabel}>
                  {(s.success_rate * 100).toFixed(0)}% success · {s.usage_count} uses
                </span>
              </div>
              {s.best_for?.length > 0 && (
                <div style={styles.bestFor}>
                  Best for: {s.best_for.map(t => (
                    <span key={t} style={styles.typeChip}>{t}</span>
                  ))}
                </div>
              )}
              {!s.is_active && (
                <button
                  onClick={() => handleSwitch(s.name)}
                  style={styles.switchBtn}
                  disabled={switching}
                >
                  {switching ? '...' : 'Activate'}
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Critic History */}
      {meta_history && meta_history.length > 0 && (
        <div style={styles.section}>
          <div style={styles.sectionTitle}>Self-Evaluation History</div>
          <div style={styles.historyList}>
            {meta_history.slice(0, 8).map((m) => (
              <div key={m.id} style={styles.historyItem}>
                <div style={styles.historyHeader}>
                  <div style={styles.qualityBadges}>
                    <span style={{
                      ...styles.qualityBadge,
                      background: m.reasoning_quality >= 0.7 ? '#1a3d1a' : m.reasoning_quality >= 0.4 ? '#3d3a1a' : '#3d1a1a',
                      color: m.reasoning_quality >= 0.7 ? '#7ed321' : m.reasoning_quality >= 0.4 ? '#f5a623' : '#e94560',
                    }}>
                      Q:{(m.reasoning_quality * 100).toFixed(0)}%
                    </span>
                    <span style={{
                      ...styles.qualityBadge,
                      background: m.action_efficiency >= 0.7 ? '#1a3d1a' : m.action_efficiency >= 0.4 ? '#3d3a1a' : '#3d1a1a',
                      color: m.action_efficiency >= 0.7 ? '#7ed321' : m.action_efficiency >= 0.4 ? '#f5a623' : '#e94560',
                    }}>
                      E:{(m.action_efficiency * 100).toFixed(0)}%
                    </span>
                    {m.repeated_mistake && (
                      <span style={styles.mistakeBadge}>⚠ Repeated</span>
                    )}
                  </div>
                  <span style={styles.historyTime}>
                    {new Date(m.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                {m.lesson && <div style={styles.lesson}>💡 {m.lesson}</div>}
                {m.attention_gaps?.length > 0 && (
                  <div style={styles.gaps}>
                    Blind spots: {m.attention_gaps.join(', ')}
                  </div>
                )}
                {m.recommended_strategy && (
                  <div style={styles.recommendation}>
                    → Recommends: <strong>{m.recommended_strategy}</strong>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}


// ── Styles ──────────────────────────────────────────────────────────────

const styles = {
  container: {
    background: 'linear-gradient(135deg, #0d1117, #161b22)',
    borderRadius: '12px',
    border: '1px solid #21262d',
    padding: '16px',
    color: '#e6edf3',
    fontFamily: "'Inter', sans-serif",
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '16px',
  },
  headerIcon: { fontSize: '20px' },
  title: {
    margin: 0,
    fontSize: '15px',
    fontWeight: 600,
    flex: 1,
    background: 'linear-gradient(90deg, #f5a623, #e94560)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  toggleBtn: {
    border: 'none',
    borderRadius: '12px',
    padding: '4px 10px',
    fontSize: '11px',
    fontWeight: 600,
    color: '#fff',
    cursor: 'pointer',
  },
  empty: {
    color: '#484f58',
    fontSize: '13px',
    textAlign: 'center',
    padding: '20px 0',
  },
  activeStrategy: {
    background: 'rgba(245,166,35,0.08)',
    border: '1px solid rgba(245,166,35,0.2)',
    borderRadius: '8px',
    padding: '12px',
    marginBottom: '12px',
  },
  label: {
    fontSize: '10px',
    fontWeight: 600,
    textTransform: 'uppercase',
    color: '#8b949e',
    letterSpacing: '0.5px',
  },
  strategyName: {
    fontSize: '18px',
    fontWeight: 700,
    textTransform: 'capitalize',
    color: '#f5a623',
    marginTop: '2px',
  },
  strategyMeta: {
    display: 'flex',
    gap: '8px',
    marginTop: '6px',
  },
  metaChip: {
    fontSize: '11px',
    background: 'rgba(255,255,255,0.06)',
    padding: '2px 8px',
    borderRadius: '8px',
    color: '#8b949e',
  },
  aggregateRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '8px',
    marginBottom: '16px',
  },
  statBox: {
    background: 'rgba(255,255,255,0.03)',
    borderRadius: '8px',
    padding: '10px 6px',
    textAlign: 'center',
  },
  statValue: {
    fontSize: '18px',
    fontWeight: 700,
    color: '#e6edf3',
  },
  statLabel: {
    fontSize: '10px',
    color: '#8b949e',
    marginTop: '2px',
    textTransform: 'uppercase',
    letterSpacing: '0.3px',
  },
  section: {
    marginTop: '16px',
  },
  sectionTitle: {
    fontSize: '12px',
    fontWeight: 600,
    textTransform: 'uppercase',
    color: '#8b949e',
    letterSpacing: '0.5px',
    marginBottom: '8px',
  },
  strategyGrid: {
    display: 'grid',
    gap: '8px',
  },
  strategyCard: {
    background: 'rgba(255,255,255,0.02)',
    border: '1px solid #333',
    borderRadius: '8px',
    padding: '12px',
    transition: 'border-color 0.2s, box-shadow 0.2s',
  },
  stratCardHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  stratCardName: {
    fontSize: '14px',
    fontWeight: 600,
    textTransform: 'capitalize',
    color: '#e6edf3',
  },
  activeBadge: {
    fontSize: '9px',
    fontWeight: 700,
    background: 'linear-gradient(135deg, #f5a623, #e99c11)',
    color: '#000',
    padding: '2px 6px',
    borderRadius: '4px',
    letterSpacing: '0.5px',
  },
  stratCardDesc: {
    fontSize: '12px',
    color: '#8b949e',
    marginTop: '4px',
  },
  stratCardStats: {
    marginTop: '8px',
  },
  progressBar: {
    height: '4px',
    background: 'rgba(255,255,255,0.06)',
    borderRadius: '2px',
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: '2px',
    transition: 'width 0.3s ease',
  },
  progressLabel: {
    fontSize: '10px',
    color: '#8b949e',
    marginTop: '3px',
    display: 'block',
  },
  bestFor: {
    marginTop: '6px',
    fontSize: '11px',
    color: '#8b949e',
  },
  typeChip: {
    display: 'inline-block',
    fontSize: '10px',
    background: 'rgba(126,211,33,0.1)',
    color: '#7ed321',
    padding: '1px 6px',
    borderRadius: '4px',
    marginLeft: '4px',
  },
  switchBtn: {
    marginTop: '8px',
    width: '100%',
    padding: '6px',
    border: '1px solid #333',
    borderRadius: '6px',
    background: 'rgba(255,255,255,0.04)',
    color: '#8b949e',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  historyList: {
    display: 'grid',
    gap: '6px',
    maxHeight: '300px',
    overflowY: 'auto',
  },
  historyItem: {
    background: 'rgba(255,255,255,0.02)',
    border: '1px solid #21262d',
    borderRadius: '6px',
    padding: '10px',
  },
  historyHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  qualityBadges: {
    display: 'flex',
    gap: '4px',
  },
  qualityBadge: {
    fontSize: '10px',
    fontWeight: 600,
    padding: '2px 6px',
    borderRadius: '4px',
  },
  mistakeBadge: {
    fontSize: '10px',
    fontWeight: 600,
    background: '#3d1a1a',
    color: '#e94560',
    padding: '2px 6px',
    borderRadius: '4px',
  },
  historyTime: {
    fontSize: '10px',
    color: '#484f58',
  },
  lesson: {
    fontSize: '12px',
    color: '#e6edf3',
    marginTop: '6px',
    lineHeight: '1.4',
  },
  gaps: {
    fontSize: '11px',
    color: '#8b949e',
    marginTop: '4px',
    fontStyle: 'italic',
  },
  recommendation: {
    fontSize: '11px',
    color: '#4a90d9',
    marginTop: '4px',
  },
}
