"""
シャットダウンハンドラー

アプリケーション終了時の処理を管理します
"""

import asyncio
import logging

# ロガーの設定
logger = logging.getLogger(__name__)

# グローバル変数
_shutdown_complete = False


async def on_shutdown() -> None:
    """
    アプリケーション終了時のハンドラー

    終了時に必要なクリーンアップ処理を実行します
    """
    global _shutdown_complete

    if _shutdown_complete:
        logger.info("シャットダウン処理は既に完了しています")
        return

    try:
        # クリーンアップ処理
        await cleanup_resources()

        _shutdown_complete = True
        logger.info("シャットダウン処理が完了しました")

    except Exception as e:
        logger.error(f"シャットダウン処理中にエラーが発生: {e}")


async def cleanup_resources() -> None:
    """
    リソースのクリーンアップ処理
    """
    try:
        # 一時ファイルの削除など、必要に応じてクリーンアップ処理を実装

        # 画面 Watcher の停止 (一括 gather より前に個別停止して race を回避)
        try:
            from ..services.watcher_state import get_watcher_state_service

            watcher_service = get_watcher_state_service().get_service()
            if watcher_service is not None:
                await watcher_service.stop()
                logger.info("WatcherService を停止しました")
        except Exception as e:
            logger.warning(f"WatcherService 停止中にエラー: {e}")

        # WebSocketの接続クローズ
        try:
            from ..ws.manager import manager

            # マネージャーインスタンスから接続を取得してクローズ
            for connection in manager.active_connections.copy():
                manager.disconnect(connection)
            logger.info("WebSocket接続をクローズしました")
        except (ImportError, Exception) as e:
            logger.warning(f"WebSocket接続クローズ中にエラーが発生: {e}")

        # 非同期タスクの完了を待機
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            logger.info(f"{len(tasks)}個の非同期タスクの完了を待機しています...")
            await asyncio.gather(*tasks, return_exceptions=True)

    except Exception as e:
        logger.error(f"リソースのクリーンアップ中にエラーが発生: {e}")
        # クリーンアップ処理は致命的でないので例外は再スローしない
