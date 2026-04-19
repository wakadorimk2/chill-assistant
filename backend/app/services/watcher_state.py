"""
Watcher 状態管理サービス

WatcherService インスタンスを保持し、HTTP 層から状態取得できるようにする。
funya_state.py と同じシングルトンパターン。
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..modules.watcher import WatcherService

logger = logging.getLogger(__name__)


class WatcherStateService:
    """Watcher 状態管理サービス (シングルトン)"""

    _instance: Optional["WatcherStateService"] = None

    def __new__(cls) -> "WatcherStateService":
        if cls._instance is None:
            cls._instance = super(WatcherStateService, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        self._service: Optional["WatcherService"] = None
        logger.info("✅ Watcher 状態サービスを初期化しました")

    def get_service(self) -> Optional["WatcherService"]:
        return self._service

    def set_service(self, service: "WatcherService") -> None:
        self._service = service
        logger.info("✅ WatcherService インスタンスを設定しました")

    def get_status(self) -> dict[str, Any]:
        if self._service is None:
            return {
                "running": False,
                "initialized": False,
            }
        return self._service.get_status()


def get_watcher_state_service() -> WatcherStateService:
    return WatcherStateService()
