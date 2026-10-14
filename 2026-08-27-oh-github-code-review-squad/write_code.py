"""
STEP 1 — the agent alone.

One AutoAgent, three attributes, no infrastructure at all: no Nexus, no Redis,
no credentials beyond the model. It writes a payments module with five
deliberate defects and we check all five are there.

    python write_code.py
"""
import asyncio

from agents import CodeSmith
from runner import (RULE, DIM, GREEN, OFF, RED, banner, build_mesh, check_defects,
                    ok, save, stage, warn, write_module)


async def main():
    banner("STEP 1 — the agent alone", "three attributes, zero infrastructure")

    stage(1, "Starting a mesh with one agent")
    mesh = await build_mesh(CodeSmith)
    ok("mesh up — no Nexus connection, no credentials in play")

    stage(2, "Asking CodeSmith for the module")
    source, results = await write_module(mesh)
    ok(f"{len(source)} characters of Python returned")

    stage(3, "The module it wrote")
    print(f"{DIM}{RULE}{OFF}")
    print(source)
    print(f"{DIM}{RULE}{OFF}")

    stage(4, "Checking the five defects are actually present")
    missing = [label for label, found in results if not found]
    for label, found in results:
        print(f"  {GREEN}✓{OFF} {label}" if found else f"  {RED}✗{OFF} {label}")

    if missing:
        warn(f"{len(missing)} defect(s) still missing after 3 tries — run write_code.py again")
    else:
        path = save("payments.py", source)
        ok(f"all five present — saved to {path.parent.name}/{path.name}")
        print(f"\n  Next: {GREEN}python push_and_open_pr.py{OFF} — push it to GitHub through Nexus")

    await mesh.stop()


if __name__ == "__main__":
    asyncio.run(main())
