"""Companion 状態管理サービス (watcher_state.py と同じシングルトンパターン)."""

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..modules.companion import CompanionService

logger = logging.getLogger(__name__)


class CompanionStateService:
    """CompanionService インスタンスを保持し、HTTP 層から状態取得できるようにする."""

    _instance: Optional["CompanionStateService"] = None

    def __new__(cls) -> "CompanionStateService":
        if cls._instance is None:
            cls._instance = super(CompanionStateService, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        self._service: Optional["CompanionService"] = None
        logger.info("✅ Companion 状態サービスを初期化しました")

    def get_service(self) -> Optional["CompanionService"]:
        return self._service

    def set_service(self, service: "CompanionService") -> None:
        self._service = service
        logger.info("✅ CompanionService インスタンスを設定しました")

    def clear_service(self) -> None:
        self._service = None

    def get_status(self) -> dict[str, Any]:
        from ..config import get_settings

        settings = get_settings()
        base = {
            "enabled": settings.COMPANION_ENABLED,
            "model": settings.COMPANION_MODEL,
            "base_url": settings.COMPANION_BASE_URL,
            "rate_limit_sec": settings.COMPANION_RATE_LIMIT_SEC,
        }
        if self._service is None:
            return {**base, "ready": False, "last_speak_ts": None}
        return {
            **base,
            "ready": self._service.ready,
            "last_speak_ts": self._service.last_speak_ts,
        }


def get_companion_state_service() -> CompanionStateService:
    return CompanionStateService()
