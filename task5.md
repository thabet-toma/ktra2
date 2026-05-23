# TASK5 — Aseel-Native KTRA (Inside-Out Conversion + Backend Parity)

> **الدور:** Staff SWE / Tech Lead. هذه خطّة تُنفّذ بواسطة موديل أرخص.
> **كل** مهمة لها: هدف قابل للتحقق + مرجع Aseel صريح (ملف:سطر) + معيار قبول.
>
> **النقد الذي قاد لـtask5:** task4 (M0-M5) غلّفت الصفحات بـ
> `AseelDocumentShell` (شريط أوامر + رأس + شريط حالة) لكن **داخل الصفحات
> بقي مظهر ويب حديث (بطاقات/تدرّجات)**. الاستثناء الوحيد:
> `SalesInvoiceEditor` (M1) أُعيد بناؤه inside-out على القشرة بنجاح — هو
> **القالب الذهبي** الذي يَعمل عليه كل ما يأتي.
>
> **مصدر الحقيقة:** 14 ملف كامل في `docs/aseel_reference/full/` (مُستخرَجة
> من `/c/Users/asus/Desktop/ktra/الاصيل/`، 35MB أصلية). الـ.txt مرجع
> canonical لكل task. اللقطات المرفقة من المالك مرجع بصري إضافي.
>
> **مبدأ Web-Adapted Hybrid:** الأصيل برنامج Windows؛ KTRA صفحة ويب
> متعدّدة المستأجرين. الأصيل ليس عنده «صفقة → شحنة → تخليص → نقل محلي →
> فاتورة شراء» — هذا منطق استيراد KTRA الذي **يُحفَظ**. النموذج البصري
> والمحاسبي من الأصيل، الـbusiness flow من KTRA. هجين، لا استبدال.

---

## Pre-Planning Protocols (الـ5 إلزامية)

### 1. الوعي الزمني وموثوقية التبعيات
- التاريخ: 2026-05. React 19 (latest stable)، Vite 6، TS 5.8، Tailwind v4،
  Django 6، DRF 3.15، MySQL 8 — كلها متوافقة مع التاريخ الحالي.
- **لا dependencies جديدة** خلال task5. لا React libs إضافية. لا
  weasyprint/reportlab — الطباعة عبر `window.print()` + CSS print media.

### 2. التدفّق المنطقي ومنع زحف الميزات
- نطاق صارم: 11 milestones، ~85 task. أي شيء خارج الـmilestones = **رفض**.
- الأصيل عنده **550+ تقرير** — نأخذ **15 فقط** تَخدم KTRA (مفصَّلة في N4).
- الأصيل عنده **KDS مطابخ** + **WWW/FTP** + **POS كاشير** — **مرفوضة**
  (خارج نطاق KTRA الاستيرادي).

### 3. المعمارية الذكية (Surgical)
- **6 primitives جديدة فقط** في `components/aseel/`. أي primitive يُستخدم
  مرة واحدة فقط = لا يُجرَّد، يَبقى inline.
- **No micro-files:** كل صفحة form ≤ 800 سطر؛ تَنقسم إلى sub-sections فقط
  إذا فعلياً تَتجاوز.
- **استخدم نمط M1 كقالب:** أيّ موديل أرخص يقرأ
  `frontend_v2/components/sales/SalesInvoiceEditor.tsx` كل مرة قبل بدء
  form جديد. هو القالب الذهبي.

### 4. التتبّع (Safe Logging)
- نظام Django logging الحالي (`structlog`-style) كافٍ. لا تَضِف نظام جديد.
- كل service جديد يَستخدم `logger = logging.getLogger(__name__)` و
  `logger.info/warning/error` فقط.
- لا print statements. لا console.log في production code.

### 5. الذاكرة الخارجية (PROJECT_MAP.md)
- بعد كل N (1..10) يُحدَّث `PROJECT_MAP.md`:
  - `[ORPHANS & PENDING]` — قائمة محدَّثة.
  - بصمة الـN مع gateway verification.

---

## [TECH_STACK]

```
Frontend:
├─ React 19         (UI)
├─ Vite 6           (bundler + dev)
├─ TypeScript 5.8   (strict mode)
└─ Tailwind v4      (utility + Aseel CSS tokens)

Backend:
├─ Django 6
├─ DRF 3.15
├─ MySQL 8
└─ accounting.services.post_journal()  ⟵ المسار الوحيد لأي قيد

Shared:
└─ tools/rtf_extract.py  (decode Aseel .doc → UTF-8)
```

**ممنوع:** UI libs إضافية، new ORM libs، new PDF/print libs، new state
managers (نستخدم React useState + useReducer فقط).

---

## [SYSTEM_FLOW]

### رحلة الاستيراد الكاملة (KTRA-specific):

```
┌─[Procurement]────────────────────────────────────────────┐
│  Deal (logistics.LogisticsDeal)                          │
│   └─ items, prices, suppliers, installments              │
│                          ↓                                │
│  Shipment (logistics.LogisticsShipment)  [M3-T2 Aseel]   │
│   ├─ Customs Clearance (logistics.LogisticsClearance)    │
│   │   └─ landed-cost lines → product unit-cost           │
│   └─ Local Transport (logistics.LocalShipment) [T1-01]   │
│        └─ post_journal()  أجرة النقل                     │
│                          ↓                                │
│  Purchase Invoice (logistics.PurchaseInvoice)            │
│   └─ creates StockMovement                                │
│   └─ post_journal()  Dr Inventory / Cr AP                │
└──────────────────────────────────────────────────────────┘

┌─[Sales]──────────────────────────────────────────────────┐
│  Sales Quotation/Order   (sales.SalesQuotation)          │
│   └─ converts to ↓                                        │
│  Sales Invoice           (sales.SalesInvoice) [M1 ✅]    │
│   ├─ Attached Cheques    [M2-T3]                         │
│   ├─ Source Discount     [M2-T4]                         │
│   └─ post_journal()  Dr AR/Cash / Cr Revenue+VAT+COGS    │
│                          ↓                                │
│  Sales Return           (NEW — N0-T9)                    │
│   └─ post_journal()  reverse of original                  │
│                                                           │
│  Credit/Debit Note      (sales.CreditDebitNote) [M4-T4]  │
└──────────────────────────────────────────────────────────┘

┌─[Financial]──────────────────────────────────────────────┐
│  Customer Payment       (sales.CustomerPayment) [M4-T3]  │
│   └─ Dr Cash / Cr AR                                     │
│                                                           │
│  Supplier Payment       (NEW — N0-T10)                   │
│   └─ Dr AP / Cr Cash                                     │
│                                                           │
│  Manual Journal Entry   (accounting.JournalHeader) [M4-T2]│
│                                                           │
│  Cheque Lifecycle      (accounting.Cheque)               │
│   └─ Draft → UnderCollection → Collected / Bounced / Returned │
└──────────────────────────────────────────────────────────┘

┌─[Periodic]───────────────────────────────────────────────┐
│  VAT Statement          (NEW — N0-T11)                   │
│   └─ aggregates invoices in period                       │
│   └─ assigns vat_statement_no to each                    │
└──────────────────────────────────────────────────────────┘
```

### رحلة بصرية موحَّدة (تُطبَّق على كل صفحة):

```
┌─ AppLayout (data-skin="aseel" global) ───────────────────┐
│ titlebar:  company [fiscal year]  │  current-view chip   │
├──────────────────────────────────────────────────────────┤
│ ┌─ Sidebar ──┬─ Main ──────────────────────────────────┐ │
│ │ Aseel menu │ ┌─ AseelDocumentShell ────────────────┐ │ │
│ │ tree       │ │ titlebar (per-doc) + state          │ │ │
│ │            │ │ toolbar: ⏪ ⏮ ⏯ ⏭ ⏩ │ إضافة │ ⋯ │ │ │
│ │            │ ├─────────────────────────────────────┤ │ │
│ │            │ │ header band: dense fields           │ │ │
│ │            │ ├─────────────────────────────────────┤ │ │
│ │            │ │ gridwrap: AseelGrid (items/journal) │ │ │
│ │            │ ├─────────────────────────────────────┤ │ │
│ │            │ │ tabs ║ totals dock                  │ │ │
│ │            │ ├─────────────────────────────────────┤ │ │
│ │            │ │ statusbar (per-doc)                 │ │ │
│ │            │ └─────────────────────────────────────┘ │ │
│ └────────────┴─────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────┤
│ statusbar (global): user │ role │ date │ connection      │
└──────────────────────────────────────────────────────────┘
```

---

## [ARCHITECTURE]

### Primitives موجودة من M0 (يَستخدمها كل ما يأتي):

| Primitive | الموقع | الغرض |
|-----------|--------|------|
| `AseelDocumentShell` | `aseel/AseelDocumentShell.tsx` | إطار document كامل |
| `AseelGrid<T>` | `aseel/AseelGrid.tsx` | جدول كثيف (items/journal variants) |
| `AseelIndexPicker<T>` | `aseel/AseelIndexPicker.tsx` | فهرس منبثق |
| `useRecordNavigation` | `aseel/useRecordNavigation.ts` | التنقّل بين السجلات |
| `useAseelKeymap` | `aseel/useAseelKeymap.ts` | اختصارات الكيبورد |
| `aseel-field/input/...` classes | `styles/index.css` | tokens |

### Primitives جديدة (N1-T1..T6):

| Primitive | الغرض | الـRefs |
|-----------|------|---------|
| `AseelFormSection` | صندوق فرعي بإطار رفيع داخل tab content | الفواتير.txt:51-92 |
| `AseelDenseTable<T>` | list page table (يَستبدل DataGrid) | المحاسبة.txt:48-69 |
| `AseelReportTable<T>` | تقرير بشريط فلاتر + footer مجاميع | التقارير.txt:1-30 |
| `AseelStatusBarItem` | helper type-safe للـstatus items | اللقطات |
| `useAseelIndexKeymap` | hook منفصل لـlist pages (F2-F4 drill، Ctrl+nav) | المحاسبة.txt:48-69 |
| `useAseelFieldShortcuts` | Space/*/-/+ on focused fields | الفواتير.txt:38-43, 62 |

### Models جديدة (N0 + N8):

| Model | App | الغرض | الـRef |
|-------|-----|------|-------|
| `TenantSettings` | tenants | Group Constants (ثوابت المجموعة) | الأدوات.txt:10-101 |
| `TenantBook` | tenants | 10 books per doc type | الأدوات.txt:62-100 |
| `Account.nature` field | accounting | debit-only/credit-only/both | المحاسبة.txt:94-100 |
| `Account.cost_center_default` | accounting | per-account default | الجديد:152-153 |
| `Partner.default_cost_center` | partners | per-partner default | الجديد:152 |
| `Partner.end_of_dealing_date` | partners | warn on transactions after | الجديد:157 |
| `Partner.assigned_price_tier` | partners | 1-5 sale tier assignment | المخازن.txt:78-85 |
| `Product.price_tiers` (5 sale + 5 purchase) | inventory | multi-tier pricing | المخازن.txt:78-85 |
| `Product.account_overrides` | inventory | per-item account overrides | المخازن.txt:86-100 |
| `SalesInvoice.invoice_kind` | sales | sale/sale_return/purchase/purchase_return | الفواتير.txt:1-8 |
| `SalesInvoice.original_invoice` FK | sales | for returns | الفواتير.txt:1-8 |
| `SupplierPayment` model | sales (or new app `payments`) | mirror CustomerPayment | المعاملات.txt:1-80 |
| `VatStatement` model | accounting | periodic VAT report | الفواتير.txt:75-78 |
| `ChequeMovement` model | accounting | full cheque lifecycle audit | الشيكات.txt:43-67 |

### Hybrid policy:

- **`data-skin="aseel"` global** (مُطبَّق في M5-T1).
- **Tokens-driven:** كل لون عبر `var(--aseel-*)` أو `var(--color-*)`.
- **No raw hex** داخل الـscreens (مسموح في `components/ui/*` legacy و
  `App.tsx`). يَفحَص N9-T1 بـgrep.
- **Backend:** كل ترحيل عبر `post_journal()` الموجود. لا engine جديد.

---

## [ORPHANS & PENDING]

### Frontend pages (51 صفحة، حالة كل واحدة)

#### Forms (يَحتاج rebuild inside-out):

| # | الصفحة | حالة | يَحتاج |
|---|--------|-----|--------|
| F1 | `procurement/deals/DealForm.tsx` | shell-only (M3-T1) | inside-out (N2-T1) |
| F2 | `procurement/shipments/ShipmentForm.tsx` | shell-only (M3-T2) | inside-out (N2-T2) |
| F3 | `procurement/clearance/CustomsClearanceManagement.tsx` | shell-only (M3-T4) | inside-out (N2-T3) |
| F4 | `procurement/invoices/InvoiceForm.tsx` | shell-only (M4-T1) | inside-out (N2-T4) |
| F5 | `procurement/price-offers/PriceOfferForm.tsx` | لم يُمَس | كامل (N5-T7) |
| F6 | `items/ItemForm.tsx` | لم يُمَس | 6 pages tabs (N5-T4) |
| F7 | `accounting/AccountingJournalEntryPage.tsx` | shell-only (M4-T2) | inside-out مع Space=balance (N3-T1) |
| F8 | `sales/SalesInvoiceEditor.tsx` | ✅ مكتمل M1 — قالب ذهبي | — |
| F9 | `sales/SalesCustomerPaymentsPage.tsx` | shell-only (M4-T3) | inside-out + source-discount (N4-T4) |
| F10 | `sales/CreditDebitNotesPage.tsx` | shell-only (M4-T4) | inside-out + VAT calc + statement (N4-T5) |
| F11 | `sales/SalesQuotationsPage.tsx` | shell-only (M4-T5) | inside-out + valid-until (N4-T6) |
| F12 | `LoginPage.tsx` | لم يُمَس | يَبقى — خارج النطاق |
| F13 | `SignupPage.tsx` | لم يُمَس | يَبقى — خارج النطاق |

#### List/Management pages (تَستخدم AseelDenseTable):

| # | الصفحة | يَحتاج |
|---|--------|--------|
| L1 | `procurement/DealManagement.tsx` | DenseTable (N6-T1) |
| L2 | `procurement/shipments/ShipmentManagement.tsx` | DenseTable (N6-T2) |
| L3 | `procurement/PriceOfferManagement.tsx` | DenseTable (N5-T6) |
| L4 | `items/ItemsManagement.tsx` | DenseTable (N5-T3) |
| L5 | `suppliers/SupplierManagement.tsx` | DenseTable + dedupe with L6 (N5-T5) |
| L6 | `SupplierManagement.tsx` (root) | **يُحذَف** — duplicate (N5-T5) |
| L7 | `sales/SalesInvoicesPage.tsx` | DenseTable (N4-T1) |
| L8 | `sales/SalesCustomersPage.tsx` | DenseTable (N4-T2) |
| L9 | `sales/SalesSettingsPage.tsx` | يَبقى UI الحالي (settings مختلف) |
| L10 | `logistics/LocalShippingPage.tsx` | DenseTable (N6-T3) |
| L11 | `inventory/StockLevelsPage.tsx` | DenseTable (N5-T1) |
| L12 | `inventory/StockMovementsPage.tsx` | DenseTable (N5-T2) |
| L13 | `realestate/PropertyRentalPage.tsx` | DenseTable (N7-T9) |
| L14 | `accounting/AccountingChequesPage.tsx` | DenseTable + lifecycle (N3-T4) |
| L15 | `accounting/AccountingJournalListPage.tsx` | DenseTable (N3-T2) |
| L16 | `accounting/AccountingCoaPage.tsx` | شجرة Aseel (N3-T3) |
| L17 | `accounting/FiscalPeriodsPage.tsx` | DenseTable (N3-T5) |
| L18 | `accounting/ExchangeRatesPage.tsx` | DenseTable (N3-T6) |
| L19-L22 | `sql/Sql*Page.tsx` | DenseTable (N7-T8) |

#### Reports (تَستخدم AseelReportTable):

| # | الصفحة | يَحتاج |
|---|--------|--------|
| R1 | `accounting/AccountingGeneralLedgerPage.tsx` | ReportTable (N3-T7) — **الأهم** |
| R2 | `accounting/AccountingTrialBalancePage.tsx` | ReportTable (N3-T8) |
| R3 | `accounting/AccountingVatReportPage.tsx` | ReportTable (N3-T9) |
| R4 | `accounting/AccountingLandedCostPage.tsx` | ReportTable (N3-T10) |
| R5 | (new) Balance Sheet (الميزانية العمومية) | جديد (N3-T11) |
| R6 | (new) Income Statement (كشف الإيرادات والمصروفات) | جديد (N3-T12) |
| R7 | (new) Inventory Valuation (قيمة البضاعة) | جديد (N5-T8) |

#### HR/Admin/Misc:

| # | الصفحة | يَحتاج |
|---|--------|--------|
| H1 | Dashboard | KPI cards بـAseel summary (N7-T1) |
| H2 | `TaskManagement.tsx` | DenseTable (N7-T2) |
| H3 | `AttendanceManagement.tsx` | DenseTable (N7-T3) |
| H4 | `EmployeePointsManagement.tsx` | DenseTable (N7-T4) |
| H5 | `PointsHistoryPage.tsx` | DenseTable (N7-T5) |
| H6 | `SettingsPage.tsx` | يَبقى — system settings مختلف |
| H7 | `SmartAssistantPage.tsx` | يَبقى — AI chat خارج النطاق |
| H8 | `ResultsPage.tsx` | DenseTable (N7-T6) |
| H9-H10 | `store/*` | يَبقى — متجر علني خارج نطاق Aseel |

#### Pages جديدة (لم تُنشَأ بعد):

| # | الصفحة | الـMilestone |
|---|--------|--------------|
| N-F1 | `GroupConstantsPage.tsx` (ثوابت المجموعة F11) | N0-T4 |
| N-F2 | `SalesReturnEditor.tsx` (مرجع البيع) | N4-T7 |
| N-F3 | `PurchaseReturnEditor.tsx` (مرجع الشراء) | N4-T8 |
| N-F4 | `SupplierPaymentsPage.tsx` (سند صرف) | N4-T9 |
| N-F5 | `VatStatementsPage.tsx` (كشف ض.ق.م) | N3-T13 |
| N-F6 | `BalanceSheetPage.tsx` (الميزانية العمومية) | N3-T11 |
| N-F7 | `IncomeStatementPage.tsx` (الإيرادات والمصروفات) | N3-T12 |
| N-F8 | `InventoryValuationPage.tsx` (قيمة البضاعة) | N5-T8 |
| N-F9 | `ChequeTransferDialog.tsx` (تحويل الشيكات) | N3-T4 |

### Backend gaps (10 موديلات/services جديدة)

| # | البند | الـMilestone |
|---|-------|--------------|
| B1 | `TenantSettings` model + migration | N0-T1 |
| B2 | `TenantBook` model + `next_document_number()` helper | N0-T2..T3 |
| B3 | `Account.nature` field | N8-T6 |
| B4 | `Account.default_cost_center` | N8-T7 |
| B5 | `Partner.default_cost_center` + `end_of_dealing_date` + `assigned_price_tier` | N8-T8 |
| B6 | `Product.price_tiers` (10 tiers + currency + tax-flag) | N8-T9 |
| B7 | `Product.account_overrides` (sale/sale-return/purchase/...) | N8-T10 |
| B8 | `SalesInvoice.invoice_kind` + `original_invoice` (Sales/Purchase Return) | N8-T11 |
| B9 | `SupplierPayment` model + `post_supplier_payment()` service | N8-T12 |
| B10 | `VatStatement` model + `vat_statement` FK on invoices + builder | N8-T13 |
| B11 | `ChequeMovement` model + lifecycle service | N8-T14 |
| B12 | `next_deal/shipment/clearance_number(tenant_id, book_number)` helpers | N8-T15 |

---

## Milestones N0..N10

> **القاعدة الذهبية:** قبل بدء **أي** task، اقرأ M1's
> `SalesInvoiceEditor.tsx` — هو القالب. ثم اقرأ الـ Aseel reference المرفق
> بـtask.

### N0 — Foundation: ثوابت المجموعة + F-key reconciliation + field shortcuts

> الأساس الذي تَعتمد عليه كل الـNs اللاحقة.
> **Verifiable goal:** F11 يَفتح صفحة ثوابت المجموعة من أي مكان؛
> useAseelKeymap+useAseelIndexKeymap+useAseelFieldShortcuts صحيحة؛
> `tsc` ≤ 78؛ `vite build` 0.

- [ ] **N0-T1 — `TenantSettings` model + migration.** Backend. حقول:
  `company_name_primary`، `company_name_sub`، `address`، `po_box`، `phone`،
  `fax`، `email`، `licensed_dealer_no` (للشركة)، `income_tax_file_no`،
  `default_vat_rate`، `default_source_discount_rate`، `currency` (FK)،
  `fiscal_period_label`، `fiscal_period_start`، `fiscal_period_end`،
  `default_freight_credit_account` (FK Account)، 
  `mixture_auto_fill_enabled`، `barcode_action` (مفتاح/قراءة الباركود يَفتح
  فاتورة كاشير أم فهرس). one-to-one مع Tenant. المرجع:
  `الأدوات.txt:10-101`.

- [ ] **N0-T2 — `TenantBook` model + migration.** PK مركَّب
  `(tenant_id, document_type, book_number)`. document_type choices:
  `sales_invoice`, `purchase_invoice`, `sales_return`, `purchase_return`,
  `receipt_voucher`, `payment_voucher`, `multi_receipt`, `multi_payment`,
  `credit_note`, `debit_note`, `quotation`, `journal_entry`,
  `deal`, `shipment`, `clearance`. حقول: `name`، `last_used_number`،
  `is_active`. مرجع: `الأدوات.txt:62-100`.

- [ ] **N0-T3 — `next_document_number(tenant_id, document_type, book_number=0)`
  helper موحَّد** في `accounting/services.py`. مع `select_for_update` لكل
  `TenantBook` row. الـhelpers الموجودة (`next_invoice_number`،
  `next_credit_debit_note_number`) تَصير thin wrappers تُمرّر للـcanonical.

- [ ] **N0-T4 — `GroupConstantsPage.tsx` (frontend).** صفحة Aseel-style
  بـ`AseelDocumentShell`، 4 tabs:
  1. **بيانات عامة** — كل حقول `TenantSettings`.
  2. **أرقام الدفاتر** — جدول `AseelGrid` يَعرض كل `TenantBook` (10
     افتراضية لكل document_type، قابلة للتعديل: name + last_used_number +
     is_active).
  3. **حسابات افتراضية** — يَنقل من `SalesSettings`.
  4. **ضرائب** — يَنقل من `SalesSettings`.
  مرجع: `الأدوات.txt:10-200`.

- [ ] **N0-T5 — F11 routing.** في `AppLayout.tsx`، أَضِف keymap عام
  (`useEffect` + `window.addEventListener('keydown')`) يَستجيب لـF11 ⇒
  يَفتح `GroupConstantsPage` كـmodal portal. لا تَتعارض مع form-level
  keymaps.

- [ ] **N0-T6 — تَوسيع `useAseelKeymap` (form context).** أَضِف:
  - `F4: reviewShipment?: () => void` — **مراجعة الإرسالية المرافقة**
    (استبدل أي F4=duplicate في M1-M5).
  - `F5: sortBy?: () => void`.
  - `Alt+F4: exitForm?: () => void`.
  - `Ctrl+Home/End/PageUp/PageDown: nav navigation` (يَستخدم
    `useRecordNavigation`).
  - `Ctrl+Ins: addNew?`.
  - `Ctrl+Del: deleteCurrent?`.
  مرجع: `الفواتير.txt:207-229`.

- [ ] **N0-T7 — `useAseelIndexKeymap` hook جديد (list/index context).**
  في `aseel/useAseelIndexKeymap.ts`. callbacks مختلفة عن form:
  - `F2: drillToLedger?` — حركات المحاسبة للسجل المُحدَّد.
  - `F3: drillToStock?` — حركات المخازن.
  - `F4: showNotes?` — ملاحظات السجل.
  - `F5: sortBy?`, `F6: search?`.
  - `Ctrl+Home/End/PageUp/PageDown/Ins/Del` نفس forms.
  - `Enter: openRecord?` — يَفتح الـrecord في form mode.
  - مرجع: `المحاسبة.txt:48-69`.

- [ ] **N0-T8 — `useAseelFieldShortcuts` hook جديد.** field-level keyboard
  helpers يُستدعى داخل input handlers أو عبر `data-aseel-field` attribute:
  - `data-aseel-field="date"` + `*` ⇒ +1 day; `-` ⇒ −1 day.
  - `data-aseel-field="remaining-amount"` + Space ⇒ autofill with computed
    remaining.
  - `data-aseel-field="voucher-link"` + `*` ⇒ open attached voucher.
  - `data-aseel-field="account-number"` + `*` ⇒ next account; `-` ⇒ prev.
  - `data-aseel-field="item-number"` + `+` (alone) ⇒ next available number;
    `+<num>` ⇒ next available after num.
  مرجع: `الفواتير.txt:38-43, 62`, `المخازن.txt:30-32`.

- [ ] **N0-T9 — `AseelStatusBarItem` primitive.** في
  `aseel/AseelStatusBarItem.tsx`. props: `label`, `value`, `icon?`. يَختصر
  التكرار في 30+ صفحة.

- [ ] **N0-T10 — تصدير من `aseel/index.ts` + تَوثيق في
  `AseelKitStory.tsx`.** كل الجدد ظاهرون مع أمثلة حيّة على `/aseel-kit`.

- [ ] **N0-T11 — تَطبيق F-key fixes على M1-M5 الموجودين.** استبدل F4
  placeholders بـ`reviewShipment` في M1 SalesInvoiceEditor + M3-M4 forms.
  أَضِف Ctrl+nav handlers. لا تَكسر أي شيء (smoke test في المتصفّح).

---

### N1 — جديد primitives (Form section / Dense table / Report table)

> Verifiable: 4 components جديدة موجودة، يُستخدمون في `/aseel-kit`،
> tsc 76≤78، build 0.

- [ ] **N1-T1 — `AseelFormSection` primitive.** صندوق فرعي بإطار
  `var(--aseel-border-soft)`، عنوان رمادي `var(--aseel-ink-soft)`، grid
  داخلي 2-3 أعمدة auto-fit. props: `title?`، `children`، `cols?`. **يَجب
  يَدعم nested** (form section داخل form section). مرجع:
  `الفواتير.txt:51-92`.

- [ ] **N1-T2 — `AseelDenseTable<T>` primitive.** توسيع `AseelGrid` بـ
  variant=`'list'`. props:
  - `columns: { key, header, width?, align?, render?, sortable?, numeric? }[]`
  - `rows: T[]`
  - `getRowKey: (r) => string|number`
  - `onRowClick?: (r) => void` — double-click opens form
  - `onRowDoubleClick?: (r) => void`
  - `selectable?: boolean` + `selectedKey?` + `onSelect?`
  - `onSort?: (key, dir) => void` + `sortKey?` + `sortDir?`
  - `footer?: ReactNode` (totals row)
  - `pagination?: { page, pageSize, total, onChange }`
  - keymap-integration: emits `addNew/deleteCurrent` events للـconsumer.
  **يَستبدل DataGrid في 7 ملفات** (N4-N7).

- [ ] **N1-T3 — `AseelReportTable<T>` primitive.** للـreports:
  - `filterBar?: ReactNode` (top — date range, account, book filters)
  - `columns` (مع `numeric: true` للأعمدة الرقمية ⇒ يُظهر يمين
    `tabular-nums`)
  - `rows`
  - `totals?` (footer مجاميع الأعمدة الرقمية)
  - `exportable?: boolean` (يَعرض زر export → CSV download).
  مرجع: `التقارير.txt:1-30`.

- [ ] **N1-T4 — `AseelStatusBarItem`.** (نُقل من N0-T9 لـN1).

- [ ] **N1-T5 — `AseelDateInput` primitive (optional).** wrapper حول
  `<input type="date">` يُطبّق `useAseelFieldShortcuts` تلقائياً + يُتيح
  double-click على السنة → modal تقويم سنوي. مرجع: `الجديد:111`.

- [ ] **N1-T6 — تَصدير + AseelKitStory.** كل الجدد ظاهرون على
  `/aseel-kit` مع amber-highlight + Arabic labels + use cases.

---

### N2 — Procurement forms inside-out (F1-F4)

> Verifiable: 4 forms تَطابق لقطة الأصيل بنياً (cream/dense/grid)؛ صفر
> regression في dealsService/shipmentsApi/purchaseInvoiceApi؛ متصفّح حيّ
> ينجح؛ DOM verification.

> **القالب الذهبي:** `frontend_v2/components/sales/SalesInvoiceEditor.tsx`
> (M1). اقرأه كل مرة قبل بدء form جديد.

- [ ] **N2-T1 — `DealForm.tsx` inside-out.** استبدال الـJSX الداخلي:
  - **شريط رأس Aseel** (16-18 حقل في `AseelFormSection` "بيانات الصفقة"):
    رقم الصفقة (auto + book_number)، تاريخ، الساعة، تاريخ ثاني، تاريخ
    الاستحقاق، المورد (data-aseel-field="account-number"، + للفهرس)،
    الاسم، العنوان، مشتغل مرخص، طريقة الشحن، نوع الشحن، الحالة، Aseel
    extras (price_tier override، supplier_default_cost_center).
  - **بنود في `AseelGrid` items variant** (إن لم يَكن للـDeal بنود
    تَعرَف، أَضِف Deal items linked to Product).
  - **tabs السفلية:**
    - `الملاحظات` (textarea)
    - `الحسابات / مركز التكلفة` (journal preview — استخدم
      `journalPreview` نمط M1)
    - `أقساط الدفع` (InstallmentManager existing — wrap بـAseelFormSection)
    - `الشحن/الإرسالية` (link إلى Shipment إن وُجد + زر "ربط/إنشاء شحنة")
    - `بيانات أخرى` (config notes)
  - **totals dock:**
    - مجموع البنود (قبل الخصم)
    - الخصم
    - المجموع قبل الضريبة
    - الضريبة المضافة
    - مبلغ الصفقة الإجمالي
    - المدفوع
    - المتبقي
  - **status bar:**
    - المستخدم / رقم القيد / رقم الصفقة / المرحلة / السجل n/N / آخر مفتاح
  - **toolbar actions:**
    - إضافة (Ctrl+Ins) / تخزين (F12) / حذف (Ctrl+Del) / إلغاء (Esc) /
      طباعة (F2) / مراجعة الإرسالية (F4) / ترتيب (F5) / بحث (F6)
  - **API:** `dealsService.createDeal/updateDeal/getDeal` بلا تغيير.
  - مرجع: `الإرساليات.txt:1-34` + `intro.txt:52-55` + لقطة فواتير الشراء.

- [ ] **N2-T2 — `ShipmentForm.tsx` inside-out.** المرجع الأهم لـKTRA
  (الأصيل عنده «إرسالية» بنفس المفهوم):
  - **شريط رأس Aseel** (18-22 حقل):
    رقم الإرسالية (auto + book_number)، تاريخ، الساعة، تاريخ ثاني،
    رقم الحركة، رقم الفاتورة (read-only — إن تَحوَّلت لفاتورة)،
    المورد/المستورد (+ فهرس)، الاسم، العنوان، مشتغل مرخص، **نوع
    الإرسالية** (فاتورة / نقل — موجود M3-T2)، طريقة الشحن، رقم البوليصة،
    رقم الحاوية، تاريخ المغادرة، تاريخ الوصول، الحالة.
  - **في حالة نوع=نقل** (`shipment_type='transport'`)، أَظهِر بـ
    AseelFormSection "بيانات النقل المحلي":
    - السائق (+ فهرس) / الاسم / رقم السيارة / أجرة نقل الوحدة / أجرة
      نقل الكمية / عملة أجرة النقل / سعر العملة / حساب أجرة النقل (+
      فهرس) / رقم القيد (read-only).
    - مرجع: `الإرساليات.txt:91-109`.
  - **بنود في `AseelGrid`** (إن وُجد على Shipment، وإلا اربط بـDeal).
  - **tabs:**
    - الصفقات المرفقة (`ShipmentDealsTable` موجود — wrap)
    - تفاصيل الشحن البحري/الجوي (form section)
    - النقل المحلي (`AseelGrid` للسجلات + زر "إضافة سجل" يَفتح inline
      editor)
    - الدفعات (موجود)
    - الحسابات (journal preview)
  - **totals dock:** تكلفة الشحن / الحجم / الوزن / أجرة النقل / المدفوع /
    المتبقي.
  - **زر «تكوين فاتورة»** — مُقيَّد بـ`shipment_type !== 'transport'`
    (موجود M3-T5، يَبقى).
  - مرجع: `الإرساليات.txt:6-155`.

- [ ] **N2-T3 — `CustomsClearanceManagement.tsx` inside-out.**
  - **شريط رأس Aseel** (12-14 حقل):
    رقم البيان (auto + book_number)، تاريخ، الساعة، تاريخ ثاني، رقم
    القيد (read-only)، **كشف الضريبة** (read-only — N0-T13 VAT statement)،
    المخلِّص (+ فهرس)، الاسم، العنوان، مشتغل مرخص، رقم فاتورة المقاصة.
  - **`AseelGrid` variant=`journal`** بأعمدة:
    `seq` / `account_no` (+ فهرس) / `account_name` (read-only) / `desc`
    / `debit` / `credit` / `vat_percent` (إن سالب ⇒ credit) /
    `cost_center`.
  - **tabs:**
    - الإرساليات المرافقة (`AseelGrid` select-mode — يَربط
      LogisticsClearance بـShipment(s))
    - الحسابات (journal preview)
    - بيانات أخرى
  - **totals:** المجموع بدون ضريبة (مدين − دائن) / مجموع الضريبة / مبلغ
    البيان الإجمالي.
  - **زر ترحيل** — مسار landed-cost الموجود بلا تغيير.
  - مرجع: `الإرساليات.txt:162-214`.

- [ ] **N2-T4 — `InvoiceForm.tsx` (purchase) inside-out.** نظير M1
  لـفواتير الشراء:
  - **شريط رأس Aseel** (15-18 حقل):
    رقم الفاتورة (يدوي — لأن purchase invoices في الأصيل يدوية)، دفتر،
    تاريخ، الساعة، تاريخ ثاني، تاريخ الاستحقاق، المورد (+ فهرس)، الاسم،
    العنوان، مشتغل مرخص، رقم المستند، عملة، سعر العملة، الأسعار تشمل
    ض.ق.م، المخزن.
  - **بنود `AseelGrid`** بأعمدة: مسلسل / رقم الصنف (+ فهرس) / كتلوج /
    اسم / بيان / الوحدة / المخزن / الكمية / إضافي / سعر الوحدة / خصم
    سطر / الضريبة / السعر الإجمالي.
  - **tabs:** الملاحظات / الحسابات/مركز التكلفة / بيانات أخرى /
    المرفقات.
  - **totals:** مجموع البنود / خصم / المجموع قبل الضريبة / الضريبة /
    مدفوع نقدا / مدفوع شيكات / مبلغ الفاتورة / متبقي.
  - **status bar:** المستخدم / رقم القيد / رقم الحركة / كشف الضريبة /
    السجل n/N.
  - **F3 = سند الصرف المرفق** (modal للـSupplierPayment — يَنتظر N8-T12).
    إن SupplierPayment غير جاهز بعد، الـ button placeholder.
  - مرجع: `الفواتير.txt:1-200`.

---

### N3 — Accounting (F7 + L14-L18 + R1-R6 + N-F5 + N-F6 + N-F7)

> 13 task. القلب المحاسبي على نمط الأصيل.

- [ ] **N3-T1 — `AccountingJournalEntryPage.tsx` (F7) inside-out.**
  المرجع البصري الأهم (لقطة المالك «مراجعة قيود المحاسبة»):
  - **شريط رأس:** رقم القيد، التاريخ، الساعة، تاريخ ثاني، البيان الإجمالي،
    المرجع (reference_type + reference_id)، العملة، سعر العملة.
  - **`AseelGrid` variant=`journal`** بأعمدة:
    مسلسل / رقم الحساب (+ فهرس) / اسم الحساب (read-only) / البيان /
    مدين / دائن / مركز التكلفة (+ فهرس) / البيان التفصيلي.
  - **اختصارات خاصة:**
    - **Space على debit/credit** ⇒ يَوازن السطر تلقائياً (يَحسب الفرق
      من الأسطر السابقة).
    - **`*` على رقم الحساب** ⇒ يَفتح رصيد الحساب inline tooltip.
    - **`+` على رقم الحساب** ⇒ يَفتح `AseelIndexPicker` للحسابات.
  - **footer:** مجموع مدين / مجموع دائن / الفرق (يَجب 0).
  - **F12 = ترحيل** عبر `post_journal()` الموجود.
  - مرجع: `المحاسبة.txt:149-206`.

- [ ] **N3-T2 — `AccountingJournalListPage.tsx` (L15).** يُطابق اللقطة
  الأولى من المالك حرفياً:
  - **`AseelDenseTable`** بأعمدة: رقم القيد / تاريخ القيد / الساعة /
    مبلغ القيد / عملة القيد / بيان القيد الإجمالي / المستخدم.
  - **شريط فلاتر علوي:** من تاريخ - إلى تاريخ / دفتر / حساب / مستخدم.
  - **useAseelIndexKeymap:** F2=drillToLedger (لـreference إن وُجد)،
    F6=search، Ctrl+Ins=new (يَفتح F7).
  - مرجع: لقطة المالك + `المحاسبة.txt:48-69`.

- [ ] **N3-T3 — `AccountingCoaPage.tsx` (L16).** شجرة COA Aseel-style:
  - عمود الكود / الاسم / النوع / الطبيعة (N8-T6) / الرصيد المدين /
    الرصيد الدائن / الرصيد الصافي.
  - شجرة قابلة للطيّ (لا cards، table-like nested rows).
  - افتراضياً موسّعة لـ3 مستويات.
  - useAseelIndexKeymap: F2=drillToLedger، F4=showNotes (account notes
    — N8-T7).
  - مرجع: `المحاسبة.txt:30-100`.

- [ ] **N3-T4 — `AccountingChequesPage.tsx` (L14).**
  - **`AseelDenseTable`** للشيكات بأعمدة: رقم الشيك / البنك / الفرع /
    المبلغ / تاريخ الاستحقاق / تاريخ الإصدار / الشريك / الحساب / الحالة /
    الاتجاه.
  - **شريط فلاتر:** حالة / تاريخ استحقاق من-إلى / شريك / اتجاه.
  - **زر «تحويل الشيك» (N-F9 ChequeTransferDialog)** — modal لتحويل
    شيك من حالة إلى أخرى (Under_Collection → Collected/Bounced/Returned).
    يُسجِّل في `ChequeMovement` (N8-T14).
  - مرجع: `الشيكات.txt:1-68`.

- [ ] **N3-T5 — `FiscalPeriodsPage.tsx` (L17).** DenseTable + أزرار
  «إقفال»/«إعادة فتح» Aseel-style toolbar.

- [ ] **N3-T6 — `ExchangeRatesPage.tsx` (L18).** DenseTable + شريط فلاتر
  (عملة).

- [ ] **N3-T7 — `AccountingGeneralLedgerPage.tsx` (R1).** **التقرير
  الأهم:**
  - **`AseelReportTable`** بشريط فلاتر (حساب + من-إلى تاريخ + دفتر +
    عملة).
  - أعمدة: التاريخ / رقم القيد / البيان / المدين / الدائن / الرصيد
    التراكمي / رقم القيد المرجعي.
  - footer: مجموع مدين / مجموع دائن / الرصيد النهائي.
  - زر export → CSV.
  - مرجع: `التقارير.txt:13-26`.

- [ ] **N3-T8 — `AccountingTrialBalancePage.tsx` (R2).** ReportTable +
  فلاتر (تاريخ + فرع). أعمدة: كود / اسم / النوع / مدين / دائن. footer:
  مجموع مدين = مجموع دائن (validation). مرجع: `التقارير.txt:20`.

- [ ] **N3-T9 — `AccountingVatReportPage.tsx` (R3).** ReportTable
  بقسمين: ضريبة مخرجات (sales+returns) / ضريبة مدخلات (purchases+returns)
  / الصافي. فلاتر: فترة. مرجع: `التقارير.txt:51`.

- [ ] **N3-T10 — `AccountingLandedCostPage.tsx` (R4).** ReportTable
  للـlanded-cost الموجود. فلاتر: شحنة/صفقة/فترة. أعمدة الصنف وحصّته من
  الشحن والتخليص + footer.

- [ ] **N3-T11 — `BalanceSheetPage.tsx` (R5، جديد).** الميزانية العمومية
  + الكشوف المرافقة (مدينون، دائنون، تشغيل، متاجرة، أرباح/خسائر،
  إيرادات/مصروفات). فلاتر: تاريخ as-of + عملة + فرع. مرجع:
  `التحاليل المالية.txt:33-80`.

- [ ] **N3-T12 — `IncomeStatementPage.tsx` (R6، جديد).** كشف الإيرادات
  والمصروفات — periodic، يَجمع الفواتير في الفترة + يَحجز/يَستثني فواتير.
  حقول: رقم الكشف، التاريخ، البيان، المبلغ، الضريبة. مرجع:
  `الإيرادات والمصروفات.txt:1-34`.

- [ ] **N3-T13 — `VatStatementsPage.tsx` (N-F5، جديد).** كشف الضريبة
  المضافة الدوري:
  - DenseTable للكشوف السابقة (رقم الكشف / فترة / إجمالي ضريبة /
    الحالة).
  - زر «كشف جديد» يَفتح form بـ AseelDocumentShell: تاريخ بداية - نهاية،
    يَجمع الفواتير في الفترة مع `vat_statement IS NULL`، يَسمح
    بتفعيل/إلغاء تفعيل كل فاتورة، يُولّد `vat_statement_no`.
  - مرجع: `الفواتير.txt:75-78` + الجديد:18.

---

### N4 — Sales sub-pages (L7-L9 + F9-F11 + N-F2 + N-F3 + N-F4)

> 9 tasks: 3 list + 4 form inside + 2 new docs (Sales Return، Purchase Return).

- [ ] **N4-T1 — `SalesInvoicesPage.tsx` (L7).** DenseTable + فلاتر +
  Ctrl+Ins يَفتح `SalesInvoiceEditor`. أعمدة: رقم / تاريخ / العميل /
  النوع / الحالة / الإجمالي / المدفوع / المتبقي / الكشف / إجراءات.

- [ ] **N4-T2 — `SalesCustomersPage.tsx` (L8).** DenseTable للعملاء +
  حقول Partner الجديدة (default_cost_center، end_of_dealing_date،
  assigned_price_tier — N8-T8).

- [ ] **N4-T3 — `SalesSettingsPage.tsx` (L9).** يَبقى مع تحديث: نقل
  الحقول العامة لـ`GroupConstantsPage` (N0-T4) — تَبقى الحسابات
  الافتراضية المتعلّقة بالمبيعات.

- [ ] **N4-T4 — `SalesCustomerPaymentsPage.tsx` (F9) inside-out.** شاشة
  سند قبض Aseel-style:
  - **شريط رأس:** دفتر، رقم السند، التاريخ، الساعة، تاريخ ثاني، العملة،
    السعر، العميل (+ فهرس)، الاسم، العنوان، مشتغل مرخص، رقم القيد،
    الصندوق (+ فهرس).
  - **حقول مالية:** مجموع الشيكات (auto from grid)، المبلغ نقدا (Space
    autofill = remaining)، المجموع، **نسبة خصم المصدر**، **مبلغ خصم
    المصدر** (في السند نفسه!)، مبلغ الحساب (remaining).
  - **`AseelGrid` للشيكات** (تفاصيل السند) بأعمدة: مسلسل / رقم الشيك /
    اسم صاحب الشيك / تاريخ استحقاق / المبلغ / عملة / السعر / حساب الشيك
    (+ فهرس) / اسم الحساب / البيان / اسم البنك / الفرع.
  - **tabs:** الملاحظات / الحسابات / بيانات أخرى.
  - **F12 = ترحيل**؛ **زر «اقتراح FIFO»** (موجود) + **زر «تعبئة شيكات
    متشابهة متكرّرة»** (الجديد:29 — feature لتعبئة شيكات بنفس البنك/المبلغ
    لشهور متتالية).
  - مرجع: `المعاملات المالية.txt:1-80`.

- [ ] **N4-T5 — `CreditDebitNotesPage.tsx` (F10) inside-out.**
  - **شريط رأس:** دفتر، رقم الإشعار، التاريخ، الساعة، تاريخ ثاني، رقم
    القيد، **كشف الضريبة** (N3-T13)، الحساب (العميل/الزبون، + فهرس)،
    الاسم، العنوان، مشتغل مرخص، **رقم فاتورة المقاصة** (الفاتورة
    المرتبطة)، **حساب الإشعار** (+ فهرس)، عملة الإشعار، السعر، النوع
    (مدين/دائن).
  - **حقول المبلغ:**
    - المبلغ (مع Space autofill من رصيد الحساب)
    - يشمل قيمة الضريبة المضافة (checkbox)
    - المبلغ (بدون ضريبة) — read-only أو manual بحسب checkbox
    - نسبة الضريبة المضافة
    - مبلغ الضريبة
    - مبلغ الإشعار الإجمالي
  - **tabs:** الملاحظات / الحسابات (journal preview).
  - مرجع: `الإشعارات.txt:1-65`.

- [ ] **N4-T6 — `SalesQuotationsPage.tsx` (F11) inside-out.**
  - **شريط رأس:** دفتر، رقم العرض، التاريخ، الساعة، تاريخ ثاني،
    **فعال حتى تاريخ**، **فعال** (checkbox)، الزبون (+ فهرس)، الاسم،
    العنوان، مشتغل مرخص، الأسعار تشمل ض.ق.م، عملة، سعر العملة.
  - **بنود `AseelGrid`** بأعمدة: مسلسل / رقم الصنف (+ فهرس) / كتلوج /
    اسم / بيان / الوحدة / المخزن / الكمية / إضافي / سعر الوحدة / خصم
    سطر / الضريبة % / السعر الإجمالي / **تاريخ ثاني** (الجديد:196).
  - **totals:** مجموع بدون ضريبة / الخصم / نسبة الخصم / مبلغ الخصم
    النسبي / المجموع بعد الخصم / نسبة ض.ق.م / مبلغ الضريبة / مبلغ
    العرض الإجمالي.
  - **toolbar:** «تحويل لفاتورة» (يَستخدم `convertQuotationToInvoice`
    الموجود) + «تحويل لإرسالية» (جديد إن وقت يَسمح، وإلا لـN10).
  - مرجع: `العروض والطلبيات.txt:1-83`.

- [ ] **N4-T7 — `SalesReturnEditor.tsx` (N-F2، جديد).** «مرجع البيع» —
  وثيقة كاملة:
  - نفس `SalesInvoiceEditor` بنياً مع `invoice_kind='sale_return'` +
    `original_invoice` FK + (اختياري) نَسخ البنود من الأصلية.
  - post: يَعكس قيد الفاتورة الأصلية + يُعيد للمخزون + يُرجع للمدفوع
    (Dr Sales Return Revenue / Cr AR).
  - depends on N8-T11 backend.
  - مرجع: `الفواتير.txt:1-8`.

- [ ] **N4-T8 — `PurchaseReturnEditor.tsx` (N-F3، جديد).** «مرجع
  الشراء» — مثل N4-T7 لكن لـ Purchase. depends on N8-T11.

- [ ] **N4-T9 — `SupplierPaymentsPage.tsx` (N-F4، جديد).** «سند صرف»
  للموردين — مرآة N4-T4 لكن للموردين. depends on N8-T12. مرجع:
  `المعاملات المالية.txt:1-80`.

---

### N5 — Inventory + Items + Suppliers + Price Offers (F5-F6 + L3-L4 + L5 + L11-L12 + N-F8)

> 8 tasks.

- [ ] **N5-T1 — `StockLevelsPage.tsx` (L11).** DenseTable + فلاتر (مخزن
  / فئة / تحت الحد الأدنى / فوق الحد الأقصى). أعمدة: SKU / الاسم /
  المخزن / المتاح / تحت الحجز / المتوفر / السعر / التكلفة.

- [ ] **N5-T2 — `StockMovementsPage.tsx` (L12).** DenseTable + فلاتر.

- [ ] **N5-T3 — `ItemsManagement.tsx` (L4).** DenseTable للأصناف.

- [ ] **N5-T4 — `ItemForm.tsx` (F6) inside-out.** Aseel-style مع **6
  pages** كما في المخازن.txt:11-25:
  1. **بيانات عامة:** رقم الصنف (+ key)، كتلوج، اسم، بيان، موقع،
     الوحدة الرئيسية + 2 وحدات إضافية + conversion factors.
  2. **الأرصدة والحركات:** رصيد أول المدة (read-only)، مجموع وارد،
     مجموع صادر، الرصيد، **الحد الأدنى**، **الحد الأقصى**، **حد إعادة
     الطلب**، تاريخ آخر حركة.
  3. **أسعار البيع والشراء:** **5 أسعار بيع + 5 أسعار شراء** (كل واحد
     بعملة + tax-inclusive flag) — depends on N8-T9.
  4. **بيانات المتاجرة:** حساب البيع، حساب مرجع البيع، حساب الشراء،
     حساب مرجع الشراء، حساب المورد، حساب بضاعة آخر المدة — depends on
     N8-T10.
  5. **بيانات أخرى:** التصنيف، الكميات الإضافية.
  6. **معادلات التصنيع:** AseelGrid للـ components (item + qty).
  مرجع: `المخازن.txt:1-100`.

- [ ] **N5-T5 — `SupplierManagement.tsx` (L5).** DenseTable + **حذف
  `SupplierManagement.tsx` root (L6 duplicate)** + استبدال كل imports.

- [ ] **N5-T6 — `PriceOfferManagement.tsx` (L3).** DenseTable.

- [ ] **N5-T7 — `PriceOfferForm.tsx` (F5).** Aseel-style مع 4 types
  (incoming/outgoing offer/order) — مرجع: `العروض والطلبيات.txt:4-9`.

- [ ] **N5-T8 — `InventoryValuationPage.tsx` (N-F8، جديد).** قيمة
  البضاعة الموجودة بطرق متعدّدة (FIFO/LIFO/avg-purchase/avg-sale/
  selected-price). فلاتر: مخزن / فرع / تاريخ as-of. مرجع:
  `التحاليل المالية.txt:1-32`.

---

### N6 — Procurement managements (L1-L2 + L10)

- [ ] **N6-T1 — `DealManagement.tsx` (L1).** DenseTable.
- [ ] **N6-T2 — `ShipmentManagement.tsx` (L2).** DenseTable.
- [ ] **N6-T3 — `LocalShippingPage.tsx` (L10).** DenseTable — يَبقى
  المصدر المستقل (T1-01).

---

### N7 — HR/Admin/Misc/SQL (H1-H8 + L19-L22 + L13)

- [ ] **N7-T1 — `Dashboard`.** KPI Aseel-style summary blocks.
- [ ] **N7-T2..T5 — TaskMgmt / AttendanceMgmt / EmployeePointsMgmt /
  PointsHistory.** DenseTable لكل.
- [ ] **N7-T6 — `ResultsPage.tsx`.** DenseTable.
- [ ] **N7-T7 — `SettingsPage.tsx`.** Aseel form sections.
- [ ] **N7-T8 — `sql/Sql*Page.tsx` (4 صفحات).** DenseTable لكل.
- [ ] **N7-T9 — `PropertyRentalPage.tsx` (L13).** DenseTable. منطق
  realestate يَبقى.

---

### N8 — Backend hardening (B1-B12)

> Backend models + services. **كل migration بـnumbering واضح**.

- [ ] **N8-T1..T2 — `TenantSettings` + `TenantBook` migrations.** (نُقل
  لـN0-T1..T2). يَجب يُنفَّذ مع N0.

- [ ] **N8-T3 — `next_document_number()` helper.** (نُقل لـN0-T3).

- [ ] **N8-T4 — Refactor existing helpers** (`next_invoice_number`،
  `next_credit_debit_note_number`) لـthin wrappers حول
  `next_document_number()`. لا breaking changes.

- [ ] **N8-T5 — Migration للـDeal/Shipment/Clearance** لإضافة
  `book_number` (الذي ينقص في Deal و Clearance) + `next_deal_number()`،
  `next_shipment_number()`، `next_clearance_number()` helpers (thin
  wrappers حول N0-T3).

- [ ] **N8-T6 — `Account.nature` field migration.** choices:
  `('debit_only', 'credit_only', 'both')`. validation في
  `post_journal()`: قيد على حساب «مدين فقط» في الـcredit ⇒
  ValidationError. backfill: افتراضي حسب `account_type`.
  مرجع: `المحاسبة.txt:94-100`.

- [ ] **N8-T7 — `Account.default_cost_center` FK + `Account.notes`
  TextField.** للـdrill-down F4 (notes). مرجع: الجديد:152-153.

- [ ] **N8-T8 — `Partner` enrichment migration.** حقول جديدة:
  `default_cost_center` (FK CostCenter)، `end_of_dealing_date` (Date)،
  `assigned_price_tier` (1-5 int)، `password_for_invoices` (CharField،
  nullable — يُتحقَّق منه عند إنشاء فاتورة للعميل). مرجع: الجديد:152-158.

- [ ] **N8-T9 — `Product.price_tiers` migration.** جدول جديد
  `ProductPriceTier(product, tier_type='sale'|'purchase', tier_number=1-5,
  price, currency, tax_inclusive)`. 10 rows لكل product
  (5 sale + 5 purchase). مرجع: `المخازن.txt:78-85`.

- [ ] **N8-T10 — `Product.account_overrides` migration.** 6 nullable
  FK fields: `sale_account_override`، `sale_return_account_override`،
  `purchase_account_override`، `purchase_return_account_override`،
  `supplier_account_override`، `ending_inventory_account_override`.
  منطق resolution في `post_sales_invoice` + `post_purchase_invoice`:
  product override → SalesSettings → fallback. مرجع: `المخازن.txt:86-100`.

- [ ] **N8-T11 — `SalesInvoice.invoice_kind` migration + Sales/Purchase
  Return logic.** حقل `invoice_kind` choices `('sale', 'sale_return',
  'purchase', 'purchase_return')` + `original_invoice` FK self-reference.
  Refactor `post_sales_invoice` ليَتعامل مع كل الأنواع (Return = reverse
  signs). مرجع: `الفواتير.txt:1-8`.

- [ ] **N8-T12 — `SupplierPayment` model + service.** app: `sales` (أو
  جديد `payments`). model: مرآة `CustomerPayment` لكن `partner_type =
  Supplier`. service `post_supplier_payment(payment, user=)`: Dr AP /
  Cr Cash (بدل Dr Cash / Cr AR). شيكات مرفقة بنفس آلية M2-T3. خصم
  مصدر في السند نفسه (مرجع `المعاملات.txt:58-61`). idempotent عبر
  `post_journal()`.

- [ ] **N8-T13 — `VatStatement` model + builder + invoice link.**
  - model: `VatStatement(tenant_id, period_from, period_to, status,
    total_sales_vat, total_purchase_vat, net, statement_number)`.
  - `SalesInvoice.vat_statement` FK + `PurchaseInvoice.vat_statement` FK.
  - service `build_vat_statement(tenant_id, period_from, period_to)`:
    يَجمع الفواتير المرحَّلة في الفترة بـ`vat_statement IS NULL`،
    يُولِّد رقم كشف، يَربط كل فاتورة بالكشف.
  - مرجع: `الفواتير.txt:75-78`.

- [ ] **N8-T14 — `ChequeMovement` model + lifecycle service.**
  - model: `ChequeMovement(cheque, from_account, to_account,
    transfer_date, transfer_amount, new_status, notes, user)`.
  - service `transfer_cheque(cheque_id, new_status, transfer_account?,
    transfer_date, notes, user)`: validates legal status transitions،
    يُسجِّل movement، يُولِّد قيد محاسبي عبر `post_journal()` (Dr
    new_account / Cr old_account).
  - مرجع: `الشيكات.txt:43-67`.

- [ ] **N8-T15 — Audit log consistency.** كل `post_*()` services يَستخدمون
  `create_audit_log(tenant, user, action, model_name, object_id,
  change_details)` بشكل موحَّد. صَنِّف الـactions: POST، UNPOST، VOID،
  TRANSFER.

---

### N9 — System-wide cleanup

- [ ] **N9-T1 — حذف raw hex/Tailwind-named colors من الـscreens.**
  `grep -E '(from-|to-|bg-|text-|border-)(emerald|blue|red|amber|orange|
  teal|cyan|slate|gray|zinc|stone|neutral|sky|violet|purple|fuchsia|
  pink|rose|lime|yellow)-[0-9]'` يَجب يُرجع 0 داخل
  `components/{sales,procurement,accounting,inventory,items,suppliers,
  realestate,sql}/`. الـlegacy `components/ui/*` + `App.tsx` مسموح.

- [ ] **N9-T2 — تَطبيق `AseelStates` (EmptyState/Spinner/ErrorState) في
  كل قائمة وتقرير.** بدلاً من رسائل ad-hoc.

- [ ] **N9-T3 — Dark mode في Aseel.** كتلة `[data-skin="aseel"][data-
  theme="dark"]` في `index.css`: cream → dark sepia. tokens فقط، لا
  دلائل bg-X-X.

- [ ] **N9-T4 — Mobile RTL polish.** كل `headband` يَتحوّل لعمود واحد <
  640px. كل toolbar صفّين. test متصفّح حيّ بـpreview_resize.

- [ ] **N9-T5 — Print CSS.** `@media print`: يُخفي toolbar/statusbar/
  sidebar + يَوسّع الجدول + يَطبع شعار من `TenantSettings.company_name`.

- [ ] **N9-T6 — Export to CSV من كل `AseelDenseTable` و
  `AseelReportTable`.** زر «تصدير» في top-right. CSV UTF-8 BOM (لـArabic
  في Excel). مرجع: `الأدوات.txt:1-8`.

- [ ] **N9-T7 — `«أخرى» submenu** في كل form (الجديد:136-143).** القائمة
  السريعة right-click تَحوي: قيد المحاسبة (view linked journal)،
  السداد (payment status)، الصورة (attached image)، إلغاء المستند
  (void document)، نسخة المستند (duplicate). الحالة: «معطَّل» إن لا
  صلاحية / لا data.

- [ ] **N9-T8 — Color coding rows** (الجديد:31, 77).** اختياري — حقل
  `Partner.row_color` HEX، يَنعكس على الـrow في AseelDenseTable عند
  عرض الشريك. للـMVP يَكفي text-color override، لا حاجة لـtheme كامل.

---

### N10 — Final review + verification + push

- [ ] **N10-T1 — مراجعة Opus لكل N0-N9** مقابل `docs/aseel_reference/
  full/*` + لقطات المالك. لا drift، لا feature creep.

- [ ] **N10-T2 — تحقّق حيّ شامل:** Django:8000 + Vite:3000. سير كامل:
  - فتح GroupConstants (F11) ⇒ تحرير دفتر فاتورة المبيعات.
  - صفقة جديدة ⇒ شحنة ⇒ تخليص ⇒ نقل محلي ⇒ فاتورة شراء (Aseel-style).
  - عرض سعر ⇒ تحويل لفاتورة مبيعات ⇒ سند قبض + شيكات ⇒ ترحيل.
  - إشعار دائن ⇒ ترحيل.
  - كشف ضريبة دوري للفترة.
  - قيد محاسبة يدوي.
  - General Ledger للحساب.
  - Console clean. `vite build` 0. `manage.py check` 0. migrations no
    drift.

- [ ] **N10-T3 — تحديث `PROJECT_MAP.md`** بـ`[ORPHANS & PENDING]` نظيف +
  بصمة كل N0-N9.

- [ ] **N10-T4 — Push إلى main + GitHub** (بنفس بروتوكول task4: stash
  main worktree، fast-forward، push).

---

## Verification Matrix

| N | Verifiable Goals |
|---|------------------|
| N0 | F11 يَفتح GroupConstants من أي مكان · TenantBook موجود · F-key fixes مُطبَّقة على M1-M5 · 3 hooks جدد (keymap form/index + field shortcuts) · tsc ≤ 78 · build 0 |
| N1 | 4 primitives جديدة + AseelDateInput · `/aseel-kit` يَعرضهم · tsc ≤ 78 · build 0 |
| N2 | 4 procurement forms inside-out · DOM يَطابق لقطة الأصيل · صفر تغيير API · متصفّح حيّ بـdata-skin |
| N3 | F7 يَستجيب لـSpace/`*`/`+` · 13 صفحة محاسبة بنمط الأصيل · 4 تقارير + 3 جديدة · كلها تَطبع |
| N4 | 9 صفحات sales + Sales/Purchase Return + SupplierPayment forms · صفر تغيير API الموجود |
| N5 | 8 صفحات inventory + Items 6-page form · 5+5 price tiers visible · per-item account overrides |
| N6 | 3 procurement management lists على DenseTable |
| N7 | 10 صفحات HR/SQL/Dashboard على DenseTable |
| N8 | 12 backend changes (Tenant + Settings + Books + Account.nature + Partner enrichment + Product enrichment + invoice_kind + SupplierPayment + VatStatement + ChequeMovement + audit) · `manage.py check` 0 · migrations no drift · unit tests for each service |
| N9 | `grep` لا hex راؤ · dark Aseel · mobile + print + CSV export · «أخرى» menu |
| N10 | كل N0-N9 مكتمل · push على main + GitHub · console clean في live |

---

## Execution Rules (صارمة للموديل الأرخص)

1. **اقرأ M1 `SalesInvoiceEditor.tsx` قبل كل form جديد.** هو القالب
   الذهبي. لا تَخترع.
2. **اقرأ مرجع الـtask المذكور** في `docs/aseel_reference/full/<file>:
   <lines>` قبل البدء.
3. **لا تَلمس `services/*Api.ts` إلا بإضافة helpers جديدة.** الـAPI
   الموجود يَبقى. لا تَزِد args على functions موجودة.
4. **اعمل في `claude/<branch>` worktree، ليس في `main`.** سَتُمسَح في main.
5. **بعد كل N، أوقَف وانتظر مراجعة Opus.** لا تَتقدّم لـN+1 بلا موافقة.
6. **`tsc --noEmit` ≤ 78 errors** قبل كل commit. regression = رفض.
7. **migrations renamed sequentially** (`0012_*.py`، `0013_*.py`، ...).
   لا تَعارض numbering.
8. **متصفّح حيّ verify** بعد كل task — DOM-check + screenshot.
9. **لا feature creep:** الأصيل عنده 550 تقرير + KDS + WWW + POS.
   نَأخذ فقط ما هو في الـmilestones.
10. **commit per task** برسالة `task5 N<X>-T<Y>: <description>`.
11. **لا UI libs جديدة** (Material/Chakra/Ant/إلخ). Tailwind v4 + Aseel
    tokens فقط.
12. **اقرأ هذا الـtask5.md كاملاً قبل البدء** — لا تَقفز للـ N0 مباشرة.

---

## Aseel ↔ KTRA Mapping (نهائي)

| الموضوع | الأصيل | KTRA | المتبنّى |
|---------|--------|------|---------|
| فاتورة مبيعات | مع شيكات + خصم مصدر | مع شيكات (M2-T3) + خصم مصدر (M2-T4) | KTRA-Aseel هجين |
| فاتورة مرجع بيع | وثيقة كاملة | غير موجود | N8-T11 + N4-T7 جديد |
| فاتورة شراء | يدوية | عبر صفقة → شحنة → تخليص → نقل | KTRA flow + Aseel UI (N2-T4) |
| فاتورة مرجع شراء | وثيقة كاملة | غير موجود | N8-T11 + N4-T8 جديد |
| الشحنات/الإرساليات | إرسالية نقل/فاتورة | logistics.LogisticsShipment | متجانس (M3-T2 + N2-T2) |
| التخليص الجمركي | غير موجود (داخل فاتورة) | logistics.LogisticsClearance | KTRA business + Aseel «بيان جمركي» UI (N2-T3) |
| النقل المحلي | داخل إرسالية نقل | logistics.LocalShipment | KTRA business + Aseel tab UI (داخل ShipmentForm) |
| إشعارات مدينة/دائنة | موجود | M4-T4 | متجانس + N4-T5 UI |
| العروض والطلبيات | 4 أنواع | SalesQuotation | M4-T5 + N4-T6 UI كامل + N5-T7 price offer |
| سند قبض/صرف | إيصال قبض + سند صرف | CustomerPayment (receipt only) | KTRA + N8-T12 SupplierPayment + N4-T9 |
| ض.ق.م كشف دوري | كشف دوري | TaxRate per-line | N8-T13 VatStatement + N3-T13 UI |
| الشيكات lifecycle | تحويلات متعدّدة | Cheque مع status | KTRA + N8-T14 ChequeMovement + N3-T4 transfer dialog |
| Per-book numbering | 10 دفاتر لكل نوع | book_number int (M2-T5) | N0-T2 TenantBook موحَّد |
| ثوابت المجموعة | F11 صفحة مركزية | موزَّع على SalesSettings + env | N0-T1 TenantSettings + N0-T4 page |
| المخازن + Items | 6 pages، 5+5 tiers، account overrides | بسيط | N5-T4 + N8-T9 + N8-T10 |
| Account.nature | مدين/دائن/كلاهما | غير موجود | N8-T6 |
| Reports | 550+ | ~10 | N3-T7..T13 = 7 reports هي اللازمة |

---

## Status

> **Status:** `[ ]` N0..N10 pending owner approval · 2026-05-21
>
> **Total:** 11 milestones · ~85 task · ~14 backend models/migrations جديدة ·
> 6 frontend primitives جديدة · 9 صفحات جديدة + 51 صفحة تُعاد بناؤها.
>
> **Estimated execution:** كل N يَحتاج ~2-5 ساعات تنفيذ من موديل أرخص +
> ساعة مراجعة من Opus = ~30-50 ساعة إجمالاً.
>
> **انتظار موافقة المالك قبل بدء N0.**
