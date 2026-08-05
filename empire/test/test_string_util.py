import pytest

from empire.server.utils.string_util import (
    get_random_string,
    is_valid_session_id,
    slugify,
)


@pytest.mark.parametrize(
    ("session_id", "expected"),
    [
        ("ABCDEFGH", True),
        ("12345678", True),
        ("ABCDEF1H", True),
        ("A1B2C3D4", True),
        ("ABCDEFG", False),
        ("ABCDEFGHI", False),
        ("ABCD_EFG", False),
        ("       ", False),
        ("", False),
        (12345678, False),
        (None, False),
        ("./../../", False),
    ],
)
def test_is_valid_session_id(session_id, expected):
    assert is_valid_session_id(session_id) == expected, (
        f"Test failed for session_id: {session_id}"
    )


def test_slugify():
    assert (
        slugify("this/has invalid_characters-in\tstring")
        == "this_has_invalid_characters_in_string"
    )


class TestGetRandomString:
    def test_default_length(self):
        s = get_random_string()
        assert 6 <= len(s) <= 15  # noqa: PLR2004

    def test_explicit_length(self):
        s = get_random_string(length=10)
        assert len(s) == 10  # noqa: PLR2004

    def test_custom_charset(self):
        s = get_random_string(length=20, charset="abc")
        assert all(c in "abc" for c in s)
