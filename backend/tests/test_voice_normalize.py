"""voice.normalize.soften_punctuation の挙動を確認."""

import pytest

from app.modules.voice.normalize import soften_punctuation


@pytest.mark.parametrize(
    "given,expected",
    [
        # 既に終止記号があれば変えない
        ("お疲れさま。", "お疲れさま。"),
        ("見てたよ！", "見てたよ！"),
        ("どうしたの？", "どうしたの？"),
        # 終止記号が無ければ「。」を補う
        ("画面を見てたね", "画面を見てたね。"),
        # 接続詞の直後に「、」が無ければ挿入
        ("でも気にしないで", "でも、気にしないで。"),
        ("だから一緒にいこう", "だから、一緒にいこう。"),
        # 既に句読点があるなら接続詞ロジックは触らない
        ("でも、もう大丈夫。", "でも、もう大丈夫。"),
        # 末尾の前後空白は除去される
        ("  おはよう  ", "おはよう。"),
    ],
)
def test_soften_punctuation_cases(given: str, expected: str) -> None:
    assert soften_punctuation(given) == expected


def test_soften_punctuation_empty() -> None:
    assert soften_punctuation("") == ""
    assert soften_punctuation("   ") == ""


def test_soften_punctuation_idempotent() -> None:
    """2 回適用しても結果が変わらない."""
    once = soften_punctuation("でも気にしないで")
    twice = soften_punctuation(once)
    assert once == twice
