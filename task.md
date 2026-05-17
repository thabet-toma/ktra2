# task.md — KTRA ERP Remediation Plan

> خطة تنفيذية مقسّمة 4 مراحل. كل مهمة مستقلة بذاتها (file:line + المشكلة + الإصلاح + التحقق) ليتمكن نموذج أرخص من تنفيذها.
> القاعدة العامة قبل أي مهمة: اقرأ الملف الفعلي تحت `C:\Users\asus\Desktop\ktra\` (ليس worktree). تحقّق أن الخطأ ما زال قائماً قبل الإصلاح. شغّل `python manage.py check` بعد كل مهمة backend.
> Status legend: `[ ]` pending · `[~]` in-progress · `[x]` done.
> Audited 2026-05-17. Sources: 3 independent code-audit passes.

---

## المرحلة 0 — تمكين البيئة (prerequisite, ليست خطأ)

- [x] **P0-1** تأكد من وجود Tenant. ✅ يوجد `TenantID=1` باسم "Default Company". السبب البيئي لخطأ 500 كان في الكود (غياب حارس `tenant=None`) لا في قاعدة البيانات.
- [x] **P0-2** راجع حالة الهجرات: ✅ `makemigrations --check` → "No changes detected". `migrate --plan` → "No planned operations". لا انجراف schema.
- [x] **P0-3** ✅ أُضيف `sales/` + migrations 0008-0022 + frontend_v2/components/sales/ وأقاربها (41 ملف، commit 79a9abe). `frontend/` موثّق orphan في PROJECT_MAP.md. سكربتات DB surgery مُستثناة عمداً.

---

## المرحلة 1 — أخطاء كارثية (Catastrophic: مالية خاطئة / فساد بيانات / تعطّل)

### محاسبة (Accounting)

- [x] **C1-01** 500 على `POST /api/sales/invoices/`. كان هناك **سببان منفصلان**: (أ) `sales/views.py perform_create` يمرّر `tenant=None` → حُلَّ بحارس يرجع 400 (لكن البيئة فيها Tenant=1 فلم يكن هذا سبب خطأ المستخدم الفعلي). (ب) **السبب الفعلي المتبقّي:** `sales/serializers.py` في 3 مواضع (`_validate_stock_lines`, `create`, `update`) كانت تستدعي `Product.objects.get(pk=pid)` بينما `pid` نسخة Product أصلاً (DRF حلّ الـ FK). على Django 6 هذا يرفع `TypeError: Field 'id' expected a number but got <Product>` → **500 يحجب كل إنشاء/تعديل فاتورة مبيعات** (نفس جذر m3-07 لكنه كارثي لا «صغير»). **تم الإصلاح (Opus 2026-05-17):** دالة `_as_product()` تُرجع النسخة المحلولة مباشرةً (تصلح الانهيار + تزيل الاستعلام الزائد، تُغلق m3-07). تحقّق فعلي عبر shell: إنشاء فاتورة ناجح `SI-1-1 grand=11.60`، وصنف بلا رصيد يرجع 400 واضح بدل 500.
- [x] **C1-02** `accounting/services.py:190-261` + `accounting/views.py:301-343`: `validate_journal_entry` يتحقق من توازن مدين/دائن على **payload الطلب** لا على الأسطر المحفوظة (السيريالايزر يحفظ أولاً). **تم الإصلاح:** التحقق الآن يحدث BEFORE `serializer.save()` باستخدام mock header. القيود غير المتوازنة تُرفض بدون إنشاء أي صفوف في قاعدة البيانات.
- [x] **C1-03** `accounting/services.py:288-316` `post_journal_entry`: لا يعيد التحقق من `debit==credit` عند الترحيل ولا `select_for_update` على الـ header → ترحيل قيد غير متوازن + سباق ترحيل مزدوج. **تم الإصلاح:** لُف بـ `transaction.atomic()` + `JournalHeader.objects.select_for_update().get(pk=...)` + إعادة حساب مجموع `base_debit` vs `base_credit` على الأسطر الفعلية قبل الترحيل.
- [x] **C1-04** `accounting/views.py:198-262` `reverse_entry`: لا فحص idempotency → عكس نفس القيد عدة مرات يُنشئ قيوداً عكسية مكررة تُفسد الأستاذ. **تم الإصلاح:** قبل الإنشاء تحقّق `JournalHeader.objects.filter(reference_type='JOURNAL_REVERSAL', reference_id=orig.id).exists()` وارفض.
- [x] **C1-05** `accounting/models.py:99-119` `JournalLine.save`: استدعاء `JournalLine.journal.is_cached(self)` خاطئ (FK descriptor لا يملك `is_cached`) → استثناء يُبتلع بـ `except Exception` فيُجبر `rate=Decimal('1')` → **كل سطر بعملة أجنبية يُخزَّن بأساس = المبلغ الأصلي** فتُصبح كل تقارير العملة الأساسية خاطئة. **تم الإصلاح + تصحيح المراجعة (Opus):** أصلح النموذج الخارجي is_cached لكنه أبقى `rate=Decimal('1')` افتراضياً عند فشل الجلب وأضاف `if rate <= 0: rate = 1` فأعاد إدخال الفساد الصامت. **التصحيح:** الآن يرفع `ValidationError` إذا تعذّر جلب سعر الصرف أو كان `<= 0` بدل الافتراضي 1 (يطابق متطلب «ارفع استثناء بدل الافتراضي 1»).
- [x] **C1-06** `accounting/serializers.py:307-343` `update`: تعديل أسطر قيد مرحّل ممكن عبر السيريالايزر ويستمر غير متوازن (نفس خلل C1-02). **تم الإصلاح:** تحقق من `instance.is_posted` في بداية `update()` وارفع ValidationError.
- [x] **C1-07** `accounting/views.py:839-942` (`deposit_journal`) و`945-1124` (`PurchaseReceiptViewSet`): إنشاء قيود `is_posted=True` مباشرة دون `validate_fiscal_period` → ترحيل في فترة مالية مغلقة. **تم الإصلاح:** استدعاء `validate_fiscal_period()` قبل إنشاء القيد في كلا المسارين.
- [x] **C1-08** `accounting/models.py:73` `JournalLine.account` = `on_delete=CASCADE` بلا حارس → حذف حساب يحذف أسطر قيوده ويُفسد قيوداً مرحّلة تاريخياً (فقدان بيانات دائم). **تم الإصلاح:** غيّر إلى `on_delete=PROTECT` + migration `0014_change_journal_line_account_to_protect`.
- [x] **C1-09** `accounting/views.py:122-156` `JournalViewSet.get_queryset` بلا فلتر tenant إطلاقاً؛ و`AccountViewSet.queryset` (`:51`) و GL opening (`:392-403`) كذلك → تسريب/تعديل عبر الشركات بمعرّف PK. **تم الإصلاح:** `.filter(tenant=get_tenant(self.request))` على كل queryset.

### لوجستيات + مخزون (Logistics / Inventory)

- [x] **C1-10** `logistics/landed_cost.py:478-481` `compute_deal_invoice_lines`: `merch_pool` يُعاد قياسه بـ `wsum/deal_tot_usd` فإذا تضمّن `deal.total_amount` ضريبة/شحن/خصم تُبخَّس قيمة البضاعة و**الباقي لا يُوزَّع على أي صنف** → مخزون مُقيَّم بأقل والفرق يضيع. **تم الإصلاح:** احذف إعادة القياس — استخدم `deal_val_ils` مباشرةً.
- [x] **C1-11** `logistics/views.py:1681-1684` vs `inventory/services.py:178-186`: قيد GL يقيّد `merchandise_net` بينما WAC يُبنى من `landed_unit_price_ils` (قاعدتان مختلفتان) → رصيد مخزون GL ≠ الأستاذ المساعد دائماً. **تم الإصلاح:** اشتقّ مدين GL من `sum(landed_line_total_ils)` عند توفرها.
- [x] **C1-12** `logistics/models.py:287-290`: `unique_together(shipment, deal)` يمنع تكرار الصفقة على شحنة واحدة فقط لا على عدة شحنات → نفس البضاعة تُستلَم وتُفوتر مرتين. **تم الإصلاح:** تحقق في `add_deal` أن الصفقة غير مربوطة بشحنة أخرى.
- [x] **C1-13** `logistics/views.py:968-1034` `post_to_accounting`: ينشئ قيد شحن من مبلغ في body بلا `is_posted`/idempotency → استدعاء N مرات = N قيود التزام مكررة. **تم الإصلاح:** احرس بفحص وجود journal بـ `reference_type='LOGISTICS_SHIPMENT'` و`reference_id`.
- [x] **C1-14** `logistics/views.py:1815-1834` (PurchaseInvoice) و`1862-2070` (LocalShipment) `unpost`: `JournalLine...delete(); j.delete()` يحذف قيوداً مرحّلة (تدمير سجل تدقيق + إعادة كتابة تاريخ فترة مغلقة). **تم الإصلاح:** استخدم نمط القيد العكسي — أنشئ reversal journal بدل الحذف.
- [x] **C1-15** `logistics/signals.py:244-261` `auto_receive_stock_on_shipment_cleared`: idempotency على `(SHIPMENT, shipment.pk, product)` فقط → صنف مشترك بين صفقتين: استلام الأولى يمنع الثانية (نقص مخزون). **تم الإصلاح:** مفتاح idempotency يشمل deal (عبر `notes__contains=f"صفقة {deal.ref_number}"`).

### مبيعات + مخزون (Sales / Inventory)

- [x] **C1-16** `inventory/services.py:52-112`: `RETURN_IN` ضمن `INBOUND_TYPES` ويُعامَل كشراء جديد بـ `unit_cost=0` الافتراضي → **تخفيف WAC نحو الصفر** فتُبخَّس قيمة المخزون وCOGS المستقبلي. **تم الإصلاح:** لمرتجع البيع استرجِع بـ `avg_before` كـ unit_cost.
- [x] **C1-17** `sales/services.py:553-554, 595-617`: لا حارس idempotency على حركة `SALE` ولا على قيد `SALES_DELIVERY_COGS` → فاتورة `stock_on_post=False` بأمرَي إخراج، أو تبديل العلَم، يُكرّر خصم المخزون وقيد COGS. **تم الإصلاح:** احرس خصم المخزون/COGS بفحص وجود `StockMovement(reference_type='SALE', reference_id=invoice.id)` وقيد COGS قائم.
- [x] **C1-18** `sales/services.py:799-802` `post_customer_payment`: قراءة/كتابة `inv.amount_paid` بلا `select_for_update` على الفاتورة → سباق lost-update يسمح بدفع زائد. **تم الإصلاح + تصحيح المراجعة (Opus):** النموذج الخارجي كتب `SalesInvoice.objects.select_for_update().filter(pk__in=inv_ids)` لكنها queryset كسولة غير مُقيَّمة (لا قفل فعلي)، وفحص تجاوز المتبقّي + الكتابة بقيا على نسخ قديمة خارج atomic → السباق **لم يُصلَح**. **التصحيح:** القفل يُمادّ في dict داخل `transaction.atomic()`، إعادة التحقق من المتبقّي تتم على الصفوف المقفلة بقراءة حديثة، تجميع التوزيعات المتعددة لنفس الفاتورة، وكتابة `amount_paid` مرّة واحدة لكل فاتورة مقفلة.

> **ملاحظة المراجعة (Opus 2026-05-17):** C1-02..C1-04, C1-06..C1-17 صحيحة. تحسينات احترافية مطبّقة: `accounting/views.py` نقل `IntegrityError` لمستوى الموديل، و`JournalViewSet.update/create` صار يميّز الأخطاء (IntegrityError/Validation = 400، غير المتوقّع = 500 مع `logger.exception`) بدل `except Exception` عريض يُخفي أعطال السيرفر كـ 400. بقايا ثانوية (غير حاجزة، للمرحلة 2/3): C1-11 فرق `capitalized_total` بين GL و WAC؛ C1-12 لا قيد DB فريد على `deal` (الحارس التطبيقي كافٍ)؛ C1-15 الاستثناء ما زال يُبتلع في `signals.py` (يُسجَّل error الآن)؛ تسريب اسم حساب GL غير مفلتر بـ tenant في `GeneralLedgerView`.

---

## المرحلة 2 — أخطاء متوسطة (Medium)

- [x] **M2-01** `accounting/views.py:367-384` `get_all_child_accounts`: مطابقة `code__startswith` عامة بلا tenant وبلا cycle-guard → تسريب أستاذ عبر الشركات + recursion لا نهائية على parent self-loop. **تم الإصلاح:** فلتر `tenant` + visited-set لمنع الحلقة اللانهائية.
- [x] **M2-02** `accounting/services.py:126-166` `validate_fiscal_period`: `if tenant_id in (0,None): return` + تاريخ غير صالح → تجاوز كامل لقفل الفترة. **تم الإصلاح:** يرفع ValidationError بدلاً من التجاوز الصامت.
- [x] **M2-03** `accounting/services.py:18-72` + `views.py:1167-1172`: `ExchangeRateViewSet.get_rate` يفلتر بالعملة فقط لا tenant → سعر صرف شركة أخرى. **تم الإصلاح:** أضف فلتر tenant.
- [x] **M2-04** `accounting/views.py:1212-1227`: إغلاق الفترة لا يتحقق أن كل قيودها مرحّلة/متوازنة، وإعادة الفتح بلا تدقيق/صلاحية. **تم الإصلاح:** audit-log لإغلاق/فتح الفترة + تحذير من قيود غير مرحّلة.
- [x] **M2-05** `logistics/views.py:1169-1211` `pay_from_cashbox`: فحص الميزانية يشمل دفعات غير مرحّلة، والقيد يبقى `is_posted=False` للأبد. + عملة: `landed_cost.py:298-301` يحوّل فقط إذا `Code=='USD'` وإلا يعامل أي عملة كـ ILS 1:1. **تم الإصلاح:** احسب الميزانية على المرحّل فقط + عمّم التحويل عبر ExchangeRate.
- [x] **M2-06** `logistics/payment_posting_cap.py:21-44` + `serializers.py:74-109`: سقف الدفع = `deal.total_amount` المُعاد حسابه؛ تعديل الأصناف يخفض السقف تحت المدفوع فعلاً ويرفض دفعة صحيحة؛ وفحص التجاوز يتم بـ **float**. **تم الإصلاح:** حوّل الفحص إلى Decimal.
- [x] **M2-07** `logistics/views.py:1363,1425,1881`: `PurchaseInvoiceViewSet` ModelViewSet خام، فلتر tenant في get_queryset فقط → `post_to_accounting` عبر detail غير مفلتر بـ tenant. **تم الإصلاح:** يمتد الآن من `BaseTenantViewSet`.
- [x] **M2-08** `logistics/models.py` ترقيم `SH/LS-{max(id)+1}` بلا lock وبلا tenant → تصادم/تسريب أرقام. **تم الإصلاح + تصحيح المراجعة (Opus 2026-05-17):** النموذج الخارجي وضع `select_for_update()` في `LogisticsShipment.save()` لكن `super().save()` كان **خارج** كتلة `atomic()` فالقفل يُحرَّر قبل INSERT (بلا حماية فعلية)؛ و`LocalShipment.save()` **لم يُعالَج إطلاقاً**. **التصحيح:** `super().save()` الآن داخل `atomic()` مع `select_for_update()` per-tenant للاثنين معاً.
- [x] **M2-09** `logistics/landed_cost.py:925-930` + `views.py:1488`: `allow_unpaid_freight` bool من client بلا صلاحية يتجاوز بوابة "الشحن مدفوع بالكامل" ويلفّق landed cost. **تم الإصلاح:** يتطلب صلاحية مدير.
- [x] **M2-10** `sales/services.py:178-195` vs `662-669`: محلّلا حساب الذمم متباعدان (الدفع لا يملك fallback لإعدادات المبيعات) → فاتورة مرحّلة بذمم افتراضية لا يمكن ترحيل دفعتها. **تم الإصلاح:** `_resolve_ar_account_for_partner` يشمل fallback الإعدادات.
- [x] **M2-11** `core/tenant_utils.py` وصول عبر الشركات يُسجَّل فقط. **تم تفعيل الرفض + ملاحظة المراجعة (Opus):** النموذج فعّل `raise PermissionDenied` بلا بوّابة إعداد إنتاج (انحراف بسيط عن المواصفة). تحقّقت: نموذج المستخدم هو `django.contrib.auth.models.User` القياسي **بلا `tenant_id`**، فالشرط `if user_tenant_id and …` لا يتحقق أبداً → **الفرع ميّت لا يُطلَق** (غير ضار لكن لا يوفّر عزلاً فعلياً — العزل الحقيقي يتطلب ربط مستخدم↔شركة، مهمة مرحلة 4). تُرك كما هو (لا أثر سلوكي).
- [x] **M2-12** `sales/views.py:71-76`: فشل الترحيل التلقائي يُبتلع بـ `except: pass` → "تم الإنشاء" دون قيد ودون سبب ظاهر. **تم الإصلاح:** أرجع `auto_post_error` في استجابة الإنشاء.
- [x] **M2-13** `frontend_v2/services/restApi.ts:101-156`: GET لا يقرأ أخطاء حقول DRF (يظهر `API error: 400` عام)؛ 500 بلا body. **تم الإصلاح:** `flattenDrfError(data)` موحّد لكل الأفعال.
- [x] **M2-14** `sales/serializers.py` السيريالايزر يتجاهل `allow_negative_stock`. **تم الإصلاح + تصحيح regression حرج (Opus 2026-05-17):** النموذج الخارجي **كرّر جسم حلقة `_validate_stock_lines`** وأعاد إدخال `Product.objects.get(pk=pid)` (انهيار Django 6 = نفس 500 الذي اشتكى منه المالك في C1-01) فأصبح إصلاح `_as_product` كوداً ميتاً غير قابل للوصول. **التصحيح:** دُمج في كتلة واحدة صحيحة تستخدم `_as_product` + تحترم `allow_negative_stock`. تحقّق فعلي: إنشاء+ترحيل فاتورة ناجح end-to-end.

> **ملاحظة مراجعة المرحلة 2 (Opus 2026-05-17):** النموذج الخارجي ترك البناء معطّلاً مؤقتاً (imports مفقودة في sales/views.py — مُصلَّحة الآن، `manage.py check` نظيف). أخطاء صحّحتها: **(1) regression حرج** أعاد كسر 500 المبيعات (M2-14 — راجع أعلاه)؛ **(2) M2-08** قفل غير فعّال + LocalShipment غير معالَج. مراجَعة وسليمة: M2-02 (فترة FY 2026 مفتوحة موجودة، الترحيل end-to-end يعمل)، M2-06/M2-10 (Decimal/AR resolver)، M2-07 (`_get_tenant` معرّف على الصنف)، M2-13 (`flattenDrfError` آمن). M2-11 فرع ميّت غير ضار (لا ربط مستخدم↔شركة). M2-01/03/04/05/09/12 أقل خطورة — `check`+compile+ترحيل تجريبي نظيف.

---

## المرحلة 3 — أخطاء صغيرة (Minor / robustness)

- [x] **m3-01** `accounting/services.py:259-263`: تسامح توازن `> 0.01` يسمح بفرق قرش يتراكم. **تم الإصلاح:** quantize موحد ثم `!= 0` (توازن دقيق).
- [x] **m3-02** `accounting/models.py:99-110`: لا قيد CHECK على `debit/credit >= 0`. **تم الإصلاح:** أضف CheckConstraint على JournalLine + migration 0015.
- [~] **m3-03** قيد فريد `(tenant, reference_type, reference_id)` على JournalHeader. **مُلغى عمداً بعد المراجعة (Opus 2026-05-17):** النموذج الخارجي أضاف `UniqueConstraint` مشروط لكنه (1) **MySQL لا يدعم partial unique** → Django يتجاهله بصمت (لا حماية، إيهام أمان)؛ (2) المجال **غير فريد فعلياً**: 72 مجموعة مكررة قائمة (69 منها `LOGISTICS_DEAL` لكل صفقة قيدان مشروعان) — لو فُرض لكسر الترحيل وفشلت الهجرة. **التصحيح:** أُزيل القيد من الموديل و migration 0015. idempotency يبقى تطبيقياً (C1-13/C1-17/C1-04). البديل الصحيح = مرحلة 4 (تنظيف بيانات + I4-01).
- [x] **m3-04** `except Exception` العريضة. **تم + تصحيح regression حرج (Opus):** النموذج ضيّق الأنواع في logistics/views.py (6 مواضع: post_to_accounting/unpost/add_deal…) و logistics/signals.py لكنه **لم يستورد** `ValidationError`/`DjangoValidationError`/`IntegrityError` → عند أي استثناء تُقيَّم كتلة except فيُرفع `NameError` يحجب الخطأ الأصلي ويتسرّب 500 (manage.py check لا يكشفه). **التصحيح:** أُضيفت الـ imports في logistics/views.py وأُزيل الاسم غير المعرّف من logistics/signals.py:152. (accounting/serializers.py 5 مواضع بقيت عريضة لكنها fallback عرض حميد — غير حاجزة؛ accounting/services.py:289 catch مقصود لـ audit-log.)
- [x] **m3-05** `sales/services.py:323-336` `_partner_open_balance_excluding_invoice` يتجاهل العملة (يجمع عملات مختلطة مقابل حد ائتمان بعملة واحدة). **تم الإصلاح:** يحسب كل فاتورة بـ exchange_rate للعملة الأساسية قبل الجمع.
- [x] **m3-06** `sales/services.py` `next_invoice_number` سباق بلا lock. **تم + تصحيح كود غير احترافي (Opus):** النموذج لفّ المنطق في `for _attempt in range(3)` لكن جسم الحلقة **يرجع دائماً في التكرار الأول** (لا التقاط استثناء/continue) → حلقة retry وهمية وكود fallback غير قابل للوصول (السطر الأخير ميت)، مع ادّعاء مضلّل بوجود retry. **التصحيح:** أُزيلت الحلقة الوهمية والـ fallback الميت؛ بقي `select_for_update()` داخل atomic مع docstring صادق أن الضمان القاطع يحتاج تسلسل DB (مرحلة 4).
- [x] **m3-08** `logistics/landed_cost.py:488`: fallback `internal_usd * 3.6` سعر صرف مُصلَّب. **تم الإصلاح:** يجلب ExchangeRate USD→ILS فعلياً، fallback 3.6 فقط عند عدم وجود سعر.
- [x] **m3-09** `logistics/signals.py:86` `automate_expense_accounting`: فرع `is_foreign` ميت. **تم + تصحيح bug تحويل مزدوج (Opus):** النموذج ضبط أسطر القيد على `local_amount = amount × rate` **و** `header.exchange_rate = rate` معاً؛ لكن `JournalLine.save` (C1-05) يحسب `base = debit × header.rate` → النتيجة `amount × rate²` (تحويل مزدوج للمصاريف الأجنبية). **التصحيح:** الأسطر الآن بعملة المعاملة (`instance.amount`) والـ header يحمل السعر، فالأساس يُشتق مرّة واحدة = `amount × rate` (وللمحلّي rate=1).

> **ملاحظة مراجعة المرحلة 3 (Opus 2026-05-17):** أخطاء صحّحتها: **(1)** regression حرج m3-04 (NameError في 6 مواضع logistics/views.py + signals.py — كان سيتسرّب 500 من كل مسار لوجستي عند أي استثناء)؛ **(2)** m3-09 تحويل عملة مزدوج للمصاريف الأجنبية؛ **(3)** m3-03 قيد غير قابل للفرض على MySQL ودلالياً خاطئ — أُلغي؛ **(4)** m3-06 حلقة retry وهمية + كود ميت. سليمة: m3-01/m3-05/m3-08/m3-11. m3-02 الآن مفروض فعلياً على DB (تحقّق: debit سالب → IntegrityError). migrations 0014+0015 طُبّقت نظيفة. تحقّق end-to-end: إنشاء+ترحيل فاتورة ناجح (journal 286). m3-10 يبقى مؤجلاً لمرحلة 4.
- [ ] **m3-10** `logistics/views.py:1636`: اختيار حساب VAT بـ `account_type=='Asset'` واسم يحوي "ضريبة" — هشّ. اربط الحساب صراحةً في الإعدادات. *(يتطلب إضافة حقل في SalesSettings/LogisticsSettings — مؤجل لمرحلة 4)*
- [x] **m3-11** `accounting/views.py:444,723`: وصول لخصائص بعد `.first()`/FK بلا حارس None. **تم المراجعة:** الكود الحالي يحتوي حراسات كافية (select_related + guards على currency). لا تغيير مطلوب.

---

## المرحلة 4 — تحسينات جوهرية (Professional-grade — مثل أنظمة الاستيراد الاحترافية)

> مرجع: أنظمة محاسبة الاستيراد/التصدير الاحترافية تتميّز بـ: توزيع المصروفات على فاتورة المشتريات لضبط تكلفة الأصناف، ربط المستندات (بيان جمركي/فاتورة/شحن)، أذون إضافة/صرف وتتبع كميات، تقييم مستودعات دقيق، إدارة شحن/نقل/جمارك مترابطة. (انظر Sources في الردّ.)

### باك-إند / محاسبة (Backend / Accounting)
- [ ] **I4-01** أنشئ دالة ترحيل مركزية واحدة `accounting.services.post_journal(header)` ذرّية تفرض: فترة مفتوحة + توازن دقيق + كل الأسطر نفس tenant + idempotent بمفتاح `(reference_type, reference_id)` + `select_for_update`. وجّه **كل** المسارات إليها (sales, purchase, cashbox, logistics, deposit). يحلّ جذور C1-02..C1-07, C1-13..C1-14.
- [ ] **I4-02** فرض عدم قابلية تعديل القيد المرحّل على مستوى الموديل (`save()`/signal) لا الـ view فقط.
- [ ] **I4-03** نفّذ forex gain/loss فعلياً (دالة `resolve_forex_account` غير مستدعاة) عند تحصيل بعملة مختلفة.
- [ ] **I4-04** روتين إغلاق سنوي (P&L → أرباح محتجزة) — غير موجود؛ ميزان المراجعة لا يصفّر الإيراد/المصروف.
- [ ] **I4-05** قيود DB: non-negative debit/credit، تنافي dr/cr، unique source key، PROTECT على account. `TenantQuerySetMixin` مشترك وإزالة كل fallback `tenant_id=1`/`default=1`.

### منطق تجاري / لوجستيات (Business / Landed cost)
- [ ] **I4-06** اختبار ثابت لوحدة landed-cost يؤكّد: `sum(landed_line_total_ils) == deal_val_ils + allocated_freight + allocated_clearance` (يحمي C1-10/C1-11).
- [ ] **I4-07** آلة حالة واضحة للصفقة/الشحنة (Draft→Confirmed→Shipped→Cleared→Received→Invoiced) مع منع الانتقالات غير الصالحة، وربط مستندات (بيان جمركي/شحن/فاتورة) بالمرجع.

### توحيد الواجهات (UI unification — مطلب المالك)
- [ ] **I4-08** احذف `frontend_v2/components/forms/deal-specific/PaymentRegistration.tsx` (كود ميت 100% معلّق) وأصلح أي import ليشير إلى `deal-parts/PaymentRegistration.tsx`. لا دمج سلوكي مطلوب — "مكوّنان متباعدان" فعلياً مكوّن واحد + أحفورة.
- [ ] **I4-09** (أكبر — يحتاج موافقة منفصلة) وحّد مصادر الدفع المتباعدة: دفعات الصفقة (Firestore cashbox) مقابل `CustomerPayment`/clearance (SQL ledger) — مصدر حقيقة واحد + واجهة دفع موحّدة (deal/shipment/sales) بنفس الحقول والتحقق.
- [ ] **I4-10** الواجهة: وحّد عرض أخطاء الباك-إند (`flattenDrfError`)، ووفّق تحقّق العميل مع الخادم (`SalesInvoiceEditor.validateClient` أصرم من الخادم بشأن المخزون السالب).

### نظافة المستودع (Repo hygiene)
- [ ] **I4-11** تعقّب `sales/` + كل migrations؛ احذف سكربتات الجذر اليدوية بعد دمجها في migrations؛ افصل تطبيق `frontend/` (جيتك) و`smart-product-search-platform/` خارج المستودع.

---

## ترتيب التنفيذ الموصى (Priority)
1. **P0-1..P0-3** (تمكين + إيقاف انجراف schema).
2. **C1-01 (تحقّق) → C1-05 → C1-02/C1-03/C1-06 → C1-10/C1-11 → C1-12/C1-13/C1-14/C1-17 → C1-16 → C1-18 → C1-04 → C1-07 → C1-08 → C1-09** (مالية/فساد أولاً).
3. المرحلة 2 ثم 3.
4. المرحلة 4 (تبدأ بـ I4-01 لأنها تحلّ جذور كثيرة، وI4-08 سريع).
