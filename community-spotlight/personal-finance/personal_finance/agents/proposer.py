"""The proposer: reads where the money actually goes and names the categories for it."""

from __future__ import annotations

import json
from decimal import Decimal

from jarviscore import AutoAgent
from pydantic import BaseModel, Field

from personal_finance import facts, layouts, profiles
from personal_finance.contracts import LayoutProfile, Transaction, Verdict
from personal_finance.desk import DEFAULT_USER, Desk
from personal_finance.notes import Notes

LAYOUT_NAME = "mpesa-statement"
MOST_PLACES = 60
RESERVED = "uncategorised"

# people are masked; businesses are named, because the name is the whole signal for a category
PEOPLE = {"send_money", "received"}

CONTRACT = """
Answer with JSON only, in this shape:

{"categories": [{"name": "<lower_case_with_underscores>",
                 "meaning": "<one sentence a person would recognise as their own>",
                 "places": ["<the label of each place that belongs here>"]}]}

Use between 5 and 12 categories, put every place given into exactly one of them, and draw the
names from what this person actually spends on, in the words they would use.
"""


class ProposedCategory(BaseModel):
    """One category the desk suggests, with what it would hold."""

    name: str
    meaning: str
    places: list[str] = Field(default_factory=list)
    spent: Decimal = Decimal(0)
    payments: int = 0


class Proposer(AutoAgent):
    """Suggests the categories that fit one person's spending."""

    name = "Proposer"
    role = "proposer"
    capabilities = ["category_proposal"]
    description = "Reads a statement and proposes the categories that fit it."
    system_prompt = (
        "You name the categories a person would use for their own money, by looking at where "
        "it actually went. A good set reflects this person's own life: "
        "it separates what they would want to see apart, keeps together what they would think of "
        "as one thing, and uses words they would say out loud. Places identified only by a label "
        "are people they sent money to, and the amounts, the frequency and what else they spend "
        "on say more about those than a name would."
    )

    def __init__(
        self, layout: LayoutProfile | None = None, user: str = DEFAULT_USER, agent_id=None
    ):
        super().__init__(agent_id=agent_id)
        self.desk = Desk(user)
        self.layout = layout if layout is not None else layouts.load(LAYOUT_NAME)
        self.spend_usd = 0.0
        self._aliases: dict[str, str] = {}
        self._names: dict[str, str] = {}

    def label(self, key: str, kinds: list[str]) -> str:
        """A business keeps its name; a person becomes a label."""
        if not set(kinds) & PEOPLE:
            self._names[key] = key
            return key
        if key not in self._aliases:
            alias = f"person {len(self._aliases) + 1}"
            self._aliases[key] = alias
            self._names[alias] = key
        return self._aliases[key]

    def places(
        self,
        transactions: list[Transaction],
        verdicts: dict[str, Verdict] | None = None,
        notes: Notes | None = None,
    ) -> list[dict]:
        """Where the money went, as little as the proposer needs to name a category."""
        # what the statement explains is fixed by the issuer, not by the categories you keep
        stated = set(profiles.categories().by_kind)
        sheets = [
            s
            for s in facts.sheets(transactions, self.layout, verdicts, notes)
            if s.payments and not s.mine and not set(s.kinds) <= stated
        ]
        return [
            {
                "place": self.label(sheet.key, sheet.kinds),
                "spent": sheet.paid_out,
                "payments": sheet.payments,
                "usual": sheet.usual,
                "how_paid": sheet.kinds,
            }
            for sheet in sheets[:MOST_PLACES]
        ]

    async def propose(
        self,
        transactions: list[Transaction],
        verdicts: dict[str, Verdict] | None = None,
        notes: Notes | None = None,
    ) -> list[ProposedCategory]:
        places = self.places(transactions, verdicts, notes)
        if not places:
            return []
        if not hasattr(self, "llm") or self.llm is None:
            from jarviscore.config import settings
            from jarviscore.execution.llm import UnifiedLLMClient

            self.llm = UnifiedLLMClient(settings.model_dump())

        answer = await self.llm.generate(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": json.dumps({"places": places}, default=str) + "\n" + CONTRACT,
                },
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        self.spend_usd += float(answer.get("cost_usd", 0.0) or 0.0)
        return self._read(answer.get("content", ""), {p["place"]: p for p in places})

    def _read(self, content: str, by_place: dict[str, dict]) -> list[ProposedCategory]:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return []

        proposed = []
        for entry in payload.get("categories", []):
            name = str(entry.get("name", "")).strip().lower().replace(" ", "_")
            if not name or name == RESERVED:
                continue
            # a proposal may only hold places that were actually offered to it
            members = [str(p) for p in entry.get("places", []) if str(p) in by_place]
            proposed.append(
                ProposedCategory(
                    name=name,
                    meaning=str(entry.get("meaning", "")).strip(),
                    places=[self._names.get(place, place) for place in members],
                    spent=sum((by_place[p]["spent"] for p in members), Decimal(0)),
                    payments=sum(by_place[p]["payments"] for p in members),
                )
            )
        return sorted(proposed, key=lambda c: c.spent, reverse=True)
