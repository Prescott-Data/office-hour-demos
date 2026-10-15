"""The watchdog: asks the numbers what they look like, and says what deserves your attention."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from jarviscore import AutoAgent
from pydantic import BaseModel, Field

from personal_finance import layouts
from personal_finance.contracts import Finding, LayoutProfile, Transaction, Verdict
from personal_finance.desk import DEFAULT_USER, Desk
from personal_finance.masking import Masker
from personal_finance.notes import Notes
from personal_finance.probes import PROBES, Toolbox

LAYOUT_NAME = "mpesa-statement"
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
ROUNDS = 2

ASK = """
Answer with JSON only, in this shape:

{"run": [{"probe": "<name>", "takes": {"<argument>": "<value>"}}]}

Each round, ask for up to five probes whose figures would change what you would say. An empty
list says the figures already in hand settle it.
"""

TELL = """
Answer with JSON only, in this shape:

{"findings": [{"about": "<the label of the place, exactly as given, or none>",
               "topic": "<one of: repeat, missing, rising, unusual, commitment, other>",
               "say": "<one sentence to the person, quoting only figures above>",
               "why_it_matters": "<one short sentence>"}]}

Return up to %d findings. A finding earns its place when the figures show something they
would be surprised by and could act on.
"""


class Watched(BaseModel):
    """What the watchdog made of one statement, kept so it does not change under you."""

    findings: list[Finding] = Field(default_factory=list)
    probes_run: list[str] = Field(default_factory=list)
    statement: str = ""


class Watchdog(AutoAgent):
    """Decides what in a statement is worth saying out loud."""

    name = "Watchdog"
    role = "watchdog"
    capabilities = ["spending_oversight"]
    description = "Asks what the figures look like and reports what deserves attention."
    system_prompt = (
        "You look after someone's money. You work from the figures probes return rather than "
        "the statement itself. Something deserves their attention when the "
        "figures depart from that place's own pattern in a way they could act on: the same "
        "amount paid twice within minutes rather than spread through a day, a commitment that "
        "that is overdue against its own rhythm, an amount that has climbed between months, a "
        "new habit forming. Where they have told you a pattern is normal for them, believe them. "
        "Their attention is the scarce thing, so a handful of findings they would be surprised "
        "by is worth more than a long list, and it takes as many figures as it takes to find "
        "those few."
    )

    def __init__(
        self,
        layout: LayoutProfile | None = None,
        user: str = DEFAULT_USER,
        desk: Desk | None = None,
        agent_id=None,
    ):
        super().__init__(agent_id=agent_id)
        self.desk = desk if desk is not None else Desk(user)
        self.layout = layout if layout is not None else layouts.load(LAYOUT_NAME)
        self.spend_usd = 0.0
        self.masker = Masker()

    @staticmethod
    def fingerprint(transactions: list[Transaction]) -> str:
        seed = "|".join(sorted(t.reference for t in transactions))
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def _llm(self):
        if not hasattr(self, "llm") or self.llm is None:
            from jarviscore.config import settings
            from jarviscore.execution.llm import UnifiedLLMClient

            self.llm = UnifiedLLMClient(settings.model_dump())
        return self.llm

    async def _ask(self, prompt: str) -> dict:
        answer = await self._llm().generate(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        self.spend_usd += float(answer.get("cost_usd", 0.0) or 0.0)
        try:
            return json.loads(answer.get("content", ""))
        except json.JSONDecodeError:
            return {}

    async def review(
        self,
        transactions: list[Transaction],
        verdicts: dict[str, Verdict] | None = None,
        notes: Notes | None = None,
        keep: int = 6,
        fresh: bool = False,
    ) -> list[Finding]:
        """Worked out once per statement, then kept, with anything you dismissed left out."""
        notes = notes if notes is not None else self.desk.notes()
        statement = self.fingerprint(transactions)
        kept = self.desk.watched()
        if not fresh and statement in kept.data:
            return self._allowed(Watched(**kept.data[statement]).findings, notes)

        watched = await self._work_out(transactions, verdicts, notes, keep)
        watched.statement = statement
        kept.data[statement] = json.loads(watched.model_dump_json())
        kept.save()
        return self._allowed(watched.findings, notes)

    def _allowed(self, findings: list[Finding], notes: Notes) -> list[Finding]:
        """A topic you called normal for a place never comes back."""
        return [
            finding
            for finding in findings
            if finding.kind not in notes.normal(self._place_of(finding))
        ]

    @staticmethod
    def _place_of(finding: Finding) -> str:
        return finding.headline.split(":")[0].strip()

    async def _work_out(
        self,
        transactions: list[Transaction],
        verdicts: dict[str, Verdict] | None,
        notes: Notes,
        keep: int,
    ) -> Watched:
        toolbox = Toolbox(transactions, self.layout, notes)
        catalogue = [json.loads(probe.model_dump_json()) for probe in PROBES]
        # one orienting figure, so the first question arrives with something in hand
        gathered: dict[str, Any] = {"spending()": self.masker.hide(toolbox.run("spending"))}

        for _round in range(ROUNDS):
            wanted = await self._ask(
                json.dumps({"probes_you_can_run": catalogue, "already_answered": gathered},
                           default=str)
                + ASK
            )
            asked = wanted.get("run") or []
            if not asked:
                break
            for request in asked[:5]:
                name = str(request.get("probe", ""))
                takes = request.get("takes") or {}
                label = f"{name}({','.join(f'{k}={v}' for k, v in takes.items())})"
                gathered[label] = self.masker.hide(toolbox.run(name, **takes))

        if not gathered:
            return Watched()

        told = await self._ask(json.dumps({"figures": gathered}, default=str) + TELL % keep)
        return Watched(
            findings=self._read(told, gathered)[:keep],
            probes_run=sorted(gathered),
        )

    def _read(self, told: dict, gathered: dict) -> list[Finding]:
        stated = {
            match.group(0).replace(",", "").rstrip("0").rstrip(".")
            for match in NUMBER.finditer(json.dumps(gathered, default=str))
        }
        findings = []
        for entry in told.get("findings", []):
            sentence = str(entry.get("say", "")).strip()
            # a finding may only repeat figures a probe returned
            if not sentence or not self._grounded(sentence, stated):
                continue
            about = self.masker.reveal(str(entry.get("about", "")).strip())
            findings.append(
                Finding(
                    kind=str(entry.get("topic", "other")),
                    headline=f"{about}: {self.masker.reveal(sentence)}" if about else
                    self.masker.reveal(sentence),
                    evidence=[str(entry.get("why_it_matters", "")).strip()],
                )
            )
        return findings

    @staticmethod
    def _grounded(sentence: str, stated: set[str]) -> bool:
        for match in NUMBER.finditer(sentence):
            if match.group(0).replace(",", "").rstrip("0").rstrip(".") not in stated:
                return False
        return True
