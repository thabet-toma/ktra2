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
  const healthMethods: string[] = [];
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
      const method = route.request().method();
      healthMethods.push(method);
      if (method === "HEAD") {
        await route.fulfill({ status: 503, body: "temporary" });
      } else {
        await route.fulfill({ status: 200, body: "OK" });
        confirmRetry?.();
      }
      return;
    }

    await route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto("/accounting/year-end-close");
  await retryObserved;

  await expect(page.getByText(/تعذّر الاتصال بالخادم رغم وجود إنترنت/)).toHaveCount(0);
  expect(healthMethods).toEqual(expect.arrayContaining(["HEAD", "GET"]));
});

test("confirmed API failure still shows actionable offline state", async ({ page }) => {
  const healthMethods: string[] = [];
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
      const method = route.request().method();
      healthMethods.push(method);
      await route.fulfill({ status: 503, body: "unavailable" });
      if (method === "GET") confirmSecondFailure?.();
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto("/accounting/year-end-close");
  await twoFailuresObserved;

  await expect(page.getByText(/تعذّر الاتصال بالخادم رغم وجود إنترنت/)).toBeVisible();
  await expect(page.getByRole("button", { name: "إصلاح الاتصال" })).toBeVisible();
  expect(healthMethods).toEqual(expect.arrayContaining(["HEAD", "GET"]));
});
