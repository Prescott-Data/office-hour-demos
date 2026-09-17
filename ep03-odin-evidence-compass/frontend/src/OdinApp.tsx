import {
  Braces, Focus, LoaderCircle, Play, RotateCcw, Route, Search, ZoomIn, ZoomOut,
} from 'lucide-react'
import { startTransition, useEffect, useState } from 'react'
import { fetchGraph, retrieveFromOdin } from './api'
import { GraphCanvas } from './GraphCanvas'
import { PathLedgerEntry } from './PathLedgerEntry'
import './OdinApp.css'
import './ForensicMap.css'
import type { GraphNode, GraphResponse, OdinPath, RetrievalResponse } from './types'

const TYPE_LABELS: Record<string, string> = {
  claim: 'Claims', person: 'People', vehicle: 'Vehicles', policy: 'Policies',
  garage: 'Garages', assessor: 'Assessors', address: 'Addresses', device: 'Devices',
  payment_account: 'Accounts',
}

const PIPELINE_STAGES = [
  'Personalized PageRank',
  'Beam path enumeration',
  'NPLL plausibility scoring',
  'Evidence aggregation',
]

function pathDestination(path: OdinPath) {
  return path.edges.at(-1)?.v ?? ''
}

export default function OdinApp() {
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [seed, setSeed] = useState('ExtractedEntities/claim_00')
  const [retrieval, setRetrieval] = useState<RetrievalResponse | null>(null)
  const [selectedPathIndex, setSelectedPathIndex] = useState<number | null>(null)
  const [hoveredPathIndex, setHoveredPathIndex] = useState<number | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [rawEvidencePathIndex, setRawEvidencePathIndex] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [pipelineStage, setPipelineStage] = useState(-1)
  const [replaying, setReplaying] = useState(false)
  const [replayCount, setReplayCount] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [graphCommand, setGraphCommand] = useState<'fit' | 'zoom-in' | 'zoom-out' | null>(null)
  const [commandSequence, setCommandSequence] = useState(0)

  useEffect(() => {
    fetchGraph()
      .then((response) => startTransition(() => setGraph(response)))
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!replaying || !retrieval) return
    const pathCount = retrieval.result.paths.length
    const timer = window.setTimeout(() => {
      if (replayCount >= pathCount) {
        setReplaying(false)
        setSelectedPathIndex(0)
        return
      }
      setReplayCount((count) => count + 1)
    }, 110)
    return () => window.clearTimeout(timer)
  }, [replayCount, replaying, retrieval])

  function issueGraphCommand(command: 'fit' | 'zoom-in' | 'zoom-out') {
    setGraphCommand(command)
    setCommandSequence((sequence) => sequence + 1)
  }

  function resetView() {
    setRetrieval(null)
    setSelectedPathIndex(null)
    setSelectedNode(null)
    setRawEvidencePathIndex(null)
    setHoveredPathIndex(null)
    setReplaying(false)
    setReplayCount(0)
    issueGraphCommand('fit')
  }

  function replayTraversal() {
    if (!retrieval) return
    setSelectedPathIndex(null)
    setHoveredPathIndex(null)
    setSelectedNode(null)
    setRawEvidencePathIndex(null)
    setReplayCount(0)
    setReplaying(true)
  }

  async function runOdin() {
    setRunning(true)
    setRetrieval(null)
    setError(null)
    setSelectedPathIndex(null)
    setSelectedNode(null)
    setRawEvidencePathIndex(null)
    setHoveredPathIndex(null)
    setPipelineStage(0)
    const stageTimers = PIPELINE_STAGES.slice(1).map((_, index) =>
      window.setTimeout(() => setPipelineStage(index + 1), (index + 1) * 420),
    )
    const minimumDuration = new Promise((resolve) => window.setTimeout(resolve, 1680))
    try {
      const [response] = await Promise.all([retrieveFromOdin(seed), minimumDuration])
      startTransition(() => {
        setRetrieval(response)
        setReplayCount(0)
        setReplaying(true)
      })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      stageTimers.forEach((timer) => window.clearTimeout(timer))
      setPipelineStage(-1)
      setRunning(false)
    }
  }

  if (loading) {
    return <main className="startup"><LoaderCircle className="spin" /> Loading graph from ArangoDB</main>
  }
  if (!graph) {
    return <main className="startup error-state">Unable to load graph. {error}</main>
  }

  const claims = graph.nodes.filter((node) => node.type === 'claim')
  const paths = retrieval?.result.paths ?? []
  const visiblePaths = replaying ? paths.slice(0, replayCount) : paths
  const displayPathIndex = hoveredPathIndex ?? selectedPathIndex
  const selectedPath = displayPathIndex === null ? null : paths[displayPathIndex] ?? null
  const replayPath = replaying && replayCount > 0 ? paths[replayCount - 1] ?? null : null
  const maxStructural = Math.max(
    0,
    ...(retrieval?.navigation.paths.map((path) => path.signals.structural_ppr) ?? []),
  )
  const rawEvidencePath = rawEvidencePathIndex === null
    ? null
    : retrieval?.navigation.paths[rawEvidencePathIndex] ?? null
  const destinationCounts = paths.reduce<Record<string, number>>((counts, path) => {
    const destination = pathDestination(path)
    counts[destination] = (counts[destination] ?? 0) + 1
    return counts
  }, {})
  const selectedConnections = selectedNode
    ? graph.edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id)
    : []
  const selectedPprIndex = selectedNode && retrieval
    ? retrieval.result.topk_ppr.findIndex(([nodeId]) => nodeId === selectedNode.id)
    : -1
  const selectedPpr = selectedPprIndex >= 0 && retrieval
    ? retrieval.result.topk_ppr[selectedPprIndex][1]
    : null
  const selectedNodePathIndexes = selectedNode
    ? paths.flatMap((path, index) =>
        path.edges.some((edge) => edge.u === selectedNode.id || edge.v === selectedNode.id)
          ? [index]
          : [],
      )
    : []
  const activeNodeIndex = selectedNode && selectedPath
    ? [selectedPath.edges[0]?.u, ...selectedPath.edges.map((edge) => edge.v)].indexOf(selectedNode.id)
    : -1

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <img className="odin-logo" src="/brand/odin-combo-black.svg" alt="Odin" />
          <div className="product-title">
            <h1>Odin Evidence Map</h1>
            <span>Evidence map</span>
          </div>
          <div className="prescott-brand">
            <span>by</span>
            <img src="/brand/prescott-monogram-black.svg" alt="" />
            <b>Prescott Data</b>
          </div>
        </div>

        <div className="run-controls">
          <label>
            <span>Seed entity</span>
            <select value={seed} onChange={(event) => { setSeed(event.target.value); resetView() }} disabled={running || replaying}>
              {claims.map((claim) => <option key={claim.id} value={claim.id}>{claim.label}</option>)}
            </select>
          </label>
          <div className="parameter-set" aria-label="Requested Odin parameters">
            <span><b>12</b> paths</span><span><b>10</b> hops</span><span><b>32</b> beam</span>
          </div>
          <button className="run-button" type="button" onClick={runOdin} disabled={running || replaying}>
            {running ? <LoaderCircle className="spin" size={17} /> : <Play size={17} fill="currentColor" />}
            {running ? 'Odin is retrieving' : 'Run Odin'}
          </button>
          <button className="icon-button" type="button" onClick={resetView} title="Reset to raw graph"><RotateCcw size={18} /></button>
        </div>
      </header>

      <section className="workspace">
        <div className="map-region">
          <div className="map-status">
            <div><span className={`mode-dot ${retrieval ? 'evidence-mode' : ''}`} /><strong>{replaying ? 'Result replay' : retrieval ? 'Odin traversal' : 'Raw graph'}</strong><span>{replaying ? `retained candidate ${replayCount} / ${paths.length}` : retrieval ? `${paths.length} ranked paths` : `${graph.counts.nodes} entities / ${graph.counts.edges} relations / ${graph.database}`}</span></div>
            <div className="map-tools">
              <button type="button" onClick={replayTraversal} title="Replay retained paths" disabled={!retrieval || replaying}><Route size={17} /></button>
              <button type="button" onClick={() => issueGraphCommand('zoom-in')} title="Zoom in"><ZoomIn size={17} /></button>
              <button type="button" onClick={() => issueGraphCommand('zoom-out')} title="Zoom out"><ZoomOut size={17} /></button>
              <button type="button" onClick={() => issueGraphCommand('fit')} title="Fit graph"><Focus size={17} /></button>
            </div>
          </div>

          <GraphCanvas graph={graph} seed={seed} evidencePaths={visiblePaths} selectedPath={replaying ? null : selectedPath} replayPath={replayPath} selectedNodeId={selectedNode?.id ?? null}
            onSelectNode={setSelectedNode} command={graphCommand} commandSequence={commandSequence} />

          <div className="legend" aria-label="Entity type legend">
            {Object.entries(TYPE_LABELS).map(([type, label]) => <span key={type}><i className={`legend-swatch type-${type}`} />{label}</span>)}
          </div>

          {retrieval && !replaying && <div className="run-metrics">{retrieval.navigation.summary.retained_nodes} retained / {retrieval.navigation.summary.graph_nodes} graph · {retrieval.navigation.summary.node_expansions} expansions · {retrieval.navigation.summary.edges_examined} edges examined</div>}

          {running && <div className="retrieval-overlay"><LoaderCircle className="spin" size={32} /><strong>Odin is navigating</strong><ol>{PIPELINE_STAGES.map((stage, index) => <li className={index < pipelineStage ? 'complete' : index === pipelineStage ? 'active' : ''} key={stage}>{stage}</li>)}</ol><span>Pipeline phases shown in execution order</span></div>}
          {error && <div className="error-banner">{error}</div>}

          {selectedNode && (
            <aside className="node-inspector">
              <button type="button" onClick={() => setSelectedNode(null)} aria-label="Close entity inspector">×</button>
              <span>{TYPE_LABELS[selectedNode.type] ?? selectedNode.type}</span><h2>{selectedNode.label}</h2>
              <p>{selectedConnections.length} recorded connections</p>
              {retrieval && <div className="node-why">
                <div><span>PPR rank</span><b>{selectedPprIndex >= 0 ? `#${selectedPprIndex + 1}` : '—'}</b><small>{selectedPpr?.toFixed(5) ?? 'not ranked'}</small></div>
                <div><span>Returned paths</span><b>{selectedNodePathIndexes.length}</b><small>of {paths.length}</small></div>
                <div><span>Active role</span><b>{activeNodeIndex >= 0 ? `step ${activeNodeIndex + 1}` : 'context'}</b><small>{activeNodeIndex === 0 ? 'seed' : activeNodeIndex > 0 ? 'traversed' : 'not selected'}</small></div>
              </div>}
              {selectedNodePathIndexes.length > 0 && <div className="node-path-links">
                <span>Paths containing this entity</span>
                <div>{selectedNodePathIndexes.map((pathIndex) => <button type="button" key={pathIndex} onClick={() => { setSelectedPathIndex(pathIndex); setSelectedNode(null) }}>{String(pathIndex + 1).padStart(2, '0')}</button>)}</div>
              </div>}
              <ul>{selectedConnections.slice(0, 6).map((edge) => <li key={edge.id}><b>{edge.relation.replaceAll('_', ' ')}</b><span><small>{edge.source_document}</small><small>{edge.source_title}</small></span></li>)}</ul>
            </aside>
          )}

          {rawEvidencePath && (
            <aside className="raw-evidence-drawer">
              <button type="button" onClick={() => setRawEvidencePathIndex(null)} aria-label="Close raw evidence">×</button>
              <span>Canonical evidence / path {String(rawEvidencePath.rank).padStart(2, '0')}</span>
              <h2>Source record chain</h2>
              <div className="raw-path-score">Path score <b>{rawEvidencePath.score.toFixed(6)}</b></div>
              <ol>
                {rawEvidencePath.edges.map((edge, index) => (
                  <li key={`${edge.source}-${edge.relation}-${edge.target}`}>
                    <small>{String(index + 1).padStart(2, '0')} / {edge.relation.replaceAll('_', ' ')}</small>
                    <b>{edge.source_document}</b>
                    <span>{edge.source_title}</span>
                    <code>{edge.source} → {edge.target}</code>
                  </li>
                ))}
              </ol>
            </aside>
          )}
        </div>

        <aside className="evidence-rail">
          <div className="rail-heading"><div><span>Evidence ledger</span><h2>{retrieval ? 'Ranked paths' : 'Awaiting retrieval'}</h2></div>{retrieval && <span className="version-badge">ODIN / {retrieval.runtime.odin_version}</span>}</div>
          {!retrieval ? (
            <div className="empty-rail">
              <Search size={30} /><p>Select a seed and run Odin to reduce this graph into ranked evidence paths.</p>
              <pre><code>{`result = engine.retrieve(\n  seeds=["${seed}"],\n  max_paths=12,\n  hop_limit=10,\n  beam_width=32,\n)`}</code></pre>
            </div>
          ) : (
            <>
              <div className="effective-strip"><div><span>Requested</span><b>{retrieval.requested.max_paths} / {retrieval.requested.hop_limit} / {retrieval.requested.beam_width}</b></div><i>→</i><div><span>Effective</span><b>{retrieval.effective.max_paths} / {retrieval.effective.hop_limit} / {retrieval.effective.beam_width}</b></div></div>
              <div className="adaptive-note"><span>Adaptive pass</span> Initial support widened the search envelope once.</div>
              <div className="timing-strip">
                <span>PPR <b>{retrieval.navigation.summary.ppr_ms.toFixed(1)}ms</b></span>
                <span>Beam <b>{retrieval.navigation.summary.beam_ms.toFixed(1)}ms</b></span>
                <span>Score <b>{retrieval.navigation.summary.scoring_ms.toFixed(1)}ms</b></span>
                <span>Total <b>{retrieval.navigation.summary.total_ms.toFixed(0)}ms</b></span>
              </div>
              <div className="path-list">
                {visiblePaths.map((path, index) => (
                  <PathLedgerEntry
                    key={`${index}-${path.score}`}
                    graph={graph}
                    path={path}
                    navigation={retrieval.navigation.paths[index]}
                    index={index}
                    active={selectedPathIndex === index}
                    destinationCount={destinationCounts[pathDestination(path)]}
                    maxStructural={maxStructural}
                    onHover={setHoveredPathIndex}
                    onSelect={(pathIndex) => { setSelectedPathIndex(pathIndex); setSelectedNode(null) }}
                    onViewRaw={setRawEvidencePathIndex}
                  />
                ))}
              </div>
              <footer className="artifact-footer"><Braces size={15} /><span>Canonical evidence</span><b>{retrieval.artifact}</b></footer>
            </>
          )}
        </aside>
      </section>
    </main>
  )
}