#!/usr/bin/env python3
"""
List what the Nexus gateway can connect to.

    python providers.py              # everything, grouped by auth type
    python providers.py git          # just the ones matching "git"
    python providers.py gmail        # and what to do when there are none

Why this exists rather than `jarviscore nexus list`: that command prints a
"Gateway providers:" header and then nothing. /v1/providers returns
{auth_type: {name: {...}}} and the CLI iterates it as if it were a list of
dicts, so p.get() raises AttributeError straight into a bare `except: pass`.
This script talks to the gateway directly, so everyone following along gets
the same output whichever framework version they have installed.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

GREEN, YELLOW, CYAN, DIM, BOLD, OFF = (
    "\033[32m", "\033[33m", "\033[36m", "\033[2m", "\033[1m", "\033[0m"
)


def fetch(gateway: str) -> dict:
    with urllib.request.urlopen(f"{gateway.rstrip('/')}/v1/providers", timeout=15) as r:
        return json.loads(r.read())


def flatten(payload: dict) -> list:
    """{auth_type: {name: meta}} -> [(name, auth_type), ...], newest shape first."""
    rows = []
    if isinstance(payload, dict):
        for auth_type, bundle in payload.items():
            if isinstance(bundle, dict):
                rows.extend((name, auth_type) for name in bundle)
    elif isinstance(payload, list):          # older gateway builds
        rows = [(p.get("name", "?"), p.get("auth_type", "?"))
                for p in payload if isinstance(p, dict)]
    return sorted(rows)


def main() -> int:
    gateway = os.getenv("NEXUS_GATEWAY_URL", "")
    if not gateway:
        print(f"{YELLOW}!{OFF}  NEXUS_GATEWAY_URL is not set.")
        print(f"{CYAN}i{OFF}  Copy .env.example to .env and fill it in.")
        return 1

    needle = (sys.argv[1] if len(sys.argv) > 1 else "").lower()

    try:
        rows = flatten(fetch(gateway))
    except urllib.error.HTTPError as e:
        print(f"{YELLOW}!{OFF}  Gateway returned HTTP {e.code}")
        return 1
    except Exception as e:
        print(f"{YELLOW}!{OFF}  Gateway unreachable: {e}")
        return 1

    total = len(rows)
    if needle:
        rows = [r for r in rows if needle in r[0].lower()]

    if not rows:
        print()
        print(f"{YELLOW}!{OFF}  No gateway provider matches {needle!r}.")
        print(f"{CYAN}i{OFF}  Register it:  jarviscore nexus register {needle} "
              f"--client-id=... --client-secret=...")
        print()
        return 0

    label = f"Gateway providers ({len(rows)}"
    label += f" of {total} matching {needle!r})" if needle else ")"
    print()
    print(f"{BOLD}  {label}:{OFF}")
    for name, auth_type in rows:
        print(f"  {GREEN}✓{OFF}  {name:<26} {DIM}{auth_type}{OFF}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
