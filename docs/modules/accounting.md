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
| `accounting/cashbox.py` | حلّ حساب أب الصناديق وحساب رأس المال، وتوليد أكواد الأبناء (`allocate_child_account_code` — تخدم الصناديق والبنوك معاً) | 103 |
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
| `CashBoxLedgerAccount` | `external_id`، `name`، `currency_code`، `is_default`، `is_active`، `notes` | `account` (OneToOne → Account، تحت «1110»)؛ فريد `(tenant, external_id)` |
| `CashBoxUserDefault` | — | `tenant`، `user`، `cash_box`؛ فريد `(tenant, user)` |
| `CashBoxFxLot` | `original_fc`، `remaining_fc`، `rate`، `source` | `cash_box`، `journal` |
| `CashTransfer` | `number`، `transfer_date`، `amount`، `rate` | طرفان اختياريان لكلٍّ من الجهتين (`from_cash_box`/`from_bank_account` و`to_*`)، `journal` |
| `CashCount` | `count_date`، `book_balance`، `counted_total`، `difference`، `denominations`، `status` | `cash_box` (PROTECT)، `journal` |
| `ExpenseVoucher` (issue #56) | `number`، `date`، `amount`، `tax_amount`، `payment_method` (`cash`\|`cheque`\|`on_account`)، `kind` (`normal`\|`return`، issue #80)، `is_posted` | `expense_account` (PROTECT)، `cash_or_bank_account` (PROTECT, يُملأ فقط عند `cash`)، `beneficiary_partner` (PROTECT, **اختياري تماماً**)، `journal` (SET_NULL) |
| `RevenueVoucher` (issue #80) | `number`، `date`، `amount`، `tax_amount`، `payment_method` (`cash`\|`cheque`\|`on_account`)، `kind` (`normal`\|`return`)، `is_posted` | `revenue_account` (PROTECT)، `cash_or_bank_account` (PROTECT, يُملأ فقط عند `cash`)، `payer_partner` (PROTECT, **اختياري تماماً**)، `journal` (SET_NULL) — مرآة حرفية لـ`ExpenseVoucher` |
| `PartnerAccountCodingRule` (issue #84) | — | `partner` (CASCADE)، `account` (PROTECT)؛ فريد `(tenant, partner)` — قاعدة ترميز واحدة لكل طرف، تُكتب عند حفظ صفٍّ ناجح في الحفظ الدفعي وتُقترح في الصفّ التالي |
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

### الخزينة — الصندوق كيانٌ أول، وحسابُه في الشجرة وجهُه المحاسبي
الصندوق `CashBoxLedgerAccount` يُنشأ بنداءٍ واحد ذرّي
(`accounting/services.py` (`create_cash_box`)، على نمط `create_bank_account`)
يكتب معاً: الحساب تحت «1110» بكود `1110B0001` وبـ`sub_type='cash_box'`، وسطر
الصندوق، ووثيقة مرآته في `bridge`. قبلها كان الإنشاء **نداءين من المتصفح**
(المرآة أولاً ثم الحساب) بلا معاملة تجمعهما، فسقوطُ الثاني يترك صندوقاً بلا
حساب — مالٌ يتحرّك بلا وجهٍ في الدفاتر، وواجهةٌ فيها زرّ إصلاح يدوي.
**المرآة صارت مشتقّة**: الخادم وحده يكتبها، ورصيدُها لا يُعتمد — مصدر الرصيد
دفتر الأستاذ (`cash_box_balance`). و`external_id` مفتاح توافق يولّده الخادم.

**دورة الحياة**: `update_cash_box` (الاسم يزامن حساب الشجرة والمرآة معاً؛ تغيير
عملة صندوقٍ له طبقات FIFO **مرفوض** لأن رصيده الدفتري محسوب بها)، و
`set_default_cash_box` (افتراضيٌّ واحد لكل شركة، مفروضٌ **في طبقة الخدمة داخل
معاملة** لا بقيد شرطي: MySQL بلا فهارس جزئية). **لا حذف** — الحساب يحمل حركة،
والتعطيل (`is_active=False`) يخفيه من المنتقيات.

#### سلّم حلّ حساب الصندوق — مصدرٌ واحد
`accounting/services.py` (`resolve_cash_account`) هو **المحلّ الوحيد** لكل
المستندات: الاختيار الصريح ← صندوق المستخدم الافتراضي (`CashBoxUserDefault`،
يُتخطّى إن خالف عملة المستند) ← صندوق الشركة الافتراضي ← إعدادات
المبيعات/الشراء ← الشجرة المعيارية (شبكة أمان) ← **خطأ إرشادي**.
`resolve_default_cash_account` صار غلافاً مفوِّضاً يُعيد `None` بدل الاستثناء
(لمستدعيه القدامى)، و`accounting/cashbox.py`
(`resolve_default_cash_box_account`) **مسحوب** ولم يبقَ له مستدعٍ إلا الأمر
الإداري `rewire_logistics_payment_cash_lines`.

> **«أوّل حساب نقدي» ليست خطوةً في السلّم ولا في الواجهة.** كانت السلسلة القديمة
> تطابق `code` تماماً في `("1101","1102","1110")` — و«1110» أبُ الصناديق لا
> صندوق — فلم تكن تُعيد صندوقاً حقيقياً **بنيوياً**: شركةٌ بعشرة صناديق تقع كل
> سنداتها على «1101 النقدية» العامّ. وفي الواجهة كان
> `frontend_v2/components/procurement/invoices/InvoiceForm.tsx` يملأ رأس
> الفاتورة بـ`allAccounts.find(accountMatchesPurpose(a,"cash"))` — أوّل حساب
> بترتيب الكود، أي صندوق الشيقل دائماً — ثم يُرسلها فتبدو اختيار المستخدم.
> السلّم الواجهيّ الآن في `frontend_v2/utils/cashBox.ts`
> (`pickDefaultCashAccount`)، وترتيبُ الشجرة ليس نيّةَ مستخدم.

> **وشبكة الأمان الأخيرة لا ترى حسابات الأطراف.** بعد سلسلة الأكواد تقرأ الخطوة
> الأخيرة **اسمَ** الحساب (`صندوق`/`نقد`/`بنك`)، والاسم ليس ملكاً للشركة وحدها:
> `accounting/api.py` (`sync_partner_accounting`) يسمّي حساب الطرف باسم صاحبه
> ويعيد تسميته معه، فزبونٌ اسمه «محمد نقدي» يمنح حساب ذممه اسماً يطابق «نقد»
> حرفاً بحرف — فيصير حسابُه صندوقَ الشركة: قيدٌ يدين ويدائن الطرف نفسه، أو
> يُدائن ذمم زبونٍ كأنها نقد، **بلا رسالة خطأ**. تُستبعد حسابات الأطراف الآن
> قبل قراءة الاسم بـ`accounting/services.py` (`_without_partner_accounts`):
> الرابط الموثوق (`Partner.linked_account`) والتصنيف المخزَّن (`sub_type` في
> `receivable`/`payable`) معاً — الرابط يمسك المربوط اليوم، والتصنيف يمسك حساب
> ذممٍ فقد رابطه أو لم يُربط بعد. وهي **دالّة لا سطر مكرَّر** لأن للقاعدة
> مستعملاً ثانياً في مسار العرض: `core/reports/treasury.py` (`_cash_movements`)
> كان يعدّ ذمّة زبونٍ اسمه «صندوق التوفير» حركةَ خزينة. ولم تُلغَ الشبكة — حسابٌ
> نقديٌّ لا يخصّ طرفاً يبقى مقبولاً، وشركةٌ لا تملك إلا حساب ذمم تقع على
> **الخطأ الإرشادي** لا على مالٍ خاطئ صامت.

> **والمرفق يغلب الرأس**: `sales/services/flow.py`
> (`_resolve_settlement_cash_account_id`) و`logistics/services.py`
> (`settle_attached_purchase_intent`) تقرآن `attached_cash_account` **قبل**
> `cash_or_bank_account`. الأول لا يكتبه إلا مسار «إرفاق دفعة» فهو اختيار
> المستخدم الصريح، والثاني تملؤه الواجهة تلقائياً. بالترتيب المعكوس كان الرأس
> يبتلع الاختيار فيُدائَن صندوقٌ لم يخترْه أحد.

#### الكشف والعمليات
- `cash_box_statement` — نظير `bank_account_statement` بلا أعمدة المطابقة:
  افتتاحيٌّ وصفوفٌ برصيدٍ جارٍ وختاميّ، بترتيب `(تاريخ، قيد، سطر)` مستقر. كانت
  الشاشة تدمج المرآة بالأستاذ **في المتصفح** بترتيبٍ مُلفَّق (الأستاذ مثبَّت على
  `T12:00:00` ثم `journal_id ‰ 1000 × 0.001`)، فعمود «الرصيد» لم يكن رصيداً جارياً.
- `cash_box_adjustment(direction='in'|'out')` — إيداع/سحب بقيدٍ واحد مقابل حساب
  رأس المال (أو حسابٍ مقابل صريح). السحب يُرفض إن جاوز الرصيد. عمّم
  `deposit-journal` القديمة (إيداعٌ فقط ومفتاحها `external_id`)، وهي باقية للتوافق.
- `create_cash_transfer` — تحويل بين خزينتين بمستندٍ واحد وقيدٍ واحد؛ والوجهةُ
  صندوقُ عملةٍ أجنبية تُفوَّض إلى `fx_fifo.transfer_ils_to_fx` لأن طبقات FIFO
  مصدر تكلفة العملة، وقيدٌ مباشر بجانبها يفسدها بصمت.
- `post_cash_count` — فرق الجرد إلى «زيادة الصندوق» (`4202`) أو «عجز الصندوق»
  (`5206`) — نمط Odoo (Profit/Loss Account). الفرق صفراً ⇒ لا قيد.
- الأمر `backfill_cash_boxes` (`--link` و`--history`): يربط صناديق ما قبل توحيد
  الإنشاء بالشجرة، ويرحّل **قيداً افتتاحياً واحداً لكل صندوق** بفرق المرآة عن
  الأستاذ في تاريخ القطع (قرار المالك: لا ترحيل حركة-بحركة يكتب في فتراتٍ سابقة).
  بلا خيارات = تقريرٌ فقط، وهو idempotent.

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

**المنتجات المتتبَّعة تسلسلياً في بضاعة الافتتاح** (`_serial_items`): الافتتاح
يُدخل الكمية للمخزن ولا يُنشئ وحدةً مُرقَّمة واحدة — `ProductSerial` تُنشأ من
استلام الشراء — فشركةٌ نمط بيعها «إجباري» تُمنع من بيع بضاعة افتتاحها عند
`inventory/serials.py` (`consume_sales_serials`) برسالة «المتوفر في المخزن 0
والمطلوب N» لا تقول أين تُرقَّم. لذلك يحمل الملخّص `serial_items`: صفٌّ لكل منتج
متتبَّع في بنود الافتتاح بالمُسجَّل والمطلوب، تعرضه الشاشة بعد الترحيل برابطٍ إلى
مسار الترقيم القائم `products/{id}/serials/register/`. **إرشاد لا حارس**: الافتتاح
صحيح بلا أرقام والبيع وحده هو ما يحتاجها، فلا يُمنع الترحيل. التجميع بالمنتج لا
بالبند (الوحدة المُرقَّمة بلا مستودع)، و«المُسجَّل» كل وحدات المنتج بأي حالة لا
«في المخزن» وحدها — فبيعُ وحدة لا يُعيد منتجاً أُتمّ ترقيمه ناقصاً. استعلام واحد
مهما كثرت البنود، مفلترٌ بالشركة.

**الشاشة**: `frontend_v2/components/accounting/OpeningBalancesPage.tsx` — مسار
`/accounting/opening-balances` تحت قائمة «المحاسبة». ثلاثة تبويبات (حسابات ·
أطراف · مخزون) ورأسٌ يعرض تاريخ البدء وتاريخ القيد المشتقّ منه والحالة و«صافي
حقوق الملكية الافتتاحية». الترحيل يحفظ المسودة أولاً ثم يرحّل — فالمرحَّل هو ما
تراه الشاشة لا آخر مسودة محفوظة — وهو وإلغاؤه خلف حوار تأكيد. تبويب الأطراف
يعرض لكل طرف المُدخل والمرحَّل معاً وزرّ عكس قيده، ومنتقي الحسابات يُخفي ما
يرفضه `assert_account_allowed` (والخادم يبقى هو الحارس). خطأ الفترة المالية
يظهر بزرّ ينقل إلى شاشة الفترات. وتبويب المخزون بعد الترحيل يعرض لوحة المنتجات
المتتبَّعة تسلسلياً (المُسجَّل/المطلوب) بزرّ يفتح كرت المنتج على تبويب «الأرقام
التسلسلية» (`/products/{id}?tab=serials`) — و`ItemForm` يتتبّع تبويبه النشط
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
def vat_period_totals(tenant_id: int, period_from, period_to, *, posted_only: bool = True) -> dict:  # مصدر ض.ق.م الوحيد لفترة — من JournalLine (issue #79)؛ يستهلكها build_vat_statement وVatReportView وclient_financial_summary معاً
def assert_no_final_vat_statement(tenant_id, transaction_date, document_label=""):  # يرفض فكّ ترحيل مستندٍ داخل فترة كشف ض.ق.م `final` (issue #79) — تُستدعى من unpost_document
def create_fiscal_year(tenant, year, granularity='monthly') -> list[FiscalPeriod]:  # 12 شهراً (افتراضي) أو فترة `FY <year>` واحدة — idempotent
def assert_no_period_overlap(tenant_id, start_date, end_date, exclude_pk=None):  # فترتان متقاطعتان لنفس الشركة تُرفضان
def post_journal_entry(journal_id, user=None):  # ترحيل قيد موجود بالـid
def year_end_close(*, tenant_id: int, fiscal_year: int, retained_earnings_account_id: int, user=None) -> dict:  # تصفير الإيراد/المصروف إلى الأرباح المحتجزة
def next_document_number(tenant_id: int, document_type: str, book_number: int = 0, branch_id: int | None = None) -> int:  # ترقيم المستندات عبر TenantBook مع select_for_update
def get_exchange_rate(tenant_id: int, from_currency_id: int, to_currency_id: int, effective_date=None) -> Decimal:  # أحدث سعر ≤ التاريخ، أو مقلوب الاتجاه المعاكس
def convert_amount(amount: Decimal, from_currency_id: int, to_currency_id: int, tenant_id: int, effective_date=None, explicit_rate: Decimal | None = None) -> tuple[Decimal, Decimal]:  # (المبلغ المحوَّل، السعر)
def transfer_cheque(cheque_id, movement_type, *, user=None, notes='', account_id=None, movement_date=None, bank_account_id=None, endorsed_to_id=None):  # تحويل حالة شيك + قيده؛ يرفض حركةً على سندٍ غير مرحّل، ومسودةً داخل مستند، وتاريخاً مستقبلياً أو أسبق من آخر حركة مرحّلة، وإيداعاً بلا بنك متى كان للشركة بنوك نشطة
def deposit_cheques_batch(tenant_id, cheque_ids, *, bank_account_id=None, user=None, movement_date=None, notes='') -> dict:  # إيداع حزمة شيكات ذرّياً (الكلّ أو لا شيء) + بيانات قسيمة الإيداع
def cheque_source_document(cheque) -> dict | None:  # المستند الذي دخل الشيك الدفاتر ضمنه: نوعه ورقمه وهل رُحِّل
def post_cheque_movement_journal(cheque, movement_type, *, when, user=None, account_id=None, branch_id=None):  # قيد حركة شيك واحدة، idempotent
def cheque_wallet(tenant_id: int, *, today=None) -> dict:  # محفظة الشيكات المفتوحة حسب الحالة والاستحقاق
def create_bank_account(*, tenant, bank, name, currency, branch=None, account_number=None, iban=None, is_default=False, notes=None, user=None):  # حساب بنكي + حسابه في الشجرة تحت «1102»
def bank_account_statement(bank_account, *, start_date=None, end_date=None, posted_only=True):  # حركة الحساب البنكي + حالة المطابقة
def close_bank_reconciliation(reconciliation, *, user=None):  # يُرفض الإقفال ما لم يكن الفرق صفراً
def partner_account_statement(*, tenant_id: int, partner_id: int, is_supplier: bool, limit: int = 50, offset: int = 0, ordering: str = "newest", only_payments: bool = False, anchor_reference_type: str | None = None, anchor_reference_id: int | None = None) -> dict:  # كشف حساب الطرف برصيد قبل الحركة وبعدها؛ only_payments يستثني الفاتورة من المعروض ولا يمسّ الحساب؛ والمرساة تُركّز النافذة على مستندٍ بعينه وتُرجع `anchor` (قبل/بعد/الأثر) بلا أن تمسّ الحساب
def partner_posted_balance(tenant_id: int, partner_id: int) -> tuple[Decimal, Decimal]:  # (debit, credit) من الأسطر المرحّلة بالعملة الأساسية
def attach_partner_posted_balance(rows, partner_id_field: str, *, supplier: bool, attr: str):  # أرصدة صفحة محمَّلة باستعلام واحد (للقوائم)
def annotate_partner_posted_balance(queryset, partner_id_field: str, *, supplier: bool, alias: str):  # للصف الواحد/الفلترة فقط — لا للقوائم
def resolve_expense_account(tenant_id: int, name: str, parent_code: str = EXPENSE_VOUCHER_PARENT_CODE):  # حساب مصروف تحت أبٍ معطى («52» افتراضياً) أو يُنشئه — تعميم issue #56
def resolve_revenue_account(tenant_id: int, name: str, parent_code: str = REVENUE_VOUCHER_PARENT_CODE):  # حساب إيراد تحت أبٍ معطى («42» افتراضياً) أو يُنشئه — مرآة resolve_expense_account (issue #80)
def resolve_import_expense_account(tenant_id: int, name: str):  # غلافٌ رفيع فوق resolve_expense_account بأب «53» — لمستدعيه القائمين
def create_expense_voucher(*, tenant, date, amount, currency, tax_amount=Decimal("0"), exchange_rate=Decimal("1"), payment_method, expense_account=None, expense_account_name=None, expense_parent_code=None, cash_or_bank_account_id=None, beneficiary_partner=None, beneficiary_name="", description="", attachment_url="", kind=None, user=None):  # سند مصروف (issue #56): ينشئ ويرحّل فوراً — بلا مورّدٍ إلزامي وبلا مخزون؛ المستفيد اختياري تماماً؛ kind='return' (issue #80) يقلب اتجاه القيد
def unpost_expense_voucher(voucher, *, user=None) -> dict:  # التراجع عن ترحيل سند مصروف عبر unpost_document — مرآة unpost_supplier_payment بلا شيكات
def create_revenue_voucher(*, tenant, date, amount, currency, tax_amount=Decimal("0"), exchange_rate=Decimal("1"), payment_method, revenue_account=None, revenue_account_name=None, revenue_parent_code=None, cash_or_bank_account_id=None, payer_partner=None, payer_name="", description="", attachment_url="", kind=None, user=None):  # سند إيراد (issue #80): مرآة create_expense_voucher حرفياً بعكس الاتجاه؛ الدافع اختياري تماماً، «على الحساب» يَدين ذمّة الدافع أو 1103 العام
def unpost_revenue_voucher(voucher, *, user=None) -> dict:  # التراجع عن ترحيل سند إيراد عبر unpost_document — مرآة unpost_expense_voucher
def upsert_coding_rule(tenant_id: int, partner_id: int, account_id: int):  # قاعدة الترميز (شركة، طرف) ← حساب — عند الحفظ لا الاقتراح؛ طرفٌ واحد ⇒ قاعدةٌ واحدة (issue #84)
def batch_save_vouchers(*, tenant, rows: list[dict], user=None) -> dict:  # نقطة الحفظ الدفعية: كل صفٍّ سندَ إيرادٍ أو مصروف بمعاملته الذرّية الخاصة؛ يكتب قاعدة الترميز داخل معاملة الصفّ الناجح (issue #84)
def resolve_cash_account(tenant_id: int, *, explicit_account_id=None, user=None, currency_code: str | None = None, required: bool = True):  # السلّم الوحيد لحساب الصندوق/البنك — صريح ← افتراضي المستخدم ← افتراضي الشركة ← الإعدادات ← الشجرة ← خطأ إرشادي؛ وشبكةُ الاسم الأخيرة لا تلتقط حساب طرف
def resolve_default_cash_account(tenant_id: int):  # غلافٌ متوافق فوقها يُعيد None بدل الاستثناء
def create_cash_box(*, tenant, name, currency_code="ILS", is_default=False, external_id=None, notes=None, user=None):  # الصندوق + حسابه تحت «1110» + وثيقة مرآته، ذرّياً
def update_cash_box(box, *, name=None, is_active=None, notes=None, currency_code=None, user=None):  # الاسم يزامن الشجرة والمرآة؛ عملة صندوقٍ له طبقات FIFO مرفوضة
def set_default_cash_box(box, *, user=None):  # افتراضيٌّ واحد لكل شركة، ذرّياً
def cash_box_statement(cash_box, *, start_date=None, end_date=None, posted_only=True):  # افتتاحي + صفوف برصيد جارٍ + ختامي
def cash_box_balance(cash_box, *, as_of=None) -> Decimal:  # الرصيد الدفتري من الأسطر المرحّلة
def cash_box_adjustment(cash_box, *, direction, amount, contra_account=None, date=None, memo="", user=None):  # إيداع/سحب بقيدٍ واحد؛ السحب فوق الرصيد مرفوض
def create_cash_transfer(*, tenant, transfer_date, amount, from_cash_box=None, from_bank_account=None, to_cash_box=None, to_bank_account=None, rate=None, notes=None, user=None):  # تحويل بمستند واحد؛ الوجهة FX تمرّ بـfx_fifo
def post_cash_count(count, *, user=None):  # فرق الجرد إلى 4202 (زيادة) أو 5206 (عجز)
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
| GET/POST | `cheques/` | `ChequeViewSet` — فلاتر خادمية: `search` (رقم الشيك/الاسم عليه/البنك/حساب الساحب/الطرف)، `status`، `direction`، `partner`، `due_from`/`due_to`، `deposit_bank_account`، و`ordering` بقائمة بيضاء؛ الترقيم اختياري بـ`?page=` |
| DELETE | `cheques/{id}/` | `ChequeViewSet.destroy` — يرفض شيكاً له حركة مرحّلة، أو تجاوزت حالته اليد، أو مستنده مرحّل |
| POST | `cheques/{id}/transfer/` | `ChequeViewSet` (يستدعي `transfer_cheque`) |
| POST | `cheques/deposit-batch/` | `ChequeViewSet.deposit_batch` — إيداع حزمة ذرّياً؛ الرفض يعود 400 بـ`rejected` (سببٌ لكل ورقة) ولا يُودَع شيء |
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
| GET/POST/PATCH | `cash-box-accounts/` · `cash-box-accounts/{id}/` | `CashBoxLedgerViewSet` — الإنشاء نداءٌ واحد ذرّي (`name` وحده يكفي؛ `external_id` يولّده الخادم)، والتعديل يزامن اسم الحساب. **لا DELETE**، و`PUT` يوجَّه إلى `PATCH` |
| POST | `cash-box-accounts/{id}/set-default/` · `{id}/adjust/` · `{id}/fund-capital/` · `{id}/transfer-from-ils/` | افتراضي الشركة · إيداع/سحب (`direction`) · تمويل FX · تحويل من صندوق شيقل. الصلاحيات: `finance.cashbox.manage` / `.deposit` / `.withdraw` |
| GET | `cash-box-accounts/{id}/statement/` (`start_date`/`end_date`/`include_unposted`) · `{id}/fx-lots/` | كشف برصيد جارٍ خادمي · طبقات FIFO |
| GET/PUT | `cash-box-accounts/my-default/` | صندوق المستخدم الافتراضي؛ `cash_box: null` يحذفه |
| GET/POST | `cash-transfers/` | `CashTransferViewSet` — بصلاحية `finance.cashbox.transfer`؛ لا تعديل ولا حذف (المعالجة بتحويل معاكس) |
| GET/POST/PATCH | `cash-counts/` · `{id}/post/` | `CashCountViewSet` — بصلاحية `finance.cashbox.count`؛ المرحَّل لا يُعدَّل |
| GET/POST | `expense-vouchers/` | `ExpenseVoucherViewSet` (issue #56) — `create` يرحّل فوراً بصلاحية `finance.expense.create`؛ لا PATCH ولا DELETE |
| POST | `expense-vouchers/{id}/unpost/` | `ExpenseVoucherViewSet.unpost` — بصلاحية `finance.expense.unpost` |
| GET/POST | `revenue-vouchers/` | `RevenueVoucherViewSet` (issue #80) — مرآة `ExpenseVoucherViewSet`؛ `create` يرحّل فوراً بصلاحية `finance.revenue.create`؛ لا PATCH ولا DELETE |
| POST | `revenue-vouchers/{id}/unpost/` | `RevenueVoucherViewSet.unpost` — بصلاحية `finance.revenue.unpost` |
| POST | `vouchers/batch-save/` | `VoucherBatchSaveView` (issue #84) — صفوفٌ كل صفٍّ سندَ إيرادٍ أو مصروف، كلٌّ بمعاملته الذرّية الخاصة (`batch_save_vouchers`)؛ الاستجابة `200` دائماً مع `rows`/`succeeded`/`failed` — صفٌّ فاشل (تحقّقٍ أو صلاحية أو خطأ ترحيل) لا يُسقط البقية. صفٌّ ناجحٌ بطرفٍ وحساب يكتب قاعدة ترميز `(tenant, partner)` |
| GET/PATCH/DELETE | `coding-rules/` · `coding-rules/{id}/` | `PartnerAccountCodingRuleViewSet` (issue #84) — قواعد الترميز `(tenant, partner) → account`؛ **لا POST** (الإنشاء أثرٌ جانبي للحفظ الدفعي وحده)، والتعديل/الحذف بصلاحية `finance.coding_rule.manage` |
| GET/POST | `cost-centers/` · `tax-rates/` · `banks/` · `bank-branches/` · `purchase-receipts/` · `currencies/` | حسب `urls.py` |

**«قيد التسوية» ليس نوعاً ثانياً من القيود ولا شاشةً مستقلة** — هو وسمٌ على القيد اليدوي
نفسه: `reference_type='ADJUSTMENT'` بتسميته العربية في `accounting/serializers.py`
(`SOURCE_LABEL_MAP`)، يُصفّى بفلتر `reference_type` القائم ويمرّ بدورة المسودّة/الترحيل
وقاعدة التوازن نفسها بلا استثناء.

## الاعتماديات
**يعتمد على:**
- `partners` — **models مباشرة**: `accounting/models.py` (`from partners.models import Partner`) لبناء `JournalLine.partner` (`models.py`) و`Cheque.partner` (`models.py`)، ويتحقق منه في `services.py` داخل `validate_journal_entry`.
- `tenants` — **models مباشرة**: `accounting/models.py` (`Tenant, Currency`) و`accounting/services.py` (`Currency, TenantBook` لترقيم المستندات).
- `core` — **services**: `accounting/services.py` (`run_tax_period_guards`) من `core.hooks`، و`accounting/views.py` (`core.access`، `core.api_defaults`، `core.tenant_utils`).
- استيرادات كسولة داخل الدوال (لكسر الدوران): `inventory.services` في `services.py`، و`sales.models`/`logistics.models` و`sales.services`/`logistics.services` داخل `accounting/services.py` (`unpost_document`)، وكذلك `sales.models` (`SalesSettings`، `VatStatement`) داخل `accounting/services.py` (`_resolve_vat_account_ids`، `assert_no_final_vat_statement` — issue #79).

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
- **الشيك لا يتحرك خارج جدول اتجاهه** — `accounting/services.py` (`INCOMING_TRANSITIONS`) و`accounting/services.py` (`OUTGOING_TRANSITIONS`) هما المصدر الواحد، و`accounting/services.py` (`transfer_cheque`) ترفض الانتقال غير المسموح، وترفض أي حركة على شيكٍ سندُه غير مرحّل، وتكتب `ChequeMovement` مربوطةً بقيدها. والورقة المظهَّرة لها مخرج واحد هو `bounce` (قيدٌ بين ذمّتين: العميل الساحب يعود مديناً والمستفيد تعود ذمّته، بلا مساس بحسابَي الشيكات).
- **ما يعلنه الخادم للشاشة هو ما يقبله** — `accounting/services.py` (`allowed_movement_options`) تعيد قائمة فارغة لورقةٍ سندُها غير مرحّل بدل عرض حركاتٍ يرفضها الحارس حتماً، و`needs_document_post` و`source_document` في `accounting/serializers.py` (`ChequeSerializer`) يقولان أيّ سند يُرحَّل.
- **بنك الإيداع يُسجَّل على الورقة لا في القيد** — قيد الإيداع يبقى 1107 ÷ 1109 بحسابٍ واحد للشيكات برسم التحصيل؛ و`deposit_bank_account` هو المصدر الوحيد لمعرفة أين الورقة، فيُلزَم متى كانت للشركة حسابات بنكية نشطة (`accounting/services.py` (`CHEQUE_MOVEMENTS_NEEDING_BANK_ACCOUNT`)).
- **`endorsed_to` و`deposit_bank_account` قراءةٌ فقط في الـAPI** — يكتبهما `transfer_cheque` مع قيد الحركة وحده؛ وما يقرأه قيد السند (المبلغ، الاتجاه، الطرف، العملة) مقفولٌ ما دام المستند مرحّلاً (`accounting/serializers.py` (`ChequeSerializer`)).
- **لا تُقفل مطابقة بنكية بفرق ≥ 0.01** (`accounting/services.py` (`close_bank_reconciliation`))، وكل `JournalLine` تُطابَق مرة واحدة (`accounting/models.py` (`BankReconciliationLine`)).
- **الفترة المُقفَلة لا تتغيّر إلا عبر `reopen/` بسبب مسجَّل** — `FiscalPeriodViewSet.perform_update`/`perform_destroy` (`accounting/views.py`) يرفضان أي تعديل أو حذف عليها، ويمنعان حذف فترة في مداها قيد مرحّل (تاريخٌ بلا فترة تغطّيه يشلّ الترحيل وإلغاءه معاً)، وكل تعديل أو حذف ناجح يُكتب في سجل التدقيق.
- **حساب صندوق الدفع يُحلّ من `resolve_cash_account` وحدها** — لا «أوّل حساب
  نقدي» في خادمٍ ولا واجهة، ولا محلّ ثانٍ. و**حساب طرفٍ لا يُنتقى صندوقاً أبداً**:
  شبكة الأمان الأخيرة (المطابقة بالاسم) تستبعد المربوط بـ`Partner.linked_account`
  والمصنَّف `receivable`/`payable` قبل أن تقرأ الاسم. و`attached_cash_account` يغلب
  `cash_or_bank_account` في مسارَي البيع والشراء (`_resolve_settlement_cash_account_id`
  و`settle_attached_purchase_intent`): الأول اختيار المستخدم والثاني تعبئة تلقائية.
- **الصندوق يُنشأ بـ`create_cash_box` وحدها** — نداءٌ واحد يكتب الحساب والربط
  والمرآة معاً. لا إنشاء حسابٍ من جهة ووثيقةِ صندوق من جهة أخرى.
- **الافتراضي واحدٌ لكل شركة، مفروضٌ في الخدمة داخل معاملة** لا بقيد شرطي —
  MySQL بلا فهارس جزئية، فقيدٌ بـ`condition=` يوجد في SQLite ويغيب عن الإنتاج.
- **لا حذف لصندوق** (`http_method_names` بلا `delete`) — حسابه يحمل حركة؛
  التعطيل يخفيه من المنتقيات. و`PUT` موجَّه إلى `PATCH` كي لا يتجاوز تزامنَ الاسم.
- **رصيد الصندوق من دفتر الأستاذ لا من المرآة** — `cash_box_balance`؛ حقل
  `currentBalance` في المرآة مشتقٌّ ولا يُعتمد.
- **`create_audit_log` يجب أن يبقى معزولاً** — سطر تدقيق فاشل لا يجوز أن يُرجِع معاملة المستدعي (سبب اختبار `test_audit_log_isolation`).
- **قيد افتتاحي مرحّل واحد لكل شركة** — مفروضٌ في `accounting/opening_balance.py` (`post_opening_balance`) داخل المعاملة تحت `select_for_update`، **لا بقيد فريد شرطي**: MySQL لا يدعم الفهارس الجزئية، فقيدٌ بـ`condition=` يوجد في قاعدة الاختبارات (SQLite) ويغيب بصمت عن الإنتاج. لا قيد افتتاحي ثانٍ إلا بعد عكس الأول صراحةً.
- **أرصدة الذمم والمخزون لا تُدخل في بنود حسابات الافتتاح** — `assert_account_allowed` يرفضها (ومعها حساب `3300` نفسه وأي حساب مربوط بطرف) عند الحفظ وعند الترحيل معاً؛ أرقامها تأتي من `PARTNER_OPENING` ومن بنود المخزون، وإدخالها هنا يضاعف الرصيد.
- **بضاعة أول المدة تُسجَّل بتاريخ `entry_date` لا `today`** (`accounting/opening_balance.py` (`post_opening_balance`)) — تاريخٌ آخر يضع الحركة في فترة أخرى ويرتّبها خطأً أمام أول شراء فعلي في متوسط التكلفة.
- **سند المصروف (issue #56) لا يفرض مورّداً** — بخلاف `sales.SupplierPayment` (`partner` بـ`PROTECT`)، `ExpenseVoucher.beneficiary_partner` اختياريٌّ تماماً؛ «على الحساب» بلا مستفيد يقع على «2101» العام لا على حساب طرف. الترحيل حصراً عبر `create_expense_voucher` (`post_journal`) والتراجع عبر `unpost_expense_voucher` (`unpost_document`، النوع `EXPENSE_VOUCHER`). **الشاشة**: `frontend_v2/components/accounting/ExpenseVouchersPage.tsx` (مسار `/accounting/expense-vouchers`، تحت مجموعة «المالية» في الشريط الجانبي) — قائمة + نافذة إنشاء ترحّل فوراً؛ المستفيد مطويٌّ افتراضياً في الوضع السهل عبر مفتاح `doc.expense-beneficiary` في `SIMPLE_MASK`. المنطق المشتقّ (حقول كل مصدر دفع ومعاينة القيد) في `frontend_v2/utils/expenseVoucherEntryPreview.ts`.
- **سند الإيراد (issue #80) مرآة حرفية لسند المصروف بعكس الاتجاه** — `RevenueVoucher.payer_partner` اختياريٌّ تماماً كذلك؛ «على الحساب» بلا دافع يقع على «1103» العام، وبدافعٍ شريك يَدين ذمّته (`sales.services.flow._resolve_ar_account_for_partner`، مرآة `_resolve_ap_account`). الترحيل عبر `create_revenue_voucher`/`unpost_revenue_voucher` (النوع `REVENUE_VOUCHER`). **حساب ضريبة المخرجات**: `TaxRate.tax_account` باتجاه `sales`/`both` أولاً — فالسند يكتب حيث تكتب فاتورة البيع فعلاً في شركةٍ نسبتُها على حسابٍ غير «2104» — ثم سقوطٌ إلى الكود المعياري `2104`؛ `vat_period_totals` تقرأ نفس السلسلة بالضبط فيتّفق الكاتب والقارئ دائماً (راجع «مصدرٌ واحد لأرقام ض.ق.م» أدناه). **حقل `kind` (`normal`/`return`) على السندين معاً**: المرتجع يقلب مدين↔دائن لكل أسطر القيد بعد بنائها بالمبلغ الموجب نفسه — مرآة عكس إشارات `SalesInvoice.invoice_kind` في `sales/services/flow.py` — فلا مبالغ سالبة تصل `post_journal`. `resolve_expense_account`/`resolve_revenue_account` كلاهما غلافان رفيعان فوق `_resolve_named_account_under_parent` (يفصل بينهما `account_type` وحده).
- **`TenantBook.get_next_number`/`next_document_number` ينشئان الدفتر كسولاً (`get_or_create`)** — شركةٌ قائمة سبقت إضافة `expense_voucher` إلى `TenantBook.DOCUMENT_TYPES` لا تُعطَّل: أول طلب رقم يخلق دفترها (`book_number=0`) بدل أن يفشل.
- **مصدرٌ واحد لأرقام ض.ق.م (issue #79)**: `vat_period_totals` (`accounting/services.py`) تقرأ `JournalLine` وحدها — لا `SalesInvoice.tax_amount` — لأن كل قيدٍ يمرّ بـ`post_journal` فهي وحدها ترى كل مصدر ضريبة (سند مصروف · إيصال استلام · فاتورة شراء · فاتورة بيع). `sales.services.build_vat_statement` (يحفظ)، `VatReportView` (يعرض)، و`accountant_portal.services.client_financial_summary` (ملخص الزبون) يستدعونها وحدها. **مجموعة حسابات الضريبة اتحادٌ لا اشتقاقٌ واحد**: المخرجات = `TaxRate.tax_account` (اتجاه `sales`/`both`) — كل مسار ترحيلٍ للمخرجات من فاتورة يمرّ بها فعلاً (`sales/services/calc.py` — `_build_tax_buckets`) — **∪ سلسلة السقوط الحرفية** (الكود `2104` إن وُجد، وإلا **كل** حساب `Liability` اسمه يحوي «ضريبة» أو «VAT») **issue #80 (مراجعة الالتزام)**: `create_revenue_voucher` يكتب على «2104» بالكود مباشرةً لا عبر `TaxRate`، فشركةٌ بلا `TaxRate` إطلاقاً (حال «دفتر العميل»: محاسبٌ يرمّز سندات إيرادٍ ومصروفٍ ولا يفتح فاتورة بيعٍ واحدة) كانت تُصفِّر مخرجاتها المُرحَّلة فعلاً في الكشف — مرآة سقوط المدخلات حرفياً. المدخلات = `SalesSettings.vat_input_account` ∪ `TaxRate.tax_account` (اتجاه `purchase`/`both`) **∪ سلسلة السقوط الحرفية** (الكود `1105` ثم `Asset` باسمٍ يحوي «ضريبة») لأن مسارات ترحيلٍ فعلية — `logistics/services.py` (`_resolve_vat_input_account`) و`accounting/views.py` (مسار استلام فاتورة شراء قديم) — تجد الحساب بالكود مباشرةً بلا قراءة `SalesSettings`/`TaxRate` إطلاقاً؛ اشتقاقٌ وحده كان يُصفِّر ضريبة مدخلاتٍ مُرحَّلة فعلاً لشركةٍ لم تُعيَّن فيها `SalesSettings.vat_input_account` (الحال الافتراضي) فيُبالَغ في «الصافي المستحق». **لا أثر رجعي**: كشفٌ محفوظ (مسودة أو نهائي) لا تُعاد كتابة أرقامه أبداً؛ `sales.services.vat_statement_diff_report` تقرأ الفرق بين المحفوظ والمحسوب الآن **بلا كتابة**. وفكّ ترحيل مستندٍ مؤرَّخ داخل فترة كشف `final` مرفوض من `unpost_document` (`assert_no_final_vat_statement`) — الإقرار المقدَّم يُصحَّح بإقرار معدَّل لا بتعديل صامت.

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
| `accounting/tests/test_cheque_guards.py` | حارس حذف الشيك، وقفل الكتابة الخام بعد الترحيل، ومخرج ارتداد الورقة المظهَّرة، ومنع صرف مسودة داخل مستند، وحراسة تاريخ الحركة |
| `accounting/tests/test_cheque_deposit_batch.py` · `test_cheque_deposit_bank.py` | ذرّية الإيداع الجماعي وقسيمته، وإلزام بنك الإيداع مع بقاء القيد 1107 ÷ 1109 |
| `accounting/tests/test_cheque_source_document.py` · `test_cheque_list_filters.py` · `test_cheque_voucher_autopost.py` | المستند المصدر وصمت الحركات قبل ترحيله، والفلاتر والبحث والترقيم بعزل الشركة، وترحيل سندٍ فيه شيك على شركة تنقصها حسابات الشيكات |
| `accounting/tests/test_journal_tenant_scoping.py` | رفض شريك/مركز تكلفة من شركة أخرى في `validate_journal_entry` |
| `accounting/tests/test_accounting_permissions.py` | إنفاذ مفاتيح `accounting.*` على القيد والشجرة والفترات |
| `accounting/tests/test_partner_statement.py` | مطابقة الرصيد الجاري في كشف الحساب مع `partner_posted_balance` |
| `sales/tests/test_invoice_context_tabs.py` | **المرساة** (`anchor_*`): نافذةٌ تتمركز على المستند فيبقى ظاهراً ولو تلته عشراتُ الحركات، و«قبل/بعد» يطابقان سطرَه في الكشف الكامل، وبلا تمريرها الحمولة كما كانت حرفياً (بلا `anchor` ولا `is_anchor`) |
| `accounting/tests/test_audit_log_isolation.py` | سطر التدقيق لا يُسقط عملية المستدعي |
| `accounting/tests/test_fx_fifo.py` | طبقات FIFO لصندوق العملة الأجنبية |
| `accounting/tests/test_cash_box_treasury.py` | الخزينة خدميّاً: ذرّية الإنشاء (فشلٌ بعد الحساب ⇒ لا حساب يتيم)، تزامن التسمية، وحدانية الافتراضي، **سلّم الحلّ كاملاً** (ومنه أن شركةً بصناديق لا تسقط على «1101»)، الرصيد الجاري، التحويل وطبقته FIFO، وفرق الجرد بطرفيه |
| `accounting/tests/test_cash_box_api.py` | عقد الـAPI: الإنشاء بنداء واحد، PATCH يزامن الشجرة، `my-default` ذهاباً وإياباً، الكشف، رفض السحب فوق الرصيد، عزل الشركات، وإنفاذ مفاتيح `finance.cashbox.*` |
| `logistics/tests/test_attach_payment_box_selection.py` | **الحارس**: الصندوق المختار في لوحة الدفع هو المُدائَن ولو حمل الرأس غيره؛ والرأس يبقى مصدراً بلا اختيار؛ والسقوط على صندوقٍ حقيقي لا «1101» |
| `accounting/tests/test_journal_pagination.py` · `test_journal_reference_perf.py` · `test_account_list_perf.py` | عقد الترقيم وغياب N+1 |
| `accounting/tests/test_fiscal_period_lock.py` | قفل الشهر المالي من كل مسار: الترحيل وإلغاؤه والتداخل و`close/`+`reopen/`، وCRUD الفترة (صلاحية، مُقفَلة غير قابلة للتعديل أو الحذف، سجل تدقيق) |
| `accounting/tests/test_journal_filters.py` | تصفية الدفتر بالحساب (بلا تكرار عبر الصفحات) وبالمستخدم، وختم `created_by` من مسارَي الإنشاء، ودورة قيد التسوية |
| `accounting/tests/test_opening_balance.py` | القيد الافتتاحي الموحّد: تاريخه وتوازنه وسطر `3300`، ومطابقة حسابات المخزون في الأستاذ لإجمالي تقرير «تقييم المخزون» بالرقم، ومنع القيد الثاني قبل العكس، والعكس وحارس الاعتمادية، والحسابات الممنوعة، والفترة الغائبة/المغلقة بلا حالة جزئية، وعزل الشركات |
| `accounting/tests/test_expense_voucher_api.py` | سند المصروف (issue #56): كهرباء نقداً بلا مورّد، الحساب بالاسم تحت «52»، الشيك على «2111»، «على الحساب» على «2101» أو حساب المستفيد، الضريبة على «1105»، **مرتجعٌ (issue #80) يقلب مدين↔دائن بمبلغ موجب**، نوع غير صالح مرفوض، التراجع عن الترحيل، شركةٌ قائمة بلا دفتر `expense_voucher` مسبَق، عزل الشركات، وصلاحيتا `finance.expense.create`/`.unpost` |
| `accounting/tests/test_revenue_voucher_api.py` | سند الإيراد (issue #80، مرآة `test_expense_voucher_api.py`): عمولة نقداً بلا دافع، الحساب بالاسم تحت «42»، الشيك على «1107»، «على الحساب» على «1103» أو يَدين حساب الدافع، الضريبة على «2104»، مرتجعٌ يقلب الاتجاه، نوع غير صالح مرفوض، PATCH/DELETE مرفوضان، التراجع عن الترحيل، شركةٌ قائمة بلا دفتر `revenue_voucher` مسبَق، عزل الشركات، وصلاحيتا `finance.revenue.create`/`.unpost` |
| `accounting/tests/test_vat_single_source.py` | issue #79: `build_vat_statement`/`VatReportView`/`client_financial_summary` يعطون الرقم نفسه من ثلاثة مصادر (فاتورة بيع · سند مصروف · استلام فاتورة شراء)، فكّ الترحيل يُرفض داخل فترة كشف `final` ويُقبل خارجها، الكشف النهائي لا تُعاد كتابة أرقامه، وتقرير الفرق يقرأ بلا كتابة. **issue #80**: سند الإيراد يظهر في الكشف حتى بلا `TaxRate` إطلاقاً (سقوط الكود «2104» — الاختبار الحاسم لحال «دفتر العميل»)، ويكتب على حساب `TaxRate` مخرجاتٍ غير معياري لا على «2104» وحده حين توجد نسبة |
