import { expect, test, type Page } from '@playwright/test';

/**
 * ISSUE #118 — الرحلة الأمّ لمسودّات المستندات المحلية: فاتورة الشراء (أول
 * محرِّر يتبنّى `useDocumentDraft`، ولا تحفظ اليوم شيئاً إطلاقاً).
 *
 * نقطة اللمس المختارة للاختبار: حقل «رقم المستند» (`supplierInvoiceNumber`) —
 * نصٌّ حرّ مرئيٌّ بلا فتح نافذة اختيار مورّد/صنف، ويمرّ عبر `handleUpdateFinancial`
 * الذي يرفع `markDirty()` فعلياً (تحقّقٌ من الكود قبل الاختبار). هذا يكفي لإثبات
 * الآلية الكاملة (لمسة ⇐ كتابة مؤجَّلة ⇐ كتابة عند الإخفاء ⇐ استعادة تلقائية ⇐
 * تراجع) بلا خوض تعقيد منتقي المورّد/الصنف — و**رأسٌ بلا بنود** هو بالضبط ما
 * يُختبَر هنا: صفّ الصنف الافتراضي يبقى فارغاً طوال الرحلة ولا يمنع الحفظ ولا
 * الاستعادة (نقض `lines.length > 0`، issue #109 §٤).
 *
 * `document-coding.spec.ts` هو السابقة: تمويهُ REST عبر `page.route` يكفي
 * لتشغيلها على `npm run dev` بلا خادم — فاتورة الشراء REST بالكامل أيضاً
 * (`purchaseInvoiceApi`)، وحتى القوائم المارّة بـ`components/legacy/firestoreService.ts`
 * (الموردون والمنتجات) تنادي نقاط `/api/partners/lookup/` و`/api/lookup/products/`
 * فعلياً — لا جسر Firestore حقيقي متبقٍّ خلف الاسم.
 */

test.use({ serviceWorkers: 'block' });

const USER = {
  id: 'draft-e2e-user',
  name: 'مستخدم اختبار المسودّات',
  role: 'manager',
  email: 'draft-e2e@example.test',
  employmentStatus: 'active',
  isApproved: true,
  isEmailVerified: true,
};

function tenant(id: number, name: string) {
  return {
    TenantID: id, CompanyName: name, SubscriptionPlan: 'Enterprise',
    Status: 'Active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
    template: 'general', managed_by: null,
  };
}

/**
 * يبدّل الشركة النشطة لبقية الاختبار — لا `localStorage.setItem` مباشرةً وحده:
 * `page.reload()` القادم يُعيد تشغيل كل init scripts المسجَّلة، فتسجيل واحدٍ
 * جديد هنا يضمن بقاء القيمة بعد التحديث (لا قبله فقط)، ويُطبَّق فوراً أيضاً
 * على الصفحة الحالية دون انتظار تحميلٍ جديد.
 */
async function switchTenant(page: Page, tenantId: number): Promise<void> {
  await page.addInitScript((tid: number) => {
    localStorage.setItem('tenantId', String(tid));
  }, tenantId);
  // والتطبيقُ الفوريُّ على الصفحة الحالية **فقط إن كانت صفحةً حقيقية**:
  // قبل أوّل `goto` نحن على `about:blank` حيث `localStorage` يرمي
  // `SecurityError` — و`addInitScript` أعلاه يكفي وحده لما بعد التنقّل.
  if (page.url().startsWith('http')) {
    await page.evaluate((tid: number) => {
      localStorage.setItem('tenantId', String(tid));
    }, tenantId);
  }
}

async function stub(page: Page, tenantIds: number[] = [1]) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'draft-e2e-token');
    localStorage.setItem('userId', 'draft-e2e-user');
  });
  // الشركة النشطة وحدها تُضبط بمساعد منفصل (`switchTenant`) — `addInitScript`
  // يُعاد تشغيله عند **كل** تنقّل/إعادة تحميل في نفس السياق، فتثبيت `tenantId`
  // هنا كان يمحو أي تبديلٍ لاحق للشركة صامتاً في اللحظة التي يُعاد فيها تحميل
  // الصفحة — وهو بالضبط ما يفعله اختبار «شركتان».
  await switchTenant(page, tenantIds[0]);

  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const path = url.pathname;
    const json = (body: unknown, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(body),
    });

    if (path.endsWith('/hr/users/draft-e2e-user/')) return json(USER);
    if (path.endsWith('/tenants/companies/my-companies/')) {
      return json(tenantIds.map((id, i) => ({
        id, tenant: tenant(id, `شركة اختبار ${id}`), role: 'manager',
        is_default: i === 0, created_at: '2026-01-01T00:00:00Z', can_access_import: false,
      })));
    }
    if (path.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true,
        permissions: [
          'purchase.invoice.view', 'purchase.invoice.create', 'purchase.invoice.edit',
          'purchase.payment.create',
        ],
        modules: {}, template: 'general', terms: {}, shell: null, ui_mode: 'advanced',
      });
    }
    if (path.endsWith('/accounting/accounts/')) return json([]);
    if (path.endsWith('/accounting/cash-box-accounts/')) return json([]);
    if (path.endsWith('/accounting/cash-box-accounts/my-default/')) {
      return json({ cash_box: null, cash_box_name: null });
    }
    if (path.endsWith('/logistics/purchase-settings/current/')) {
      return json({ serial_entry_mode: 'off', receive_on_post: true, default_cash_account: null });
    }
    if (path.startsWith('/api/partners/lookup/')) return json([]);
    if (path.startsWith('/api/lookup/products/')) return json([]);
    if (path.endsWith('/logistics/purchase-invoices/') && request.method() === 'GET') {
      return json({ count: 0, next: null, previous: null, results: [] });
    }
    if (path.endsWith('/hr/auth/logout/') && request.method() === 'POST') {
      return json({ detail: 'ok' });
    }
    return json([]);
  });
}

/** عدد صفوف مسودّات المستندات في IndexedDB — بلا اعتماد على أي وحدة تطبيق،
 *  كي يبقى فحصاً مستقلاً عن تفاصيل التنفيذ الداخلية. */
async function documentDraftCount(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        const req = indexedDB.open('ktra_offline');
        req.onerror = () => resolve(-1);
        req.onsuccess = () => {
          const db = req.result;
          if (!db.objectStoreNames.contains('document_drafts')) {
            db.close();
            resolve(0);
            return;
          }
          const tx = db.transaction('document_drafts', 'readonly');
          const store = tx.objectStore('document_drafts');
          const countReq = store.count();
          countReq.onsuccess = () => {
            db.close();
            resolve(countReq.result);
          };
          countReq.onerror = () => {
            db.close();
            resolve(-1);
          };
        };
      }),
  );
}

const SUPPLIER_DOC_FIELD = 'رقم فاتورة المورد';

test('الرحلة الأمّ: فاتورة شراء جديدة، اكتب، أخفِ التبويب، أعِد التحميل ← المحتوى موجود والشريط ظاهر، ثم تراجع ← نظيف', async ({ page }) => {
  test.setTimeout(60_000);
  await stub(page);

  await page.goto('/purchase-invoices/new');
  const docField = page.getByPlaceholder(SUPPLIER_DOC_FIELD);
  await expect(docField).toBeVisible({ timeout: 30_000 });

  // رأسٌ بلا بنود: صفّ الصنف الافتراضي يبقى فارغاً طوال الرحلة (نقض §٤).
  await docField.fill('SUP-DRAFT-001');
  await expect(docField).toHaveValue('SUP-DRAFT-001');

  // إخفاء التبويب — الحدّ الأخير المضمون للكتابة (لا beforeunload، issue #109 §٣).
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });

  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

  await page.reload();
  await expect(page.getByTestId('draft-restored-banner')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByPlaceholder(SUPPLIER_DOC_FIELD)).toHaveValue('SUP-DRAFT-001');

  await page.getByTestId('draft-restored-undo').click();
  await expect(page.getByTestId('draft-restored-banner')).toHaveCount(0);
  await expect(page.getByPlaceholder(SUPPLIER_DOC_FIELD)).toHaveValue('');
  await expect.poll(() => documentDraftCount(page)).toBe(0);
});

test('شركتان: مسودّة شركة لا تظهر في أخرى (يُختبَر بشركتين لا بواحدة)', async ({ page }) => {
  test.setTimeout(60_000);
  await stub(page, [1, 2]);

  await page.goto('/purchase-invoices/new');
  const docField = page.getByPlaceholder(SUPPLIER_DOC_FIELD);
  await expect(docField).toBeVisible({ timeout: 30_000 });
  await docField.fill('T1-ONLY-DRAFT');
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

  // تبديل الشركة النشطة (كما يفعل مبدّل الشركات فعلياً) ثم إعادة فتح نفس الشاشة.
  await switchTenant(page, 2);
  await page.reload();
  await expect(page.getByPlaceholder(SUPPLIER_DOC_FIELD)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('draft-restored-banner')).toHaveCount(0);
  await expect(page.getByPlaceholder(SUPPLIER_DOC_FIELD)).toHaveValue('');

  // والعودة للشركة الأولى تُعيد المسودّة — إثباتٌ أن العزل بالمفتاح لا بالمحو.
  await switchTenant(page, 1);
  await page.reload();
  await expect(page.getByTestId('draft-restored-banner')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByPlaceholder(SUPPLIER_DOC_FIELD)).toHaveValue('T1-ONLY-DRAFT');
});

test('الخروج يمحو المسودّات المحلية (خصوصية جهاز مشترك)', async ({ page }) => {
  test.setTimeout(60_000);
  await stub(page);

  await page.goto('/purchase-invoices/new');
  const docField = page.getByPlaceholder(SUPPLIER_DOC_FIELD);
  await expect(docField).toBeVisible({ timeout: 30_000 });
  await docField.fill('LOGOUT-DRAFT');
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

  // مسار الخروج الحقيقي من الواجهة — لا محاكاة يدوية لمسح localStorage وحده:
  // زرّ «تسجيل الخروج» (`AppLayout.tsx`) ← تأكيدٌ ← `AuthContext.logout()` ←
  // `authService.logoutUser()` نفسها، وهي بالضبط النقطة التي تمسح المسودّات.
  await page.getByRole('button', { name: 'تسجيل الخروج' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'حذف' }).click();

  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBe(0);
});

/**
 * ISSUE #120 — الحارس مقلوب: يُحاول الحفظ المحلي أوّلاً، ولا يعترض المغادرة
 * إلّا إن فشل فعلاً. `InvoiceForm.tsx` هو المستهلك الوحيد لـ`useDocumentDraft`
 * (issue #118)، فهو حامل الحارس المقلوب الوحيد — و`SalesInvoiceEditor.tsx`
 * و`ImportDocumentScreen.tsx` يحتفظان بحارسهما القديم غير المشروط عمداً حتى
 * تنضمّا إلى الخطّاف المشترك (issue #121): بلا محاولة حفظٍ فعلية لا معنى
 * لشرط «إلّا إن فشل»، وحذفُ الحارس قبلها يستبدل حواراً مزعجاً بضياعٍ صامت.
 *
 * التحقّق **لا** يعتمد على حوار متصفّح حقيقي (سلوك beforeunload في Chromium
 * تحت الأتمتة متقلّب بين إصدارات Playwright) بل على إرسال حدث `beforeunload`
 * صناعياً وقراءة `event.defaultPrevented` مباشرة — فحصٌ حتميّ لنفس الشرط الذي
 * يقرّره مستمع الحارس في الكود (`e.preventDefault()` من عدمه).
 */
async function dispatchBeforeUnload(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const ev = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(ev);
    return ev.defaultPrevented;
  });
}

test('الحارس المقلوب: الحفظ المحلي ينجح ← بلا اعتراض مغادرة والعمل محفوظ فعلاً (issue #120)', async ({ page }) => {
  test.setTimeout(60_000);
  await stub(page);

  await page.goto('/purchase-invoices/new');
  const docField = page.getByPlaceholder(SUPPLIER_DOC_FIELD);
  await expect(docField).toBeVisible({ timeout: 30_000 });
  await docField.fill('SUP-DRAFT-NODIALOG');
  await expect(docField).toHaveValue('SUP-DRAFT-NODIALOG');

  // مؤشّر «حُفظ HH:mm» (issue #120 §٣) هو إثبات نجاح الحفظ المحلي فعلياً —
  // لا انتظار توقيتٍ أعمى للكتابة المؤجَّلة (٥٠٠ms).
  await expect(page.getByTestId('draft-saved-indicator')).toBeVisible({ timeout: 10_000 });
  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

  // ولا لافتة فشلٍ لاصقة، ولا اعتراض مغادرة حقيقي.
  await expect(page.getByTestId('draft-save-failed-banner')).toHaveCount(0);
  expect(await dispatchBeforeUnload(page)).toBe(false);
});

test('حالة فشلٍ مُصطنَعة: كتابة IndexedDB معطَّلة ← اللافتة اللاصقة تظهر والمغادرة تُستوقَف (issue #120)', async ({ page }) => {
  test.setTimeout(60_000);

  // اصطناعٌ نظيف للفشل من داخل الاختبار وحده — لا مِقبض اختبارٍ في كود
  // الإنتاج: تعطيل `IDBObjectStore.put` لمخزن `document_drafts` تحديداً (بلا
  // مسّ مخازن أخرى) يحاكي حصّةً ممتلئة أو تصفّحاً خاصاً بلا محاكاة تلك البيئات
  // فعلياً. يُسجَّل قبل أي تنقّل كي يسري على كل تحميل صفحة.
  await page.addInitScript(() => {
    const originalPut = IDBObjectStore.prototype.put;
    IDBObjectStore.prototype.put = function (this: IDBObjectStore, ...args: unknown[]) {
      if (this.name === 'document_drafts') {
        throw new DOMException('محاكاة فشل كتابة (issue #120 e2e)', 'QuotaExceededError');
      }
      return (originalPut as (...a: unknown[]) => IDBRequest).apply(this, args);
    };
  });
  await stub(page);

  await page.goto('/purchase-invoices/new');
  const docField = page.getByPlaceholder(SUPPLIER_DOC_FIELD);
  await expect(docField).toBeVisible({ timeout: 30_000 });
  await docField.fill('SUP-DRAFT-FAIL');

  await expect(page.getByTestId('draft-save-failed-banner')).toBeVisible({ timeout: 10_000 });
  // لا مؤشّر «حُفظ» — الكتابة فشلت فعلاً، لا وهم نجاح.
  await expect(page.getByTestId('draft-saved-indicator')).toHaveCount(0);
  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBe(0);

  expect(await dispatchBeforeUnload(page)).toBe(true);
});
