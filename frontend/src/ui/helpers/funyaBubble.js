/**
 * funyaBubble.js
 * ふにゃ見守りモード時の吹き出し表示を制御するモジュール
 */

import { logDebug } from '../../core/logger.js';

// 2026-04-27: backend funya_watcher が SpeechBus 経由で発話・broadcast するため
// frontend 側の自前ポーリング + 自前メッセージリスト + speak() 呼び出しは廃止。
// 吹き出し UI は WS の {type:"speak"} 受信時に showFunyaBubble() を直接叩く形になった。

const MESSAGES = [
    '……ふにゃ？ だいじょうぶ？',
    'ひとやすみ、しよっか🐈️',
];

// 状態管理
let bubbleElement = null;
let textElement = null;
let timeout = null; // 自動非表示タイマー用

// 最後に表示したテキストとタイムスタンプ（重複防止用）
let lastDisplayedText = '';
let lastDisplayedTime = 0;

// 吹き出しの自動非表示を無効にするフラグ
let keepBubbleVisibleFlag = false;

/**
 * ランダムなメッセージを取得
 * @returns {string} ランダムなメッセージ
 */
function getRandomMessage() {
    const index = Math.floor(Math.random() * MESSAGES.length);
    return MESSAGES[index];
}

/**
 * 吹き出し要素を作成
 * @returns {HTMLElement} 吹き出し要素
 */
function createBubbleElement() {
    // 既に存在する場合は作成しない
    if (document.getElementById('funyaBubble')) {
        return document.getElementById('funyaBubble');
    }

    // 吹き出し要素
    const bubble = document.createElement('div');
    bubble.id = 'funyaBubble';
    bubble.className = 'funya-bubble hide';

    // テキスト要素
    const text = document.createElement('div');
    text.id = 'funyaText';
    text.className = 'funya-text';

    // メッセージを設定
    const message = document.createElement('span');
    message.innerHTML = `<span class="funya-icon">🐾</span>${getRandomMessage()}`;
    text.appendChild(message);

    // 要素を組み立て
    bubble.appendChild(text);
    document.body.appendChild(bubble);

    return bubble;
}

/**
 * ふにゃ吹き出しの位置を立ち絵に合わせて更新する
 */
function updateFunyaBubblePosition() {
    const assistantImage = document.getElementById('assistantImage');
    const funyaBubble = document.getElementById('funyaBubble');

    if (!assistantImage || !funyaBubble) return;

    // 立ち絵の位置情報を取得
    const imageRect = assistantImage.getBoundingClientRect();
    const windowHeight = window.innerHeight;

    // 画面が小さい場合は上部に配置、それ以外は立ち絵の頭上に配置
    if (windowHeight < 600) {
        funyaBubble.style.top = '10px';
        funyaBubble.style.bottom = 'auto';
        funyaBubble.style.right = '10px';
    } else {
        funyaBubble.style.bottom = `${window.innerHeight - imageRect.top + 20}px`;
        funyaBubble.style.top = 'auto';
        funyaBubble.style.right = `${window.innerWidth - imageRect.right + 50}px`;
    }
}

// updateBubbleVisibility はポーリング廃止と共に削除 (2026-04-27)。
// 吹き出し表示は WS 経由で showFunyaBubble() を呼ぶ形になっている。

/**
 * 任意のメッセージを表示する吹き出し.
 * 音声再生は backend SpeechConsumer (winsound) が担当するためここでは行わない.
 * @param {string} text 表示するテキスト
 * @param {number} duration 表示時間（ミリ秒）デフォルトは5000ms
 * @param {boolean} _withVoice 互換のため受け取るが未使用 (backend が発話する)
 * @param {string} _emotion 互換のため受け取るが未使用
 * @returns {HTMLElement} 吹き出し要素
 */
export function showFunyaBubble(text, duration = 5000, _withVoice = false, _emotion = 'normal') {
    // 重複防止：直近で同じテキストが表示されていたら無視する（5秒以内）
    const now = Date.now();
    if (text === lastDisplayedText && now - lastDisplayedTime < 5000) {
        logDebug(`🛑 重複表示を防止しました: "${text?.substring(0, 15)}..." (前回から${now - lastDisplayedTime}ms)`);
        return bubbleElement;
    }

    // 表示テキストとタイムスタンプを記録
    lastDisplayedText = text || '';
    lastDisplayedTime = now;

    // 既存のタイマーをクリア
    if (timeout) {
        clearTimeout(timeout);
        timeout = null;
    }

    if (!bubbleElement) {
        bubbleElement = createBubbleElement();
        textElement = document.getElementById('funyaText');
    }

    // テキストを設定
    let displayText;
    if (text) {
        displayText = text;
        textElement.innerHTML = `<span class="funya-icon">🐾</span>${text}`;
    } else {
        displayText = getRandomMessage();
        textElement.innerHTML = `<span class="funya-icon">🐾</span>${displayText}`;
    }

    // 吹き出しを表示
    bubbleElement.classList.remove('hide');
    bubbleElement.classList.add('show');

    // 立ち絵の位置に合わせて吹き出しの位置を調整
    updateFunyaBubblePosition();

    logDebug(`ふにゃ吹き出しを表示: ${displayText || 'ランダムメッセージ'}`);

    // 指定時間後に自動的に非表示（強制表示モードでない場合のみ）
    if (!keepBubbleVisibleFlag) {
        timeout = setTimeout(() => {
            hideFunyaBubble();
        }, duration);
    } else {
        logDebug('🔒 吹き出しの自動非表示が無効化されているため、タイマーをセットしません');
    }

    return bubbleElement;
}

/**
 * 吹き出しを非表示にする
 */
export function hideFunyaBubble() {
    // 強制表示モードの場合は非表示にしない
    if (keepBubbleVisibleFlag) {
        logDebug('🔒 吹き出しの自動非表示が無効化されているため、非表示処理をスキップします');
        return;
    }

    if (bubbleElement) {
        bubbleElement.classList.remove('show');
        bubbleElement.classList.add('hide');
        logDebug('ふにゃ吹き出しを非表示');
    }

    if (timeout) {
        clearTimeout(timeout);
        timeout = null;
    }
}

/**
 * ふにゃ見守りモード初期化 (互換 API).
 * 旧実装の自動ポーリング & 自動発話は backend SpeechBus 経由に置き換わったため
 * 立ち絵位置監視のセットアップだけ残してある.
 */
export function startFunyaWatchingMode() {
    logDebug('ふにゃ見守りモード初期化 (ポーリング無効、位置監視のみ)');
    setupPositionObserver();
}

/**
 * 立ち絵の位置変更を監視する設定
 */
function setupPositionObserver() {
    // ResizeObserverを追加し、画面サイズ変更時に吹き出しの位置を調整
    const resizeObserver = new ResizeObserver(() => {
        if (document.getElementById('funyaBubble')?.classList.contains('show')) {
            updateFunyaBubblePosition();
        }
    });
    resizeObserver.observe(document.body);

    // MutationObserverを使用して立ち絵の位置変更を監視
    const assistantObserver = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.type === 'attributes' &&
                (mutation.attributeName === 'style' || mutation.attributeName === 'class')) {
                if (document.getElementById('funyaBubble')?.classList.contains('show')) {
                    updateFunyaBubblePosition();
                }
            }
        });
    });

    // 立ち絵の監視を開始
    setTimeout(() => {
        const imgElement = document.getElementById('assistantImage');
        if (imgElement) {
            assistantObserver.observe(imgElement, { attributes: true });
        }
    }, 100);

    // カスタムイベントリスナーを追加
    window.addEventListener('assistant-image-loaded', () => {
        // 立ち絵が読み込まれたときに吹き出しの位置を更新
        if (document.getElementById('funyaBubble')) {
            updateFunyaBubblePosition();
            logDebug('🔄 カスタムイベントで吹き出し位置を更新しました');
        }
    });
}

/**
 * ふにゃ見守りモードのポーリングを停止 (互換 API、現状ノーオペ).
 */
export function stopFunyaWatchingMode() {
    logDebug('ふにゃ見守りモード停止 (no-op)');
    hideFunyaBubble();
}

/**
 * 吹き出しの自動非表示を無効にする
 * 設定UIが表示されている間など、吹き出しを表示し続けたい場合に使用
 */
export function keepBubbleVisible() {
    keepBubbleVisibleFlag = true;
    logDebug('🔒 吹き出しの自動非表示を無効化しました');

    // 既存のタイマーをクリア
    if (timeout) {
        clearTimeout(timeout);
        timeout = null;
    }
}

/**
 * 吹き出しの自動非表示を有効に戻す
 */
export function allowBubbleHide() {
    keepBubbleVisibleFlag = false;
    logDebug('🔓 吹き出しの自動非表示を再有効化しました');
}

// 旧 DOMContentLoaded 自動起動は廃止 (backend funya_watcher 側に集約)。