"""SpeechConsumer 状態管理サービス (watcher_state / companion_state と同パターン)."""

import logging
from typing import Any, Optional

from .speech_consumer import SpeechConsumer

logger = logging.getLogger(__name__)


class SpeechConsumerStateService:
    """SpeechConsumer インスタンスを保持し、HTTP 層から状態取得できるようにする."""

    _instance: Optional["SpeechConsumerStateService"] = None

    def __new__(cls) -> "SpeechConsumerStateService":
        if cls._instance is None:
            cls._instance = super(SpeechConsumerStateService, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        self._service: Optional[SpeechConsumer] = None
        logger.info("✅ SpeechConsumer 状態サービスを初期化しました")

    def get_service(self) -> Optional[SpeechConsumer]:
        return self._service

    def set_service(self, service: SpeechConsumer) -> None:
        self._service = service
        logger.info("✅ SpeechConsumer インスタンスを設定しました")

    def clear_service(self) -> None:
        self._service = None

    def get_status(self) -> dict[str, Any]:
        if self._service is None:
            return {"running": False, "initialized": False}
        return {"initialized": True, **self._service.get_status()}


def get_speech_consumer_state_service() -> SpeechConsumerStateService:
    return SpeechConsumerStateService()
