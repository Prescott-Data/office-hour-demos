"""A run anyone can do from a fresh clone, with no statement of their own and no keys."""

from __future__ import annotations

from personal_finance import counterparty, facts, layouts, profiles
from personal_finance.demo.statement import words
from personal_finance.notes import Notes
from personal_finance.probes import Toolbox
from personal_finance.sources.table import extract
from personal_finance.verify import check_balances

LAYOUT = "mpesa-statement"


def main() -> None:
    layout = layouts.load(LAYOUT)
    transactions = extract(words(), layout, source="demo-statement")
    verdict = check_balances(transactions)

    print(f"Read {len(transactions)} transactions from a statement that never existed.")
    print(f"  {verdict.summary()}\n")

    policy = profiles.categories()
    placed: dict[str, list] = {}
    for transaction in transactions:
        kind = counterparty.kind(transaction.description, layout.kinds)
        where = policy.by_kind.get(kind, "needs the categoriser")
        placed.setdefault(where, []).append(transaction)
    print("What the statement explains by itself:")
    for where, rows in sorted(placed.items(), key=lambda item: -len(item[1])):
        print(f"  {where:<28}{len(rows):>3} transactions")

    toolbox = Toolbox(transactions, layout, Notes("/dev/null"))
    print("\nWhat the probes say, with no model involved:")
    for name, takes in (
        ("spending", {}), ("borrowing", {}), ("repeats", {"within_hours": 0.25}),
        ("recurring", {"least_payments": 2}),
    ):
        print(f"  {name}: {toolbox.run(name, **takes)}")

    print(
        "\nEverything above is arithmetic. Categorising, the watchdog and the auditor need a "
        "model, so set AZURE_API_KEY and TYPESAFE_API_KEY and run `pf propose <statement.pdf>`."
    )
    print(f"Spending in the period, own accounts left out: {facts.spending(toolbox.sheets)}")
