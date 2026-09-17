import { ChevronLeft, ChevronRight, Expand, ExternalLink, LoaderCircle, Play, RotateCcw } from 'lucide-react'
import { startTransition, useCallback, useEffect, useRef, useState } from 'react'
import { fetchAgentMission, fetchGraph, streamAgentInvestigation } from './api'
import { GraphCanvas } from './GraphCanvas'
import type { AgentEvent, GraphResponse, OdinBounds, OdinPath, RetrievalResponse } from './types'
import './PresentationApp.css'

const TASK = 'Five claims arrived today: 1042, 1088, 1116, 1173, 1210. Before any approval, investigate each with connected evidence and recommend: clear, or escalate to investigators (SIU).'
const VERIFIED_MISSION_ID = 'a39fcc71-baef-4fe6-abf3-0172cc2b0889'

const CHAPTERS = [
  { id: 'title', kicker: 'Technical session', title: 'Give Your AI Agent a Compass, Not a Bigger Prompt', copy: 'How knowledge graphs help AI agents navigate and rank connected evidence.', state: 'AGENT RECEIVES A TASK' },
  { id: 'origin', kicker: 'The problem we faced ourselves', title: 'We had the data. The agent still lost direction.', copy: 'The evidence existed across 775 entities and 2,619 relationships. Putting more of that neighbourhood into context made the task noisier—not the useful route clearer.', state: 'CONNECTED DATA · NO DIRECTION' },
  { id: 'case', kicker: "This morning's docket", title: 'Five claims. Which ones can move?', copy: 'No single recorded relationship decides the case. The connection only appears across records. 775 entities. 2,619 traversable relationships.', state: 'A DECISION IS DUE' },
  { id: 'agent', kicker: 'Live investigation', title: 'No route supplied. The agent chooses where to investigate.', copy: TASK, state: 'CLAIMS AGENT' },
  { id: 'verdict', kicker: 'The reveal', title: 'Recommendations with corroborating evidence attached.', copy: 'Validated run: three cleared and two escalated. The agent assembled the supporting chain across multiple completed Odin calls.', state: 'TRIAGE RECOMMENDATIONS' },
  { id: 'prompt-cost', kicker: 'The expensive alternative', title: 'Without direction, the model inherits the graph problem.', copy: 'More prompt means more responsibilities: understand the schema, generate a query, traverse correctly, rank routes, and still interpret the evidence.', state: 'FAILURE SURFACE GROWS' },
  { id: 'prompt', kicker: 'The reusable boundary', title: 'A task and tools. Not the graph.', copy: 'The stable contract defines evidence discipline. The task and bounds arrive at runtime. Graph topology, query language, the hidden route, and the expected recommendation stay outside model context.', state: 'STABLE CONTRACT · VARIABLE MISSION' },
  { id: 'path', kicker: 'One Odin call', title: 'A returned path is a lead. Not a conclusion.', copy: 'Claim 1042 → Device D-33C → Claim 1173 was returned by the Claim 1042 retrieval. One shared device justified continued investigation, not an accusation.', state: 'RETURNED PATH · RANK 24' },
  { id: 'compass', kicker: 'Division of responsibility', title: 'The agent explores. Odin supplies the compass.', copy: 'The agent chooses what to investigate. It does not generate AQL or Cypher. Odin orients, navigates, and ranks the graph evidence returned for interpretation.', state: 'AGENT CHOOSES A SEED' },
  { id: 'orient', kicker: 'Seed → orientation', title: 'First, learn where to look.', copy: 'Personalized PageRank orients the search around the chosen seed before bounded traversal begins. It is direction—not the final answer.', state: 'ODIN ORIENTING' },
  { id: 'navigate', kicker: 'Orientation → bounded walk', title: 'Explore many routes. Keep plausible paths.', copy: 'Beam search applies explicit limits, scores candidate routes, and returns the complete retained set in rank order.', state: 'ODIN NAVIGATING' },
  { id: 'evidence', kicker: 'One returned path, exactly', title: 'Inspect what Odin actually returned.', copy: 'The Claim 1042 retrieval returned this two-hop shared-device path. The canonical artifact retains it alongside every other ranked path, score, relation, PPR result, and source record.', state: 'RETURNED EVIDENCE' },
  { id: 'trust', kicker: 'The trust boundary', title: 'Connected evidence directs attention. It does not prove intent.', copy: 'A score ranks attention. A path records a connection. A corroborating chain combines evidence across calls. The agent recommends; a human verifies.', state: 'EVIDENCE ≠ ACCUSATION' },
  { id: 'close', kicker: 'The complete loop', title: 'Question. Seed. Navigate. Interpret. Choose again.', copy: 'A bigger prompt gives an agent more material. Odin gives it direction. Next session: post-payment review — where fraud patterns hide.', state: 'COMPASS → EXPLORER' },
  { id: 'questions', kicker: 'Q&A', title: 'Questions?', copy: 'Let’s discuss the implementation, evidence contract, or where graph navigation applies in your systems.', state: 'Q&A · POST-CLOSE' },
]

const DOCKET = [
  ['1042', 'escalate'], ['1088', 'clear'], ['1116', 'clear'], ['1173', 'escalate'], ['1210', 'clear'],
] as const

function StaticChapterVisual({ id }: { id: string }) {
  if (id === 'title') return <div className="direction-visual">
    <div><small>Material</small><b>2,619 relationships</b><span>Present but unranked</span></div>
    <i>→</i><div className="signal"><small>Compass</small><b>Odin</b><span>Navigate + rank</span></div>
    <i>→</i><div><small>Direction</small><b>Evidence path</b><span>Agent can act</span></div>
  </div>
  if (id === 'case') return <div className="docket-visual">
    <header><span>Claim</span><span>Single-record view</span><span>Decision</span></header>
    {DOCKET.map(([claim]) => <div key={claim}><b>{claim}</b><span>No decisive signal</span><em>?</em></div>)}
    <footer>Two claims share a connected route no row reveals.</footer>
  </div>
  if (id === 'verdict') return <div className="verdict-visual">
    <div className="verdict-grid">{DOCKET.map(([claim, outcome]) => <article className={outcome} key={claim}><small>Claim</small><b>{claim}</b><span>{outcome}</span></article>)}</div>
    <div className="verdict-route-panel">
      <div className="verdict-evidence-label"><small>Corroborating evidence chain</small><span>Assembled across multiple completed Odin calls</span></div>
      <div className="verdict-route"><b>1042</b><span>filed_from →</span><b>D-33C</b><span>registered_to →</span><b>Jon Bell</b><span>← controlled_by</span><b>A-224</b><span>← payable_to</span><b>1173</b></div>
    </div>
  </div>
  if (id === 'prompt-cost') return <div className="cost-visual">
    {['Understand the graph schema', 'Generate valid graph queries', 'Choose and traverse routes', 'Rank evidence before interpreting it'].map((responsibility, index) => <div key={responsibility}><small>Responsibility {String(index + 1).padStart(2, '0')}</small><b>{responsibility}</b></div>)}
    <footer>More instructions do not remove the navigation problem. They move it into the model.</footer>
  </div>
  if (id === 'prompt') return <div className="prompt-visual">
    <section><small>Stable capability</small><b>System + tools</b><p>Evidence discipline · agent/Odin responsibility · completion boundary</p><code>retrieve_with_odin(seed)</code></section>
    <section><small>Runtime variables</small><b>Task + bounds</b><p>Five claims · clear or escalate</p><code>12 paths · 10 hops · beam 32</code></section>
    <footer><small>Outside model context</small><span>775-entity topology</span><span>Schema + query language</span><span>Route + expected recommendation</span></footer>
  </div>
  if (id === 'path') return <div className="path-visual">
    <div><small>Claim</small><b>1042</b></div><span>filed_from →</span>
    <div className="signal"><small>Device</small><b>D-33C</b></div><span>filed_claim →</span>
    <div><small>Claim</small><b>1173</b></div>
    <footer><small>Returned path · Claim 1042 retrieval · rank 24</small><strong>One shared device was a lead. The agent continued investigating.</strong></footer>
  </div>
  if (id === 'compass') return <div className="roles-visual">
    <section><small>Agent</small><b>Choose a seed</b><b>Interpret evidence</b><b>Choose again</b></section>
    <div><span>seed</span><i>→</i><span>ranked paths</span><i>←</i></div>
    <section className="signal"><small>Odin</small><b>Orient with PPR</b><b>Walk within bounds</b><b>Rank complete paths</b></section>
    <pre>find_graph_entities(query=&quot;1042&quot;){'\n'}retrieve_with_odin(seed=&quot;ExtractedEntities/claim_00&quot;){'\n'}{'// No AQL · No Cypher · No route supplied'}</pre>
  </div>
  if (id === 'orient') return <div className="ranking-visual">
    <header><span>PPR rank</span><span>Entity</span><span>Before path walk</span></header>
    <div><b>#1</b><span>Claim 1042 · claim_00</span><code>seed</code></div>
    <div className="signal"><b>#2</b><span>Riverside Bodyworks · garage_02</span><code>oriented near seed</code></div>
    <div><b>#5</b><span>Device D-33C · device_02</span><code>bridge candidate</code></div>
    <div><b>#10</b><span>Jon Bell · person_09</span><code>connected person</code></div>
    <footer>Orientation narrows attention before traversal begins.</footer>
  </div>
  if (id === 'evidence') return <div className="evidence-visual">
    <header><span>Hop</span><span>Recorded relationship</span><span>Exact source record</span></header>
    <div><b>01</b><span>Claim 1042 —filed_from→ Device D-33C</span><code>Documents/record_006</code></div>
    <div><b>02</b><span>Device D-33C —filed_claim→ Claim 1173</span><code>Documents/record_027</code></div>
    <footer><strong>Returned path · rank 24 · score 0.02135</strong> Preserved with all 24 paths in the canonical retrieval artifact.</footer>
  </div>
  if (id === 'trust') return <div className="trust-visual">
    <div><small>Score</small><b>Ranks attention</b><span>Not probability of fraud</span></div>
    <div><small>Returned path</small><b>Records a connection</b><span>One Odin call</span></div>
    <div><small>Corroborating chain</small><b>Combines evidence</b><span>Multiple completed calls</span></div>
    <div className="signal"><small>Decision boundary</small><b>Agent recommends</b><span>Human verifies meaning and intent</span></div>
  </div>
  if (id === 'close') return <div className="loop-visual">{['Question', 'Seed', 'Orient', 'Navigate', 'Interpret', 'Choose again'].map((step, index) => <div key={step}><b>{String(index + 1).padStart(2, '0')}</b><span>{step}</span></div>)}</div>
  if (id === 'questions') return <div className="questions-visual"><small>Prescott Developers Office Hours</small><b>Q&amp;A</b><span>Thank you.</span></div>
  return null
}

function chapterFromPath() {
  const id = window.location.pathname.split('/').filter(Boolean).at(-1)
  const index = CHAPTERS.findIndex((chapter) => chapter.id === id)
  if (index >= 0) return index
  const saved = Number(window.localStorage.getItem('odin-presentation-chapter'))
  return Number.isInteger(saved) && saved >= 0 && saved < CHAPTERS.length ? saved : 0
}

function eventLabel(event: AgentEvent) {
  if (event.type === 'navigation_bounds') return 'Navigation bounds set'
  if (event.type === 'turn_started') return 'Turn started'
  if (event.type === 'model_started') return 'Model called'
  if (event.type === 'model_response') return 'Model chose an action'
  if (event.type === 'action_rejected') return 'Action rejected'
  if (event.type === 'tool_started') return `${String(event.data.tool ?? 'Tool').replaceAll('_', ' ')} called`
  if (event.type === 'scratchpad_updated') return 'Scratchpad updated'
  if (event.type === 'odin_started') return 'Odin called'
  if (event.type === 'odin_result') return 'Odin returned evidence'
  if (event.type === 'tool_result') return String(event.data.tool ?? 'Tool result').replaceAll('_', ' ')
  if (event.type === 'agent_complete') return 'Agent conclusion'
  return 'Run failed'
}

type ToolCallMessage = {
  content?: unknown
  tool_calls?: Array<{ function?: { name?: string, arguments?: string } }>
}

function parsedAgentResponse(event: AgentEvent | undefined): { rationale: string, actions: Array<{ name: string, arguments: unknown }> } | null {
  if (event?.type !== 'model_response') return null
  const response = event.data.response
  if (!response || typeof response !== 'object') return null
  const message = (response as { choices?: Array<{ message?: ToolCallMessage }> }).choices?.[0]?.message
  if (!message) return null
  return {
    rationale: typeof message.content === 'string' ? message.content : '',
    actions: (message.tool_calls ?? []).map((call) => {
      let args: unknown = call.function?.arguments
      if (typeof args === 'string') {
        try { args = JSON.parse(args) } catch { /* keep the raw string when unparseable */ }
      }
      return { name: call.function?.name ?? '', arguments: args }
    }),
  }
}

function shortEntity(id: string) {
  return id.split('/').at(-1)?.replaceAll('_', ' ') ?? id
}

export default function PresentationApp() {
  const standaloneAgent = window.location.pathname === '/agent'
  const [chapterIndex, setChapterIndex] = useState(chapterFromPath)
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [missionId, setMissionId] = useState<string | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [retrievals, setRetrievals] = useState<RetrievalResponse[]>([])
  const [referenceRetrievals, setReferenceRetrievals] = useState<RetrievalResponse[]>([])
  const [activeRetrievalId, setActiveRetrievalId] = useState<string | null>(null)
  const [scratchpad, setScratchpad] = useState('')
  const [activeEvent, setActiveEvent] = useState(0)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [bounds, setBounds] = useState<OdinBounds>({ max_paths: 12, hop_limit: 10, beam_width: 32 })
  const [replaying, setReplaying] = useState(false)
  const [replayCount, setReplayCount] = useState(0)
  const [manualReplayId, setManualReplayId] = useState<string | null>(null)
  const [liveReplayProgress, setLiveReplayProgress] = useState<Record<string, number>>({})
  const streamedEventCount = useRef(0)
  const chapter = CHAPTERS[chapterIndex]

  useEffect(() => {
    fetchGraph().then((value) => startTransition(() => setGraph(value))).catch((reason: unknown) => setError(String(reason)))
  }, [])

  useEffect(() => {
    if (chapter.id !== 'navigate' || retrievals.length > 0 || referenceRetrievals.length > 0) return
    fetchAgentMission(VERIFIED_MISSION_ID)
      .then((mission) => startTransition(() => setReferenceRetrievals(mission.odin_calls)))
      .catch(() => undefined)
  }, [chapter.id, referenceRetrievals.length, retrievals.length])

  const goTo = useCallback((nextIndex: number) => {
    const bounded = Math.max(0, Math.min(CHAPTERS.length - 1, nextIndex))
    setChapterIndex(bounded)
    window.localStorage.setItem('odin-presentation-chapter', String(bounded))
    window.history.replaceState(null, '', `/present/${CHAPTERS[bounded].id}`)
  }, [])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.target as HTMLElement)?.matches('button, input, select, textarea')) return
      if (event.key === 'ArrowRight' || event.key === 'PageDown' || event.key === ' ') { event.preventDefault(); goTo(chapterIndex + 1) }
      if (event.key === 'ArrowLeft' || event.key === 'PageUp') { event.preventDefault(); goTo(chapterIndex - 1) }
      if (event.key.toLowerCase() === 'f') void document.documentElement.requestFullscreen?.()
      if (event.key === 'Escape' && document.fullscreenElement) void document.exitFullscreen()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [chapterIndex, goTo])

  async function runMission() {
    streamedEventCount.current = 0
    setRunning(true); setError(null); setMissionId(null); setEvents([]); setRetrievals([]); setActiveRetrievalId(null); setScratchpad(''); setActiveEvent(0); setReplaying(false); setReplayCount(0); setManualReplayId(null); setLiveReplayProgress({})
    try {
      await streamAgentInvestigation(TASK, bounds, (message) => {
        if (message.type === 'mission_started') setMissionId(message.mission_id)
        if (message.type === 'mission_event') {
          const eventIndex = streamedEventCount.current
          streamedEventCount.current += 1
          setEvents((current) => [...current, message.event])
          setActiveEvent(eventIndex)
          if (message.event.type === 'odin_result') setActiveRetrievalId(String(message.event.data.call_id))
          if (message.event.type === 'scratchpad_updated') setScratchpad(String(message.event.data.scratchpad ?? ''))
        }
        if (message.type === 'odin_retrieval') {
          setRetrievals((current) => [...current, message.retrieval])
          setActiveRetrievalId(message.retrieval.call_id)
          setLiveReplayProgress((current) => ({ ...current, [message.retrieval.call_id]: 0 }))
        }
        if (message.type === 'stream_error') setError(message.detail)
      })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setRunning(false)
    }
  }

  const event = events[activeEvent]
  const eventRetrievalId = event?.type === 'odin_result' ? String(event.data.call_id) : null
  const requestedRetrievalId = manualReplayId ?? eventRetrievalId ?? activeRetrievalId
  const liveRetrieval = requestedRetrievalId
    ? retrievals.find((item) => item.call_id === requestedRetrievalId)
    : retrievals.at(-1)
  const storyRetrieval = retrievals.find((item) => item.requested.seeds[0] === 'ExtractedEntities/claim_00')
    ?? referenceRetrievals.find((item) => item.requested.seeds[0] === 'ExtractedEntities/claim_00')
  const retrieval = chapter.id === 'navigate'
    ? (manualReplayId ? liveRetrieval : storyRetrieval ?? liveRetrieval ?? referenceRetrievals.at(-1))
    : liveRetrieval
  const odinIsRunning = event?.type === 'odin_started'
  const latestOdinTurnId = events.reduce((turnId, item) => item.type === 'odin_started' ? Number(item.data.turn_id) : turnId, 0)
  const waveStarts = events.filter((item) => (
    item.type === 'odin_started'
    && Number(item.data.turn_id) === latestOdinTurnId
    && typeof (item.data.tool_call_id ?? item.data.call_id) === 'string'
  ))
  const waveRetrievals = waveStarts.flatMap((started) => {
    const toolCallId = String(started.data.tool_call_id ?? started.data.call_id)
    const completed = retrievals.find((item) => item.agent_tool_call_id === toolCallId)
    return completed ? [completed] : []
  })
  const liveWave = chapter.id === 'agent' && manualReplayId === null
  const liveReplayPaths = liveWave ? waveRetrievals.flatMap((item) => {
    const progress = liveReplayProgress[item.call_id] ?? 0
    if (progress === 0 || progress >= item.result.paths.length) return []
    const path = item.result.paths[Math.min(progress, item.result.paths.length) - 1]
    return path ? [path] : []
  }) : []
  const liveTrailPaths = liveWave ? waveRetrievals.flatMap((item) => {
    const progress = liveReplayProgress[item.call_id] ?? 0
    return progress >= item.result.paths.length ? item.result.paths.slice(0, 1) : []
  }) : []
  const paths: OdinPath[] = odinIsRunning && !liveWave ? [] : retrieval?.result.paths ?? []
  const visiblePaths = replaying ? paths.slice(0, replayCount) : paths
  const replayPath = replaying && replayCount > 0 ? paths[replayCount - 1] ?? null : null
  const activeSeeds = liveWave ? waveStarts.map((item) => String(item.data.seed)) : []
  const seed = activeSeeds.at(-1) ?? (odinIsRunning ? String(event.data.seed) : retrieval?.requested.seeds[0] ?? 'ExtractedEntities/claim_00')
  const selectedPath = !liveWave && !replaying && event?.type === 'odin_result' ? paths[0] ?? null : null
  const completedWaveCalls = waveRetrievals.length
  const modelTurns = events
    .map((item, index) => ({ event: item, eventIndex: index, response: parsedAgentResponse(item) }))
    .filter((item): item is typeof item & { response: NonNullable<typeof item.response> } => item.response !== null)
  const currentTurn = events.filter((item) => item.type === 'turn_started').length
  const latestTool = [...events].reverse().find((item) => item.type === 'tool_started')
  const latestOdin = [...events].reverse().find((item) => item.type === 'odin_started')
  const completion = [...events].reverse().find((item) => item.type === 'agent_complete' || item.type === 'agent_failed')
  const scratchpadUpdates = events.filter((item) => item.type === 'scratchpad_updated').length
  const entityLabel = (id: string) => {
    const node = graph?.nodes.find((item) => item.id === id)
    return node ? `${node.label} · ${node.key}` : shortEntity(id)
  }

  useEffect(() => {
    if (!liveWave || waveRetrievals.length === 0) return
    const timer = window.setTimeout(() => {
      setLiveReplayProgress((current) => {
        let changed = false
        const next = { ...current }
        waveRetrievals.forEach((item) => {
          const progress = current[item.call_id] ?? 0
          if (progress < item.result.paths.length) {
            next[item.call_id] = progress + 1
            changed = true
          }
        })
        return changed ? next : current
      })
    }, 240)
    return () => window.clearTimeout(timer)
  }, [liveReplayProgress, liveWave, waveRetrievals])

  useEffect(() => {
    if (!replaying) return
    const total = retrieval?.result.paths.length ?? 0
    const timer = window.setTimeout(() => {
      if (replayCount >= total) setReplaying(false)
      else setReplayCount((count) => count + 1)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [replayCount, replaying, retrieval])

  useEffect(() => {
    if (chapter.id !== 'navigate' || !retrieval) return
    const timer = window.setTimeout(() => {
      setReplayCount(0)
      setReplaying(true)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [chapter.id, retrieval])

  return (
    <main className={`presentation-shell ${standaloneAgent ? 'standalone-agent-shell' : ''}`}>
      <header className="presentation-bar">
        <img src="/brand/odin-combo-black.svg" alt="Odin" />
        <span>{standaloneAgent ? 'LIVE AGENT MISSION' : chapter.state}</span>
        <div>{standaloneAgent ? <b>CLAIMS INVESTIGATION</b> : <><b>{String(chapterIndex + 1).padStart(2, '0')}</b> / {String(CHAPTERS.length).padStart(2, '0')}</>}</div>
      </header>

      <section className={`presentation-stage chapter-${chapter.id} ${standaloneAgent ? 'agent-live-stage' : ''}`}>
        <div className="presentation-copy">
          <span>{chapter.kicker}</span>
          <h1>{chapter.title}</h1>
          <p>{chapter.copy}</p>
        </div>

        {(chapter.id === 'origin' || (chapter.id === 'agent' && standaloneAgent)) ? <div className="graph-stage" aria-label="Connected insurance evidence graph">
          {graph ? <GraphCanvas graph={graph} seed={chapter.id === 'origin' ? '' : seed} activeSeeds={chapter.id === 'origin' ? [] : activeSeeds} evidencePaths={chapter.id === 'origin' ? [] : liveWave ? liveTrailPaths : visiblePaths} selectedPath={chapter.id === 'origin' ? null : selectedPath} replayPath={chapter.id === 'origin' ? null : replayPath} replayPaths={chapter.id === 'origin' ? [] : liveReplayPaths} selectedNodeId={null} onSelectNode={() => undefined} command={null} commandSequence={0} /> : <LoaderCircle className="spin" />}
          {chapter.id === 'origin' && <div className="origin-overlay">
            <span>Available topology</span>
            <b>{graph?.counts.nodes ?? '—'} entities</b>
            <b>{graph?.counts.edges ?? '—'} relationships</b>
            <small>No route ranked yet</small>
          </div>}
          {chapter.id === 'agent' && waveStarts.length > 0 && <div className="odin-wave" aria-live="polite">
            <header><span>Odin calls · turn {latestOdinTurnId}</span><small>{completedWaveCalls} / {waveStarts.length} returned</small></header>
            <div>{waveStarts.map((started) => {
              const toolCallId = String(started.data.tool_call_id ?? started.data.call_id)
              const completed = waveRetrievals.find((item) => item.agent_tool_call_id === toolCallId)
              return <span className={completed ? 'returned' : 'running'} key={toolCallId}>
                <i />{entityLabel(String(started.data.seed))}<small>{completed ? `${completed.observations.returned_paths} paths` : 'running'}</small>
              </span>
            })}</div>
          </div>}
          <div className="graph-caption">{chapter.id === 'origin' ? 'Raw connected topology · available to Odin, not pasted into the agent prompt' : replaying ? `Odin traversal replay · path ${replayCount} / ${paths.length} · rank order` : liveWave && waveStarts.length ? `Live traversal · ${liveReplayPaths.length} active · ${completedWaveCalls} / ${waveStarts.length} calls returned` : odinIsRunning ? `Odin navigating · ${entityLabel(seed)} · ${String(event.data.hop_limit)} hop limit` : retrieval ? `Result replay · ${paths.length} returned paths · ${retrieval.call_id}` : graph ? `${graph.counts.nodes} entities · ${graph.counts.edges} recorded relationships` : 'Loading graph'}</div>
        </div> : chapter.id === 'agent' ? <div className="chapter-visual">
          <div className="explorer-launch agent-launch">
            <small>Live proof · autonomous investigation</small>
            <b>The agent receives the decision to make. Not the route.</b>
            <div><span>Task</span><strong>Five claims · clear or escalate</strong></div>
            <div><span>Live evidence</span><strong>Seeds · Odin calls · scratchpad · recommendations</strong></div>
            <button type="button" onClick={() => window.open('/agent', '_blank', 'noopener,noreferrer')}>
              <ExternalLink size={18} /> Open live claims agent
            </button>
            <p>Watch autonomous seed selection, evidence retrieval, continuity, and judgment.</p>
          </div>
        </div> : chapter.id === 'navigate' ? <div className="chapter-visual">
          <div className="explorer-launch">
            <small>Live mechanism · bounded graph navigation</small>
            <b>One seed turns topology into ranked evidence.</b>
            <div><span>Initial seed</span><strong>Claim 1042</strong></div>
            <div><span>Requested</span><strong>12 paths · 10 hops · beam 32</strong></div>
            <button type="button" onClick={() => window.open('/demo?seed=ExtractedEntities%2Fclaim_00&max_paths=12&hop_limit=10&beam_width=32', '_blank', 'noopener,noreferrer')}>
              <ExternalLink size={18} /> Open live Odin explorer
            </button>
            <p>Requested and effective bounds remain visible throughout the retrieval.</p>
          </div>
        </div> : <div className="chapter-visual"><StaticChapterVisual id={chapter.id} /></div>}

        {chapter.id === 'agent' && standaloneAgent && (
          <aside className="agent-workbench">
            <div className="workbench-heading"><span>Claims agent × Odin · live</span><b>Agent execution</b></div>
            {!missionId && !running && <>
              <div className="bounds-controls" aria-label="Odin navigation bounds">
                <label>max paths<input type="number" min={1} max={200} value={bounds.max_paths} onChange={(e) => setBounds({ ...bounds, max_paths: Number(e.target.value) })} /></label>
                <label>hop limit<input type="number" min={1} max={10} value={bounds.hop_limit} onChange={(e) => setBounds({ ...bounds, hop_limit: Number(e.target.value) })} /></label>
                <label>beam width<input type="number" min={1} max={256} value={bounds.beam_width} onChange={(e) => setBounds({ ...bounds, beam_width: Number(e.target.value) })} /></label>
              </div>
              <button type="button" onClick={runMission}><Play size={16} fill="currentColor" /> Run agent</button>
            </>}
            {running && <div className="live-status"><LoaderCircle className="spin" /><span>Live · turn {currentTurn || 1} · {events.length} recorded events</span></div>}
            {events.length > 0 && <>
              <section className="turn-feed" aria-live="polite">
                <header><span>Agent rationale</span><small>{modelTurns.length} model turns</small></header>
                <div>
                  {modelTurns.map(({ event: modelEvent, eventIndex, response }, index) => {
                    return <button type="button" key={modelEvent.event_id} className={eventIndex === activeEvent ? 'active' : ''} onClick={() => setActiveEvent(eventIndex)}>
                      <span><b>Turn {index + 1}</b><em>{response.actions.length} tool {response.actions.length === 1 ? 'call' : 'calls'}</em></span>
                      <p>{response.rationale || 'The model returned no audience-safe rationale.'}</p>
                      <div className="turn-actions">{response.actions.map((action, actionIndex) => {
                        const args = action.arguments && typeof action.arguments === 'object' ? action.arguments as Record<string, unknown> : {}
                        return <code key={`${action.name}-${actionIndex}`}>
                          <strong>{action.name.replaceAll('_', ' ')}</strong>
                          {action.name === 'retrieve_with_odin' && typeof args.seed === 'string' ? ` · seed ${entityLabel(args.seed)}` : ''}
                          {action.name === 'find_graph_entities' && typeof args.query === 'string' ? ` · query ${args.query}` : ''}
                        </code>
                      })}</div>
                    </button>
                  })}
                  {modelTurns.length === 0 && <p className="turn-waiting">Waiting for the first model response.</p>}
                </div>
              </section>
              {latestTool && <section className="current-activity">
                <header><span>Current activity</span><small>{running ? 'live' : 'last action'}</small></header>
                <b>{String(latestTool.data.tool).replaceAll('_', ' ')}</b>
                {String(latestTool.data.tool) === 'retrieve_with_odin' && latestOdin && <>
                  <p>Seed · {entityLabel(String(latestOdin.data.seed))}</p>
                  <code>{String(latestOdin.data.max_paths)} paths · {String(latestOdin.data.hop_limit)} hops · beam {String(latestOdin.data.beam_width)}</code>
                </>}
              </section>}

              {completion && <section className={`completion-summary ${completion.type === 'agent_failed' ? 'failed' : ''}`}>
                <small>{completion.type === 'agent_failed' ? 'Mission failed' : 'Agent conclusion'}</small>
                <p>{completion.type === 'agent_failed'
                  ? String(completion.data.message ?? 'The mission stopped explicitly.')
                  : String((completion.data.conclusion as Record<string, unknown> | undefined)?.conclusion ?? 'Mission complete.')}</p>
              </section>}

              <details className="scratchpad-disclosure">
                <summary>Scratchpad <small>{scratchpadUpdates ? `${scratchpadUpdates} updates` : 'empty'}</small></summary>
                <pre>{scratchpad || 'The agent has not written to its scratchpad yet.'}</pre>
              </details>

              <details className="technical-details">
                <summary>Technical details <small>{events.length} complete events</small></summary>
                <ol className="execution-timeline" aria-label="Complete agent and Odin execution timeline">
                  {events.map((item, index) => <li key={item.event_id}>
                    <button type="button" className={index === activeEvent ? 'active' : ''} onClick={() => {
                      setActiveEvent(index)
                      if (item.type === 'odin_result') {
                        setActiveRetrievalId(String(item.data.call_id))
                        setManualReplayId(String(item.data.call_id))
                        setReplayCount(0)
                        setReplaying(true)
                      }
                    }}>
                      <i className={`event-dot event-${item.type}`} />
                      <span>{eventLabel(item)}</span>
                      <small>{item.type === 'odin_result' ? `${String(item.data.paths)} paths` : String(item.data.status ?? '')}</small>
                    </button>
                  </li>)}
                </ol>
                {event && <section className="event-inspector" aria-live="polite">
                  <header><span>{eventLabel(event)}</span><time>{new Date(event.timestamp).toLocaleTimeString()}</time></header>
                  {event.type === 'odin_result' && retrieval && <dl className="odin-metrics">
                    <div><dt>Seed</dt><dd>{entityLabel(retrieval.requested.seeds[0])}</dd></div>
                    <div><dt>Returned</dt><dd>{retrieval.observations.returned_paths} paths</dd></div>
                    <div><dt>Effective</dt><dd>{retrieval.effective.hop_limit} hops · beam {retrieval.effective.beam_width}</dd></div>
                  </dl>}
                  <pre>{JSON.stringify(event.data, null, 2)}</pre>
                </section>}
                <nav className="event-controls">
                  <button type="button" onClick={() => setActiveEvent((value) => Math.max(0, value - 1))} disabled={activeEvent === 0}><ChevronLeft size={16} /></button>
                  <span>{activeEvent + 1} / {events.length}</span>
                  <button type="button" onClick={() => setActiveEvent((value) => Math.min(events.length - 1, value + 1))} disabled={activeEvent === events.length - 1}><ChevronRight size={16} /></button>
                  <button type="button" onClick={runMission} title="Run a new mission"><RotateCcw size={15} /></button>
                </nav>
                <footer>Canonical mission · {missionId ?? 'starting'}</footer>
              </details>
            </>}
            {error && <p className="agent-error">{error}</p>}
          </aside>
        )}
      </section>

      {!standaloneAgent && <footer className="presentation-controls">
        <button type="button" onClick={() => goTo(chapterIndex - 1)} disabled={chapterIndex === 0} aria-label="Previous chapter"><ChevronLeft /></button>
        <div>{CHAPTERS.map((item, index) => <button key={item.id} type="button" className={index === chapterIndex ? 'active' : ''} onClick={() => goTo(index)} aria-label={`Open ${item.title}`} />)}</div>
        <button type="button" onClick={() => void document.documentElement.requestFullscreen?.()} aria-label="Enter fullscreen"><Expand /></button>
        <button type="button" onClick={() => goTo(chapterIndex + 1)} disabled={chapterIndex === CHAPTERS.length - 1} aria-label="Next chapter"><ChevronRight /></button>
      </footer>}
    </main>
  )
}
