import { test, expect } from '@playwright/test';

test('Check settings api and localstorage', async ({ page }) => {
  test.skip(process.env.LIVE_DEBUG !== '1', 'requires the live backend and is not part of the deterministic suite');
  // Login or go to the page directly if already logged in
  await page.goto('http://localhost:3000/sales/customer-payments');
  await page.waitForLoadState('networkidle');
  
  // Expose a function to collect logs
  const logs: any[] = [];
  page.on('console', msg => logs.push({ type: msg.type(), text: msg.text() }));

  // Call the APIs in the browser
  const data = await page.evaluate(async () => {
    const token = localStorage.getItem("token");
    const tenantId = localStorage.getItem("tenantId") || "1";
    const headers = {
      "Content-Type": "application/json",
      "Authorization": token ? `Token ${token}` : "",
      "X-Tenant-Id": tenantId
    };

    const pSet = await fetch("http://localhost:8000/api/logistics/purchase-settings/current/", { headers })
      .then(r => r.json()).catch(e => e.toString());
    const sSet = await fetch("http://localhost:8000/api/logistics/sales-settings/current/", { headers })
      .then(r => r.json()).catch(e => e.toString());

    return { pSet, sSet };
  });

  console.log("=== API DATA ===");
  console.log(JSON.stringify(data, null, 2));
  console.log("=== BROWSER CONSOLE LOGS ===");
  console.log(logs);
});
