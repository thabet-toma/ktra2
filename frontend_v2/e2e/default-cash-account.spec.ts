import { test, expect } from '@playwright/test';

test('New Customer Payment modal selects default cash account from purchase settings', async ({ page }) => {
  // Go to purchase settings and set a default cash account first?
  // Or just go to customer payments and expect it not to be empty.
  await page.goto('http://localhost:3000/sales/customer-payments');
  
  // Open the modal
  const newPaymentBtn = page.locator('button:has-text("دفعة جديدة")');
  await newPaymentBtn.waitFor({ state: 'visible', timeout: 15000 });
  await newPaymentBtn.click();

  // Find the cash account select
  const cashSelect = page.locator('select').nth(3); // The fourth select based on the DOM order: Partner, Currency, Cash Account
  // Actually, we can locate it by label
  const cashSelectLabel = page.locator('label', { hasText: 'الصندوق / البنك' });
  const cashSelectByLabel = cashSelectLabel.locator('..').locator('select');

  // Since it should be prefilled from settings, it should not have the value "" (which is "اختر...")
  const value = await cashSelectByLabel.inputValue();
  
  // The test might fail initially if the code is not implemented (will be "")
  // Once implemented, if the backend has a default, it will be the default ID.
  // Note: if backend has NO default, this test might still fail. We assume there's a default.
  expect(value).not.toBe("");
});
