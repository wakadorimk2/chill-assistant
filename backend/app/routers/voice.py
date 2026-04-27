"""音声ルーター — VOICEVOX 接続確認のみ.

旧 `/api/voice/synthesize`, `/speak`, `/speak_with_preset`, `/synthesize-play`,
`/analyze`, `/speaker` は SpeechBus への一本化に伴い 2026-04-27 に削除。
発話投入は `POST /api/speech/enqueue` を使う。
"""

import logging

import requests
from fastapi import APIRouter

from ..config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()
settings = get_settings()


@router.get("/api/voice/check-connection")
async def check_voicevox_connection() -> dict:
    """VOICEVOXとの接続状態を確認するエンドポイント"""
    try:
        host = settings.VOICEVOX_HOST
        response = requests.get(f"{host}/version", timeout=2)

        if response.status_code == 200:
            version = response.text
            logger.info(f"VOICEVOX接続確認: バージョン {version}")
            return {"connected": True, "version": version}
        else:
            logger.warning(f"VOICEVOX接続失敗: ステータス {response.status_code}")
            return {"connected": False, "error": f"ステータス {response.status_code}"}

    except Exception as e:
        logger.error(f"VOICEVOX接続確認エラー: {str(e)}")
        return {"connected": False, "error": str(e)}
