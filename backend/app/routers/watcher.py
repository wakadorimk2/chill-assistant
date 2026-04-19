"""
Watcher ルーター

画面 / ウィンドウ監視サービスの状態取得 + 最新キャプチャ画像の取得 (デバッグ用) を提供。
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from ..services.watcher_state import get_watcher_state_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/watcher",
    tags=["watcher"],
    responses={404: {"description": "見つかりません"}},
)


@router.get("/status")
async def get_watcher_status() -> dict[str, Any]:
    """Watcher サービスの状態を取得"""
    try:
        return get_watcher_state_service().get_status()
    except Exception as e:
        logger.error(f"Watcher 状態取得エラー: {e}")
        raise HTTPException(
            status_code=500, detail=f"Watcher 状態の取得に失敗しました: {e}"
        ) from e


@router.get("/last-frame")
async def get_last_frame() -> Response:
    """最新キャプチャを JPEG で返す (デバッグ用)"""
    service = get_watcher_state_service().get_service()
    if service is None:
        raise HTTPException(status_code=503, detail="watcher not running")
    jpeg = service.get_latest_frame_jpeg()
    if jpeg is None:
        raise HTTPException(status_code=404, detail="no frame yet")
    return Response(content=jpeg, media_type="image/jpeg")
