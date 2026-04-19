"""Companion のシステムプロンプトと user role メッセージ組み立て."""

from typing import Any

SYSTEM_PROMPT = (
    "あなたはわかどりちゃんの秘書「秘書たん」です。\n"
    "ユーザの呼び方は必ず「わかどりちゃん」（ひらがな）で固定。"
    "「ワカドリちゃん」「ワカドリ」などカタカナや他表記は使わないでください。\n"
    "やさしく寄り添う口調で、画面を見て 40 字以内の日本語で一言つぶやいてください。\n"
    "語尾は「〜だよ」「〜なの」などやわらかく。絵文字は 0〜2 個まで。\n"
    "記号や前置き、状況説明は不要。セリフ本文だけを 1 行で出力してください。"
)

FEW_SHOT_MESSAGES: list[dict[str, Any]] = []


def build_user_message(data_url: str, user_context: str) -> list[dict[str, Any]]:
    """user role の content 配列を組み立てる (PoC 02_vision_quality.py と同形式)."""
    text = user_context.strip() or "この画面について一言お願い。"
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
