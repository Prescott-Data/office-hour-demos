"""
Demo Tracer - Real-time trace emission for dashboard visualization.

Usage:
    from shared.tracer import DemoTracer

    tracer = DemoTracer()
    tracer.start_workflow("wf-123", "Code Review", ["Security", "Performance"])
    tracer.thinking("Security", "Analyzing code for vulnerabilities...")
    tracer.action("Security", "scan_vulnerabilities", {"file": "main.py"})
    tracer.observation("Security", "Found 2 critical issues")
    tracer.step_complete("security", "Security", "success", "2 vulnerabilities found")
    tracer.workflow_complete({"status": "completed", "report": "..."})
"""

import asyncio
import httpx
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DemoTracer:
    """Emits trace events to the dashboard for real-time visualization."""

    def __init__(self, dashboard_url: str = "http://localhost:8080"):
        self.dashboard_url = dashboard_url
        self.workflow_id: Optional[str] = None
        self.enabled = True
        self._client: Optional[httpx.AsyncClient] = None
        # Delay between traces for visual effect (ms)
        self.trace_delay = 0.15  # 150ms between traces

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=5.0)
        return self._client

    async def _emit(self, trace_type: str, agent: str, data: Dict[str, Any], delay: bool = True):
        """Emit a trace event to the dashboard."""
        if not self.enabled:
            return

        trace = {
            "workflow_id": self.workflow_id,
            "type": trace_type,
            "agent": agent,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }

        try:
            client = await self._get_client()
            await client.post(
                f"{self.dashboard_url}/api/trace",
                json=trace
            )
            # Add delay for visual streaming effect
            if delay and self.trace_delay > 0:
                await asyncio.sleep(self.trace_delay)
        except Exception as e:
            # Don't fail the demo if dashboard isn't running
            logger.debug(f"Could not emit trace: {e}")

    def _emit_sync(self, trace_type: str, agent: str, data: Dict[str, Any]):
        """Synchronous wrapper for emit - creates event loop if needed."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._emit(trace_type, agent, data))
            else:
                loop.run_until_complete(self._emit(trace_type, agent, data))
        except RuntimeError:
            # No event loop, create one
            asyncio.run(self._emit(trace_type, agent, data))

    # --- Workflow Events ---

    async def start_workflow(self, workflow_id: str, demo_name: str, agents: List[str]):
        """Mark workflow start."""
        self.workflow_id = workflow_id
        await self._emit("workflow_start", "Orchestrator", {
            "workflow_id": workflow_id,
            "demo": demo_name,
            "agents": agents,
            "message": f"Starting {demo_name}"
        })

    async def workflow_complete(self, result: Dict[str, Any]):
        """Mark workflow complete."""
        await self._emit("workflow_complete", "Orchestrator", {
            "status": result.get("status", "completed"),
            "message": "Workflow completed successfully"
        })

    # --- Agent Cognitive Events ---

    async def thinking(self, agent: str, thought: str):
        """Agent is reasoning/planning."""
        await self._emit("thinking", agent, {"thought": thought})

    async def action(self, agent: str, tool: str, args: Optional[Dict] = None):
        """Agent is executing a tool/action."""
        await self._emit("action", agent, {
            "action": f"Executing {tool}",
            "tool": tool,
            "args": args or {}
        })

    async def observation(self, agent: str, result: str):
        """Agent received a result/observation."""
        await self._emit("observation", agent, {"result": result})

    async def working(self, agent: str, status: str):
        """Agent is actively working (progress indicator)."""
        await self._emit("working", agent, {"thought": status}, delay=False)

    # --- Communication Events ---

    async def mailbox(self, from_agent: str, to_agent: str, message: str):
        """Agent-to-agent communication."""
        await self._emit("mailbox", to_agent, {
            "from": from_agent,
            "to": to_agent,
            "message": message
        })

    # --- Progress Events ---

    async def step_start(self, step_id: str, agent: str, task: str):
        """Agent claims/starts a step."""
        await self._emit("step_start", agent, {
            "step_id": step_id,
            "task": task
        })

    async def step_complete(self, step_id: str, agent: str, status: str, output_preview: str = ""):
        """Step finished."""
        await self._emit("step_complete", agent, {
            "step_id": step_id,
            "status": status,
            "output_preview": output_preview[:200] if output_preview else ""
        })

    async def error(self, agent: str, error_message: str):
        """Something went wrong."""
        await self._emit("error", agent, {"error": error_message})

    # --- Cleanup ---

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Global tracer instance for convenience
_tracer: Optional[DemoTracer] = None


def get_tracer(dashboard_url: str = "http://localhost:8080") -> DemoTracer:
    """Get or create the global tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = DemoTracer(dashboard_url)
    return _tracer
