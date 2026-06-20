import { test, expect } from '@playwright/test';

test.describe('Global Back Button', () => {
  test('A clear back button is visible on the page', async ({ page }) => {
    // Navigate to the root page
    await page.goto('/');
    
    // Check if the back button exists using aria-label, role, or title
    const backButton = page.getByRole('button', { name: /رجوع/i });
    
    // We expect the button to be visible
    await expect(backButton).toBeVisible({ timeout: 5000 });
  });
});
