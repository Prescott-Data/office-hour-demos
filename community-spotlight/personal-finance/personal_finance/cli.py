"""The desk from a terminal. Everything here runs on your machine."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from personal_finance import counterparty, facts, layouts, owner, review
from personal_finance.agents.auditor import Auditor
from personal_finance.agents.categoriser import Categoriser
from personal_finance.agents.proposer import Proposer
from personal_finance.agents.watchdog import Watchdog
from personal_finance.desk import DEFAULT_USER, Desk
from personal_finance.sources.pdf import read_pages, read_words
from personal_finance.sources.table import extract
from personal_finance.verify import check_balances


def _load(path: str, desk: Desk):
    layout = layouts.load("mpesa-statement")
    policy = desk.categories().policy()
    rows = extract(read_words(path), layout, source=Path(path).stem)
    _claim_owner(path, layout, desk, rows)
    return rows, layout, policy


def _claim_owner(path: str, layout, desk: Desk, rows) -> None:
    """Whoever the statement says it belongs to is not a counterparty of their own."""
    who = owner.named_in(read_pages(path), layout.owner_label)
    if not who:
        return
    notes = desk.notes()
    for key in {counterparty.key(r.description, layout.kinds) for r in rows}:
        if owner.is_the_owner(key, who) and not notes.mine(key):
            notes.claim(key)
            print(f"({key} is you, so it is no longer counted as spending)")


def _agent(layout, policy, desk: Desk) -> Categoriser:
    from jarviscore.execution.decisions import create_decision_client

    agent = Categoriser(
        layout, policy, corrections=desk.corrections(), judgements=desk.judgements()
    )
    # None without TYPESAFE_API_KEY, which still leaves corrections and the stated kinds working
    agent.decisions = create_decision_client({})
    return agent


def read(args) -> None:
    rows, _, _ = _load(args.statement, Desk(args.user))
    verdict = check_balances(rows)
    print(f"{len(rows)} transactions read from {Path(args.statement).name}")
    print(verdict.summary())
    if not verdict.ok:
        print(f"{len(verdict.breaks)} rows do not follow from the balance before them")


def categorise(args) -> None:
    desk = Desk(args.user)
    rows, layout, policy = _load(args.statement, desk)
    agent = _agent(layout, policy, desk)
    verdicts = asyncio.run(agent.categorise([r.description for r in rows]))
    placed = Counter()
    for row in rows:
        found = verdicts.get(counterparty.key(row.description, layout.kinds))
        placed[found.category if found else "unplaced"] += 1
    for category, count in placed.most_common():
        print(f"  {category:<22}{count}")
    held = sum(1 for v in verdicts.values() if v.needs_review)
    print(f"\nasked {agent.questions_asked} question(s), cost ${agent.spend_usd:.6f}")
    if held:
        print(f"{held} counterparties need you: run 'pf review {args.statement}'")


def review_cmd(args) -> None:
    desk = Desk(args.user)
    rows, layout, policy = _load(args.statement, desk)
    agent = _agent(layout, policy, desk)
    verdicts = asyncio.run(agent.categorise([r.description for r in rows]))
    items = review.pending(rows, verdicts, layout)
    if not items:
        print("nothing waiting on you")
        return

    names = list(policy.categories)
    print(f"{len(items)} counterparties to settle. Enter to skip, q to stop.\n")
    for position, item in enumerate(items, start=1):
        print(f"[{position}/{len(items)}] {item.headline()}")
        if item.confidence is not None:
            print(f"    best guess: {item.suggested} (confidence {item.confidence:.2f})")
        for example in item.examples:
            print(f"    {example}")
        for index, name in enumerate(names, start=1):
            print(f"    {index:>2}. {name}")
        answer = input("  category number: ").strip()
        if answer.lower() == "q":
            break
        if not answer.isdigit() or not 1 <= int(answer) <= len(names):
            print("  skipped\n")
            continue
        chosen = names[int(answer) - 1]
        agent.correct(item.key, chosen)
        print(f"  {item.key} is {chosen}, and will not be asked again\n")


def watch(args) -> None:
    desk = Desk(args.user)
    rows, layout, policy = _load(args.statement, desk)
    notes = desk.notes()
    if args.sheets:
        for sheet in facts.sheets(rows, layout, notes=notes):
            print(f"  {sheet.key}: {sheet.payments} payments, {sheet.paid_out} out, "
                  f"usual {sheet.usual}, every {sheet.every_days} days, "
                  f"{len(sheet.same_day_pairs)} same-day pair(s)")
        return
    verdicts = asyncio.run(_agent(layout, policy, desk).categorise([r.description for r in rows]))
    agent = Watchdog(layout)
    for finding in asyncio.run(agent.review(rows, verdicts, notes)):
        print(f"  [{finding.kind}] {finding.headline}")
        for line in finding.evidence:
            print(f"      {line}")
    print(f"\nread {agent.sheets_read} sheet(s), cost ${agent.spend_usd:.6f}")


def propose(args) -> None:
    desk = Desk(args.user)
    rows, layout, _policy = _load(args.statement, desk)
    agent = Proposer(layout, user=desk.user)
    proposed = asyncio.run(agent.propose(rows, notes=desk.notes()))
    if not proposed:
        print("nothing proposed")
        return

    print(f"{len(proposed)} categories proposed, from {len(rows)} transactions.")
    print(f"cost ${agent.spend_usd:.6f}\n")
    kept: dict[str, str] = {}
    placements: list[tuple[str, str]] = []
    for position, category in enumerate(proposed, start=1):
        places = list(category.places)
        while True:
            print(f"[{position}/{len(proposed)}] {category.name}: {category.meaning}")
            print(f"    {category.payments} payments, {category.spent} in total")
            for index, place in enumerate(places, start=1):
                print(f"    {index:>3}. {place}")
            print("    Enter to keep · r <name> rename · 2 5 or d 2 5 to drop those · s skip")
            answer = input("  > ").strip()
            if answer.lower() == "s":
                print("  skipped\n")
                places = []
                break
            if answer.lower().startswith("d ") or answer.replace(" ", "").isdigit():
                wanted = answer.split()[1:] if answer.lower().startswith("d ") else answer.split()
                dropping = {int(n) for n in wanted if n.isdigit()}
                places = [p for i, p in enumerate(places, start=1) if i not in dropping]
                print(f"  dropped {len(dropping)}, {len(places)} left\n")
                continue
            if answer.lower().startswith("r "):
                category.name = answer[2:].strip().replace(" ", "_").lower()
                print(f"  renamed to {category.name}\n")
                continue
            if answer:
                print("  say r to rename, d to drop, s to skip, or Enter to keep\n")
                continue
            break
        if not places:
            continue
        kept[category.name] = category.meaning
        placements += [(place, category.name) for place in places]
        print(f"  kept {category.name} with {len(places)} places\n")

    if not kept:
        print("nothing kept, your categories are unchanged")
        return
    catalogue = desk.categories()
    catalogue.replace(kept)
    catalogue.approve()
    corrections = desk.corrections()
    for place, name in placements:
        corrections.record(place, name)
    print(f"{len(kept)} categories saved, {len(placements)} places placed in them")


def categories_cmd(args) -> None:
    catalogue = Desk(args.user).categories()
    if args.action == "list":
        for name, meaning in catalogue.policy().categories.items():
            print(f"  {name}: {meaning}")
        print(f"\napproved: {catalogue.approved}")
    elif args.action == "rename":
        print("renamed" if catalogue.rename(args.first, args.second) else "no such category")
    elif args.action == "remove":
        print("removed" if catalogue.remove(args.first) else "no such category")


def forget(args) -> None:
    desk = Desk(args.user)
    layout = layouts.load("mpesa-statement")
    key = counterparty.key(args.counterparty, layout.kinds)
    if desk.corrections().forget(key):
        print(f"{key} is unplaced, and will be judged again")
    else:
        print(f"{key} was not placed by you")


def audit(args) -> None:
    desk = Desk(args.user)
    rows, layout, _policy = _load(args.statement, desk)
    agent = Auditor(layout, desk=desk)
    found = asyncio.run(agent.audit(rows, notes=desk.notes(), fresh=args.fresh))
    print(f"{found.headline()}, of {found.spent} that left\n")
    for index, line in enumerate(found.lines, start=1):
        mark = "avoidable" if line.avoidable else "cost, not waste"
        whose = "your call" if line.your_call else "the desk's view"
        print(f"  {index:>2}. [{mark}] {line.what}: {line.amount}  ({whose})")
        print(f"      {line.says}")
    if found.caveat:
        print(f"\n{found.caveat}")
    if agent.spend_usd:
        print(f"cost ${agent.spend_usd:.6f}")
    if not args.rule:
        waiting = len(found.unruled())
        if waiting:
            print(f"\n{waiting} line(s) still carry the desk's view. "
                  f"Run with --rule to settle them.")
        return

    rulings = desk.rulings()
    print("\nFor each line: y if it was avoidable, n if it was simply spending, "
          "Enter to leave it.\n")
    for line in found.lines:
        answer = input(f"  {line.what} ({line.amount}) avoidable? ").strip().lower()
        if answer in {"y", "yes"}:
            rulings.record(line.what, True)
        elif answer in {"n", "no"}:
            rulings.record(line.what, False)
    settled = agent.apply_rulings(found, rulings)
    print(f"\n{settled.headline()}")


def dismiss(args) -> None:
    desk = Desk(args.user)
    layout = layouts.load("mpesa-statement")
    key = counterparty.key(args.counterparty, layout.kinds)
    desk.notes().dismiss(key, args.topic)
    print(f"{key}: {args.topic} is normal, and will not be raised again")


def mine(args) -> None:
    desk = Desk(args.user)
    layout = layouts.load("mpesa-statement")
    notes = desk.notes()
    if not args.counterparty:
        for key in notes.mine_keys():
            print(f"  {key}")
        return
    key = counterparty.key(args.counterparty, layout.kinds)
    notes.claim(key)
    print(f"{key} is yours, so money moved there no longer counts as spending")


def set_cmd(args) -> None:
    desk = Desk(args.user)
    layout, policy = layouts.load("mpesa-statement"), desk.categories().policy()
    agent = Categoriser(
        layout, policy, corrections=desk.corrections(), judgements=desk.judgements()
    )
    key = agent.correct(args.counterparty, args.category)
    print(f"{key} is {args.category}")


def main() -> None:
    load_dotenv(".env")
    parser = argparse.ArgumentParser(prog="pf", description="A private money desk.")
    parser.add_argument("--user", default=DEFAULT_USER, help="whose desk to use")
    commands = parser.add_subparsers(dest="command", required=True)

    for name, handler, helptext in (
        ("read", read, "read a statement and check it reconciles"),
        ("categorise", categorise, "categorise a statement"),
        ("review", review_cmd, "settle the counterparties the desk could not"),
        ("watch", watch, "report what in a statement deserves attention"),
        ("propose", propose, "suggest the categories that fit your spending"),
        ("audit", audit, "what the period cost that need not have"),
    ):
        sub = commands.add_parser(name, help=helptext)
        sub.add_argument("statement", help="path to a statement PDF")
        if name == "audit":
            sub.add_argument("--rule", action="store_true", help="settle each line yourself")
            sub.add_argument("--fresh", action="store_true", help="work it out again")
        if name == "watch":
            sub.add_argument(
                "--sheets", action="store_true", help="show the figures without asking a model"
            )
        sub.set_defaults(handler=handler)

    cats = commands.add_parser("categories", help="list, rename or remove your categories")
    cats.add_argument("action", choices=["list", "rename", "remove"])
    cats.add_argument("first", nargs="?")
    cats.add_argument("second", nargs="?")
    cats.set_defaults(handler=categories_cmd)

    drop = commands.add_parser("forget", help="undo a category you set for a counterparty")
    drop.add_argument("counterparty")
    drop.set_defaults(handler=forget)

    quiet = commands.add_parser("dismiss", help="say a pattern is normal for a counterparty")
    quiet.add_argument("counterparty")
    quiet.add_argument("topic", help="for example same_day_pairs, rhythm, amounts")
    quiet.set_defaults(handler=dismiss)

    own = commands.add_parser("mine", help="mark a counterparty as an account of your own")
    own.add_argument("counterparty", nargs="?")
    own.set_defaults(handler=mine)

    fix = commands.add_parser("set", help="record a category for a counterparty")
    fix.add_argument("counterparty")
    fix.add_argument("category")
    fix.set_defaults(handler=set_cmd)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
