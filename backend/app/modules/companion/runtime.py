"""Companion ランタイム — LM Studio の OpenAI 互換 API を叩いて短文を生成する."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any, Optional

import cv2
import numpy as np
from numpy.typing import NDArray
from openai import OpenAI

from .prompts import FEW_SHOT_MESSAGES, SYSTEM_PROMPT, build_user_message

logger = logging.getLogger(__name__)


class Companion:
    """Vision LLM ラッパ (LM Studio 経由)."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        max_tokens: int = 80,
        temperature: float = 0.7,
        timeout_sec: float = 60.0,
        jpeg_quality: int = 70,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout_sec = timeout_sec
        self._jpeg_quality = jpeg_quality
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._ready = False
        self._warmup_latency_sec: Optional[float] = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def warmup_latency_sec(self) -> Optional[float]:
        return self._warmup_latency_sec

    async def load(self, warmup: bool = True) -> None:
        """LM Studio の死活確認と任意 warm-up."""
        try:
            await asyncio.to_thread(self._client.models.list)
            self._ready = True
            logger.info(
                f"Companion: LM Studio 接続確認 OK "
                f"(base_url={self._base_url}, model={self._model})"
            )
        except Exception as e:
            self._ready = False
            logger.warning(
                f"Companion: LM Studio 接続確認に失敗 (起動は継続): "
                f"{type(e).__name__}: {e}"
            )
            return

        if not warmup:
            return

        try:
            # 初回 KV cache 冷スタートを warm-up で消化 (PoC で未実装だった)。
            # 1x1 は Vision encoder が "model crashed" で弾くことがあるので 256x256 に。
            dummy = np.zeros((256, 256, 3), dtype=np.uint8)
            start = time.perf_counter()
            text = await self.generate(dummy, "warm-up")
            self._warmup_latency_sec = round(time.perf_counter() - start, 2)
            logger.info(
                f"Companion: warm-up 完了 "
                f"(latency={self._warmup_latency_sec}s, reply_len={len(text)})"
            )
        except Exception as e:
            logger.warning(
                f"Companion: warm-up に失敗 (握って続行): {type(e).__name__}: {e}"
            )

    async def generate(
        self, image: NDArray[np.uint8], user_context: str
    ) -> str:
        """ndarray 入力で発話テキストを生成."""
        try:
            encode_result = await asyncio.to_thread(
                cv2.imencode,
                ".jpg",
                image,
                [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality],
            )
            ok, buf = encode_result
            if not ok:
                logger.error("Companion: JPEG エンコードに失敗")
                return ""
            jpeg_bytes = bytes(buf.tobytes())
        except Exception as e:
            logger.error(f"Companion: JPEG エンコード例外: {type(e).__name__}: {e}")
            return ""
        return await self.generate_from_jpeg(jpeg_bytes, user_context)

    async def generate_from_jpeg(
        self, jpeg_bytes: bytes, user_context: str
    ) -> str:
        """JPEG bytes 入力で発話テキストを生成 (watcher.get_latest_frame_jpeg 直結用)."""
        if not jpeg_bytes:
            return ""
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        data_url = f"data:image/jpeg;base64,{b64}"

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        messages.extend(FEW_SHOT_MESSAGES)
        messages.append(
            {"role": "user", "content": build_user_message(data_url, user_context)}
        )

        try:
            resp = await asyncio.to_thread(
                lambda: self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    timeout=self._timeout_sec,
                )
            )
            text = (resp.choices[0].message.content or "").strip()
            return text
        except Exception as e:
            logger.error(
                f"Companion: 推論に失敗: {type(e).__name__}: {e}"
            )
            return ""
