import { defineConfig } from 'vite';
import { resolve } from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  root: 'frontend', // 開発サーバーのルートディレクトリを変更
  base: './', // 相対パスでビルドするために必要
  preload: {
    entry: 'frontend/src/main/preload/preload.js',
  },
  main: {
    entry: 'frontend/src/main/index.mjs',
  },
  css: {
    devSourcemap: true,
    // CSSモジュールのロード問題を解決するための設定
    postcss: {},
    preprocessorOptions: {
      css: {
        charset: false
      }
    }
  },

  // Electron統合のためのサーバー設定
  server: {
    port: 5173,
    strictPort: true,
    watch: {
      usePolling: true,
      interval: 100
    },
    hmr: {
      overlay: false, // HMRオーバーレイを無効化（Electronウィンドウで表示崩れを防ぐ）
      protocol: 'ws',
      host: 'localhost',
      port: 5174,
      clientPort: 5174,
      timeout: 5000
    }
  },

  // エイリアスの設定（相対パスを@付きのパスで置き換え可能に）
  resolve: {
    alias: {
      '@features': resolve(__dirname, 'frontend/src/features'),
      '@shared': resolve(__dirname, 'frontend/src/shared'),
      '@core': resolve(__dirname, 'frontend/src/core'),
      '@ui': resolve(__dirname, 'frontend/src/ui'),
      '@emotion': resolve(__dirname, 'frontend/src/emotion'),
      '@voice': resolve(__dirname, 'frontend/src/voice'),
      '@renderer': resolve(__dirname, 'frontend/src/renderer'),
    },
    extensions: ['.mjs', '.js', '.ts', '.jsx', '.tsx', '.json', '.css']
  },

  // Electronでの使用に適した設定
  build: {
    outDir: 'dist', // ルートからの相対パスになるよう調整
    emptyOutDir: true,
    // アセットのインライン化サイズを調整（CSSが適切に処理されるように）
    assetsInlineLimit: 0,
    // CSSを別ファイルとして抽出するためのオプション
    cssCodeSplit: true,
    // ビルド設定
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'frontend/index.html')
      },
      output: {
        assetFileNames: 'assets/[name].[ext]'
      }
    }
  }
}); 