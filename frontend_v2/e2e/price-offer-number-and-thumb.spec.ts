import { test, expect, type Page } from '@playwright/test';

/**
 * THA-116 (#31) — عمود «رقم المستند» في قائمة عروض وطلبيات الاستيراد.
 *
 * عنصران في صفّ واحد: مربّع صورة ثابت 72px ورقم المستند. العقد المثبَّت هنا:
 *   1. الصورة تملأ مربّعها (`object-fit: cover` على عنصر بحجم الحاوية كاملاً)،
 *      فالصورة العمودية تُقصّ ولا تُترك بهامش أبيض.
 *   2. رقم طويل لا يوسّع عمودَه ولا يزاحم الصورة ولا العمود المجاور: عرض
 *      الأعمدة لا يتغيّر بين قائمة فيها رقم طويل وقائمة بأرقام قصيرة فقط.
 *   3. المعروض تسلسلٌ وحده (`IQ-0006` ← `6`) والكامل في التلميح — إلا حين
 *      يتصادم تسلسلان في القائمة، فتعود الأرقام كاملةً بالقصّ الأوسط.
 *
 * مراجعة المالك (٢٢‏/٨‏/٢٠٢٦) نسخت معيار «رقم من ١٢ محرفاً يظهر كاملاً»:
 * «الرقم ملوش لزمة كثير ماكل الصور… يبين بس ٦ ويكبر الصور عحساب الرقم».
 * فالمعيار المُستبدَل صار: التسلسل وحده، والمربّع 72px، والكامل في `title`.
 * (48px كانت الخطوة الأولى، ونصفُ الخانة بقي فارغاً — «لسا مش كبار».)
 */

/** صورة عمودية (نسبة 1:3) — `contain` يتركها بهامشين، `cover` يملأ المربّع. */
const PORTRAIT_IMAGE =
  'data:image/svg+xml;utf8,'
  + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="120">'
    + '<rect width="40" height="120" fill="#2f6fb2"/></svg>',
  );

/** رقم أطول من حدّ العرض — الحالة التي كانت توسّع العمود على حساب جارته. */
const LONG_NUMBER = 'IQ-0000000123456';

const quotation = (
  id: number, quotationNumber: string, orderName: string, withImage: boolean,
) => ({
  id,
  quotation_number: quotationNumber,
  scope: 'import',
  status: 'draft',
  supplier: 7,
  supplier_name: 'مصنع شنغهاي',
  order_name: orderName,
  order_description: 'وصف قصير',
  quotation_date: '2026-08-16',
  currency: 1,
  currency_code: 'USD',
  exchange_rate: '1',
  subtotal: '100',
  discount_amount: '0',
  tax_rate: '0',
  tax_amount: '0',
  grand_total: '100',
  shipping_cost_estimate: '0',
  is_shipping_included: false,
  created_at: `2026-08-1${id}T00:00:00Z`,
  attachments: withImage
    ? [{ name: 'صورة المنتج.png', url: PORTRAIT_IMAGE, type: 'image/png', size: 1024 }]
    : [],
  lines: [],
});

/** القائمة التي فيها الرقم الطويل. */
const WITH_LONG_NUMBER = [
  quotation(1, LONG_NUMBER, 'طلبية الرقم الطويل', true),
  quotation(2, 'IQ-00006', 'طلبية الرقم القصير', true),
  quotation(3, 'IQ-00007', 'طلبية بلا صورة', false),
];

/** نفس القائمة بأرقام قصيرة فقط — مرجع قياس عرض الأعمدة. */
const SHORT_NUMBERS_ONLY = [
  quotation(1, 'IQ-00005', 'طلبية الرقم الطويل', true),
  quotation(2, 'IQ-00006', 'طلبية الرقم القصير', true),
  quotation(3, 'IQ-00007', 'طلبية بلا صورة', false),
];

/**
 * رقم من **١٢ محرفاً** — كان معيار المالك السابق («يظهر كاملاً»)، وصار الآن
 * أشدَّ حالات الاختصار وضوحاً: أحدَ عشرَ محرفاً منه بادئةٌ أو أصفار، والمميِّز
 * محرفٌ واحد. يبقى محروساً هنا لأن انقلاب السلوك عنده هو الفرق بين الشاشتين.
 */
const TWELVE_CHAR_NUMBER = 'IQ-000000006';
const WITH_TWELVE_CHAR = [
  quotation(1, TWELVE_CHAR_NUMBER, 'طلبية الرقم الطويل', true),
  quotation(2, 'IQ-00007', 'طلبية الرقم القصير', true),
  quotation(3, 'IQ-00008', 'طلبية بلا صورة', false),
];

/**
 * تسلسلان متصادمان في قائمة واحدة (`IQ-0006` و`IQ-06` كلاهما «٦»). الاختصار
 * هنا يجعل صفّين متطابقين، فالعقد أن تعود القائمة كلّها إلى الأرقام الكاملة.
 */
const WITH_COLLIDING_SERIALS = [
  quotation(1, 'IQ-0006', 'طلبية الرقم الطويل', true),
  quotation(2, 'IQ-06', 'طلبية الرقم القصير', true),
  quotation(3, 'IQ-00007', 'طلبية بلا صورة', false),
];

/** يفتح شاشة عروض الاستيراد على قائمة معطاة — الخادم كله مموَّه. */
const openOffers = async (page: Page, rows: unknown[]) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'offer-cell-e2e-token');
    localStorage.setItem('userId', 'offer-cell-e2e-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    let body: unknown = [];
    const path = url.pathname;
    if (path.endsWith('/hr/users/offer-cell-e2e-user/')) {
      body = {
        id: 'offer-cell-e2e-user',
        name: 'Offer Cell Tester',
        role: 'manager',
        email: 'offer@example.test',
        employmentStatus: 'active',
        isApproved: true,
        isEmailVerified: true,
      };
    } else if (path.endsWith('/tenants/companies/my-companies/')) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الاستيراد', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: true,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z',
        can_access_import: true,
      }];
    } else if (path.endsWith('/permissions/me/')) {
      // `can()` يقرأ القائمة نفسها لا `is_manager` — الشاشة محروسة بـ
      // `import.deal.manage` (`utils/viewPermissions.ts`).
      body = {
        role: 'manager',
        is_manager: true,
        permissions: ['import.deal.manage', 'purchase.invoice.view'],
      };
    } else if (path.endsWith('/logistics/supplier-quotations/')) {
      body = rows;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/import-offers');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('th', { hasText: 'رقم المستند' })).toBeVisible();
};

/** عرض العمودين المتجاورين كما رسمهما المتصفح. */
const columnWidths = (page: Page) => page.evaluate(() => {
  const headers = Array.from(document.querySelectorAll('thead th'));
  const width = (label: string) => Math.round(
    headers.find((th) => th.textContent?.includes(label))!.getBoundingClientRect().width,
  );
  return { number: width('رقم المستند'), summary: width('اسم ووصف الطلبية') };
});

/** ارتفاع الرقم المرسوم — سطران يساويان ضعف سطر، وهو ما كان يزاحم الصورة. */
const numberLineHeight = (page: Page, orderName = 'طلبية الرقم الطويل') =>
  page.locator('tbody tr', { hasText: orderName })
    .first().locator('td').first().locator('b')
    .evaluate((b) => Math.round(b.getBoundingClientRect().height));

test('الصورة العمودية تملأ مربّعها بلا هامش', async ({ page }) => {
  await openOffers(page, WITH_LONG_NUMBER);

  const cell = page.locator('tbody tr', { hasText: 'طلبية الرقم الطويل' })
    .first().locator('td').first();
  const thumb = cell.locator('img');
  await expect(thumb).toBeVisible();

  const fill = await thumb.evaluate((img) => {
    const box = img.getBoundingClientRect();
    const holder = (img.parentElement as HTMLElement).getBoundingClientRect();
    return {
      objectFit: getComputedStyle(img).objectFit,
      width: Math.round(box.width),
      height: Math.round(box.height),
      holderWidth: Math.round(holder.width),
      holderHeight: Math.round(holder.height),
    };
  });

  expect(fill.objectFit).toBe('cover');
  // المربّع ثابت 72px ولم يُسحق بالرقم إلى جانبه. والقياس على الحاوية نفسها:
  // `h-18 w-18` صنفٌ ديناميكي في Tailwind 4 — لو لم يُولَّد لسقط الارتفاع إلى
  // ارتفاع الصورة الطبيعي بلا أن يُسقط شيءٌ آخر، وهو عطبٌ صامت.
  expect(fill.holderWidth).toBe(72);
  expect(fill.holderHeight).toBe(72);
  // لا هامش بين الصورة وحاويتها — الفرق حدّ المربّع فقط (1px من كل جهة).
  expect(fill.holderWidth - fill.width).toBeLessThanOrEqual(2);
  expect(fill.holderHeight - fill.height).toBeLessThanOrEqual(2);
});

test('الرقم الطويل يبقى سطراً واحداً بجانب الصورة ولا يقتطع من العمود المجاور', async ({ page }) => {
  await openOffers(page, SHORT_NUMBERS_ONLY);
  const baseline = await columnWidths(page);
  const shortLine = await numberLineHeight(page);

  await page.unrouteAll();
  await openOffers(page, WITH_LONG_NUMBER);
  const withLong = await columnWidths(page);

  // العطب المُصلَح: الرقم كان يلتفّ سطرين بجانب الصورة (`white-space: normal`)
  // فيزاحمها بدل أن يقف إلى جانبها. سطر واحد مهما طال الرقم.
  expect(await numberLineHeight(page)).toBe(shortLine);

  // والعمود يبقى داخل عرضه المعلن: 128px تسع مربّعاً 72px وتسلسلاً من ستّ
  // خانات — وهو أقصى ما تعيده `documentSerialDisplay`. المُعلَن هنا ليس اختياراً
  // جمالياً بل حاصلَ قياس: بأقلّ منه يتجاوزه المتصفح متى طال التسلسل، فيصير
  // الرقم المعلن كذبةً. وهو مع ذلك أضيقُ من 150px الأصلية والصورة ضِعفها.
  expect(withLong.number).toBeLessThanOrEqual(128);
  // التسامح 4px لا 2: مع مربّع 72px صار المتغيّرُ الوحيدُ بين القائمتين طولَ
  // التسلسل نفسه (خانة واحدة مقابل ستّ)، وهو 3px يعيد `table-layout: auto`
  // توزيعها. الـ2px الأصلية كانت مقيسةً على خلية أخرى — رقمٍ كاملٍ في 150px.
  // والحدّ يبقى حدّاً: سرقةُ عمودٍ حقيقيةٍ عشراتُ البكسلات لا ثلاثة.
  expect(baseline.summary - withLong.summary).toBeLessThanOrEqual(4);

  // ومحتوى الخلية لا يتجاوز الخلية — لا قطع لعنصر مجاور.
  const overflow = await page.locator('tbody tr', { hasText: 'طلبية الرقم الطويل' })
    .first().locator('td').first()
    .evaluate((td) => {
      const inner = td.firstElementChild as HTMLElement;
      return Math.round(
        inner.getBoundingClientRect().width - td.getBoundingClientRect().width,
      );
    });
  expect(overflow).toBeLessThanOrEqual(0);
});

test('على الجوال أيضاً: سطر واحد ومربّع صورة كامل', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openOffers(page, WITH_LONG_NUMBER);

  // الجدول يمرّر أفقياً داخل `.ktra-gridwrap` — الخلية نفسها لا تنكسر.
  // سطر الجوال أقصر من سطر سطح المكتب، فالمقياس هو صفّ الرقم القصير نفسه.
  expect(await numberLineHeight(page))
    .toBe(await numberLineHeight(page, 'طلبية الرقم القصير'));
  const thumb = await page.locator('tbody tr', { hasText: 'طلبية الرقم الطويل' })
    .first().locator('td').first().locator('img')
    .evaluate((img) => {
      const holder = (img.parentElement as HTMLElement).getBoundingClientRect();
      return { w: Math.round(holder.width), h: Math.round(holder.height) };
    });
  expect(thumb).toEqual({ w: 72, h: 72 });
});

test('معيار المالك: التسلسل وحده يُعرض، بلا قصّ CSS — مكتباً وجوالاً', async ({ page }) => {
  /** يقارن عرض النصّ المرسوم بعرض الخانة: تساويهما يعني أن CSS لم يقصّ شيئاً. */
  const rendered = () => page.locator('tbody tr', { hasText: 'طلبية الرقم الطويل' })
    .first().locator('td').first().locator('b')
    .evaluate((b) => ({
      text: b.textContent,
      title: b.getAttribute('title'),
      scrollWidth: b.scrollWidth,
      clientWidth: b.clientWidth,
    }));

  await openOffers(page, WITH_TWELVE_CHAR);
  const desktop = await rendered();
  expect(desktop.text).toBe('6');
  // الكامل لم يُفقد — هو في التلميح وفي البحث.
  expect(desktop.title).toBe(TWELVE_CHAR_NUMBER);
  expect(desktop.scrollWidth).toBe(desktop.clientWidth);

  await page.setViewportSize({ width: 390, height: 844 });
  const mobile = await rendered();
  expect(mobile.text).toBe('6');
  expect(mobile.title).toBe(TWELVE_CHAR_NUMBER);
  expect(mobile.scrollWidth).toBe(mobile.clientWidth);
});

test('التسلسل وحده والكامل في التلميح', async ({ page }) => {
  await openOffers(page, WITH_LONG_NUMBER);

  const longNumber = page.locator('tbody tr', { hasText: 'طلبية الرقم الطويل' })
    .first().locator('td').first().locator('b');
  await expect(longNumber).toHaveAttribute('title', LONG_NUMBER);
  await expect(longNumber).toHaveText('123456');

  const shortNumber = page.locator('tbody tr', { hasText: 'طلبية الرقم القصير' })
    .first().locator('td').first().locator('b');
  await expect(shortNumber).toHaveText('6');
  await expect(shortNumber).toHaveAttribute('title', 'IQ-00006');
});

test('تصادم التسلسلات يعيد القائمة كلّها إلى الأرقام الكاملة', async ({ page }) => {
  await openOffers(page, WITH_COLLIDING_SERIALS);

  const numberOf = (orderName: string) => page.locator('tbody tr', { hasText: orderName })
    .first().locator('td').first().locator('b');

  // لولا الحارس لظهر الصفّان «٦» و«٦»: صفّان لا يفرّق بينهما شيء.
  await expect(numberOf('طلبية الرقم الطويل')).toHaveText('IQ-0006');
  await expect(numberOf('طلبية الرقم القصير')).toHaveText('IQ-06');
  // والحارس على القائمة لا على الصفّ — الصفّ الثالث يتبعها ولو لم يتصادم.
  await expect(numberOf('طلبية بلا صورة')).toHaveText('IQ-00007');
});
