"""Speech ルーター — speech_bus / consumer の状態取得 (Step 4)."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from ..services.speech_consumer_state import get_speech_consumer_state_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/speech",
    tags=["speech"],
    responses={404: {"description": "見つかりません"}},
)


@router.get("/status")
async def get_speech_status() -> dict[str, Any]:
    """SpeechConsumer の状態 (queue size, spoken/dropped カウント等)."""
    try:
        return get_speech_consumer_state_service().get_status()
    except Exception as e:
        logger.error(f"speech 状態取得エラー: {e}")
        raise HTTPException(
            status_code=500, detail=f"speech 状態の取得に失敗しました: {e}"
        ) from e
