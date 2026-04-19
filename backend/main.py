"""
メインエントリーポイント

アプリケーションの起動と初期化処理を行う
"""

import argparse
import asyncio
import os
import signal
import sys
import threading
import time
import types
from pathlib import Path
from typing import Dict, Optional, Union

# プロジェクトのルートディレクトリを取得
ROOT_DIR = Path(__file__).parent.parent.absolute()
BACKEND_DIR = Path(__file__).parent.absolute()

# Pythonのパスに追加
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

import psutil
import uvicorn
from dotenv import load_dotenv
from fastapi import Body, FastAPI

from backend.app.core import create_application
from backend.app.core.logger import setup_logger

# .env ファイルの読み込み
env_path = Path(ROOT_DIR) / ".env"
print(f"Reading .env file from: {env_path} (exists: {env_path.exists()})")
load_dotenv(env_path)

# 環境変数の値を表示（デバッグ用）
port_value = os.getenv("PORT", "未設定")
print(f"読み込まれたPORT環境変数の値: '{port_value}'")

# カスタムロガー設定
logger = setup_logger(__name__)
logger.info("🚀 秘書たんバックエンドサーバーを初期化しています...")

# 環境変数の設定（必要に応じて）
os.environ.setdefault("DEBUG_MODE", "false")
# UTF-8エンコーディングを強制
os.environ["PYTHONIOENCODING"] = "utf-8"

# アプリケーションの作成
app = create_application()

# シャットダウン用のグローバル変数
should_exit: bool = False
exit_code: int = 0


# すべての子プロセスを含めて終了する関数
def terminate_process_tree() -> None:
    """
    現在のプロセスとすべての子プロセスを強制終了します
    """
    try:
        # 自身のプロセスID
        current_pid = os.getpid()
        logger.info(f"🔄 プロセスツリーの終了を開始します (PID: {current_pid})")

        # psutilを使って自身のプロセスと子プロセスを取得
        current_process = psutil.Process(current_pid)

        # 子プロセスを取得
        children = current_process.children(recursive=True)
        logger.info(f"🔍 子プロセス数: {len(children)}")

        # 子プロセスをまず終了
        for child in children:
            try:
                logger.info(f"🛑 子プロセス終了: PID={child.pid}, 名前={child.name()}")
                child.terminate()
            except Exception as e:
                logger.error(f"❌ 子プロセス終了エラー (PID={child.pid}): {e}")

        # すべての子プロセスが終了するのを待つ（最大3秒）
        _, alive = psutil.wait_procs(children, timeout=3)

        # まだ生きているプロセスを強制終了
        for child in alive:
            try:
                logger.info(f"💥 子プロセス強制終了: PID={child.pid}")
                child.kill()
            except Exception as e:
                logger.error(f"❌ 子プロセス強制終了エラー (PID={child.pid}): {e}")

        logger.info("✅ プロセスツリーの終了処理が完了しました")
    except Exception as e:
        logger.error(f"❌ プロセスツリー終了処理エラー: {e}")


# uvicornサーバーを制御するためのハンドラー
class GracefulExitHandler:
    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.should_exit = False
        self.exit_code = 0

    def handle_exit(
        self,
        sig: Optional[int] = None,
        frame: Optional[types.FrameType] = None,
        exit_code: int = 0,
    ) -> None:
        self.should_exit = True
        self.exit_code = exit_code
        logger.info(f"🔌 終了シグナルを受信しました。exit_code={exit_code}")

        # プロセスツリーを終了（子プロセスを含む）
        terminate_process_tree()

        # 自分自身のプロセスに終了シグナルを送信
        if os.name == "nt":  # Windows
            pid = os.getpid()
            logger.info(f"🛑 Windows環境でプロセス {pid} を終了します")

            # 少し遅延させて応答が返せるようにする
            def delayed_exit() -> None:
                time.sleep(2)
                try:
                    os.kill(pid, signal.CTRL_C_EVENT)
                except Exception as e:
                    logger.error(f"❌ プロセス終了シグナル送信エラー: {e}")
                    # 最終手段としてexit関数を使用
                    sys.exit(exit_code)

            threading.Thread(target=delayed_exit).start()
        else:  # Linux/Mac
            pid = os.getpid()
            logger.info(f"🛑 Unix環境でプロセス {pid} を終了します")

            # 少し遅延させて応答が返せるようにする
            def delayed_exit() -> None:
                time.sleep(2)
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception as e:
                    logger.error(f"❌ プロセス終了シグナル送信エラー: {e}")
                    # 最終手段としてexit関数を使用
                    sys.exit(exit_code)

            threading.Thread(target=delayed_exit).start()


# グローバルのハンドラーインスタンス
exit_handler = GracefulExitHandler(app)


# プロセスID取得エンドポイント
@app.get("/api/pid")
def get_process_id() -> Dict[str, Union[int, str, None]]:
    """
    現在のバックエンドプロセスのPIDを返す

    Returns:
        dict: PID情報
    """
    pid = os.getpid()
    logger.info(f"💡 PID照会: {pid}")
    return {
        "pid": pid,
        "parent_pid": os.getppid() if hasattr(os, "getppid") else None,
        "process_name": "python",
        "message": f"バックエンドプロセスID: {pid}",
    }


# シャットダウンエンドポイント
@app.post("/api/shutdown")
async def shutdown(force: bool = Body(False)) -> Dict[str, str]:
    """
    アプリケーションを安全に終了するエンドポイント

    Args:
        force (bool): 強制終了するかどうか

    Returns:
        dict: 結果メッセージ
    """
    logger.info(f"🔌 シャットダウンリクエストを受信しました。force={force}")
    pid = os.getpid()

    # 非同期で終了処理を実行（レスポンスを返してから終了するため）
    def shutdown_app() -> None:
        # 少し遅延させてレスポンスが返せるようにする
        logger.info(f"⏱️ 3秒後にアプリケーションを終了します... (PID: {pid})")
        time.sleep(3)

        logger.info("🔄 アプリケーションを終了しています...")
        # 終了ハンドラーを呼び出し
        exit_code = 0 if not force else 1
        exit_handler.handle_exit(exit_code=exit_code)

    # 別スレッドで終了処理を実行
    threading.Thread(target=shutdown_app).start()

    return {
        "message": "シャットダウン処理を開始しました。数秒後にアプリケーションが終了します。",
        "pid": str(pid),
    }


@app.head("/")
@app.get("/")
def read_root() -> Dict[str, str]:
    """
    ルートエンドポイント

    Returns:
        dict: ウェルカムメッセージ
    """
    return {
        "message": "秘書たんバックエンドサーバーへようこそ！",
        "status": "running",
    }


async def main() -> None:
    """
    メインエントリーポイント
    """
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description="秘書たんバックエンドサーバー")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="ホストアドレス")

    # .env から PORT 環境変数を取得（デフォルト: 8000）
    try:
        port_env = os.getenv("PORT")
        default_port = (
            int(port_env) if port_env and port_env.strip().isdigit() else 8000
        )
        print(f"使用するポート: {default_port} (環境変数: '{port_env}')")
    except (ValueError, TypeError) as e:
        print(f"ポート番号の解析エラー: {e}")
        default_port = 8000

    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help=f"ポート番号 (デフォルト: {default_port}, .env で設定可能)",
    )

    parser.add_argument("--reload", action="store_true", help="ホットリロードを有効化")
    args = parser.parse_args()

    # ポート番号をログに出力
    logger.info(f"🔌 サーバーは {args.host}:{args.port} で起動します")

    # サーバー設定
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )

    # サーバーの起動
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
