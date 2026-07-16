import { expect, test } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const approvedUser = {
  id: "health-user",
  name: "Health Test User",
  role: "manager",
  email: "health@example.test",
  employmentStatus: "active",
  isApproved: true,
  isEmailVerified: true,
};

test("one transient health failure does not show the offline banner", async ({ page }) => {
  let healthCalls = 0;
  let confirmRetry: (() => void) | undefined;
  const retryObserved = new Promise<void>((resolve) => {
    confirmRetry = resolve;
  });
  await page.addInitScript(() => {
    localStorage.setItem("token", "health-token");
    localStorage.setItem("userId", "health-user");
    localStorage.setItem("tenantId", "1");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApiRequest =
      url.hostname === "api.smart.ktragroup.com" ||
      url.port === "8000" ||
      url.pathname.startsWith("/api/");

    if (!isApiRequest) {
      await route.continue();
      return;
    }

    if (url.pathname.endsWith("/hr/users/health-user/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(approvedUser) });
      return;
    }

    if (url.pathname.endsWith("/health/")) {
      healthCalls += 1;
      if (healthCalls === 1) {
        await route.fulfill({ status: 503, body: "temporary" });
      } else {
        confirmRetry?.();
        await route.fulfill({ status: 200, body: "OK" });
      }
      return;
    }

    await route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto("/dashboard");
  await retryObserved;

  await expect(page.getByText(/تعذّر الاتصال بالخادم رغم وجود إنترنت/)).toHaveCount(0);
  expect(healthCalls).toBe(2);
});

test("confirmed API failure still shows actionable offline state", async ({ page }) => {
  let healthCalls = 0;
  let confirmSecondFailure: (() => void) | undefined;
  const twoFailuresObserved = new Promise<void>((resolve) => {
    confirmSecondFailure = resolve;
  });
  await page.addInitScript(() => {
    localStorage.setItem("token", "health-token");
    localStorage.setItem("userId", "health-user");
    localStorage.setItem("tenantId", "1");
  });

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApiRequest =
      url.hostname === "api.smart.ktragroup.com" ||
      url.port === "8000" ||
      url.pathname.startsWith("/api/");
    if (!isApiRequest) {
      await route.continue();
      return;
    }
    if (url.pathname.endsWith("/hr/users/health-user/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(approvedUser) });
      return;
    }
    if (url.pathname.endsWith("/health/")) {
      healthCalls += 1;
      if (healthCalls === 2) confirmSecondFailure?.();
      await route.fulfill({ status: 503, body: "unavailable" });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto("/dashboard");
  await twoFailuresObserved;

  await expect(page.getByText(/تعذّر الاتصال بالخادم رغم وجود إنترنت/)).toBeVisible();
  await expect(page.locator('button[title*="مسح كاش المتصفح"]')).toBeVisible();
  expect(healthCalls).toBe(2);
});
