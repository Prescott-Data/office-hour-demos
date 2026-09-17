"""A small, explicit claims agent that uses Odin as a navigation tool."""

from __future__ import annotations

import json
import os
import re
import asyncio
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol
from uuid import uuid4

from dotenv import load_dotenv
from openai import AsyncAzureOpenAI


load_dotenv(Path(__file__).parent / ".env")


EventSink = Callable[[dict[str, Any]], None]
_MISSION_EVENT_SINK: ContextVar[EventSink | None] = ContextVar("agent_mission_event_sink", default=None)


SYSTEM_PROMPT = """You are a claims investigation agent. You decide what to inspect and when you have enough evidence.

Odin is one of your tools. Odin navigates and ranks connected graph evidence; it does not make the claim decision for you.

Work from recorded evidence only. Resolve human labels to exact recorded entity IDs instead of guessing. Navigate from every claim under review. Treat the first claim retrievals as orientation, not a conclusion: follow promising non-claim bridge entities in at least two successive investigation rounds. Compare evidence across claims and distinguish independently corroborated patterns from legitimate shared infrastructure. The same device, payment account, controller, garage, or address recurring across claims is a signal to investigate, not an automatic reason to escalate. Report relied-on paths and source records exactly. Scores rank attention; they are not proof. Never declare fraud, guilt, intent, truth, or causality. Recommend only clear or escalate for human investigation, with recorded evidence and limitations.

Use the scratchpad for mission continuity, not private reasoning. At mission start, write a concise note with GOAL and PLAN before or alongside the first investigation tools. After each evidence-bearing tool batch returns, update the scratchpad before the next investigation batch or finish. Keep the note concise and structured as GOAL, COMPLETED, LEARNED, and NEXT so another agent could continue the mission.

Before each tool call, state in one or two sentences what you learned and why the next action is useful. Do not reveal hidden chain-of-thought."""


TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "find_graph_entities",
        "description": "Find every recorded graph entity matching a human label, type, or exact ID.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Human label, entity type, or exact recorded entity ID."},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "retrieve_with_odin",
        "description": "Navigate and rank connected graph evidence outward from a seed entity. Navigation bounds are fixed by the mission; choose only where to navigate from.",
        "parameters": {"type": "object", "properties": {
            "seed": {"type": "string", "description": "Exact recorded entity ID to navigate from."},
        }, "required": ["seed"]},
    }},
    {"type": "function", "function": {
        "name": "update_scratchpad",
        "description": "Append concise mission-continuity state to durable working memory. Start with GOAL and PLAN; after evidence-bearing tool results record COMPLETED, LEARNED, and NEXT. Include exact entity IDs and uncertainties, but not private chain-of-thought.",
        "parameters": {"type": "object", "properties": {
            "note": {"type": "string"},
        }, "required": ["note"]},
    }},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Deliver the final triage result after claim orientation and at least two rounds of follow-up navigation from promising non-claim bridge entities.",
        "parameters": {"type": "object", "properties": {"result": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "object",
                    "description": "One entry per claim under review, keyed exactly 'Claim <number>'.",
                    "additionalProperties": {"type": "object", "properties": {
                        "recommendation": {"type": "string", "enum": ["clear", "escalate"]},
                        "justification": {"type": "string", "description": "The recorded relationships that justify the recommendation."},
                    }, "required": ["recommendation", "justification"]},
                },
                "evidence": {
                    "type": "object",
                    "properties": {
                        "follow_up_seeds": {"type": "array", "items": {"type": "string"}, "description": "Exact non-claim entity IDs investigated after claim orientation."},
                        "paths": {"type": "array", "items": {"type": "string"}, "description": "Recorded paths relied on for clear or escalate recommendations."},
                        "source_records": {"type": "array", "items": {"type": "string"}, "description": "Exact source document IDs supporting the relied-on paths."},
                        "odin_call_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["follow_up_seeds", "paths", "source_records", "odin_call_ids"],
                },
                "limitations": {"type": "array", "items": {"type": "string"}, "description": "What the recorded evidence cannot establish."},
                "verification_actions": {"type": "array", "items": {"type": "string"}},
                "conclusion": {"type": "string", "description": "How many claims were cleared and how many escalated."},
            },
            "required": ["findings", "evidence", "limitations", "verification_actions", "conclusion"],
        }}, "required": ["result"]},
    }},
]


@dataclass
class AgentState:
    task: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    scratchpad: str = ""
    steps_taken: int = 0


class ModelClient(Protocol):
    async def generate(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]: ...


class AgentConfigurationError(RuntimeError):
    """The local model provider configuration is incomplete."""


class AzureModelClient:
    """Direct Azure OpenAI client. No agent framework sits between the loop and model."""

    def __init__(self) -> None:
        api_key = os.getenv("AZURE_API_KEY", "").strip()
        endpoint = os.getenv("AZURE_ENDPOINT", "").strip()
        if not api_key or not endpoint:
            raise AgentConfigurationError("AZURE_API_KEY and AZURE_ENDPOINT must be configured.")
        self.deployment = os.getenv("AZURE_DEPLOYMENT", "gpt-5.4").strip()
        self.max_output_tokens = int(os.getenv("AGENT_MAX_OUTPUT_TOKENS", "16000"))
        self.client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=os.getenv("AZURE_API_VERSION", "2025-04-01-preview"),
            timeout=float(os.getenv("AGENT_LLM_TIMEOUT_SECONDS", "180")),
        )

    async def generate(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        response = await self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            tools=tools,
            tool_choice="required",
            max_completion_tokens=self.max_output_tokens,
        )
        return response.model_dump(mode="json")


class MissionRecorder:
    """Persist the complete mission after every state transition and stream each event."""

    def __init__(self, task: str, artifact_directory: Path | str) -> None:
        mission_id = str(uuid4())
        self._event_sink = _MISSION_EVENT_SINK.get()
        self.path = Path(artifact_directory) / f"agent-odin-{mission_id}.json"
        self.mission: dict[str, Any] = {
            "mission_id": mission_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "agent": {"implementation": "explicit-loop", "style": "Scout", "role": "claims_investigator"},
            "task": task,
            "status": "running",
            "scratchpad": "",
            "state": {},
            "events": [],
            "llm_calls": [],
            "tool_calls": [],
            "odin_calls": [],
            "trace_policy": {
                "canonical_fields": ["state", "llm_calls", "tool_calls", "odin_calls"],
                "model_view": "All turn history and all reasoning-bearing Odin evidence; duplicated result paths and runtime diagnostics excluded explicitly.",
            },
        }
        self.persist()
        self._emit({
            "type": "mission_started",
            "mission_id": mission_id,
            "task": task,
            "captured_at": self.mission["captured_at"],
        })

    def _emit(self, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(payload)

    def event(self, event_type: str, data: dict[str, Any]) -> None:
        event = {
            "event_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "data": data,
        }
        self.mission["events"].append(event)
        self.persist()
        self._emit({"type": "mission_event", "event": event})

    def record_state(self, state: AgentState) -> None:
        self.mission["scratchpad"] = state.scratchpad
        self.mission["state"] = asdict(state)
        self.persist()

    def model_result(self, call_id: str, request: dict[str, Any], response: dict[str, Any] | None, error: str | None = None) -> None:
        self.mission["llm_calls"].append({
            "call_id": call_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "request": request,
            "response": response,
            "error": error,
        })
        self.event("model_response", {
            "call_id": call_id,
            "status": "error" if error else "success",
            "response": response,
            "error": error,
            "canonical_field": "llm_calls",
        })

    def tool_started(self, call_id: str, tool: str, params: dict[str, Any], rationale: str) -> None:
        self.event("tool_started", {
            "call_id": call_id,
            "tool": tool,
            "params": params,
            "rationale": rationale,
        })

    def tool_result(self, call_id: str, tool: str, params: dict[str, Any], result: Any = None, error: str | None = None) -> None:
        self.mission["tool_calls"].append({
            "call_id": call_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "params": params,
            "result": result,
            "error": error,
        })
        self.event("tool_result", {
            "call_id": call_id,
            "tool": tool,
            "status": "error" if error else "success",
            "params": params,
            "result": result,
            "error": error,
            "canonical_field": "tool_calls",
        })

    def odin_result(self, payload: dict[str, Any]) -> None:
        self.mission["odin_calls"].append(payload)
        self.event("odin_result", {
            "round": len(self.mission["odin_calls"]),
            "call_id": payload["call_id"],
            "tool_call_id": payload.get("agent_tool_call_id"),
            "seed": payload["requested"]["seeds"][0],
            "paths": len(payload["result"].get("paths", [])),
        })
        self._emit({"type": "odin_retrieval", "retrieval": payload})

    def finish(self, result: dict[str, Any], state: AgentState) -> None:
        self.record_state(state)
        recommendations = [
            str(finding.get("recommendation", "")).casefold()
            for finding in result["findings"].values()
            if isinstance(finding, dict) and finding.get("recommendation")
        ]
        summary = f"{recommendations.count('clear')} cleared; {recommendations.count('escalate')} escalated."
        self.mission["status"] = "success"
        self.mission["conclusion"] = result
        self.mission["result_summary"] = summary
        self.event("agent_complete", {"status": "success", "summary": summary, "conclusion": result})

    def fail(self, error: BaseException, state: AgentState) -> None:
        self.record_state(state)
        self.mission["status"] = "failure"
        self.mission["error"] = {"type": type(error).__name__, "message": str(error)}
        self.event("agent_failed", self.mission["error"])

    def persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.mission, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        temporary.replace(self.path)


def _model_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep every evidentiary path and PPR row while removing known duplication."""
    result = payload["result"]
    return {
        "call_id": payload["call_id"],
        "requested": payload["requested"],
        "effective": payload["effective"],
        "observations": payload["observations"],
        "navigation": payload["navigation"],
        "topk_ppr": result.get("topk_ppr", []),
        "insight_score": result.get("insight_score"),
        "excluded_diagnostics": ["result.trace", "duplicate result.paths"],
        "canonical_artifact": payload.get("artifact"),
    }


def _expected_claims(task: str) -> set[str]:
    return {f"Claim {number}" for number in re.findall(r"\b\d{3,}\b", task)}


def _validate_result(result: Any, expected_claims: set[str]) -> tuple[bool, str]:
    required = {"findings", "evidence", "limitations", "verification_actions", "conclusion"}
    if not isinstance(result, dict) or not required.issubset(result):
        return False, f"Result must contain: {', '.join(sorted(required))}."
    if any(result.get(field) in (None, "", [], {}) for field in required):
        return False, "Every required result field must be non-empty."
    findings = result["findings"]
    if not isinstance(findings, dict):
        return False, "Findings must be keyed by claim label."
    for label in expected_claims:
        finding = findings.get(label)
        if not isinstance(finding, dict):
            return False, f"Findings must include {label}."
        if str(finding.get("recommendation", "")).casefold() not in {"clear", "escalate"}:
            return False, f"{label} recommendation must be 'clear' or 'escalate'."
        if not finding.get("justification"):
            return False, f"{label} must include an evidence-based justification."
    evidence = result["evidence"]
    if not isinstance(evidence, dict):
        return False, "Evidence must identify follow-up seeds, paths, source records, and Odin call IDs."
    evidence_fields = {"follow_up_seeds", "paths", "source_records", "odin_call_ids"}
    if not evidence_fields.issubset(evidence):
        return False, f"Evidence must contain: {', '.join(sorted(evidence_fields))}."
    if any(not isinstance(evidence[field], list) for field in evidence_fields):
        return False, "Evidence follow-up seeds, paths, source records, and Odin call IDs must be arrays."
    if len(set(evidence["follow_up_seeds"])) < 3:
        return False, "Evidence must identify at least three distinct non-claim follow-up seeds."
    if not evidence["paths"] or not evidence["source_records"] or not evidence["odin_call_ids"]:
        return False, "Evidence paths, source records, and Odin call IDs must be non-empty."
    if not isinstance(result["limitations"], list) or not all(result["limitations"]):
        return False, "Limitations must be a non-empty array of statements."
    if not isinstance(result["verification_actions"], list) or not all(result["verification_actions"]):
        return False, "Verification actions must be a non-empty array of actions."
    conclusion = str(result["conclusion"]).casefold()
    if "clear" not in conclusion or "escalat" not in conclusion:
        return False, "Conclusion must state how many claims were cleared and escalated."
    return True, ""


def _assistant_message(response: dict[str, Any]) -> dict[str, Any]:
    try:
        choice = response["choices"][0]
        if choice.get("finish_reason") == "length":
            raise RuntimeError("Model output reached the provider limit; the mission stopped without accepting a partial action.")
        message = choice["message"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("Model response did not contain a complete assistant message.") from error
    cleaned: dict[str, Any] = {"role": "assistant", "content": message.get("content")}
    if message.get("tool_calls"):
        cleaned["tool_calls"] = message["tool_calls"]
    return cleaned


class ClaimsAgent:
    """A visible reason/act/observe loop patterned after Scout's cognitive loop."""

    def __init__(
        self,
        retrieve: Callable[..., dict[str, Any]],
        find_entities: Callable[[str], dict[str, Any]],
        *,
        model: ModelClient | None = None,
        artifact_directory: Path | str = "artifacts/agent-runs",
        max_steps: int = 24,
    ) -> None:
        self.retrieve = retrieve
        self.find_entities = find_entities
        self.model = model
        self.artifact_directory = Path(artifact_directory)
        self.max_steps = max_steps

    @property
    def odin_bounds(self) -> dict[str, int]:
        # Scout's validated navigation defaults, with hop_limit capped at Odin 0.2.0's maximum of 10.
        return {
            "max_paths": int(os.getenv("ODIN_DEFAULT_MAX_PATHS", "12")),
            "hop_limit": int(os.getenv("ODIN_DEFAULT_HOP_LIMIT", "10")),
            "beam_width": int(os.getenv("ODIN_DEFAULT_BEAM_WIDTH", "32")),
        }

    def _guard_messages(self, messages: list[dict[str, Any]]) -> None:
        serialized = json.dumps(messages, default=str)
        # Default sized to the deployment's 1.1M-token window with headroom for the system prompt and output.
        limit = int(os.getenv("AGENT_MODEL_INPUT_CHAR_LIMIT", "4000000"))
        if len(serialized) > limit:
            raise RuntimeError(
                f"Complete conversation state is {len(serialized)} characters, exceeding the explicit model-input limit of {limit}; "
                "the mission stopped without truncation."
            )

    async def _call_model(self, state: AgentState, recorder: MissionRecorder) -> tuple[str, dict[str, Any]]:
        if self.model is None:
            self.model = AzureModelClient()
        call_id = str(uuid4())
        self._guard_messages(state.messages)
        request = {"messages": state.messages, "tools": TOOLS}
        recorder.event("model_started", {"call_id": call_id, "turn_id": state.steps_taken})
        try:
            response = await self.model.generate(messages=state.messages, tools=TOOLS)
        except Exception as error:
            recorder.model_result(call_id, request, None, str(error))
            raise
        recorder.model_result(call_id, request, response)
        return call_id, _assistant_message(response)

    async def run(self, task: str, odin_bounds: dict[str, int] | None = None) -> dict[str, Any]:
        state = AgentState(task=task, messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ])
        recorder = MissionRecorder(task, self.artifact_directory)
        mission_bounds = {**self.odin_bounds, **{k: int(v) for k, v in (odin_bounds or {}).items()}}
        recorder.event("navigation_bounds", mission_bounds)
        pending_tool: tuple[str, str, dict[str, Any]] | None = None
        retrieved_seed_turns: dict[str, int] = {}
        try:
            while state.steps_taken < self.max_steps:
                state.steps_taken += 1
                recorder.event("turn_started", {"turn_id": state.steps_taken})
                model_call_id, assistant = await self._call_model(state, recorder)
                state.messages.append(assistant)
                rationale = str(assistant.get("content") or "").strip()
                tool_calls = assistant.get("tool_calls") or []
                if not tool_calls:
                    feedback = "Respond with a tool call. Use finish when the investigation is complete."
                    state.messages.append({"role": "user", "content": feedback})
                    recorder.event("action_rejected", {"reason": feedback, "model_call_id": model_call_id})
                    recorder.record_state(state)
                    continue

                for call in tool_calls:
                    tool_call_id = str(call.get("id") or uuid4())
                    tool = str(call.get("function", {}).get("name", ""))
                    raw_arguments = call.get("function", {}).get("arguments") or "{}"
                    try:
                        params = json.loads(raw_arguments)
                        if not isinstance(params, dict):
                            raise ValueError("arguments must be a JSON object")
                    except (json.JSONDecodeError, ValueError) as error:
                        params = {"raw_arguments": raw_arguments}
                        recorder.tool_started(tool_call_id, tool, params, rationale)
                        output: Any = {"status": "rejected", "reason": f"Tool arguments must be a JSON object: {error}"}
                        state.messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(output, default=str)})
                        recorder.tool_result(tool_call_id, tool, params, output)
                        continue

                    recorder.tool_started(tool_call_id, tool, params, rationale)
                    pending_tool = (tool_call_id, tool, params)
                    finished = False
                    if tool == "find_graph_entities":
                        query = str(params.get("query", "")).strip()
                        if not query:
                            output = {"status": "rejected", "reason": "find_graph_entities requires query."}
                        else:
                            output = self.find_entities(query)
                    elif tool == "retrieve_with_odin":
                        seed = str(params.get("seed", "")).strip()
                        if not seed:
                            output = {"status": "rejected", "reason": "retrieve_with_odin requires an exact seed entity ID."}
                        else:
                            bounds = {"seed": seed, **mission_bounds}
                            recorder.event("odin_started", {"call_id": tool_call_id, "tool_call_id": tool_call_id, "turn_id": state.steps_taken, **bounds})
                            payload = await asyncio.to_thread(self.retrieve, **bounds)
                            payload["agent_tool_call_id"] = tool_call_id
                            recorder.odin_result(payload)
                            retrieved_seed_turns[seed] = state.steps_taken
                            output = {"status": "success", "evidence": _model_evidence(payload)}
                    elif tool == "update_scratchpad":
                        note = str(params.get("note", "")).strip()
                        if not note:
                            output = {"status": "rejected", "reason": "update_scratchpad requires note."}
                        else:
                            separator = "\n" if state.scratchpad else ""
                            state.scratchpad += f"{separator}- {note}"
                            recorder.event("scratchpad_updated", {"note": note, "scratchpad": state.scratchpad})
                            output = {"status": "success", "message": "Note stored in working memory."}
                    elif tool == "finish":
                        result = params.get("result")
                        expected_claims = _expected_claims(task)
                        claim_seeds = {
                            seed for seed in retrieved_seed_turns
                            if seed.startswith("ExtractedEntities/claim_")
                        }
                        follow_up_seed_turns = {
                            seed: turn for seed, turn in retrieved_seed_turns.items()
                            if not seed.startswith("ExtractedEntities/claim_")
                        }
                        if len(claim_seeds) < len(expected_claims):
                            output = {
                                "status": "rejected",
                                "reason": f"Navigate from at least {len(expected_claims)} distinct claim seeds before finishing.",
                            }
                        elif len(follow_up_seed_turns) < 3 or len(set(follow_up_seed_turns.values())) < 2:
                            output = {
                                "status": "rejected",
                                "reason": "Navigate from at least three distinct non-claim bridge seeds across two separate follow-up turns before finishing.",
                            }
                        else:
                            valid, reason = _validate_result(result, expected_claims)
                            if valid:
                                declared_seeds = set(result["evidence"]["follow_up_seeds"])
                                if not declared_seeds.issubset(follow_up_seed_turns):
                                    valid = False
                                    reason = "Every declared follow-up seed must correspond to a completed Odin retrieval."
                            output = {"status": "accepted" if valid else "rejected", "reason": reason}
                            finished = valid
                    else:
                        output = {"status": "rejected", "reason": f"Unknown tool: {tool}."}

                    state.messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(output, default=str)})
                    recorder.tool_result(tool_call_id, tool, params, output)
                    pending_tool = None
                    if finished:
                        recorder.finish(params["result"], state)
                        return {
                            "status": "success",
                            "output": recorder.mission,
                            "result_summary": recorder.mission["result_summary"],
                            "result_id": recorder.mission["mission_id"],
                            "artifact": str(recorder.path),
                        }

                recorder.record_state(state)

            raise RuntimeError(f"Agent step budget exhausted after {self.max_steps} turns.")
        except BaseException as error:
            if pending_tool is not None:
                call_id, tool, params = pending_tool
                recorder.tool_result(call_id, tool, params, error=str(error))
            recorder.fail(error, state)
            raise
