import { expect, test } from "@playwright/test";

// API mocks must observe startup requests; a previously installed PWA worker can bypass routing.
test.use({ serviceWorkers: "block" });

test("authenticated shell does not wait for non-critical activity data", async ({ page }, testInfo) => {
  let activityResponseFinished = false;
  await page.addInitScript(() => {
    localStorage.setItem("token", "e2e-token");
    localStorage.setItem("userId", "e2e-user");
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

    if (url.pathname.endsWith("/hr/users/e2e-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "e2e-user",
          name: "Performance Test User",
          role: "manager",
          email: "performance@example.test",
          employmentStatus: "active",
          isApproved: true,
          isEmailVerified: true,
        }),
      });
      return;
    }

    // Simulate a slow compatibility/local-data endpoint. It must not gate the app shell.
    if (url.pathname.includes("/mapper/activityStatus/e2e-user/")) {
      await new Promise((resolve) => setTimeout(resolve, 5_000));
      activityResponseFinished = true;
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
      return;
    }

    await route.fulfill({ contentType: "application/json", body: "[]" });
  });

  const startedAt = Date.now();
  await page.goto(process.env.KTRA_E2E_APP_URL || "/dashboard");
  await expect(page.getByRole("button", { name: "تسجيل الخروج" })).toBeVisible({ timeout: 8_000 });
  const shellReadyMs = Date.now() - startedAt;

  expect(activityResponseFinished).toBe(false);
  testInfo.annotations.push({ type: "shell-ready-ms", description: String(shellReadyMs) });
  console.info(`shell-ready-ms=${shellReadyMs}`);
  // Set a strict budget when running against the prebuilt production preview.
  const budgetMs = Number(process.env.KTRA_E2E_SHELL_BUDGET_MS || 0);
  if (budgetMs > 0) expect(shellReadyMs).toBeLessThan(budgetMs);
});

test("idle authenticated shell does not poll mapper collections every five seconds", async ({ page }) => {
  const mapperCounts = new Map<string, number>();
  await page.addInitScript(() => {
    localStorage.setItem("token", "e2e-token");
    localStorage.setItem("userId", "e2e-user");
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

    if (url.pathname.endsWith("/hr/users/e2e-user/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "e2e-user",
          name: "Idle Poll Test User",
          role: "manager",
          email: "idle-poll@example.test",
          employmentStatus: "active",
          isApproved: true,
          isEmailVerified: true,
        }),
      });
      return;
    }

    if (url.pathname.includes("/mapper/")) {
      mapperCounts.set(url.pathname, (mapperCounts.get(url.pathname) || 0) + 1);
      if (url.pathname.includes("/activityStatus/")) {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            id: "e2e-user",
            lastCheckIn: new Date().toISOString(),
            isCurrentlyActive: true,
            checkInButtonEnabled: true,
          }),
        });
        return;
      }
    }

    await route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto(process.env.KTRA_E2E_APP_URL || "/dashboard");
  await expect(page.getByRole("button", { name: "تسجيل الخروج" })).toBeVisible({ timeout: 8_000 });
  await expect.poll(() => [...mapperCounts.keys()].some((path) => path.endsWith("/mapper/users/"))).toBe(true);
  await expect.poll(() => [...mapperCounts.keys()].some((path) => path.endsWith("/mapper/tasks/"))).toBe(true);

  // Let all startup subscriptions settle, then span the former 5-second polling boundary.
  await page.waitForTimeout(500);
  const settledCounts = new Map(mapperCounts);
  await page.waitForTimeout(5_500);
  expect(mapperCounts).toEqual(settledCounts);
});
