import { Page } from '@playwright/test';

const OFFLINE_TEST_USER_ID = 'offline-e2e-user';

/**
 * Install the authenticated session and deterministic API responses required
 * for offline UI tests. Offline affordances live inside the authenticated app
 * shell, so visiting a protected URL without this setup only renders the
 * public landing page.
 */
export async function installAuthenticatedOfflineApp(page: Page) {
  await page.addInitScript((userId) => {
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem('token', 'offline-e2e-token');
    localStorage.setItem('userId', userId);
    localStorage.setItem('tenantId', '1');
  }, OFFLINE_TEST_USER_ID);

  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApiRequest =
      url.port === '8000' ||
      url.pathname.startsWith('/api/');

    if (!isApiRequest) {
      await route.continue();
      return;
    }

    if (url.pathname.endsWith(`/hr/users/${OFFLINE_TEST_USER_ID}/`)) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          id: OFFLINE_TEST_USER_ID,
          name: 'Offline E2E User',
          role: 'manager',
          email: 'offline@example.test',
          employmentStatus: 'active',
          isApproved: true,
          isEmailVerified: true,
        }),
      });
      return;
    }

    if (url.pathname.endsWith('/health/')) {
      await route.fulfill({ status: 200, contentType: 'text/plain', body: 'OK' });
      return;
    }

    if (url.pathname.endsWith('/dashboard/')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          deals: {
            total: 0, open: 0, shipped: 0, cleared: 0, closed: 0,
            open_value: 0, this_month: 0, status_distribution: [], recent: [],
          },
          shipments: {
            total: 0, in_transit: 0, arrived: 0, clearing: 0, cleared: 0, recent: [],
          },
          payments: { total: 0, posted: 0, total_paid: 0, paid_this_month: 0 },
          invoices: { total: 0, posted: 0, draft: 0, total_value: 0, recent: [] },
          inventory: {
            total_products: 0, in_stock: 0, low_stock: 0, out_of_stock: 0,
            inventory_value: 0, movements_this_month: 0, low_stock_items: [],
          },
          accounting: { journals_this_month: 0 },
          alerts: [],
        }),
      });
      return;
    }

    if (url.pathname.includes('/mapper/activityStatus/')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ isCurrentlyActive: true }),
      });
      return;
    }

    await route.fulfill({ contentType: 'application/json', body: '[]' });
  });
}

export async function openAuthenticatedOfflineApp(page: Page, path = '/dashboard') {
  // The shell can paint before React flushes useEffect. The initial health
  // probe is started from the same effect that registers online/offline event
  // listeners, so observing it gives us a deterministic readiness signal.
  const onlineStatusReady = page.waitForResponse(
    (response) => new URL(response.url()).pathname.endsWith('/health/'),
    { timeout: 15_000 },
  );
  await page.goto(path, { waitUntil: 'domcontentloaded' });
  await Promise.all([
    page.locator('main.app-content').waitFor({ state: 'visible', timeout: 15_000 }),
    onlineStatusReady,
  ]);
}

export async function setOffline(page: Page, offline: boolean) {
  await page.evaluate(async (off) => {
    // Consumers such as OfflineCoachmark inspect navigator.onLine inside the
    // event handler, so update it before dispatching the synthetic fallback.
    const dispatchConnectionEvent = () => {
      Object.defineProperty(navigator, 'onLine', { configurable: true, value: !off });
      window.dispatchEvent(new Event(off ? 'offline' : 'online'));
    };
    dispatchConnectionEvent();

    // React StrictMode tears down and reinstalls effects once in development.
    // Repeat after that cycle so this test fallback cannot land in the narrow
    // interval where listeners are temporarily detached.
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
    dispatchConnectionEvent();
  }, offline);
}
