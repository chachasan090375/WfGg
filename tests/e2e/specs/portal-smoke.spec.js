import { expect, test } from '@playwright/test';

const baseUrl = process.env.WFGG_E2E_BASE_URL;

test.describe('WfGg portal smoke', () => {
  test.skip(!baseUrl, 'WFGG_E2E_BASE_URL is not configured');

  test('homepage answers and renders HTML', async ({ page }) => {
    const response = await page.goto('/', { waitUntil: 'domcontentloaded' });
    expect(response).not.toBeNull();
    expect(response.status()).toBeLessThan(400);
    await expect(page.locator('body')).toBeVisible();
    expect((await page.locator('body').innerText()).trim().length).toBeGreaterThan(20);
  });
});
