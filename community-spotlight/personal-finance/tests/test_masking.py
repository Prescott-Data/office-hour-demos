from personal_finance.masking import Masker


def test_the_same_place_keeps_the_same_label():
    masker = Masker()
    assert masker.label("HILLSIDE") == masker.label("HILLSIDE") != masker.label("CORNER CO")


def test_places_inside_a_probe_answer_are_hidden():
    masker = Masker()
    hidden = masker.hide({"found": [{"place": "ASHA MWANGI", "paid_out": "6940"}]})
    assert hidden["found"][0]["place"] == "counterparty 1"
    assert hidden["found"][0]["paid_out"] == "6940"  # figures are left alone


def test_the_name_comes_back():
    masker = Masker()
    masker.label("BRIAN OTIENO")
    assert masker.reveal("counterparty 1 took 200") == "BRIAN OTIENO took 200"


def test_a_low_label_leaves_a_higher_one_alone():
    """With 91 counterparties, label 5 must not corrupt every mention of 50-59."""
    masker = Masker()
    for number in range(1, 60):
        masker.label(f"PLACE {number}")
    assert masker.labels["PLACE 5"] == "counterparty 5"
    assert masker.labels["PLACE 55"] == "counterparty 55"
    assert masker.reveal("counterparty 55 is overdue") == "PLACE 55 is overdue"
    assert masker.reveal("counterparty 5 is overdue") == "PLACE 5 is overdue"


def test_a_name_with_a_backslash_survives_being_put_back():
    masker = Masker()
    masker.label(r"A\1 SHOP")
    assert masker.reveal("counterparty 1 rose") == r"A\1 SHOP rose"
