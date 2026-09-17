import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import AgentState, ClaimsAgent, MissionRecorder, _MISSION_EVENT_SINK, _validate_result


CLAIM = "ExtractedEntities/claim_00"
DEVICE = "ExtractedEntities/device_02"
PERSON = "ExtractedEntities/person_09"
ACCOUNT = "ExtractedEntities/account_00"


def model_response(rationale, tool, arguments, call_id="call-1"):
    return {
        "id": f"model-{tool}",
        "model": "fake",
        "choices": [{"finish_reason": "tool_calls", "message": {
            "content": rationale,
            "tool_calls": [{"id": call_id, "type": "function", "function": {"name": tool, "arguments": json.dumps(arguments)}}],
        }}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def generate(self, *, messages, tools):
        self.requests.append({"messages": json.loads(json.dumps(messages)), "tools": tools})
        return self.responses.pop(0)


def retrieval(*, seed, max_paths, hop_limit, beam_width):
    path = {
        "score": 0.75,
        "edges": [{"u": seed, "v": DEVICE, "relation": "used_device"}],
    }
    return {
        "call_id": "odin-claim-1042",
        "artifact": "odin-claim-1042.json",
        "requested": {"seeds": [seed], "max_paths": max_paths, "hop_limit": hop_limit, "beam_width": beam_width},
        "effective": {"max_paths": max_paths, "hop_limit": hop_limit, "beam_width": beam_width},
        "observations": {"returned_paths": 1},
        "navigation": {"paths": [path], "retained_node_ids": [seed, DEVICE], "retained_edge_ids": ["edge-1"], "summary": {}},
        "result": {"paths": [path], "topk_ppr": [[seed, 1.0], [DEVICE, 0.4]], "insight_score": 0.8, "trace": {"diagnostic": True}},
    }


class ClaimsAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_loop_chooses_tools_updates_scratchpad_and_finishes(self):
        result = {
            "findings": {"Claim 1042": {"recommendation": "escalate", "justification": "Claim 1042 used device_02."}},
            "evidence": {
                "follow_up_seeds": [DEVICE, PERSON, ACCOUNT],
                "paths": ["Claim 1042 --filed_from--> device_02"],
                "source_records": ["Documents/record_006"],
                "odin_call_ids": ["odin-claim-1042"],
            },
            "limitations": ["The path does not establish intent."],
            "verification_actions": ["Inspect the source record."],
            "conclusion": "Zero claims cleared; one claim escalated for human investigation.",
        }
        model = FakeModel([
            model_response("Resolve the claim label before navigating.", "find_graph_entities", {"query": "Claim 1042"}, "call-1"),
            model_response("Navigate from the resolved claim.", "retrieve_with_odin", {"seed": CLAIM}, "call-2"),
            model_response("Inspect the filing device and its recorded owner.", "retrieve_with_odin", {"seed": DEVICE}, "call-3"),
            model_response("Corroborate the controller through independent account and person routes.", "retrieve_with_odin", {"seed": PERSON}, "call-4"),
            model_response("Check the payment bridge independently.", "retrieve_with_odin", {"seed": ACCOUNT}, "call-5"),
            model_response("Retain the cross-claim device observation.", "update_scratchpad", {"note": f"Claim 1042 resolves to {CLAIM}; it used device_02."}, "call-6"),
            model_response("The recorded route is sufficient for escalation, with limitations.", "finish", {"result": result}, "call-7"),
        ])

        with tempfile.TemporaryDirectory() as directory:
            agent = ClaimsAgent(
                retrieval,
                lambda query: {"status": "success", "query": query, "matches": [{"id": CLAIM, "label": "Claim 1042"}]},
                model=model,
                artifact_directory=directory,
            )
            response = await agent.run("Investigate Claim 1042")
            artifact = json.loads(Path(response["artifact"]).read_text(encoding="utf-8"))

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["result_summary"], "0 cleared; 1 escalated.")
        tool_events = [event["data"]["tool"] for event in artifact["events"] if event["type"] == "tool_result"]
        self.assertEqual(tool_events, ["find_graph_entities", "retrieve_with_odin", "retrieve_with_odin", "retrieve_with_odin", "retrieve_with_odin", "update_scratchpad", "finish"])
        self.assertIn(CLAIM, artifact["scratchpad"])
        self.assertEqual(artifact["odin_calls"][0]["result"]["paths"][-1]["edges"][-1]["relation"], "used_device")
        self.assertTrue(any(event["type"] == "scratchpad_updated" for event in artifact["events"]))
        odin_started = next(event for event in artifact["events"] if event["type"] == "odin_started")
        odin_result = next(event for event in artifact["events"] if event["type"] == "odin_result")
        self.assertEqual(odin_started["data"]["turn_id"], 2)
        self.assertEqual(odin_started["data"]["tool_call_id"], "call-2")
        self.assertEqual(odin_result["data"]["tool_call_id"], "call-2")
        final_messages = json.dumps(model.requests[-1]["messages"])
        self.assertIn("used_device", final_messages)

    async def test_model_input_limit_fails_instead_of_trimming_tail_evidence(self):
        state = AgentState(task="Investigate Claim 1042")
        tail_relation = "tail_relation_after_former_limit"
        state.messages.append({
            "role": "tool",
            "tool_call_id": "tool-1",
            "content": json.dumps({"paths": [{"edges": [{"relation": tail_relation, "evidence": "x" * 2_000}]}]}),
        })
        agent = ClaimsAgent(retrieval, lambda query: {"matches": []}, model=FakeModel([]))

        with patch.dict(os.environ, {"AGENT_MODEL_INPUT_CHAR_LIMIT": "100"}):
            with self.assertRaisesRegex(RuntimeError, "stopped without truncation"):
                agent._guard_messages(state.messages)

        with patch.dict(os.environ, {"AGENT_MODEL_INPUT_CHAR_LIMIT": "10000"}):
            agent._guard_messages(state.messages)

    async def test_stream_contains_complete_model_and_odin_results(self):
        streamed = []
        token = _MISSION_EVENT_SINK.set(streamed.append)
        try:
            with tempfile.TemporaryDirectory() as directory:
                recorder = MissionRecorder("Investigate Claim 1042", directory)
                long_tail = "complete-model-output" * 10_000
                recorder.model_result(
                    "model-call",
                    {"system_prompt": "complete", "prompt": "complete"},
                    {"choices": [{"message": {"content": long_tail}}]},
                )
                recorder.odin_result(retrieval(seed=CLAIM, max_paths=12, hop_limit=10, beam_width=32))
        finally:
            _MISSION_EVENT_SINK.reset(token)

        model_event = next(item["event"] for item in streamed if item["type"] == "mission_event" and item["event"]["type"] == "model_response")
        self.assertEqual(model_event["data"]["response"]["choices"][0]["message"]["content"], long_tail)
        odin_event = next(item for item in streamed if item["type"] == "odin_retrieval")
        self.assertEqual(odin_event["retrieval"]["result"]["paths"][-1]["edges"][-1]["relation"], "used_device")

    async def test_completion_contract_is_generic_and_does_not_encode_verdicts(self):
        claims = {"Claim 1042", "Claim 1173"}
        result = {
            "findings": {
                label: {"recommendation": recommendation, "justification": f"Recorded evidence for {label}."}
                for label, recommendation in (("Claim 1042", "clear"), ("Claim 1173", "escalate"))
            },
            "evidence": {
                "follow_up_seeds": [DEVICE, PERSON, ACCOUNT],
                "paths": ["Claim 1042 --filed_from--> device_02"],
                "source_records": ["Documents/record_006"],
                "odin_call_ids": ["call-a", "call-b"],
            },
            "limitations": ["Human verification remains required."],
            "verification_actions": ["Inspect records."],
            "conclusion": "One claim cleared; one claim escalated.",
        }
        self.assertEqual(_validate_result(result, claims), (True, ""))
        result["findings"]["Claim 1173"]["recommendation"] = "fraud"
        valid, reason = _validate_result(result, claims)
        self.assertFalse(valid)
        self.assertIn("clear' or 'escalate", reason)

        result["findings"]["Claim 1173"]["recommendation"] = "escalate"
        result["limitations"] = "Human verification remains required."
        valid, reason = _validate_result(result, claims)
        self.assertFalse(valid)
        self.assertIn("array", reason)


if __name__ == "__main__":
    unittest.main()
