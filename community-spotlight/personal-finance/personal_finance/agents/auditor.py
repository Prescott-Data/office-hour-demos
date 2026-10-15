"""The auditor: works out what this month cost that need not have, by asking the numbers."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

from jarviscore import AutoAgent
from pydantic import BaseModel, Field

from personal_finance import layouts
from personal_finance.contracts import LayoutProfile, Transaction
from personal_finance.desk import DEFAULT_USER, Desk
from personal_finance.masking import Masker
from personal_finance.notes import Notes
from personal_finance.probes import PROBES, Toolbox
from personal_finance.rulings import Rulings

LAYOUT_NAME = "mpesa-statement"
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
ROUNDS = 2

ASK = """
Answer with JSON only, in this shape:

{"run": [{"probe": "<name>", "takes": {"<argument>": "<value>"}}]}

Each round, ask for up to five probes whose figures would change your answer. An empty list
says the figures already in hand settle it.
"""

DECIDE = """
Answer with JSON only, in this shape:

{"lines": [{"what": "<a few words naming it>",
            "amount": "<a figure from the probes>",
            "avoidable": true,
            "says": "<one sentence to the person>"}],
 "caveat": "<one sentence on what this figure does not mean>"}

Every amount is a figure a probe returned. Mark `avoidable` true where a different choice on
the day would have kept the money, and false where they bought something, so the total stays
honest.
"""


class Line(BaseModel):
    what: str
    amount: Decimal
    avoidable: bool
    says: str
    your_call: bool = False  # True once you have ruled on it yourself


class Audit(BaseModel):
    """What the period cost beyond the things bought, and how sure each part is."""

    lines: list[Line] = Field(default_factory=list)
    caveat: str = ""
    spent: Decimal = Decimal(0)
    probes_run: list[str] = Field(default_factory=list)
    statement: str = ""  # which statement this was worked out from

    @property
    def avoidable_total(self) -> Decimal:
        return sum((line.amount for line in self.lines if line.avoidable), Decimal(0))

    def headline(self) -> str:
        if not self.lines:
            return "nothing stood out as avoidable"
        return f"{self.avoidable_total} of what left need not have"

    def unruled(self) -> list[Line]:
        """The lines still carrying the agent's opinion rather than yours."""
        return [line for line in self.lines if not line.your_call]


class Auditor(AutoAgent):
    """Decides what in a period was avoidable cost rather than something bought."""

    name = "Auditor"
    role = "auditor"
    capabilities = ["avoidable_cost"]
    description = "Works out what a period cost that need not have."
    system_prompt = (
        "You work out what somebody's money went on that bought them nothing. You work from "
        "the figures probes return rather than the statement itself. Money is avoidable when a "
        "different choice on the day would have kept it: a charge for a way of paying, the "
        "price of borrowing where waiting was open to them, the same amount paid twice within "
        "minutes, a rhythm of payments for something they have stopped using. Money spent on "
        "things they chose to buy counts as cost, however large, and holding that line is what "
        "makes the whole figure trustworthy. Where the figures leave it open, saying so is "
        "worth more than a number."
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

    def _llm(self):
        if not hasattr(self, "llm") or self.llm is None:
            from jarviscore.config import settings
            from jarviscore.execution.llm import UnifiedLLMClient

            self.llm = UnifiedLLMClient(settings.model_dump())
        return self.llm

    async def _ask(self, prompt: str, temperature: float = 0.2) -> dict:
        answer = await self._llm().generate(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        self.spend_usd += float(answer.get("cost_usd", 0.0) or 0.0)
        try:
            return json.loads(answer.get("content", ""))
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def fingerprint(transactions: list[Transaction]) -> str:
        """Identifies one statement, so its audit is worked out once and then kept."""
        seed = "|".join(sorted(t.reference for t in transactions))
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def apply_rulings(self, audit: Audit, rulings: Rulings | None = None) -> Audit:
        """Your call on a line replaces the agent's, every time it is read back."""
        rulings = rulings if rulings is not None else self.desk.rulings()
        for line in audit.lines:
            said = rulings.says(line.what)
            if said is not None:
                line.avoidable, line.your_call = said, True
        return audit

    async def audit(
        self,
        transactions: list[Transaction],
        notes: Notes | None = None,
        rulings: Rulings | None = None,
        fresh: bool = False,
        mask: bool = True,
    ) -> Audit:
        """Worked out once per statement, then kept, with your rulings laid over it."""
        statement = self.fingerprint(transactions)
        kept = self.desk.audits()
        if not fresh and statement in kept.data:
            return self.apply_rulings(Audit(**kept.data[statement]), rulings)

        audit = await self._work_out(transactions, notes, mask)
        audit.statement = statement
        kept.data[statement] = json.loads(audit.model_dump_json())
        kept.save()
        return self.apply_rulings(audit, rulings)

    async def _work_out(
        self,
        transactions: list[Transaction],
        notes: Notes | None = None,
        mask: bool = True,
    ) -> Audit:
        """Let the agent choose what to measure, then let it say what the measurements mean."""
        toolbox = Toolbox(transactions, self.layout, notes or self.desk.notes())
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
                answer = toolbox.run(name, **takes)
                gathered[label] = self.masker.hide(answer) if mask else answer

        if not gathered:
            return Audit(spent=toolbox._spending()["spent"])

        decided = await self._ask(
            json.dumps({"figures": gathered}, default=str) + DECIDE, temperature=0.0
        )
        return self._read(decided, gathered, toolbox)

    def _read(self, decided: dict, gathered: dict, toolbox: Toolbox) -> Audit:
        stated = {
            match.group(0).replace(",", "").rstrip("0").rstrip(".")
            for match in NUMBER.finditer(json.dumps(gathered, default=str))
        }
        audit = Audit(
            spent=toolbox._spending()["spent"],
            caveat=str(decided.get("caveat", "")).strip(),
            probes_run=sorted(gathered),
        )
        for entry in decided.get("lines", []):
            amount = str(entry.get("amount", "")).replace(",", "").strip()
            # a line may only carry a figure a probe returned
            if amount.rstrip("0").rstrip(".") not in stated:
                continue
            try:
                audit.lines.append(
                    Line(
                        what=self.masker.reveal(str(entry.get("what", "")).strip()),
                        amount=Decimal(amount),
                        avoidable=bool(entry.get("avoidable", False)),
                        says=self.masker.reveal(str(entry.get("says", "")).strip()),
                    )
                )
            except (ValueError, ArithmeticError):
                continue
        return audit

    async def on_peer_request(self, message) -> dict | None:
        """Hand another agent the audit already worked out, with no model call at all."""
        data = message.data if isinstance(message.data, dict) else {}
        wanted = f"{data.get('capability', '')} {data.get('task', '')}"
        if "avoidable" not in wanted:
            return None
        statement = str(data.get("statement", ""))
        kept = self.desk.audits()
        if statement not in kept.data:
            return {"status": "failure", "error": "that statement has not been audited"}
        audit = self.apply_rulings(Audit(**kept.data[statement]))
        return {
            "status": "success",
            "audit": json.loads(audit.model_dump_json()),
            "avoidable_total": str(audit.avoidable_total),
            "headline": audit.headline(),
        }
