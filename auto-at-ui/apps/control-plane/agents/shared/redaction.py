SENSITIVE_FIELD_NAMES = frozenset({"authorization", "cookie", "password", "secret", "token"})


def redact_mapping(values: dict[str, object]) -> dict[str, object]:
    """Redact common secret fields before data enters prompts or audit logs."""
    return {
        key: "[REDACTED]" if key.lower() in SENSITIVE_FIELD_NAMES else value
        for key, value in values.items()
    }
