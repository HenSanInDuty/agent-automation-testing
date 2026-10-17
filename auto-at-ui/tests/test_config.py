from config import Settings


def test_settings_reads_port_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "7001")

    assert Settings().port == 7001


def test_settings_reads_storage_and_database_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@postgres:5432/test")
    monkeypatch.setenv("RUSTFS_ENDPOINT", "http://rustfs:9000")
    monkeypatch.setenv("RUSTFS_BUCKET", "test-artifacts")

    settings = Settings()

    assert settings.database_url == "postgresql://test:test@postgres:5432/test"
    assert settings.rustfs_endpoint == "http://rustfs:9000"
    assert settings.rustfs_bucket == "test-artifacts"


def test_settings_accepts_standard_google_application_credentials_environment(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/run/secrets/google-service.json")

    assert Settings().google_drive_service_account_file == "/run/secrets/google-service.json"


def test_settings_accepts_standard_google_oauth_environment(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "refresh-token")

    settings = Settings()

    assert settings.google_drive_oauth_client_id == "client-id"
    assert settings.google_drive_oauth_client_secret == "client-secret"
    assert settings.google_drive_oauth_refresh_token == "refresh-token"


def test_gemini_key_is_optional_and_excluded_from_repr_and_serialization(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert Settings(_env_file=None).gemini_api_key is None
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-gemini-secret")
    monkeypatch.setenv("VISION_RAW_SCREENSHOT_TRANSFER_PROVIDER", "gemini")
    settings = Settings(_env_file=None)
    assert settings.gemini_api_key == "synthetic-gemini-secret"
    assert settings.vision_raw_screenshot_transfer_provider == "gemini"
    assert "synthetic-gemini-secret" not in repr(settings)
    assert "gemini_api_key" not in settings.model_dump()
