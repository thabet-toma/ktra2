# accounting — دفتر الأستاذ المركزي: شجرة الحسابات، القيود، الشيكات، البنوك، الفترات المالية والعملات

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-11. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض
`accounting` هو المصدر الوحيد للحقيقة المحاسبية في المشروع: شجرة الحسابات (`Account`)
ودفتر اليومية (`JournalHeader`/`JournalLine`) وما يبنى عليهما من ميزان مراجعة وأستاذ
عام وتقرير ضريبة. كل الـapps الأخرى (المبيعات، اللوجستيات، المخزون، الرواتب) لا تُنشئ
قيوداً بنفسها بل تستدعي `accounting.services.post_journal` — وهي الدالة المركزية التي
تفرض الفترة المالية المفتوحة والتوازن والـidempotency. يضم الـapp أيضاً دورة الشيكات
(وارد/صادر) والبنوك والمطابقة البنكية وصناديق العملة الأجنبية بمنهج FIFO.

## أهم الملفات
| الملف | الغرض | أسطر |
|---|---|---|
| `accounting/api.py` | **الواجهة العامة للكتابة من خارج accounting** (المرحلة 2): `post_document`، `reverse_journal`، `purge_journals`، `get_account_by_code`، والجانب المحاسبي للشريك (`sync_partner_accounting`/`ensure_partner_account`/`create_partner_opening_balance`) | 467 |
| `accounting/services.py` | كل منطق الترحيل والتحقق: `post_journal`، `unpost_document`، الشيكات، البنوك، أرصدة الأطراف | 1738 |
| `accounting/views.py` | 19 ViewSet: الحسابات، القيود، الشيكات، الميزان، الأستاذ، الضريبة، البنوك، الأرصدة الافتتاحية | 1963 |
| `accounting/models.py` | 20 موديلاً محاسبياً (Account، Journal*، Cheque، Bank*، FiscalPeriod، TaxRate، OpeningBalance*…) | 824 |
| `accounting/serializers.py` | عقود الـAPI + ملخّص مرجع القيد (`build_journal_reference_summary`) | 553 |
| `accounting/opening_balance.py` | الأرصدة الافتتاحية: المستند وحفظه وترحيله وعكسه وملخّصه (`post_opening_balance`، `unpost_opening_balance`، `opening_balance_summary`) | 422 |
| `accounting/fx_fifo.py` | طبقات FIFO لصناديق العملة الأجنبية | 185 |
| `accounting/cashbox.py` | حلّ حسابات الصناديق النقدية وتوليد أكواد أبناء | 103 |
| `accounting/account_classification.py` | اشتقاق `Account.sub_type` (`classify_tenant_accounts`، `backfill_account_sub_types`) | 168 |
| `accounting/urls.py` | تسجيل الـrouter (19 مسار) | 44 |

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `Account` | `code`، `name`، `account_type`، `sub_type`، `nature`، `is_active` | `parent` (self, SET_NULL)، `tenant`؛ `unique_together (tenant, code)` |
| `JournalHeader` | `transaction_date`، `reference_type`، `reference_id`، `is_posted`، `exchange_rate` | `tenant`، `branch` (PROTECT)، `currency` (PROTECT)، `created_by` (auth.User, SET_NULL — NULL في القيود الأقدم من العمود)، `lines` |
| `JournalLine` | `debit`، `credit`، `base_debit`، `base_credit`، `description` | `journal` (CASCADE)، `account` (PROTECT)، `partner` (SET_NULL)، `cost_center` |
| `VoidedJournal` | `original_journal_id`، `reference_type`، `reference_id` | فريد على `(tenant, reference_type, reference_id)` |
| `Cheque` | `cheque_number`، `amount`، `due_date`، `status` (يشمل `Received`/`Endorsed`/`Cancelled`)، `direction` | `partner` (RESTRICT)، `endorsed_to` (Partner, SET_NULL)، `bank`، `deposit_bank_account`، `sales_invoice`، `customer_payment`، `supplier_payment`، `purchase_invoice` |
| `ChequeMovement` | `movement_type`، `notes` | `cheque` (CASCADE، related_name=`movements`)، `journal` (JournalHeader, SET_NULL) |
| `BankAccount` | `name`، `account_number`، `iban`، `is_default` | `bank` (PROTECT)، `account` (OneToOne → Account, PROTECT)، جدول `company_bank_accounts` |
| `BankReconciliation` / `…Line` | `statement_date`، `statement_balance`، `status` | `journal_line` OneToOne — الحركة تُطابَق مرة واحدة فقط |
| `CashBoxLedgerAccount` / `CashBoxFxLot` | `external_id`، `original_fc`، `remaining_fc`، `rate` | `account` (OneToOne)، `cash_box`، `journal` |
| `FiscalPeriod` | `start_date`، `end_date`، `status`، `is_closed` | `tenant` |
| `ExchangeRate` | `rate`، `effective_date` | `from_currency`/`to_currency` (PROTECT)؛ فريد مع `(tenant, effective_date)` |
| `TaxRate` | `code`، `rate`، `direction` | `tax_account` (PROTECT)؛ `unique_together (tenant, code)` |
| `CostCenter` / `AccountingAuditLog` | `code`/`action`، `model_name`، `object_id` | `tenant` |
| `OpeningBalance` | `start_date`، `entry_date` (= البدء − يوم، مشتقّ في `save`)، `status` (`draft`/`posted`)، `posted_at` | `tenant`، `journal` (SET_NULL)، `created_by`؛ مستند واحد لكل شركة |
| `OpeningBalanceAccountLine` | `debit`/`credit` (غير سالبين، طرف واحد)، `notes` | `opening` (CASCADE)، `account` (PROTECT)؛ فريد `(opening, account)` |
| `OpeningBalanceStockLine` | `quantity` (> 0)، `unit_cost` (≥ 0) | `opening` (CASCADE)، `product`/`warehouse` (PROTECT، والمستودع إلزامي)؛ فريد `(opening, product, warehouse)` |

### `Account.sub_type` — التصنيف الوظيفي
`account_type` الخمسة تقود الطبيعة والحساب الختامي والتقارير، ولا تقول **غرض**
الحساب: الصندوق والذمم والمخزون كلها `Asset`. `sub_type`
(`cash_box | bank | receivable | payable | inventory`، وNULL = حساب عادي) هو
الجواب المخزَّن الذي تفلتر عليه منتقيات الحسابات بدل تخمين الرقم أو الاسم في كل
شاشة. يُشتقّ في `accounting/account_classification.py`
(`classify_tenant_accounts`) بترتيب حجّية: روابط الخادم
(`BankAccount.account`، `CashBoxLedgerAccount.account`، `Partner.linked_account`)
← سلالة الشجرة المعيارية (1101/1110، 1102، 1103، 1104) ← اسم الحساب (للأصول
وحدها). `backfill_account_sub_types` يملأ الفارغ فقط، فلا يمحو تصحيحاً يدوياً
وإعادة تشغيله آمنة.

**الـbackfill يصنّف حسابات اليوم؛ والحياة بعده على `Account.save()`** — يشتقّ
التصنيف عند الإنشاء وحده وحين يكون فارغاً (`account_classification.py`
(`sub_type_for_account`)): تصنيف الأب ← سلالة الكود ← الاسم. نقطة واحدة عمداً،
فكل مسار يُنشئ حساباً — بذر شجرة شركة، الحساب التلقائي للطرف، الحساب التشغيلي،
الـAPI — يرثها بلا أن يتذكّرها أحد، ولولاها لمات الاشتقاق لحظة تطبيق الهجرة.
ولا تُصدر استعلاماً: لا تقرأ الأب إلا إن كان محمّلاً في الذاكرة أصلاً
(`_parent_in_memory`)، وإلا اكتفت بسلالة الكود — استعلامٌ في الحفظ يصير N+1 في
بذر شجرة كاملة. التصنيف الصريح — ومنه التصحيح اليدوي من بطاقة الحساب — أقوى من
الاشتقاق دائماً.

حسابات الأطراف تأخذ تصنيفها من نوع الطرف (`sub_type_for_partner`)، وهو الرابط
الموثوق: `accounting/api.py` (`sync_partner_accounting`) يكتبه عند الإنشاء
**وينقله مع الأب والنوع عند تغيير نوع الطرف** — مورّدٌ صار عميلاً كان يبقى
`payable` بعد انتقال حسابه تحت المدينين. النقطتان اللتان تنشئان حسابات بأنفسهما
(`accounting/services.py` (`create_bank_account`) و
`accounting/views.py` (`CashBoxLedgerViewSet.create`)) تكتبان التصنيف عند
الإنشاء. **لا تُضاف قيم إلى `ACCOUNT_TYPES`** بدلاً من ذلك — تلك الخمسة تكسر
`accountNature`/`accountStatement` والتقارير بصمت.

### الأرصدة الافتتاحية — قيد موحّد واحد لكل شركة
بدء التشغيل على النظام يحتاج ثلاث أرجل: أرصدة الحسابات، وأرصدة الأطراف، وبضاعة
أول المدة. `accounting/opening_balance.py` يملك **الرجلين الأولى والثالثة**:
مستند `OpeningBalance` يُرحَّل مرة واحدة فيُنتج قيداً واحداً بمرجع
`OPENING_BALANCE` عبر `post_journal`، ويسجّل بضاعة أول المدة حركاتِ `IN` عبر
`record_stock_movement` بنفس المرجع **وبتاريخ `entry_date`** — لا `today`، وإلا
دخلت الحركة فترةً أخرى ورُتّبت خطأً أمام أول شراء فعلي في حساب متوسط التكلفة.

**الرِّجل الثانية لم تتغيّر**: أرصدة الأطراف تبقى على آليتها القائمة — قيد لكل
طرف بمرجع `PARTNER_OPENING` (`accounting/api.py`
(`create_partner_opening_balance`)) — لأن شركات إنتاج لديها قيوداً منها مرحّلة
فعلاً. ولذلك يرفض `assert_account_allowed` أي حساب `sub_type ∈ (receivable,
payable, inventory)`، وحساب الموازنة نفسه، وأي حساب مربوط بطرف: أرقام تلك
الحسابات تأتي من رِجل أخرى، وإدخالها هنا يضاعف الرصيد. الحارس يعمل عند الحفظ
وعند الترحيل معاً — إخفاء الحساب في الواجهة ليس منعاً.

**تاريخ القيد `= start_date − 1`** (نمط Xero/Odoo): أرصدة الافتتاح هي أرصدة
الإقفال في اليوم السابق للبدء. حارس الفترة المالية يبقى مفروضاً عليه — إن لم
تغطِّ `entry_date` فترةٌ مفتوحة يفشل الترحيل برسالة تدلّ على شاشة الفترات، ولا
ينزلق التاريخ صامتاً.

**حساب الموازنة `3300 أرصدة افتتاحية`** يستقبل الفرق تلقائياً بدل منع الترحيل
حتى يوازن المستخدم يدوياً: رِجلا المخزون والأطراف يحسبهما النظام، والفرق **هو**
«صافي حقوق الملكية الافتتاحية». يُحلّ عبر `resolve_opening_offset_account`
(فوقها `accounting/api.py` (`ensure_account`)) — وهي نفسها نقطة الحلّ التي صار
`create_partner_opening_balance` يستعملها، فتتجمّع كل أرجل الافتتاح في حساب
واحد. **التعادل بين المخزون والأستاذ يثبت بالبناء**: قيمة القيد على حسابات
المخزون = مجموع (كمية × تكلفة) = قيمة الحركات المسجَّلة، مصدرٌ واحد لا مصدران.

العكس يمرّ من `unpost_document` فيرث حارس `find_stock_dependents`: إن بيعت بضاعة
الافتتاح يُرفض بقائمة المستندات المعتمِدة بدل أن يُيتّمها.

**الأصناف المتتبَّعة تسلسلياً في بضاعة الافتتاح** (`_serial_items`): الافتتاح
يُدخل الكمية للمخزن ولا يُنشئ وحدةً مُرقَّمة واحدة — `ProductSerial` تُنشأ من
استلام الشراء — فشركةٌ نمط بيعها «إجباري» تُمنع من بيع بضاعة افتتاحها عند
`inventory/serials.py` (`consume_sales_serials`) برسالة «المتوفر في المخزن 0
والمطلوب N» لا تقول أين تُرقَّم. لذلك يحمل الملخّص `serial_items`: صفٌّ لكل صنف
متتبَّع في بنود الافتتاح بالمُسجَّل والمطلوب، تعرضه الشاشة بعد الترحيل برابطٍ إلى
مسار الترقيم القائم `products/{id}/serials/register/`. **إرشاد لا حارس**: الافتتاح
صحيح بلا أرقام والبيع وحده هو ما يحتاجها، فلا يُمنع الترحيل. التجميع بالصنف لا
بالبند (الوحدة المُرقَّمة بلا مستودع)، و«المُسجَّل» كل وحدات الصنف بأي حالة لا
«في المخزن» وحدها — فبيعُ وحدة لا يُعيد صنفاً أُتمّ ترقيمه ناقصاً. استعلام واحد
مهما كثرت البنود، مفلترٌ بالشركة.

**الشاشة**: `frontend_v2/components/accounting/OpeningBalancesPage.tsx` — مسار
`/accounting/opening-balances` تحت قائمة «المحاسبة». ثلاثة تبويبات (حسابات ·
أطراف · مخزون) ورأسٌ يعرض تاريخ البدء وتاريخ القيد المشتقّ منه والحالة و«صافي
حقوق الملكية الافتتاحية». الترحيل يحفظ المسودة أولاً ثم يرحّل — فالمرحَّل هو ما
تراه الشاشة لا آخر مسودة محفوظة — وهو وإلغاؤه خلف حوار تأكيد. تبويب الأطراف
يعرض لكل طرف المُدخل والمرحَّل معاً وزرّ عكس قيده، ومنتقي الحسابات يُخفي ما
يرفضه `assert_account_allowed` (والخادم يبقى هو الحارس). خطأ الفترة المالية
يظهر بزرّ ينقل إلى شاشة الفترات. وتبويب المخزون بعد الترحيل يعرض لوحة الأصناف
المتتبَّعة تسلسلياً (المُسجَّل/المطلوب) بزرّ يفتح كرت الصنف على تبويب «الأرقام
التسلسلية» (`/products/{id}?tab=serials`) — و`ItemFormAseel` يتتبّع تبويبه النشط
بالمفتاح لا بفهرس الغلاف كي يصمد الرابط حتى وقد لحق التبويب متأخراً. عميلها في
`frontend_v2/services/accountingApi.ts`.

## دوال الـservices العامة
```python
# التوقيعات فقط — منسوخة حرفياً من accounting/opening_balance.py
def opening_balance_summary(tenant) -> dict:  # الحالة + البنود + المجاميع + أرصدة الأطراف وحالة ترحيل كلٍّ منها
def save_opening_lines(opening, *, start_date=None, account_lines=None, stock_lines=None) -> OpeningBalance:  # حفظ جماعي للمسودة (None = لا تلمس هذه الرِّجل)
def post_opening_balance(opening, *, user=None) -> OpeningBalance:  # حركات المخزون + القيد الموحّد + سطر الموازنة، ذرّياً
def unpost_opening_balance(opening, *, user=None) -> dict:  # حذف القيد وعكس حركاته عبر unpost_document
def resolve_opening_offset_account(tenant_id: int) -> Account:  # «3300» للشركة، يُنشأ إن غاب
def assert_account_allowed(account, *, offset_account_id: int) -> None:  # يرفض الذمم/المخزون/3300/حساب طرف
def get_or_create_opening(tenant) -> OpeningBalance:  # مستند الافتتاح الحالي للشركة
```

```python
# التوقيعات فقط — منسوخة حرفياً من accounting/services.py
def post_journal(*, tenant_id: int, transaction_date, reference_type: str, reference_id: int | None, description: str, lines_data: list[dict], currency=None, exchange_rate=Decimal("1"), user=None, idempotent: bool = True, branch_id: int | None = None) -> JournalHeader:  # المسار الوحيد لإنشاء + ترحيل أي قيد
def unpost_document(*, tenant_id: int, reference_id: int, journal_reference_types, stock_reference_types=(), user=None, document_label: str = "", recycle: bool = False) -> dict:  # حذف كل قيود مستند + عكس حركات مخزونه ذرّياً — بعد حارس الفترة على تواريخ المستند
def validate_journal_entry(header, lines_data):  # توازن + حساب فعّال + نفس الشركة + فترة مفتوحة
def validate_fiscal_period(tenant_id, transaction_date):  # يرمي ValidationError إن كانت الفترة مقفلة
def assert_period_open_for_unpost(tenant_id, transaction_date, document_label=""):  # نفس حرّاس post_journal، برسالة تراجع
def create_fiscal_year(tenant, year, granularity='monthly') -> list[FiscalPeriod]:  # 12 شهراً (افتراضي) أو فترة `FY <year>` واحدة — idempotent
def assert_no_period_overlap(tenant_id, start_date, end_date, exclude_pk=None):  # فترتان متقاطعتان لنفس الشركة تُرفضان
def post_journal_entry(journal_id, user=None):  # ترحيل قيد موجود بالـid
def year_end_close(*, tenant_id: int, fiscal_year: int, retained_earnings_account_id: int, user=None) -> dict:  # تصفير الإيراد/المصروف إلى الأرباح المحتجزة
def next_document_number(tenant_id: int, document_type: str, book_number: int = 0, branch_id: int | None = None) -> int:  # ترقيم المستندات عبر TenantBook مع select_for_update
def get_exchange_rate(tenant_id: int, from_currency_id: int, to_currency_id: int, effective_date=None) -> Decimal:  # أحدث سعر ≤ التاريخ، أو مقلوب الاتجاه المعاكس
def convert_amount(amount: Decimal, from_currency_id: int, to_currency_id: int, tenant_id: int, effective_date=None, explicit_rate: Decimal | None = None) -> tuple[Decimal, Decimal]:  # (المبلغ المحوَّل، السعر)
def transfer_cheque(cheque_id, movement_type, *, user=None, notes='', account_id=None, movement_date=None, bank_account_id=None):  # تحويل حالة شيك + قيده
def post_cheque_movement_journal(cheque, movement_type, *, when, user=None, account_id=None, branch_id=None):  # قيد حركة شيك واحدة، idempotent
def cheque_wallet(tenant_id: int, *, today=None) -> dict:  # محفظة الشيكات المفتوحة حسب الحالة والاستحقاق
def create_bank_account(*, tenant, bank, name, currency, branch=None, account_number=None, iban=None, is_default=False, notes=None, user=None):  # حساب بنكي + حسابه في الشجرة تحت «1102»
def bank_account_statement(bank_account, *, start_date=None, end_date=None, posted_only=True):  # حركة الحساب البنكي + حالة المطابقة
def close_bank_reconciliation(reconciliation, *, user=None):  # يُرفض الإقفال ما لم يكن الفرق صفراً
def partner_account_statement(*, tenant_id: int, partner_id: int, is_supplier: bool, limit: int = 50, offset: int = 0, ordering: str = "newest") -> dict:  # كشف حساب الطرف برصيد جارٍ
def partner_posted_balance(tenant_id: int, partner_id: int) -> tuple[Decimal, Decimal]:  # (debit, credit) من الأسطر المرحّلة بالعملة الأساسية
def attach_partner_posted_balance(rows, partner_id_field: str, *, supplier: bool, attr: str):  # أرصدة صفحة محمَّلة باستعلام واحد (للقوائم)
def annotate_partner_posted_balance(queryset, partner_id_field: str, *, supplier: bool, alias: str):  # للصف الواحد/الفلترة فقط — لا للقوائم
def resolve_import_expense_account(tenant_id: int, name: str):  # حساب مصروف استيراد تحت البند «53» أو يُنشئه
def resolve_default_cash_account(tenant_id: int):  # حساب الصندوق الافتراضي
def resolve_forex_account(tenant_id: int) -> Account | None:  # حساب فروقات العملة
def create_audit_log(tenant, user, action, model_name, object_id, change_details):  # سطر تدقيق معزول لا يُسقط المستدعي
```

## أهم الـAPI endpoints
| Method | المسار | الـview |
|---|---|---|
| GET/POST | `accounts/` | `AccountViewSet` |
| POST | `accounts/resolve-import-expense/` | `AccountViewSet.resolve_import_expense` |
| GET/POST | `journals/` | `JournalViewSet` (ترقيم اختياري بـ`?page=`؛ فلاتر: `reference_type`، `date_from`/`date_to`، `search`، `account` (سطر على هذا الحساب — `Exists` بلا `distinct`)، `user` (منشئ القيد)) |
| GET | `journals/users/` | `JournalViewSet.journal_users` — خيارات فلتر «المستخدم» من قيود الشركة وحدها |
| POST | `journals/{id}/post/` | `JournalViewSet.post_entry` — يتطلب `accounting.journal.post` |
| POST | `journals/{id}/reverse/` | `JournalViewSet.reverse_entry` — يتطلب `accounting.journal.unpost` |
| GET/POST | `cheques/` | `ChequeViewSet` |
| POST | `cheques/{id}/transfer/` | `ChequeViewSet` (يستدعي `transfer_cheque`) |
| GET | `cheques/{id}/movements/` · `cheques/wallet/` | `ChequeViewSet` |
| GET | `general-ledger/` · `trial-balance/` · `vat-report/` | `GeneralLedgerView` · `TrialBalanceView` · `VatReportView` |
| GET | `bank-accounts/{id}/statement/` | `BankAccountViewSet` |
| POST | `bank-reconciliations/{id}/toggle-line/` · `close/` · `reopen/` | `BankReconciliationViewSet` |
| POST | `fiscal-periods/create-year/` (`granularity` = `monthly` افتراضاً \| `yearly`؛ **يردّ قائمة فترات** لا فترة واحدة — 12 صفاً في الحالة الشهرية) · `{id}/close/` (409 مع قيود غير مرحّلة ما لم يُمرَّر `force`) · `{id}/reopen/` (`reason` إلزامي، يُحفظ في سجل التدقيق) · `year-end-close/` | `FiscalPeriodViewSet` — كلها بـ`accounting.period.manage` |
| GET/POST/PATCH/DELETE | `fiscal-periods/` · `fiscal-periods/{id}/` | `FiscalPeriodViewSet` — الكتابة كلها بـ`accounting.period.manage`؛ المُقفَلة لا تُعدَّل ولا تُحذف، والحذف مرفوض إن كان في مداها قيد مرحّل؛ `status`/`is_closed` للقراءة فقط (تتغيّر عبر `close/`+`reopen/` وحدهما)، وكل تعديل أو حذف يُكتب في `AccountingAuditLog` |
| GET | `opening-balance/` | `OpeningBalanceViewSet.list` — الحالة والبنود والمجاميع وأرصدة الأطراف؛ المبالغ نصوصاً والتواريخ ISO |
| PUT | `opening-balance/lines/` | `OpeningBalanceViewSet.save_lines` — استبدال جماعي للمسودة؛ الرِّجل الغائبة عن الطلب لا تُمَسّ، والمستند المرحَّل يُرفض تعديله |
| POST | `opening-balance/post/` · `opening-balance/unpost/` | `OpeningBalanceViewSet` — بصلاحيتَي `accounting.journal.post` / `accounting.journal.unpost` القائمتين (لا مفاتيح جديدة) |
| GET | `exchange-rates/get-rate/` | `ExchangeRateViewSet` |
| GET/POST | `cost-centers/` · `tax-rates/` · `banks/` · `bank-branches/` · `cash-box-accounts/` · `purchase-receipts/` · `currencies/` | حسب `urls.py` |

**«قيد التسوية» ليس نوعاً ثانياً من القيود ولا شاشةً مستقلة** — هو وسمٌ على القيد اليدوي
نفسه: `reference_type='ADJUSTMENT'` بتسميته العربية في `accounting/serializers.py`
(`SOURCE_LABEL_MAP`)، يُصفّى بفلتر `reference_type` القائم ويمرّ بدورة المسودّة/الترحيل
وقاعدة التوازن نفسها بلا استثناء.

## الاعتماديات
**يعتمد على:**
- `partners` — **models مباشرة**: `accounting/models.py` (`from partners.models import Partner`) لبناء `JournalLine.partner` (`models.py`) و`Cheque.partner` (`models.py`)، ويتحقق منه في `services.py` داخل `validate_journal_entry`.
- `tenants` — **models مباشرة**: `accounting/models.py` (`Tenant, Currency`) و`accounting/services.py` (`Currency, TenantBook` لترقيم المستندات).
- `core` — **services**: `accounting/services.py` (`run_tax_period_guards`) من `core.hooks`، و`accounting/views.py` (`core.access`، `core.api_defaults`، `core.tenant_utils`).
- استيرادات كسولة داخل الدوال (لكسر الدوران): `inventory.services` في `services.py`، و`sales.models`/`logistics.models` و`sales.services`/`logistics.services` داخل `accounting/services.py` (`unpost_document`).

**يعتمد عليه:** `sales` (`sales/services/`)، `logistics` (`logistics/services.py` لـ`post_journal`)، `inventory` (`inventory/services.py`)، `partners` (`partners/signals.py`، `partners/views.py`)، `core`، `hr`، `tenants`، `accountant_portal`.

## قواعد لا يجوز كسرها
- **كل قيد يمرّ عبر `post_journal`** — هي وحدها تفرض الفترة المفتوحة والتوازن والـidempotency وقفل `select_for_update` (`accounting/services.py` (`post_journal`)). أي كتابة مباشرة لـ`JournalHeader`/`JournalLine` تتجاوز كل ذلك.
- **من خارج accounting الكتابة عبر `accounting.api` فقط** (المرحلة 2): `post_document` للقيود، `reverse_journal` للعكس (ومعه التجاوز الوحيد المشروع لغارد القيد المرحّل عند `unpost_original=True`)، `purge_journals` للتطهير الإداري — عقد `no-direct-accounting-models` في `.importlinter` يمنع أي استيراد جديد لـ`accounting.models`.
- **لا تعديل على قيد مرحّل**: `JournalHeader.save` يرمي `ValidationError` إن كان `is_posted` سابقاً (`accounting/models.py` (`JournalHeader`)) — أنشئ قيداً عكسياً.
- **التوازن دقيق بعد `quantize('0.01')`** ولا يُقبل قيد بمجموع صفر (`accounting/services.py` (`validate_journal_entry`)).
- **`base_debit`/`base_credit` تُحسب في `JournalLine.save` من `exchange_rate` الرأس**، وسعر مفقود أو ≤ 0 يفشل بصوت عالٍ لا يسقط إلى 1 (`accounting/models.py` (`JournalLine`)).
- **`nature` الحساب مفروضة على الترحيل**: `debit_only` يرفض أي دائن و`credit_only` يرفض أي مدين (`accounting/services.py` (`post_journal`)).
- **`JournalLine.account` بـ`PROTECT`** — لا يُحذف حساب له حركة، و`debit`/`credit` بقيدَي `CheckConstraint` غير سالبين (`accounting/models.py` (`JournalLine`)).
- **كل قراءة مُنطاقة بالشركة**: `tenant is None ⇒ .none()` في `accounting/views.py` (`JournalViewSet`) و`accounting/views.py` (`AccountViewSet`).
- **وكل مرساة تُكتب مُنطاقة بها أيضاً**: `get_queryset` يحمي القراءة وحدها، فحقول الـpk الكاتبة تُعلَن `TenantScopedPrimaryKeyRelatedField` (`core/api_defaults.py`) — أب الحساب (`accounting/serializers.py` (`AccountSerializer`)) وشريك السطر ومركز كلفته (`JournalLineSerializer`). معرّف شركة أخرى يعود «غير موجود»، فلا شجرةَ تُعلَّق تحت شركة غيرها ولا كشفَ لوجود المعرّف.
- **الشيك لا يتحرك خارج جدول اتجاهه** — `accounting/services.py` (`INCOMING_TRANSITIONS`) و`accounting/services.py` (`OUTGOING_TRANSITIONS`) هما المصدر الواحد، و`accounting/services.py` (`transfer_cheque`) ترفض الانتقال غير المسموح، وترفض أي حركة على شيكٍ سندُه غير مرحّل، وتكتب `ChequeMovement` مربوطةً بقيدها.
- **لا تُقفل مطابقة بنكية بفرق ≥ 0.01** (`accounting/services.py` (`close_bank_reconciliation`))، وكل `JournalLine` تُطابَق مرة واحدة (`accounting/models.py` (`BankReconciliationLine`)).
- **الفترة المُقفَلة لا تتغيّر إلا عبر `reopen/` بسبب مسجَّل** — `FiscalPeriodViewSet.perform_update`/`perform_destroy` (`accounting/views.py`) يرفضان أي تعديل أو حذف عليها، ويمنعان حذف فترة في مداها قيد مرحّل (تاريخٌ بلا فترة تغطّيه يشلّ الترحيل وإلغاءه معاً)، وكل تعديل أو حذف ناجح يُكتب في سجل التدقيق.
- **`create_audit_log` يجب أن يبقى معزولاً** — سطر تدقيق فاشل لا يجوز أن يُرجِع معاملة المستدعي (سبب اختبار `test_audit_log_isolation`).
- **قيد افتتاحي مرحّل واحد لكل شركة** — مفروضٌ في `accounting/opening_balance.py` (`post_opening_balance`) داخل المعاملة تحت `select_for_update`، **لا بقيد فريد شرطي**: MySQL لا يدعم الفهارس الجزئية، فقيدٌ بـ`condition=` يوجد في قاعدة الاختبارات (SQLite) ويغيب بصمت عن الإنتاج. لا قيد افتتاحي ثانٍ إلا بعد عكس الأول صراحةً.
- **أرصدة الذمم والمخزون لا تُدخل في بنود حسابات الافتتاح** — `assert_account_allowed` يرفضها (ومعها حساب `3300` نفسه وأي حساب مربوط بطرف) عند الحفظ وعند الترحيل معاً؛ أرقامها تأتي من `PARTNER_OPENING` ومن بنود المخزون، وإدخالها هنا يضاعف الرصيد.
- **بضاعة أول المدة تُسجَّل بتاريخ `entry_date` لا `today`** (`accounting/opening_balance.py` (`post_opening_balance`)) — تاريخٌ آخر يضع الحركة في فترة أخرى ويرتّبها خطأً أمام أول شراء فعلي في متوسط التكلفة.

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `accounting/tests/test_unpost_document.py` | حذف كل قيود مستند بحدوده وحده + إعادة حركات المخزون + الذرّية (324 سطر) |
| `accounting/tests/test_banks_and_reconciliation.py` | البنوك والفروع والحسابات والمطابقة البنكية (296 سطر) |
| `accounting/tests/test_cheque_outgoing_and_wallet.py` | إغلاق دورة الشيك الصادر + محفظة الشيكات |
| `accounting/tests/test_cheque_transfer_journals.py` | التحويل يرحّل قيداً ويمنع PATCH الخام على `status` |
| `accounting/tests/test_cheque_lifecycle.py` | إنفاذ جدولَي الانتقالات لكل اتجاه عبر `transfer_cheque` |
| `accounting/tests/test_cheque_cycle_v2.py` | قيد الإيداع (1107 ÷ 1109)، التظهير، إعادة الإيداع، إلغاء الصادر، وصراحة ريزولفرَي حسابَي الشيكات |
| `accounting/tests/test_cheque_accounts_autocreate.py` · `test_cheque_create_api.py` · `test_cheques_column_alignment.py` | إنشاء حسابي الشيكات تلقائياً، وعقد إنشاء الشيك داخل سند |
| `accounting/tests/test_journal_tenant_scoping.py` | رفض شريك/مركز تكلفة من شركة أخرى في `validate_journal_entry` |
| `accounting/tests/test_accounting_permissions.py` | إنفاذ مفاتيح `accounting.*` على القيد والشجرة والفترات |
| `accounting/tests/test_partner_statement.py` | مطابقة الرصيد الجاري في كشف الحساب مع `partner_posted_balance` |
| `accounting/tests/test_audit_log_isolation.py` | سطر التدقيق لا يُسقط عملية المستدعي |
| `accounting/tests/test_fx_fifo.py` | طبقات FIFO لصندوق العملة الأجنبية |
| `accounting/tests/test_journal_pagination.py` · `test_journal_reference_perf.py` · `test_account_list_perf.py` | عقد الترقيم وغياب N+1 |
| `accounting/tests/test_fiscal_period_lock.py` | قفل الشهر المالي من كل مسار: الترحيل وإلغاؤه والتداخل و`close/`+`reopen/`، وCRUD الفترة (صلاحية، مُقفَلة غير قابلة للتعديل أو الحذف، سجل تدقيق) |
| `accounting/tests/test_journal_filters.py` | تصفية الدفتر بالحساب (بلا تكرار عبر الصفحات) وبالمستخدم، وختم `created_by` من مسارَي الإنشاء، ودورة قيد التسوية |
| `accounting/tests/test_opening_balance.py` | القيد الافتتاحي الموحّد: تاريخه وتوازنه وسطر `3300`، ومطابقة حسابات المخزون في الأستاذ لإجمالي تقرير «تقييم المخزون» بالرقم، ومنع القيد الثاني قبل العكس، والعكس وحارس الاعتمادية، والحسابات الممنوعة، والفترة الغائبة/المغلقة بلا حالة جزئية، وعزل الشركات |
