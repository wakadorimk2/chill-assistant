"""Speech ルーター — speech_bus / consumer の状態取得 + 外部 enqueue (Step 4)."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.speech_bus import SpeechRequest, get_speech_bus
from ..services.speech_consumer_state import get_speech_consumer_state_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/speech",
    tags=["speech"],
    responses={404: {"description": "見つかりません"}},
)


class SpeechEnqueueRequest(BaseModel):
    """frontend からの発話要求 (pawButton / random_speak など)."""

    text: str = Field(..., min_length=1, description="発話テキスト")
    emotion: str = Field("通常", description="VOICE_PRESETS のキー")
    source: str = Field("frontend", description="呼び出し元タグ (rate limit 用)")
    bypass_rate_limit: bool = Field(False, description="True で rate limit 無視")


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


@router.post("/enqueue")
async def enqueue_speech(req: SpeechEnqueueRequest) -> dict[str, Any]:
    """frontend からの発話要求を SpeechBus に投入する.

    旧 `/api/voice/synthesize` の代替. 実際の合成・再生は SpeechConsumer 側.
    """
    bus = get_speech_bus()
    request = SpeechRequest(
        text=req.text,
        source=req.source,
        emotion=req.emotion,
        bypass_rate_limit=req.bypass_rate_limit,
        message_type=f"speech_{req.source}",
    )
    queued = await bus.put(request)
    if not queued:
        logger.warning(
            f"speech enqueue: queue full source={req.source} "
            f"text='{req.text[:20]}...'"
        )
    return {"queued": queued, "queue_size": bus.qsize, "source": req.source}
