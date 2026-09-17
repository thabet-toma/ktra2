# جردُ محرِّرات المستندات — ما تفعله كلُّ شاشةٍ اليوم

> بحثٌ مرجعيّ للقضية [#102](https://github.com/thabet-toma/ktra2/issues/102) ضمن خريطة [#100](https://github.com/thabet-toma/ktra2/issues/100).
> **جردٌ لا رأي:** كلُّ سطرٍ هنا مقروءٌ من الملف نفسه لا مستنتَجٌ من grep. التاريخ: 2026-09-03. الفرع: `research/editor-audit`.

---

## 1. الحدُّ: ما الذي عُدَّ «محرِّراً»؟

**محرِّر مستند** = شاشةٌ أو نافذةٌ تجمع حقول مستندٍ (رأس، وغالباً بنود) في **حالةٍ محلية** ثم تُرسلها بنداءِ إنشاء/تعديل. يُستثنى من العدّ: صفحات القوائم المجرَّدة، والتقارير، والإعدادات، ولوحات العرض، والمنتقيات (pickers)، والأغلفة العارضة (`shared/CommercialDocumentEditor.tsx` و`forms/shared/ItemsTableSection.tsx` هياكلُ عرضٍ تُعيد استعمالها المحرِّرات، لا محرِّرات).

أُضيفت **فئةٌ ثانية** لأنّ التذكرة سمّت منها اثنين (`items/ItemForm.tsx` و`accountant/office/OfficeClientForm.tsx`): **نماذج البيانات الرئيسية** — كرت صنف، كرت شريك، سجلّ عميل. ليست مستنداتٍ (لا ترحيل ولا رقم سلسلة) لكنها تشترك في نفس شكل «حالة + مُعرِّف + حفظ».

وميّزتُ **ثلاثة أنماطٍ** للتحرير، لأنّ «الحفظ التلقائي» لا يعني الشيء نفسه فيها:

| الرمز | النمط | المعنى |
|---|---|---|
| **ج** | اجمعْ ثمّ احفظ | الحالة محلية حتى ضغطة الحفظ — النمط الوحيد الذي يقبل «مسودّةً محلية» أصلاً |
| **م** | تحريرٌ مباشر | كلُّ تعديلٍ نداءُ خادمٍ فوريّ — لا حالة مسودّة أصلاً فلا شيء يُحفظ تلقائياً |
| **خ** | مختلط | رأسٌ يُجمَع ويُحفظ، وحقولٌ أخرى تُكتب فور تغييرها |

---

## 2. الجدول

**مفاتيح الأعمدة:**
`حفظ تلقائي` = كتابةٌ محلية (localStorage / IndexedDB / مؤقّت حول الحالة) أو كتابةٌ خادمية بلا ضغطة حفظ ·
`draft خادمية` = هل للمستند حالةُ مسودّةٍ في النموذج، وما اسمها ·
`الرقم` = متى يُستهلَك رقم المستند من سلسلته ·
`مغادرة` = `beforeunload` أو حارسُ توجيه أو تأكيدُ إغلاق ·
`الحمولة` = `buildPayload()` مسمّاة واحدة أم بناءٌ داخل مُعالج الحفظ أم متناثر ·
`آثار قبل الحفظ` = ما يصل الخادمَ قبل وجود المستند ·
`سطر/حالة` = عدد الأسطر / عدد نداءات `useState`.

### 2.1 المبيعات

| # | الملف (`frontend_v2/components/`) | المستند | نمط | حفظ تلقائي | `draft` خادمية | الرقم | مغادرة | الحمولة | آثار قبل الحفظ | سطر/حالة |
|---|---|---|:--:|---|---|---|---|---|---|---|
| 1 | `sales/SalesInvoiceEditor.tsx` | فاتورة بيع | ج | **نعم — الوحيد**: `setTimeout` 2000ms ← `db.invoice_drafts` (Dexie/IndexedDB)، مفتاحه `<tenant>:new`، والاسترجاع مقصورٌ على فاتورةٍ جديدة | نعم `status='draft'` | **عند الإنشاء** — `next_invoice_number` يزيد `TenantBook.last_used_number` | **نعم** `beforeunload` + `guardedReset()` | **`buildPayload()` واحدة** | إنشاء شريك (`CustomerQuickAddModal`)، إنشاء صنف (`ItemQuickCreateModal`)، **إنشاء نسبة ضريبة** (`POST accounting/tax-rates/`)، معاينة الرقم (قراءة) | 4651 / 87 |
| 2 | `sales/SalesReturnEditor.tsx` | مرتجع بيع | ج | لا | نعم `draft` | **عند الإنشاء** — نفس سلسلة الفاتورة | لا | داخل `submit()` | لا | 400 / 12 |
| 3 | `sales/PurchaseReturnEditor.tsx` | مرتجع شراء | ج | لا | نعم `draft` | عند الإنشاء — `PRET-####` مشتقٌّ من الأكبر (لا عدّاد) | لا | داخل `submit()` | لا | 525 / 15 |
| 4 | `sales/SalesQuotationsPage.tsx` | عرض سعر للزبون | ج | لا | نعم `draft` | **عند الإنشاء** — `next_quotation_number` | لا (Esc يُغلق بلا سؤال) | داخل `handleSave()` | لا محلياً — **لكن كلّ حفظٍ يكتب `CustomerProductQuote`** (ذاكرة أسعار الزبون) | 968 / 32 |
| 5 | `sales/SalesOrdersPage.tsx` | طلبية زبون | ج | لا | نعم `draft` | **عند الإنشاء** — `next_order_number` | لا | داخل `save()` | لا (الحجز يبدأ عند `confirmed` لا `draft`) | 661 / 22 |
| 6 | `sales/DeliveryNotesPage.tsx` | إرسالية بيع | ج | لا | **لا** — تبدأ `pending` | **عند الإنشاء** — `next_delivery_number` | لا | داخل `save()` | لا — والحفظ نفسه **يُحرِّك المخزون** | 1127 / 26 |
| 7 | `sales/DeliverGoodsModal.tsx` | تسليم بنود فاتورة | ج | لا | لا | عند الإنشاء | لا | عند نداء الحفظ | لا | 321 / 7 |
| 8 | `sales/CreditDebitNotesPage.tsx` | إشعار دائن/مدين | ج | لا | نعم `draft` | **عند الإنشاء** — `next_credit_debit_note_number` | لا | داخل `handleSave()` | لا | 469 / 17 |
| 9 | `sales/SalesCustomerPaymentsPage.tsx` (`NewPaymentModal`) | سند قبض | ج | لا | `is_posted` فقط — **والواجهة ترسل `auto_post`** | لا رقم سلسلة (المعرِّف هو الرقم) | لا | كائنٌ حرفيّ في وسيط `createCustomerPayment` | قراءةٌ فقط (`payment-defaults`، `suggestFifoAllocations`) — والشيكات تُنشأ خادمياً عند الحفظ | 1071 / 35 |
| 10 | `sales/NewSupplierPaymentModal.tsx` | سند صرف | ج | لا | `is_posted` + `auto_post` | لا | لا | كائنٌ حرفيّ في وسيط `addSupplierPayment` | لا | 329 / 17 |

### 2.2 الشراء والاستيراد

| # | الملف | المستند | نمط | حفظ تلقائي | `draft` خادمية | الرقم | مغادرة | الحمولة | آثار قبل الحفظ | سطر/حالة |
|---|---|---|:--:|---|---|---|---|---|---|---|
| 11 | `procurement/invoices/InvoiceForm.tsx` | فاتورة شراء/دولية | ج | لا | نعم `draft` | عند الإنشاء — `INV-####` مشتقٌّ من الأكبر (لا عدّاد) | **تأكيدٌ داخل التطبيق** (`guardedCancel`/`guardedNew`) — **لا `beforeunload`** | متناثر: `payload` ثمّ `sqlBody` (~65 سطراً) داخل `handleSave` | **إنشاء حسابٍ في شجرة الحسابات** (`POST accounting/accounts/resolve-import-expense/` أثناء كتابة اسم الرسم)، إنشاء مورّد، إنشاء صنف، رفع مرفقات (Cloudinary) | 3931 / 52 |
| 12 | `procurement/price-offers/PriceOfferForm.tsx` | عرض سعر مورّد | ج | لا | نعم `draft` | **عند الإنشاء** — `supplier_quotation_<scope>` من `TenantBook` | لا (Esc يُلغي فوراً) | **`buildPayload()` واحدة** | رفع مرفقات، إنشاء/تعديل صنف من المنتقي | 953 / 37 |
| 13 | `procurement/deals/DealForm.tsx` | صفقة استيراد | خ | **نعم — خادميّ ضمنيّ**: كلُّ عمليةِ دفعٍ تُطلق `updateDeal(...)` للبنود والإجماليات أولاً، وفشله يُبتلع (`console.error("Auto-save failed")`)؛ ونقرُ رقاقة المرحلة يُطلق `patchShippingWorkflow` بلا ضغطة حفظ | نعم `stage='draft'` | عند الإنشاء — `D-####` مشتقٌّ من الأكبر | لا | **متناثر**: `finalFormData` للتعديل، و`createData` + قائمةُ 35 اسماً للإنشاء | فحص تفرّد، إنشاء صنف، رفع مرفقات | 1440 / 20 |
| 14 | `procurement/deals/FirstDealWizard.tsx` | معالج أوّل صفقة | ج | لا | نعم `draft` | عند الإنشاء | لا | لكلّ خطوة | **ينشئ أصنافاً ثمّ الصفقة** | 299 / 8 |
| 15 | `procurement/receipts/GoodsReceiptsPage.tsx` | إرسالية شراء | ج | لا | **لا** (نموذج توثيقيّ بلا حالة) | **عند الإنشاء** — `next_goods_receipt_number` | لا | `payload` ثمّ `body` داخل `save()` | لا | 1172 / 26 |
| 16 | `procurement/invoices/ReceiveGoodsModal.tsx` | استلام بنود فاتورة | ج | لا | لا | **عند الإنشاء** | لا | عند نداء الحفظ | لا | 328 / 6 |
| 17 | `procurement/old-invoices/OldInvoiceFormModal.tsx` | فاتورة أرشيفية | ج | لا | نعم `draft` | عند الإنشاء | لا | `invoiceData` داخل `handleSubmit` ثمّ يُسلَّم للأب | **رفع صور (Cloudinary)** | 662 / 31 |
| 18 | `import-flow/ImportDocumentScreen.tsx` | رحلة الشحنة (شحنة/تخليص/نقل محلي/دفعات) | خ | **نعم — خادميّ**: تعديلُ سعر الشحن، وقياس الصفقة، والتوزيع، ودفعةُ الوكيل كلُّها `PATCH` فوريّ بلا ضغطة حفظ، ويتبعها `recalculateLandedCost({auto_repost:true})` — أي **إعادةُ ترحيلٍ محاسبيّ تلقائية** | `Pending` للشحنة (لا `draft`) | عند الإنشاء — `SH-####` من الأكبر | **نعم `beforeunload`** — لكنه يحرس **رأس الشحنة وحده**؛ التخليص والنقل المحلي بلا حراسة | **متناثر عبر ≥4 حافظين**؛ `handleSaveShipment` يرسل `shipmentForm` كاملاً حرفياً | **إنشاء شريك** (`POST partners/`) لمخلِّص/ناقل/وكيل، **وإنشاء صفّ تخليصٍ فوراً** | 2661 / 47 |
| 19 | `import-flow/CreateShipmentFromDealsModal.tsx` | شحنة من صفقات | ج | لا | — | عند الإنشاء | لا | عند نداء الحفظ | لا | 279 / 8 |
| 20 | `forms/deal-parts/PaymentRegistration.tsx` | دفعةُ صفقة (لوحة داخل `DealForm`) | ج | لا (المؤقّت 350ms قراءةُ رصيدٍ فقط) | — | لا | لا (ليست شاشةً موجَّهة) | **ثلاثة بناةٍ منفصلين**: `handleSaveClaim` · `handleSaveSwift` · `handleConfirmSupplier` | **رفع صورة المطالبة/السويفت قبل تسجيل أيّ دفعة** | 937 / 17 |
| 21 | `sql/SqlDealsPage.tsx` | صفقة (نموذج مبسّط) | ج | لا | نعم `draft` | عند الإنشاء | لا | كائنٌ حرفيّ في نداء `apiPostObject` | لا | 370 / 12 |

### 2.3 المحاسبة والخزينة

| # | الملف | المستند | نمط | حفظ تلقائي | `draft` خادمية | الرقم | مغادرة | الحمولة | آثار قبل الحفظ | سطر/حالة |
|---|---|---|:--:|---|---|---|---|---|---|---|
| 22 | `accounting/AccountingJournalEntryPage.tsx` | قيد يومية | ج | لا | **نعم عملياً** — `is_posted=False` (لا حقل `status`)؛ `buildPayload` يثبّت `is_posted:false` والترحيل نداءٌ منفصل `/journals/{id}/post/` | **رقم القيد هو المفتاح التلقائي `JournalID`** — يُستهلَك عند الإنشاء ولا يعود (إلا عبر حجز `VoidedJournal` عند إلغاء الترحيل) | لا | **`buildPayload()` واحدة** | قراءةُ رصيد حسابٍ أثناء التحرير | 1301 / 16 |
| 23 | `accounting/ExpenseVouchersPage.tsx` (`NewExpenseVoucherModal`) | سند مصروف | ج | لا | **لا مسودّة** — `create_expense_voucher` ينشئ ويرحّل في نداءٍ واحد | **عند الحفظ = عند الترحيل** — `next_document_number('expense_voucher')` | لا | داخل `submit()` | **اسمُ حسابٍ حرّ يُنشئ حساباً في الشجرة خادمياً** (`resolve_expense_account` تحت «52»/«53») | 424 / 22 |
| 24 | `accounting/RevenueVouchersPage.tsx` (`NewRevenueVoucherModal`) | سند إيراد | ج | لا | **لا مسودّة** — يرحّل فوراً | عند الحفظ = عند الترحيل | لا | داخل `submit()` | مثل أعلاه | 423 / 22 |
| 25 | `accounting/OpeningBalancesPage.tsx` | أرصدة افتتاحية | خ | لا | **نعم `draft`** — زرّان صريحان: «حفظ المسودة» و«ترحيل» | لا رقم | لا | **`linesPayload()` واحدة** | تبويب الشركاء **ليس جزءاً من المسودّة**: `savePartner` يكتب فوراً لكلّ شريك | 791 / 14 |
| 26 | `accounting/DocumentCodingPage.tsx` | ترميز مستندات (دفعة سندات) | ج | لا (ذاكرة الجلسة حالةُ React) | **لا** — كلُّ صفٍّ يصير سند مصروف/إيراد **مرحَّلاً** | عند الحفظ = عند الترحيل، **لكلّ صفّ** | لا | داخل `handleSave()` | **رفع المرفق (Cloudinary) قبل الحفظ** | 729 / 17 |
| 27 | `accounting/AccountingChequesPage.tsx` | (ورشةُ شيكات — لا تُنشئ شيكاً) | م | لا | `Cheque.status='Draft'` | رقم الشيك يدويّ من الورقة | لا | حمولتان صغيرتان داخليتان (تحويل · إيداع دفعة) | كلُّ إجراءٍ **يرحّل فوراً** | 1094 / 34 |
| 28 | `accounting/BankReconciliationPage.tsx` | مطابقة بنكية | م | لا | `status='Open'` | لا | لا | نداءاتٌ صغيرة (تأشير سطرٍ = نداء) | المستند يُنشَأ أولاً ثمّ يُحرَّر حيّاً | 285 / 9 |
| 29 | `finance/modals/CashCountModal.tsx` | جرد صندوق | ج | لا | نعم `draft` (`CashCount`) | لا | لا | عند نداء الحفظ | ينشئ ثمّ يرحّل في نفس المُعالج | 251 / 6 |
| 30 | `finance/modals/CashTransferModal.tsx` | تحويل نقدي | ج | لا | **لا حقل حالة** — يُرحَّل فوراً | لا | لا | عند نداء الحفظ | — | 239 / 8 |
| 31 | `finance/modals/DepositModal.tsx` | إيداع/سحب من الصندوق | ج | لا | لا | لا | لا | عند نداء الحفظ | — | 177 / 5 |
| 32 | `finance/modals/FundFxBoxModal.tsx` | تمويل صندوق عملة | ج | لا | لا | لا | لا | عند نداء الحفظ | — | 189 / 8 |
| 33 | `shared/VoucherAllocationModal.tsx` | تخصيص سندٍ على فواتير | ج | لا | — | لا | لا | عند نداء الحفظ | — | 184 / 4 |

### 2.4 المخزون وما بعد البيع

| # | الملف | المستند | نمط | حفظ تلقائي | `draft` خادمية | الرقم | مغادرة | الحمولة | آثار قبل الحفظ | سطر/حالة |
|---|---|---|:--:|---|---|---|---|---|---|---|
| 34 | `inventory/StocktakePage.tsx` | جرد مخزني | ج | لا | `is_posted=False` (مساران: حفظ · حفظ وترحيل) | **عند الترحيل لا الإنشاء** — `_next_doc_number(... 'JRD')` | لا | داخل `save(post)` | لا | 640 / 18 |
| 35 | `inventory/WarehouseTransferPage.tsx` | تحويل مستودعي | ج | لا | `is_posted` — **لكن لا مسار مسودّة في الواجهة**: `saveAndPost` يسلسل الإنشاء ثمّ الترحيل بلا شرط | **عند الترحيل** — `TRF-####` | لا | داخل `saveAndPost` | لا | 197 / 13 |
| 36 | `aftersales/ServiceOrderIntakeModal.tsx` | أمر صيانة (استلام) | ج | لا | **لا** — يبدأ `received` | **عند الإنشاء** — `next_service_order_number` من `TenantBook` | لا | عند نداء `createServiceOrder` | لا | 429 / 5 |
| 37 | `aftersales/ServiceOrderDocument.tsx` | مستند أمر الصيانة | م | لا | — (السجل قائم) | — | لا (تأكيدُ حذفٍ فقط) | **لكلّ إجراءٍ حمولته** (حفظ حقول · انتقال حالة · إضافة قطعة · توليد فاتورة) | كلُّ تعديلٍ نداءٌ فوريّ | 813 / 13 |
| 38 | `aftersales/WarrantyCardModal.tsx` | بطاقة كفالة | ج | لا | لا (الحالة مشتقّة من التواريخ) | لا رقم | لا | **حمولةٌ واحدة** داخل `save()` | لا | 568 / 5 |

### 2.5 الموارد البشرية والشخصي والمهام

| # | الملف | المستند | نمط | حفظ تلقائي | `draft` خادمية | الرقم | مغادرة | الحمولة | آثار قبل الحفظ | سطر/حالة |
|---|---|---|:--:|---|---|---|---|---|---|---|
| 39 | `hr/PayrollPage.tsx` | كشف راتب · سجلّ ساعات · صرف | ج | لا | `Payslip.status='draft'` — والصرف (`PayrollPayment`) **يُرحَّل فور الحفظ** | لا | لا | **خمسُ حمولاتٍ منفصلة** (`saveEmployee` · `addHours` · `addAdjustment` · `generateSlip` · `payEmployee`) | `previewPayslip` نداءُ خادمٍ عند كلّ تغيير فترة/بدل (قراءة)؛ وحفظُ الموظف يفتح له حساباً في الشجرة خادمياً | 1205 / 19 |
| 40 | `hr/ContractsPage.tsx` | عقد عمل (ببنود) | ج | لا | نعم `draft` | لا | لا | `payload` داخل المُعالج | لا | 668 / 9 |
| 41 | `hr/RequestsPage.tsx` | طلب موظف | ج | لا | نعم `draft` — لكنّ الواجهة تُنشئ **ثمّ تُقدِّم فوراً** (`createRequest` ← `submitRequest`) | لا | لا | `payload` داخل المُعالج | لا | 607 / 9 |
| 42 | `personal/PersonalExpensesPage.tsx` | مصروف شخصي | خ | لا | لا قيد ولا ترحيل أصلاً | لا | لا | `payload` داخل `save()` | إنشاءُ «ورقة» أو «تصنيف» يكتب خادمياً فور الضغط | 733 / 18 |
| 43 | `modals/SubmissionForm.tsx` | تسليم مهمة (ببنود) | ج | **نعم — `localStorage`**: `submission_draft_<taskId>_<userId>` يُكتب عند كلّ تغيير للبنود **بلا debounce**، ويُمسح عند التقديم | `TaskSubmission` | لا | تأكيدُ إلغاءٍ نصُّه «البنود محفوظة محلياً» | `submissionData` داخل `confirmSubmit` | لا | 707 / 9 |

### 2.6 نماذج البيانات الرئيسية (الفئة ب)

| # | الملف | السجل | نمط | حفظ تلقائي | مغادرة | الحمولة | آثار قبل الحفظ | سطر/حالة |
|---|---|---|:--:|---|---|---|---|---|
| 44 | `items/ItemForm.tsx` | كرت صنف | ج | لا (المؤقّت 400ms فحصُ اسمٍ مكرَّر — قراءة) | لا | **`payload` واحد** داخل `handleSave` + `tiersToPayload` | **رفع صورة (Cloudinary)**، **`generateBarcode()` يحجز باركوداً خادمياً**، حذفُ داتاشيت فوريّ، `addBrand` ينشئ صفَّ منتجٍ شقيقاً | 1126 / 19 |
| 45 | `items/ItemQuickEditModal.tsx` | تعديل صنف سريع | ج | لا | لا | **`dirtySimplePayload(before, form)`** — فرقٌ عن لقطةٍ سابقة (البنّاء الوحيد المشترك خارج الملف) | لا | 189 / 7 |
| 46 | `partners/PartnerEditorModal.tsx` | كرت شريك (بحساباتٍ بنكية) | ج | لا | لا (النقر خارج الإطار يُغلق فوراً) | **`payload` واحد** داخل `save()` | لا | 520 / 7 |
| 47 | `accountant/office/OfficeClientForm.tsx` | عميل مكتب المحاسبة | ج | لا | لا | لا بنّاء — `draft` يُمرَّر كما هو | لا | 151 / 3 |
| 48 | `accountant/office/OfficeClientLinkForm.tsx` | ربطُ عميلٍ بشركة | ج | لا | لا | نداءان بحقلٍ واحد | **`requestAccountantEngagement` يُنشئ طلبَ ارتباطٍ قبل تخزين الربط** — فشلُ الثاني يترك الأول يتيماً | 206 / 9 |
| 49 | `devices/SensitiveDevicesScreen.tsx` | تسجيل جهاز حسّاس | ج | لا (مؤقّتا 500/300ms بحثٌ وفحصُ IMEI — قراءة) | لا | كائنٌ حرفيّ في نداء `createDevice` | **`uploadDevicePhoto` يرفع الصورة قبل وجود السجل** | 779 / 22 |

**خارج العدّ عمداً** (فُحصت ولا تُنشئ مستنداً): `procurement/PurchaseInvoice.tsx` (غلافٌ يفوِّض إلى `InvoiceForm`؛ وفيه كودٌ ميت: `invoiceToSqlPayload` بلا مُستدعٍ في المستودع كلّه) · `procurement/invoices/ClearanceImportModal.tsx` (معالجُ اختيارٍ يطلب من الخادم أن يُولّد الفواتير) · `logistics/LocalShippingPage.tsx` (قائمةٌ تُرحّل وتُلغي؛ محرِّرها هو `ImportDocumentScreen`) · `accounting/VatStatementsPage.tsx` (**لا تحفظ شيئاً** — القائمة مصفوفةٌ فارغة وزرُّ الإصدار يُظهر رسالة «غير مُنفَّذ») · `realestate/PropertyRentalPage.tsx` (خمسةُ نماذجَ صغيرةٍ لبياناتٍ رئيسية) · `accounting/AccountingCoaPage.tsx` (كرت حساب) · `procurement/DealManagement.tsx` و`PriceOfferManagement.tsx` و`OldPurchaseInvoice.tsx` (قوائمُ تستضيف المحرِّرات أعلاه).

---

## 3. الأسئلة الثلاثة

### 3.1 كم محرِّراً بالضبط؟

**49 محرِّراً**، موزَّعةً هكذا:

| الفئة | العدد |
|---|---:|
| محرِّرات مستندات (2.1–2.5) | **43** |
| نماذج بيانات رئيسية (2.6) | **6** |
| **المجموع** | **49** |

وبحسب النمط: **42** «اجمعْ ثمّ احفظ» · **3** «تحريرٌ مباشر» (`AccountingChequesPage` · `BankReconciliationPage` · `ServiceOrderDocument`) · **4** مختلطة (`DealForm` · `ImportDocumentScreen` · `OpeningBalancesPage` · `PersonalExpensesPage`).

**الحفظ التلقائي:** **أربعُ شاشاتٍ فقط تكتب بلا ضغطة حفظٍ صريحة، وواحدةٌ منها فقط تكتب مسودّةً محليةً لمستند:**

1. `SalesInvoiceEditor.tsx` — **المسودّة المحلية الوحيدة في محرِّرات المستندات**: 2000ms ← IndexedDB.
2. `modals/SubmissionForm.tsx` — مسودّةُ `localStorage` بلا debounce (تسليمُ مهمة، ليس مستنداً مالياً). *تصحيحٌ لظنٍّ سابقٍ بأنّ الحفظ التلقائي واحدٌ في المستودع: هما اثنان، والثاني خارج نطاق المستندات.*
3. `DealForm.tsx` و`ImportDocumentScreen.tsx` — **حفظٌ خادميّ ضمنيّ** (لا مسودّة محلية): `PATCH` فوريّ عند تغيير حقلٍ أو نقر رقاقةٍ، وفي حالة `ImportDocumentScreen` يتبعه **إعادةُ ترحيلٍ محاسبيّ تلقائية**. هذا نوعٌ من الخطر مختلفٌ عن المسودّة: لا يحمي من فقدِ العمل، بل يُثبِّت أثراً لم يُطلَب.

**إنذارُ المغادرة:** موجودٌ في **شاشتين فقط** من 49 — `SalesInvoiceEditor.tsx` (مشروطٌ بـ`dirty` وحالة `draft`) و`ImportDocumentScreen.tsx` (يحرس **رأس الشحنة وحده**). و`InvoiceForm.tsx` وحدها تملك تأكيداً داخل التطبيق (`guardedCancel`) بلا حارسِ متصفّح. **لا حارسَ توجيهٍ (router blocker) في المستودع كلّه.**

**الأرقام:** **14 شاشةً تستهلك رقماً من `TenantBook` عند الإنشاء/الحفظ الأول** — وهو عدّادٌ لا يرجع، فكلُّ مسودّةٍ مهجورةٍ ثقبٌ في السلسلة:
`SalesInvoiceEditor` · `SalesReturnEditor` · `SalesQuotationsPage` · `SalesOrdersPage` · `CreditDebitNotesPage` · `DeliveryNotesPage` · `DeliverGoodsModal` · `GoodsReceiptsPage` · `ReceiveGoodsModal` · `PriceOfferForm` · `ServiceOrderIntakeModal` · `ExpenseVouchersPage` · `RevenueVouchersPage` · `DocumentCodingPage`.
ويُضاف إليها `AccountingJournalEntryPage` بنوعٍ مختلف: رقمُ القيد هو المفتاح التلقائي `JournalID`، يُستهلَك عند الإنشاء ولا يعود إلا عبر حجزِ `VoidedJournal`.

وفي المقابل ثلاثةُ أنماطٍ **لا تحرق عدّاداً**: (أ) ترقيمٌ مشتقٌّ من الأكبر — فاتورة الشراء `INV-`، ومرتجع الشراء `PRET-`، والصفقة `D-`، والشحنة `SH-`؛ (ب) **ترقيمٌ عند الترحيل لا عند الإنشاء** — الجرد `JRD-` والتحويل المستودعي `TRF-` (وهذا هو النمط الصحيح)؛ (ج) بلا رقمٍ أصلاً — سندات القبض والصرف وبطاقة الكفالة والقيد الافتتاحي.

### 3.2 أثمّة نمطٌ مشترك يصلح مِعلاقاً؟

**الشكل مشترك، والعقد ليس كذلك.**

الشكل واحدٌ فعلاً: كلُّ محرِّرٍ من الفئة «ج» عنده (حالةُ رأسٍ + مصفوفةُ بنودٍ أحياناً) و(`id` أو `null`) و(مُعالجُ حفظٍ يفرِّق بين `create` و`update`). فمِعلاقٌ بتوقيع `useDocumentDraft({ id, buildPayload, save })` **ممكن**.

لكنّ **الحمولة ليست دالّةً في أغلبها**:

| شكل الحمولة | العدد | الأمثلة |
|---|---:|---|
| دالّةُ بناءٍ مسمّاة واحدة | **5** | `SalesInvoiceEditor` · `PriceOfferForm` · `AccountingJournalEntryPage` (الثلاث باسم `buildPayload`) · `OpeningBalancesPage` (`linesPayload`) · `ItemQuickEditModal` (`dirtySimplePayload`) |
| بناءٌ في مكانٍ واحدٍ لكن داخل مُعالج الحفظ (كائنٌ حرفيّ) | **36** | الأغلبية الساحقة |
| **متناثرٌ على مواضعَ لا تشترك** | **8** | `InvoiceForm` (payload+sqlBody) · `DealForm` (مسارا إنشاء/تعديل مختلفان) · `ImportDocumentScreen` (≥4 حافظين) · `PaymentRegistration` (3 بناة) · `PayrollPage` (5 حمولات) · و«التحرير المباشر» الثلاثة (`ServiceOrderDocument` · `AccountingChequesPage` · `BankReconciliationPage`) حيث لكلّ إجراءٍ حمولته |

**الحكم:** المِعلاق المشترك ممكنٌ لأنّ *الشكل* واحد، لكنه **يلزمه وصلٌ يدويّ لكلّ شاشة** — استخراجُ دالّةِ بناءٍ من داخل مُعالج الحفظ في 36 شاشة، وإعادةُ توحيدٍ حقيقية في الثماني المتناثرة. لا يوجد اليوم عقدٌ قائمٌ يُلتقط بلا جراحة. والمتناثرةُ هي الأغلى، وهي بالمصادفة أكبر الملفات (`InvoiceForm` 3931 سطراً، `ImportDocumentScreen` 2661، `DealForm` 1440).

**ملاحظةٌ جانبية:** يوجد صندوقُ بريدٍ للطفرات غير المتصلة (`services/offline/mutationClient.ts` فوق `enqueueMutation` ← `db.mutation_queue`) — **بلا أيّ مستوردٍ في `frontend_v2`**. أي أنّ بنيةَ الطابور قائمة ولا يستعملها أيُّ محرِّر. (لا يُحكَم بموته: تحقّقٌ ثانٍ لازم قبل حذفه.)

### 3.3 أيُّها الأخطر لو حُفظ تلقائياً؟

مرتَّبةً من الأخطر:

**فئة 1 — الحفظُ نفسه ترحيلٌ محاسبيّ (لا مسودّة أصلاً):**
1. **`ExpenseVouchersPage`** و**`RevenueVouchersPage`** — `create_expense_voucher`/`create_revenue_voucher` تُنشئ السند **وتُرحّل قيده في النداء نفسه**. مسودّةٌ تلقائية هنا = قيدٌ في الدفاتر لم يقصده أحد. وفوق ذلك: اسمُ حسابٍ حرٌّ **يُنشئ حساباً في شجرة الحسابات**.
2. **`DocumentCodingPage`** — نفس الخدمتين، **لكلّ صفٍّ في الشبكة**، بمرفقٍ مرفوعٍ قبل الحفظ.
3. **`AccountingChequesPage`** — كلُّ إجراء (تحويل حالة، إيداع دفعة) يُنشئ قيداً فوراً.
4. **`finance/modals/CashTransferModal`** و**`DepositModal`** و**`FundFxBoxModal`** و**`CashCountModal`** — حركاتُ خزينةٍ تُرحَّل عند الحفظ.
5. **سندا القبض والصرف** (`NewPaymentModal` · `NewSupplierPaymentModal`) — الواجهة ترسل `auto_post`، والحفظ يُرحِّل ويُنشئ شيكاتٍ حقيقية.
6. **`WarehouseTransferPage`** — لا مسار مسودّةٍ في الواجهة أصلاً: الحفظ يسلسل الإنشاء ثمّ الترحيل.

**فئة 2 — الحفظ يحرِّك مخزوناً أو يحجزه:**
7. **`DeliveryNotesPage`** و**`DeliverGoodsModal`** — الحفظ يخصم المخزون ويُرحّل قيد التكلفة.
8. **`ReceiveGoodsModal`** و**`GoodsReceiptsPage`** — الاستلام يُدخل الكمية.
9. **`SalesOrdersPage`** — الحجز مشروطٌ بحالة `confirmed`، فمسودّةٌ لا تحجز؛ **لكنها تحرق رقم طلبية**.

**فئة 3 — الحفظ يُنشئ كياناً يتيماً إن هُجر المستند:**
10. **`InvoiceForm`** — `resolve-import-expense` **يُنشئ حساباً في شجرة الحسابات أثناء الكتابة** (قبل أيّ حفظ)، ويُنشئ مورّداً وصنفاً ويرفع مرفقات.
11. **`ImportDocumentScreen`** — **يُنشئ شريكاً** (مخلّص/ناقل/وكيل) و**صفَّ تخليصٍ** فوراً، و`PATCH`اته تُطلق **إعادةَ ترحيلٍ محاسبيّ** (`auto_repost:true`).
12. **`SalesInvoiceEditor`** — يُنشئ شريكاً وصنفاً و**نسبةَ ضريبةٍ جديدة** قبل الحفظ.
13. **`DealForm`** و**`FirstDealWizard`** — إنشاءُ أصنافٍ ورفعُ مرفقات؛ و`DealForm` يحفظ البنود خادمياً ضمنياً عند أيّ عملية دفع.
14. **`ItemForm`** — `generateBarcode()` **يحجز باركوداً خادمياً** قبل حفظ الصنف، ويرفع صورةً إلى Cloudinary.
15. **`OfficeClientLinkForm`** — طلبُ الارتباط يُنشأ قبل تخزين الربط.
16. **`SensitiveDevicesScreen`** · **`OldInvoiceFormModal`** · **`PaymentRegistration`** · **`PriceOfferForm`** — رفعُ ملفاتٍ قبل وجود السجل.

**فئة 4 — الحفظ يُلوِّث بياناتٍ مشتقّة:**
17. **`SalesQuotationsPage`** — كلُّ حفظٍ (إنشاءً وتعديلاً) يكتب في `CustomerProductQuote`، أي **ذاكرةِ أسعار الزبون** التي تغذّي عروضاً وفواتيرَ لاحقة.

**فئة 5 — الرقم:**
18. **القيد اليدوي (`AccountingJournalEntryPage`)** — له مسودّةٌ حقيقية (`is_posted=false`)، فهو **الأقلّ خطراً محاسبياً** في المحاسبة كلّها؛ لكنّ رقم القيد هو المفتاح التلقائي، فمسودّةٌ تلقائية تعني قفزاتٍ في ترقيم دفتر اليومية.
19. **الأربع عشرة شاشةً** التي تحرق عدّاد `TenantBook` (القائمة في 3.1) — أيُّ مسودّةٍ تلقائيةٍ تُنشئ صفّاً خادمياً فيها تفتح ثقباً دائماً في سلسلةٍ يراجعها مدقّقٌ ضريبيّ.

**الأسلم لو أُريد بدءٌ محدود:** المحرِّرات التي لها مسودّةٌ خادمية حقيقية **ولا تحرق عدّاداً** ولا تُنشئ كياناً قبل الحفظ — `OpeningBalancesPage` (زرّا مسودّة/ترحيل قائمان أصلاً) و`StocktakePage` (الترقيم عند الترحيل) و`ContractsPage` و`PurchaseReturnEditor`. والنمطُ الذي يجب تعميمه خادمياً قبل أيّ مسودّةٍ تلقائية هو نمطُ المخزون: **الرقم يُخصَّص عند الترحيل، لا عند الإنشاء.**

---

## 4. مراجع الكود

| الحقيقة | الموضع |
|---|---|
| مولِّد الأرقام المركزي (عدّاد لا يرجع) | `accounting/services.py` (`next_document_number`) · `tenants/models.py` (`TenantBook.get_next_number`) |
| رقم فاتورة البيع عند الإنشاء | `sales/serializers.py` (`SalesInvoiceSerializer.create`) ← `sales/services/numbering.py` (`next_invoice_number`) |
| معاينةُ الرقم بلا استهلاك | `sales/services/numbering.py` (`preview_next_invoice_number`) · `logistics/views/invoices.py` (`_next_invoice_number`) |
| القيد يُنشأ مرحَّلاً دائماً من المسارات الآلية | `accounting/services.py` (`post_journal`, `is_posted=True`) |
| القيد اليدوي يُنشأ غير مرحَّل | `accounting/views.py` (`JournalViewSet.create`, `post_entry`) |
| سندا المصروف/الإيراد: إنشاءٌ وترحيلٌ في نداءٍ واحد | `accounting/services.py` (`create_expense_voucher`, `create_revenue_voucher`) |
| إنشاءُ حسابٍ من اسمٍ حرّ | `accounting/services.py` (`resolve_expense_account`) · نقطة `accounts/resolve-import-expense/` |
| الترقيم عند الترحيل (النمط الصحيح) | `inventory/services.py` (`_next_doc_number`, `post_warehouse_transfer`, `post_stocktake`) |
| الحجز مشتقٌّ من الطلبيات المؤكَّدة وحدها | `sales/services/numbering.py` (`_active_reservation_lines`) |
| ذاكرةُ أسعار الزبون تُكتب عند كلّ حفظ عرض | `sales/serializers.py` (`_sync_customer_prices`) |
| جدولُ المسودّات المحلي | `frontend_v2/services/offline/db.ts` (`invoice_drafts`) |
| طابورُ الطفرات غير المتصل (بلا مستورد) | `frontend_v2/services/offline/mutationClient.ts` · `cachedApi.ts` (`enqueueMutation`) |
