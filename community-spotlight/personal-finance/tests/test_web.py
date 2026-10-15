import json

import pytest
from fastapi.testclient import TestClient

from personal_finance import web
from personal_finance.desk import Desk
from tests.fixtures import paid


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "_desk", lambda user="me": Desk("web-test", tmp_path))
    web.STATE.update(transactions=[], verdicts={}, findings=[], summary=None, name="")
    return TestClient(web.app)


def load(rows, name="statement.pdf"):
    web.STATE.update(transactions=rows, verdicts={}, findings=[], summary=None, name=name)


def test_the_page_is_served(client):
    assert client.get("/").status_code == 200


def test_the_page_can_ask_whether_the_agents_are_up(client):
    body = client.get("/api/ready").json()
    assert set(body) == {"ready", "starting", "failed"}
    assert body["ready"] is False  # they start on first use, not on boot


def test_a_new_category_can_be_made_and_used_in_one_step(client):
    load([paid("BODA GUY", 200, 1)])
    client.post("/api/categories/add", json={"name": "transport", "meaning": "Fares and rides."})
    client.post("/api/move", json={"keys": ["BODA GUY"], "category": "transport"})
    body = client.get("/api/categories").json()
    transport = next(c for c in body["categories"] if c["name"] == "transport")
    assert [t["key"] for t in transport["transactions"]] == ["BODA GUY"]


def test_a_statement_that_is_not_a_pdf_is_refused(client):
    answer = client.post(
        "/api/statement",
        files={"statement": ("not.pdf", b"nonsense", "application/pdf")},
        data={"password": ""},
    )
    assert answer.status_code == 400
    assert "error" in answer.json()


def test_transactions_appear_under_a_category(client):
    load([paid("CORNER CO", 900, 1)])
    body = client.get("/api/categories").json()
    unplaced = next(c for c in body["categories"] if c["name"] == "uncategorised")
    assert unplaced["transactions"][0]["description"].endswith("CORNER CO")
    assert "groceries" in body["names"]


def test_moving_a_transaction_keeps_it_there(client, tmp_path):
    load([paid("CORNER CO", 900, 1), paid("CORNER CO", 100, 2)])
    moved = client.post("/api/move", json={"keys": ["CORNER CO"], "category": "groceries"})
    assert moved.status_code == 200

    body = client.get("/api/categories").json()
    groceries = next(c for c in body["categories"] if c["name"] == "groceries")
    assert len(groceries["transactions"]) == 2  # both payments followed the counterparty
    assert all(t["corrected"] for t in groceries["transactions"])
    assert "CORNER CO" in Desk("web-test", tmp_path).corrections()


def test_a_category_you_do_not_keep_is_refused(client):
    load([paid("CORNER CO", 900, 1)])
    refused = client.post("/api/move", json={"keys": ["CORNER CO"], "category": "holidays"})
    assert refused.status_code == 400


def test_categorising_without_a_statement_says_so(client):
    assert client.post("/api/categorise").status_code == 400


def test_analysing_before_categorising_says_so(client):
    load([paid("CORNER CO", 900, 1)])
    assert client.post("/api/analyse").status_code == 400


def test_several_unrelated_transactions_move_together(client):
    load([paid("CORNER CO", 900, 1), paid("CITY POWER PREPAID", 500, 2)])
    client.post("/api/move",
                json={"keys": ["CORNER CO", "CITY POWER PREPAID"], "category": "household"})
    body = client.get("/api/categories").json()
    household = next(c for c in body["categories"] if c["name"] == "household")
    assert {t["key"] for t in household["transactions"]} == {"CORNER CO", "CITY POWER PREPAID"}


def test_a_category_of_your_own_can_be_added(client):
    load([paid("CORNER CO", 900, 1)])
    added = client.post("/api/categories/add", json={"name": "Church Giving", "meaning": "Tithes."})
    assert added.json()["added"] == "church_giving"
    assert "church_giving" in client.get("/api/categories").json()["names"]


def test_a_category_that_already_exists_is_refused(client):
    load([paid("CORNER CO", 900, 1)])
    assert client.post(
        "/api/categories/add", json={"name": "groceries", "meaning": "Food."}
    ).status_code == 400


def test_merging_moves_what_sat_in_the_old_category(client):
    load([paid("CORNER CO", 900, 1)])
    client.post("/api/categories/add", json={"name": "food", "meaning": "Anything edible."})
    client.post("/api/move", json={"keys": ["CORNER CO"], "category": "groceries"})
    merged = client.post("/api/categories/merge", json={"source": "groceries", "target": "food"})
    assert merged.status_code == 200
    body = client.get("/api/categories").json()
    assert "groceries" not in body["names"]
    food = next(c for c in body["categories"] if c["name"] == "food")
    assert [t["key"] for t in food["transactions"]] == ["CORNER CO"]


def test_a_move_marks_the_findings_stale(client):
    load([paid("CORNER CO", 900, 1)])
    web.STATE["findings"] = [{"kind": "repeat", "headline": "something", "evidence": []}]
    client.post("/api/move", json={"keys": ["CORNER CO"], "category": "groceries"})
    assert client.get("/api/findings").json()["stale"] is True


def test_findings_are_empty_until_the_desk_runs(client):
    load([paid("CORNER CO", 900, 1)])
    body = client.get("/api/findings").json()
    assert body["findings"] == [] and body["summary"] is None


def test_the_sheets_behind_the_watchdog_are_visible(client):
    load([paid("CORNER CO", 900, 1), paid("CORNER CO", 100, 2)])
    sheets = client.get("/api/sheets").json()["sheets"]
    assert sheets[0]["key"] == "CORNER CO" and sheets[0]["payments"] == 2


def test_an_audit_not_yet_worked_out_says_so(client):
    load([paid("CORNER CO", 900, 1)])
    assert client.get("/api/audit").json()["worked_out"] is False


def test_the_audit_panel_reads_what_was_already_worked_out(client, tmp_path):
    from personal_finance.agents.auditor import Audit, Line
    from personal_finance.desk import Desk

    rows = [paid("CORNER CO", 900, 1)]
    load(rows)
    desk = Desk("web-test", tmp_path)
    kept = desk.audits()
    audit = Audit(
        lines=[Line(what="charges", amount="30", avoidable=True, says="fees"),
               Line(what="the shop", amount="900", avoidable=False, says="you bought things")],
        caveat="Not all spending is waste.", spent="930",
    )
    from personal_finance.agents.auditor import Auditor

    kept.data[Auditor.fingerprint(rows)] = json.loads(audit.model_dump_json())
    kept.save()

    body = client.get("/api/audit").json()
    assert body["worked_out"] and body["avoidable"] == "30"
    assert body["unruled"] == 2 and len(body["lines"]) == 2


def test_ruling_a_line_changes_the_total_and_sticks(client, tmp_path):
    from personal_finance.agents.auditor import Audit, Auditor, Line
    from personal_finance.desk import Desk

    rows = [paid("CORNER CO", 900, 1)]
    load(rows)
    kept = Desk("web-test", tmp_path).audits()
    kept.data[Auditor.fingerprint(rows)] = json.loads(
        Audit(lines=[Line(what="charges", amount="30", avoidable=True, says="fees")],
              spent="930").model_dump_json()
    )
    kept.save()

    body = client.post("/api/audit/rule", json={"what": "charges", "avoidable": False}).json()
    assert body["avoidable"] == "0"
    assert body["lines"][0]["your_call"] is True
    assert client.get("/api/audit").json()["unruled"] == 0  # your word is kept
