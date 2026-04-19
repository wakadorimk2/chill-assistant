# 02 — 二層構造への移行プラン（素案）

**作成日**: 2026-04-19
**対象**: chill-assistant を YOLO ベースのゲーム連動アプリから、Vision LLM ベースの汎用相棒に作り替える
**想定ハードウェア**: Ryzen 7 7800X3D / RTX 5070 12GB GDDR7 / 64GB RAM / Windows 11 Pro

> このドキュメントは「素案」。最終的なモデル選定・ランタイム選定は Step 3 着手前に実測で確定する。不確かな数値には **【要確認】** マーク、調査中に出た改善アイデアには **[提案]** マーカーを付けている。

---

## 1. 全体アーキテクチャ（結論先出し）

```
┌────────────── Electron (frontend) ──────────────┐
│ 立ち絵 / 吹き出し / 肉球ボタン                   │
│ SpeechManager + expressionManager                │
│ WebSocket 受信: {type:"speak", text, emotion}    │
└──────────────▲───────────────────────────────────┘
               │ WebSocket (既存 manager.broadcast)
┌──────────────┴─── FastAPI (backend) ─────────────┐
│                                                   │
│  voice.engine.speak_with_emotion (温存・無改修)   │
│           ▲                                       │
│           │ generated text + emotion              │
│  ┌────────┴──────────────┐                        │
│  │ companion.service     │ ← 喋り手層             │
│  │ (Vision LLM runtime)  │   イベント時 or N分毎  │
│  └────────▲──────────────┘                        │
│           │ WatcherEvent                          │
│           │ (asyncio.Queue)                       │
│  ┌────────┴──────────────┐                        │
│  │ watcher.service       │ ← 見張り番層           │
│  │ (mss / diff / title)  │   常時稼働            │
│  └───────────────────────┘                        │
│                                                   │
│  既存温存:                                        │
│    voice / emotion / funya_state / ws /           │
│    ocr / voicevox_starter                         │
└───────────────────────────────────────────────────┘
```

- **同プロセス内の 2 つの asyncio タスク** として実装
- 間を `asyncio.Queue[WatcherEvent]` で接続
- 既存 `ws/manager.py`・`voice/engine.py`・`funya_watcher.py` は無改修で再利用
- Step 4 で `speech_bus` asyncio.Queue を導入し、companion / funya / その他の発話リクエストを一元化

---

## 2. 見張り番層（Watcher）設計

### 2.1 責務

| 観点 | 設計 |
|---|---|
| 目的 | 「いま喋り手を起こす価値があるか」の軽量判定のみ。自身は一切喋らない |
| 周期 | フェーズ分け: **アクティブ時 3秒 / アイドル時 10秒 / ふにゃモード中 30秒** |
| 出力 | `WatcherEvent(kind, score, screenshot_bytes, window_title, ts)` を `asyncio.Queue` に enqueue |
| VRAM | 0（純粋な CV / OS 呼び出しのみ） |
| CPU 目標 | <5%（アイドル時） |

### 2.2 検知シグナル 4 種

| 優先 | シグナル | 実装 | コスト |
|---|---|---|---|
| 高 | ウィンドウタイトル変化 | `pywin32.GetForegroundWindow` + `GetWindowText` を 2秒毎 | 極軽 |
| 中 | 画面大変化 | mss で 3〜10秒毎に 1枚 → Gray → 240×135 縮小 → `cv2.absdiff` の `np.mean()` がしきい値 (~12.0) 超 | 軽 |
| 中 | ユーザ無操作 | 既存 `FunyaWatcher` の状態を `services/funya_state.py` 経由で参照（書き込みはしない） | 0 |
| 低 | 音量スパイク | WASAPI loopback で RMS 測定 → フェーズ2送り | 中 |

### 2.3 ファイル構成（新設）

```
backend/app/modules/watcher/
├── __init__.py
├── service.py           # WatcherService、Queue の所有者、start/stop
├── screen_watcher.py    # mss + cv2.absdiff のメインループ
├── window_watcher.py    # pywin32 GetForegroundWindow ポーリング
├── capture.py           # mss / dxcam 切替アダプタ (capture_screen() -> np.ndarray)  [提案]
└── events.py            # @dataclass WatcherEvent
```

### 2.4 既存 `zombie/monitor.py` からの流用方針

流用する骨格:
- `with mss.mss() as sct: while self.is_monitoring: ...` のループ構造
- CPU 使用率に応じた `adaptive_interval` の伸縮ロジック
- `asyncio.CancelledError` を掴んでの graceful 終了

流用しない部分:
- YOLO / ResNet 依存、`detector_core` 全体
- `cooldown_timestamps` の "few/warning/many" 三段階
- `_process_detection_results` の副作用過多な構造

→ **monitor.py を読みながら 60〜100 行の新 `screen_watcher.py` を書き起こす**のが現実的。

### 2.5 FunyaWatcher との関係

**推奨: 併存（吸収しない）**

- FunyaWatcher = 「無操作を検知してキャラが自発的に寄り添う」という UX 完成機能 → 温存
- 新 Watcher = 「画面内容の変化を Vision LLM に運ぶ」という技術的役割
- 両者は同階層に並べ、新 Watcher が FunyaWatcher の状態を**参照のみ**（`services/funya_state.py` 経由、書き込み禁止）

---

## 3. 喋り手層（Companion）設計

### 3.1 責務

| 観点 | 設計 |
|---|---|
| 目的 | Watcher Event + キャプチャを Vision LLM に通し、**秘書たん口調の短文 40字程度** を生成 |
| 起動モード | (a) Watcher イベント駆動 (b) タイマー駆動「2〜5分毎のぼそっと一言」 |
| レート制限 | 1分に最大1発話のハードリミット + 話題ジャンル別 2分クールダウン |
| VRAM | 常駐ロード（§5 で詳述） |
| 出力 | 生成テキスト → `voice/engine.speak_with_emotion()` へ渡して完結 |

### 3.2 ファイル構成（新設）

```
backend/app/modules/companion/
├── __init__.py
├── runtime.py           # llama-cpp-python / ONNX Runtime GenAI ラッパ (Companion.generate)
├── prompts.py           # システムプロンプト + few-shot 例（既存セリフ辞書を移植）
└── service.py           # タイマー + Queue consumer + レート制限
```

### 3.3 Vision LLM モデル候補比較

> **注**: 数値はコミュニティ報告ベースの概算、2025年末〜2026年初頭時点の情報。すべて実機計測で **【要確認】**。

| モデル | パラメータ | VRAM (4bit) | VRAM (fp16) | 推論レイテンシ (5070・画像1+短文) | 日本語品質 | GGUF | ONNX | ライセンス |
|---|---|---|---|---|---|---|---|---|
| Qwen2.5-VL 7B | 7B | ~6 GB **【要確認】** | ~16 GB | 2〜4秒 **【要確認】** | 良好 | ○ | △ 非公式 | Apache 2.0 |
| Qwen2.5-VL 3B | 3B | ~3 GB | ~7 GB | 1〜2秒 **【要確認】** | 中〜良 | ○ | △ | Apache 2.0 |
| Phi-3.5-Vision | 4.2B | ~4 GB | ~9 GB | 2〜3秒 **【要確認】** | 中（プロンプト誘導要） | △ | **◎ ORT GenAI 公式** | MIT |
| Florence-2 + Phi-3.5-mini | 0.77B + 3.8B | ~4 GB | ~8 GB | Florence 0.3s + LLM 1s | Florence 英語のみ（要翻訳） | 両方 ○ | Florence ◎ | MIT / MIT |
| InternVL 2.5 8B | 8B | ~7 GB | ~18 GB | 3〜5秒 **【要確認】** | 良 | ○ | △ | MIT（重み条件あり）**【要確認】** |
| MiniCPM-V 2.6 | 8B | ~6 GB | ~16 GB | 3〜5秒 | 中〜良 | ○ | △ | Apache 2.0 + 条項 **【要確認】** |
| Llama-3.2 Vision 11B | 11B | ~9 GB | 24GB超 | 4〜7秒 | 中（日本語チューニング弱い） | ○ | △ | Llama Community License |
| Gemma 3 Vision 系 | — | **【要確認】** | **【要確認】** | **【要確認】** | **【要確認】** | **【要確認】** | **【要確認】** | Gemma License **【要確認】** |

### 3.4 推奨モデル

#### 第一候補: **Qwen2.5-VL 7B (GGUF Q4_K_M)**

- 候補群で日本語品質が頭ひとつ抜ける（Qwen 系は一貫して日本語が強い）
- 4bit で約 6GB、5070 12GB に残り 6GB 余らせられる
- Apache 2.0 で商用含め使い勝手が素直
- llama-cpp-python + GGUF の組み合わせはユーザーの「Ollama 避けたい、直接ランタイムを触りたい」前提に合う

#### 第二候補: **Phi-3.5-Vision（ONNX Runtime GenAI 経由）**

- ユーザーの「ONNX Runtime 直叩き前例あり」資産を活かす
- MS が一番注力して整備している Vision モデル、公式サンプル豊富
- 日本語はシステムプロンプトで「短い日本語で返答」と強く縛れば運用可能
- 欠点: 日本語品質が Qwen に劣る、DirectML フォールバックの懸念

### 3.5 常駐 vs 必要時ロード

**推奨: 常駐（起動時1回ロード）** ただし条件付き

理由:
- ロード時間 5〜15秒。毎回払うと「画面変化から 20秒後に喋る」体験になり破綻
- 7B-4bit で 6GB なら常駐しても 5070 の予算内
- アンロード / ロードはむしろ **VRAM 断片化の原因** になりやすい

例外運用:
- ユーザーがフルスクリーンゲームを起動 → companion を eager unload（`window_watcher` が検知）
- ゲーム終了 → reload

3B を選ぶケース:
- 30秒ごとに軽く喋らせたい用途なら Qwen2.5-VL 3B に落とす価値あり
- ただし内容の妥当性は落ちる → `03_open_questions.md` で判断

---

## 4. 推論ランタイム比較

### 4.1 候補比較

| ランタイム | Windows+CUDA12 成熟度 | Vision LLM 対応 | 実装量 | 所感 |
|---|---|---|---|---|
| **ONNX Runtime GenAI** | ◎ MS 本体、Windows DX 最優先 **【要確認】** | Phi-3.5-Vision 公式、他は少ない | 小 | ユーザ前例あり、Phi 系なら最強 |
| **llama-cpp-python (GGUF)** | ○ CUDA backend 安定、別ビルド要 **【要確認】** | Qwen2.5-VL, MiniCPM-V など順次対応 | 小 | Python から `llama_cpp.Llama` でロード一発 |
| **Transformers + bitsandbytes 4bit** | ○ Windows で歴史的に鬼門、2025 後半に公式 wheel 整備 **【要確認】** | 最多 | 中 | 最後の手段、柔軟性最大 |
| **vLLM** | △ Windows は WSL2 前提が主流 **【要確認】** | 多い | 中 | Windows ネイティブは茨の道 |
| **LMDeploy / TensorRT-LLM** | ○ NVIDIA 直系 **【要確認】** | 多い | 大 | エンジンビルド面倒、単一モデルには過剰 |

### 4.2 推奨順位（ユーザー前提反映）

1. **llama-cpp-python + GGUF**（第一推奨）
   - Ollama 忌避に最も整合。Ollama は中身が llama.cpp のラッパーなので「llama.cpp を直接叩く」は求めている粒度
   - Qwen2.5-VL 7B-GGUF Q4_K_M を 1 ファイルロード
   - CPU fallback も同 API で書ける（保険）
2. **ONNX Runtime GenAI**（第二推奨）
   - ユーザーの前例資産活用ルート
   - 日本語品質 vs 習熟度で 1 と 2 が入れ替わる可能性あり
3. **Transformers (4bit)**（緊急時のみ）
   - Windows + bitsandbytes の噛み合わせが散発する **【要確認】**、最初から選ばない
4. vLLM / LMDeploy は単一マシン 1 ユーザー用途ではオーバーキル

### 4.3 最終決定前に測る 3 項目

Step 3 着手前に以下を実測して決定:

1. llama-cpp-python の CUDA ビルド wheel が RTX 5070 (Blackwell, sm_120 相当) に対応しているか
2. Qwen2.5-VL 7B-GGUF の vision projector 層が llama.cpp mainline で完全動作するか（VL は text-only より対応が遅れがち）
3. Phi-3.5-Vision の日本語プロンプト動作が体感レベルで納得いくか（同一プロンプト 30 サンプル比較）

---

## 5. 既存 VOICEVOX 層への接続点

### 5.1 4 案比較

| 案 | pros | cons | 事故リスク |
|---|---|---|---|
| 1. companion から直接 `speak_with_emotion()` | 最短コード、既存関数そのまま | テスト困難、モック困難 | 中：起動前呼び出しは `is_voicevox_ready` 未チェック |
| 2. REST `POST /api/companion/speak` | HTTP で叩ける、再現可能 | 同プロセス内で無駄な HTTP、タイムアウト問題 | 低 |
| 3. WS `{type:"speak",...}` broadcast のみ | フロント一本化、既存パターン踏襲 | フロント未起動時に音が出ない、バックエンド単体テスト困難 | 低 |
| 4. `asyncio.Queue` internal event bus | モジュール疎結合、複数購読者可能、テスト容易 | 設計手数増、デバッグ追跡手間 | 最低 |

### 5.2 推奨: **案 4 ＋ 案 3 併用**

```
companion.generate(text, emotion)
   ↓  speech_bus.put(SpeechRequest(text, emotion, source="companion"))
   ↓
┌─ speech_consumer (単一コンシューマ) ─┐
│  1. dedup / throttle 判定             │
│  2. voice.engine.speak_with_emotion()  ← 音声再生
│  3. manager.broadcast({type:"speak"})  ← 表情・吹き出し用にフロント通知
└────────────────────────────────────────┘
```

ポイント:
- 発話の意思決定 / VOICEVOX API 呼び出し / フロント配信を分離
- speech_consumer に `is_message_duplicate` / VOICEVOX 起動待ち / `is_voicevox_ready` ポーリングをまとめる
- companion / watcher / funya / 将来の他モジュールは全部 Queue に流し込むだけ

### 5.3 MVP は案 1 でスタート

Step 3 で LLM ロードと発話疎通の確認を最短でやりたいので、**Step 3 時点では案 1（直接呼び出し）で動かし、Step 4 で案 4 にリファクタ**する。冗長な配管を先に作ると初動が遅れるため。

### 5.4 既存の事故モード対策

- **VOICEVOX 未起動時呼び出し** → speech_consumer 内で `await is_voicevox_ready()` を 3 回 1秒間隔リトライ、失敗でドロップ
- **音声重複** → 既存 `player.is_message_duplicate(message_type, text, 3.0)` がそのまま効く。`message_type = "companion_comment"` を新設
- **ゲームフルスクリーン中の抑制** → speech_consumer 前段で「フォアグラウンドが games 一覧に含まれる場合は `importance=low` を drop」フィルタ

---

## 6. 実装フェーズ（5段階）

### Step 1 — 破棄フェーズ

**作業**:
- `backend/app/modules/zombie/` 削除
- `backend/trained_models/zombie_detector_v2/` 削除
- `backend/ml/` 配下のスクリプト・画像削除
- `backend/requirements.txt` から `ultralytics`, `torch`, `torchvision` 削除
- `backend/ml/requirements.txt` 削除
- `backend/app/events/startup_handler.py` の `start_zombie_monitoring` 呼び出し削除
- `backend/app/events/shutdown_handler.py` の `stop_zombie_monitoring` 呼び出し削除
- `backend/app/routers/websocket.py:104-275` の start/stop_monitoring コマンド分岐削除
- `backend/app/routers/voice.py:230-286` の `react_to_zombie` エンドポイント削除
- `pyproject.toml` の Python target を `py311` or `py312` に変更検討 **【要確認】**
- `fastapi 0.104.1 → 0.115系 / pydantic 2.4.2 → 2.9系` への更新可否を検証（`BaseSettings` 壊れ確認）
- `.env` に `VOICEVOX_ENGINE_PATH` を明示
- **[提案]** `voicevox_starter.py` の `default_paths` に `%LOCALAPPDATA%\Programs\VOICEVOX\vv-engine\run.exe` 追加

**DoD**:
- `python backend/main.py` がエラーなく起動
- `/ws` に接続でき、REST `POST /api/voice/synthesize` で任意のテキストが VOICEVOX 経由で合成・再生できる
- 立ち絵クリックで既存のランダムセリフが問題なく喋れる

---

### Step 2 — watcher 骨格

**作業**:
- `backend/app/modules/watcher/` を新設（`__init__.py`, `service.py`, `screen_watcher.py`, `window_watcher.py`, `capture.py`, `events.py`）
- `service.py` は `asyncio.Queue[WatcherEvent]` を所有、`startup_handler` から `create_task` で起動
- `screen_watcher.py`: mss + cv2.absdiff の 3/10/30秒フェーズループ
- `window_watcher.py`: `pywin32.GetForegroundWindow` を 2秒毎ポーリング
- `capture.py`: `capture_screen() -> np.ndarray` のアダプタ（初期実装は mss のみ）**[提案]**
- `requirements.txt` に `pywin32` を追加
- 試験的に `ws/manager.py` 経由で `{type:"watcher_event", kind, score}` をブロードキャスト（喋らせない）

**DoD**:
- アプリ起動後、YouTube 再生 / 停止 / タブ切替 を行うとフロント側の DevTools で `watcher_event` が観測される
- CPU 使用率が 5% 未満（アイドル時）
- マルチモニタ環境で少なくともプライマリが正しくキャプチャされる

---

### Step 3 — companion 骨格（LLM ロードとダミー発話）

**作業**:
- 実測 3 項目を Step 2 完了時までに済ませてモデル・ランタイム確定（§4.3）
- `backend/app/modules/companion/` 新設（`runtime.py`, `prompts.py`, `service.py`）
- `requirements.txt` に `llama-cpp-python` (CUDA) を追加
- `runtime.py` に `Companion.generate(image: np.ndarray, user_context: str) -> str` を実装
- モデルは起動時にロード（`startup_handler` から `await companion.load()`）
- テスト用エンドポイント `POST /api/companion/debug-speak` を追加（固定画像 → LLM 推論 → `speak_with_emotion()` 直呼び）
- `prompts.py` に最小限のシステムプロンプト（「秘書たん口調、40字以内、日本語」）

**DoD**:
- `curl -X POST /api/companion/debug-speak -F "image=@test.png"` で秘書たんが喋る
- VRAM 使用量が 6GB 前後で安定、漏れなし
- 推論レイテンシ 1 画像あたり 5秒以内（画像 1 + 短文 40字）

---

### Step 4 — watcher ↔ companion 接続 + speech_bus リファクタ

**作業**:
- `companion/service.py` が watcher の Queue を consume
- レート制限実装: 1分1発話、同種イベント 2分クールダウン
- `speech_bus` (asyncio.Queue[SpeechRequest]) を新設（§5.2）
- `speech_consumer` タスクを `startup_handler` で起動
- companion / funya の発話を speech_bus 経由に切り替え
- プロンプトテンプレート改善: 「秘書たん口調」「40字以内」「画面を直接指した口調禁止」「自然に触れる」
- 起動時ダミー発話: 「今日の画面、見てるね。ふにゃっ」

**DoD**:
- ブラウザでサイトを切り替えると 5〜10 秒以内に立ち絵が切替後の内容に触れた一言を喋る
- 1 分間に 2 発話以上しないことをログで確認
- VOICEVOX 未起動状態でも application がクラッシュせず、復帰後に正常発話

---

### Step 5 — 定期「何気ない一言」＋ セリフ辞書 few-shot 移植

**作業**:
- `companion/service.py` にタイマータスク追加（3〜6 分ランダム間隔）
- 既存セリフ辞書を `companion/prompts.py` の few-shot 例に移植:
  - `frontend/src/emotion/emotionHandler.js:15-24` のランダムセリフ 8件
  - `backend/app/modules/funya_watcher/funya_watcher.py:37-43` の見守りセリフ 5件
- FunyaWatcher 無操作イベントを watcher 経由で companion に渡す（「ユーザが離れている」コンテキスト）
- LLM 出力の末尾に `[emotion:surprised]` 等の制御トークンを出させ、前段でパース → `speak_with_emotion` の引数にマップ
- VOICE_PRESETS (7 種) との紐付け

**DoD**:
- 1 時間放置して 10〜20 回程度の自然な発話
- ログ上の同一セリフ重複率 10% 未満
- 手元の主観評価で「秘書たんらしさ」が 2025年版と同等以上

---

## 7. 実装の前提・依存

### 7.1 新規追加パッケージ

| パッケージ | 用途 | バージョン指定 |
|---|---|---|
| `llama-cpp-python` | 第一候補ランタイム | CUDA ビルド推奨。5070 sm_120 対応 wheel 確認 **【要確認】** |
| `pywin32` | フォアグラウンドウィンドウ監視 | 最新 |
| `onnxruntime-genai` | 第二候補ランタイム（選定後） | CUDA Provider 明示 |
| (任意) `dxcam` | capture.py 内の切替候補 | 要求が出たら追加 |

### 7.2 環境変数（新規）

| 変数 | 用途 | 既定値 |
|---|---|---|
| `COMPANION_MODEL_PATH` | GGUF / ONNX モデルファイルパス | — |
| `COMPANION_RUNTIME` | `llama_cpp` / `onnx_genai` | `llama_cpp` |
| `COMPANION_SPEAK_RATE_LIMIT_SEC` | 1発話あたりの最小間隔 | `60` |
| `COMPANION_PERIODIC_INTERVAL_SEC` | 定期発話の基準秒 | `240`（±60） |
| `WATCHER_SCREEN_DIFF_THRESHOLD` | 画面変化しきい値 | `12.0` |
| `WATCHER_ACTIVE_INTERVAL_SEC` | アクティブ時周期 | `3` |
| `WATCHER_IDLE_INTERVAL_SEC` | アイドル時周期 | `10` |

既存の `VOICEVOX_HOST`, `VOICEVOX_SPEAKER`, `VOICEVOX_ENGINE_PATH`, `ZOMBIE_DETECTION_ENABLED`（→ 削除）, `DISABLE_FUNYA_WATCHER` と共存。

### 7.3 ディレクトリ作成

- `data/companion_samples/` — Vision LLM 入力の保存先（運用するかは `03_open_questions.md`）
- `models/` or `trained_models/companion/` — GGUF / ONNX モデルファイル配置（.gitignore 追加）

---

## 8. 検証計画

### 8.1 Step ごとの検証

各 Step の DoD を満たしたうえで、以下の横断シナリオを実施:

1. **起動→終了シナリオ**: VOICEVOX 起動 → 立ち絵表示 → companion ロード完了 → 自発発話 → 終了時 VRAM 解放
2. **ゲームフルスクリーンシナリオ**: 7DTD / Factorio などフルスクリーンゲーム起動 → watcher がウィンドウタイトル変化を検知 → companion unload（選択時） → ゲーム終了 → reload
3. **長時間放置シナリオ**: 4時間放置、メモリリーク・VRAM 漏れの監視
4. **VOICEVOX 停止→復帰シナリオ**: VOICEVOX 再起動中に companion が発話しようとしても落ちない

### 8.2 実測すべき数値

- 起動時間（main.py 起動 → 最初の発話まで）
- アイドル時 CPU 使用率
- アイドル時 VRAM 占有
- 推論レイテンシ（画像 → 発話開始まで）
- 1時間あたり発話回数
- 発話の重複率

---

## 9. ロールバック方針

各 Step で問題が出た場合の戻し方:

- Step 1 で `pydantic 2.9` 移行が詰まる → 2.4 系のまま維持、watcher / companion 実装はこの制約下で
- Step 3 で llama-cpp-python の 5070 対応 wheel が未提供 → ONNX Runtime GenAI + Phi-3.5-Vision に切替（4日程度の追加作業）
- Step 4 で VRAM が予算オーバー → 3B モデルに降格、または必要時ロード方式へ切替
- Step 5 で発話品質が期待未満 → プロンプトチューニング 2週間、それでも届かなければモデル差し替え

---

## 10. 付録: アーキテクチャ判断メモ

### 10.1 Python 側完結 vs Electron 側キャプチャ

**結論: Python 側完結**

- Vision LLM 推論が Python プロセス内 → 画面を直接 `np.ndarray` で渡すのが最短
- 既存 mss 実績あり
- Electron 経由は IPC Base64 往復でオーバーヘッド

### 10.2 差分検知方式

**結論: OpenCV absdiff 2段フィルタ（初期）**

- pHash (imagehash) は動画再生中の常時差分 > 0 問題で生しきい値判定に向かない
- absdiff は軽量、単純、デバッグ容易
- 3 枚移動平均で「急変1回」と「継続的な動き」を区別
- アスペクト比変化でウィンドウ切替を別カテゴリ化

### 10.3 配置の根拠

- `backend/app/modules/watcher/` 新設 → zombie 破棄後に名前の因縁がない、責務 clear
- `funya_watcher/` 拡張 → 非推奨（入力監視と画面監視で依存パッケージが違い凝集下がる）
- `zombie/` リネーム → 非推奨（git 履歴追跡が困難）

---

以上が移行素案。Step 1 着手前に `03_open_questions.md` の核心判断 5 項目を確定させること。
