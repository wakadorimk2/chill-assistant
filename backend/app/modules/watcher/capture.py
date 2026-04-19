"""
画面キャプチャと差分計算用前処理

mss / cv2 を使う純関数のみ。クラス階層は作らない。
"""

import cv2
import mss
import numpy as np
from numpy.typing import NDArray


def capture_primary_screen() -> NDArray[np.uint8]:
    """
    プライマリモニタを 1 枚キャプチャして BGR ndarray を返す。

    `with mss.mss() as sct:` を関数内で開閉することで、スレッド固定問題を回避する。
    (ocr/ocr_capture.py と同じパターン)
    """
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        img = np.array(screenshot)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def to_gray_small(
    frame: NDArray[np.uint8],
    size: tuple[int, int] = (240, 135),
) -> NDArray[np.uint8]:
    """グレースケール化 + INTER_AREA リサイズ。差分計算用。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, size, interpolation=cv2.INTER_AREA)
