import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig(() => {
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
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '.'),
        }
      },
      build: {
        rollupOptions: {
          output: {
            manualChunks(id) {
              if (!id.includes('node_modules')) return undefined;
              if (/node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/.test(id)) {
                return 'vendor-react';
              }
              if (id.includes('node_modules/dexie/')) return 'vendor-offline';
              if (id.includes('node_modules/lucide-react/')) return 'vendor-icons';
              return undefined;
            },
          },
        },
      }
    };
});
