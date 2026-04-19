"""WatcherEvent.to_payload() の出力 JSON シェイプを検証"""

from app.modules.watcher.events import WatcherEvent, WatcherEventKind


def test_to_payload_screen_diff() -> None:
    event = WatcherEvent(
        kind=WatcherEventKind.SCREEN_DIFF,
        score=18.5,
        window_title="Visual Studio Code",
        ts=1700000000.0,
        extra={"state": "animating"},
    )
    payload = event.to_payload()

    assert payload == {
        "kind": "screen_diff",
        "score": 18.5,
        "window_title": "Visual Studio Code",
        "ts": 1700000000.0,
        "extra": {"state": "animating"},
    }


def test_to_payload_window_changed_with_none_title() -> None:
    event = WatcherEvent(
        kind=WatcherEventKind.WINDOW_CHANGED,
        score=1.0,
        window_title=None,
        ts=1700000001.0,
    )
    payload = event.to_payload()

    assert payload["kind"] == "window_changed"
    assert payload["window_title"] is None
    assert payload["extra"] == {}


def test_event_kind_values() -> None:
    assert WatcherEventKind.WINDOW_CHANGED.value == "window_changed"
    assert WatcherEventKind.SCREEN_DIFF.value == "screen_diff"
    assert WatcherEventKind.USER_IDLE.value == "user_idle"
