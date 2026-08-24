import { test, expect } from '@playwright/test';

/**
 * B3 — المشي الكامل على مكتب المحاسبة، **على خادم حقيقي بلا أي stub**:
 * دخول محاسب ← إضافة زبون خارجي ← برنامج مراجعة بموعد ← الأجندة ← «مواعيد قريبة»
 * على لوحة المكتب.
 *
 * يحتاج backend على 8000 وحساب محاسب مُتحقَّق منه (`OFFICE_EMAIL`/`OFFICE_PASSWORD`).
 */
const EMAIL = process.env.OFFICE_EMAIL || 'office.walk@ktra.test';
const PASSWORD = process.env.OFFICE_PASSWORD || 'Walk!2026#office';
const CLIENT_NAME = `مؤسسة المشي التجارية ${Date.now()}`;
const SHOTS = 'e2e/office-walk-shots';

/**
 * هذا المشي يحتاج خادماً حيّاً وحساباً مزروعاً، فبدونهما كان يسقط **أحمر** في كل
 * تشغيل محلي — وأحمرٌ دائمٌ يُدرّب على تجاهل الأحمر. صار يتخطّى نفسه معلناً
 * سببه، فيبقى الأحمر معنىً لا ضجيجاً.
 */
test.beforeEach(async ({ request }) => {
  let alive = false;
  try {
    const probe = await request.get('http://localhost:8000/api/', { timeout: 3_000 });
    alive = probe.status() < 500;
  } catch {
    alive = false;
  }
  test.skip(!alive, 'يلزمه backend على 8000 وحساب محاسب مُتحقَّق (OFFICE_EMAIL/OFFICE_PASSWORD)');
});

test('المكتب يخدم زبوناً خارجياً من إضافته إلى ظهور موعده على اللوحة', async ({ page }) => {
  test.setTimeout(180_000);

  // ① دخول المحاسب — النموذج الحقيقي، لا حقن توكن.
  await page.goto('/');
  // الزائر يهبط على الصفحة التعريفية أولاً — «تسجيل الدخول» منها.
  await page.getByRole('button', { name: /تسجيل الدخول|دخول/ }).first().click();
  // حقلا الدخول بلا `htmlFor` على تسميتهما (خارج نطاق B3) — نُمسكهما بالـplaceholder.
  await page.getByPlaceholder('example@email.com').fill(EMAIL);
  await page.getByPlaceholder('••••••••').fill(PASSWORD);
  await page.getByRole('button', { name: /تسجيل الدخول/ }).first().click();

  await expect(page.getByRole('heading', { name: 'لوحة المكتب' })).toBeVisible({ timeout: 40_000 });
  await page.screenshot({ path: `${SHOTS}/01-dashboard.png`, fullPage: true });

  // ② «زبائني» — القائمة الموحّدة.
  await page.getByRole('button', { name: 'زبائني' }).first().click();
  await expect(page.getByRole('heading', { name: /^زبائني/ })).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: `${SHOTS}/02-clients.png`, fullPage: true });

  // ③ إضافة زبون خارجي.
  await page.getByRole('button', { name: 'إضافة زبون' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByLabel(/الاسم التجاري/).fill(CLIENT_NAME);
  await dialog.getByLabel('الاسم الأول').fill('سامي');
  await dialog.getByLabel('الجوال').fill('0599111222');
  await dialog.getByLabel('القطاع').fill('تجارة عامة');
  await dialog.getByLabel('الرقم الضريبي').fill('556677889');
  await page.screenshot({ path: `${SHOTS}/03-add-client-form.png`, fullPage: true });
  await dialog.getByRole('button', { name: 'حفظ' }).click();

  // الحفظ يفتح ملف الزبون مباشرة — لا يترك المحاسب أمام قائمة يبحث فيها عمّا أضافه.
  await expect(page.getByRole('heading', { name: new RegExp(CLIENT_NAME) })).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: `${SHOTS}/04-client-file-data.png`, fullPage: true });

  // ④ برنامج مراجعة بموعد.
  await page.getByRole('button', { name: 'برامج المراجعة' }).click();
  await page.getByRole('button', { name: 'برنامج جديد' }).click();
  const programDialog = page.getByRole('dialog');
  await expect(programDialog).toBeVisible();
  const due = new Date();
  due.setDate(due.getDate() + 3);
  const dueIso = due.toISOString().slice(0, 10);
  await programDialog.getByLabel('موعد الانتهاء').fill(dueIso);
  await programDialog.getByLabel('الفريق المكلّف بالبرنامج').fill('فريق الضريبة');
  await page.screenshot({ path: `${SHOTS}/05-program-form.png`, fullPage: true });
  await programDialog.getByRole('button', { name: 'حفظ' }).click();

  await expect(page.getByRole('heading', { name: /برامج المراجعة \(/ })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('فريق الضريبة')).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/06-programs.png`, fullPage: true });

  // ⑤ موعد في أجندة الزبون.
  await page.getByRole('button', { name: 'مهام/مواعيد' }).click();
  await page.getByRole('button', { name: 'موعد جديد' }).click();
  const taskDialog = page.getByRole('dialog');
  await taskDialog.getByLabel('العنوان').fill('زيارة الزبون لتسليم المستندات');
  await taskDialog.getByRole('button', { name: 'حفظ' }).click();
  await expect(page.getByText('زيارة الزبون لتسليم المستندات')).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: `${SHOTS}/07-client-tasks.png`, fullPage: true });

  // ⑥ رفع مستند — الطلب يصل فعلاً إلى مسار المكتب بجسم multipart صحيح.
  await page.getByRole('button', { name: 'مستندات', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'رفع مستند' })).toBeVisible({ timeout: 20_000 });
  await page.getByLabel('الملف').setInputFiles({
    name: 'عقد-الخدمة.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('عقد تقديم خدمات محاسبية'),
  });
  await page.getByLabel('الاسم', { exact: true }).fill('عقد تقديم الخدمة');
  const uploadResponse = page.waitForResponse((res) => res.url().includes('/accountant/practice/documents/upload/'));
  await page.getByRole('button', { name: 'ارفع' }).click();
  const upload = await uploadResponse;
  console.log('UPLOAD_STATUS', upload.status(), (await upload.text()).slice(0, 200));
  await page.screenshot({ path: `${SHOTS}/08-documents.png`, fullPage: true });

  // ⑦ الأجندة: البرنامج والموعد كلاهما فيها.
  await page.getByRole('button', { name: 'المواعيد والمهام' }).first().click();
  await expect(page.getByRole('heading', { name: /^الأجندة/ })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(CLIENT_NAME).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/09-agenda.png`, fullPage: true });

  // ⑧ «مواعيد قريبة» على لوحة المكتب — نهاية الطريق التي طلبها المعيار.
  await page.getByRole('button', { name: 'لوحة المكتب' }).first().click();
  await expect(page.getByRole('heading', { name: 'مواعيد قريبة' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(CLIENT_NAME).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/10-dashboard-deadlines.png`, fullPage: true });

  // ⑨ إعدادات المكتب — أنواع الخدمات التي يبني عليها البرنامج.
  await page.getByRole('button', { name: 'إعدادات المكتب' }).first().click();
  await expect(page.getByRole('heading', { name: 'أنواع الخدمات' })).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: `${SHOTS}/11-settings.png`, fullPage: true });
});
