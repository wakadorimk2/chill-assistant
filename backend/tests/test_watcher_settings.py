"""Settings の WATCHER_* デフォルト値と env 上書きを検証"""

import pytest
from app.config.settings import Settings


def test_watcher_settings_defaults() -> None:
    s = Settings()
    assert s.WATCHER_SCREEN_DIFF_THRESHOLD == 12.0
    assert s.WATCHER_ACTIVE_INTERVAL_SEC == 3.0
    assert s.WATCHER_IDLE_INTERVAL_SEC == 10.0
    assert s.WATCHER_FUNYA_INTERVAL_SEC == 30.0
    assert s.WATCHER_WINDOW_POLL_INTERVAL_SEC == 2.0
    assert s.WATCHER_QUEUE_MAX_SIZE == 64
    assert s.WATCHER_DIFF_RESIZE_W == 240
    assert s.WATCHER_DIFF_RESIZE_H == 135


def test_watcher_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCHER_SCREEN_DIFF_THRESHOLD", "20.5")
    monkeypatch.setenv("WATCHER_ACTIVE_INTERVAL_SEC", "5.0")
    monkeypatch.setenv("WATCHER_QUEUE_MAX_SIZE", "128")
    s = Settings()
    assert s.WATCHER_SCREEN_DIFF_THRESHOLD == 20.5
    assert s.WATCHER_ACTIVE_INTERVAL_SEC == 5.0
    assert s.WATCHER_QUEUE_MAX_SIZE == 128
