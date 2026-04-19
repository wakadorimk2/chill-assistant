"""
スタートアップハンドラー

アプリケーション起動時の処理を管理します
"""

import asyncio
import logging
import os

# FunyaWatcher を無効化する環境フラグ
DISABLE_FUNYA_WATCHER = os.getenv("DISABLE_FUNYA_WATCHER", "0").lower() in (
    "1",
    "true",
    "yes",
)

# ロガーの設定
logger = logging.getLogger(__name__)

# グローバル変数
_startup_complete = False


async def on_startup() -> None:
    """
    アプリケーション起動時のハンドラー

    起動時に必要な初期化処理を実行します
    """
    global _startup_complete

    if _startup_complete:
        logger.info("スタートアップ処理は既に完了しています")
        return

    try:
        # 各種サービスの初期化
        await init_services()

        _startup_complete = True
        logger.info("スタートアップ処理が完了しました")

    except Exception as e:
        logger.error(f"スタートアップ処理中にエラーが発生: {e}")
        raise


async def init_services() -> None:
    """
    各種サービスの初期化
    """
    from ..config import get_settings
    from ..modules.voice.voicevox_starter import start_voicevox_in_thread
    from ..services.funya_state import get_funya_state_service
    from ..services.voice import get_voice_service

    try:
        # 設定の読み込み
        _ = get_settings()
        logger.info("設定を読み込みました")

        # VOICEVOXエンジンの起動（非同期）
        start_voicevox_in_thread()
        logger.info("VOICEVOXエンジンの起動処理を開始しました")

        # 音声サービスの初期化
        _ = get_voice_service()
        logger.info("音声サービスを初期化しました")

        # ふにゃ見守りモードの初期化と開始
        if DISABLE_FUNYA_WATCHER:
            logger.info("FunyaWatcher is disabled in this environment.")
        else:
            try:
                # FunyaWatcher のインポートは必要な場合にのみ行う
                from ..modules.funya_watcher import FunyaWatcher

                # ふにゃ見守りモードの初期化
                funya_watcher = FunyaWatcher(
                    inactivity_threshold=30,  # 30秒の無操作でふにゃモード発動
                )

                # ふにゃ状態サービスにインスタンスを設定
                funya_service = get_funya_state_service()
                funya_service.set_watcher(funya_watcher)

                # 見守りを開始
                funya_watcher.start()
                logger.info("ふにゃ見守りモードを初期化して開始しました")
            except Exception as e:
                logger.error(f"ふにゃ見守りモードの初期化中にエラーが発生: {e}")

        # WebSocketマネージャーの初期化は自動的に行われます
        logger.info("各種サービスの初期化が完了しました")

    except Exception as e:
        logger.error(f"サービスの初期化中にエラーが発生: {e}")
        raise
