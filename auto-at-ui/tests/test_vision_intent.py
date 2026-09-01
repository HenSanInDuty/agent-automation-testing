from datetime import UTC, datetime, timedelta

import pytest
from agents.vision.intent import (
    VisualIntentUnavailableError,
    decrypt_visual_intent,
    encrypt_visual_intent,
)
from cryptography.fernet import Fernet


def test_visual_intent_is_encrypted_and_only_available_before_retention_expiry() -> None:
    key = Fernet.generate_key().decode("ascii")
    encrypted = encrypt_visual_intent("Open the sign-in dialog", key)

    assert encrypted != "Open the sign-in dialog"
    assert decrypt_visual_intent(encrypted, key, datetime.now(UTC) + timedelta(days=60)) == (
        "Open the sign-in dialog"
    )
    with pytest.raises(VisualIntentUnavailableError):
        decrypt_visual_intent(encrypted, key, datetime.now(UTC) - timedelta(seconds=1))


def test_visual_intent_requires_a_valid_configured_key() -> None:
    with pytest.raises(VisualIntentUnavailableError):
        encrypt_visual_intent("x", None)
