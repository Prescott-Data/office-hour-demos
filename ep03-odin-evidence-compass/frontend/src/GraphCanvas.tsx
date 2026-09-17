import cytoscape, {
  type Core,
  type ElementDefinition,
  type NodeSingular,
  type StylesheetJson,
} from 'cytoscape'
import { useEffect, useEffectEvent, useRef } from 'react'
import type { GraphNode, GraphResponse, OdinPath } from './types'

type GraphCanvasProps = {
  graph: GraphResponse
  seed: string
  activeSeeds?: string[]
  evidencePaths: OdinPath[]
  selectedPath: OdinPath | null
  replayPath: OdinPath | null
  replayPaths?: OdinPath[]
  selectedNodeId: string | null
  onSelectNode: (node: GraphNode | null) => void
  command: 'fit' | 'zoom-in' | 'zoom-out' | null
  commandSequence: number
}

const NODE_COLORS: Record<string, string> = {
  claim: '#111111', person: '#35776f', vehicle: '#b48132', policy: '#66715d',
  garage: '#866c52', assessor: '#5b7657', address: '#857f76', device: '#8a6670',
  payment_account: '#46686d',
}

const stylesheet: StylesheetJson = [
  { selector: 'node', style: {
    'background-color': (element: NodeSingular) => NODE_COLORS[element.data('type')] ?? '#77716a',
    'border-color': '#f7f5ef', 'border-width': 2, color: '#111111',
    'font-family': 'Azeret Mono, monospace', 'font-size': 9, label: '',
    'text-background-color': '#f7f5ef', 'text-background-opacity': 0.94,
    'text-background-padding': '3px', 'text-margin-y': 10, 'text-valign': 'bottom',
    shape: 'ellipse', height: 14, width: 14, 'z-index': 3,
  } },
  { selector: 'node:selected', style: { label: 'data(label)', 'z-index': 15 } },
  { selector: 'node.node-hover, node.node-focus', style: {
    label: 'data(label)', 'border-color': '#111111', 'border-width': 2,
    'underlay-color': '#18f6c1', 'underlay-opacity': 0.2, 'underlay-padding': 6,
    height: 20, width: 20, 'z-index': 28,
  } },
  { selector: 'edge', style: {
    'curve-style': 'unbundled-bezier', 'control-point-distance': 14,
    'control-point-weight': 0.5, 'line-color': '#b9b5ab', 'line-cap': 'round',
    opacity: 0.26, 'target-arrow-shape': 'none', width: 0.75,
  } },
  { selector: 'edge.node-hover-edge, edge.node-focus-edge', style: {
    'line-color': '#159b7e', 'line-cap': 'round', width: 2.1,
    opacity: 0.92, 'underlay-color': '#18f6c1', 'underlay-opacity': 0.1,
    'underlay-padding': 2, 'z-index': 24,
  } },
  { selector: '.seed', style: {
    'background-color': '#111111', 'border-color': '#18f6c1', 'border-width': 3,
    label: 'data(label)', height: 25, width: 25, 'font-size': 10, 'font-weight': 700,
    'underlay-color': '#18f6c1', 'underlay-opacity': 0.12, 'underlay-padding': 7,
    'z-index': 10,
  } },
  { selector: '.muted', style: { opacity: 0.055 } },
  { selector: 'node.evidence', style: { opacity: 0.9 } },
  { selector: '.evidence', style: { opacity: 0.78 } },
  { selector: 'edge.evidence', style: {
    'line-color': '#27a88a', 'line-cap': 'round', width: 1.5,
    opacity: 0.66, 'z-index': 6,
  } },
  { selector: 'node.replay-path', style: {
    'background-color': '#18f6c1', 'border-color': '#f7f5ef', 'border-width': 2,
    label: 'data(label)', height: 21, width: 21,
    'underlay-color': '#18f6c1', 'underlay-opacity': 0.18, 'underlay-padding': 7,
    'z-index': 18,
  } },
  { selector: 'edge.replay-path', style: {
    'line-color': '#18cfa8', 'line-cap': 'round', 'line-style': 'solid',
    width: 2.5, opacity: 0.94, 'underlay-color': '#18f6c1',
    'underlay-opacity': 0.14, 'underlay-padding': 3, 'z-index': 18,
  } },
  { selector: '.selected-path', style: { opacity: 1, 'z-index': 20 } },
  { selector: 'node.selected-path', style: {
    'background-color': '#ff624b', 'border-color': '#f7f5ef', 'border-width': 2,
    label: 'data(label)', height: 23, width: 23, 'font-size': 10, 'font-weight': 700,
    'underlay-color': '#ff4b32', 'underlay-opacity': 0.16, 'underlay-padding': 7,
  } },
  { selector: 'edge.selected-path', style: {
    color: '#111111', 'font-size': 8, 'font-weight': 600,
    'line-color': '#ff624b', 'line-cap': 'round',
    'text-background-color': '#f7f5ef', 'text-background-opacity': 0.96,
    'text-background-padding': '2px', 'text-rotation': 'autorotate', width: 2.75,
    'underlay-color': '#ff4b32', 'underlay-opacity': 0.12, 'underlay-padding': 3,
  } },
]

function elementsFromGraph(graph: GraphResponse): ElementDefinition[] {
  return [
    ...graph.nodes.map((node) => ({ data: node })),
    ...graph.edges.map((edge) => ({ data: edge })),
  ]
}

function matchingEdgeId(graph: GraphResponse, source: string, target: string, relation: string) {
  return graph.edges.find(
    (edge) => edge.source === source && edge.target === target && edge.relation === relation,
  )?.id
}

export function GraphCanvas({ graph, seed, activeSeeds = [], evidencePaths, selectedPath, replayPath, replayPaths = [], selectedNodeId, onSelectNode, command, commandSequence }: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)
  const selectNode = useEffectEvent(onSelectNode)

  useEffect(() => {
    if (!containerRef.current) return
    const cy = cytoscape({
      container: containerRef.current, elements: elementsFromGraph(graph), style: stylesheet,
      minZoom: 0.25, maxZoom: 2.4,
      layout: { name: 'cose', animate: false, randomize: true,
        nodeRepulsion: () => 7600, idealEdgeLength: () => 72,
        edgeElasticity: () => 90, gravity: 0.18, numIter: 1300, padding: 34 },
    })
    cyRef.current = cy
    cy.on('tap', 'node', (event) => selectNode(event.target.data() as GraphNode))
    cy.on('tap', (event) => { if (event.target === cy) selectNode(null) })
    cy.on('mouseover', 'node', (event) => {
      event.target.addClass('node-hover')
      event.target.connectedEdges().addClass('node-hover-edge')
    })
    cy.on('mouseout', 'node', (event) => {
      event.target.removeClass('node-hover')
      event.target.connectedEdges().removeClass('node-hover-edge')
    })
    const centerFrame = requestAnimationFrame(() => {
      if (!cy.destroyed()) {
        cy.fit(cy.elements(), 70)
        cy.center(cy.elements())
      }
    })
    return () => { cancelAnimationFrame(centerFrame); cy.destroy(); cyRef.current = null }
  }, [graph])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.batch(() => {
      cy.elements().removeClass('seed muted evidence selected-path replay-path')
      const seeds = new Set([seed, ...activeSeeds])
      seeds.forEach((id) => cy.getElementById(id).addClass('seed'))
      if (evidencePaths.length > 0) {
        cy.elements().addClass('muted')
        const nodeIds = new Set<string>([seed])
        const edgeIds = new Set<string>()
        evidencePaths.forEach((path) => path.edges.forEach((edge) => {
          nodeIds.add(edge.u); nodeIds.add(edge.v)
          const edgeId = matchingEdgeId(graph, edge.u, edge.v, edge.relation)
          if (edgeId) edgeIds.add(edgeId)
        }))
        nodeIds.forEach((id) => cy.getElementById(id).removeClass('muted').addClass('evidence'))
        edgeIds.forEach((id) => cy.getElementById(id).removeClass('muted').addClass('evidence'))
      }
      selectedPath?.edges.forEach((edge) => {
        cy.getElementById(edge.u).removeClass('muted').addClass('selected-path')
        cy.getElementById(edge.v).removeClass('muted').addClass('selected-path')
        const edgeId = matchingEdgeId(graph, edge.u, edge.v, edge.relation)
        if (edgeId) cy.getElementById(edgeId).removeClass('muted').addClass('selected-path')
      })
      const currentReplayPaths = replayPath ? [replayPath, ...replayPaths] : replayPaths
      currentReplayPaths.forEach((path) => path.edges.forEach((edge) => {
          cy.getElementById(edge.u).removeClass('muted').addClass('replay-path')
          cy.getElementById(edge.v).removeClass('muted').addClass('replay-path')
          const edgeId = matchingEdgeId(graph, edge.u, edge.v, edge.relation)
          if (edgeId) cy.getElementById(edgeId).removeClass('muted').addClass('replay-path')
        }))
    })
    const focus = replayPath || replayPaths.length > 0
      ? cy.elements('.replay-path')
      : selectedPath
        ? cy.elements('.selected-path')
        : cy.elements('.evidence')
    if (focus.length) {
      cy.animate({ fit: { eles: focus, padding: 90 }, duration: 260 })
      if (cy.zoom() > 1.65) cy.zoom(1.65)
      cy.center(focus)
    }
  }, [activeSeeds, evidencePaths, graph, replayPath, replayPaths, seed, selectedPath])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.elements().removeClass('node-focus node-focus-edge')
    if (!selectedNodeId) return
    const node = cy.getElementById(selectedNodeId)
    node.addClass('node-focus')
    node.connectedEdges().addClass('node-focus-edge')
  }, [selectedNodeId])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy || !command) return
    if (command === 'fit') cy.animate({ fit: { eles: cy.elements(':visible'), padding: 38 }, duration: 320 })
    const extent = cy.extent()
    const center = { x: (extent.x1 + extent.x2) / 2, y: (extent.y1 + extent.y2) / 2 }
    if (command === 'zoom-in') cy.animate({ zoom: { level: cy.zoom() * 1.2, position: center }, duration: 180 })
    if (command === 'zoom-out') cy.animate({ zoom: { level: cy.zoom() / 1.2, position: center }, duration: 180 })
  }, [command, commandSequence])

  return <div ref={containerRef} className="graph-canvas" aria-label="Insurance evidence graph" />
}