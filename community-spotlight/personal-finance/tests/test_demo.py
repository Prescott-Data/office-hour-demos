"""The demo is the only thing a stranger can run, so it is pinned like anything else."""

from personal_finance import layouts
from personal_finance.demo import main
from personal_finance.demo.statement import STORY, words
from personal_finance.notes import Notes
from personal_finance.probes import Toolbox
from personal_finance.sources.table import extract
from personal_finance.verify import check_balances

PROFILE = layouts.load("mpesa-statement")


def rows():
    return extract(words(), PROFILE, source="demo")


def test_every_invented_transaction_is_read():
    assert len(rows()) == len(STORY)


def test_the_invented_statement_proves_itself():
    verdict = check_balances(rows())
    assert verdict.ok, verdict.summary()
    assert verdict.checked == len(STORY) - 1


def test_descriptions_survive_their_column():
    found = {row.description for row in rows()}
    assert any("MAMA NGINA GROCERS" in text for text in found)
    assert any("DAUDI THE LANDLORD" in text for text in found)


def test_the_double_payment_is_there_to_be_found():
    toolbox = Toolbox(rows(), PROFILE, Notes("/dev/null"))
    repeats = toolbox.run("repeats", within_hours=0.25)
    assert repeats["found"], "the demo should hold one thing worth catching"


def test_it_runs_with_no_keys_and_no_statement(capsys, monkeypatch):
    monkeypatch.delenv("AZURE_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    main()
    assert "reconcile" in capsys.readouterr().out
