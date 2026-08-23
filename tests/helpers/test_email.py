from app.helpers.email import collect_email_errors

INVALID_EMAIL = "Enter a valid email address."


def test_valid_emails_have_no_errors():
    assert collect_email_errors("a@b.c") == []
    assert collect_email_errors("user@example.com") == []
    assert collect_email_errors("user.name+tag@example.co.uk") == []
    assert collect_email_errors("a" * 88 + "@b.co") == []


def test_email_rejects_empty_and_malformed():
    assert collect_email_errors("") == [INVALID_EMAIL]
    assert collect_email_errors("not-an-email") == [INVALID_EMAIL]
    assert collect_email_errors("user@") == [INVALID_EMAIL]
    assert collect_email_errors("@example.com") == [INVALID_EMAIL]
    assert collect_email_errors("user@example") == [INVALID_EMAIL]
    assert collect_email_errors("user example.com") == [INVALID_EMAIL]
    assert collect_email_errors("user@exa mple.com") == [INVALID_EMAIL]


def test_email_rejects_addresses_over_100_characters():
    too_long = "a" * 89 + "@example.com"
    assert len(too_long) == 101
    assert collect_email_errors(too_long) == [INVALID_EMAIL]


def test_email_accepts_addresses_at_100_characters():
    at_limit = "a" * 88 + "@example.com"
    assert len(at_limit) == 100
    assert collect_email_errors(at_limit) == []
