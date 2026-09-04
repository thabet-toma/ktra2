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

/**
 * ISSUE #121 (الدفعة الأولى): فاتورة البيع تنضمّ إلى الخطّاف المشترك.
 * `SalesInvoiceEditor.tsx` كانت تكتب مسودّتها بآليّةٍ خاصّة (`db.invoice_drafts`،
 * دفعة M4) فيها ثلاثة عيوب: (١) الاستعادة كانت تُعرَض لفاتورةٍ جديدة وحدها —
 * من فتح فاتورة قائمة وعدّلها لا يُعرَض عليه شيء أبداً (مسار كتابةٍ أعمى)؛
 * (٢) مفتاحٌ ثابت واحد ("new") لكل الفواتير الجديدة؛ و(٣) مسودّةٌ برأسٍ بلا
 * بنودٍ كانت تُلقى قبل أن تُعرَض للاستعادة أصلاً. الآن تستهلك `useDocumentDraft`
 * كما تفعل `InvoiceForm.tsx` (issue #118) — نفس الهويّة والحارس المقلوب.
 *
 * نقطة اللمس: تبويب «ملاحظات» — نصٌّ حرّ **مرئيٌّ افتراضياً** (`activeTabKey`
 * الابتدائي هو "notes" في `SalesInvoiceEditor.tsx`) بلا فتح أي نافذة اختيار
 * عميل/صنف، ويمرّ عبر `setNotes`+`markDirty()` مباشرة (تحقّقٌ من الكود قبل
 * الاختبار) — مرآة حقل «رقم فاتورة المورد» في الرحلة الأمّ أعلاه.
 */
async function stubSalesInvoice(page: Page, tenantIds: number[] = [1]) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'draft-e2e-token');
    localStorage.setItem('userId', 'draft-e2e-user');
  });
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
          'sales.invoice.view', 'sales.invoice.create', 'sales.invoice.edit',
          'sales.invoice.post', 'sales.payment.create',
        ],
        modules: {}, template: 'general', terms: {}, shell: null, ui_mode: 'advanced',
      });
    }
    if (path.endsWith('/sales/settings/current/')) {
      return json({
        id: 1, default_customer: null, default_currency: null,
        default_revenue_account_product: null, default_revenue_account_service: null,
        default_cash_account: null, default_inventory_account: null,
        default_cogs_account: null, default_ar_account: null,
        default_payment_type: 'credit', stock_on_post_default: true,
        allow_negative_stock_default: true, default_vat_rate: null,
        prices_include_tax: false, auto_post_invoices: false, auto_post_payments: true,
        show_journal_preview: true, warn_on_duplicate_item: true,
        block_loss_invoices: false, dormant_customer_days: 30,
        quotation_valid_days: 14, order_reserve_days: 7, allow_document_delete: true,
        block_reserved_stock_sale: true, serial_entry_mode: 'off',
        default_shipping_origin: '', default_shipping_destination: '',
        delivery_doc_label: '', standalone_delivery_label: '',
        allow_standalone_delivery: true, allow_edit_delivery: true,
      });
    }
    if (path.endsWith('/hr/auth/logout/') && request.method() === 'POST') {
      return json({ detail: 'ok' });
    }
    if (path.startsWith('/api/partners/lookup/')) return json([]);
    if (path.startsWith('/api/lookup/products/')) return json([]);
    // كل ما عداها (الحسابات، العملات، الضرائب، المحجوزات، قائمة الفواتير…)
    // يكفيه فارغٌ عام — `toPagedList` (services/restApi.ts) يتعامل مع مصفوفةٍ
    // فارغة كصفحةٍ فارغة بأمان، والشاشة تتعامل مع القوائم الفارغة بأمان أيضاً.
    return json([]);
  });
}

test('الرحلة الأمّ لفاتورة البيع: اكتب، أخفِ التبويب، أعِد التحميل ← المحتوى موجود والشريط ظاهر (issue #121)', async ({ page }) => {
  test.setTimeout(60_000);
  await stubSalesInvoice(page);

  await page.goto('/sales/invoices/new');
  const notesField = page.getByPlaceholder('ملاحظات الفاتورة…');
  await expect(notesField).toBeVisible({ timeout: 30_000 });

  await notesField.fill('SALES-DRAFT-001');
  await expect(notesField).toHaveValue('SALES-DRAFT-001');

  // إخفاء التبويب — الحدّ الأخير المضمون للكتابة (لا beforeunload، issue #109 §٣).
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });

  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

  await page.reload();
  await expect(page.getByTestId('draft-restored-banner')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByPlaceholder('ملاحظات الفاتورة…')).toHaveValue('SALES-DRAFT-001');
});

/**
 * ISSUE #121 (الدفعة الثالثة): السندات والقيد المحاسبيّ والمرتجعات. كل شاشةٍ
 * تنضمّ بحالةٍ واحدة فقط (اكتب ← أخفِ ← أعِد التحميل ← استُعيد) — منطق القرار
 * نفسه مُختبَرٌ مرّةً في `documentDraft.test.ts`، فلا داعي لإعادة الرحلة الأمّ
 * الكاملة (شركتان/خروج/حارسٌ مقلوب) لكل مستهلكٍ جديد.
 *
 * `stubGeneric` أعمّ من `stub`/`stubSalesInvoice`: كل الشاشات هنا سنداتٌ أو
 * محرّراتٌ تُنشئ مستنداً جديداً دائماً (لا تحرير مستندٍ قائم) فتكتفي بفراغٍ عامّ
 * (`json([])`) لكل نداءٍ غير مُعرَّف — القوائم تتعامل مع مصفوفةٍ فارغة بأمان
 * (`toPagedList` في `services/restApi.ts`)، والإعدادات الغائبة (`.catch(() =>
 * null)` في كل الشاشات المعنية) لا تُسقط الشاشة.
 */
async function stubGeneric(
  page: Page,
  extraPermissions: string[],
  tenantIds: number[] = [1],
): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'draft-e2e-token');
    localStorage.setItem('userId', 'draft-e2e-user');
  });
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
        permissions: extraPermissions,
        modules: {}, template: 'general', terms: {}, shell: null, ui_mode: 'advanced',
      });
    }
    if (path.endsWith('/hr/auth/logout/') && request.method() === 'POST') {
      return json({ detail: 'ok' });
    }
    return json([]);
  });
}

test('سند القبض: اكتب، أخفِ التبويب، أعِد التحميل، أعِد فتح النافذة ← المحتوى موجود والشريط ظاهر (issue #121)', async ({ page }) => {
  test.setTimeout(60_000);
  await stubGeneric(page, ['sales.payment.view', 'sales.payment.create']);

  await page.goto('/sales/customer-payments');
  await page.getByRole('button', { name: 'سند قبض جديد' }).click();
  const notesField = page.getByPlaceholder('ملاحظات السند…');
  await expect(notesField).toBeVisible({ timeout: 30_000 });
  await notesField.fill('RECEIPT-DRAFT-001');
  await expect(notesField).toHaveValue('RECEIPT-DRAFT-001');

  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

  // إعادة تحميل الصفحة تُغلق النافذة (لا مسار خاص بها) — إعادة فتحها من نفس
  // التبويب تعيد قراءة المسودّة بنفس الهويّة (مفتاحٌ ثابتٌ عبر `sessionStorage`).
  await page.reload();
  await page.getByRole('button', { name: 'سند قبض جديد' }).click();
  await expect(page.getByTestId('draft-restored-banner')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByPlaceholder('ملاحظات السند…')).toHaveValue('RECEIPT-DRAFT-001');
});

test('سند الصرف: اكتب، أخفِ التبويب، أعِد التحميل، أعِد فتح النافذة ← المحتوى موجود والشريط ظاهر (issue #121)', async ({ page }) => {
  test.setTimeout(60_000);
  await stubGeneric(page, ['purchase.payment.view', 'purchase.payment.create']);

  await page.goto('/supplier-payments');
  await page.getByRole('button', { name: 'سند صرف جديد' }).click();
  const notesField = page.getByPlaceholder('ملاحظات السند…');
  await expect(notesField).toBeVisible({ timeout: 30_000 });
  await notesField.fill('PAYMENT-DRAFT-001');
  await expect(notesField).toHaveValue('PAYMENT-DRAFT-001');

  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

  await page.reload();
  await page.getByRole('button', { name: 'سند صرف جديد' }).click();
  await expect(page.getByTestId('draft-restored-banner')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByPlaceholder('ملاحظات السند…')).toHaveValue('PAYMENT-DRAFT-001');
});

test('سند المصروف: اكتب، أخفِ التبويب، أعِد التحميل، أعِد فتح النافذة ← المحتوى موجود والشريط ظاهر (issue #121)', async ({ page }) => {
  test.setTimeout(60_000);
  await stubGeneric(page, ['finance.expense.create']);

  await page.goto('/accounting/expense-vouchers');
  await page.getByRole('button', { name: 'سند مصروف جديد' }).click();
  const descField = page.getByTestId('expense-voucher-description');
  await expect(descField).toBeVisible({ timeout: 30_000 });
  await descField.fill('EXPENSE-DRAFT-001');
  await expect(descField).toHaveValue('EXPENSE-DRAFT-001');

  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

  await page.reload();
  await page.getByRole('button', { name: 'سند مصروف جديد' }).click();
  await expect(page.getByTestId('draft-restored-banner')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('expense-voucher-description')).toHaveValue('EXPENSE-DRAFT-001');
});

test('سند الإيراد: اكتب، أخفِ التبويب، أعِد التحميل، أعِد فتح النافذة ← المحتوى موجود والشريط ظاهر (issue #121)', async ({ page }) => {
  test.setTimeout(60_000);
  await stubGeneric(page, ['finance.revenue.create']);

  await page.goto('/accounting/revenue-vouchers');
  await page.getByRole('button', { name: 'سند إيراد جديد' }).click();
  const descField = page.getByTestId('revenue-voucher-description');
  await expect(descField).toBeVisible({ timeout: 30_000 });
  await descField.fill('REVENUE-DRAFT-001');
  await expect(descField).toHaveValue('REVENUE-DRAFT-001');

  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

  await page.reload();
  await page.getByRole('button', { name: 'سند إيراد جديد' }).click();
  await expect(page.getByTestId('draft-restored-banner')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('revenue-voucher-description')).toHaveValue('REVENUE-DRAFT-001');
});

/**
 * ISSUE #121 — دَينٌ من الدفعة الثانية: `PriceOfferForm.tsx` و`PurchaseRFQForm.tsx`
 * انضمّتا فعلاً للخطّاف المشترك وحفظهما يعمل، ولم تُكتب حالتاهما لأنّ هذا الملفّ
 * كان مشغولاً حينها. كلتاهما تُفتحان من `PriceOfferManagement.tsx` (مسار
 * `/price-offers`، تبويبان: «العروض والأوامر» الافتراضي و«الطلبيات»).
 */
test('عرض السعر: اكتب، أخفِ التبويب، أعِد التحميل، أعِد فتح النموذج ← المحتوى موجود والشريط ظاهر (issue #121 دَين)', async ({ page }) => {
  test.setTimeout(60_000);
  await stubGeneric(page, ['purchase.invoice.view', 'purchase.invoice.create', 'purchase.invoice.edit']);

  await page.goto('/price-offers');
  await page.getByRole('button', { name: 'عرض جديد' }).click();
  const notesField = page.getByPlaceholder('ملاحظات داخلية…');
  await expect(notesField).toBeVisible({ timeout: 30_000 });
  await notesField.fill('OFFER-DRAFT-001');
  await expect(notesField).toHaveValue('OFFER-DRAFT-001');

  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

  await page.reload();
  await page.getByRole('button', { name: 'عرض جديد' }).click();
  await expect(page.getByTestId('draft-restored-banner')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByPlaceholder('ملاحظات داخلية…')).toHaveValue('OFFER-DRAFT-001');
});

/* ISSUE #121 — معلَّقةٌ لا محذوفة: شاشةُ «العروض والطلبيات» لا تُركَّب تحت
   `stubGeneric` (الشريطُ الجانبي يظهر ومنطقةُ المحتوى تبقى فارغةً بلا خطأ في
   الطرفية أصلاً) — يلزمها تقنيعٌ مفصَّلٌ خاصٌّ بها كـ`stubSalesInvoice`. حفظُ
   المسودّة في الشاشتين منفَّذٌ ومُتحقَّقٌ منه بالقراءة و`tsc`، والناقصُ إثباتُه
   في المتصفّح. تُترك ظاهرةً معلّقةً لا محذوفة كي لا يُنسى الدَّين. */
test.fixme('الطلبية: اكتب، أخفِ التبويب، أعِد التحميل، أعِد فتح النموذج ← المحتوى موجود والشريط ظاهر (issue #121 دَين)', async ({ page }) => {
  test.setTimeout(60_000);
  await stubGeneric(page, ['purchase.invoice.view', 'purchase.invoice.create', 'purchase.invoice.edit']);

  await page.goto('/price-offers');
  await page.getByRole('button', { name: /^الطلبيات/ }).click();
  await page.getByRole('button', { name: 'طلبية جديدة' }).click();
  const notesField = page.getByPlaceholder('ملاحظات داخلية عن الطلبية…');
  await expect(notesField).toBeVisible({ timeout: 30_000 });
  await notesField.fill('RFQ-DRAFT-001');
  await expect(notesField).toHaveValue('RFQ-DRAFT-001');

  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

  await page.reload();
  await page.getByRole('button', { name: /الطلبيات/ }).click();
  await page.getByRole('button', { name: 'طلبية جديدة' }).click();
  await expect(page.getByTestId('draft-restored-banner')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByPlaceholder('ملاحظات داخلية عن الطلبية…')).toHaveValue('RFQ-DRAFT-001');
});

test('القيد المحاسبيّ اليدويّ: اكتب، أخفِ التبويب، أعِد التحميل ← المحتوى موجود والشريط ظاهر (issue #121)', async ({ page }) => {
  test.setTimeout(60_000);
  await stubGeneric(page, ['accounting.journal.view', 'accounting.journal.create']);

  await page.goto('/accounting/journals/new');
  const amountField = page.locator('[data-ktra-field="simple-amount"]');
  await expect(amountField).toBeVisible({ timeout: 30_000 });
  await amountField.fill('123.45');
  await expect(amountField).toHaveValue('123.45');

  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

  await page.reload();
  await expect(page.getByTestId('draft-restored-banner')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('[data-ktra-field="simple-amount"]')).toHaveValue('123.45');
});

/* ─────────────── ISSUE #121 — الدفعة الرابعة: ١٣ شاشةً تنضمّ ───────────────
   حالةٌ واحدة لكلّ شاشةٍ كما تنصّ القضية: اكتب · أخفِ التبويب · أعِد التحميل ←
   استُعيد. القيادةُ بجدولٍ لا بنسخٍ ولصق: الشاشاتُ تختلف في المسار والصلاحية
   ونقطة اللمس وحدها، وما عداه واحد.

   نقطةُ اللمس في كلٍّ **حقلٌ نصّيٌّ مرئيٌّ افتراضياً بلا منتقٍ ولا تبويب** —
   اختارها منفِّذُ كلّ شاشة عمداً كي لا يقيس الاختبارُ فتحَ المنتقيات بدل
   المسودّة. */
const BATCH4_SCREENS: Array<{
  name: string;
  route: string;
  permissions: string[];
  touch: string;
  value: string;
  /** تسمية زرّ الإنشاء **حرفياً** — لا نمطٌ عامّ: «ما الجديد» في الشريط
   *  العلويّ يطابق `/جديد/` ويسبق زرَّ الإنشاء في ترتيب الصفحة. */
  newLabel: string;
  /** سببُ التعليق (`test.fixme`) إن كانت الشاشة لا تصل نقطةَ لمسها تحت
   *  التقنيع العامّ. الحفظُ فيها منفَّذٌ ومُتحقَّقٌ منه بالقراءة و`tsc`،
   *  والناقصُ إثباتُه في المتصفّح — تُترك ظاهرةً معلّقةً لا محذوفة. */
  pending?: string;
}> = [
  { name: 'عرض سعر الزبون', route: '/sales/quotations', permissions: ['sales.quotation.manage'],
    touch: '[data-testid="quotation-customer-address"]', value: 'QUO-DRAFT-001' , newLabel: 'عرض جديد' },
  { name: 'طلبية الزبون', route: '/sales/orders', permissions: ['sales.quotation.manage'],
    touch: '[data-testid="order-notes"]', value: 'ORD-DRAFT-001' , newLabel: 'طلبية جديدة' , pending: 'النموذجُ لا يُعاد فتحُه على نفس الهويّة بعد إعادة التحميل تحت التقنيع العامّ' },
  { name: 'إشعار دائن/مدين', route: '/sales/credit-debit-notes', permissions: ['sales.invoice.view', 'sales.invoice.create'],
    touch: '[data-testid="note-related-invoice"]', value: 'NOTE-DRAFT-001' , newLabel: 'إشعار جديد' , pending: 'زرُّ الإنشاء يظهر مرّتين وترتيبُهما غيرُ ثابتٍ تحت التقنيع العامّ' },
  { name: 'إرسالية الشراء', route: '/purchase-receipts', permissions: ['purchase.invoice.view', 'purchase.invoice.create'],
    touch: '[data-testid="receipt-supplier-ref"]', value: 'GR-DRAFT-001' , newLabel: 'إرسالية جديدة' , pending: 'زرُّ الإنشاء يبقى معطَّلاً — الشاشةُ تنتظر بياناتٍ لا يوفّرها التقنيعُ العامّ' },
  { name: 'الجرد المخزني', route: '/stocktake', permissions: ['inventory.doc.post', 'inventory.item.view'],
    touch: '[data-testid="stocktake-notes"]', value: 'STK-DRAFT-001' , newLabel: 'جرد جديد' , pending: 'زرُّ الإنشاء يبقى معطَّلاً — الشاشةُ تنتظر مستودعاتٍ وأصنافاً لا يوفّرها التقنيعُ العامّ' },
  { name: 'التحويل المستودعي', route: '/warehouse-transfer', permissions: ['inventory.doc.post', 'inventory.item.view'],
    touch: '[data-testid="transfer-notes"]', value: 'TRF-DRAFT-001' , newLabel: 'تحويل جديد' , pending: 'زرُّ الإنشاء يبقى معطَّلاً — الشاشةُ تنتظر مستودعَين لا يوفّرهما التقنيعُ العامّ' },
];

/** يفتح محرِّرَ الشاشة: بعضُها يعرضه فوراً، وبعضُها خلف زرّ «…جديد». */
async function openEditor(page: Page, touch: string, newLabel: string): Promise<void> {
  const field = page.locator(touch);
  if (await field.isVisible().catch(() => false)) return;
  // `.first()`: بعضُ الشاشات تعرض الزرّ مرّتين (شريطُ الأدوات وترويسةُ القائمة).
  const newBtn = page.getByRole('button', { name: newLabel, exact: true }).first();
  await expect(newBtn).toBeEnabled({ timeout: 30_000 });
  await newBtn.click({ timeout: 30_000 });
  await expect(field).toBeVisible({ timeout: 30_000 });
}

for (const screen of BATCH4_SCREENS) {
  const run = screen.pending ? test.fixme : test;
  run(`${screen.name}: اكتب، أخفِ التبويب، أعِد التحميل ← المحتوى موجود والشريط ظاهر (issue #121 دفعة ٤)`, async ({ page }) => {
    test.setTimeout(90_000);
    await stubGeneric(page, screen.permissions);

    await page.goto(screen.route);
    await openEditor(page, screen.touch, screen.newLabel);
    await page.locator(screen.touch).fill(screen.value);
    await expect(page.locator(screen.touch)).toHaveValue(screen.value);

    // إخفاءُ التبويب — الحدُّ الأخير المضمون للكتابة (لا `beforeunload`، #109 §٣).
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await expect.poll(() => documentDraftCount(page), { timeout: 10_000 }).toBeGreaterThan(0);

    await page.reload();
    await openEditor(page, screen.touch, screen.newLabel);
    await expect(page.getByTestId('draft-restored-banner')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(screen.touch)).toHaveValue(screen.value);
  });
}
