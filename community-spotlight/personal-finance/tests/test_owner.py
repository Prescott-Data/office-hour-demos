from personal_finance import owner

PAGES = ["M-PESA STATEMENT\nCustomer Name:   ASHA ATIENO OCHIENG'\nMobile Number: 0712345678"]


def test_the_owner_is_read_from_the_statement():
    assert owner.named_in(PAGES, "Customer Name") == "ASHA ATIENO OCHIENG'"


def test_a_missing_label_finds_nobody():
    assert owner.named_in(PAGES, "Account Holder") == ""
    assert owner.named_in(PAGES, "") == ""


def test_a_counterparty_sharing_your_name_is_you():
    assert owner.is_the_owner("ASHA OCHIENG'", "ASHA ATIENO OCHIENG'")


def test_someone_sharing_one_name_with_you_is_not_you():
    assert not owner.is_the_owner("ASHA ACHIENG", "ASHA ATIENO OCHIENG'")


def test_nobody_is_you_when_the_statement_never_said():
    assert not owner.is_the_owner("ANYONE", "")
