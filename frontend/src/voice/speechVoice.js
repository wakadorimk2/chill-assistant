/**
 * speechVoice.js
 * 発話要求を backend (SpeechBus) に投げる薄いクライアント.
 *
 * 2026-04-27: ローカル音声合成・再生は廃止。発話は全て backend SpeechConsumer
 * に集約され、winsound 経由で再生される。frontend は enqueue するだけ。
 * volume は backend へ通らないので volume slider は当面ノーオペ。
 */

import { logDebug, logError } from '@core/logger.js';

// バックエンドの enqueue エンドポイント
const SPEECH_ENQUEUE_URL = 'http://127.0.0.1:8001/api/speech/enqueue';
const VOICEVOX_CHECK_URL = 'http://127.0.0.1:8001/api/voice/check-connection';

// 重複実行防止 (短時間の連打抑制). backend 側にも dedup あり。
let lastSpeechText = '';
let lastSpeechTimestamp = 0;
const DUPLICATE_SPEECH_THRESHOLD = 500;

// 音量設定 (現状ローカル再生していないので機能していない、後日 backend 連携予定)
let volume = localStorage.getItem('voiceVolume') !== null
    ? parseFloat(localStorage.getItem('voiceVolume'))
    : 1.0;

/**
 * 発話要求を SpeechBus に enqueue する.
 * @param {string} text - 発話テキスト
 * @param {string} emotion - VOICE_PRESETS のキー (例: '通常', 'にこにこ')
 * @param {number} _speakerId - 互換のため受け取るが未使用 (backend で settings.VOICEVOX_SPEAKER を使用)
 * @param {AbortSignal} signal - リクエストキャンセル用シグナル
 * @param {boolean} _useCache - 互換のため受け取るが未使用 (backend 側でキャッシュ管理)
 * @returns {Promise<boolean>} enqueue 成功なら true
 */
export async function speakText(text, emotion = '通常', _speakerId = null, signal = null, _useCache = true) {
    if (!text) return false;

    // 短時間連打抑制
    const now = Date.now();
    if (text === lastSpeechText && now - lastSpeechTimestamp < DUPLICATE_SPEECH_THRESHOLD) {
        logDebug(`🛑 重複発話を検出: "${text.substring(0, 15)}..." (${now - lastSpeechTimestamp}ms以内)`);
        return true;
    }
    lastSpeechText = text;
    lastSpeechTimestamp = now;

    try {
        const timeoutSignal = AbortSignal.timeout(3000);
        const finalSignal = signal
            ? AbortSignal.any([signal, timeoutSignal])
            : timeoutSignal;

        const response = await fetch(SPEECH_ENQUEUE_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text,
                emotion,
                source: 'frontend',
            }),
            signal: finalSignal,
        });

        if (!response.ok) {
            const errorText = await response.text();
            logError(`speech enqueue 失敗: ${response.status} ${response.statusText} - ${errorText}`);
            return false;
        }

        const data = await response.json();
        logDebug(`✅ speech enqueued: queued=${data.queued} qsize=${data.queue_size}`);
        return Boolean(data.queued);
    } catch (error) {
        if (error.name === 'AbortError') {
            logDebug('🎙 発話要求がキャンセル/タイムアウト');
            return false;
        }
        logError(`speech enqueue エラー: ${error.message}`);
        return false;
    }
}

/**
 * 旧 API 互換のスタブ. backend が再生しているので frontend には停止対象がない.
 * (発話を中断したい場合は backend 側に新規 endpoint を切る必要がある)
 */
export function stopCurrentPlayback() {
    logDebug('stopCurrentPlayback: backend 再生のため frontend からは停止できません (no-op)');
}

export function stopSpeaking() {
    return stopCurrentPlayback();
}

/**
 * VOICEVOX サーバーとの接続を確認する.
 */
export async function checkVoicevoxConnection() {
    try {
        const response = await fetch(VOICEVOX_CHECK_URL, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
            signal: AbortSignal.timeout(3000),
        });
        if (!response.ok) return false;
        const data = await response.json();
        logDebug(`VOICEVOX接続確認: ${JSON.stringify(data)}`);
        return Boolean(data.connected);
    } catch (error) {
        logDebug(`VOICEVOX接続確認エラー: ${error.message}`);
        return false;
    }
}

/**
 * 旧 API 互換: 現在再生中かどうか.
 * backend 側の状態は /api/speech/status で取れるが同期取得できないので false 固定.
 */
export function isSpeaking() {
    return false;
}

/**
 * 音声キャッシュクリアのスタブ. backend 側のキャッシュは管理外.
 */
export function clearAudioCache() {
    logDebug('clearAudioCache: backend キャッシュは frontend からクリアできません (no-op)');
}

/**
 * 音量設定 (現状 backend 再生のため反映されない、localStorage には保存).
 */
export function setVolume(newVolume) {
    const validVolume = Math.max(0.0, Math.min(1.0, newVolume));
    volume = validVolume;
    localStorage.setItem('voiceVolume', volume.toString());
    logDebug(`音量を設定: ${volume} (backend 再生のため現状未反映)`);
    return volume;
}

export function getVolume() {
    return volume;
}
