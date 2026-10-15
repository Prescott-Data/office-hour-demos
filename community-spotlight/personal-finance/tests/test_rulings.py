from personal_finance.rulings import Rulings, label


def test_the_same_line_worded_differently_is_one_ruling():
    assert label("Transaction charges") == label("transaction  charges!") == "transaction_charges"


def test_a_ruling_survives_a_restart(tmp_path):
    Rulings(tmp_path / "r.json").record("charges", False)
    assert Rulings(tmp_path / "r.json").says("Charges") is False


def test_nothing_is_said_about_a_line_you_have_not_ruled_on(tmp_path):
    assert Rulings(tmp_path / "r.json").says("anything") is None


def test_a_ruling_can_be_taken_back(tmp_path):
    rulings = Rulings(tmp_path / "r.json")
    rulings.record("borrowing", True)
    assert rulings.forget("borrowing") and rulings.says("borrowing") is None
    assert not rulings.forget("borrowing")
