"""
STEP 3 — read it back from GitHub, review it, remember.

Inspector reviews the file fetched from the GitHub API, not the copy on disk.
Reviewing what was actually committed is a different claim from reviewing what
we happen to have locally, and it is the one worth making.

Findings go into long-term memory under a workflow id that does not change
between runs, so a second run opens with what changed.

    python review_pr.py        # first run  — a fresh look
    python review_pr.py        # second run — "here is what changed"
"""
import asyncio
import json

from agents import Inspector
from config import TARGET_PATH, repo_slug
from runner import (banner, build_mesh, comment_on_pr, connect, link, load,
                    memory_for, ok, read_file, save, stage, think,
                    BOLD, DIM, GREEN, OFF, RULE)

SEV = {"critical": "\033[31m", "high": "\033[33m", "medium": "\033[36m", "low": "\033[2m"}


def render(findings: list) -> str:
    """The PR comment Inspector leaves behind."""
    lines = ["## Automated review", "", "| Severity | Type | Line | Issue |", "|---|---|---|---|"]
    for f in findings:
        lines.append(f"| **{f.get('severity','?')}** | {f.get('type','?')} | "
                     f"{f.get('line','?')} | {f.get('description','')} |")
    lines += ["", "_Posted by Inspector via JarvisCore._"]
    return "\n".join(lines)


async def main():
    push = load("push.json", as_json=True)
    banner("STEP 3 — review and memory", f"{repo_slug()} · PR #{push['pr_number']}")

    stage(1, "Starting the mesh")
    mesh = await build_mesh(Inspector)

    stage(2, "What do we remember about this repository?")
    memory = memory_for(mesh, step_id="review", agent_id="inspector")
    prior = await memory.ltm.load_summary() if memory.ltm else None
    ok("recalled a previous review" if prior else "nothing yet — this is a first look")

    stage(3, "Connecting to GitHub and reading the file back")
    proxy, conn = await connect(mesh, "github")
    source = await read_file(proxy, conn, push["branch"], TARGET_PATH)
    ok(f"{len(source)} characters fetched from the branch — not from disk")

    stage(4, "Inspector reviewing it")
    data = await think(mesh, "inspector", (
        f"Review this file. It is {TARGET_PATH} exactly as committed to "
        f"{repo_slug()} on branch {push['branch']}.\n\n"
        f"```python\n{source}\n```\n\n"
        + (f"For reference, here is your review of an EARLIER VERSION of this "
           f"file:\n{prior}\n\nReview the code above from scratch — line numbers "
           f"and contents may have changed. Then open your summary by saying what "
           f"is different from that earlier review. Do not copy findings forward "
           f"unless you can still see them in the code above.\n\n" if prior else "")
        + "Every severity value must be exactly one of these words: "
          "critical, high, medium, low. Never a number.\n\n"
          "Set result = {'success': True, 'data': {'severity': <highest severity word>, "
          "'summary': <2-3 sentences>, 'findings': [{'type':..., 'severity':..., "
          "'line':..., 'description':..., 'fix':...}]}}"
    ))

    findings = data.get("findings", [])
    stage(5, f"{len(findings)} findings · overall {BOLD}{data.get('severity','?')}{OFF}")
    for f in findings:
        colour = SEV.get(str(f.get("severity", "")).lower(), "")
        print(f"  {colour}{str(f.get('severity','?')).upper():<9}{OFF} "
              f"line {str(f.get('line','?')):<8} {f.get('type','?')}")
        print(f"            {DIM}{f.get('description','')}{OFF}")

    print(f"\n{DIM}  {data.get('summary','')}{OFF}")

    stage(6, "Posting the review on the pull request")
    url = await comment_on_pr(proxy, conn, push["pr_number"], render(findings))
    link("comment", url)

    stage(7, "Writing the findings to long-term memory")
    if memory.ltm:
        await memory.ltm.save_summary(json.dumps(
            {"severity": data.get("severity"), "summary": data.get("summary"),
             "findings": findings}, indent=2))
        ok("saved — run review_pr.py again and Inspector opens with what changed")

    save("review.json", data)
    print(f"\n  Next: {GREEN}python email_report.py{OFF} — draft the report and send it")

    await mesh.stop()


if __name__ == "__main__":
    asyncio.run(main())
