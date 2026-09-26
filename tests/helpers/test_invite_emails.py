from app.helpers.invites import collect_invite_email_errors, normalized_invite_emails

INVALID_EMAIL = "Enter a valid email address."


def test_normalized_invite_emails_skips_blanks_and_duplicates():
    assert normalized_invite_emails(None) == []
    assert normalized_invite_emails(["", "  "]) == []
    assert normalized_invite_emails(
        [" other@example.com ", "OTHER@example.com", "new@example.com"]
    ) == ["other@example.com", "new@example.com"]


def test_collect_invite_email_errors_accepts_empty_list():
    assert collect_invite_email_errors([], owner_email="elisa@example.com") == []
    assert collect_invite_email_errors(["", "  "], owner_email="elisa@example.com") == []


def test_collect_invite_email_errors_rejects_invalid_and_self():
    errors = collect_invite_email_errors(
        ["not-an-email", "elisa@example.com"],
        owner_email="Elisa@example.com",
    )
    assert INVALID_EMAIL in errors
    assert "You cannot invite yourself." in errors


def test_collect_invite_email_errors_rejects_duplicates():
    errors = collect_invite_email_errors(
        ["a@example.com", "A@example.com"],
        owner_email="elisa@example.com",
    )
    assert errors == ["Remove duplicate email addresses."]
