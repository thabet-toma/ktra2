# partners — بطاقة الطرف الموحّدة (عميل/مورد/وكيل شحن/مخلّص/ناقل) وربطها بحساب في شجرة الحسابات

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-11. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض
`partners` يحمل الكيان المشترك بين كل الوحدات: `Partner` بستة أنواع في `PARTNER_TYPES`
(عميل، مورد، وكيل شحن، مخلّص جمركي، ناقل محلي، ناقل) مع حساباته البنكية وملاحظاته
(CRM). الـapp نفسه بلا `services.py`. منذ المرحلة 2 (accounting facade) صار
`partners/signals.py` واجهة رقيقة: إشارة `post_save` تنادي
`accounting.api.sync_partner_accounting` التي تُنشئ للطرف حساباً في الشجرة
وتُرحّل قيد رصيده الافتتاحي. الأرصدة وكشوف الحساب لا تُخزَّن هنا بل تُقرأ من
`accounting.services` حتى يبقى دفتر الأستاذ المصدر الوحيد للحقيقة.

## أهم الملفات
| الملف | الغرض | أسطر |
|---|---|---|
| `partners/views.py` | `PartnerViewSet` + `CustomerNoteViewSet` وإجراءات البطاقة (رصيد/بروفايل/كشف/فواتير) | 572 |
| `partners/signals.py` | `post_save` ينادي `accounting.api.sync_partner_accounting` فقط (المنطق في `accounting/api.py`) | 27 |
| `partners/models.py` | `Partner`، `PartnerGroup`، `PartnerBankAccount`، `CustomerNote` | 206 |
| `partners/serializers.py` | عقود الـAPI + كشف الأرقام الشبيهة (T-DUPID) | 196 |
| `partners/urls.py` | تسجيل `partners/` و`customer-notes/` | 11 |
| `partners/agent_api.py` | نقطتا بوت الفواتير للأطراف (`/api/agent/suppliers/` و`/api/agent/customers/`، مسجَّلتان في `core/urls.py`). تسكنان هنا لا في `core` لأن `.importlinter` يمنع `core` من استيراد `partners.serializers`؛ `partner_type` مثبَّت خادمياً ولا مسار تعديل أو حذف | 158 |
| `partners/apps.py` | `ready()` يستورد `partners.signals` — بدونه لا يعمل أي شيء تلقائي | 8 |

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `Partner` | `name`، `partner_type`، `supplier_scope`، `tax_number`، `credit_limit`، `opening_balance`، `opening_balance_date`، `assigned_price_tier`، `end_of_dealing_date`، `row_color`، `is_active` (إيقاف لا حذف)، `sector`، `mobile` (ISSUE #86) | `tenant` (CASCADE)، `group` → `PartnerGroup`، `linked_account` → `accounting.Account` (SET_NULL)، `default_cost_center` → `accounting.CostCenter`، `currency`، `engagement` → `accountant_portal.AccountantEngagement` (SET_NULL، مرجع نصّي، ISSUE #86)، `managed_tenant` → `tenants.Tenant` (SET_NULL، مرجع نصّي، ISSUE #86)؛ `client_type` property مشتقّة (managed/engaged/hybrid/unlinked) — زبون مكتب محاسبة إن وُجدا |
| `PartnerGroup` | `name`، `group_type` | `account_receivable` / `account_payable` → `accounting.Account` (SET_NULL) |
| `PartnerBankAccount` | `bank_name`، `account_number`، `iban`، `swift_code`، `beneficiary_name`، `is_default`، `is_active` | `partner` (CASCADE)، `currency` (PROTECT)؛ `unique_together (tenant, partner, account_number)` |
| `CustomerNote` | `title`، `body`، `remind_on`، `is_done`، `priority`، `target_type/id/label/path` | `partner` (CASCADE، nullable)، `created_by`؛ 4 فهارس مركّبة تبدأ بـ`tenant` |

## دوال الـservices العامة
لا يوجد `partners/services.py`. المنطق المحاسبي انتقل إلى `accounting/api.py`
(المرحلة 2)، والباقي في `serializers.py`:

```python
# accounting/api.py — الواجهة المحاسبية للشريك (كانت في partners/signals قبل المرحلة 2)
def sync_partner_accounting(partner) -> None:  # ينشئ/يزامن حساب الطرف ويرحّل الرصيد الافتتاحي (يستدعيه signal الـpost_save)
def ensure_partner_account(partner):  # يضمن وجود الحساب المربوط عبر إعادة save()
def create_partner_opening_balance(partner) -> None:  # قيد PARTNER_OPENING مقابل حساب «3300»

# partners/serializers.py — منسوخة حرفياً
def normalize_identifier(value) -> str:  # صورة الرقم القابلة للمقارنة (أرقام وحروف لاتينية بحالة موحّدة)
def find_partner_with_similar_tax_number(tenant_id, tax_number, *, exclude_id=None):  # (معرّف، اسم) أو None
def find_partner_with_similar_bank_account(tenant_id, account_number, *, exclude_partner_id=None):  # (معرّف، اسم) أو None
```

## أهم الـAPI endpoints
| Method | المسار | الـview |
|---|---|---|
| GET/POST | `partners/` | `PartnerViewSet` (فلاتر: `partner_type` و`supplier_scope` قيمةً أو قائمةً بفاصلة، `kinds` (أصناف `PARTNER_KINDS`: `supplier_local`/`supplier_international`/`supplier_unscoped` أو نوع الطرف)، `assigned_price_tier`، `search`، `include_inactive=1` — الموقوف مخفيّ من القائمة و`lookup` افتراضاً) |
| GET | `partners/kind-counts/` | `PartnerViewSet.kind_counts` — عدّاد كل صنف (يحترم `search` و`include_inactive`) لرقاقات صفحة الأطراف الدائنة |
| POST | `partners/bulk-scope/` | `PartnerViewSet.bulk_scope` — `{ids, supplier_scope: local\|international}`: تصنيف جماعي لموردي الشركة وحدهم (غير المورد يُتجاهل) |
| DELETE | `partners/{id}/` | `PartnerViewSet.destroy` — 400 «عليه حركات (…) — أوقفه بدل حذفه» إن حمل أيّ مرجع غير مملوك؛ وإلا يُحذف مع حسابه الفارغ |
| GET | `partners/lookup/` | `PartnerViewSet.lookup` — مصفوفة خام محدودة (افتراضي 200، حد أقصى 500) |
| GET | `partners/{id}/balance/` | `PartnerViewSet.balance` — رصيد حالي + `projected_balance` بعد `?proposed_total=`، و`is_creditor` (موجبُ الدائن «له») |
| GET | `partners/{id}/profile/` | `PartnerViewSet.profile` — Dr/Cr + إجمالي المبيعات/المشتريات (الدولية بحصّة المورد، وللمخلّص/الوكيل/الناقل مجموع مستحقّاتهم مع تعديلاتها) + آخر معاملة + للدائن `on_account_payments`/`accrual_surplus` (`logistics.domain.party_accruals.party_on_account_summary`) — مربّعا «دفعات تحت الحساب» و«فائض تحت الحساب» فوق كشف الحساب |
| GET | `partners/{id}/statement/` | `PartnerViewSet.statement` (`limit` ≤ 200، `offset`، `ordering`، `only_payments`، `currency=USD`: الكشف بالدولار من `amount_currency` — سطرٌ بلا مبلغ به `currency_missing` بشيكله ولا يدخل الرصيد، و`fx` سطر فرق الصرف الختامي، و`currencies` في الحالتين تختار بها الشاشة زرّ «₪ / $» وافتراضيَّ الدولار للوكيل والمورد ذي القيود الدولارية) — كل صفّ يحمل `balance_before` و`running_balance`: الرصيد قبل الحركة وبعدها، و`reversal_pair_id`/`reversal_pair` لطرفَي «قيد + عكسه» صافيهما صفر ومعهما `balance_before_folded`/`running_balance_folded` (الرصيد بلا الأزواج) — الشاشة تطوي الزوج افتراضياً في سطر «قيد صُحّح: #الأصل ⇄ #العكس (صافي 0)» يُفتح بكبسة، و«إظهار القيود المعكوسة» يعيدهما بالرصيد الخام. `only_payments=true` يستثني الفاتورة نفسها — وللطرف الدائن مستحقّات التخليص/الشحن/النقل وقيود تعديلها أيضاً — ويُبقي كل ما عداها (سند · ارتداد شيك · إشعار دائن) — الترشيح يحكم المعروض لا الحساب |
| GET | `partners/{id}/stock-movements/` | `PartnerViewSet.stock_movements` → `inventory/services.py` (`partner_stock_movements`) — حركات مخزون الشريك مجمَّعةً تحت المستند المسبِّب |
| GET | `partners/{id}/invoices/` | `PartnerViewSet.invoices` — فواتير البيع والشراء بحالة الدفع، وللطرف الدائن مستحقّات التخليص/الشحن/النقل (`_party_accrual_invoice_rows`: بوسم الشحنة و`shipment_id` رابطاً إليها، والمدفوع يشمل الإشعارات المدينة المربوطة `noted`) |
| GET | `partners/{id}/surplus/` | `PartnerViewSet.surplus` — `{"rows": …}` من `sales.services.party_surplus_rows`: فائض الطرف مصدراً مصدراً (سند/إشعار) بعملته — أعلى نافذة الاسترداد |
| GET | `partners/{id}/payment-defaults/` | `PartnerViewSet.payment_defaults` (`?direction=Incoming\|Outgoing`) |
| GET/POST | `customer-notes/` | `CustomerNoteViewSet` (فلاتر `partner`، `target_type`، `target_id`) |
| GET | `customer-notes/alerts/` | `CustomerNoteViewSet.alerts` — «عاجل» مستحقة لطرف بعينه |
| GET | `customer-notes/reminders-due/` | `CustomerNoteViewSet.reminders_due` |

## الاعتماديات
**يعتمد على:**
- `accounting` — **api**: `partners/signals.py` (`from accounting.api import sync_partner_accounting`). المنطق نفسه (بأكواده الـhardcoded: `2101`/`1103`/`2106`-`2109` في `_expected_parent_code_for_partner_type` بـ`accounting/api.py`، و`3300` تحت جذر `3` بـ`api.py:440-450`، وكود الحساب الجديد = `parent.code + str(partner.id).zfill(4)` بـ`api.py`) يسكن الآن داخل accounting.
- `accounting` — **services**: `partners/views.py:47,73` (`partner_posted_balance`) و`partners/views.py` (`partner_account_statement`) — الأرصدة لا تُحسب هنا.
- `tenants` — **models**: `partners/models.py` (`Tenant, Currency`).
- `core` — **services**: `partners/views.py:12-14` (`ApiAuthAndUser`، `enforce_limits`، `get_tenant`) والحدّ `partners.records` عند الإنشاء (`views.py`)، و`core.payments.document_payment_summary` (`views.py`).
- `sales` / `logistics` — **models كسولة داخل الإجراءات فقط**: `views.py:74-75` و`views.py:141-144` (`SalesInvoice`، `PurchaseInvoice`) — استيراد داخل الدالة عمداً لكسر الدوران.

**يعتمد عليه:** `accounting` (`accounting/models.py`)، `sales` (`sales/models.py`)، `inventory` (`inventory/models.py`)، `logistics` (`logistics/models.py`)، `core` (`core/plans.py`)، `bridge` (`bridge/views.py`)، `accountant_portal` (**models** — `accountant_portal/practice.py` يستورد `partners.models.Partner`/`CustomerNote` مباشرةً، ISSUE #86: زبون مكتب المحاسبة صار طرفاً). عملياً كل موديل فاتورة أو حركة في المشروع يحمل FK إلى `Partner`.
`Partner.engagement`/`Partner.managed_tenant` مراجعُ نصّية إلى `accountant_portal.AccountantEngagement`/`tenants.Tenant` — الاتجاه يبقى وحيداً: `partners` لا يستورد `accountant_portal` بكود حقيقي أبداً.

## قواعد لا يجوز كسرها
- **`partners/apps.py:7-8` يستورد `partners.signals` داخل `ready()`** — إزالته تُعطّل إنشاء حسابات الأطراف والأرصدة الافتتاحية بصمت.
- **الحماية من تكرار القيد الافتتاحي طبقتان**: فحص وجود `reference_type='PARTNER_OPENING'` مع `reference_id=partner.id` في `accounting/api.py` (`sync_partner_accounting`)، وidempotency ذرّية على المفتاح نفسه داخل `post_journal` — لا تكسر أياً منهما.
- **أكواد الشجرة `2101`/`1103`/`2106`/`2107`/`2108`/`2109` و`3300` و`3` مربوطة نصّاً بالكود** (`accounting/api.py` (`_expected_parent_code_for_partner_type`)): إعادة ترقيم شجرة الحسابات في `seed_*_coa` تُسقط ربط الأطراف. **الأب الغائب يُكمَل عند الحاجة** (`_ensure_partner_parent` ← `tenants/services.py` (`ensure_operational_accounts`)، idempotent ويحترم قالب الشركة) — شركاتٌ بُذرت قبل 2109 كان ناقلها يُنشأ بلا حساب بصمت ثم يقع سنده على 2101. **والخلل لا يُبتلع**: ردّ حفظ الطرف يحمل `account_warning` (`partners/views.py` — `_with_account_warning` ← `accounting/api.py` (`partner_account_problem`)) فتعرضه نافذة البطاقة، و`accounting/management/commands/audit_partner_accounts.py` يعرض الأطراف بلا حساب أو تحت أبٍ لا يطابق نوعهم ويصلحهم بـ`--apply` عبر `sync_partner_accounting` نفسها مع سجلّ تدقيق.
- **الشركة تأتي من الطرف نفسه لا من تخمين**: بلا `tenant` تُسجَّل رسالة خطأ ويُتخطّى إنشاء الحساب (`api.py:294-300`, `444-450`).
- **قيد الرصيد الافتتاحي عبر `post_journal`** (قرار 2026-08-11، `3358bf7`): idempotent على `(PARTNER_OPENING, partner.id)` وآمن تحت السباق، ويتطلب **فترة مالية مفتوحة** عند تاريخ الرصيد — وإلا يُسجَّل الخطأ ويُتخطى القيد بلا إسقاط حفظ الشريك؛ تصحيح التاريخ وإعادة الحفظ يعيدان المحاولة (`accounting/tests/test_api.py`).
- **`opening_balance` رقم بإشارة، والصفر وحده يعني «لا قيد»**: الموجب = العميل مدين لنا / نحن مدينون للمورّد، والسالب = دفعة مقدّمة تقلب طرفَي القيد (عميلٌ دفع مقدّماً ⇒ دائن على حسابه ومدين على `3300`، والمورّد المدفوع سلفاً مرآته). لا سطر بمبلغ سالب — الاتجاه بالطرف وحده (`accounting/api.py` (`create_partner_opening_balance`)).
- **تاريخ الرصيد يتبع افتتاح الشركة حين لا يُدخله المستخدم**: `opening_balance_date` ← `OpeningBalance.entry_date` (`accounting/opening_balance.py` (`company_opening_entry_date`)) ← تاريخ اليوم، ويُثبَّت على الطرف بعد الترحيل بتحديث مباشر (لا `save()`، كي لا يُعيد `post_save` الدورة).
- **رصيدٌ مرحّل لا يتغيّر بالتعديل — يُعكس أولاً**: تعديل `opening_balance` بعد الترحيل لا يمسّ القيد (idempotency)، والمسار الوحيد هو `POST /api/accounting/opening-balance/partners/{id}/reverse/` (`accounting/opening_balance.py` (`reverse_partner_opening`)) الذي يحذف القيد عبر `unpost_document`، ثم يُنشئه حفظُ الطرف التالي بالمبلغ الجديد. شاشة الأرصدة الافتتاحية تعرض `posted_amount` (المرحَّل فعلاً) بجانب `opening_balance` (المُدخل) كي لا يُظنّ أن التعديل وصل الدفاتر.
- **الإشارة تُعيد استخدام حساب موجود بنفس الاسم تحت الأب نفسه** إن لم يكن مربوطاً بطرف آخر بدل إنشاء تكرار (`api.py:330-343`).
- **تغيير `partner_type` يعيد نقل الحساب لأبيه المتوقّع** ويغيّر `account_type` تبعاً له (`api.py:376-390`) — لا تُعدّل `parent` يدوياً في مكان آخر.
- **`supplier_scope=''` (غير مصنَّف) يظهر في قائمتي المحلي والدولي معاً** (`views.py:197-199`، `models.py:58-64`) — تضييق الفلتر يُخفي موردين قائمين (اختبار `test_supplier_scope`).
- **`get_queryset` يُرجع `.none()` عند غياب الشركة** في `PartnerViewSet` و`CustomerNoteViewSet` (`views.py:188-191`، `486-488`).
- **لا رقم ضريبي ولا رقم حساب بنكي «شبيه» لطرفين** — المقارنة بعد التطبيع في بايثون لا في SQL (`serializers.py:155-170`، `views.py:306-325`)، وحساب بنكي افتراضي واحد فقط ويجب أن يكون فعّالاً (`views.py:346-371`).
- **`enforce_limits(tenant, 'partners.records')` قبل أي إنشاء** (`views.py`).
- **إشارة الرصيد قاعدةٌ واحدة في الخادم** — `partners/models.py` (`is_creditor_party`، `CREDITOR_PARTNER_TYPES`): المورد والمخلّص ووكيل الشحن والناقل المحلي والناقل رصيدهم دائن − مدين، والعميل مدين − دائن. يقرؤها `balance` و`profile` و`statement` (`running_balance`/`balance_before`/`closing_balance`) وتقرير أستاذ الطرف (`core/reports/ledger_import.py` — `_partner_is_customer`). كانت المقارنة بـ«supplier» وحده فظهر رصيد المخلّص حاييم −7,551.50 بدل «له 7,551.50»؛ ونافذة سند القبض (`SalesCustomerPaymentsPage.tsx` — `CustomerLedgerBalance`) تقرأ `is_creditor` فتقول «له/عليه» للدائن. ومنتقي المستفيد من تظهير الشيك (`AccountingChequesPage.tsx`) وأعمدة الأرصدة الافتتاحية بالأنواع الدائنة كلّها وبأسمائها، وكرت المخلّص/الوكيل/الناقل بلا «فاتورة شراء» ولا «عرض سعر شراء» (`partnerActions.ts` — `partnerActionGroups` بـ`partnerType`).
- **جانب الطرف واتجاه سنده قاعدةٌ واحدة في الواجهة** — `frontend_v2/utils/partnerActions.ts` (`partnerKindFromType`، `partnerVoucherDirections`): المورد والمخلّص ووكيل الشحن والناقل المحلي والناقل **أطرافٌ دائنة** ⇒ «سند صرف» افتراضياً و«سند قبض (استرداد)» خيارٌ ثانٍ صريح؛ العميل «سند قبض» وحده. يقرؤها كرت الطرف (`PartnerProfilePage.tsx`) وقائمة زر اليمين ونافذة سند الصرف (`NewSupplierPaymentModal.tsx`). مقارنةُ `partner_type === 'supplier'` كانت تجعل المخلّص «عميلاً» في كرته وتُخرجه من منتقي سند الصرف. الخادم لا يفلتر النوع في السندين: القيد Dr ذمّة الطرف / Cr الصندوق للصرف ومرآته للقبض (`logistics/tests/test_creditor_party_vouchers.py`).

- **الطرف الذي عليه حركات لا يُحذف — يُوقَف** (`partners/views.py` (`PartnerViewSet.destroy`، `_delete_blockers`)): العلاقات تُقرأ من `Partner._meta.related_objects` فلا تفوت علاقةٌ تُضاف لاحقاً، وكلّ ما ليس في `DELETE_OWNED` (بنوكه وملاحظاته وسجلّ نشاطه وقواعد ترميزه وأصناف مورّده وعروض أسعاره) ويحمل صفّاً يمنع، وكذلك قيدٌ على حسابه بلا وسم. `ProtectedError` وحده لم يكن حارساً: القيود والتخليصات والشحنات تشير للطرف بـ`SET_NULL` فكان الحذف يمرّ ويمسح وسمه عنها بصمت. الحذف الناجح يحذف حسابه الفارغ (`accounting/api.py` (`delete_account_if_unused`)). والإيقاف `is_active=False` يُخفيه من القائمة و`lookup` ومنتقيات الوكيل (`partners/agent_api.py`) ويُبقي كرته وكشفه.

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `partners/tests/test_customer_notes.py` | إنشاء الملاحظة مع `created_by`، الفلترة بـ`?partner`، العزل بين الشركات، `reminders-due` و`alerts` |
| `partners/tests/test_partner_card_payment_clarity.py` | `invoices/` يطابق حالة الدفع في شاشة الفواتير، و`link_key` يربط الحركة بمستندها في كشف الحساب، والسند على فاتورتين يحمل `link_targets` بمبلغ كلٍّ منهما |
| `core/tests/test_creditor_aging_and_balances.py` | أعمار الذمم الدائنة = رصيد كل طرفٍ في الدفتر (المخلّص والناقل)؛ «أرصدة الموردين» بكل الأنواع الدائنة وعمود النوع وفلتره؛ كرت المخلّص بمستحقّاته ومجموعها |
| `partners/tests/test_creditor_party_sign.py` | إشارة الرصيد لكل نوع طرف دائن في `balance`/`profile`/`statement` (دائن − مدين) والعميل كما كان |
| `logistics/tests/test_statement_accrual_links.py` | مستحق التخليص مع دفعته المباشرة وسنده الموزَّع عليه وحده في مجموعةٍ واحدة، وسند على ثلاثة مستحقّات صفٌّ واحد بـ«3 مستحقات: …» والرصيد الختامي لا يتغيّر، وسند شراء على فاتورتين |
| `partners/tests/test_partner_stock_movements.py` | حركات مخزون الشريك مجمَّعةً تحت مستندها، وعزلها عن الشركات الأخرى (العدد تسريبٌ أيضاً) |
| `partners/tests/test_partner_duplicate_identifiers.py` | رفض الرقم الضريبي/البنكي الشبيه، مُنطاقاً بالشركة وعبر كل الأنواع |
| `partners/tests/test_supplier_scope.py` | غير المصنَّف يظهر في الجانبين — الفصل لا يُخفي مورداً قائماً |
| `partners/tests/test_partner_list_pagination.py` | حدود `list`/`lookup` والفلترة والعزل وعدد الاستعلامات |
| `partners/tests/test_partner_payment_defaults.py` | حسابات البنك المعادة وافتراضات الشيك الوارد |
| `accounting/tests/test_partner_accounts_audit.py` | الأب 2109 الغائب يُكمَل فيُنشأ للناقل حسابه، وردّ الحفظ يحمل `account_warning` حين يتعذّر، و`audit_partner_accounts` يقرأ ثم يصلح (بلا حساب / أبٌ خاطئ) ولا يجد شيئاً في تشغيله الثاني |
| `partners/tests/test_partner_deactivate_delete.py` | الموقوف يختفي من القائمة و`lookup` ويظهر بـ`include_inactive=1` وكرته تُفتح؛ حذف طرفٍ بقيد موسوم (SET_NULL) أو بعرض سعر (PROTECT) ⇒ 400 برسالة لا 500 ولا حذف صامت؛ حذف طرفٍ بلا حركات يحذف حسابه الفارغ |
| `partners/tests/test_supplier_kinds_filter.py` | `kinds` يجمع «مورد محلي + مخلّص» بلا تسريب الوكيل ذي النطاق الفارغ، `partner_type`/`supplier_scope` قوائم، `kind-counts` يستثني الموقوف والشركات الأخرى، و`bulk-scope` يمسّ موردي الشركة وحدهم |
| `frontend_v2/e2e/supplier-management-kinds.spec.ts` | رقاقات الأصناف تُطلب من الخادم بعدّادها وتبقى بعد إعادة التحميل؛ «فتح البطاقة» لكل صف؛ التصنيف الجماعي؛ «جديد» يسأل الصنف ثم يفتح البطاقة بنوعٍ ونطاقٍ مثبّتين |
| `logistics/tests/test_creditor_party_vouchers.py` | سند صرف للمخلّص ووكيل الشحن والناقل المحلي بقيد Dr ذمّته / Cr الصندوق، وسند قبض منه (استرداد) يدائن ذمّته |
