# Legacy Snippets — Step 2 移植用素材

Step 1（破棄フェーズ）で削除される旧 zombie 検出系のうち、Step 2（watcher モジュール新規実装）で再利用したいコード断片を抜粋保存した保管庫。

**注意**: コピペではなく、新しい watcher / companion の設計に合わせて採用する。Step 2 ではこの抜粋を参考に、gaming-agnostic（特定ゲームに依存しない）な汎用キャプチャ + 差分検知モジュールを組み立てる。

---

## 1. WebSocket broadcast パターン

秘書たん → フロントエンドへ通知を流すパターン。`ConnectionManager.broadcast()` は **Step 1 で削除せず温存する**（watcher / companion で引き続き使う）。以下はそのパターンを利用する側（削除される zombie/callbacks.py）の記述例。

### 1-A. ConnectionManager.broadcast() 本体（温存対象。参考のため転記）

**元ネタ**: `backend/app/ws/manager.py:67-98`

```python
async def broadcast(self, message: Dict[str, Any]) -> None:
    """
    接続中の全クライアントにメッセージをブロードキャストする
    """
    print(
        f"[BACKEND] WebSocketブロードキャスト開始: "
        f"{message.get('type', 'unknown')} - "
        f"接続数: {len(self.active_connections)}"
    )
    if len(self.active_connections) == 0:
        print(
            f"[BACKEND] WebSocket接続がありません！"
            f"ブロードキャストをスキップ: {message.get('type', 'unknown')}"
        )
        logger.warning(
            f"WebSocket接続がありません。ブロードキャストをスキップ: {message}"
        )
        return

    for connection in self.active_connections:
        try:
            await connection.send_json(message)
        except Exception as e:
            logger.error(f"ブロードキャスト送信エラー: {e}")
            print(f"[BACKEND] WebSocketブロードキャスト送信エラー: {str(e)}")
            continue

    logger.debug(f"ブロードキャストメッセージを送信しました: {message}")
    print(
        f"[BACKEND] WebSocketブロードキャスト完了: {message.get('type', 'unknown')}"
    )
```

### 1-B. send_notification() ラッパー（温存対象）

**元ネタ**: `backend/app/ws/manager.py:105-142`

```python
async def send_notification(
    message: str,
    message_type: str = "info",
    title: str = "通知",
    importance: str = "normal",
    skipAudio: bool = False,
) -> None:
    """
    WebSocket経由でクライアントに通知を送信

    Args:
        message: 通知メッセージ
        message_type: 通知タイプ（info, warning, error, success, ...）
        title: 通知タイトル
        importance: 重要度（normal, high, low）
        skipAudio: 音声読み上げをスキップするかどうか
    """
    current_timestamp = time.time()

    notification_data: Dict[str, Any] = {
        "type": "notification",
        "data": {
            "message": message,
            "messageType": message_type,
            "title": title,
            "importance": importance,
            "timestamp": current_timestamp,
            "skipAudio": skipAudio,
        },
    }

    await manager.broadcast(notification_data)
    logger.info(f"通知を送信: {message_type} - {message}")
```

### 1-C. 削除側：watcher イベント送信ペイロードの参考例

**元ネタ**: `backend/app/modules/zombie/callbacks.py:398-407`

`type` / `data` で階層化されたイベントペイロード構造。Step 2 の watcher でも同じ型を踏襲する想定（type は "watcher_frame" や "scene_change" などに置き換え）。

```python
# カスタム型イベント（zombie_warning）を送るケース
zombie_warning_data = {
    "type": "zombie_warning",
    "data": {"count": count, "positions": positions},
}
await manager.broadcast(zombie_warning_data)
```

汎用通知（Toast レベル）は `send_notification()` を使い、カスタム型イベントは `manager.broadcast({"type": "...", "data": {...}})` を直接呼ぶ、という使い分け。

---

## 2. mss キャプチャループ + adaptive_interval

Step 2 の watcher が画面キャプチャ + フレーム間隔調整を実装する際のベースライン。`backend/app/modules/zombie/detector_core.py` から抜粋。

### 2-A. 初期化パラメータ（adaptive な制御フィールド）

**元ネタ**: `backend/app/modules/zombie/detector_core.py:81-84`

```python
self.adaptive_interval = PERFORMANCE_SETTINGS["frame_interval"]  # 基本フレーム間隔（秒）
self.resize_factor = PERFORMANCE_SETTINGS["resize_factor"]       # リサイズ倍率 (0-1)
self.skip_ratio: float = float(PERFORMANCE_SETTINGS["skip_ratio"])  # 何フレームに1回だけ処理するか
self.cpu_threshold = PERFORMANCE_SETTINGS["cpu_threshold"]       # 高負荷判定の CPU% 閾値
```

関連: `cpu_check_interval = 10` (秒ごとに CPU チェック), `last_cpu_check_time = 0`。

### 2-B. 監視ループ本体

**元ネタ**: `backend/app/modules/zombie/detector_core.py:264-346`

```python
async def _monitor_loop(
    self,
    zombie_callback: Optional[Callable[[int, Any], Any]] = None,
    few_zombies_callback: Optional[Callable[[int, Any], Any]] = None,
    warning_zombies_callback: Optional[Callable[[int, Any], Any]] = None,
) -> None:
    """
    ゾンビ検出の非同期監視ループ
    """
    logger.info("監視ループを開始します")

    # 画面キャプチャの設定
    with mss.mss() as sct:
        # モニターの取得
        monitor = sct.monitors[1]  # プライマリーモニター

        while self.is_monitoring:
            try:
                # フレームカウントを更新
                self.frame_count += 1

                # スキップレートが設定されている場合、一部のフレームをスキップ
                if self.skip_ratio > 1 and self.frame_count % self.skip_ratio != 0:
                    await asyncio.sleep(0.1)
                    continue

                # CPU使用率を定期的にチェックし、高負荷時はパフォーマンス設定を調整
                current_time = time.time()
                if (
                    current_time - self.last_cpu_check_time
                    > self.cpu_check_interval
                ):
                    self._adjust_performance_settings()
                    self.last_cpu_check_time = current_time

                # 画面キャプチャを実行
                screenshot = await self._capture_screen(sct, monitor)
                if screenshot is None:
                    logger.warning("画面キャプチャに失敗しました")
                    await asyncio.sleep(1)
                    continue

                # === ここに watcher 固有の処理（差分検知 / Vision LLM 呼び出し）を差し込む ===
                # 旧実装ではここで YOLO 推論 + コールバックディスパッチを行っていた

                # 次のフレームまで待機
                await asyncio.sleep(self.adaptive_interval)

            except asyncio.CancelledError:
                logger.info("監視タスクがキャンセルされました")
                break
            except Exception as e:
                logger.error(f"監視ループ中にエラーが発生しました: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(2)  # エラー発生時は少し長めの待機

    logger.info("監視ループを終了しました")
```

### 2-C. CPU 負荷による adaptive 調整

**元ネタ**: `backend/app/modules/zombie/detector_core.py:348-381`

```python
def _adjust_performance_settings(self) -> None:
    """
    CPU使用率に基づいてパフォーマンス設定を調整する
    """
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)

        # 高負荷時の調整
        if cpu_percent > self.cpu_threshold:
            self.adaptive_interval = min(
                PERFORMANCE_SETTINGS["frame_interval"] * 1.5, 2.0
            )
            self.resize_factor = max(
                PERFORMANCE_SETTINGS["resize_factor"] * 0.8, 0.3
            )
            self.skip_ratio = min(PERFORMANCE_SETTINGS["skip_ratio"] + 1, 5)
            logger.info(
                f"高CPU負荷 ({cpu_percent:.1f}%)のため設定調整: "
                f"interval={self.adaptive_interval:.1f}s, "
                f"resize={self.resize_factor:.2f}"
            )
        else:
            # 通常負荷時は標準設定に戻す
            self.adaptive_interval = PERFORMANCE_SETTINGS["frame_interval"]
            self.resize_factor = PERFORMANCE_SETTINGS["resize_factor"]
            self.skip_ratio = PERFORMANCE_SETTINGS["skip_ratio"]
    except Exception as e:
        logger.error(f"パフォーマンス設定の調整中にエラー発生: {e}")
```

### 2-D. キャプチャ単体関数

**元ネタ**: `backend/app/modules/zombie/detector_core.py:383-415`

```python
async def _capture_screen(
    self, sct: mss.mss, monitor: Dict[str, int]
) -> Optional[NDArray[np.uint8]]:
    """
    画面キャプチャを行う
    """
    try:
        screenshot = sct.grab(monitor)
        img = np.array(screenshot)
        img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        # リサイズが必要なら実行
        if self.resize_factor < 1.0:
            width = int(img_bgr.shape[1] * self.resize_factor)
            height = int(img_bgr.shape[0] * self.resize_factor)
            img_bgr = cv2.resize(img_bgr, (width, height))

        return img_bgr
    except Exception as e:
        logger.error(f"画面キャプチャ中にエラーが発生: {e}")
        return None
```

### 2-E. 監視タスクのライフサイクル管理（グローバル変数パターン）

**元ネタ**: `backend/app/modules/zombie/monitor.py:15-35, 39-142`

旧実装はモジュールレベルのグローバル変数でタスクを管理していた。Step 2 では **WatcherService クラスにカプセル化** するのが望ましい。以下は構造参考。

```python
# グローバル変数（旧実装）
is_monitoring: bool = False
zombie_detector: Optional[Any] = None
zombie_monitor_task: Optional[Any] = None


def is_monitoring_started() -> bool:
    global is_monitoring, zombie_monitor_task
    return (
        is_monitoring
        and zombie_monitor_task is not None
        and not zombie_monitor_task.done()
    )


async def start_zombie_monitoring() -> Optional[Any]:
    global is_monitoring, zombie_detector, zombie_monitor_task

    if is_monitoring_started():
        return None

    # 検出器初期化
    if zombie_detector is None:
        zombie_detector = ZombieDetector(
            model_path=model_path, confidence=0.45, debug_mode=DEBUG_MODE
        )

    # 監視タスク起動
    zombie_monitor_task = await zombie_detector.start_monitoring(
        callback=_zombie_alert_callback,
        few_zombies_callback=zombie_few_alert,
        warning_zombies_callback=zombie_warning,
    )
    is_monitoring = True
    return zombie_monitor_task
```

---

## 3. Step 2 で watcher に作り直すときの設計メモ

- キャプチャループ本体は **差分検知 + Vision LLM 問い合わせ** に差し替える（YOLO を抜いた場所に Qwen3-VL-8B 呼び出しを載せる）
- `adaptive_interval` の考え方は流用するが、調整トリガーを「CPU 負荷」だけでなく「LLM 推論レイテンシ」も加味する
- プロセス名フィルタ（7DTD 優先、他ゲーム拡張可能）は新規実装
- グローバル変数ではなく `WatcherService` クラスにまとめ、lifespan から DI で注入する
- broadcast のペイロード型は新しい型名（例: `"watcher_event"`）を定義して、フロントエンドの受信側と合わせる

## 4. 破棄されたが将来検討する要素

- ResNet 分類器（ZombieClassifier）: Vision LLM で置き換え、出番なし
- `notification_manager` による同時通知数制限: Step 3 で companion 側に類似機構を作る可能性
- デバッグ画像保存: Step 1 決定で「画像本体は保存しない、メタのみ」の方針あり。流用しない
