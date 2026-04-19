"""
アプリケーション生成モジュール

FastAPI アプリケーションの生成と初期化を行う。
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..config import get_settings
from .logger import setup_logger

logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan コンテキストマネージャ (startup / shutdown)"""
    from ..events import shutdown_handler, startup_handler

    logger.info("🚀 アプリケーションを起動しています...")
    await startup_handler.on_startup()
    logger.info("✅ アプリケーションの起動が完了しました")

    try:
        yield
    finally:
        logger.info("🔌 アプリケーションをシャットダウンしています...")
        await shutdown_handler.on_shutdown()
        logger.info("✅ アプリケーションのシャットダウンが完了しました")


def create_application() -> FastAPI:
    """
    FastAPI アプリケーションを作成して初期化

    Returns:
        FastAPI: 初期化された FastAPI インスタンス
    """
    settings = get_settings()

    app = FastAPI(
        title="秘書たん API",
        description="ローカル Vision LLM と連携する秘書たんシステム API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    try:
        for mount_path, directory in [
            ("/static", settings.STATIC_DIR),
            ("/temp", settings.TEMP_DIR),
            ("/shared", settings.SHARED_DIR),
        ]:
            dir_path = Path(directory)
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"📁 静的ファイルディレクトリを作成: {directory}")

            app.mount(
                mount_path, StaticFiles(directory=directory), name=mount_path.strip("/")
            )
            logger.info(f"🔗 静的ファイルをマウント: {mount_path} -> {directory}")

    except Exception as e:
        logger.error(f"❌ 静的ファイルのマウント中にエラー: {e}")

    register_routers(app)

    return app


def register_routers(app: FastAPI) -> None:
    """ルーターを登録"""
    try:
        from ..routers import (
            funya_router,
            health_router,
            ocr_router,
            voice_router,
            watcher_router,
            websocket_router,
        )

        app.include_router(health_router)
        app.include_router(ocr_router)
        app.include_router(voice_router)
        app.include_router(websocket_router)
        app.include_router(funya_router)
        app.include_router(watcher_router)

        logger.info("🔄 ルーターを登録しました")

    except Exception as e:
        logger.error(f"❌ ルーターの登録中にエラー: {e}")
