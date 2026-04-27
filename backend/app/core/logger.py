"""
カスタムロガーモジュール

アプリケーション全体で使用される拡張ロギング機能を提供します
"""

import io
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

# UTF-8エンコーディングの標準出力・標準エラー出力を設定
# 既に設定されていない場合のみ設定
if not hasattr(sys.stdout, "encoding") or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if not hasattr(sys.stderr, "encoding") or sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


# カラー定義
class ColorCodes:
    GREY = "\033[37m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    BLUE = "\033[34m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"


# カスタムフォーマッタ
class ColoredFormatter(logging.Formatter):
    """
    カラー付きのログフォーマッタ
    """

    COLORS = {
        "DEBUG": ColorCodes.CYAN,
        "INFO": ColorCodes.GREEN,
        "WARNING": ColorCodes.YELLOW,
        "ERROR": ColorCodes.RED,
        "CRITICAL": ColorCodes.BOLD + ColorCodes.RED,
    }

    def __init__(self, fmt: str, datefmt: Optional[str] = None):
        super().__init__(fmt, datefmt)

    def format(self, record: logging.LogRecord) -> str:
        # 後段 handler (file 等) に色コードが漏れないよう、record は変えずに
        # フォーマット中だけ一時的に levelname/name を差し替えて元に戻す
        original_levelname = record.levelname
        original_name = record.name
        if original_levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[original_levelname]}"
                f"{original_levelname}{ColorCodes.RESET}"
            )
        record.name = f"{ColorCodes.BLUE}{original_name}{ColorCodes.RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname
            record.name = original_name


def setup_logger(
    name: Optional[str] = None, level: int = logging.INFO
) -> logging.Logger:
    """
    アプリケーション用のロガーをセットアップ

    Args:
        name: ロガー名（デフォルトはルートロガー）
        level: ログレベル（デフォルトはINFO）

    Returns:
        logging.Logger: 設定されたロガーインスタンス
    """
    # ロガーの取得
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 既存のハンドラをクリア
    if logger.handlers:
        logger.handlers.clear()

    # 標準出力へのハンドラを作成
    # sys.stdoutは既にUTF-8エンコーディングが設定されているので、そのまま使用
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # フォーマッタの設定
    formatter = ColoredFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)

    # ハンドラの追加
    logger.addHandler(console_handler)

    return logger


def setup_file_logging(
    log_file: str,
    max_bytes: int = 5_000_000,
    backup_count: int = 5,
    level: int = logging.INFO,
    parent_logger_name: str = "backend.app",
) -> None:
    """親 logger に RotatingFileHandler を 1 つだけ追加.

    setup_logger() で立てた子 logger は propagate=True (default) なので、
    親に handler を 1 つ入れれば子由来のログも全部このファイルに書かれる.
    重複呼び出しは前回の RotatingFileHandler を捨ててから新しいものを付ける.

    Args:
        log_file: 出力ファイルパス
        max_bytes: ローテートサイズ (bytes)
        backup_count: 保持する世代数
        level: ファイルに残すログレベル
        parent_logger_name: handler を付ける logger 名 (default: "backend.app")
    """
    parent = logging.getLogger(parent_logger_name)
    parent.setLevel(level)

    # 既存の RotatingFileHandler を捨てて重複防止
    for h in list(parent.handlers):
        if isinstance(h, RotatingFileHandler):
            parent.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass

    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    parent.addHandler(handler)
    parent.info(
        f"📝 ファイルロガー有効: {log_file} "
        f"(maxBytes={max_bytes}, backupCount={backup_count})"
    )


# エラーフォーマッタ（スタックトレース出力用）
def format_exception(exc: Exception) -> str:
    """
    例外情報を読みやすくフォーマット

    Args:
        exc: 例外オブジェクト

    Returns:
        str: フォーマットされた例外情報
    """
    return (
        f"{ColorCodes.RED}エラー ({type(exc).__name__}): {str(exc)}{ColorCodes.RESET}"
    )


# 使用例:
# logger = setup_logger(__name__)
# logger.info("情報メッセージ")
# logger.warning("警告メッセージ")
# logger.error("エラーメッセージ")
#
# try:
#     1/0
# except Exception as e:
#     logger.error(format_exception(e))
