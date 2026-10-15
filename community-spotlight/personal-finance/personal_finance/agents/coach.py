"""The coach: says where the money went, in the words a person would use."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from decimal import Decimal

from jarviscore import AutoAgent
from pydantic import BaseModel, Field

from personal_finance import facts
from personal_finance.agents.auditor import Auditor
from personal_finance.contracts import Finding, LayoutProfile, Transaction, Verdict
from personal_finance.notes import Notes

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# the shape of the answer lives in the task, which is where the kernel actually passes it on
CONTRACT = """
Answer with JSON only, in this shape:

{"headline": "<one sentence saying how the period went>",
 "paragraphs": ["<two to four short paragraphs>"],
 "worth_knowing": ["<up to three short lines, each about one thing they could act on>"]}

Every number you write appears in the figures above. Where a figure is missing, the shape of
the month is still worth describing in words.
"""


class Summary(BaseModel):
    """What the coach says, and the figures it was given to say it from."""

    headline: str = ""
    paragraphs: list[str] = Field(default_factory=list)
    worth_knowing: list[str] = Field(default_factory=list)
    spent: Decimal = Decimal(0)
    received: Decimal = Decimal(0)
    transactions: int = 0

    def text(self) -> str:
        lines = [self.headline, ""]
        lines += [paragraph + "\n" for paragraph in self.paragraphs]
        if self.worth_knowing:
            lines.append("Worth knowing:")
            lines += [f"  - {line}" for line in self.worth_knowing]
        return "\n".join(lines).strip()


class Coach(AutoAgent):
    """Explains a period's spending to the person who lived it."""

    name = "Coach"
    role = "coach"
    capabilities = ["spending_summary"]
    description = "Writes the plain account of where the money went."
    system_prompt = (
        "You explain someone's own month back to them. They already know what they bought, so "
        "a summary earns its place by naming the shape that was hidden from them: what took "
        "the most, what changed against the month before, what a total adds up to across small "
        "payments. Write the way a careful friend would speak, in whole sentences, using their "
        "figures and their own category names. Money moved between their own accounts counts as "
        "moving rather than spending. Where the figures leave a claim open, the shape of the "
        "month is still worth describing in words."
    )

    def __init__(self, layout: LayoutProfile, agent_id=None):
        super().__init__(agent_id=agent_id)
        self.layout = layout
        self.spend_usd = 0.0

    def figures(
        self,
        transactions: list[Transaction],
        verdicts: dict[str, Verdict] | None = None,
        notes: Notes | None = None,
    ) -> dict:
        """Totals by category and by month, with your own accounts left out."""
        sheets = [s for s in facts.sheets(transactions, self.layout, verdicts, notes) if not s.mine]
        spent = facts.spending(sheets)

        by_category: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
        counts: dict[str, int] = defaultdict(int)
        by_month: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: defaultdict(lambda: Decimal(0))
        )
        for sheet in sheets:
            by_category[sheet.category] += sheet.paid_out
            counts[sheet.category] += sheet.payments
            for month, total in sheet.by_month.items():
                by_month[month][sheet.category] += total

        categories = [
            {
                "category": category,
                "spent": total,
                "payments": counts[category],
                "share": (total / spent * 100).quantize(Decimal("0.1")) if spent else Decimal(0),
            }
            for category, total in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
        ]
        return {
            "period": {
                "from": min((s.first_seen for s in sheets), default=""),
                "to": max((s.last_seen for s in sheets), default=""),
            },
            "spent": spent,
            "received": sum((s.paid_in for s in sheets), Decimal(0)),
            "transactions": sum(s.payments + s.receipts for s in sheets),
            "by_category": categories,
            "by_month": {month: dict(totals) for month, totals in sorted(by_month.items())},
            "places_paid": len(sheets),
        }

    async def ask_the_auditor(self, transactions: list[Transaction]) -> dict | None:
        """Ask whichever peer does avoidable cost, rather than working it out again."""
        peers = getattr(self, "peers", None)
        if peers is None:
            return None
        reply = await peers.request(
            "auditor",
            {
                "task": "what in this statement was avoidable",
                "capability": "avoidable_cost",
                "statement": Auditor.fingerprint(transactions),
            },
            timeout=30,
        )
        if not reply or reply.get("status") != "success":
            return None
        return {
            "avoidable_total": reply.get("avoidable_total"),
            "lines": [
                {"what": line["what"], "amount": line["amount"], "avoidable": line["avoidable"]}
                for line in reply.get("audit", {}).get("lines", [])
            ],
        }

    async def summarise(
        self,
        transactions: list[Transaction],
        verdicts: dict[str, Verdict] | None = None,
        notes: Notes | None = None,
        findings: list[Finding] | None = None,
    ) -> Summary:
        figures = self.figures(transactions, verdicts, notes)
        agreed = await self.ask_the_auditor(transactions)
        if agreed:
            figures["avoidable"] = agreed
        if not hasattr(self, "llm") or self.llm is None:
            from jarviscore.config import settings
            from jarviscore.execution.llm import UnifiedLLMClient

            self.llm = UnifiedLLMClient(settings.model_dump())

        payload = {"figures": figures}
        if findings:
            payload["already_flagged"] = [f.headline for f in findings]

        answer = await self.llm.generate(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": json.dumps(payload, default=str) + "\n" + CONTRACT},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        self.spend_usd += float(answer.get("cost_usd", 0.0) or 0.0)
        return self._read(answer.get("content", ""), figures)

    def _read(self, content: str, figures: dict) -> Summary:
        summary = Summary(
            spent=figures["spent"],
            received=figures["received"],
            transactions=figures["transactions"],
        )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return summary

        stated = self._stated(figures)
        summary.headline = self._kept(str(payload.get("headline", "")), stated)
        summary.paragraphs = [
            line
            for line in (self._kept(str(p), stated) for p in payload.get("paragraphs", []))
            if line
        ]
        summary.worth_knowing = [
            line
            for line in (self._kept(str(p), stated) for p in payload.get("worth_knowing", []))
            if line
        ]
        return summary

    @staticmethod
    def _stated(figures: dict) -> set[str]:
        return {
            match.group(0).replace(",", "").rstrip("0").rstrip(".")
            for match in NUMBER.finditer(json.dumps(figures, default=str))
        }

    @staticmethod
    def _kept(sentence: str, stated: set[str]) -> str:
        """A sentence survives only when every figure in it was given."""
        for match in NUMBER.finditer(sentence):
            quoted = match.group(0).replace(",", "").rstrip("0").rstrip(".")
            if quoted not in stated:
                return ""
        return sentence.strip()
