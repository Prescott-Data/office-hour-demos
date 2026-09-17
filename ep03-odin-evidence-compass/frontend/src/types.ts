export type GraphNode = {
  id: string
  key: string
  label: string
  type: string
}

export type GraphEdge = {
  id: string
  source: string
  target: string
  relation: string
  confidence: number
  created_at: string
  source_document: string
  source_title: string
}

export type GraphResponse = {
  database: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  counts: { nodes: number; edges: number }
}

export type PathEdge = {
  u: string
  v: string
  relation: string
  confidence: number
  provenance: string[] | null
}

export type OdinPath = {
  id: string | null
  score: number
  edges: PathEdge[]
}

export type RetrievalResponse = {
  call_id: string
  agent_tool_call_id?: string
  captured_at: string
  artifact: string
  runtime: { odin_version: string }
  requested: {
    seeds: string[]
    max_paths: number
    hop_limit: number
    beam_width: number
  }
  effective: {
    max_paths: number
    hop_limit: number
    beam_width: number
    early_stop_reason: string | null
  }
  observations: {
    returned_paths: number
    path_depths: number[]
    depth_counts: Record<string, number>
    deepest_path: number
  }
  navigation: {
    paths: NavigationPath[]
    retained_node_ids: string[]
    retained_edge_ids: string[]
    summary: {
      graph_nodes: number
      graph_edges: number
      retained_nodes: number
      retained_edges: number
      node_expansions: number
      edges_examined: number
      paths_retained: number
      ppr_ms: number
      beam_ms: number
      scoring_ms: number
      total_ms: number
    }
  }
  result: {
    paths: OdinPath[]
    topk_ppr: [string, number][]
    insight_score: number
    trace: Record<string, unknown>
    [key: string]: unknown
  }
}

export type NavigationNode = {
  id: string
  ppr_rank: number | null
  ppr: number
}

export type NavigationEdge = {
  source: string
  target: string
  relation: string
  npll: number
  graph_edge_id: string | null
  raw_confidence: number | null
  created_at: string | null
  source_document: string | null
  source_title: string | null
}

export type NavigationPath = {
  rank: number
  score: number
  nodes: NavigationNode[]
  edges: NavigationEdge[]
  signals: {
    structural_ppr: number
    semantic_npll: number
    temporal: { status: 'active' | 'inactive'; factor: number }
    community_bridge: { status: 'active' | 'not_configured'; factor: number }
  }
}

export type AgentEvent = {
  event_id: string
  timestamp: string
  type: 'navigation_bounds' | 'turn_started' | 'model_started' | 'model_response' | 'action_rejected' | 'tool_started' | 'scratchpad_updated' | 'odin_started' | 'odin_result' | 'tool_result' | 'agent_complete' | 'agent_failed'
  data: Record<string, unknown>
}

export type OdinBounds = {
  max_paths: number
  hop_limit: number
  beam_width: number
}

export type MissionStreamEvent =
  | { type: 'mission_started'; mission_id: string; task: string; captured_at: string }
  | { type: 'mission_event'; event: AgentEvent }
  | { type: 'odin_retrieval'; retrieval: RetrievalResponse }
  | { type: 'stream_error'; detail: string }

export type AgentMission = {
  mission_id: string
  captured_at: string
  agent: { implementation: 'explicit-loop'; style: 'Scout'; role: string }
  task: string
  status: 'running' | 'success' | 'failure' | 'yield'
  events: AgentEvent[]
  llm_calls: Array<Record<string, unknown>>
  tool_calls: Array<Record<string, unknown>>
  odin_calls: RetrievalResponse[]
  scratchpad: string
  conclusion?: Record<string, unknown>
  result_summary?: string
}

export type AgentInvestigationResponse = {
  status: 'success'
  output: AgentMission
  result_summary: string
  result_id: string
  artifact: string
}
