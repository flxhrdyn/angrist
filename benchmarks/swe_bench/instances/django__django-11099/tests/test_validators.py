import pytest
from django.contrib.auth.validators import ASCIIUsernameValidator


def test_valid_username():
    v = ASCIIUsernameValidator()
    v("valid_user123")
    v("user.name+tag@example")


def test_trailing_newline_rejected():
    v = ASCIIUsernameValidator()
    with pytest.raises(ValueError):
        v("username\n")
