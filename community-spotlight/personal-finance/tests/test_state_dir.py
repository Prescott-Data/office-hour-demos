"""Where the desk is kept, which decides whether two front doors reach the same desk."""

from pathlib import Path

from personal_finance.state import state_dir

PROJECT = Path(__file__).resolve().parent.parent


def test_it_does_not_move_when_the_process_moves(monkeypatch, tmp_path):
    monkeypatch.delenv("PF_STATE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert state_dir() == PROJECT / ".pf-state"


def test_the_shared_desk_and_the_cli_land_on_the_same_desk(monkeypatch, tmp_path):
    monkeypatch.delenv("PF_STATE_DIR", raising=False)
    monkeypatch.chdir(PROJECT)
    from_cli = state_dir()
    monkeypatch.chdir(tmp_path)  # the Desk runs each task from its own working directory
    assert state_dir() == from_cli


def test_you_can_say_where_it_goes(monkeypatch, tmp_path):
    monkeypatch.setenv("PF_STATE_DIR", str(tmp_path / "elsewhere"))
    assert state_dir() == tmp_path / "elsewhere"
