# 01 — モジュール仕分け表

**作成日**: 2026-04-19
**目的**: chill-assistant 全モジュール・主要ファイルを「温存 / 軽く改修 / 破棄 / 保留」に分類。`02_migration_plan_draft.md` の実装ステップ着手前に、どこを触るかの全景を一目で掴むためのチェックリスト。

**凡例**:
- ✅ **温存**: そのまま使う。触る必要なし。
- 🔧 **軽く改修**: 既存のまま残すが、zombie 連動や依存更新で数十行レベルの手入れが入る。
- ❌ **破棄**: ファイル丸ごと削除。
- ❓ **保留**: 今回の方針で去就が未決定。`03_open_questions.md` で判断を仰ぐ。

---

## 1. バックエンド

### 1.1 `backend/app/modules/voice/`

| ファイル | 分類 | 理由 / 作業内容 |
|---|---|---|
| `engine.py` (294行) | ✅ 温存 | 3つの再利用エントリ (`speak_with_emotion`, `synthesize_direct`, `safe_play_voice`) が今回の中核。無改修 |
| `voicevox_starter.py` (243行) | 🔧 軽く改修 | `default_paths` に `%LOCALAPPDATA%\Programs\VOICEVOX\vv-engine\run.exe` を追加（1行）**[提案]** |
| `player.py` (103行) | ✅ 温存 | 重複チェック + 非同期再生、そのまま再利用 |
| `cache.py` (82行) | ✅ 温存 | ただしコミット `e3c9cd1` で生成キャッシュは git 追跡外、運用パスのみ確認 |
| `react.py` (148行) | ❌ 破棄 | ゾンビ反応専用テンプレート。汎用版では不要 |
| `presets.py` | ✅ 温存 | 音声プリセット定義、汎用にも使える |

### 1.2 `backend/app/modules/emotion/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `analyzer.py` (~80行) | ✅ 温存 | テキスト→感情分類 + 7種音声パラメータプリセット。Vision LLM 出力の感情タグ付けに直結再利用可 |

### 1.3 `backend/app/modules/zombie/` **丸ごと破棄**

| ファイル | 分類 | 備考 |
|---|---|---|
| `service.py` (212行) | ❌ 破棄 | シングルトン制御、YOLO 前提 |
| `detector_core.py` (757行) | ❌ 破棄 | YOLOv8 + ResNet 依存 |
| `callbacks.py` (571行) | ❌ 破棄 | **削除前に `send_notification` → `manager.broadcast` の配線パターンを参考値として記録** |
| `frame_extractor.py` (244行) | ❌ 破棄 | 動画処理、YOLO 向け |
| `monitor.py` (175行) | ❌ 破棄 | **削除前に mss ループ + adaptive_interval 構造を新 `watcher/screen_watcher.py` の雛形として引用** |
| `notification.py` (192行) | ❌ 破棄 | ゾンビ通知フォーマッタ |
| `config.py` (120行) | ❌ 破棄 | ゾンビ検出設定 |
| `performance.py` (73行) | ❌ 破棄 | パフォーマンス調整（流用可能だが依存過多、watcher で書き直す） |
| `logger_setup.py` (67行) | ❌ 破棄 | ロギング、独立再設定 |
| `__init__.py` | ❌ 破棄 | |
| `ml/infer_zombie_classifier.py` | ❌ 破棄 | ResNet 推論 |
| `ml/train_zombie_classifier.py` | ❌ 破棄 | ResNet 学習 |

### 1.4 `backend/app/modules/funya_watcher/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `funya_watcher.py` | ✅ 温存 | pynput 監視 + 30秒閾値 + callback。新 watcher 層と並列配置、状態参照のみ |

### 1.5 `backend/app/modules/ocr/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `ocr_capture.py` | ❓ 保留 | OCR を残すかの判断は `03_open_questions.md`。Vision LLM で代替可能なら削除 |
| `ocr_text.py` | ❓ 保留 | 同上 |

### 1.6 `backend/app/modules/llm/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `openai_client.py` | ❓ 保留 | 「完全ローカル厳守」なら削除、フォールバック温存なら残す。判断は `03_open_questions.md` |

### 1.7 `backend/app/events/`

| ファイル | 分類 | 理由 / 作業 |
|---|---|---|
| `startup_handler.py` | 🔧 軽く改修 | `start_zombie_monitoring` の呼び出し削除（数十行）。watcher/companion の起動コードに差し替え |
| `shutdown_handler.py` | 🔧 軽く改修 | `stop_zombie_monitoring` 削除、companion のモデル unload 追加 |
| `dispatcher.py` | ✅ 温存 | イベント配送基盤、汎用 |

### 1.8 `backend/app/routers/`

| ファイル | 分類 | 理由 / 作業 |
|---|---|---|
| `voice.py` (333行) | 🔧 軽く改修 | `react_to_zombie` エンドポイント (line 230-286) 削除 |
| `websocket.py` (283行) | 🔧 軽く改修 | `command == "start_monitoring"` / `"stop_monitoring"` の分岐削除 (line 104-275)。将来的に `watcher_event` 種別の broadcast を追加 |
| `health.py` | ✅ 温存 | `GET /` ヘルスチェック |
| `ocr_router.py` | ❓ 保留 | OCR 去就に連動 |
| `funya.py` | ✅ 温存 | `/api/funya/status` は `funyaBubble.js` が依存 |
| `settings.py` | ✅ 温存 | `/api/settings/*` |

### 1.9 `backend/app/schemas/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `base.py` | ✅ 温存 | 基底モデル |
| `voice.py` | ✅ 温存 | `VoiceSynthesisRequest` ほか |
| `events.py` | 🔧 軽く改修 | `ZombieDetectedEvent` を削除、`WatcherEvent` を追加 |

### 1.10 `backend/app/services/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `voice.py` | ✅ 温存 | `VoiceService`, `_playback_state`（重複抑止） |
| `funya_state.py` | ✅ 温存 | FunyaWatcher 状態管理、新 watcher が参照 |

### 1.11 `backend/app/ws/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `manager.py` (143行) | ✅ 温存 | `ConnectionManager`、`broadcast`、`send_notification`。そのまま再利用 |

### 1.12 `backend/app/config/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `settings.py` | 🔧 軽く改修 | pydantic 2.9 移行時に `BaseSettings` 参照パス変更が高確率。VOICEVOX 探索パス追加 |

### 1.13 `backend/app/core/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `app.py` | ✅ 温存 | FastAPI 初期化、ルーター登録 |
| `logger.py` | ✅ 温存 | |
| `init.py` | ✅ 温存 | |

### 1.14 `backend/` 直下

| ファイル | 分類 | 作業 |
|---|---|---|
| `main.py` | ✅ 温存 | uvicorn エントリ |
| `debug_start.py` | ✅ 温存 | デバッグ起動、破棄検討は任意 |
| `test_api.py` / `test_voice.py` | ✅ 温存 | 動作試験、価値あり |
| `requirements.txt` | 🔧 軽く改修 | 詳細は §3 |

### 1.15 `backend/ml/`, `backend/trained_models/`

| パス | 分類 | 作業 |
|---|---|---|
| `backend/ml/requirements.txt` | ❌ 破棄 | fastai / torch / torchvision / matplotlib、学習用。汎用化で不要 |
| `backend/ml/*.py` | ❌ 破棄 | ResNet 学習スクリプト |
| `backend/ml/*.png` | ❌ 破棄 | 学習グラフ、リポジトリから削除 |
| `backend/trained_models/zombie_detector_v2/` 全16ファイル | ❌ 破棄 | YOLOv8 重み + 学習グラフ。リポジトリから削除 |

### 1.16 新設（ファイルは作らない、レポート内言及のみ）

| パス | 役割 |
|---|---|
| `backend/app/modules/watcher/service.py` | Watcher サービス、`asyncio.Queue` 所有 |
| `backend/app/modules/watcher/screen_watcher.py` | mss + cv2.absdiff メインループ |
| `backend/app/modules/watcher/window_watcher.py` | pywin32 フォアグラウンド監視 |
| `backend/app/modules/watcher/capture.py` | mss / dxcam 切替アダプタ **[提案]** |
| `backend/app/modules/watcher/events.py` | `WatcherEvent` dataclass |
| `backend/app/modules/companion/runtime.py` | llama-cpp-python / ONNX Runtime GenAI ラッパ |
| `backend/app/modules/companion/prompts.py` | システムプロンプト + few-shot（既存セリフ辞書を移植） |
| `backend/app/modules/companion/service.py` | タイマー + Queue consumer + レート制限 |

---

## 2. フロントエンド

### 2.1 `frontend/src/emotion/`（キャラ中核、温存最優先）

| ファイル | 分類 | 理由 |
|---|---|---|
| `SpeechManager/SpeechManager.js` | ✅ 温存 | VOICEVOX 中心クラス、重複 500ms デバウンス、5回再試行 |
| `SpeechManager/speakCore.js` | ✅ 温存 | |
| `SpeechManager/voicevoxClient.js` | ✅ 温存 | |
| `speechManager.js` (53行) | ✅ 温存 | 互換ラッパー |
| `characterController.js` (270行) | ✅ 温存 | 立ち絵制御 |
| `characterDictionary.json` | ✅ 温存 | 表情 8種 × ポーズ 6種 × エフェクトのメタデータ |
| `expressionManager.js` (212行) | ✅ 温存 | 表情差分切替、口パクアニメ |
| `audioReactor.js` | ✅ 温存 | 音声反応 |
| `emotionHandler.js` | 🔧 軽く改修 | ランダムセリフ 8件は残し、tone 制御を analyzer と整合化可能 |

### 2.2 `frontend/src/ui/helpers/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `assistantImage.js` (68行) | ✅ 温存 | `#assistantImage` 表示 |
| `funyaBubble.js` (385行) | ✅ 温存 | 吹き出し + 見守り 30秒ポーリング |
| `uiBuilder.js` (294行) | ✅ 温存 | |
| `volumeControl.js` (281行) | ✅ 温存 | |
| `speechBridge.js` (184行) | ✅ 温存 | |

### 2.3 `frontend/src/features/ui/handlers/`

| ファイル | 分類 | 理由 / 作業 |
|---|---|---|
| `assistantImageHandler.js` (156行) | ✅ 温存 | 立ち絵クリック反応、コミット `634a86b` の修正後 |
| `pawButtonHandler.js` (180+行) | 🔧 軽く改修 | 左クリックの「ホルドモード」（YOLO連動）削除。右クリック設定パネルは温存 |
| `layoutManager.js` | ✅ 温存 | |

### 2.4 `frontend/src/shared/ui/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `dragHelpers.js` (47行) | ✅ 温存 | 5px ドラッグ判定 |
| `handlers/*` | ✅ 温存 | |

### 2.5 `frontend/src/main/`（Electron）

| ファイル | 分類 | 理由 |
|---|---|---|
| `index.mjs` (692行) | ✅ 温存 | Electron main、透過最前面、CSP、バックエンド起動 |
| `preload/preload.js` (260行) | ✅ 温存 | contextBridge、`speechManagerBridge.waitForReady` |
| `preload/paw-preload.js` | ✅ 温存 | |
| `utils/backend.js`, `voicevox.js`, `logger.js` | ✅ 温存 | |
| `windows/pawWindow.js` | ✅ 温存 | |

### 2.6 `frontend/src/renderer/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `renderer.js` (655行) | ✅ 温存 | 初期化、演出、`window.speechManager` 登録 |
| `assistantUI.js` | ✅ 温存 | |

### 2.7 `frontend/src/voice/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `speechVoice.js` (~280行) | ✅ 温存 | VOICEVOX API 呼び出し、AudioBuffer キャッシュ |

### 2.8 `frontend/src/core/`

| ファイル | 分類 | 理由 |
|---|---|---|
| `apiClient.js` (91行) | ✅ 温存 | REST ラッパー |
| `logger.js` (47行) | ✅ 温存 | |

### 2.9 `frontend/src/ui/styles/`

すべて ✅ 温存。CSS 全体（main.css, base/, components/, animations/）

---

## 3. 依存パッケージ（Python `backend/requirements.txt`）

### 温存

| パッケージ | 現バージョン | 用途 |
|---|---|---|
| FastAPI | 0.104.1 | メインフレーム、2.9 系に要更新検証 |
| uvicorn | 0.23.2 | ASGI |
| Pydantic | 2.4.2 | 2.9 系に要更新。`BaseSettings` が `pydantic-settings` に分離 |
| requests | 2.31.0 | VOICEVOX HTTP |
| python-dotenv | 1.0.0 | `.env` |
| psutil | 5.9.6 | プロセス管理 |
| websockets | 11.0.3 | WS |
| mss | 9.0.1 | スクリーンキャプチャ |
| pynput | 1.7.6 | FunyaWatcher |
| pyaudio | 0.2.13 | 音声デバイス |
| pydub | 0.25.1 | 音声ファイル |
| pillow | 10.1.0 | 画像 |
| python-multipart | 0.0.6 | HTTP multipart |

### 破棄

| パッケージ | 現バージョン | 理由 |
|---|---|---|
| ultralytics | 8.0.207 | YOLO 専用 |
| torch | 2.1.0 | YOLO / ResNet、5070 対応にも不適合（最低 2.6+ 相当が必要） |
| torchvision | — | YOLO / ResNet |
| fastai | 2.7.12 | ResNet 学習 |
| matplotlib | — | 学習可視化 |

### 判断保留

| パッケージ | 保留理由 |
|---|---|
| opencv-python | watcher の差分検知で必要、Vision LLM ランタイムに同梱されるなら削減可 |
| numpy | 画像処理の基本、2.x 移行要検証 |
| easyocr | OCR 機能の去就 → `03_open_questions.md` |
| pytesseract | 同上 |
| pyautogui | 使用箇所未特定 **【要確認】** |

### 新規追加候補（`02_migration_plan_draft.md` 参照）

- `llama-cpp-python` (CUDA wheel / ソースビルド) — 第一候補ランタイム
- `onnxruntime-genai` — 第二候補ランタイム
- `pywin32` — window_watcher 用
- （必要なら）`dxcam` — capture.py のアダプタ内で選択可能に

---

## 4. 依存パッケージ（Node `package.json`）

### 温存

- `electron` (^24.8.8)
- `electron-log` (^5.3.3)
- `electron-store` (^8.1.0)
- `@electron/remote` (^2.1.2)
- `node-fetch` (^3.3.2)
- `axios` (^1.8.4)
- `iconv-lite` (^0.6.3)

### 開発ツール（温存）

- `vite` (^6.2.4)
- `electron-builder` (^24.9.1)
- `concurrently`, `cross-env`, `eslint`, `prettier`

### 判断保留

- `@vitejs/plugin-react` — React 未使用なら削除可、UI のモダン化検討時に残す

---

## 5. 静的アセット・設定ファイル

| パス | 分類 | 作業 |
|---|---|---|
| `config.json` (ルート) | ✅ 温存 | VOICEVOX 設定 |
| `config/config.json` | ✅ 温存 | アプリ設定 |
| `Dockerfile` | 🔧 軽く改修 | ultralytics/torch 削除に連動して依存整理、llama-cpp-python は GPU 前提なのでコンテナ起動時の扱いは要検討 |
| `pyproject.toml` | 🔧 軽く改修 | Python target `py310` → `py311` or `py312` 要検討 **【要確認】** |
| `README.md` | 🔧 軽く改修 | 方針転換後に書き直し（実装完了後） |
| `docs/character-differential-system.md` | ✅ 温存 | 2025年設計書、`characterDictionary.json` と整合 |
| `docs/system-flow.png` | ✅ 温存 | |
| `.cursorrules` | ✅ 温存 | 開発時ルール |
| `tools/screenshot_capture.py` | ❌ 破棄 | ゲームプレイ 5秒間隔キャプチャ、今回の watcher で代替 |
| `tools/stop_hisyotan.ps1` | ✅ 温存 | 終了スクリプト |

---

## 6. サマリ（ボリューム目安）

| 分類 | 件数 | 推定削除行数 |
|---|---|---|
| ❌ 破棄（zombie モジュール） | 12ファイル | ~2,500行 |
| ❌ 破棄（学習モデル・グラフ） | 20+ファイル（バイナリ中心） | — |
| ❌ 破棄（tools/screenshot_capture） | 1ファイル | ~100行 |
| 🔧 軽く改修（backend） | 8ファイル | 削除+追加合わせ ~200行 |
| 🔧 軽く改修（frontend） | 2ファイル | ~50行 |
| ✅ 温存（backend コア） | 20+ファイル | 変更なし |
| ✅ 温存（frontend コア） | 30+ファイル | 変更なし |
| ❓ 保留 | 4項目 | `03_open_questions.md` で判断 |
| ✨ 新設（watcher + companion） | 8ファイル | ~500行（Step 2-5 で書く） |

実質的に **「破棄の方がコード行数ベースでは多く、追加は 500 行程度で済む」** 見立て。温存するキャラ中核部分には一切手を入れないので、リスクは低い。
