import { expect, test } from "@playwright/test";

test.use({ serviceWorkers: "block" });

test("company member management never receives platform users", async ({ page }) => {
  let platformUsersRequests = 0;
  let mapperUsersRequests = 0;
  let membershipRole = "manager";
  const company = {
    TenantID: 73,
    CompanyName: "Privacy Company",
    SubscriptionPlan: "Enterprise",
    Status: "Active",
    CreatedAt: "2026-07-22T00:00:00Z",
    import_enabled: false,
  };
  const membership = {
    id: 901,
    tenant: company,
    role: "manager",
    is_default: true,
    created_at: "2026-07-22T00:00:00Z",
    can_access_import: false,
  };
  const managerRow = {
    membership_id: 901,
    user_id: 45,
    username: "privacy-manager",
    email: "manager@example.test",
    full_name: "Privacy Manager",
    role: "manager",
    is_default: true,
    can_access_import: false,
  };

  await page.addInitScript(() => {
    localStorage.setItem("token", "privacy-token");
    localStorage.setItem("userId", "member-privacy-user");
    localStorage.setItem("tenantId", "73");
  });

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.port === "8000" || url.pathname.startsWith("/api/");
    if (!isApi) return route.continue();

    if (url.pathname.endsWith("/hr/users/")) {
      platformUsersRequests += 1;
      return route.fulfill({ status: 403, contentType: "application/json", body: '{"detail":"Forbidden"}' });
    }
    if (url.pathname.endsWith("/mapper/users/")) {
      mapperUsersRequests += 1;
      return route.fulfill({ status: 403, contentType: "application/json", body: '{"detail":"Forbidden"}' });
    }
    if (url.pathname.endsWith("/hr/users/member-privacy-user/")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "member-privacy-user",
          name: "Privacy Manager",
          role: membershipRole === "manager" ? "manager" : "employee",
          email: "manager@example.test",
          employmentStatus: "active",
          isApproved: true,
          isEmailVerified: true,
          isSuperAdmin: false,
        }),
      });
    }
    if (url.pathname.endsWith("/tenants/companies/my-companies/")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{ ...membership, role: membershipRole }]),
      });
    }
    if (url.pathname.endsWith("/tenants/companies/73/members/")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify([managerRow]) });
    }
    return route.fulfill({ contentType: "application/json", body: "[]" });
  });

  await page.goto("/dashboard");
  await page.getByRole("button", { name: /Privacy Company/ }).dispatchEvent("click");
  // Company identity settings can refresh the switcher once after it opens;
  // dispatching the click avoids Playwright waiting on the replaced button node.
  await page.getByRole("button", { name: "إدارة الشركة (الاسم والأعضاء)" }).dispatchEvent("click");

  const identifier = page.getByLabel("البريد الإلكتروني أو اسم المستخدم");
  await expect(identifier).toBeVisible();
  await expect(page.getByText(/لا يعرض النظام حسابات المنصة ولا يقترحها تلقائياً/)).toBeVisible();
  expect(platformUsersRequests).toBe(0);
  expect(mapperUsersRequests).toBe(0);

  membershipRole = "staff";
  await page.reload();
  await page.getByRole("button", { name: /Privacy Company/ }).dispatchEvent("click");
  await expect(page.getByRole("button", { name: "إدارة الشركة (الاسم والأعضاء)" })).toHaveCount(0);
  expect(mapperUsersRequests).toBe(0);
});
