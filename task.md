# task.md — KTRA ERP Remediation Plan

> خطة تنفيذية مقسّمة 4 مراحل. كل مهمة مستقلة بذاتها (file:line + المشكلة + الإصلاح + التحقق) ليتمكن نموذج أرخص من تنفيذها.
> القاعدة العامة قبل أي مهمة: اقرأ الملف الفعلي تحت `C:\Users\asus\Desktop\ktra\` (ليس worktree). تحقّق أن الخطأ ما زال قائماً قبل الإصلاح. شغّل `python manage.py check` بعد كل مهمة backend.
> Status legend: `[ ]` pending · `[~]` in-progress · `[x]` done.
> Audited 2026-05-17. Sources: 3 independent code-audit passes.

---

## المرحلة 0 — تمكين البيئة (prerequisite, ليست خطأ)

- [ ] **P0-1** تأكد من وجود Tenant. شغّل: `python manage.py shell -c "from tenants.models import Tenant; print(list(Tenant.objects.values('TenantID','CompanyName')))"`. إن كانت فارغة أو لا يوجد `TenantID=1` → أنشئ شركة عبر admin أو seed، أو اضبط `localStorage.tenantId`/`VITE_TENANT_ID` في الواجهة على معرّف موجود. (هذا هو السبب البيئي الفعلي لخطأ 500.)
- [ ] **P0-2** راجع حالة الهجرات: `python manage.py makemigrations --check --dry-run` ثم `python manage.py migrate`. وثّق أي عدم تطابق schema (موجود سكربتات surgery يدوية في الجذر).
- [ ] **P0-3** أضف `sales/` وكل migrations غير المتعقّبة إلى git (commit) لإيقاف انجراف الـ schema. انقل `frontend/` (تطبيق جيتك Next.js غير المرتبط) خارج المستودع أو وثّقه كـ orphan.

---

## المرحلة 1 — أخطاء كارثية (Catastrophic: مالية خاطئة / فساد بيانات / تعطّل)

### محاسبة (Accounting)

- [x] **C1-01 (مُنجز جزئياً — تم تطبيق الحارس)** 500 على `POST /api/sales/invoices/`. `sales/views.py perform_create` كان يمرّر `tenant=None` فيُفكَّك `None.TenantID` في `sales/serializers.py:170`. **تم:** إضافة حارس يرجع 400 برسالة واضحة. **متبقٍّ للتحقق:** أعد إنشاء فاتورة وتأكد أن الرسالة واضحة بدل 500، ثم نفّذ P0-1.
- [ ] **C1-02** `accounting/services.py:190-261` + `accounting/views.py:301-343`: `validate_journal_entry` يتحقق من توازن مدين/دائن على **payload الطلب** لا على الأسطر المحفوظة (السيريالايزر يحفظ أولاً). إصلاح: تحقّق من الأسطر المبنية **قبل** `serializer.save()`، أو أعد استعلام `header.lines.all()` بعد الحفظ وتحقّق داخل `transaction.atomic()`. تحقّق: أنشئ قيداً غير متوازن عبر API → يجب أن يُرفض ولا يُحفظ.
- [ ] **C1-03** `accounting/services.py:288-316` `post_journal_entry`: لا يعيد التحقق من `debit==credit` عند الترحيل ولا `select_for_update` على الـ header → ترحيل قيد غير متوازن + سباق ترحيل مزدوج. إصلاح: لُف بـ `transaction.atomic()` + `JournalHeader.objects.select_for_update().get(pk=...)` + إعادة حساب مجموع `base_debit` vs `base_credit` على الأسطر الفعلية قبل الترحيل. تحقّق: محاولتا ترحيل متزامنتان تنتجان قيداً واحداً فقط.
- [ ] **C1-04** `accounting/views.py:198-262` `reverse_entry`: لا فحص idempotency → عكس نفس القيد عدة مرات يُنشئ قيوداً عكسية مكررة تُفسد الأستاذ. إصلاح: قبل الإنشاء تحقّق `JournalHeader.objects.filter(reference_type='JOURNAL_REVERSAL', reference_id=orig.id).exists()` وارفض؛ علّم الأصل كـ معكوس. تحقّق: استدعِ /reverse مرتين → الثانية تُرفض.
- [ ] **C1-05** `accounting/models.py:99-119` `JournalLine.save`: استدعاء `JournalLine.journal.is_cached(self)` خاطئ (FK descriptor لا يملك `is_cached`) → استثناء يُبتلع بـ `except Exception` فيُجبر `rate=Decimal('1')` → **كل سطر بعملة أجنبية يُخزَّن بأساس = المبلغ الأصلي** فتُصبح كل تقارير العملة الأساسية خاطئة. إصلاح: استخدم `self._meta.get_field('journal').is_cached(self)`؛ احذف الـ except العريض؛ إن فشل جلب السعر ارفع استثناء بدل الافتراضي 1. تحقّق: قيد بعملة ≠ الأساسية → `base_debit/base_credit` = المبلغ × السعر الصحيح.
- [ ] **C1-06** `accounting/serializers.py:307-343` `update`: تعديل أسطر قيد مرحّل ممكن عبر السيريالايزر ويستمر غير متوازن (نفس خلل C1-02). إصلاح: تحقّق من `instance.lines.all()` المحفوظة بعد الحفظ وداخل atomic؛ امنع تعديل المرحّل على مستوى الموديل لا فقط الـ view.
- [ ] **C1-07** `accounting/views.py:839-942` (`deposit_journal`) و`945-1124` (`PurchaseReceiptViewSet`): إنشاء قيود `is_posted=True` مباشرة دون `validate_fiscal_period` → ترحيل في فترة مالية مغلقة. إصلاح: مرّر كل ترحيل عبر دالة `post_journal()` مركزية تفرض: الفترة مفتوحة + متوازن + نفس tenant + idempotent. تحقّق: أغلق فترة ثم حاول إيداع بتاريخها → يُرفض.
- [ ] **C1-08** `accounting/models.py:73` `JournalLine.account` = `on_delete=CASCADE` بلا حارس → حذف حساب يحذف أسطر قيوده ويُفسد قيوداً مرحّلة تاريخياً (فقدان بيانات دائم). إصلاح: غيّر إلى `on_delete=PROTECT` + امنع حذف حساب له أسطر في `AccountViewSet`. تحقّق: حذف حساب له أسطر يُرفض. (migration مطلوبة.)
- [ ] **C1-09** `accounting/views.py:122-156` `JournalViewSet.get_queryset` بلا فلتر tenant إطلاقاً؛ و`AccountViewSet.queryset` (`:51`) و GL opening (`:392-403`) كذلك → تسريب/تعديل عبر الشركات بمعرّف PK. إصلاح: `.filter(tenant=get_tenant(self.request))` على كل queryset؛ أنشئ `TenantQuerySetMixin` مشترك. تحقّق: طلب بـ X-Tenant-Id مختلف لا يصل لقيد شركة أخرى.

### لوجستيات + مخزون (Logistics / Inventory)

- [ ] **C1-10** `logistics/landed_cost.py:478-481` `compute_deal_invoice_lines`: `merch_pool` يُعاد قياسه بـ `wsum/deal_tot_usd` فإذا تضمّن `deal.total_amount` ضريبة/شحن/خصم تُبخَّس قيمة البضاعة و**الباقي لا يُوزَّع على أي صنف** → مخزون مُقيَّم بأقل والفرق يضيع. إصلاح: وزّع كامل `deal_val_ils` على الأسطر بالوزن (احذف إعادة القياس) ووازِن الكسور (penny-balance) كما في `distribute_by_weights`. تحقّق: `sum(landed_line_total_ils) == deal_val_ils + freight + clearance`.
- [ ] **C1-11** `logistics/views.py:1681-1684` vs `inventory/services.py:178-186`: قيد GL يقيّد `merchandise_net` بينما WAC يُبنى من `landed_unit_price_ils` (قاعدتان مختلفتان) → رصيد مخزون GL ≠ الأستاذ المساعد دائماً. إصلاح: اشتقّ مدين GL وWAC من نفس الإجمالي (`sum(landed_line_total_ils)`). تحقّق: رصيد حساب المخزون = Σ(qty×WAC).
- [ ] **C1-12** `logistics/models.py:287-290`: `unique_together(shipment, deal)` يمنع تكرار الصفقة على شحنة واحدة فقط لا على عدة شحنات → نفس البضاعة تُستلَم وتُفوتر مرتين. إصلاح: امنع أكثر من شحنة فعّالة لكل صفقة (تحقّق في `add_deal` `views.py:656-671` + قيد DB جزئي على `deal`). تحقّق: إضافة صفقة لشحنة ثانية تُرفض.
- [ ] **C1-13** `logistics/views.py:968-1034` `post_to_accounting`: ينشئ قيد شحن من مبلغ في body بلا `is_posted`/idempotency → استدعاء N مرات = N قيود التزام مكررة. إصلاح: احرس بعلَم `is_posted` أو وجود journal بـ `reference_id`؛ اشتقّ المبلغ من الموديل لا من body. تحقّق: استدعاء مزدوج ينتج قيداً واحداً.
- [ ] **C1-14** `logistics/views.py:1815-1834` (PurchaseInvoice) و`1862-2070` (LocalShipment) `unpost`: `JournalLine...delete(); j.delete()` يحذف قيوداً مرحّلة (تدمير سجل تدقيق + إعادة كتابة تاريخ فترة مغلقة). إصلاح: استخدم نمط القيد العكسي (مثل `views.py:512`)؛ لا تحذف GL مرحّلاً أبداً. تحقّق: unpost ينشئ قيداً عكسياً ويُبقي الأصل.
- [ ] **C1-15** `logistics/signals.py:244-261` `auto_receive_stock_on_shipment_cleared`: idempotency على `(SHIPMENT, shipment.pk, product)` فقط → صنف مشترك بين صفقتين: استلام الأولى يمنع الثانية (نقص مخزون)؛ والاستثناءات تُبتلع وتُترك الحالة نصف مُستلمة. إصلاح: مفتاح idempotency يشمل deal/line؛ ارفع الاستثناء أو استخدم outbox. تحقّق: شحنة بصنف مكرر عبر صفقتين تستلم الكمية الكاملة.

### مبيعات + مخزون (Sales / Inventory)

- [ ] **C1-16** `inventory/services.py:52-112`: `RETURN_IN` ضمن `INBOUND_TYPES` ويُعامَل كشراء جديد بـ `unit_cost=0` الافتراضي → **تخفيف WAC نحو الصفر** فتُبخَّس قيمة المخزون وCOGS المستقبلي. إصلاح: لمرتجع البيع استرجِع بتكلفة البيع الأصلية (`avg_cost_before`) أو كإضافة كمية محايدة التكلفة بالـ avg الحالي. تحقّق: مرتجع بيع لا يغيّر avg_cost.
- [ ] **C1-17** `sales/services.py:553-554, 595-617`: لا حارس idempotency على حركة `SALE` ولا على قيد `SALES_DELIVERY_COGS` → فاتورة `stock_on_post=False` بأمرَي إخراج، أو تبديل العلَم، يُكرّر خصم المخزون وقيد COGS. إصلاح: احرس خصم المخزون/COGS بفحص وجود `StockMovement(reference_type='SALE', reference_id=invoice.id)` وقيد COGS قائم. تحقّق: تسليمان لنفس الفاتورة لا يكرران الخصم.
- [ ] **C1-18** `sales/services.py:799-802` `post_customer_payment`: قراءة/كتابة `inv.amount_paid` بلا `select_for_update` على الفاتورة → سباق lost-update يسمح بدفع زائد. إصلاح: `SalesInvoice.objects.select_for_update().get(pk=...)` داخل atomic قبل قراءة/كتابة `amount_paid`. تحقّق: دفعتان متزامنتان لا تتجاوزان المتبقي.

---

## المرحلة 2 — أخطاء متوسطة (Medium)

- [ ] **M2-01** `accounting/views.py:367-384` `get_all_child_accounts`: مطابقة `code__startswith` عامة بلا tenant وبلا cycle-guard → تسريب أستاذ عبر الشركات + recursion لا نهائية على parent self-loop. إصلاح: فلتر `tenant`, visited-set, فاصل في مطابقة الكود.
- [ ] **M2-02** `accounting/services.py:126-166` `validate_fiscal_period`: `if tenant_id in (0,None): return` + تاريخ غير صالح → تجاوز كامل لقفل الفترة. إصلاح: لا تتجاوز بصمت؛ اطلب tenant حقيقي وتاريخاً صالحاً أو ارفع.
- [ ] **M2-03** `accounting/services.py:18-72` + `views.py:1167-1172`: `ExchangeRateViewSet.get_rate` يفلتر بالعملة فقط لا tenant → سعر صرف شركة أخرى. إصلاح: أضف فلتر tenant.
- [ ] **M2-04** `accounting/views.py:1212-1227`: إغلاق الفترة لا يتحقق أن كل قيودها مرحّلة/متوازنة، وإعادة الفتح بلا تدقيق/صلاحية. إصلاح: قيّد + audit-log لإغلاق/فتح الفترة؛ حذّر من قيود غير مرحّلة.
- [ ] **M2-05** `logistics/views.py:1169-1211` `pay_from_cashbox`: فحص الميزانية يشمل دفعات غير مرحّلة، والقيد يبقى `is_posted=False` للأبد. إصلاح: احسب الميزانية على المرحّل فقط؛ أضف مسار ترحيل. + عملة: `landed_cost.py:298-301` يحوّل فقط إذا `Code=='USD'` وإلا يعامل أي عملة كـ ILS 1:1 — عمّم التحويل.
- [ ] **M2-06** `logistics/payment_posting_cap.py:21-44` + `serializers.py:74-109`: سقف الدفع = `deal.total_amount` المُعاد حسابه؛ تعديل الأصناف يخفض السقف تحت المدفوع فعلاً ويرفض دفعة صحيحة؛ وفحص التجاوز يتم بـ **float**. إصلاح: ثبّت السقف على المدفوع المرحّل؛ حوّل الفحص إلى Decimal.
- [ ] **M2-07** `logistics/views.py:1363,1425,1881`: `PurchaseInvoiceViewSet` ModelViewSet خام، فلتر tenant في get_queryset فقط → `post_to_accounting` عبر detail غير مفلتر بـ tenant. + حفظ `tenant=None`/`default=1` تسريب. إصلاح: استخدم BaseTenantViewSet موحّد؛ tenant مطلوب لا default=1.
- [ ] **M2-08** `logistics/models.py:257-267,564-574` + `views.py:1408-1423`: ترقيم `SH-{max(id)+1}` بلا lock وبلا tenant → تصادم/تسريب أرقام. إصلاح: ترقيم ذرّي per-tenant (select_for_update أو sequence).
- [ ] **M2-09** `logistics/landed_cost.py:925-930` + `views.py:1488`: `allow_unpaid_freight` bool من client بلا صلاحية يتجاوز بوابة "الشحن مدفوع بالكامل" ويلفّق landed cost. إصلاح: صلاحية على هذا العلَم.
- [ ] **M2-10** `sales/services.py:178-195` vs `662-669`: محلّلا حساب الذمم متباعدان (الدفع لا يملك fallback لإعدادات المبيعات) → فاتورة مرحّلة بذمم افتراضية لا يمكن ترحيل دفعتها. إصلاح: وحّدهما على محلّل واحد يشمل fallback الإعدادات.
- [ ] **M2-11** `core/tenant_utils.py:127-135`: وصول عبر الشركات يُسجَّل فقط، `raise PermissionDenied` معطّل (تعليق) → أي مستخدم يقرأ/يكتب بيانات شركة أخرى عبر X-Tenant-Id. إصلاح: فعّل الرفض في إعداد الإنتاج.
- [ ] **M2-12** `sales/views.py:71-76`: فشل الترحيل التلقائي يُبتلع بـ `except: pass` → "تم الإنشاء" دون قيد ودون سبب ظاهر. إصلاح: أرجع `auto_post_error` في استجابة الإنشاء.
- [ ] **M2-13** `frontend_v2/services/restApi.ts:101-156`: GET لا يقرأ أخطاء حقول DRF (يظهر `API error: 400` عام)؛ 500 بلا body. إصلاح: `flattenDrfError(data)` موحّد لكل الأفعال.
- [ ] **M2-14** `sales/serializers.py:21-50` vs `inventory/services.py:69-76`: تحقّق المخزون مكرر و TOCTOU؛ السيريالايزر يتجاهل `allow_negative_stock` فيرفض بيعاً تسمح به الخدمة. إصلاح: الخدمة هي المرجع الوحيد؛ اجعل السيريالايزر يحاكي `allow_negative_stock` ووثّقه كـ pre-check.

---

## المرحلة 3 — أخطاء صغيرة (Minor / robustness)

- [ ] **m3-01** `accounting/services.py:257`: تسامح توازن `> 0.01` يسمح بفرق قرش يتراكم. اجعله `!= 0` بعد quantize موحّد.
- [ ] **m3-02** `accounting/models.py:74-87`: لا قيد CHECK على `debit/credit >= 0` ولا منع سطر بمدين ودائن معاً. أضف قيوداً.
- [ ] **m3-03** `accounting/models.py:46-67`: لا قيد فريد `(tenant, reference_type, reference_id)` على JournalHeader → قيود مصدر مكررة. أضف unique constraint (يدعم C1-13/C1-17).
- [ ] **m3-04** بواقع `except Exception` العريضة تبتلع الأخطاء: `accounting/services.py:113,284`, `accounting/serializers.py:76,129,143,158,202`, `logistics/signals.py:142`, `logistics/views.py:332,602,886,1033,1292,1804,2048`, `sales/services.py:509-517`. ضيّق الالتقاط واسجّل/ارفع.
- [ ] **m3-05** `sales/services.py:323-336` `_partner_open_balance_excluding_invoice` يتجاهل العملة (يجمع عملات مختلطة مقابل حد ائتمان بعملة واحدة). افصل حسب العملة.
- [ ] **m3-06** `sales/services.py:887-900` `next_invoice_number` سباق بلا lock → IntegrityError غير ملتقَط. رقّم ذرّياً أو التقط التصادم وأعد المحاولة.
- [ ] **m3-07** `sales/serializers.py:177-186,223`: `row["product"]` نسخة موديل لا pk (استعلام زائد ومربك). نظّف للوضوح/الأداء.
- [ ] **m3-08** `logistics/landed_cost.py:471`: fallback `internal_usd * 3.6` سعر صرف مُصلَّب. اجلب السعر الفعلي أو ارفع.
- [ ] **m3-09** `logistics/signals.py:86` `automate_expense_accounting`: فرع `is_foreign` ميت (الفرعان متطابقان، rate=1 دائماً) → مصاريف لوجستية أجنبية بـ 1:1. صحّح التحويل.
- [ ] **m3-10** `logistics/views.py:1636`: اختيار حساب VAT بـ `account_type=='Asset'` واسم يحوي "ضريبة" — هشّ. اربط الحساب صراحةً في الإعدادات.
- [ ] **m3-11** `accounting/views.py:444,723`: وصول لخصائص بعد `.first()`/FK بلا حارس None. أضف حراس.

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
