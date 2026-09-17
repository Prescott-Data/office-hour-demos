import { FileText, Gauge, Route } from 'lucide-react'
import type { CSSProperties } from 'react'
import type { GraphResponse, NavigationPath, OdinPath } from './types'

type PathLedgerEntryProps = {
  graph: GraphResponse
  path: OdinPath
  navigation: NavigationPath
  index: number
  active: boolean
  destinationCount: number
  maxStructural: number
  onHover: (index: number | null) => void
  onSelect: (index: number) => void
  onViewRaw: (index: number) => void
}

function nodeLabel(graph: GraphResponse, nodeId: string) {
  return graph.nodes.find((node) => node.id === nodeId)?.label ?? nodeId
}

export function PathLedgerEntry({
  graph,
  path,
  navigation,
  index,
  active,
  destinationCount,
  maxStructural,
  onHover,
  onSelect,
  onViewRaw,
}: PathLedgerEntryProps) {
  const destination = navigation.nodes.at(-1)?.id ?? ''
  const structuralWidth = maxStructural > 0
    ? navigation.signals.structural_ppr / maxStructural * 100
    : 0

  return (
    <article className={active ? 'path-entry active' : 'path-entry'}>
      <button
        type="button"
        className="path-row"
        style={{ '--path-index': index } as CSSProperties}
        onMouseEnter={() => onHover(index)}
        onMouseLeave={() => onHover(null)}
        onClick={() => onSelect(index)}
      >
        <span className="rank">{String(index + 1).padStart(2, '0')}</span>
        <span className="path-copy">
          <strong>
            {nodeLabel(graph, destination)}
            {destinationCount > 1 && <em>{destinationCount} routes</em>}
          </strong>
          <small>{path.edges.map((edge) => edge.relation.replaceAll('_', ' ')).join('  →  ')}</small>
          <span>{path.edges.length} {path.edges.length === 1 ? 'hop' : 'hops'} / score {path.score.toFixed(4)}</span>
        </span>
        <span className="score-bar"><i style={{ width: `${Math.max(12, path.score * 1000)}%` }} /></span>
      </button>

      {active && (
        <div className="path-analysis">
          <section>
            <h3><Route size={13} /> Ordered traversal</h3>
            <ol className="path-sequence">
              {navigation.nodes.map((node, nodeIndex) => (
                <li key={`${node.id}-${nodeIndex}`}>
                  <b>{nodeLabel(graph, node.id)}</b>
                  {navigation.edges[nodeIndex] && <span>{navigation.edges[nodeIndex].relation.replaceAll('_', ' ')}</span>}
                </li>
              ))}
            </ol>
          </section>

          <section className="compass-panel">
            <h3><Gauge size={13} /> COMPASS signals</h3>
            <div className="signal-row">
              <span>Structural / PPR</span><b>{navigation.signals.structural_ppr.toFixed(4)}</b>
              <i><u style={{ width: `${structuralWidth}%` }} /></i>
            </div>
            <div className="signal-row">
              <span>Semantic / NPLL</span><b>{navigation.signals.semantic_npll.toFixed(4)}</b>
              <i><u style={{ width: `${navigation.signals.semantic_npll * 100}%` }} /></i>
            </div>
            <div className="signal-status"><span>Temporal</span><b>{navigation.signals.temporal.status}</b></div>
            <div className="signal-status"><span>Community / bridge</span><b>{navigation.signals.community_bridge.status.replace('_', ' ')}</b></div>
            <p>Raw signal terms used by Odin; they are not additive percentages.</p>
          </section>

          <section className="provenance-panel">
            <h3><FileText size={13} /> Provenance</h3>
            {navigation.edges.map((edge, edgeIndex) => (
              <div className="provenance-row" key={`${edge.source}-${edge.relation}-${edge.target}`}>
                <span>{String(edgeIndex + 1).padStart(2, '0')} · {edge.relation.replaceAll('_', ' ')}</span>
                <b>{edge.source_document ?? 'No source record'}</b>
              </div>
            ))}
            <button type="button" className="raw-evidence-button" onClick={() => onViewRaw(index)}>View raw evidence →</button>
          </section>
        </div>
      )}
    </article>
  )
}