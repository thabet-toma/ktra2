import { test, expect } from '@playwright/test';

test.describe('Global Back Button', () => {
  test('A clear back button is visible on the page', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('token', 'back-button-e2e-token');
      localStorage.setItem('userId', 'back-button-e2e-user');
      localStorage.setItem('tenantId', '1');
    });
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url());
      const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
      if (!isApi) return route.continue();
      if (url.pathname.endsWith('/hr/users/back-button-e2e-user/')) {
        return route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'back-button-e2e-user',
            name: 'Back Button Tester',
            role: 'manager',
            email: 'back-button@example.test',
            employmentStatus: 'active',
            isApproved: true,
            isEmailVerified: true,
          }),
        });
      }
      await route.fulfill({ contentType: 'application/json', body: '[]' });
    });
    await page.goto('/dashboard');
    
    // Check if the back button exists using aria-label, role, or title
    const backButton = page.getByRole('button', { name: /رجوع/i });
    
    // We expect the button to be visible
    await expect(backButton).toBeVisible({ timeout: 5000 });
  });
});
