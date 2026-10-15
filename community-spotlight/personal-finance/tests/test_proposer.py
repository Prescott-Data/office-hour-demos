import json
from decimal import Decimal

import pytest

from personal_finance import layouts
from personal_finance.agents.proposer import Proposer
from personal_finance.contracts import Transaction
from personal_finance.notes import Notes
from tests.fixtures import START, paid

LAYOUT = layouts.load("mpesa-statement")


class StubLLM:
    def __init__(self, payload):
        self.payload, self.seen = payload, []

    async def generate(self, *, messages, temperature=0.4, response_format=None):
        self.seen.append(messages[-1]["content"])
        return {"content": json.dumps(self.payload), "cost_usd": 0.0004}


def sent_to(person, amount, day):
    return Transaction(
        reference=f"P{day}{int(amount)}", timestamp=START.replace(day=day + 1),
        description=f"Customer Transfer to 2547***678 - {person}", status="Completed",
        withdrawn=Decimal(str(amount)), balance=Decimal("500"), source="fixture")


def rows():
    return [paid("CORNER CO", 900, 1), paid("CORNER CO", 1100, 2), sent_to("NELLY ACHIENG", 500, 3)]


def build(payload):
    agent = Proposer(LAYOUT)
    agent.llm = StubLLM(payload)
    return agent


def test_a_business_keeps_its_name_and_a_person_does_not():
    agent = Proposer(LAYOUT)
    places = {p["place"] for p in agent.places(rows(), notes=Notes("/dev/null"))}
    assert "CORNER CO" in places
    assert "NELLY ACHIENG" not in places
    assert any(place.startswith("person ") for place in places)


@pytest.mark.asyncio
async def test_the_person_behind_a_label_comes_back_locally():
    agent = build({"categories": [
        {"name": "friends_and_family", "meaning": "People I help out.", "places": ["person 1"]}]})
    proposed = await agent.propose(rows(), notes=Notes("/dev/null"))
    assert proposed[0].places == ["NELLY ACHIENG"]
    assert proposed[0].spent == Decimal("500")


@pytest.mark.asyncio
async def test_a_category_holding_a_place_that_was_never_offered_drops_it():
    agent = build({"categories": [
        {"name": "groceries", "meaning": "Food.", "places": ["CORNER CO", "INVENTED SHOP"]}]})
    proposed = await agent.propose(rows(), notes=Notes("/dev/null"))
    assert proposed[0].places == ["CORNER CO"]
    assert proposed[0].payments == 2


@pytest.mark.asyncio
async def test_categories_come_back_heaviest_first():
    agent = build({"categories": [
        {"name": "friends_and_family", "meaning": "People.", "places": ["person 1"]},
        {"name": "groceries", "meaning": "Food.", "places": ["CORNER CO"]}]})
    assert [c.name for c in await agent.propose(rows(), notes=Notes("/dev/null"))] == [
        "groceries", "friends_and_family"]


@pytest.mark.asyncio
async def test_uncategorised_cannot_be_proposed():
    agent = build({"categories": [
        {"name": "uncategorised", "meaning": "Anything.", "places": ["CORNER CO"]}]})
    assert await agent.propose(rows(), notes=Notes("/dev/null")) == []


@pytest.mark.asyncio
async def test_an_unreadable_answer_proposes_nothing():
    agent = Proposer(LAYOUT)

    class Broken:
        async def generate(self, *, messages, temperature=0.4, response_format=None):
            return {"content": "no", "cost_usd": 0.0}

    agent.llm = Broken()
    assert await agent.propose(rows(), notes=Notes("/dev/null")) == []
