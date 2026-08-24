import { test, expect } from '@playwright/test';

/**
 * T-WIN — النافذة العائمة: تُسحب، وتُحجَّم، وتعود حيث تُركت.
 * تُقاد من معرض المكوّنات `/aseel-kit` — عام وحتمي، وبيانات الشركات ليست كذلك.
 * (نفس مبرّر `aseel-dense-table-widths.spec.ts`.)
 */

const openWindow = async (page: import('@playwright/test').Page) => {
  await page.goto('/aseel-kit');
  const opener = page.getByTestId('story-open-float');
  await expect(opener).toBeVisible({ timeout: 15000 });
  await opener.click();
  const win = page.getByTestId('story-float-win');
  await expect(win).toBeVisible();
  return win;
};

/**
 * مقاييس التخطيط لا الصندوق المرئي: حركة الدخول (scale .97) تُصغّر
 * boundingBox لحظةَ القياس فتتذبذب المقارنة. offsetWidth/offsetLeft لا يراهما
 * التحويل.
 */
const boxOf = async (locator: import('@playwright/test').Locator) => {
  await expect(locator).toBeVisible();
  return locator.evaluate((el) => {
    const node = el as HTMLElement;
    return {
      x: node.offsetLeft, y: node.offsetTop,
      width: node.offsetWidth, height: node.offsetHeight,
    };
  });
};

/** سحب حقيقي بأحداث المؤشر: الحلقة مبنية على pointer لا mouse. */
const dragBy = async (
  page: import('@playwright/test').Page,
  from: { x: number; y: number },
  dx: number,
  dy: number,
) => {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + dx / 2, from.y + dy / 2, { steps: 4 });
  await page.mouse.move(from.x + dx, from.y + dy, { steps: 4 });
  await page.mouse.up();
};

test('النافذة العائمة تُسحب من شريط عنوانها', async ({ page }) => {
  const win = await openWindow(page);
  const before = await boxOf(win);

  const barBox = (await win.locator('.aseel-float-win__bar').boundingBox())!;
  await dragBy(page, { x: barBox.x + barBox.width / 2, y: barBox.y + barBox.height / 2 }, -120, 80);

  const after = await boxOf(win);
  expect(Math.round(after.x)).toBeLessThan(Math.round(before.x));
  expect(Math.round(after.y)).toBeGreaterThan(Math.round(before.y));
  expect(Math.round(after.width)).toBe(Math.round(before.width));
  expect(Math.round(after.height)).toBe(Math.round(before.height));
});

test('النافذة العائمة تُحجَّم من الزاوية السفلى، والهندسة تعود بعد إعادة التحميل', async ({ page }) => {
  const win = await openWindow(page);
  const before = await boxOf(win);

  const gripBox = (await win.locator('[data-grip="se"]').boundingBox())!;
  await dragBy(page, { x: gripBox.x + gripBox.width / 2, y: gripBox.y + gripBox.height / 2 }, 90, 60);

  const resized = await boxOf(win);
  expect(Math.round(resized.width)).toBeGreaterThan(Math.round(before.width));
  expect(Math.round(resized.height)).toBeGreaterThan(Math.round(before.height));

  const saved = await page.evaluate(() => localStorage.getItem('ktra:win:kit-demo'));
  expect(saved, 'الهندسة تُكتب عند رفع الإصبع').not.toBeNull();

  await page.reload();
  const reopened = await openWindow(page);
  const restored = await boxOf(reopened);
  expect(Math.round(restored.width)).toBe(Math.round(resized.width));
  expect(Math.round(restored.height)).toBe(Math.round(resized.height));
  expect(Math.round(restored.x)).toBe(Math.round(resized.x));
});

test('Escape يُغلق النافذة', async ({ page }) => {
  const win = await openWindow(page);
  await win.press('Escape');
  await expect(win).toBeHidden();
});

test('على الجوال النافذة لوحٌ ملء الشاشة بلا مقابض', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 780 });
  const win = await openWindow(page);
  const box = await boxOf(win);
  const layoutWidth = await page.evaluate(() => document.documentElement.clientWidth);
  expect(box.width).toBe(layoutWidth);
  await expect(win.locator('[data-grip="se"]')).toHaveCount(0);
});
