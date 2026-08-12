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
| `accounting/api.py` | **الواجهة العامة للكتابة من خارج accounting** (المرحلة 2): `post_document`، `reverse_journal`، `purge_journals`، `get_account_by_code`، والجانب المحاسبي للشريك (`sync_partner_accounting`/`ensure_partner_account`/`create_partner_opening_balance`) | 481 |
| `accounting/services.py` | كل منطق الترحيل والتحقق: `post_journal`، `unpost_document`، الشيكات، البنوك، أرصدة الأطراف | 1738 |
| `accounting/views.py` | 18 ViewSet: الحسابات، القيود، الشيكات، الميزان، الأستاذ، الضريبة، البنوك | 1892 |
| `accounting/models.py` | 17 موديلاً محاسبياً (Account، Journal*، Cheque، Bank*، FiscalPeriod، TaxRate…) | 737 |
| `accounting/serializers.py` | عقود الـAPI + ملخّص مرجع القيد (`build_journal_reference_summary`) | 576 |
| `accounting/fx_fifo.py` | طبقات FIFO لصناديق العملة الأجنبية | 185 |
| `accounting/cashbox.py` | حلّ حسابات الصناديق النقدية وتوليد أكواد أبناء | 103 |
| `accounting/urls.py` | تسجيل الـrouter (18 مسار) | 45 |

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `Account` | `code`، `name`، `account_type`، `nature`، `is_active` | `parent` (self, SET_NULL)، `tenant`؛ `unique_together (tenant, code)` |
| `JournalHeader` | `transaction_date`، `reference_type`، `reference_id`، `is_posted`، `exchange_rate` | `tenant`، `branch` (PROTECT)، `currency` (PROTECT)، `lines` |
| `JournalLine` | `debit`، `credit`، `base_debit`، `base_credit`، `description` | `journal` (CASCADE)، `account` (PROTECT)، `partner` (SET_NULL)، `cost_center` |
| `VoidedJournal` | `original_journal_id`، `reference_type`، `reference_id` | فريد على `(tenant, reference_type, reference_id)` |
| `Cheque` | `cheque_number`، `amount`، `due_date`، `status`، `direction`، `VALID_TRANSITIONS` | `partner` (RESTRICT)، `bank`، `deposit_bank_account`، `sales_invoice`، `customer_payment`، `supplier_payment`، `purchase_invoice` |
| `ChequeMovement` | `movement_type`، `notes` | `cheque` (CASCADE، related_name=`movements`) |
| `BankAccount` | `name`، `account_number`، `iban`، `is_default` | `bank` (PROTECT)، `account` (OneToOne → Account, PROTECT)، جدول `company_bank_accounts` |
| `BankReconciliation` / `…Line` | `statement_date`، `statement_balance`، `status` | `journal_line` OneToOne — الحركة تُطابَق مرة واحدة فقط |
| `CashBoxLedgerAccount` / `CashBoxFxLot` | `external_id`، `original_fc`، `remaining_fc`، `rate` | `account` (OneToOne)، `cash_box`، `journal` |
| `FiscalPeriod` | `start_date`، `end_date`، `status`، `is_closed` | `tenant` |
| `ExchangeRate` | `rate`، `effective_date` | `from_currency`/`to_currency` (PROTECT)؛ فريد مع `(tenant, effective_date)` |
| `TaxRate` | `code`، `rate`، `direction` | `tax_account` (PROTECT)؛ `unique_together (tenant, code)` |
| `CostCenter` / `AccountingAuditLog` | `code`/`action`، `model_name`، `object_id` | `tenant` |

## دوال الـservices العامة
```python
# التوقيعات فقط — منسوخة حرفياً من accounting/services.py
def post_journal(*, tenant_id: int, transaction_date, reference_type: str, reference_id: int | None, description: str, lines_data: list[dict], currency=None, exchange_rate=Decimal("1"), user=None, idempotent: bool = True, branch_id: int | None = None) -> JournalHeader:  # المسار الوحيد لإنشاء + ترحيل أي قيد
def unpost_document(*, tenant_id: int, reference_id: int, journal_reference_types, stock_reference_types=(), user=None, document_label: str = "", recycle: bool = False) -> dict:  # حذف كل قيود مستند + عكس حركات مخزونه ذرّياً
def validate_journal_entry(header, lines_data):  # توازن + حساب فعّال + نفس الشركة + فترة مفتوحة
def validate_fiscal_period(tenant_id, transaction_date):  # يرمي ValidationError إن كانت الفترة مقفلة
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
| GET/POST | `journals/` | `JournalViewSet` (ترقيم اختياري بـ`?page=`) |
| POST | `journals/{id}/post/` | `JournalViewSet.post_entry` — يتطلب `accounting.journal.post` |
| POST | `journals/{id}/reverse/` | `JournalViewSet.reverse_entry` — يتطلب `accounting.journal.unpost` |
| GET/POST | `cheques/` | `ChequeViewSet` |
| POST | `cheques/{id}/transfer/` | `ChequeViewSet` (يستدعي `transfer_cheque`) |
| GET | `cheques/{id}/movements/` · `cheques/wallet/` | `ChequeViewSet` |
| GET | `general-ledger/` · `trial-balance/` · `vat-report/` | `GeneralLedgerView` · `TrialBalanceView` · `VatReportView` |
| GET | `bank-accounts/{id}/statement/` | `BankAccountViewSet` |
| POST | `bank-reconciliations/{id}/toggle-line/` · `close/` · `reopen/` | `BankReconciliationViewSet` |
| POST | `fiscal-periods/create-year/` · `{id}/close/` · `{id}/reopen/` · `year-end-close/` | `FiscalPeriodViewSet` |
| GET | `exchange-rates/get-rate/` | `ExchangeRateViewSet` |
| GET/POST | `cost-centers/` · `tax-rates/` · `banks/` · `bank-branches/` · `cash-box-accounts/` · `purchase-receipts/` · `currencies/` | حسب `urls.py` |

## الاعتماديات
**يعتمد على:**
- `partners` — **models مباشرة**: `accounting/models.py` (`from partners.models import Partner`) لبناء `JournalLine.partner` (`models.py`) و`Cheque.partner` (`models.py`)، ويتحقق منه في `services.py` داخل `validate_journal_entry`.
- `tenants` — **models مباشرة**: `accounting/models.py` (`Tenant, Currency`) و`accounting/services.py` (`Currency, TenantBook` لترقيم المستندات).
- `core` — **services**: `accounting/services.py` (`from core.hooks import run_tax_period_guards`)، و`accounting/views.py:13-17` (`core.access`، `core.api_defaults`، `core.tenant_utils`).
- استيرادات كسولة داخل الدوال (لكسر الدوران): `inventory.services` في `services.py`، `sales.models`/`logistics.models` في `services.py:930-931`، `sales.services`/`logistics.services` في `services.py:1007,1013`.

**يعتمد عليه:** `sales` (`sales/services.py:14-15`)، `logistics` (`logistics/services.py`، `logistics/services.py:999,1280,1699` لـ`post_journal`)، `inventory` (`inventory/services.py:1118,1281`)، `partners` (`partners/signals.py`، `partners/views.py`)، `core`، `hr`، `tenants`، `accountant_portal`.

## قواعد لا يجوز كسرها
- **كل قيد يمرّ عبر `post_journal`** — هي وحدها تفرض الفترة المفتوحة والتوازن والـidempotency وقفل `select_for_update` (`accounting/services.py:479-636`). أي كتابة مباشرة لـ`JournalHeader`/`JournalLine` تتجاوز كل ذلك.
- **من خارج accounting الكتابة عبر `accounting.api` فقط** (المرحلة 2): `post_document` للقيود، `reverse_journal` للعكس (ومعه التجاوز الوحيد المشروع لغارد القيد المرحّل عند `unpost_original=True`)، `purge_journals` للتطهير الإداري — عقد `no-direct-accounting-models` في `.importlinter` يمنع أي استيراد جديد لـ`accounting.models`.
- **لا تعديل على قيد مرحّل**: `JournalHeader.save` يرمي `ValidationError` إن كان `is_posted` سابقاً (`accounting/models.py:110-120`) — أنشئ قيداً عكسياً.
- **التوازن دقيق بعد `quantize('0.01')`** ولا يُقبل قيد بمجموع صفر (`accounting/services.py:387-401`).
- **`base_debit`/`base_credit` تُحسب في `JournalLine.save` من `exchange_rate` الرأس**، وسعر مفقود أو ≤ 0 يفشل بصوت عالٍ لا يسقط إلى 1 (`accounting/models.py:167-201`).
- **`nature` الحساب مفروضة على الترحيل**: `debit_only` يرفض أي دائن و`credit_only` يرفض أي مدين (`accounting/services.py:593-607`).
- **`JournalLine.account` بـ`PROTECT`** — لا يُحذف حساب له حركة (`accounting/models.py`)؛ و`debit`/`credit` بقيدَي `CheckConstraint` غير سالبين (`models.py:156-165`).
- **كل قراءة مُنطاقة بالشركة**: `tenant is None ⇒ .none()` في `JournalViewSet.get_queryset` و`AccountViewSet.get_queryset` (`accounting/views.py:288-291`, `81-84`).
- **الشيك لا يتحرك خارج `VALID_TRANSITIONS`** — `Cheque.change_status` يرفض الانتقال غير المسموح ويسجّل `ChequeMovement` (`accounting/models.py:329-376`).
- **لا تُقفل مطابقة بنكية بفرق ≥ 0.01** (`accounting/services.py:1441-1452`)، وكل `JournalLine` تُطابَق مرة واحدة (`models.py`).
- **`create_audit_log` يجب أن يبقى معزولاً** — سطر تدقيق فاشل لا يجوز أن يُرجِع معاملة المستدعي (سبب اختبار `test_audit_log_isolation`).

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `accounting/tests/test_unpost_document.py` | حذف كل قيود مستند بحدوده وحده + إعادة حركات المخزون + الذرّية (324 سطر) |
| `accounting/tests/test_banks_and_reconciliation.py` | البنوك والفروع والحسابات والمطابقة البنكية (296 سطر) |
| `accounting/tests/test_cheque_outgoing_and_wallet.py` | إغلاق دورة الشيك الصادر + محفظة الشيكات |
| `accounting/tests/test_cheque_transfer_journals.py` | التحويل يرحّل قيداً ويمنع PATCH الخام على `status` |
| `accounting/tests/test_cheque_lifecycle.py` | إنفاذ `VALID_TRANSITIONS` |
| `accounting/tests/test_cheque_accounts_autocreate.py` · `test_cheque_create_api.py` · `test_cheques_column_alignment.py` | إنشاء حسابي الشيكات تلقائياً، وعقد إنشاء الشيك داخل سند |
| `accounting/tests/test_journal_tenant_scoping.py` | رفض شريك/مركز تكلفة من شركة أخرى في `validate_journal_entry` |
| `accounting/tests/test_accounting_permissions.py` | إنفاذ مفاتيح `accounting.*` على القيد والشجرة والفترات |
| `accounting/tests/test_partner_statement.py` | مطابقة الرصيد الجاري في كشف الحساب مع `partner_posted_balance` |
| `accounting/tests/test_audit_log_isolation.py` | سطر التدقيق لا يُسقط عملية المستدعي |
| `accounting/tests/test_fx_fifo.py` | طبقات FIFO لصندوق العملة الأجنبية |
| `accounting/tests/test_journal_pagination.py` · `test_journal_reference_perf.py` · `test_account_list_perf.py` | عقد الترقيم وغياب N+1 |
