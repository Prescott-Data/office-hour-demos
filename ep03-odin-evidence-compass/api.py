"""HTTP API for the Odin graph demonstration."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import math
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from odin import OdinEngine
from pydantic import BaseModel, Field

from agent import AgentConfigurationError, ClaimsAgent, _MISSION_EVENT_SINK
from dataset import validate_dataset
from load_graph import get_database, load_graph


ARTIFACT_DIRECTORY = Path(__file__).parent / "artifacts"
DEFAULT_SEED = "ExtractedEntities/claim_00"
RETRIEVAL_LOCK = threading.Lock()


class RetrievalRequest(BaseModel):
    seed: str = DEFAULT_SEED
    max_paths: int = Field(default=12, ge=1, le=200)
    hop_limit: int = Field(default=10, ge=1, le=10)
    beam_width: int = Field(default=32, ge=1, le=256)


class AgentInvestigationRequest(BaseModel):
    task: str = "Five claims arrived today: 1042, 1088, 1116, 1173, 1210. Before any approval, investigate each with connected evidence and recommend: clear, or escalate to investigators (SIU)."
    max_paths: int = Field(default=12, ge=1, le=200)
    hop_limit: int = Field(default=10, ge=1, le=10)
    beam_width: int = Field(default=32, ge=1, le=256)

    def odin_bounds(self) -> dict[str, int]:
        return {"max_paths": self.max_paths, "hop_limit": self.hop_limit, "beam_width": self.beam_width}


def _prepare_database():
    try:
        database = get_database(reset=False)
        expected = validate_dataset()
        collections_ready = all(
            database.has_collection(name)
            for name in ("ExtractedEntities", "ExtractedRelationships")
        )
        counts_match = collections_ready and (
            database.collection("ExtractedEntities").count()
            == expected["entities"]
            and database.collection("ExtractedRelationships").count()
            == expected["relationships"]
        )
        if counts_match:
            return database
    except Exception:
        pass
    database, _ = load_graph(reset=True)
    return database


DATABASE = _prepare_database()
ENGINE = OdinEngine(
    db=DATABASE,
    community_id="global",
    community_mode="none",
)


def _retrieve_for_agent(*, seed: str, max_paths: int, hop_limit: int, beam_width: int) -> dict[str, object]:
    return retrieve(RetrievalRequest(
        seed=seed,
        max_paths=max_paths,
        hop_limit=hop_limit,
        beam_width=beam_width,
    ))


def _find_entities_for_agent(query: str) -> dict[str, object]:
    normalized = query.casefold().strip()
    matches = [
        node for node in _graph_from_arango()["nodes"]
        if normalized in node["id"].casefold()
        or normalized in node["label"].casefold()
        or normalized in node["type"].casefold()
    ]
    return {"status": "success", "query": query, "matches": matches, "count": len(matches)}


CLAIMS_AGENT = ClaimsAgent(
    _retrieve_for_agent,
    _find_entities_for_agent,
    artifact_directory=Path(__file__).parent / "artifacts" / "agent-runs",
)

app = FastAPI(title="Odin Evidence Map API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _graph_from_arango() -> dict[str, object]:
    nodes = list(
        DATABASE.aql.execute(
            """
            FOR node IN ExtractedEntities
              SORT node._key
              RETURN {
                id: node._id,
                key: node._key,
                label: node.name,
                type: node.type
              }
            """
        )
    )
    edges = list(
        DATABASE.aql.execute(
            """
            FOR edge IN ExtractedRelationships
                            LET source = DOCUMENT(edge.source_document_id)
              SORT edge._key
              RETURN {
                id: edge._id,
                source: edge._from,
                target: edge._to,
                relation: edge.relationship,
                confidence: edge.raw_confidence,
                                created_at: edge.created_at,
                                source_document: edge.source_document_id,
                                source_title: source.title
              }
            """
        )
    )
    return {
        "database": DATABASE.name,
        "nodes": nodes,
        "edges": edges,
        "counts": {"nodes": len(nodes), "edges": len(edges)},
    }


def _power_mean(values: list[float], rho: float) -> float:
    if not values:
        return 0.0
    if rho == 0.0:
        return math.exp(sum(math.log(max(value, 1e-12)) for value in values) / len(values))
    total = sum(max(value, 1e-12) ** rho for value in values) / len(values)
    return max(total, 1e-12) ** (1.0 / rho)


def _navigation_evidence(result: dict) -> dict[str, object]:
    graph = _graph_from_arango()
    edge_index = {
        (edge["source"], edge["relation"], edge["target"]): edge
        for edge in graph["edges"]
    }
    ppr_entries = result.get("topk_ppr", [])
    ppr_index = {
        node_id: {"rank": rank, "value": float(value)}
        for rank, (node_id, value) in enumerate(ppr_entries, start=1)
    }
    params = result.get("trace", {}).get("params")
    if isinstance(params, dict):
        rho = float(params.get("path_cfg", {}).get("power_mean_rho", 0.5))
    else:
        rho = float(getattr(getattr(params, "path_cfg", None), "power_mean_rho", 0.5))
    npll_cache: dict[tuple[str, str, str], float] = {}
    enriched_paths = []
    retained_nodes: set[str] = set()
    retained_edges: set[str] = set()

    for path_index, path in enumerate(result.get("paths", []), start=1):
        path_nodes: list[str] = []
        path_edges = []
        npll_values = []
        for edge in path.get("edges", []):
            source = edge["u"]
            target = edge["v"]
            relation = edge["relation"]
            edge_key = (source, relation, target)
            graph_edge = edge_index.get(edge_key)
            if edge_key not in npll_cache:
                npll_cache[edge_key] = float(ENGINE.score_edge(source, relation, target))
            npll_value = npll_cache[edge_key]
            npll_values.append(npll_value)
            if not path_nodes:
                path_nodes.append(source)
            path_nodes.append(target)
            retained_nodes.update((source, target))
            if graph_edge:
                retained_edges.add(graph_edge["id"])
            path_edges.append(
                {
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "npll": npll_value,
                    "graph_edge_id": graph_edge.get("id") if graph_edge else None,
                    "raw_confidence": graph_edge.get("confidence") if graph_edge else None,
                    "created_at": graph_edge.get("created_at") if graph_edge else None,
                    "source_document": graph_edge.get("source_document") if graph_edge else None,
                    "source_title": graph_edge.get("source_title") if graph_edge else None,
                }
            )

        node_signals = [
            {
                "id": node_id,
                "ppr_rank": ppr_index.get(node_id, {}).get("rank"),
                "ppr": ppr_index.get(node_id, {}).get("value", 0.0),
            }
            for node_id in path_nodes
        ]
        enriched_paths.append(
            {
                "rank": path_index,
                "score": path.get("score"),
                "nodes": node_signals,
                "edges": path_edges,
                "signals": {
                    "structural_ppr": _power_mean(
                        [float(node["ppr"]) for node in node_signals],
                        rho,
                    ),
                    "semantic_npll": math.prod(npll_values) if npll_values else 0.0,
                    "temporal": {"status": "inactive", "factor": 1.0},
                    "community_bridge": {"status": "not_configured", "factor": 1.0},
                },
            }
        )

    beam_usage = result.get("used_budget", {}).get("beam", {})
    timings = result.get("trace", {}).get("timings_ms", {})
    return {
        "paths": enriched_paths,
        "retained_node_ids": sorted(retained_nodes),
        "retained_edge_ids": sorted(retained_edges),
        "summary": {
            "graph_nodes": graph["counts"]["nodes"],
            "graph_edges": graph["counts"]["edges"],
            "retained_nodes": len(retained_nodes),
            "retained_edges": len(retained_edges),
            "node_expansions": beam_usage.get("nodes", 0),
            "edges_examined": beam_usage.get("edges", 0),
            "paths_retained": beam_usage.get("paths", 0),
            "ppr_ms": timings.get("ppr_done", 0),
            "beam_ms": timings.get("beam_done", 0),
            "scoring_ms": timings.get("scoring_done", 0),
            "total_ms": timings.get("total", 0),
        },
    }


def _effective_parameters(result: dict) -> dict[str, object]:
    beam_trace = result.get("trace", {}).get("beam", {})
    return {
        "max_paths": len(result.get("paths", [])),
        "hop_limit": beam_trace.get("hop_limit"),
        "beam_width": beam_trace.get("beam_width"),
        "early_stop_reason": beam_trace.get("early_stop_reason"),
    }


def _write_artifact(payload: dict) -> Path:
    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACT_DIRECTORY / f"odin-retrieve-{payload['call_id']}.json"
    artifact_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return artifact_path


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "database": DATABASE.name,
        "odin_version": importlib.metadata.version("odin-engine"),
    }


@app.get("/api/graph")
def graph() -> dict[str, object]:
    return _graph_from_arango()


@app.post("/api/retrieve")
def retrieve(request: RetrievalRequest) -> dict[str, object]:
    if not DATABASE.has_document(request.seed):
        raise HTTPException(status_code=404, detail=f"Unknown seed: {request.seed}")

    requested = {
        "seeds": [request.seed],
        "max_paths": request.max_paths,
        "hop_limit": request.hop_limit,
        "beam_width": request.beam_width,
    }
    with RETRIEVAL_LOCK:
        result = ENGINE.retrieve(**requested)
        navigation = _navigation_evidence(result)

    path_depths = [len(path.get("edges", [])) for path in result.get("paths", [])]
    call_id = str(uuid4())
    payload = {
        "call_id": call_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {"odin_version": importlib.metadata.version("odin-engine")},
        "requested": requested,
        "effective": _effective_parameters(result),
        "observations": {
            "returned_paths": len(path_depths),
            "path_depths": path_depths,
            "depth_counts": dict(sorted(Counter(path_depths).items())),
            "deepest_path": max(path_depths, default=0),
        },
        "navigation": navigation,
        "result": result,
    }
    payload = jsonable_encoder(payload)
    artifact_path = _write_artifact(payload)
    payload["artifact"] = artifact_path.name
    return payload


@app.post("/api/agent/investigate")
async def investigate(request: AgentInvestigationRequest) -> dict[str, object]:
    try:
        result = await CLAIMS_AGENT.run(request.task, odin_bounds=request.odin_bounds())
    except AgentConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail="Agent LLM provider is not configured or unavailable.",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if result.get("status") != "success":
        raise HTTPException(
            status_code=502,
            detail=result.get("result_summary") or "Claims investigation failed.",
        )
    return result


@app.post("/api/agent/investigate/stream")
async def investigate_stream(request: AgentInvestigationRequest) -> StreamingResponse:
    async def stream():
        queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def publish(payload: dict[str, object]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, payload)

        async def run_mission() -> None:
            token = _MISSION_EVENT_SINK.set(publish)
            try:
                result = await CLAIMS_AGENT.run(request.task, odin_bounds=request.odin_bounds())
                if result.get("status") != "success":
                    publish({
                        "type": "stream_error",
                        "detail": result.get("result_summary") or "Claims investigation failed.",
                    })
            except Exception as error:
                publish({"type": "stream_error", "detail": str(error)})
            finally:
                _MISSION_EVENT_SINK.reset(token)
                loop.call_soon_threadsafe(queue.put_nowait, None)

        mission_task = asyncio.create_task(run_mission())
        try:
            while True:
                payload = await queue.get()
                if payload is None:
                    break
                yield json.dumps(payload, sort_keys=True, default=str) + "\n"
        finally:
            await mission_task

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/agent/artifacts/{mission_id}")
def agent_artifact(mission_id: str) -> dict[str, object]:
    artifact_path = ARTIFACT_DIRECTORY / "agent-runs" / f"agent-odin-{mission_id}.json"
    if not artifact_path.is_file():
        raise HTTPException(status_code=404, detail=f"Unknown agent mission: {mission_id}")
    return json.loads(artifact_path.read_text(encoding="utf-8"))
