import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, '.', '');
    return {
      server: {
        port: 3000,
        host: '0.0.0.0',
      },
      plugins: [
        react(),
        tailwindcss(),
        VitePWA({
          registerType: 'prompt',
          strategies: 'injectManifest',
          srcDir: '.',
          filename: 'sw.ts',
          injectManifest: {
            maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
          },
          manifest: {
            name: 'نظام K.T.R.A',
            short_name: 'K.T.R.A',
            description: 'نظام متكامل لإدارة الفواتير والشحنات والاستيراد والتخليص الجمركي',
            theme_color: '#1e40af',
            background_color: '#ffffff',
            display: 'standalone',
            orientation: 'any',
            start_url: '/',
            scope: '/',
            lang: 'ar',
            dir: 'rtl',
          },
          devOptions: { enabled: false },
        }),
      ],
      define: {
        'process.env.API_KEY': JSON.stringify(env.GEMINI_API_KEY),
        'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY)
      },
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '.'),
        }
      }
    };
});
