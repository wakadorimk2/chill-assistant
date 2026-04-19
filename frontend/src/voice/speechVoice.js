/**
 * speechVoice.js
 * VOICEVOX音声合成エンジンとの通信および音声再生を担当するモジュール
 */

import { logDebug, logError } from '@core/logger.js';

// AudioContextのシングルトンインスタンス
let audioContext = null;

// 音声再生中フラグ
let isPlaying = false;

// 音声キャッシュ（AudioBufferをキャッシュするように変更）
const audioCache = new Map();
const CACHE_MAX_SIZE = 20; // キャッシュの最大エントリ数

// 重複実行防止用の変数
let lastSpeechText = '';
let lastSpeechTimestamp = 0;
const DUPLICATE_SPEECH_THRESHOLD = 500; // ミリ秒単位での重複防止時間閾値

// 音量設定（0.0〜1.0）
let volume = localStorage.getItem('voiceVolume') !== null
    ? parseFloat(localStorage.getItem('voiceVolume'))
    : 1.0;

/**
 * AudioContextの初期化
 * @returns {AudioContext} 初期化されたAudioContext
 */
function getAudioContext() {
    if (!audioContext) {
        try {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            logDebug('AudioContextを初期化しました');
        } catch (err) {
            logError(`AudioContext初期化エラー: ${err.message}`);
            return null;
        }
    }
    return audioContext;
}

/**
 * キャッシュにエントリを追加する
 * @param {string} cacheKey - キャッシュキー
 * @param {AudioBuffer} audioBuffer - デコード済み音声データ
 */
function addToCache(cacheKey, audioBuffer) {
    // キャッシュが最大サイズに達している場合、最も古いエントリを削除
    if (audioCache.size >= CACHE_MAX_SIZE) {
        const oldestKey = audioCache.keys().next().value;
        audioCache.delete(oldestKey);
        logDebug(`キャッシュから古いエントリを削除: ${oldestKey}`);
    }

    // キャッシュに追加
    audioCache.set(cacheKey, audioBuffer);
    logDebug(`デコード済み音声データをキャッシュに追加: ${cacheKey}`);
}

/**
 * キャッシュキーを生成する
 * @param {string} text - 合成するテキスト
 * @param {string} emotion - 感情
 * @param {number} speakerId - 話者ID
 * @returns {string} キャッシュキー
 */
function generateCacheKey(text, emotion, speakerId) {
    return `${speakerId}_${emotion}_${text}`;
}

/**
 * AudioBufferを再生する関数
 * @param {AudioBuffer} audioBuffer - 再生する音声データ（デコード済みAudioBuffer）
 * @returns {Promise<boolean>} 再生が完了したらtrueを返す
 */
async function playAudioBuffer(audioBuffer) {
    try {
        const context = getAudioContext();
        if (!context) return false;

        // 再生中の場合は前の再生を停止
        if (isPlaying) {
            logDebug('前の音声再生を停止します');
            stopCurrentPlayback();
        }

        // 音源ノードを作成
        const sourceNode = context.createBufferSource();
        sourceNode.buffer = audioBuffer;

        // 音量ノードを追加
        const gainNode = context.createGain();
        gainNode.gain.value = volume; // 現在の音量設定を適用

        // ノードを接続
        sourceNode.connect(gainNode);
        gainNode.connect(context.destination);

        // 再生中フラグをセット
        isPlaying = true;
        logDebug(`音声再生を開始します (音量: ${volume})`);

        // 再生開始
        sourceNode.start(0);

        // 再生終了時の処理
        return new Promise((resolve) => {
            sourceNode.onended = () => {
                isPlaying = false;
                logDebug('音声再生が完了しました');
                resolve(true);
            };

            // タイムアウト処理（万が一onendedが発火しない場合の保険）
            setTimeout(() => {
                if (isPlaying) {
                    isPlaying = false;
                    logDebug('音声再生タイムアウト処理を実行しました');
                    resolve(true);
                }
            }, audioBuffer.duration * 1000 + 500);
        });
    } catch (error) {
        isPlaying = false;
        logError(`音声再生エラー: ${error.message}`);
        return false;
    }
}

/**
 * ArrayBufferをデコードしてAudioBufferを取得する
 * @param {ArrayBuffer} audioData - デコード前の音声データ
 * @returns {Promise<AudioBuffer>} デコード済みのAudioBuffer
 */
async function decodeAudioData(audioData) {
    try {
        const context = getAudioContext();
        if (!context) throw new Error('AudioContextが初期化できません');

        // ArrayBufferをクローンして使用する（detached状態を防ぐため）
        const clonedBuffer = audioData.slice(0);
        return await context.decodeAudioData(clonedBuffer);
    } catch (error) {
        logError(`音声デコードエラー: ${error.message}`);
        throw error;
    }
}

/**
 * テキストを音声合成して再生する
 * @param {string} text - 合成するテキスト
 * @param {string} emotion - 感情
 * @param {number} speakerId - 話者ID
 * @param {AbortSignal} signal - リクエストキャンセル用のシグナル
 * @param {boolean} useCache - キャッシュを使用するかどうか
 * @returns {Promise<boolean>} 成功したかどうか
 */
export async function speakText(text, emotion = 'normal', speakerId = 8, signal = null, useCache = true) {
    try {
        // 重複実行防止処理
        const now = Date.now();
        if (text === lastSpeechText && now - lastSpeechTimestamp < DUPLICATE_SPEECH_THRESHOLD) {
            logDebug(`🛑 重複発話を検出しました: "${text.substring(0, 15)}..." (${now - lastSpeechTimestamp}ms以内の重複)`);
            return true; // 重複とみなして処理せず成功扱いで返す
        }

        // 実行情報を記録
        lastSpeechText = text;
        lastSpeechTimestamp = now;

        // キャッシュキーを生成
        const cacheKey = generateCacheKey(text, emotion, speakerId);

        // キャッシュをチェック
        if (useCache && audioCache.has(cacheKey)) {
            logDebug(`キャッシュからAudioBufferを使用: ${cacheKey}`);
            // キャッシュからAudioBufferを取得して再生
            await playAudioBuffer(audioCache.get(cacheKey));
            return true;
        }

        // バックエンドAPIのベースURLを設定
        const apiBaseUrl = 'http://127.0.0.1:8001';

        logDebug(`VOICEVOX音声合成APIを呼び出します (話者ID: ${speakerId}, 感情: ${emotion})`);

        // タイムアウト設定
        const timeoutSignal = AbortSignal.timeout(10000); // 10秒でタイムアウト

        // 複数のシグナルを組み合わせる関数
        const combineSignals = (...signals) => {
            // nullや未定義のシグナルを除外
            const validSignals = signals.filter(s => s);
            if (validSignals.length === 0) return null;
            if (validSignals.length === 1) return validSignals[0];

            const controller = new AbortController();
            const { signal } = controller;

            validSignals.forEach(s => {
                if (s.aborted) {
                    controller.abort(s.reason);
                    return;
                }

                s.addEventListener('abort', () => controller.abort(s.reason), { once: true });
            });

            return signal;
        };

        // シグナルの組み合わせ
        const combinedSignal = combineSignals(signal, timeoutSignal);

        // リクエストボディを準備
        const requestBody = {
            text: text,
            emotion: emotion,
            speaker_id: speakerId
        };

        logDebug(`リクエスト内容: ${JSON.stringify(requestBody)}`);

        // バックエンド側で音声合成＆WAVデータ取得するAPIを呼び出す
        const response = await fetch(`${apiBaseUrl}/api/voice/synthesize`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody),
            signal: combinedSignal
        });

        if (!response.ok) {
            // レスポンスのテキストを取得してエラーメッセージに含める
            const errorText = await response.text();
            logError(`バックエンドAPI呼び出し失敗: ${response.status} ${response.statusText}`);
            logError(`エラー詳細: ${errorText}`);

            // 422エラーの場合はより詳細なエラーメッセージを出力
            if (response.status === 422) {
                logError(`VOICEVOX合成エラー: リクエストデータの問題。VOICEVOXエンジンの問題を確認してください。`);
                // 開発者向けデバッグログ
                console.debug('送信したリクエスト:', JSON.stringify(requestBody, null, 2));
            }

            throw new Error(`バックエンドAPI呼び出し失敗: ${response.status} ${response.statusText}`);
        }

        // WAVデータを取得（バイナリデータとして）
        const audioData = await response.arrayBuffer();

        // 音声データをデコード
        const audioBuffer = await decodeAudioData(audioData);

        // キャッシュに追加
        if (useCache) {
            addToCache(cacheKey, audioBuffer);
        }

        // 音声再生
        await playAudioBuffer(audioBuffer);

        return true;

    } catch (error) {
        // エラーハンドリング：AbortErrorの場合は正常処理
        if (error.name === 'AbortError') {
            if (error.message === 'The operation was aborted due to timeout') {
                logDebug("⏱ 音声合成リクエストがタイムアウトしました");
            } else {
                logDebug("🎙 発話リクエストがキャンセルされました");
            }
            return false;
        }

        // ネットワークエラーの場合
        if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
            logDebug(`ネットワークエラー: バックエンドサーバーに接続できません`);
            return false;
        }

        logError(`VOICEVOX音声合成エラー: ${error.message}`);
        return false;
    }
}

/**
 * 現在再生中の音声を停止する
 */
export function stopCurrentPlayback() {
    try {
        if (audioContext && isPlaying) {
            // すべてのノードを切断
            audioContext.suspend();
            setTimeout(() => {
                audioContext.resume();
            }, 100);

            isPlaying = false;
            logDebug('音声再生を停止しました');
        }
    } catch (err) {
        logError(`音声停止エラー: ${err.message}`);
    }
}

/**
 * 現在再生中の音声を停止する (stopCurrentPlaybackのエイリアス)
 */
export function stopSpeaking() {
    return stopCurrentPlayback();
}

/**
 * VOICEVOXサーバーとの接続を確認する
 * @returns {Promise<boolean>} 接続成功したかどうか
 */
export async function checkVoicevoxConnection() {
    try {
        const apiBaseUrl = 'http://127.0.0.1:8001';

        // 接続確認用のエンドポイントを呼び出す
        const response = await fetch(`${apiBaseUrl}/api/voice/check-connection`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            },
            signal: AbortSignal.timeout(3000) // 3秒でタイムアウト
        });

        if (response.ok) {
            const data = await response.json();
            logDebug(`VOICEVOX接続確認成功: ${JSON.stringify(data)}`);
            return true;
        }

        return false;
    } catch (error) {
        logDebug(`VOICEVOX接続確認エラー: ${error.message}`);
        return false;
    }
}

/**
 * 現在音声が再生中かどうかを返す
 * @returns {boolean} 再生中かどうか
 */
export function isSpeaking() {
    return isPlaying;
}

/**
 * 音声キャッシュを全てクリアする
 */
export function clearAudioCache() {
    audioCache.clear();
    logDebug('音声キャッシュをクリアしました');
}

/**
 * 音量を設定する
 * @param {number} newVolume - 新しい音量値（0.0〜1.0）
 */
export function setVolume(newVolume) {
    // 値の範囲を0.0〜1.0に制限
    const validVolume = Math.max(0.0, Math.min(1.0, newVolume));
    volume = validVolume;

    // 設定をlocalStorageに保存
    localStorage.setItem('voiceVolume', volume.toString());

    logDebug(`音量を設定しました: ${volume}`);
    return volume;
}

/**
 * 現在の音量を取得する
 * @returns {number} 現在の音量値（0.0〜1.0）
 */
export function getVolume() {
    return volume;
} 