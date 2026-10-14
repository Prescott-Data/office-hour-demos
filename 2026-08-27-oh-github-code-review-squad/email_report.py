"""
STEP 4 — draft the report, look at it, then send it.

Reporter drafts the email from the findings in step 3. We print it, and nothing
leaves until you say so at the prompt. Then Google consent, and it sends.

    python email_report.py
"""
import asyncio
import html
import re

import config
from agents import Reporter
from config import GOOGLE_PROVIDER, GOOGLE_SCOPES, RECIPIENT, SENDER_NAME, repo_slug
from runner import (banner, build_mesh, confirm, connect, link, load, ok,
                    send_email, stage, think, warn, BOLD, DIM, GREEN, OFF, RULE)


def as_text(markup: str) -> str:
    """Rough plain-text render, so the terminal preview is readable."""
    text = re.sub(r"<br\s*/?>", "\n", markup)
    text = re.sub(r"</(p|div|tr|h[1-6]|table)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(re.sub(r"\n{3,}", "\n\n", text)).strip()


async def main():
    review = load("review.json", as_json=True)
    push = load("push.json", as_json=True)
    banner("STEP 4 — the report", f"{repo_slug()} → {RECIPIENT}")

    stage(1, "Starting the mesh")
    mesh = await build_mesh(Reporter)

    stage(2, "Reporter drafting the email")
    findings = review.get("findings", [])
    criticals = sum(1 for f in findings if str(f.get("severity", "")).lower() == "critical")
    data = await think(mesh, "reporter", (
        f"Write the review email.\n\n"
        f"Repository: {repo_slug()}   Branch: {push['branch']}\n"
        f"Pull request: {push['pr_url']}\n"
        f"Overall severity: {review.get('severity')}   Critical issues: {criticals}\n"
        f"Summary: {review.get('summary')}\n"
        f"Findings: {findings}\n\n"
        f"It is going to {RECIPIENT} and it is from {SENDER_NAME}.\n"
        f"Set result = {{'success': True, 'data': {{'subject': <subject line>, "
        f"'html': <the full HTML body>}}}}"
    ))

    subject, body = data.get("subject", ""), data.get("html", "")
    if not body:
        raise RuntimeError("Reporter returned no HTML body — re-run email_report.py.")

    stage(3, "What is about to be sent")
    print(f"  {DIM}To      {OFF}{RECIPIENT}")
    print(f"  {DIM}Subject {OFF}{BOLD}{subject}{OFF}")
    print(f"{DIM}{RULE}{OFF}")
    print(as_text(body))
    print(f"{DIM}{RULE}{OFF}")

    if not await confirm(f"Send this to {RECIPIENT}?"):
        warn("not sent — nothing left the machine")
        await mesh.stop()
        return

    stage(4, f"Connecting to {GOOGLE_PROVIDER} through Nexus")
    proxy, conn = await connect(mesh, GOOGLE_PROVIDER, scopes=GOOGLE_SCOPES)

    stage(5, "Sending")
    message_id = await send_email(proxy, conn, RECIPIENT, subject, body)
    ok(f"delivered — Gmail message id {message_id}")
    link("pull request", push["pr_url"])
    print(f"\n  {GREEN}That is the whole loop.{OFF} Open the inbox.")

    await mesh.stop()


if __name__ == "__main__":
    asyncio.run(main())
