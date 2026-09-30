import path from 'path';
import fs from 'fs';
import { execFileSync } from 'child_process';
import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';
import { PUBLIC_PAGES } from './constants/publicPages';
import { applyPageHead, buildSitemapXml, prerenderFilePath, resolveLastmod } from './utils/seoHead';

/**
 * SEO وقت البناء — بعد أن يكتب `vite build` ملف `dist/index.html`:
 * `dist/<route>/index.html` لكل صفحة في `constants/publicPages.ts` بعنوانها ووصفها
 * وcanonical وog:url الخاصة (Googlebot يقرأ HTML الخام قبل JS)، و`dist/sitemap.xml`
 * بـ`lastmod` = آخر commit مسّ مكوّن الصفحة (وإلا يوم البناء).
 * استبدالٌ نصّي بلا متصفّح headless: البناء على سيرفر بنواة واحدة و3.8GB.
 * إضافةٌ لا سكربت منفصل: الـCI يبني على Node 20 الذي لا يشغّل `.ts` مباشرةً،
 * وVite يحزم هذا الملف وما يستورده.
 */
function seoBuildPlugin(): Plugin {
  let outDir = '';
  const gitLastDate = (file: string): string | null => {
    try {
      return execFileSync('git', ['log', '-1', '--format=%cs', '--', file], { cwd: __dirname, encoding: 'utf8' });
    } catch {
      return null;
    }
  };
  return {
    name: 'ktra-seo-prerender',
    apply: 'build',
    configResolved(config) {
      outDir = path.resolve(config.root, config.build.outDir);
    },
    closeBundle() {
      const template = fs.readFileSync(path.join(outDir, 'index.html'), 'utf8');
      const buildDate = new Date();
      const entries = PUBLIC_PAGES.map((page) => {
        const target = path.join(outDir, prerenderFilePath(page.path));
        fs.mkdirSync(path.dirname(target), { recursive: true });
        fs.writeFileSync(target, applyPageHead(template, page));
        return { loc: page.canonical, lastmod: resolveLastmod(gitLastDate(page.component), buildDate) };
      });
      fs.writeFileSync(path.join(outDir, 'sitemap.xml'), buildSitemapXml(entries));
      console.info(`[seo] ${entries.length} صفحات عامة مصيَّرة مسبقاً + sitemap.xml`);
    },
  };
}

export default defineConfig(() => {
    return {
      server: {
        // 3000 يبقى الافتراضي لـ`npm run dev` العادي؛ ومتغيّر PORT يسمح لمشغّلٍ
        // خارجي أن يعيّن بورتاً حرّاً حين يكون 3000 مشغولاً. CORS لا ينكسر:
        // `core/settings.py` يسمح لأيّ بورت على localhost في وضع التطوير.
        port: Number(process.env.PORT) || 3000,
        host: '0.0.0.0',
        allowedHosts: ['ktra-pro.tech', 'www.ktra-pro.tech', '187.124.164.58', 'localhost'],
      },
      preview: {
        port: 3000,
        host: '0.0.0.0',
        allowedHosts: ['ktra-pro.tech', 'www.ktra-pro.tech', '187.124.164.58', 'localhost'],
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
        seoBuildPlugin(),
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
