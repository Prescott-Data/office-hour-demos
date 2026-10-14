"""
Demo 3 - a provider that is "up" but has no capacity left.

No keys, no network. Runs JarvisCore's real UnifiedLLMClient
(jarviscore/execution/llm.py, _generate_inner) against two local fake servers:

  provider 1 (Azure client) -> answers every request: HTTP 429,
                               "Please retry after 3600 seconds."
  provider 2 (vLLM path)    -> answers normally

A client that honors "retry after" to the letter would sleep for an hour inside
its concurrency slot. The real loop treats a hint over its cap as "this
provider is out for the window", fails fast, and falls through.

Run:
    python beat3_fake_provider.py
"""
import asyncio
import logging
import sys
import time

from aiohttp import web

from jarviscore.execution.llm import UnifiedLLMClient

_TTY = sys.stdout.isatty()


def c(code, text):
    return f"\033[{code}m{text}\033[0m" if _TTY else text


hits = {"azure": 0, "vllm": 0}


async def azure_429(request):
    hits["azure"] += 1
    return web.json_response(
        {"error": {"code": "429", "message": (
            "Requests to the ChatCompletions_Create Operation have exceeded the call "
            "rate limit of your current pricing tier. Please retry after 3600 seconds."
        )}},
        status=429,
    )


async def vllm_ok(request):
    hits["vllm"] += 1
    return web.json_response({
        "choices": [{"message": {"role": "assistant", "content": "Fallback provider answered."},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
    })


async def serve(handler):
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return site._server.sockets[0].getsockname()[1]


class _Show(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            print(c("31", f"  llm.py > {record.getMessage()}"), flush=True)


async def main():
    sys.stdout.reconfigure(line_buffering=True)
    logging.getLogger("jarviscore.execution.llm").addHandler(_Show())
    logging.getLogger("jarviscore.execution.llm").propagate = False

    azure_port = await serve(azure_429)
    vllm_port = await serve(vllm_ok)

    client = UnifiedLLMClient(config={
        "promo_token": None, "claude_api_key": None, "anthropic_api_key": None,
        "gemini_api_key": None, "vertex_ai_enabled": False,
        "azure_api_key": "fake-key", "azure_endpoint": f"http://127.0.0.1:{azure_port}",
        "azure_deployment": "gpt-4o",
        "llm_endpoint": f"http://127.0.0.1:{vllm_port}", "llm_model": "local",
    })

    print(c("1", "\nprovider order:"), [p.value for p in client.provider_order])
    print(c("90", "azure  -> 429 'Please retry after 3600 seconds'  (quota window spent)"))
    print(c("90", "vllm   -> healthy"))
    print(c("1", "\nclient.generate('say hi')  # a naive client would now sleep for an hour\n"))

    t0 = time.time()
    result = await client.generate("say hi")
    elapsed = time.time() - t0

    print(c("1", f"\nanswered by: {result['provider']}   content: {result['content']!r}"))
    print(c("1", f"elapsed: {elapsed:.1f}s   (not 3600s)"))
    print(c("90", f"requests seen -> azure: {hits['azure']}   vllm: {hits['vllm']}\n"))


if __name__ == "__main__":
    asyncio.run(main())
