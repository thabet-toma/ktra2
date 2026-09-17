import { defineConfig, devices } from '@playwright/test';

/* متغيّرُ PORT نفسُه الذي يقرؤه `vite.config.ts`: بورت 3000 مع
   `reuseExistingServer` يعني أن تشغيلاً من نسخة عملٍ ثانية (worktree) يختبر
   بصمتٍ خادمَ نسخةٍ أخرى إن كان 3000 مشغولاً بها. */
const PORT = Number(process.env.PORT) || 3000;
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 1,
  workers: 1,
  reporter: 'html',
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
