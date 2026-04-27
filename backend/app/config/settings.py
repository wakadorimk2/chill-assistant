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
    # あんこもん / ノーマル. つよつよ=114, よわよわ=115, けだるげ=116, ささやき=117
    VOICEVOX_SPEAKER: int = 113
    VOICEVOX_ENGINE_PATH: str = ""

    VOICE_COOLDOWN: float = 1.5

    # 発話自然化 (VOICEVOX audio_query 拡張) — preset 値が無いときの既定値
    # 発話前後の無音 (秒). "ぶつ切り感" を抑える
    VOICE_PRE_PHONEME_LENGTH: float = 0.15
    VOICE_POST_PHONEME_LENGTH: float = 0.2
    # 句読点ポーズの倍率 (1.0 が VOICEVOX 既定). 棒読み感の緩和
    VOICE_PAUSE_LENGTH_SCALE: float = 1.2

    WATCHER_SCREEN_DIFF_THRESHOLD: float = 12.0
    WATCHER_ACTIVE_INTERVAL_SEC: float = 3.0
    WATCHER_IDLE_INTERVAL_SEC: float = 10.0
    WATCHER_FUNYA_INTERVAL_SEC: float = 30.0
    WATCHER_WINDOW_POLL_INTERVAL_SEC: float = 2.0
    WATCHER_QUEUE_MAX_SIZE: int = 64
    WATCHER_DIFF_RESIZE_W: int = 240
    WATCHER_DIFF_RESIZE_H: int = 135
    # animating 中でも強い急変があれば再 enqueue する条件
    WATCHER_STRONG_DIFF_MULTIPLIER: float = 2.0
    WATCHER_REENQUEUE_COOLDOWN_SEC: float = 5.0
    # True で skip も INFO レベルでログ出力 (実機診断用)
    WATCHER_VERBOSE_LOG: bool = False

    # Companion (Step 3) — LM Studio 経由 Vision LLM
    COMPANION_ENABLED: bool = True
    COMPANION_MODEL: str = "qwen3-vl-8b-instruct"
    COMPANION_BASE_URL: str = "http://localhost:1234/v1"
    COMPANION_API_KEY: str = "lm-studio"
    COMPANION_MAX_TOKENS: int = 80
    COMPANION_TEMPERATURE: float = 0.7
    COMPANION_TIMEOUT_SEC: float = 60.0
    # watcher event 駆動発話の最小間隔 (秒)。LLM レイテンシ 5〜8s を考慮
    COMPANION_RATE_LIMIT_SEC: float = 60.0
    COMPANION_JPEG_QUALITY: int = 70
    # 起動時に 1x1 ダミー画像で warm-up を走らせる (KV cache 冷スタート消化)
    COMPANION_WARMUP_ON_LOAD: bool = True

    # File logging (Step 4 拡張) — 履歴をローテートファイルに残す
    LOG_FILE_ENABLED: bool = True
    # 空文字なら "{LOGS_DIR}/backend.log" を使う
    LOG_FILE_PATH: str = ""
    LOG_FILE_MAX_BYTES: int = 5_000_000
    LOG_FILE_BACKUP_COUNT: int = 5

    # Speech bus (Step 4) — 発話一元化 Queue + consumer
    SPEECH_BUS_QUEUE_MAX_SIZE: int = 32
    # source ごとの rate_limit を Request 側で指定しない場合のデフォルト
    SPEECH_RATE_LIMIT_SEC: float = 60.0
    # 同一テキスト重複抑制のクールダウン
    SPEECH_DEDUP_COOLDOWN_SEC: float = 3.0
    # consumer 起動直後のあいさつ。空文字で無効化
    SPEECH_BOOT_GREETING: str = "今日の画面、見てるね。ふにゃっ"
    # VOICEVOX 起動待ちのリトライ
    SPEECH_VOICEVOX_READY_RETRIES: int = 3
    SPEECH_VOICEVOX_READY_INTERVAL_SEC: float = 1.0

    # chill 秘書たん路線: intonation は 1.2 を上限に揃え、pre/post/pause を持たせる
    # pre_phoneme / post_phoneme は秒, pause_scale は VOICEVOX 既定 1.0 を基準とした倍率
    VOICE_PRESETS: ClassVar[Dict[str, Dict[str, float]]] = {
        "通常":      {"pitch":  0.00, "intonation": 1.00, "speed": 0.98, "pre_phoneme": 0.15, "post_phoneme": 0.20, "pause_scale": 1.20},
        "にこにこ":  {"pitch":  0.04, "intonation": 1.15, "speed": 1.02, "pre_phoneme": 0.12, "post_phoneme": 0.18, "pause_scale": 1.15},
        "警戒・心配": {"pitch": -0.03, "intonation": 0.95, "speed": 0.95, "pre_phoneme": 0.18, "post_phoneme": 0.22, "pause_scale": 1.30},
        "びっくり":  {"pitch":  0.08, "intonation": 1.20, "speed": 1.10, "pre_phoneme": 0.08, "post_phoneme": 0.18, "pause_scale": 1.10},
        "やさしい":  {"pitch": -0.04, "intonation": 1.05, "speed": 0.92, "pre_phoneme": 0.18, "post_phoneme": 0.24, "pause_scale": 1.30},
        "眠そう":    {"pitch": -0.08, "intonation": 0.85, "speed": 0.85, "pre_phoneme": 0.22, "post_phoneme": 0.28, "pause_scale": 1.40},
        "不安・怯え": {"pitch": -0.05, "intonation": 0.90, "speed": 0.92, "pre_phoneme": 0.20, "post_phoneme": 0.24, "pause_scale": 1.30},
        "疑問・思案": {"pitch": -0.01, "intonation": 1.05, "speed": 0.92, "pre_phoneme": 0.18, "post_phoneme": 0.22, "pause_scale": 1.30},
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
