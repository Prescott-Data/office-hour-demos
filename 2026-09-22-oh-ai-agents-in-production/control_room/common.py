"""Shared constants for the production control room demo."""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Imported first by server.py and worker.py, so .env is loaded before anything reads it.
try:
    from dotenv import load_dotenv
    load_dotenv(HERE.parent / ".env")
except ImportError:
    pass
RUN_DIR = HERE / ".run"
RUN_DIR.mkdir(exist_ok=True)

REDIS_URL = os.getenv("CR_REDIS_URL", "redis://localhost:6379/0")
SERVER_PORT = int(os.getenv("CR_PORT", "8090"))
TOOL_PORT = 18901       # fake third-party API (the "tool")
AZURE_PORT = 18902      # fake primary model provider
FALLBACK_PORT = 18903   # fake fallback model provider

FAKE_KEY = "sk_demo_control_room_not_a_real_key"
PROVIDER = "demo-crm"
CONNECTION_ID = f"{PROVIDER}:demo-user"

LEASE_SECONDS = 5
POLL_SECONDS = 0.5

STEPS = [
    ("intake", "Validate the release request"),
    ("plan", "Draft the release plan and remember it (tenant memory)"),
    ("fetch_config", "Fetch service config through the credential broker"),
    ("approve_release", "Human approval for the irreversible step"),
    ("execute", "Apply the release (idempotent)"),
    ("summarize", "Summarize with the model layer"),
]

MEM_PREFIX = "cr:memory"          # cr:memory:<tenant>


def memory_key(tenant: str) -> str:
    """Tenant scoping lives in the key shape: a helper only ever builds its own tenant's key."""
    return f"{MEM_PREFIX}:{tenant}"
