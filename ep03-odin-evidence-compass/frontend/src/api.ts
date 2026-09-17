import type { AgentInvestigationResponse, AgentMission, GraphResponse, MissionStreamEvent, OdinBounds, RetrievalResponse } from './types'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

async function checkedJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text()
    const error = response.headers.get('content-type')?.includes('application/json')
      ? JSON.parse(body) as { detail?: string }
      : null
    throw new Error(error?.detail || body || `Request failed with status ${response.status}`)
  }
  return response.json() as Promise<T>
}

export async function fetchGraph(): Promise<GraphResponse> {
  return checkedJson<GraphResponse>(await fetch(`${API_BASE}/api/graph`))
}

export async function fetchAgentMission(missionId: string): Promise<AgentMission> {
  return checkedJson<AgentMission>(await fetch(`${API_BASE}/api/agent/artifacts/${missionId}`))
}

export async function retrieveFromOdin(seed: string): Promise<RetrievalResponse> {
  return checkedJson<RetrievalResponse>(
    await fetch(`${API_BASE}/api/retrieve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seed, max_paths: 12, hop_limit: 10, beam_width: 32 }),
    }),
  )
}

export async function runAgentInvestigation(task: string): Promise<AgentInvestigationResponse> {
  return checkedJson<AgentInvestigationResponse>(
    await fetch(`${API_BASE}/api/agent/investigate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task }),
    }),
  )
}

export async function streamAgentInvestigation(
  task: string,
  bounds: OdinBounds,
  onEvent: (event: MissionStreamEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/agent/investigate/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task, ...bounds }),
  })
  if (!response.ok || !response.body) {
    await checkedJson<never>(response)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line) as MissionStreamEvent)
    }
    if (done) break
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as MissionStreamEvent)
}
