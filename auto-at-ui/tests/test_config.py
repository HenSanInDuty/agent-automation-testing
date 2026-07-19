from config import Settings


def test_settings_reads_port_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "7001")

    assert Settings().port == 7001


def test_settings_reads_storage_and_database_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@postgres:5432/test")
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
    monkeypatch.setenv("MINIO_BUCKET", "test-artifacts")

    settings = Settings()

    assert settings.database_url == "postgresql://test:test@postgres:5432/test"
    assert settings.minio_endpoint == "minio:9000"
    assert settings.minio_bucket == "test-artifacts"
