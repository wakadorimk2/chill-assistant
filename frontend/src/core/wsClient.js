/**
 * wsClient.js
 * backend (FastAPI /ws) との WebSocket 接続を管理する小さなクライアント.
 *
 * Step 4 で SpeechConsumer が `{type: "speak", data: {text, emotion, source, ...}}`
 * を broadcast するようになったので、その受信側を提供する.
 *
 * 設計メモ:
 * - 音声再生は backend 側 (winsound) で行う前提. frontend は吹き出し UI 表示のみ
 * - 接続切れ時は指数バックオフで自動再接続 (最大 10s)
 * - on(type, handler) で複数ハンドラを登録可能
 */

const API_HOST = (typeof window !== 'undefined' && window.electron?.apiHost) || '127.0.0.1';
const API_PORT = 8001;
const WS_URL = `ws://${API_HOST}:${API_PORT}/ws`;

class WsClient {
  constructor(url) {
    this.url = url;
    this.handlers = new Map();
    this.socket = null;
    this.shouldReconnect = true;
    this.reconnectDelay = 1000;
    this.maxReconnectDelay = 10000;
  }

  /**
   * 指定の type メッセージのハンドラを登録する.
   * @param {string} type - メッセージタイプ (例: "speak", "watcher_event", "notification")
   * @param {(payload: object) => void} handler - 受信時に呼び出されるコールバック (payload は parse 済 JSON)
   */
  on(type, handler) {
    if (!this.handlers.has(type)) this.handlers.set(type, []);
    this.handlers.get(type).push(handler);
  }

  connect() {
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    console.log(`🔌 WebSocket 接続試行: ${this.url}`);
    let socket;
    try {
      socket = new WebSocket(this.url);
    } catch (err) {
      console.error('WebSocket 生成失敗:', err);
      this._scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.onopen = () => {
      console.log('✅ WebSocket 接続確立');
      this.reconnectDelay = 1000;
    };

    socket.onmessage = (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch (e) {
        console.warn('WebSocket: JSON parse 失敗', event.data);
        return;
      }
      const type = payload?.type;
      if (!type) return;
      const handlers = this.handlers.get(type);
      if (!handlers || handlers.length === 0) return;
      for (const h of handlers) {
        try {
          h(payload);
        } catch (e) {
          console.error(`WebSocket ハンドラ例外 (type=${type}):`, e);
        }
      }
    };

    socket.onerror = (err) => {
      console.error('WebSocket エラー:', err);
    };

    socket.onclose = () => {
      console.warn('WebSocket 切断');
      this.socket = null;
      if (this.shouldReconnect) this._scheduleReconnect();
    };
  }

  _scheduleReconnect() {
    const delay = this.reconnectDelay;
    console.log(`⏳ WebSocket 再接続を ${delay}ms 後にスケジュール`);
    setTimeout(() => this.connect(), delay);
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.socket) {
      try {
        this.socket.close();
      } catch (e) {
        console.warn('WebSocket close 例外:', e);
      }
      this.socket = null;
    }
  }
}

const wsClient = new WsClient(WS_URL);

if (typeof window !== 'undefined') {
  window.wsClient = wsClient;
}

export default wsClient;
