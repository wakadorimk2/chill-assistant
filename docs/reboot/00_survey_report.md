# 00 — chill-assistant リブート統合調査レポート

**作成日**: 2026-04-19
**対象ブランチ**: main
**前提**: 2025年4月に動作完成した常駐キャラアプリを、2026年4月に「ゲーム専用→汎用相棒／ローカルLLM完結」へ方向転換する前の棚卸し。コード変更は一切行わない。

> **このレポートの読み方**
> - ファイルパス・行番号はコミット `e3c9cd1` 時点での事実ベース記述。
> - 知識が不確かな事項には **【要確認】** マーク。
> - 調査過程で出た改善提案には **[提案]** マーカー。
> - モジュール単位の仕分けは `01_module_inventory.md`、実装ステップ詳細は `02_migration_plan_draft.md`、未解決点は `03_open_questions.md` に切り出してある。

---

## セクション1: リポジトリ全体構造

### 1.1 トップ階層（深さ2）

```
chill-assistant/
├── backend/                 FastAPI バックエンド
│   ├── app/
│   │   ├── config/          settings.py (VOICEVOX_HOST, SPEAKER, ENGINE_PATH)
│   │   ├── core/            app.py (FastAPI 初期化)
│   │   ├── events/          startup_handler.py / shutdown_handler.py
│   │   ├── modules/         voice / emotion / zombie / funya_watcher / ocr / llm
│   │   ├── routers/         voice, websocket, health, ocr, funya, settings
│   │   ├── schemas/         base, voice, events
│   │   ├── services/        voice.py (VoiceService), funya_state.py
│   │   └── ws/              manager.py (ConnectionManager)
│   ├── ml/                  学習用スクリプト（破棄対象）
│   ├── trained_models/      zombie_detector_v2/ (YOLOv8 重み・破棄対象)
│   ├── data/                static, temp, logs, dialogues, phrases, detections
│   ├── main.py              uvicorn エントリポイント
│   └── requirements.txt
├── frontend/                Vite + Electron
│   ├── src/
│   │   ├── core/            apiClient.js, logger.js
│   │   ├── emotion/         SpeechManager, characterController, expressionManager
│   │   ├── features/        ui/handlers (assistantImage, pawButton, layout)
│   │   ├── main/            index.mjs (Electron main), preload/
│   │   ├── renderer/        renderer.js, assistantUI.js
│   │   ├── shared/          ui/dragHelpers, handlers
│   │   ├── ui/              helpers/ (funyaBubble, uiBuilder, volumeControl), styles/
│   │   └── voice/           speechVoice.js
│   └── index.html
├── config/
│   └── config.json          アプリ設定 (window size, always-on-top)
├── tools/                   screenshot_capture.py, stop_hisyotan.ps1
├── docs/                    character-differential-system.md, system-flow.png
├── Dockerfile               backend 単体コンテナ化
├── config.json              VOICEVOX ホスト・話者設定
├── package.json             Node 依存と npm scripts
├── pyproject.toml           ruff 設定
├── requirements.txt         Python 依存
└── README.md, LICENSE
```

### 1.2 主要ファイルの規模

| ファイル | 行数 | 役割 |
|---|---|---|
| `backend/app/modules/zombie/detector_core.py` | 757 | YOLOv8 + ResNet（破棄） |
| `backend/app/modules/zombie/callbacks.py` | 571 | 検出時 WS/音声（破棄・通知パターンは参考） |
| `frontend/src/main/index.mjs` | 692 | Electron main |
| `frontend/src/renderer/renderer.js` | 655 | renderer 初期化 |
| `frontend/src/ui/helpers/funyaBubble.js` | 385 | 吹き出し表示 |
| `backend/app/routers/voice.py` | 333 | 音声合成エンドポイント |
| `frontend/src/emotion/SpeechManager/SpeechManager.js` | ~300 | VOICEVOX 合成中心クラス |
| `backend/app/modules/voice/engine.py` | 294 | VOICEVOX HTTP 呼び出し |
| `frontend/src/ui/helpers/uiBuilder.js` | 294 | UI 構築 |
| `frontend/src/ui/helpers/volumeControl.js` | 281 | 音量 UI |
| `frontend/src/main/preload/preload.js` | 260 | contextBridge API |

### 1.3 npm scripts（`package.json`）

| script | 内容 |
|---|---|
| `dev:electron` | Vite HMR + Electron 起動 |
| `dev:frontend` | Vite dev server (port 5173) |
| `dev:backend` | `DEBUG_MODE=true python -m uvicorn backend.main:app --reload --port 8000` |
| `dev:all` | `pnpm run dev:electron` |
| `build` / `pack` / `dist` | electron-builder パッケージング |

### 1.4 依存関係の3分類（概要）

詳細は `01_module_inventory.md`。ここでは全体像のみ。

- **温存**: FastAPI, uvicorn, pydantic, requests, python-dotenv, psutil, websockets, mss, pynput, pyaudio, pydub, pillow / electron, electron-builder, electron-store, node-fetch, axios, vite
- **破棄**: ultralytics, torch, torchvision, fastai, matplotlib（学習時のみ）
- **判断保留**: opencv-python, numpy, easyocr, pytesseract, pyautogui, `modules/llm/openai_client.py`（完全ローカル方針の厳格度による）

---

## セクション2: バックエンド責務マップ

### 2.1 モジュール一覧と責務

| モジュール | 入力 | 処理 | 出力 | 主要ファイル |
|---|---|---|---|---|
| `voice/engine` | テキスト | VOICEVOX HTTP (audio_query→synthesis)、キャッシュ管理 | WAV path / bytes | `engine.py` (294行) |
| `voice/voicevox_starter` | — | VOICEVOX.exe スレッド起動、ヘルスチェック | 起動成功フラグ | `voicevox_starter.py` (243行) |
| `voice/player` | WAV path | 重複チェック、非同期再生 | 再生開始 | `player.py` (103行) |
| `voice/react` | ゾンビ数/距離 | テンプレート選択（ゾンビ反応） | メッセージ辞書 | `react.py` (148行) |
| `voice/cache` | テキスト＋wav | FS 操作 | キャッシュ有無判定、パス | `cache.py` (82行) |
| `emotion/analyzer` | テキスト | 正規表現マッチング、感情判定 | 感情タイプ＋音声パラメータ | `analyzer.py` (~80行) |
| `zombie/service` | — | シングルトン制御、start/stop_monitoring | ZombieDetector | `service.py` (212行) |
| `zombie/detector_core` | フレーム | YOLO 推論、ResNet 分類 | 検出数・座標・信頼度 | `detector_core.py` (757行) |
| `zombie/callbacks` | 検出結果 | WS 通知、音声再生、デバウンス | — | `callbacks.py` (571行) |
| `zombie/frame_extractor` | 動画 | OpenCV GPU 処理 | フレーム JPG 連番 | `frame_extractor.py` (244行) |
| `zombie/monitor` | — | mss スクリーンショット取得ループ | フレーム配列 | `monitor.py` (175行) |
| `funya_watcher/funya_watcher` | pynput イベント | キーマウス操作監視、30秒閾値 | 無操作 callback 発火 | `funya_watcher.py` |
| `ocr/ocr_capture`, `ocr_text` | 画像 / テキスト | easyocr / pytesseract | 抽出テキスト | — |
| `llm/openai_client` | プロンプト | OpenAI API 呼び出し | 応答テキスト | — |
| `ws/manager` | JSON メッセージ | 接続管理、ブロードキャスト | WS 送信 | `manager.py` (143行) |
| `routers/voice` | HTTP | エンドポイント振り分け | JSON / WAV | `voice.py` (333行) |
| `routers/websocket` | WS 接続 | ping-pong、監視コマンド | JSON 通知 | `websocket.py` (283行) |

### 2.2 WebSocket メッセージスキーマ

#### サーバー → クライアント

| type | 送信元 | スキーマ |
|---|---|---|
| `system` | `manager.send_personal_message()` | `{"type":"system","data":{"message":str}}` |
| `status` | `websocket.py` | `{"type":"status","data":{"monitoring_active":bool,"server_status":str}}` |
| `pong` | `websocket.py` | `{"type":"pong","data":{"timestamp":float}}` |
| `notification` | `send_notification()` | `{"type":"notification","data":{"message":str,"messageType":str,"title":str,"importance":str,"timestamp":float,"skipAudio":bool}}` |
| `command_result` | `websocket.py` | `{"type":"command_result","command":str,"success":bool,"message":str}` |
| `speak` | `websocket.py`（監視開始時） | `{"type":"speak","text":str,"emotion":str,"display_time":int}` |

#### クライアント → サーバー

- `{"type":"ping","timestamp":float}`
- `{"type":"command","command":"status"|"start_monitoring"|"stop_monitoring"}`

> **[提案]** 新しい見張り番層用に `watcher_event` type を追加するのが自然。既存の `speak` / `notification` 型は Vision LLM 出力の配信先としてそのまま再利用できる。

### 2.3 VOICEVOX 連携経路（最重要）

#### HTTP 呼び出し箇所

| ファイル | 行 | エンドポイント | 用途 |
|---|---|---|---|
| `voice/engine.py` | 149–152 | `POST /audio_query` | 合成クエリ作成 |
| `voice/engine.py` | 181–186 | `POST /synthesis` | 音声合成 |
| `voice/engine.py` | 253–258 | `POST /audio_query` | `speak()` 内 |
| `voice/engine.py` | 272–279 | `POST /synthesis` | `speak()` 内 |
| `routers/voice.py` | 115 | `GET /version` | 接続確認 |
| `voice/voicevox_starter.py` | 47, 202 | `GET /version` | 起動確認 |

#### 設定値（`backend/app/config/settings.py`）

```
VOICEVOX_HOST    = "http://127.0.0.1:50021"
VOICEVOX_SPEAKER = 8            # 話者 ID (config.json 側でも同じ)
VOICEVOX_ENGINE_PATH = "C:\\Users\\wakad\\AppData\\Local\\Programs\\VOICEVOX\\vv-engine\\run.exe"
```

※ `voicevox_starter.py` の `default_paths` には `%LOCALAPPDATA%\Programs\VOICEVOX\...` が含まれていない。ユーザーは `.env` の `VOICEVOX_ENGINE_PATH` 経由で上書き運用している。**[提案]** `default_paths` にこのパスパターンを追加すれば `.env` なしでも動く。

#### 音声合成→再生のデータフロー

```
[WebSocket / REST 呼び出し]
  ↓
routers/voice.py : synthesize_voice()
  ↓ request.text, speaker_id, emotion
synthesize_direct()  [engine.py:105-206]
  ├─ POST /audio_query?text=...&speaker=...
  ├─ speed/pitch/intonation/volume 上書き
  └─ POST /synthesis  →  audio_data: bytes
  ↓
Response(content=audio_data, media_type="audio/wav")

--- もしくは speak() 経由 ---

speak()  [engine.py:209-294]
  ├─ is_voice_cached(text, speaker_id)
  ├─ キャッシュあり → play_voice_async(cache_path)
  └─ なし → audio_query → synthesis → save_to_cache → play_voice_async
```

#### 新しい喋り手層からの再利用エントリポイント

1. `speak_with_emotion(text, speaker_id=8, force=False, message_type="default")`
   戻り値: `(wav_path, analysis_result)`。感情分析込みで最も完全。
2. `synthesize_direct(text, speaker_id=8, emotion="normal", speed=None, ...)`
   戻り値: `Optional[bytes]`。疎結合、合成のみ・再生しない。
3. `safe_play_voice(text, speaker_id=8, speed=1.0, ...)`
   戻り値: `Optional[str]`。重複抑止付き。

**Vision LLM 出力（例「画面に青い空が見えるね」）を喋らせる最短経路**：
```python
from backend.app.modules.voice.engine import speak_with_emotion
speak_with_emotion("画面に青い空が見えるね", speaker_id=settings.VOICEVOX_SPEAKER, force=False)
```

### 2.4 zombie 検出系の依存範囲

#### ファイル一覧

```
backend/app/modules/zombie/
├── service.py            (212行)   シングルトン管理
├── detector_core.py      (757行)   YOLOv8 + ResNet
├── callbacks.py          (571行)   WS 通知 + 音声
├── frame_extractor.py    (244行)   動画→フレーム抽出
├── monitor.py            (175行)   スクリーンショット取得ループ
├── notification.py       (192行)   通知フォーマッタ
├── config.py             (120行)   ゾンビ検出設定
├── performance.py        (73行)    パフォーマンス調整
├── logger_setup.py       (67行)    ロギング
├── __init__.py           (5行)
└── ml/
    ├── infer_zombie_classifier.py
    └── train_zombie_classifier.py
```

#### 外部依存

`torch`, `ultralytics==8.0.207`, `opencv-python`, `mss`, `numpy`, `psutil`

#### 他モジュール被参照マップ

```
startup_handler.py        → zombie/service.get_zombie_service()
shutdown_handler.py       → zombie/service (stop_monitoring)
routers/websocket.py      → zombie/service (start/stop_monitoring コマンド)
routers/voice.py          → voice/react.react_to_zombie()  ※ zombie 非依存関数
```

すべて `try/except ImportError` で包まれており、**zombie/ を丸ごと削除しても致命的エラーにはならない**（エンドポイントは無効化される）。環境変数 `ZOMBIE_DETECTION_ENABLED=false` でもすでに無効化可能。

#### 流用候補（削除前に参考値として保持したい骨格）

- `zombie/monitor.py` の mss スクリーンキャプチャループ + adaptive_interval 構造
- `zombie/callbacks.py` の `send_notification()` → `manager.broadcast()` WS 配信フロー
- `detector_core.py` の `_monitor_loop()` の asyncio.CancelledError graceful 終了パターン

新設する `backend/app/modules/watcher/screen_watcher.py` は、これらを参考に 60〜100 行で書き起こせる見込み（YOLO 依存は完全に落とす）。

### 2.5 起動経路

```
main.py
  → create_application()          [app/core/app.py:23-76]
    ├─ FastAPI() 作成
    ├─ CORS ミドルウェア
    ├─ 静的ファイルマウント
    ├─ register_routers()  (health, ocr, voice, websocket, settings, funya)
    └─ register_event_handlers()
  → uvicorn.Config(host, port, reload) → server.serve()
  → startup_handler.on_startup()
    ├─ init_services()
    │   ├─ get_settings()
    │   ├─ start_voicevox_in_thread()
    │   ├─ get_voice_service()
    │   └─ FunyaWatcher 初期化 → start()  [DISABLE_FUNYA_WATCHER で分岐]
    └─ start_zombie_monitoring()    ←★ Step 1 で削除対象
        ├─ ZOMBIE_DETECTION_ENABLED チェック
        ├─ is_voicevox_ready() で VOICEVOX 待機（最大15秒）
        └─ get_zombie_service() → start_monitoring()
```

#### 起動時のグローバル状態

| 変数 | 場所 | 用途 |
|---|---|---|
| `app` (FastAPI) | `main.py:57` | ルーター・イベント管理 |
| `manager` (ConnectionManager) | `ws/manager.py:102` | WS 接続管理 |
| `_playback_state` | `services/voice.py:87` | 音声再生の重複抑止 |
| `_zombie_service` | `zombie/service.py:16` | ゾンビ監視サービス |
| `voicevox_process` | `voicevox_starter.py:20` | VOICEVOX プロセス |
| `_voicevox_ready` | `voicevox_starter.py:25` | VOICEVOX 準備フラグ |

#### バックグラウンドタスク

1. VOICEVOX 起動スレッド（`threading.Thread(daemon=True)`）
2. ゾンビ監視 asyncio task（★ 削除対象）
3. FunyaWatcher 監視スレッド（pynput）
4. 音声再生（`asyncio.create_task`）

---

## セクション3: フロントエンド責務マップ

### 3.1 Electron の三層

#### Main プロセス `frontend/src/main/index.mjs` (692行)

- ウィンドウ生成: `frame: false, transparent: true`、`setAlwaysOnTop(true, 'screen-saver')`
- Python バックエンド起動・ヘルスチェック（SIGTERM/SIGKILL 管理、`.env` 読み込み）
- IPC ハンドラ: `set-always-on-top`, `quit-app`, `start-window-drag` ほか
- CSP: 開発と本番で切り分け、`connect-src` に `ws://127.0.0.1:*` 許可済み（line 550 付近）

#### Preload `frontend/src/main/preload/preload.js` (260行)

contextBridge 公開 API:
- `electron.ipcRenderer.{send, on, invoke}`
- `electron.theme` (isDarkMode 検出)
- `electronAPI.quitApp()`
- `electronAPI.speakText(text, emotion)`
- `electronAPI.changeSecretaryExpression(expr)`
- `electronAPI.playAudio(data, opts)` / `stopAudio()`
- `electronAPI.resolveAssetPath(path)`
- `speechManagerBridge.waitForReady(timeout)` — 前コミット `634a86b` で追加。renderer の speechManager 初期化完了まで待機させる仕掛け

#### Renderer 起動経路

`index.html` → `renderer/renderer.js` → CSS ロード → `initAssistantUI` → DOM 構築 → 立ち絵表示 → ウェルカムメッセージ → `window.speechManager` 登録 → 背景演出

### 3.2 モジュール責務

| モジュール | 責務 | 主要ファイル |
|---|---|---|
| `core/` | API 通信、ログ | `apiClient.js` (91), `logger.js` (47) |
| `emotion/` | キャラ音声・表情制御 | `characterController.js` (270), `expressionManager.js` (212), `speechManager.js` (53 互換ラッパー) |
| `emotion/SpeechManager/` | 音声合成・再生 | `SpeechManager.js`, `speakCore.js`, `voicevoxClient.js` |
| `voice/` | VOICEVOX 連携・Web Audio | `speechVoice.js` (~280) |
| `features/ui/handlers/` | UI イベント | `assistantImageHandler.js` (156), `pawButtonHandler.js` (180+) |
| `shared/ui/` | 共通 UI | `dragHelpers.js` (47) |
| `ui/helpers/` | UI 構築・表示制御 | `uiBuilder.js` (294), `funyaBubble.js` (385), `volumeControl.js` (281), `speechBridge.js` (184) |
| `ui/styles/` | CSS | main.css, base/, components/, animations/ |
| `main/` | Electron main | `index.mjs` (692), `preload.js` (260) |
| `renderer/` | renderer 初期化 | `renderer.js` (655), `assistantUI.js` (~200) |

### 3.3 キャラクター描画系（温存最優先）

#### 立ち絵表示

- `ui/helpers/assistantImage.js` : `showAssistantImage()` が `#assistantImage` の src を `/assets/images/secretary_*.png` に設定。画像ロード完了時に `assistant-image-loaded` イベント発火。
- `features/ui/handlers/assistantImageHandler.js` : click で 30% 確率「ふにゃモード」（SFX + SURPRISED 表情）、70% でランダムセリフ + ランダム表情。800ms クールタイム。

#### 表情差分

`emotion/characterDictionary.json` に定義：
- 表情 8種: `DEFAULT, HAPPY, SURPRISED, SERIOUS, SLEEPY, RELIEVED, SMILE, ANGRY`
- ポーズ 6種: `NEUTRAL, ARMSCROSSED, SEIZA, POINTING_01〜05`
- エフェクト: `ZZZ, BLUSH, SWEAT, NONE`
- 命名規則: `funya_[EXPRESSION]_[POSE]_[EXTRA].png`

`emotion/expressionManager.js` (212行) `setExpression(expression)` が URL 構築 `/assets/images/funya_${tag}_NEUTRAL_NONE.png?t=${timestamp}`（キャッシュ回避）。`.talking` クラスで口パク。

#### 吹き出し

`ui/helpers/funyaBubble.js` (385行) `showFunyaBubble(text, emotion)`：
- 自動非表示（テキスト長で調整、デフォルト 5秒）
- 見守りモード: 30秒間隔で `/api/funya/status` ポーリング → ランダムメッセージ表示
- `keepBubbleVisibleFlag` で自動非表示無効化可能
- 旧 `.speech-bubble` は `display:none, z-index:-999` で無効化済み（互換リダイレクトのみ）

#### 肉球ボタン

`features/ui/handlers/pawButtonHandler.js` :
- 左クリック: `handlePawButtonClick()` → ホルドモード（**YOLO/ゾンビ連動だが汎用版では破棄予定**）
- 右クリック: `handlePawButtonRightClick()` → 設定パネル表示
- 500ms デバウンス

#### ドラッグ移動

`shared/ui/dragHelpers.js` (47行) `setupDragBehavior(element)` : 5px 移動で `start-window-drag` を IPC send、Electron 側で `draggable-region` 対応。

### 3.4 バックエンド連携

#### REST

| エンドポイント | 呼び出し元 | 用途 |
|---|---|---|
| `GET /` | `index.mjs` (checkBackendConnection) | ヘルスチェック |
| `GET /api/settings/all` | `apiClient.js` | 全設定取得 |
| `POST /api/settings/update` | `apiClient.js` | 設定更新 |
| `GET /api/funya/status` | `funyaBubble.js` | 見守り状態 |
| `/api/voicevox/*` | `speechVoice.js`, `voicevoxClient.js` | 音声合成 |

#### WebSocket

Frontend 側の WS クライアント実装の全貌は調査時点で完全には掴めなかった **【要確認】**。`renderer.js` および `SpeechManager` 経由で `speak` メッセージを受けているものと推定される。Step 1 の疎通確認時に再検証予定。

### 3.5 音声再生経路（コミット 634a86b の文脈）

```
立ち絵クリック
  ↓ features/ui/handlers/assistantImageHandler.js:109
  ↓ クールタイム確認 (800ms)
speakRandomLine()
  ↓ resolveSpeechManager(3000)
  ↓   ├─ window.speechManager || window.SpeechManager 即座チェック
  ↓   ├─ window.speechManagerBridge.waitForReady()  ← preload.js で公開
  ↓   ├─ window.speechManagerReady Promise race
  ↓   └─ 100ms 間隔ポーリング
manager.speakWithObject({text, emotion, type})
  ↓
SpeechManager (emotion/SpeechManager/SpeechManager.js)
  ├─ lastSpokenText + 500ms デバウンス
  ├─ VOICEVOX API 呼び出し (speaker_id=8)
  ├─ 5回再試行、3秒間隔
  └─ AudioBuffer キャッシュ (最大20)
Web Audio API → AudioContext → BufferSource → GainNode → destination
```

同時に `showBubble(text)` で吹き出し、`setExpression` で表情切替。

---

## セクション4: キャラクター・世界観資産

### 4.1 立ち絵・音声アセット

メディアファイル合計: 調査時点で 27 ファイル検出（いずれも YOLO 学習用グラフ・訓練サンプル）。立ち絵 PNG・BGM・効果音の実体は **git 追跡外** か別途管理されている模様 **【要確認】**。

検出ファイルの配置:

| パス | 枚数 | 種別 |
|---|---|---|
| `backend/trained_models/zombie_detector_v2/` | 16 | 学習グラフ・train_batch / val_batch |
| `backend/ml/` | 3 | confusion_matrix, training_history, sample_images |
| `backend/app/modules/zombie/ml/` | 2 | confusion_matrix, training_history |
| `docs/` | 1 | system-flow.png |

> **[提案]** 2026年4月時点で立ち絵・効果音の実運用配置を再調査する必要あり。Step 1 で `.gitignore` と運用パスを再確認。

### 4.2 VOICEVOX 設定

`config.json`（ルート）:
```json
{
  "host": "http://127.0.0.1:50021",
  "speaker_id": 8
}
```

`config/config.json`: アプリ名「秘書たん」、ウィンドウ 1280×720 透明フレームレス常時前面。

#### 音声パラメータプリセット（`emotion/analyzer.py` 抽出・7 種）

| プリセット | pitch | intonation | speed |
|---|---|---|---|
| 通常 | 0.00 | 1.00 | 1.00 |
| にこにこ | +0.06 | 1.30 | 1.05 |
| 警戒・心配 | -0.03 | 0.90 | 0.95 |
| びっくり | +0.12 | 1.50 | 1.20 |
| やさしい | -0.06 | 1.10 | 0.90 |
| 眠そう | -0.09 | 0.80 | 0.80 |
| 不安・怯え | -0.05 | 0.85 | 0.90 |

### 4.3 セリフ辞書の所在

| 場所 | 用途 | 件数 |
|---|---|---|
| `frontend/src/emotion/emotionHandler.js:15-24` | ランダムセリフ | 8件 |
| `frontend/src/features/ui/handlers/assistantImageHandler.js:9-18` | 肉球ボタン用ランダム | (重複含む) |
| `backend/app/modules/funya_watcher/funya_watcher.py:37-43` | 見守りモード無操作時 | 5件 |

代表例:
- 「おつかれさま〜…ぎゅってしてあげたい気分なの」(tone: soft)
- 「ここにいるからね。ひとりじゃないよ」(tone: normal)
- 「ふにゃ、今日はのんびりしよ！」(tone: soft)
- 「……ふにゃ？だいじょうぶ？🐾」(funya mode)

これらは Step 5 で companion のプロンプト few-shot 例に移植してキャラ声を引き継ぐ。

### 4.4 Dockerfile / クラウド分岐

- Dockerfile: Python 3.11-slim、uvicorn 8080 port、OpenCV/easyocr/pyaudio/pytesseract/ffmpeg 同梱
- docker-compose.yml は存在しない
- クラウド環境判定: 環境変数 `DISABLE_FUNYA_WATCHER` で pynput import を回避（コミット `ee8c109`）

### 4.5 FunyaWatcher

`backend/app/modules/funya_watcher/funya_watcher.py`:
- pynput の global listener（threading、daemon）でキーマウス監視
- 閾値（デフォルト 30秒）超過で `on_enter_funya_mode` callback 発火、復帰で `on_exit_funya_mode`
- デフォルトメッセージ 5 種（上記4.3）、カスタマイズ可能

新しい見張り番層の「無操作シグナル」ソースとしてそのまま使える。新 watcher は画面変化検知に集中し、FunyaWatcher とは並列配置する方針。

---

## セクション5: 二層構造への移行設計素案（要旨）

詳細は `02_migration_plan_draft.md`。ここでは結論だけ。

### 5.1 全体アーキ

```
┌──── Electron (frontend) ────┐
│ 立ち絵 / 吹き出し / 肉球    │
│ SpeechManager + expression  │
└────────▲────────────────────┘
         │ WebSocket ({type:"speak"})
┌────────┴──── FastAPI (backend) ──────┐
│ voice/engine.speak_with_emotion (温存)│
│          ▲                            │
│          │ generated text + emotion   │
│ ┌────────┴─────────────┐              │
│ │  companion service   │ ← 喋り手層   │
│ │  (Vision LLM runtime)│              │
│ └────────▲─────────────┘              │
│          │ WatcherEvent (asyncio.Queue)│
│ ┌────────┴─────────────┐              │
│ │  watcher service     │ ← 見張り番層 │
│ │  (mss / diff / title)│              │
│ └──────────────────────┘              │
│ 既存温存: voice, emotion, funya,       │
│          ws, ocr, voicevox_starter     │
└────────────────────────────────────────┘
```

### 5.2 見張り番層（`backend/app/modules/watcher/` 新設）

- 周期: アクティブ 3s / アイドル 10s / ふにゃモード中 30s
- 検知シグナル 4種:
  1. 画面大変化（mss + cv2.absdiff、240×135 縮小、しきい値 ~12.0）
  2. フォアグラウンドウィンドウ変化（pywin32 `GetForegroundWindow` + `GetWindowText`）
  3. ユーザ無操作（既存 FunyaWatcher の状態を参照）
  4. 音量スパイク（WASAPI loopback、フェーズ2送り）
- 出力: `asyncio.Queue[WatcherEvent]` に enqueue
- VRAM 0、CPU 目標 <5%

### 5.3 喋り手層（`backend/app/modules/companion/` 新設）

- 入力: WatcherEvent + キャプチャ画像
- モデル第1候補: **Qwen2.5-VL 7B (GGUF Q4_K_M, ~6GB VRAM)** via llama-cpp-python
- 第2候補: **Phi-3.5-Vision** via ONNX Runtime GenAI
- 起動モード: イベント駆動 + 2〜5分タイマー駆動
- レート制限: 1分1発話、同種イベント 2分クールダウン
- 出力: 日本語 40字以内のテキスト + emotion タグ

### 5.4 既存 VOICEVOX 層への接続

- MVP: companion から直接 `voice/engine.speak_with_emotion()` を関数呼び出し
- 後段（Step 4）: `asyncio.Queue` ベースの `speech_bus` にリファクタ。watcher / companion / funya / 将来の他モジュールが全部ここに enqueue、単一 consumer が重複チェック + VOICEVOX ready 待ちを一箇所にまとめる。

### 5.5 実装フェーズ（5段階、各 DoD 付き）

1. 破棄フェーズ（zombie 削除、依存更新、起動疎通）
2. watcher 骨格（キャプチャ + 差分 + ウィンドウ監視）
3. companion 骨格（LLM ロード + デバッグエンドポイント）
4. watcher ↔ companion 接続 + speech_bus リファクタ
5. 定期発話 + セリフ辞書 few-shot 移植

詳細は `02_migration_plan_draft.md`。

---

## セクション6: 破棄 / 温存 / 改修 / 保留 仕分け概要

詳細は `01_module_inventory.md`。ここでは分類ごとの代表項目のみ。

### ✅ 温存（無改修）

- `backend/app/modules/voice/` 全体（engine, voicevox_starter, player, cache, presets）
- `backend/app/modules/emotion/analyzer.py`
- `backend/app/modules/funya_watcher/funya_watcher.py`
- `backend/app/ws/manager.py`
- `backend/app/modules/ocr/` （用途が残る場合）
- `frontend/src/emotion/` 一式（SpeechManager, expressionManager, characterDictionary.json）
- `frontend/src/ui/helpers/funyaBubble.js`
- `frontend/src/main/{index.mjs, preload/preload.js}`

### 🔧 温存＋軽く改修

- `backend/requirements.txt`: pydantic 2.4.2 → 2.9系 / fastapi 0.104 → 0.115 系移行検証、ultralytics/torch/torchvision 削除
- `backend/app/events/startup_handler.py`: `start_zombie_monitoring` 削除、watcher/companion の起動差し替え
- `backend/app/events/shutdown_handler.py`: `stop_zombie_monitoring` 削除
- `backend/app/routers/websocket.py`: `start_monitoring` / `stop_monitoring` コマンド削除、`watcher_event` 追加
- `backend/app/routers/voice.py`: `react_to_zombie` エンドポイント削除
- `backend/app/config/settings.py`: VOICEVOX 探索パスに `%LOCALAPPDATA%\Programs\VOICEVOX\vv-engine\run.exe` 追加
- `frontend/src/features/ui/handlers/pawButtonHandler.js`: ホルドモード（YOLO連動）削除

### ❌ 破棄

- `backend/app/modules/zombie/` 丸ごと（monitor.py と callbacks.py はコードスニペットを参考にしてから削除）
- `backend/trained_models/zombie_detector_v2/` 丸ごと
- `backend/ml/requirements.txt`
- `backend/app/modules/zombie/ml/` 配下の学習スクリプト
- `voice/react.py`（ゾンビ用テンプレート、汎用化で不要）

### ❓ 判断保留

- `opencv-python`, `numpy`: watcher の画像処理で必要、Vision LLM ランタイムが内包すれば削減可
- `easyocr`, `pytesseract`: OCR モジュールの去就次第
- `pyautogui`: 使用箇所未特定 **【要確認】**
- `backend/app/modules/llm/openai_client.py`: 完全ローカル厳守なら削除、フォールバック温存なら残す（`03_open_questions.md` 参照）

---

## セクション7: リスクと不確実性

### 7.1 パッケージ固定版の陳腐化（最優先）

2025年4月スナップショットを 2026年4月の Python/Node 環境で動かす際の具体的リスク:

| パッケージ | 現在 | 想定移行先 | リスク |
|---|---|---|---|
| **pydantic** | 2.4.2 | 2.9系 | `BaseSettings` が `pydantic-settings` に分離。`backend/app/config` が壊れる高確率。**最初のブロッカー** |
| **fastapi** | 0.104.1 | 0.115系 | `@app.on_event("startup")` が deprecation warning。現行 `startup_handler.py` はそのままだと警告、将来的には `asynccontextmanager` へ移行推奨 |
| **numpy** | 1.24.3 | 2.x 系 | OpenCV 4.10+ が numpy 2.x 前提化 **【要確認】**、Python 3.12 環境だと強制される |
| **torch** | 2.1.0 | — | 破棄対象だが、VOICEVOX 側が torch に依存していないことを Step 1 で確認必要 |

**対策**: Step 1 で `uv pip compile` or `pip-compile` により 2026年4月時点のロックを作り直す。

### 7.2 VOICEVOX のハードコードパス

`voice/voicevox_starter.py` の `default_paths` にユーザー環境 (`%LOCALAPPDATA%\Programs\VOICEVOX\vv-engine\run.exe`) が含まれていない。現状は `.env` の `VOICEVOX_ENGINE_PATH` で逃げているが、**[提案]** `default_paths` にこのパターンを追加すれば `.env` なし環境でも動く。1 行追加で済む。

### 7.3 ONNX Runtime GenAI の Windows + CUDA 12.x 成熟度 **【要確認】**

- 2025年末時点で Phi-3.5-Vision の公式サンプルは整備済み。
- ただし Windows 向け wheel の Provider デフォルトが `cuda` ではなく `dml` (DirectML) になっているケースあり。DirectML 経由だと CUDA の 6〜7 割の速度 **【要確認】**
- 本番構成では Execution Provider を明示的に `["CUDAExecutionProvider"]` に固定する運用が必要

### 7.4 llama-cpp-python の Blackwell 対応 **【要確認】**

- RTX 5070 は Blackwell アーキ（sm_120 相当）
- llama-cpp-python の CUDA wheel が 2026年4月時点で sm_120 をサポートしているか未確認
- ソースビルド必要になる可能性あり（CUDA Toolkit インストール + `CMAKE_ARGS="-DLLAMA_CUDA=on"` で wheel ビルド）

### 7.5 Qwen2.5-VL 7B GGUF の vision projector **【要確認】**

- llama.cpp mainline への vision 対応は段階的。Qwen2.5-VL の vision projector 層が完全にマージされているか要実測
- 場合によっては `ggml-org/llama.cpp` ではなく別フォーク（例: `gguf-vl`）を使う必要あり

### 7.6 pynput / mss の Windows 11 挙動

- **pynput**: UAC 昇格プロセス（管理者として起動されたゲーム等）のキーマウス入力は global listener から拾えない → 「無操作」誤判定。既知制約、Step 5 でログに明示化。
- **mss**: HDR 有効モニタで色空間が BGRA と異なるビット深度になる可能性 **【要確認】**。DRM 保護コンテンツ（Netflix 等）は真っ黒にキャプチャされる → むしろ仕様として望ましい（プライバシー保護）
- **マルチモニタ**: 既存 `monitor = sct.monitors[1]` はプライマリのみ。Vision LLM には「フォアグラウンドウィンドウのある物理モニタ」を渡したい。`window_watcher` 側で `GetForegroundWindow` → `MonitorFromWindow` → mss インデックスへマップする3ホップが必要。

### 7.7 フロントエンド側の不確定要素

- WS クライアント実装の全貌が調査時点で完全には確認できていない **【要確認】**。Step 1 の疎通確認で `{type:"speak"}` 配送経路を再検証。
- CSP で `connect-src` に `ws://127.0.0.1:*` は許可済み（`main/index.mjs:550` 付近）

### 7.8 VRAM 予算

RTX 5070 の 12GB は「Vision LLM + VOICEVOX + Electron + 作業中のアプリ/ゲーム」で共有される。安全マージンを取ると Vision LLM に使えるのは 7〜8GB 程度。Qwen2.5-VL 7B-4bit (~6GB) が実質上限。

### 7.9 モデル選定の不確定性（Step 3 前に実測で潰す）

1. llama-cpp-python CUDA wheel の sm_120 対応
2. Qwen2.5-VL 7B-GGUF の vision projector 完全動作
3. 日本語出力品質の 3 モデル横並び比較（同一プロンプト、30 サンプル）
4. ONNX Runtime GenAI の Windows CUDA Provider 対応（DirectML 強制の可能性）

---

## 付録A: コードと README の乖離

ルート `README.md` は 260行。2025年4月時点で以下の記述があるが、2026年時点のコード状態とは一部ズレている:

- 「`ZOMBIE_DETECTION_ENABLED=false` デフォルト」→ コードは既にこの方針で動作、README と整合
- 「YOLO 削除」→ コミット `f999cc8` で一部削除されたが、`requirements.txt` の `ultralytics` 記載と `backend/trained_models/zombie_detector_v2/` は残存。Step 1 で整理対象
- 「`assets/images/` に立ち絵」→ 実ファイルがコミット対象外の可能性あり、Step 1 で再確認

`docs/character-differential-system.md` は 2025年4月の立ち絵表情設計書。`characterDictionary.json` と整合。

`CLAUDE.md` はルートに未設置。

---

## 付録B: 直近コミット時系列（重要 10 件）

| ハッシュ | 日付 | 内容 |
|---|---|---|
| `e3c9cd1` | 2026-02-05 | chore: stop tracking generated voice wav cache |
| `ee8c109` | 2025-12-06 | FunyaWatcher をクラウド環境で import しないよう変更 |
| `f999cc8` | 2025-12-06 | yolo 系の行を削除 |
| `5c84652` | 2025-12-06 | Dockerfile を追加 |
| `634a86b` | 2025-11-26 | Ensure assistant image click reliably triggers speechManager (preload bridge + casing fix) |
| `a9a411b` | 2025-11-26 | fix: build volume UI safely and ensure character click hooks run |
| `571b634` | 2025-04-09 | assistantImageHandler.js / uiEventHandlers.js 新規作成 |
| `7b64f7b` | 2025-04-09 | feat: UI layout management & mouse event handling |
| `d0d68d6` | 2025-04-09 | メインウィンドウフレーム非表示、透明効果追加 |
| `9f72f38` | 2025-04-09 | 開発モード CSP 設定削除、Vite サーバー読み込み追加 |

2025年4月: UI 基盤完成 → 2025年11月: 音声再生フロー修正 → 2025年12月: YOLO削除・Docker化・クラウド対応 → 2026年2月: キャッシュ追跡停止（現時点）。

---

以上が統合レポート本文。モジュール仕分けは `01_module_inventory.md`、実装ステップは `02_migration_plan_draft.md`、未解決判断は `03_open_questions.md` を参照。
