"""発話テキストの軽量正規化.

VOICEVOX のポーズ解析が「、」「。」を頼りに抑揚を生成するため、
LLM が句読点を吐かないと棒読みになる。発話直前に最小限の句読点を補う。
"""

from __future__ import annotations

import re

# 文末として許容する記号 (VOICEVOX が文末として解釈する / 違和感が無いもの)
_SENTENCE_END_CHARS: tuple[str, ...] = (
    "。", "！", "？", "♪", "〜", "～", "…",
    ".", "!", "?",
)

# 直後にポーズを置きたい接続詞 (現れたら「、」を補う)
_CONNECTIVES: tuple[str, ...] = (
    "でも", "けど", "だから", "だって", "それで", "そして",
    "ところで", "なので", "つまり", "ちなみに",
)

_CONNECTIVE_RE = re.compile(
    "(" + "|".join(re.escape(c) for c in _CONNECTIVES) + r")(?![、。！？!?,.])"
)


def soften_punctuation(text: str) -> str:
    """LLM 応答に最低限の句読点を補う純粋関数.

    - 文末に終止記号が無ければ「。」を補う
    - 主要な接続詞の直後に「、」が無ければ挿入
    - 空文字列はそのまま返す
    """
    if not text:
        return text
    s = text.strip()
    if not s:
        return s

    s = _CONNECTIVE_RE.sub(r"\1、", s)

    if not s.endswith(_SENTENCE_END_CHARS):
        s = s + "。"

    return s
