"""
The only file you edit before the session.

Everything else — agents.py, the four scripts, main.py — reads from here, so the
two of you can swap sender and recipient without touching demo code.
"""
import os
from datetime import datetime, timezone
from pathlib import Path

# Load .env before anything reads os.environ. Without this, copying
# .env.example to .env appears to do nothing and every getenv below falls back
# to its default — which is how you get "NEXUS_GATEWAY_URL is not set" while
# staring at a .env that plainly contains it.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:  # pragma: no cover - dotenv is in requirements.txt
    pass

# ── GitHub ────────────────────────────────────────────────────────────────────
# The repo MUST be public. The Nexus gateway's GitHub app carries `public_repo`
# and not `repo`, so a private repo 403s on the first write.
# Your own account or org, and a public repo the agents may push to.
GITHUB_OWNER = os.getenv("DEMO_GITHUB_OWNER", "")
GITHUB_REPO  = os.getenv("DEMO_GITHUB_REPO",  "code-review-squad-sandbox")

# One branch per run keeps re-runs from colliding.
RUN_STAMP    = datetime.now(timezone.utc).strftime("%m%d-%H%M")
BRANCH       = os.getenv("DEMO_BRANCH", f"agent/payments-{RUN_STAMP}")
BASE_BRANCH  = os.getenv("DEMO_BASE_BRANCH", "main")
TARGET_PATH  = "src/payments.py"

# ── Google ────────────────────────────────────────────────────────────────────
# The gateway carries "google-workspace", not "gmail", and it already has a
# Google OAuth client registered against it — so nobody needs to create one in
# the Google Cloud console. We only complete consent.
#
# The catch: google-workspace is NOT in JarvisCore's local PROVIDER_CATALOG, so
# get_scopes() returns [] and the gateway would send Google a consent screen
# asking for nothing at all. Consent would "succeed" and every Gmail call would
# then 403. So we always pass the scopes explicitly — see runner.connect().
GOOGLE_PROVIDER = os.getenv("DEMO_GOOGLE_PROVIDER", "google-workspace")
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Whoever completes the Google consent is the sender; the report goes to
# DEMO_RECIPIENT.
SENDER_NAME  = os.getenv("DEMO_SENDER_NAME", "Code Review Squad")
RECIPIENT    = os.getenv("DEMO_RECIPIENT", "you@example.com")

# ── Memory ────────────────────────────────────────────────────────────────────
# Deliberately stable across runs. LongTermMemory is keyed on workflow_id, so
# reusing this id is what lets run #2 recall run #1 — that's the memory beat.
MEMORY_WORKFLOW_ID = f"code-review-{GITHUB_OWNER}-{GITHUB_REPO}".lower()

# ── Nexus ─────────────────────────────────────────────────────────────────────
# Set this in .env — see .env.example. Not defaulted on purpose: a wrong
# gateway fails somewhere confusing. Checked at use rather than at import,
# so write_code.py (which needs no infrastructure at all) still runs without it.
NEXUS_GATEWAY_URL = os.getenv("NEXUS_GATEWAY_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Consent lives in process memory only, so a restart re-prompts. Capture the
# connection_id a run prints and export it to skip consent next time.
GITHUB_CONNECTION_ID = os.getenv("NEXUS_GITHUB_CONNECTION_ID")
GOOGLE_CONNECTION_ID = os.getenv("NEXUS_GOOGLE_CONNECTION_ID")


def mesh_config() -> dict:
    """
    Config every step passes to Mesh() — Nexus on, Redis on.

    `auth_mode` is the switch that matters. Mesh only builds an
    AuthenticationManager when this key is truthy (core/mesh.py:382); without
    it, NEXUS_GATEWAY_URL is quietly ignored, no agent gets _auth_manager, and
    every nexus_call() in the demo is a stub that raises. Nothing warns you.
    """
    if not NEXUS_GATEWAY_URL:
        raise RuntimeError(
            "NEXUS_GATEWAY_URL is not set — copy .env.example to .env and fill it in. "
            "Without it no Nexus connection is resolved and nexus_call() stays a stub."
        )
    return {
        "auth_mode": "production",
        # The SWIM peer transport needs an optional dependency we do not use —
        # this demo is a single process. Leaving it on just prints a scary
        # "P2P coordinator init failed" line at startup.
        "p2p_enabled": False,
        "nexus_gateway_url": NEXUS_GATEWAY_URL,
        "nexus_return_url": os.getenv("NEXUS_RETURN_URL", "http://localhost:9090/callback"),
        "redis_url": REDIS_URL,
    }


def repo_slug() -> str:
    if not GITHUB_OWNER:
        raise RuntimeError(
            "DEMO_GITHUB_OWNER is not set — set it in .env to the account or org that "
            "owns the public repo the agents should push to."
        )
    return f"{GITHUB_OWNER}/{GITHUB_REPO}"


def branch_url() -> str:
    return f"https://github.com/{repo_slug()}/tree/{BRANCH}"
