"""The categoriser: your corrections, then what the statement states, then judgement."""

from __future__ import annotations

from jarviscore import AutoAgent

from personal_finance import categories, counterparty
from personal_finance.categories import UNCATEGORISED, Decided
from personal_finance.contracts import CategoryPolicy, LayoutProfile, Verdict
from personal_finance.corrections import Corrections
from personal_finance.desk import Desk
from personal_finance.judgements import Judgements, fingerprint

BATCH = 20


class Categoriser(AutoAgent):
    """Places a transaction in one of the categories you keep."""

    name = "Categoriser"
    role = "categoriser"
    capabilities = ["transaction_categorisation"]
    description = "Decides which of your categories a counterparty belongs in."
    system_prompt = (
        "You place spending in the categories a person keeps for their own budget. "
        "A category is right when it matches how the person would describe the purchase "
        "to themselves, using the meaning they wrote for that category. Where a counterparty "
        "could plausibly sit in more than one, the one that reflects what was actually bought "
        "is the better answer, and where the name alone carries too little to tell, saying so "
        "is worth more than a confident guess."
    )

    def __init__(
        self,
        layout: LayoutProfile,
        policy: CategoryPolicy,
        corrections: Corrections | None = None,
        judgements: Judgements | None = None,
        agent_id=None,
    ):
        super().__init__(agent_id=agent_id)
        self.layout = layout
        self.policy = policy
        self.corrections = corrections if corrections is not None else Desk().corrections()
        self.judgements = judgements if judgements is not None else Desk().judgements()
        self.spend_usd = 0.0
        self.questions_asked = 0

    def correct(self, description_or_key: str, category: str) -> str:
        """Record your answer for a counterparty, so it is never asked about again."""
        if not self.policy.allows(category):
            raise ValueError(f"{category!r} is not one of your categories")
        key = counterparty.key(description_or_key, self.layout.kinds)
        self.corrections.record(key, category)
        return key

    def settled(self, descriptions: list[str], corrections: dict[str, str] | None = None
                ) -> dict[str, Verdict]:
        """Everything answerable without judgement, keyed by counterparty."""
        verdicts: dict[str, Verdict] = {}
        for description in descriptions:
            key = counterparty.key(description, self.layout.kinds)
            if key in verdicts:
                continue
            found = categories.settle(description, self.layout, self.policy, corrections)
            if found:
                category, decided = found
                verdicts[key] = Verdict(key=key, category=category, decided_by=decided.value)
        return verdicts

    async def judge(self, keys: list[str]) -> dict[str, Verdict]:
        """Ask the decision model about counterparties the statement does not explain."""
        against = fingerprint(self.policy)
        remembered = {key: self.judgements.get(key, against) for key in keys}
        verdicts = {key: found for key, found in remembered.items() if found}
        keys = [key for key in keys if key not in verdicts]
        if not keys:
            return verdicts
        if self.decisions is None:
            raise RuntimeError(
                "no decision client: set TYPESAFE_API_KEY so the mesh attaches one"
            )

        from typesafe_sdk import Choice

        for start in range(0, len(keys), BATCH):
            batch = keys[start : start + BATCH]
            labels = {f"c{index}": key for index, key in enumerate(batch)}
            result = await self.decisions.evaluate(
                state={"counterparties": labels},
                questions={
                    label: Choice(
                        instructions=f"Which category does spending at {key!r} belong in?",
                        criteria=self.policy.categories,
                    )
                    for label, key in labels.items()
                },
            )
            self.spend_usd += float(getattr(result, "cost_usd", 0.0) or 0.0)
            self.questions_asked += len(labels)
            fresh = self._read(result.answers, labels)
            for verdict in fresh.values():
                self.judgements.put(verdict, against)
            verdicts.update(fresh)
        return verdicts

    def _read(self, answers: dict, labels: dict[str, str]) -> dict[str, Verdict]:
        verdicts = {}
        for label, answer in answers.items():
            key = labels[label]
            choice, confidence = answer.get("choice", ""), float(answer.get("confidence", 0.0))
            unsure = confidence < self.policy.confidence_threshold or not self.policy.allows(choice)
            verdicts[key] = Verdict(
                key=key,
                category=UNCATEGORISED if unsure else choice,
                decided_by=Decided.AGENT.value,
                confidence=confidence,
                needs_review=unsure,
            )
        return verdicts

    async def categorise(self, descriptions: list[str], corrections: dict[str, str] | None = None
                         ) -> dict[str, Verdict]:
        known = {**self.corrections.as_dict(), **(corrections or {})}
        verdicts = self.settled(descriptions, known)
        pending = categories.needs_judgement(descriptions, self.layout, self.policy, known)
        verdicts.update(await self.judge(pending))
        return verdicts
