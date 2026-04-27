"""
スタートアップハンドラー

アプリケーション起動時の処理を管理します
"""

import asyncio
import logging
import os
import random

# FunyaWatcher を無効化する環境フラグ
DISABLE_FUNYA_WATCHER = os.getenv("DISABLE_FUNYA_WATCHER", "0").lower() in (
    "1",
    "true",
    "yes",
)

# 画面 Watcher を無効化する環境フラグ
DISABLE_SCREEN_WATCHER = os.getenv("DISABLE_SCREEN_WATCHER", "0").lower() in (
    "1",
    "true",
    "yes",
)

# Companion (Vision LLM) を無効化する環境フラグ
DISABLE_COMPANION = os.getenv("DISABLE_COMPANION", "0").lower() in (
    "1",
    "true",
    "yes",
)

# ロガーの設定
logger = logging.getLogger(__name__)

# グローバル変数
_startup_complete = False

# funya モード突入時に喋るセリフ候補 (Step 4 で speech_bus 経由に統合)
FUNYA_MESSAGES = [
    "……ふにゃ？ だいじょうぶ？",
    "ひとやすみ、しよっか",
    "わたし、そばにいるよ",
    "……しーん。そばにいるよ",
    "おつかれさま……",
]


def _make_funya_callback(loop, bus, settings):
    """funya モード突入時に speech_bus へ投入する callback を組み立てる.

    funya_watcher は別スレッドで動くので、asyncio.Queue への投入は
    run_coroutine_threadsafe 経由で event loop に戻す必要がある.
    """
    from ..services.speech_bus import SpeechRequest

    def callback() -> None:
        try:
            text = random.choice(FUNYA_MESSAGES)
            request = SpeechRequest(
                text=text,
                source="funya",
                emotion="やさしい",
            )
            asyncio.run_coroutine_threadsafe(bus.put(request), loop)
            logger.info(f"funya enqueue: '{text}'")
        except Exception as e:
            logger.error(
                f"funya callback で speech_bus 投入失敗: "
                f"{type(e).__name__}: {e}"
            )

    return callback


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
    from ..services.speech_bus import SpeechRequest, get_speech_bus
    from ..services.speech_consumer import SpeechConsumer
    from ..services.speech_consumer_state import (
        get_speech_consumer_state_service,
    )
    from ..services.voice import get_voice_service

    try:
        # 設定の読み込み
        settings = get_settings()
        logger.info("設定を読み込みました")

        # VOICEVOXエンジンの起動（非同期）
        start_voicevox_in_thread()
        logger.info("VOICEVOXエンジンの起動処理を開始しました")

        # 音声サービスの初期化
        _ = get_voice_service()
        logger.info("音声サービスを初期化しました")

        # SpeechConsumer (Step 4) — 発話の単一コンシューマ.
        # subscribers (companion / funya / boot) が enqueue する側より先に立てる
        try:
            bus = get_speech_bus()
            consumer = SpeechConsumer(bus=bus, settings=settings)
            get_speech_consumer_state_service().set_service(consumer)
            await consumer.start()
            logger.info("SpeechConsumer を初期化して開始しました")
        except Exception as e:
            logger.error(f"SpeechConsumer の初期化中にエラー: {e}")

        # ふにゃ見守りモードの初期化と開始
        if DISABLE_FUNYA_WATCHER:
            logger.info("FunyaWatcher is disabled in this environment.")
        else:
            try:
                # FunyaWatcher のインポートは必要な場合にのみ行う
                from ..modules.funya_watcher import FunyaWatcher

                # 別スレッドの funya watcher から speech_bus に投入する callback
                running_loop = asyncio.get_running_loop()
                funya_callback = _make_funya_callback(
                    running_loop, get_speech_bus(), settings
                )

                # ふにゃ見守りモードの初期化
                funya_watcher = FunyaWatcher(
                    inactivity_threshold=30,  # 30秒の無操作でふにゃモード発動
                    on_enter_funya_mode=funya_callback,
                )

                # ふにゃ状態サービスにインスタンスを設定
                funya_service = get_funya_state_service()
                funya_service.set_watcher(funya_watcher)

                # 見守りを開始
                funya_watcher.start()
                logger.info("ふにゃ見守りモードを初期化して開始しました")
            except Exception as e:
                logger.error(f"ふにゃ見守りモードの初期化中にエラーが発生: {e}")

        # 画面 Watcher の初期化と開始
        if DISABLE_SCREEN_WATCHER:
            logger.info("WatcherService is disabled in this environment.")
        else:
            try:
                from ..modules.watcher import WatcherService
                from ..services.watcher_state import get_watcher_state_service

                watcher_service = WatcherService(get_settings())
                get_watcher_state_service().set_service(watcher_service)
                await watcher_service.start()
                logger.info("WatcherService を初期化して開始しました")
            except Exception as e:
                # funya と同方針: watcher の失敗で全体起動を止めない
                logger.error(f"WatcherService の初期化中にエラー: {e}")

        # Companion (Step 3) の初期化と開始 (watcher の後)
        if DISABLE_COMPANION or not settings.COMPANION_ENABLED:
            logger.info("CompanionService is disabled in this environment.")
        else:
            try:
                from ..modules.companion import Companion, CompanionService
                from ..services.companion_state import (
                    get_companion_state_service,
                )
                from ..services.watcher_state import get_watcher_state_service

                watcher_ref = get_watcher_state_service().get_service()
                if watcher_ref is None:
                    logger.warning(
                        "CompanionService 起動スキップ: WatcherService が未起動"
                    )
                else:
                    companion = Companion(
                        model=settings.COMPANION_MODEL,
                        base_url=settings.COMPANION_BASE_URL,
                        api_key=settings.COMPANION_API_KEY,
                        max_tokens=settings.COMPANION_MAX_TOKENS,
                        temperature=settings.COMPANION_TEMPERATURE,
                        timeout_sec=settings.COMPANION_TIMEOUT_SEC,
                        jpeg_quality=settings.COMPANION_JPEG_QUALITY,
                    )
                    await companion.load(
                        warmup=settings.COMPANION_WARMUP_ON_LOAD
                    )
                    companion_service = CompanionService(
                        companion=companion,
                        watcher=watcher_ref,
                        settings=settings,
                    )
                    get_companion_state_service().set_service(companion_service)
                    await companion_service.start()
                    logger.info("CompanionService を初期化して開始しました")
            except Exception as e:
                # watcher と同方針: companion の失敗で全体起動を止めない
                logger.error(f"CompanionService の初期化中にエラー: {e}")

        # 起動時ダミー発話 (Step 4). consumer 側で VOICEVOX ready 待ちが入る
        greeting = settings.SPEECH_BOOT_GREETING.strip()
        if greeting:
            try:
                bus = get_speech_bus()
                await bus.put(
                    SpeechRequest(
                        text=greeting,
                        source="boot",
                        emotion="通常",
                        bypass_rate_limit=True,
                        message_type="speech_boot",
                    )
                )
                logger.info(f"起動時あいさつを enqueue: '{greeting}'")
            except Exception as e:
                logger.warning(f"起動時あいさつの enqueue に失敗: {e}")

        # WebSocketマネージャーの初期化は自動的に行われます
        logger.info("各種サービスの初期化が完了しました")

    except Exception as e:
        logger.error(f"サービスの初期化中にエラーが発生: {e}")
        raise
