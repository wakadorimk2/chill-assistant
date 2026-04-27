"""Companion ルーター — debug-speak と status."""

import logging
from typing import Any, Optional

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..services.companion_state import get_companion_state_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/companion",
    tags=["companion"],
    responses={404: {"description": "見つかりません"}},
)


@router.get("/status")
async def get_companion_status() -> dict[str, Any]:
    """Companion サービスの状態を取得."""
    try:
        return get_companion_state_service().get_status()
    except Exception as e:
        logger.error(f"Companion 状態取得エラー: {e}")
        raise HTTPException(
            status_code=500, detail=f"Companion 状態の取得に失敗しました: {e}"
        ) from e


@router.post("/debug-speak")
async def debug_speak(
    image: UploadFile = File(...),
    user_context: Optional[str] = Form(None),
    speak_voice: bool = Form(True),
) -> dict[str, Any]:
    """アップロード画像を LLM に投げて 1 回発話する (rate limit バイパス).

    curl 例:
        curl -X POST http://127.0.0.1:8001/api/companion/debug-speak \\
             -F "image=@test.png" -F "user_context=テスト画像"
    """
    service = get_companion_state_service().get_service()
    if service is None:
        raise HTTPException(status_code=503, detail="companion not running")

    try:
        blob = await image.read()
        if not blob:
            raise HTTPException(status_code=400, detail="empty image payload")
        arr = np.frombuffer(blob, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise HTTPException(status_code=400, detail="image decode failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"image load failed: {e}"
        ) from e

    text, latency, queued = await service.generate_once(
        frame,
        user_context or "この画面について一言お願い。",
        speak_voice=speak_voice,
    )
    return {"text": text, "latency_sec": latency, "queued": queued}
