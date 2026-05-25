import { Page } from '@playwright/test';

export async function setOffline(page: Page, offline: boolean) {
  await page.context().setOffline(offline);
  await page.evaluate((off) => {
    if (off) {
      window.dispatchEvent(new Event('offline'));
      Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    } else {
      window.dispatchEvent(new Event('online'));
      Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
    }
  }, offline);
}
