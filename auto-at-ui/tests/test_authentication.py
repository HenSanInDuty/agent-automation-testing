import pytest
from application.authentication import PasswordPolicyError, PasswordService, digest


def test_argon2_password_hash_never_contains_password_and_verifies() -> None:
    service = PasswordService()
    password = "A-valid-password-123"

    password_hash = service.hash(password)

    assert password not in password_hash
    assert password_hash.startswith("$argon2id$")
    assert service.verify(password_hash, password)
    assert not service.verify(password_hash, "wrong-password")


@pytest.mark.parametrize("password", ["short", "alllowercase123", "ALLUPPERCASE123"])
def test_password_policy_requires_length_and_character_classes(password: str) -> None:
    with pytest.raises(PasswordPolicyError):
        PasswordService().hash(password)


def test_session_token_digest_is_stable_and_not_the_token() -> None:
    token = "opaque-session-token"
    assert digest(token) == digest(token)
    assert digest(token) != token
