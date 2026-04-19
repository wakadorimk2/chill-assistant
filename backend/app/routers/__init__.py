"""
ルーターモジュールパッケージ
"""

from .funya import router as funya_router
from .health import router as health_router
from .ocr_router import router as ocr_router
from .voice import router as voice_router
from .watcher import router as watcher_router
from .websocket import router as websocket_router

__all__ = [
    "health_router",
    "voice_router",
    "websocket_router",
    "ocr_router",
    "funya_router",
    "watcher_router",
]
