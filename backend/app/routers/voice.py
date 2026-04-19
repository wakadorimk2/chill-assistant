"""
音声合成ルーター

VOICEVOX連携の音声合成および再生に関するエンドポイント
"""

import logging
import traceback

import requests
from fastapi import APIRouter, Query, Request, Response
from starlette.responses import JSONResponse

from ..config import get_settings
from ..modules.voice.engine import speak_with_emotion, synthesize_direct
from ..schemas import VoiceSynthesisRequest

# ロガー設定
logger = logging.getLogger(__name__)

# ルーター作成
router = APIRouter()

# 設定の取得
settings = get_settings()


@router.post("/api/voice/speaker")
async def change_voice_speaker(
    speaker_id: int = Query(3, description="話者ID"),
) -> dict:
    """
    VOICEVOX話者を変更するエンドポイント

    Args:
        speaker_id: VOICEVOX話者ID
    """
    try:
        logger.info(f"VOICEVOXの話者を変更します: ID={speaker_id}")

        # Config を更新
        settings.VOICEVOX_SPEAKER = speaker_id

        # 成功レスポンス
        return {
            "status": "success",
            "message": f"話者を変更しました (ID: {speaker_id})",
            "speaker_id": speaker_id,
        }
    except Exception as e:
        logger.error(f"話者変更エラー: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"話者変更に失敗しました: {str(e)}"},
        )


@router.post("/api/voice/synthesize", response_model=None)
async def synthesize_voice(request: VoiceSynthesisRequest):
    """
    テキストを音声に変換して返すエンドポイント（ファイル保存・再生なし）
    VOICEVOXを使用して音声合成を行い、WAVデータを直接返す

    Request Body:
        text: 音声に変換するテキスト
        emotion: 感情 (オプション)
        speaker_id: 話者ID (オプション)
    """
    try:
        text = request.text
        speaker = request.speaker_id
        emotion = request.emotion

        if not text:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "テキストが空です"},
            )

        logger.info(
            f"音声合成リクエスト: text={text[:20]}..., "
            f"speaker={speaker}, emotion={emotion}"
        )

        # 直接音声合成を実行して音声データ（bytes）を取得
        audio_data = await synthesize_direct(text, speaker, emotion)

        if not audio_data:
            logger.error("音声合成に失敗: synthesize_direct関数がNoneを返しました")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "音声合成に失敗しました"},
            )

        # 音声データをレスポンスとして返す
        logger.info(f"音声合成成功: {len(audio_data)} バイトの音声を返します")
        return Response(content=audio_data, media_type="audio/wav")

    except Exception as e:
        logger.error(f"音声合成エラー: {str(e)}")
        logger.error(f"詳細なエラー情報: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"音声合成に失敗しました: {str(e)}"},
        )


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


# 既存の再生込みのエンドポイント（互換性のために残すが、
# 新しいsynthesizeエンドポイントにリダイレクト）
@router.post("/api/voice/synthesize-play", response_model=None)
async def synthesize_and_play_voice(request: Request):
    """
    テキストを音声に変換して返すエンドポイント（互換性のために残す）
    実際の処理は /api/voice/synthesize にリダイレクト

    Request Body:
        text: 音声に変換するテキスト
        speaker: 話者ID (オプション)
        emotion: 感情 (オプション)
        speedScale: 話速 (オプション)
        pitchScale: ピッチ (オプション)
        intonationScale: イントネーション (オプション)
        volumeScale: 音量 (オプション)
    """
    try:
        data = await request.json()
        text = data.get("text", "")
        speaker = data.get("speaker", settings.VOICEVOX_SPEAKER)
        emotion = data.get("emotion", "normal")

        if not text:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "テキストが空です"},
            )

        logger.info(
            f"synthesize-playエンドポイントからsynthesizeにリダイレクト: {text[:20]}..."
        )

        # 新しいリクエストオブジェクトを作成
        synthesis_request = VoiceSynthesisRequest(
            text=text, speaker_id=speaker, emotion=emotion
        )

        # 新しいエンドポイントを呼び出す
        return await synthesize_voice(synthesis_request)

    except Exception as e:
        logger.error(f"音声合成リダイレクトエラー: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"音声合成に失敗しました: {str(e)}"},
        )


@router.post("/api/voice/analyze", response_model=None)
async def analyze_voice(request: Request):
    """
    テキストの感情を分析し、適切な音声パラメータを返すエンドポイント

    Request Body:
        text: 分析するテキスト
    """
    try:
        data = await request.json()
        text = data.get("text", "")

        if not text:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "テキストが空です"},
            )

        logger.info(f"テキスト感情分析リクエスト: {text[:20]}...")

        # 感情分析のみ実行
        _, analysis_result = speak_with_emotion(text, force=True)

        return {"status": "success", "text": text, "analysis": analysis_result}

    except Exception as e:
        logger.error(f"感情分析エラー: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"感情分析に失敗しました: {str(e)}"},
        )


@router.post("/api/voice/speak")
async def speak_text(request: VoiceSynthesisRequest):
    """
    テキストを音声合成して返すエンドポイント（/api/voice/synthesize と同じ動作）
    古い実装との互換性のために残す

    Request Body:
        text: 発話するテキスト
        emotion: 感情 (オプション)
        speaker_id: 話者ID (オプション)
    """
    logger.info(
        f"speak エンドポイントが呼び出されました（synthesize に転送）: "
        f"{request.text[:20] if request.text else ''}..."
    )
    return await synthesize_voice(request)


@router.post("/api/voice/speak_with_preset")
async def speak_with_preset_endpoint(request: Request):
    """
    プリセット感情を使用してテキストを音声合成するエンドポイント

    Request Body:
        text: 発話するテキスト
        preset_name: プリセット名
        speaker_id: 話者ID (オプション)
    """
    try:
        data = await request.json()
        text = data.get("text", "")
        preset_name = data.get("preset_name", "normal")
        speaker_id = data.get("speaker_id", settings.VOICEVOX_SPEAKER)

        if not text:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "テキストが空です"},
            )

        logger.info(
            f"プリセット音声合成リクエスト: text={text[:20]}..., "
            f"preset={preset_name}, speaker={speaker_id}"
        )

        # リクエストオブジェクトを作成して合成エンドポイントにリダイレクト
        synthesis_request = VoiceSynthesisRequest(
            text=text, speaker_id=speaker_id, emotion=preset_name
        )

        # 合成エンドポイントを呼び出す
        return await synthesize_voice(synthesis_request)

    except Exception as e:
        logger.error(f"プリセット音声合成エラー: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"プリセット音声合成に失敗しました: {str(e)}",
            },
        )
