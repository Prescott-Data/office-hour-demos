"""pf.desk.yaml is read by the shared Desk, so what it may say is pinned here."""

from pathlib import Path

import yaml

from personal_finance import team

CONFIG = Path(__file__).resolve().parent.parent / "pf.desk.yaml"
SHAPES = {"circle", "rounded", "diamond", "hexagon"}  # what the Desk knows how to draw


def config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_the_factory_and_handler_are_importable_references():
    for reference in (config()["factory"], config()["mesh_handler"]):
        module, _, symbol = reference.partition(":")
        assert module == "personal_finance.team"
        assert callable(getattr(team, symbol))


def test_every_appearance_names_a_role_the_factory_builds():
    roles = {agent.role for agent in team.build_mesh().agents}
    assert set(config()["agents"]) <= roles, "the Desk refuses an appearance with no agent"


def test_every_agent_in_the_mesh_has_an_appearance():
    roles = {agent.role for agent in team.build_mesh().agents}
    assert roles == set(config()["agents"]), "an agent with no appearance gets a random colour"


def test_shapes_and_ids_are_ones_the_desk_accepts():
    for role, appearance in config()["agents"].items():
        assert appearance["shape"] in SHAPES, f"{role} asks for a shape the Desk cannot draw"
        assert appearance["id"].islower() and appearance["id"][0].isalpha()
        assert set(appearance["id"]) <= set("abcdefghijklmnopqrstuvwxyz0123456789-")
        assert appearance["color"].startswith("#") and len(appearance["color"]) == 7
