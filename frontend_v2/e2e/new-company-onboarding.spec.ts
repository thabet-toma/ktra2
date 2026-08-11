import { expect, test } from "@playwright/test";

test.use({ serviceWorkers: "block" });

const profile = {
  id: "onboarding-user",
  name: "Onboarding User",
  role: "manager",
  email: "onboarding@example.test",
  employmentStatus: "active",
  isApproved: true,
  isEmailVerified: true,
};

async function seedAuthenticatedSession(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    if (sessionStorage.getItem("onboarding-session-seeded")) return;
    sessionStorage.setItem("onboarding-session-seeded", "true");
    localStorage.setItem("token", "onboarding-token");
    localStorage.setItem("userId", "onboarding-user");
    localStorage.setItem("tenantId", "999");
    localStorage.setItem("branchId", "88");
  });
}

test("signup renders three fields and sends only the public signup contract", async ({ page }) => {
  let payload: Record<string, unknown> | null = null;
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/hr/auth/signup/")) {
      payload = route.request().postDataJSON();
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ user: profile }) });
      return;
    }
    await route.fulfill({ status: 204, body: "" });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "إنشاء حساب جديد" }).first().click();
  const form = page.locator("form");
  await expect(form.locator("input")).toHaveCount(3);
  await form.locator('input[name="fullName"]').fill("مستخدم جديد");
  await form.locator('input[name="email"]').fill("new@example.test");
  await form.locator('input[name="password"]').fill("secret6");
  await form.getByRole("button", { name: "إنشاء الحساب" }).click();

  await expect(page.getByText("تم إنشاء حسابك بنجاح.")).toBeVisible();
  await expect.poll(() => payload).toEqual({ fullName: "مستخدم جديد", email: "new@example.test", password: "secret6" });
});

test("an authenticated user without memberships sees onboarding without the app shell", async ({ page }) => {
  await seedAuthenticatedSession(page);
  const apiPaths: string[] = [];
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    apiPaths.push(url.pathname);
    if (url.pathname.endsWith("/hr/users/onboarding-user/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(profile) });
      return;
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      await route.fulfill({ contentType: "application/json", body: "[]" });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "{}" });
  });

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "لنُنشئ شركتك الأولى" })).toBeVisible();
  await expect(page.locator("aside")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => ({ tenantId: localStorage.getItem("tenantId"), branchId: localStorage.getItem("branchId") }))).toEqual({ tenantId: null, branchId: null });
  expect(apiPaths.some((path) => /\/(accounting|inventory|logistics|partners|sales)\//.test(path))).toBe(false);
});

test("a memberships load failure shows retry instead of onboarding", async ({ page }) => {
  await seedAuthenticatedSession(page);
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    if (url.pathname.endsWith("/hr/users/onboarding-user/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(profile) });
      return;
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "server error" }) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "{}" });
  });

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "تعذّر تحميل مساحة العمل" })).toBeVisible();
  await expect(page.getByRole("button", { name: "إعادة المحاولة" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "لنُنشئ شركتك الأولى" })).toHaveCount(0);
});

test("authenticated startup keeps the selected non-default company after reload", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("token", "onboarding-token");
    localStorage.setItem("userId", "onboarding-user");
    localStorage.setItem("tenantId", "42");
  });
  const memberships = [
    {
      id: 101,
      tenant: {
        TenantID: 1,
        CompanyName: "KTRA",
        SubscriptionPlan: "Enterprise",
        Status: "Active",
        CreatedAt: "2026-07-22T00:00:00Z",
        import_enabled: false,
      },
      role: "manager",
      is_default: true,
      created_at: "2026-07-22T00:00:00Z",
      can_access_import: false,
    },
    {
      id: 102,
      tenant: {
        TenantID: 42,
        CompanyName: "الشركة الثانية",
        SubscriptionPlan: "Enterprise",
        Status: "Active",
        CreatedAt: "2026-07-22T00:00:00Z",
        import_enabled: false,
      },
      role: "manager",
      is_default: false,
      created_at: "2026-07-22T00:00:00Z",
      can_access_import: false,
    },
  ];

  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    if (url.pathname.endsWith("/hr/users/onboarding-user/")) {
      await new Promise((resolve) => setTimeout(resolve, 50));
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(profile) });
      return;
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(memberships) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto("/dashboard");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("tenantId"))).toBe("42");
  await expect(page.getByRole("button", { name: /الشركة الثانية/ }).first()).toBeVisible();
});

test("creating the first company confirms the manager membership before opening the app", async ({ page }) => {
  await seedAuthenticatedSession(page);
  let companyCreated = false;
  let createRequests = 0;
  let createPayload: Record<string, unknown> | null = null;
  const membership = {
    id: 501,
    tenant: {
      TenantID: 42,
      CompanyName: "شركة البداية",
      SubscriptionPlan: "Enterprise",
      Status: "Active",
      CreatedAt: "2026-07-22T00:00:00Z",
      import_enabled: false,
    },
    role: "manager",
    is_default: true,
    created_at: "2026-07-22T00:00:00Z",
    can_access_import: false,
  };

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();
    if (url.pathname.endsWith("/hr/users/onboarding-user/")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(profile) });
      return;
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(companyCreated ? [membership] : []),
      });
      return;
    }
    if (url.pathname.endsWith("/tenants/companies/") && request.method() === "POST") {
      createRequests += 1;
      createPayload = request.postDataJSON();
      companyCreated = true;
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(membership.tenant) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto("/dashboard");
  await page.locator('input[name="companyName"]').fill("شركة البداية");
  const navigation = page.waitForEvent("framenavigated", (frame) => frame === page.mainFrame());
  await page.getByRole("button", { name: "إنشاء الشركة والمتابعة" }).click();

  await expect.poll(() => createRequests).toBe(1);
  await expect.poll(() => createPayload).toEqual({ CompanyName: "شركة البداية" });
  await navigation;
  await expect.poll(() => page.evaluate(() => ({
    tenantId: localStorage.getItem("tenantId"),
    branchId: localStorage.getItem("branchId"),
  }))).toEqual({ tenantId: "42", branchId: null });
  await page.waitForURL("**/dashboard");
});
