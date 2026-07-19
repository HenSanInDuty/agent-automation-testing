from config import Settings


def test_settings_reads_port_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "7001")

    assert Settings().port == 7001
