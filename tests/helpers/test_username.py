from app.helpers.username import collect_username_errors

LENGTH_ERROR = "Username must be between 3 and 50 characters."
CHARSET_ERROR = "Username may contain only letters, numbers, and underscores."


def test_valid_usernames_have_no_errors():
    assert collect_username_errors("abc") == []
    assert collect_username_errors("user_name") == []
    assert collect_username_errors("User123") == []
    assert collect_username_errors("a" * 50) == []


def test_username_too_short():
    assert collect_username_errors("") == [LENGTH_ERROR]
    assert collect_username_errors("ab") == [LENGTH_ERROR]


def test_username_too_long():
    assert collect_username_errors("a" * 51) == [LENGTH_ERROR]


def test_username_rejects_invalid_characters():
    assert collect_username_errors("user name") == [CHARSET_ERROR]
    assert collect_username_errors("user-name") == [CHARSET_ERROR]
    assert collect_username_errors("user.name") == [CHARSET_ERROR]
    assert collect_username_errors("user@name") == [CHARSET_ERROR]


def test_username_length_error_takes_precedence_over_charset():
    assert collect_username_errors("a!") == [LENGTH_ERROR]
    assert collect_username_errors("!" * 51) == [LENGTH_ERROR]
