"""
アプリケーション設定

pydantic-settings を使って環境変数や .env ファイルから設定を読み込む。
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Dict

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent
APP_DIR = BASE_DIR / "app"
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    """アプリケーション設定クラス (pydantic-settings)"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    DEBUG_MODE: bool = False

    STATIC_DIR: str = str(DATA_DIR / "static")
    LOGS_DIR: str = str(DATA_DIR / "logs")
    TEMP_DIR: str = str(DATA_DIR / "temp")
    SHARED_DIR: str = str(DATA_DIR / "shared")
    DIALOGUES_DIR: str = str(DATA_DIR / "dialogues")
    IMAGES_DIR: str = str(BASE_DIR.parent / "assets" / "images")

    VOICEVOX_HOST: str = "http://127.0.0.1:50021"
    VOICEVOX_SPEAKER: int = 0
    VOICEVOX_ENGINE_PATH: str = ""

    VOICE_COOLDOWN: float = 1.5

    WATCHER_SCREEN_DIFF_THRESHOLD: float = 12.0
    WATCHER_ACTIVE_INTERVAL_SEC: float = 3.0
    WATCHER_IDLE_INTERVAL_SEC: float = 10.0
    WATCHER_FUNYA_INTERVAL_SEC: float = 30.0
    WATCHER_WINDOW_POLL_INTERVAL_SEC: float = 2.0
    WATCHER_QUEUE_MAX_SIZE: int = 64
    WATCHER_DIFF_RESIZE_W: int = 240
    WATCHER_DIFF_RESIZE_H: int = 135

    VOICE_PRESETS: ClassVar[Dict[str, Dict[str, float]]] = {
        "通常": {"pitch": 0.0, "intonation": 1.0, "speed": 1.0},
        "にこにこ": {"pitch": 0.06, "intonation": 1.3, "speed": 1.05},
        "警戒・心配": {"pitch": -0.03, "intonation": 0.9, "speed": 0.95},
        "びっくり": {"pitch": 0.12, "intonation": 1.5, "speed": 1.2},
        "やさしい": {"pitch": -0.06, "intonation": 1.1, "speed": 0.9},
        "眠そう": {"pitch": -0.09, "intonation": 0.8, "speed": 0.8},
        "不安・怯え": {"pitch": -0.05, "intonation": 0.85, "speed": 0.9},
        "疑問・思案": {"pitch": -0.01, "intonation": 1.1, "speed": 0.9},
    }

    PRESET_SOUNDS: ClassVar[Dict[str, str]] = {
        "驚き": "kya.wav",
        "心配": "sigh.wav",
        "恐怖": "scream.wav",
        "ふにゃ": "funya.wav",
        "小さな驚き": "altu.wav",
        "安堵": "sigh.wav",
        "うーん": "sigh.wav",
        "出現": "appear.wav",
        "消失": "disapper.wav",
    }

    def model_post_init(self, __context: Any) -> None:
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for directory in (
            self.STATIC_DIR,
            self.LOGS_DIR,
            self.TEMP_DIR,
            self.SHARED_DIR,
            self.DIALOGUES_DIR,
        ):
            path = Path(directory)
            if not path.exists():
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"ディレクトリを作成しました: {directory}")
                except Exception as e:
                    logger.error(f"ディレクトリの作成に失敗しました: {directory} - {e}")

    def load_dialogues(self, dialogue_file: str) -> Dict[str, Any]:
        dialogue_path = Path(self.DIALOGUES_DIR) / dialogue_file
        try:
            if dialogue_path.exists():
                with open(dialogue_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            logger.warning(f"対話ファイルが見つかりません: {dialogue_path}")
            return {}
        except Exception as e:
            logger.error(f"対話ファイルの読み込みに失敗しました: {e}")
            return {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """設定のシングルトンインスタンスを取得"""
    return Settings()
