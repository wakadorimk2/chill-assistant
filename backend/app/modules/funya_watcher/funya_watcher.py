"""
ふにゃ見守りモード実装

キーボードとマウスの動きを監視し、一定時間操作がない場合に
「ふにゃ見守りモード」を発動するモジュールです。
"""

import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union

from pynput import keyboard, mouse

logger = logging.getLogger(__name__)


class FunyaWatcher:
    """ふにゃ見守りモードを管理するクラス"""

    def __init__(
        self,
        inactivity_threshold: int = 5,
        messages: Optional[List[str]] = None,
        on_enter_funya_mode: Optional[Callable[[], None]] = None,
        on_exit_funya_mode: Optional[Callable[[], None]] = None,
    ):
        """
        初期化

        Args:
            inactivity_threshold: 無操作と判定する秒数 (デフォルト: 5秒)
            messages: ふにゃメッセージのリスト (指定なしの場合はデフォルトメッセージを使用)
            on_enter_funya_mode: ふにゃモード開始時に呼び出されるコールバック関数
            on_exit_funya_mode: ふにゃモード終了時に呼び出されるコールバック関数
        """
        self.inactivity_threshold = inactivity_threshold

        # デフォルトのふにゃメッセージ
        self.default_messages = [
            "……ふにゃ？だいじょうぶ？ 🐾",
            "ひとやすみ、しよっか ✨",
            "わたし、そばにいるよ 🌸",
            "……しーん。そばにいるよ🐾",
            "おつかれさま……💫",
        ]

        self.messages = messages if messages is not None else self.default_messages
        self.on_enter_funya_mode = on_enter_funya_mode
        self.on_exit_funya_mode = on_exit_funya_mode

        # 最終操作時刻
        self.last_activity_time = datetime.now()

        # 状態管理
        self.is_watching = False
        self.is_in_funya_mode = False
        self._monitor_thread: Optional[threading.Thread] = None

        # 入力監視用リスナー
        self._mouse_listener: Optional[mouse.Listener] = None
        self._keyboard_listener: Optional[keyboard.Listener] = None

    def _on_activity(self) -> None:
        """ユーザーのアクティビティを検知したときの処理"""
        now = datetime.now()
        self.last_activity_time = now

        # ふにゃモードだった場合は終了処理
        if self.is_in_funya_mode:
            self.is_in_funya_mode = False
            if self.on_exit_funya_mode:
                self.on_exit_funya_mode()

    # マウスイベントハンドラー
    def _on_mouse_move(self, x: int, y: int) -> None:
        """マウス移動イベントハンドラー"""
        self._on_activity()

    def _on_mouse_click(
        self, x: int, y: int, button: mouse.Button, pressed: bool
    ) -> None:
        """マウスクリックイベントハンドラー"""
        self._on_activity()

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        """マウススクロールイベントハンドラー"""
        self._on_activity()

    # キーボードイベントハンドラー
    def _on_key_press(self, key: Union[keyboard.Key, keyboard.KeyCode, Any]) -> None:
        """キーボード押下イベントハンドラー"""
        self._on_activity()

    def _on_key_release(self, key: Union[keyboard.Key, keyboard.KeyCode, Any]) -> None:
        """キーボード解放イベントハンドラー"""
        self._on_activity()

    def _monitor_activity(self) -> None:
        """無操作時間を監視するスレッド処理"""
        while self.is_watching:
            now = datetime.now()
            inactive_time = (now - self.last_activity_time).total_seconds()

            # 無操作時間が閾値を超えた場合
            if inactive_time >= self.inactivity_threshold and not self.is_in_funya_mode:
                self.is_in_funya_mode = True
                # 発話の組み立てと配信は callback 側 (speech_bus 経由) に委譲
                logger.debug(
                    f"funya mode 発動 (無操作 {int(inactive_time)}s)"
                )
                if self.on_enter_funya_mode:
                    try:
                        self.on_enter_funya_mode()
                    except Exception as e:
                        logger.error(
                            f"on_enter_funya_mode コールバック例外: {e}"
                        )

            # 1秒待機
            time.sleep(1)

    def start(self) -> None:
        """監視を開始する"""
        if self.is_watching:
            return

        self.is_watching = True
        self.last_activity_time = datetime.now()

        # マウスリスナーの設定
        self._mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll,
        )
        self._mouse_listener.start()

        # キーボードリスナーの設定
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press, on_release=self._on_key_release
        )
        self._keyboard_listener.start()

        # 無操作状態監視スレッドの開始
        self._monitor_thread = threading.Thread(target=self._monitor_activity)
        self._monitor_thread.daemon = True
        self._monitor_thread.start()

        logger.info("🐾 ふにゃ見守りモードを開始しました…")

    def stop(self) -> None:
        """監視を停止する"""
        if not self.is_watching:
            return

        self.is_watching = False

        # リスナーの停止
        if self._mouse_listener:
            self._mouse_listener.stop()

        if self._keyboard_listener:
            self._keyboard_listener.stop()

        # スレッドの終了（デーモンなので明示的終了は不要）
        self._monitor_thread = None

        logger.info("🐾 ふにゃ見守りモードを終了しました…")

    def get_status(self) -> Dict[str, Union[bool, int]]:
        """
        ふにゃモードの状態を取得する

        Returns:
            Dict[str, Union[bool, int]]: ふにゃモードの状態情報を含む辞書
        """
        now = datetime.now()
        inactive_duration = (now - self.last_activity_time).total_seconds()

        return {
            "watching": self.is_in_funya_mode,
            "last_active_seconds": int(inactive_duration),
        }
