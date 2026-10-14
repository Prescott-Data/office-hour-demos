"""
Beat 3 demo — "we ran out of GPUs to buy, and the system still had to keep answering."

Only Azure is actually available to us, which turns out to match the real
incident better anyway: the real story was never "one cloud vendor down,
switch to another paid one" — it was "cloud GPU capacity ran out, fall back to
something running locally." So: Azure primary, a local model (via Ollama's
OpenAI-compatible endpoint) as the fallback. Free, self-hosted, nothing to
request access to.

Proves, live, against the real jarviscore-framework (v1.11.0) UnifiedLLMClient
— `jarviscore/execution/llm.py`, `_call_vllm` — no mocking. Ollama's
`/v1/chat/completions` is exactly the shape that method already expects; this
needed no framework code changes, only pointing `LLM_ENDPOINT` at it.

One-time setup:
    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull llama3.2:3b        # small, fast enough to answer in a few seconds
    ollama serve                    # usually starts automatically as a service

Then confirm it's up:
    curl http://localhost:11434/v1/models

Run:
    python beat3_failover.py
"""
import asyncio
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from jarviscore.execution.llm import UnifiedLLMClient

PROMPT = "In one sentence, what does a circuit breaker do in a distributed system?"

OLLAMA_ENDPOINT = os.getenv("LOCAL_LLM_ENDPOINT", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("LOCAL_LLM_MODEL", "llama3.2:3b")


def working_config() -> dict:
    """Azure primary, healthy — plus the local model registered as the
    fallback tier so it's in provider_order even when Azure is fine."""
    return {
        "azure_api_key": os.getenv("AZURE_API_KEY"),
        "azure_endpoint": os.getenv("AZURE_ENDPOINT"),
        "azure_api_version": os.getenv("AZURE_API_VERSION", "2024-10-21"),
        "claude_api_key": None,  # not available to us — Azure + local only
        "llm_endpoint": OLLAMA_ENDPOINT,
        "llm_model": OLLAMA_MODEL,
    }


def broken_primary_config() -> dict:
    """Same config, Azure deliberately unreachable — staged for the demo,
    never written back to disk. This is the live 'capacity just vanished'
    moment: Azure fails immediately, the local model is still there."""
    cfg = working_config()
    cfg["azure_api_key"] = "sk-demo-deliberately-invalid"
    cfg["azure_endpoint"] = "https://this-resource-does-not-exist.openai.azure.com"
    return cfg


async def run_once(label: str, config: dict) -> None:
    client = UnifiedLLMClient(config=config)
    print(f"\n=== {label} ===")
    print("provider order detected:", [p.value for p in client.provider_order])

    result = await client.generate(prompt=PROMPT, max_tokens=120)
    print("answered by provider:", result["provider"])
    print("model:                ", result.get("model"))
    print("cost:                 ", f"${result.get('cost_usd', 0):.4f}")
    print("content:              ", result["content"].strip())


async def main() -> None:
    await run_once("normal — Azure primary, healthy", working_config())
    await run_once("Azure capacity just vanished", broken_primary_config())
    print(
        "\nSame call, same code, same prompt. The second run's Azure attempt "
        "failed immediately and the client fell back to a model running on "
        "this machine, at zero cost, without the caller noticing or branching "
        "on it — the same shape as the real incident, minus the part where "
        "we had no GPUs left anywhere to buy."
    )


if __name__ == "__main__":
    asyncio.run(main())
