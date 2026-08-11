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
| `partners/apps.py` | `ready()` يستورد `partners.signals` — بدونه لا يعمل أي شيء تلقائي | 8 |

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `Partner` | `name`، `partner_type`، `supplier_scope`، `tax_number`، `credit_limit`، `opening_balance`، `opening_balance_date`، `assigned_price_tier`، `end_of_dealing_date`، `row_color` | `tenant` (CASCADE)، `group` → `PartnerGroup`، `linked_account` → `accounting.Account` (SET_NULL)، `default_cost_center` → `accounting.CostCenter`، `currency` |
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
| GET/POST | `partners/` | `PartnerViewSet` (فلاتر: `partner_type`، `supplier_scope`، `assigned_price_tier`، `search`) |
| GET | `partners/lookup/` | `PartnerViewSet.lookup` — مصفوفة خام محدودة (افتراضي 200، حد أقصى 500) |
| GET | `partners/{id}/balance/` | `PartnerViewSet.balance` — رصيد حالي + `projected_balance` بعد `?proposed_total=` |
| GET | `partners/{id}/profile/` | `PartnerViewSet.profile` — Dr/Cr + إجمالي المبيعات/المشتريات + آخر معاملة |
| GET | `partners/{id}/statement/` | `PartnerViewSet.statement` (`limit` ≤ 200، `offset`، `ordering`) |
| GET | `partners/{id}/invoices/` | `PartnerViewSet.invoices` — فواتير البيع والشراء بحالة الدفع |
| GET | `partners/{id}/payment-defaults/` | `PartnerViewSet.payment_defaults` (`?direction=Incoming\|Outgoing`) |
| GET/POST | `customer-notes/` | `CustomerNoteViewSet` (فلاتر `partner`، `target_type`، `target_id`) |
| GET | `customer-notes/alerts/` | `CustomerNoteViewSet.alerts` — «عاجل» مستحقة لطرف بعينه |
| GET | `customer-notes/reminders-due/` | `CustomerNoteViewSet.reminders_due` |

## الاعتماديات
**يعتمد على:**
- `accounting` — **api**: `partners/signals.py:15` (`from accounting.api import sync_partner_accounting`). المنطق نفسه (بأكواده الـhardcoded: `2101`/`1103`/`2106`-`2109` في `_expected_parent_code_for_partner_type` بـ`accounting/api.py:262`، و`3300` تحت جذر `3` بـ`api.py:440-450`، وكود الحساب الجديد = `parent.code + str(partner.id).zfill(4)` بـ`api.py:346`) يسكن الآن داخل accounting.
- `accounting` — **services**: `partners/views.py:47,73` (`partner_posted_balance`) و`partners/views.py:118` (`partner_account_statement`) — الأرصدة لا تُحسب هنا.
- `tenants` — **models**: `partners/models.py:2` (`Tenant, Currency`).
- `core` — **services**: `partners/views.py:12-14` (`ApiAuthAndUser`، `enforce_limits`، `get_tenant`) والحدّ `partners.records` عند الإنشاء (`views.py:421`)، و`core.payments.document_payment_summary` (`views.py:143`).
- `sales` / `logistics` — **models كسولة داخل الإجراءات فقط**: `views.py:74-75` و`views.py:141-144` (`SalesInvoice`، `PurchaseInvoice`) — استيراد داخل الدالة عمداً لكسر الدوران.

**يعتمد عليه:** `accounting` (`accounting/models.py:4`)، `sales` (`sales/models.py:8`)، `inventory` (`inventory/models.py:3`)، `logistics` (`logistics/models.py:3`)، `core` (`core/plans.py:98`)، `bridge` (`bridge/views.py:66`). عملياً كل موديل فاتورة أو حركة في المشروع يحمل FK إلى `Partner`.

## قواعد لا يجوز كسرها
- **`partners/apps.py:7-8` يستورد `partners.signals` داخل `ready()`** — إزالته تُعطّل إنشاء حسابات الأطراف والأرصدة الافتتاحية بصمت.
- **`create_partner_opening_balance` (في `accounting/api.py:425`) يكتب القيد يدوياً بـ`is_posted=True`** — أي أنه **يتجاوز `post_journal`**، فلا فحص فترة مالية ولا فحص طبيعة الحساب ولا `create_audit_log` (دين موثّق في نتائج المرحلة 2 بـ`docs/REFACTOR_PROMPTS.md`). الحماية الوحيدة من التكرار هي فحص وجود `reference_type='PARTNER_OPENING'` مع `reference_id=partner.id` (`api.py:392-401`) — لا تكسر هذا الفحص.
- **أكواد الشجرة `2101`/`1103`/`2106`/`2107`/`2108`/`2109` و`3300` و`3` مربوطة نصّاً بالكود** (`accounting/api.py:262-272, 440-450`): إعادة ترقيم شجرة الحسابات في `seed_*_coa` تُسقط ربط الأطراف صامتاً (`Account.DoesNotExist` تُبتلع بـ`pass`).
- **الشركة تأتي من الطرف نفسه لا من تخمين**: بلا `tenant` تُسجَّل رسالة خطأ ويُتخطّى إنشاء الحساب (`api.py:289-295`, `430-436`).
- **الإشارة تُعيد استخدام حساب موجود بنفس الاسم تحت الأب نفسه** إن لم يكن مربوطاً بطرف آخر بدل إنشاء تكرار (`api.py:330-343`).
- **تغيير `partner_type` يعيد نقل الحساب لأبيه المتوقّع** ويغيّر `account_type` تبعاً له (`api.py:376-390`) — لا تُعدّل `parent` يدوياً في مكان آخر.
- **`supplier_scope=''` (غير مصنَّف) يظهر في قائمتي المحلي والدولي معاً** (`views.py:197-199`، `models.py:58-64`) — تضييق الفلتر يُخفي موردين قائمين (اختبار `test_supplier_scope`).
- **`get_queryset` يُرجع `.none()` عند غياب الشركة** في `PartnerViewSet` و`CustomerNoteViewSet` (`views.py:188-191`، `486-488`).
- **لا رقم ضريبي ولا رقم حساب بنكي «شبيه» لطرفين** — المقارنة بعد التطبيع في بايثون لا في SQL (`serializers.py:155-170`، `views.py:306-325`)، وحساب بنكي افتراضي واحد فقط ويجب أن يكون فعّالاً (`views.py:346-371`).
- **`enforce_limits(tenant, 'partners.records')` قبل أي إنشاء** (`views.py:421`).

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `partners/tests/test_customer_notes.py` | إنشاء الملاحظة مع `created_by`، الفلترة بـ`?partner`، العزل بين الشركات، `reminders-due` و`alerts` |
| `partners/tests/test_partner_card_payment_clarity.py` | `invoices/` يطابق حالة الدفع في شاشة الفواتير، و`link_key` يربط الحركة بمستندها في كشف الحساب |
| `partners/tests/test_partner_duplicate_identifiers.py` | رفض الرقم الضريبي/البنكي الشبيه، مُنطاقاً بالشركة وعبر كل الأنواع |
| `partners/tests/test_supplier_scope.py` | غير المصنَّف يظهر في الجانبين — الفصل لا يُخفي مورداً قائماً |
| `partners/tests/test_partner_list_pagination.py` | حدود `list`/`lookup` والفلترة والعزل وعدد الاستعلامات |
| `partners/tests/test_partner_payment_defaults.py` | حسابات البنك المعادة وافتراضات الشيك الوارد |
