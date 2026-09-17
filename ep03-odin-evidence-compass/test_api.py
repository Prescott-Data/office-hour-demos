import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api import ARTIFACT_DIRECTORY, app
from agent import AgentConfigurationError, _MISSION_EVENT_SINK


class DemoApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def test_graph_comes_from_loaded_arango_database(self):
        response = self.client.get("/api/graph")

        self.assertEqual(response.status_code, 200)
        graph = response.json()
        self.assertEqual(graph["database"], "odin_demo_validation")
        self.assertEqual(graph["counts"], {"nodes": 775, "edges": 2619})
        self.assertEqual(len(graph["nodes"]), 775)
        self.assertEqual(len(graph["edges"]), 2619)
        self.assertTrue(all(edge["relation"] for edge in graph["edges"]))

    def test_retrieval_preserves_complete_result_before_response(self):
        response = self.client.post(
            "/api/retrieve",
            json={
                "seed": "ExtractedEntities/claim_00",
                "max_paths": 12,
                "hop_limit": 10,
                "beam_width": 32,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        artifact_path = ARTIFACT_DIRECTORY / payload["artifact"]
        saved = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        self.assertEqual(saved["call_id"], payload["call_id"])
        self.assertEqual(saved["result"], payload["result"])
        self.assertEqual(
            len(saved["result"]["paths"]),
            saved["observations"]["returned_paths"],
        )
        self.assertEqual(
            saved["result"]["paths"][-1]["edges"][-1]["relation"],
            payload["result"]["paths"][-1]["edges"][-1]["relation"],
        )
        self.assertEqual(len(saved["navigation"]["paths"]), len(saved["result"]["paths"]))
        tail_navigation = saved["navigation"]["paths"][-1]
        self.assertTrue(tail_navigation["edges"][-1]["source_document"].startswith("Documents/"))
        self.assertGreater(tail_navigation["signals"]["structural_ppr"], 0)
        self.assertGreater(tail_navigation["signals"]["semantic_npll"], 0)
        self.assertEqual(tail_navigation["signals"]["temporal"]["status"], "inactive")

    def test_unknown_agent_artifact_fails_clearly(self):
        response = self.client.get("/api/agent/artifacts/not-a-real-mission")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Unknown agent mission: not-a-real-mission")

    @patch("api.CLAIMS_AGENT.run", new_callable=AsyncMock)
    def test_agent_provider_failure_is_explicit(self, run_agent):
        run_agent.side_effect = AgentConfigurationError("AZURE_API_KEY and AZURE_ENDPOINT must be configured.")

        response = self.client.post("/api/agent/investigate", json={})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "Agent LLM provider is not configured or unavailable.",
        )
        run_agent.assert_awaited_once()

    @patch("api.CLAIMS_AGENT.run", new_callable=AsyncMock)
    def test_agent_stream_delivers_events_as_they_are_published(self, run_agent):
        async def publish_events(task, odin_bounds=None):
            sink = _MISSION_EVENT_SINK.get()
            self.assertIsNotNone(sink)
            self.assertEqual(odin_bounds, {"max_paths": 12, "hop_limit": 10, "beam_width": 32})
            sink({"type": "mission_started", "mission_id": "mission-live", "task": task})
            sink({
                "type": "mission_event",
                "event": {
                    "event_id": "event-live",
                    "timestamp": "2026-08-31T00:00:00+00:00",
                    "type": "odin_started",
                    "data": {"seed": "ExtractedEntities/claim_00", "max_paths": 12},
                },
            })
            return {"status": "success", "result_summary": "complete"}

        run_agent.side_effect = publish_events
        response = self.client.post("/api/agent/investigate/stream", json={})

        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual([event["type"] for event in events], ["mission_started", "mission_event"])
        self.assertEqual(events[-1]["event"]["data"]["max_paths"], 12)


if __name__ == "__main__":
    unittest.main()
