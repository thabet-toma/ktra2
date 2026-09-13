"""T-PLANLIMITS: حدود الخطة — الافتراضي، التجاوز، الحارس عند الإنشاء."""
from collections import Counter

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from core.models import TenantLimit
from core.plans import (
    LIMITS,
    bulk_usage,
    check_limit,
    current_usage,
    invalidate_limit_cache,
    limit_rows,
    limit_value,
    plan_default,
)
from inventory.models import Warehouse
from tenants.models import Tenant, UserCompanyMembership


class PlanLimitEngineTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.basic = Tenant.objects.create(
            CompanyName="شركة أساسية", SubscriptionPlan="Basic", Status="Active",
        )
        cls.enterprise = Tenant.objects.create(
            CompanyName="شركة مؤسسية", SubscriptionPlan="Enterprise", Status="Active",
        )

    def setUp(self):
        invalidate_limit_cache(self.basic.pk)
        invalidate_limit_cache(self.enterprise.pk)

    def test_plan_default_drives_the_effective_limit(self):
        self.assertEqual(
            limit_value(self.basic, "inventory.warehouses"),
            plan_default("Basic", "inventory.warehouses"),
        )
        self.assertIsNone(limit_value(self.enterprise, "inventory.warehouses"))

    def test_company_override_beats_plan_default_and_delete_restores_it(self):
        TenantLimit.objects.create(
            tenant=self.basic, limit_key="inventory.warehouses", max_value=4,
        )
        invalidate_limit_cache(self.basic.pk)
        self.assertEqual(limit_value(self.basic, "inventory.warehouses"), 4)

        TenantLimit.objects.filter(tenant=self.basic).delete()
        invalidate_limit_cache(self.basic.pk)
        self.assertEqual(
            limit_value(self.basic, "inventory.warehouses"),
            plan_default("Basic", "inventory.warehouses"),
        )

    def test_null_override_means_unlimited_not_zero(self):
        TenantLimit.objects.create(
            tenant=self.basic, limit_key="inventory.warehouses", max_value=None,
        )
        invalidate_limit_cache(self.basic.pk)
        self.assertIsNone(limit_value(self.basic, "inventory.warehouses"))
        self.assertIsNone(check_limit(self.basic, "inventory.warehouses"))

    def test_check_limit_blocks_only_when_the_next_one_exceeds(self):
        TenantLimit.objects.create(
            tenant=self.basic, limit_key="inventory.warehouses", max_value=2,
        )
        invalidate_limit_cache(self.basic.pk)
        Warehouse.objects.create(tenant=self.basic, name="مستودع 1")
        self.assertIsNone(check_limit(self.basic, "inventory.warehouses"))

        Warehouse.objects.create(tenant=self.basic, name="مستودع 2")
        message = check_limit(self.basic, "inventory.warehouses")
        self.assertIsNotNone(message)
        self.assertIn("المستودعات", message)

    def test_usage_counts_only_the_same_company(self):
        Warehouse.objects.create(tenant=self.basic, name="مستودع الشركة")
        Warehouse.objects.create(tenant=self.enterprise, name="مستودع شركة أخرى")
        self.assertEqual(current_usage(self.basic, "inventory.warehouses"), 1)

    def test_limit_rows_cover_every_declared_limit(self):
        rows = {row["key"] for row in limit_rows(self.basic)}
        self.assertEqual(rows, set(LIMITS))


class CompositeLimitsAreDerivedNotRecountedTest(APITestCase):
    """الحدُّ المركَّبُ يُعلِن مصادرَه، فيُشتقُّ منها ولا يُعيد عدَّها.

    قبلَ هذا كان لمعنى «إجمالي الفواتير = بيعٌ + شراء» **نسختان**: دالّةٌ تجمع
    العدَّ الفرديَّ وأخرى تجمع العدَّ المجمَّع. والثمنُ مقيسٌ لا نظريّ:
    `limit_rows` تنادي `current_usage` لكلّ حدٍّ، فيُعَدُّ جدولا الفواتير **مرّتين**
    — مرّةً لحدَّيهما ومرّةً لحدّ المجموع — أي استعلامان زائدان في كلّ فتحٍ
    لبطاقة «خطّتي» وكلّ قراءةٍ لصفوف لوحة المنصّة.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            CompanyName="شركة المركَّب", SubscriptionPlan="Basic", Status="Active",
        )
        cls.other = Tenant.objects.create(
            CompanyName="شركة أخرى", SubscriptionPlan="Basic", Status="Active",
        )

    def setUp(self):
        invalidate_limit_cache(self.tenant.pk)

    def test_every_declared_source_is_a_real_atomic_limit(self):
        """مفتاحٌ في `sums` لا يقابله حدٌّ = `KeyError` في وقت التشغيل لا هنا."""
        broken = []
        for key, spec in LIMITS.items():
            for source in spec.sums:
                if source not in LIMITS:
                    broken.append(f"{key} ← {source} (لا حدَّ بهذا المفتاح)")
                elif LIMITS[source].sums:
                    broken.append(f"{key} ← {source} (مركَّبٌ يجمع مركَّباً)")
        self.assertEqual(broken, [], f"مصادرُ حدٍّ مركَّبٍ غيرُ سليمة: {broken}")

    def test_the_composite_equals_the_sum_of_its_sources(self):
        """الطريقان — العدُّ المباشرُ والاشتقاقُ — على الرقم نفسِه لكلّ حدّ.

        وبصفوفٍ حقيقيّةٍ لا بقاعدةٍ فارغة: صفرٌ يساوي صفراً في كلّ حال، فتأكيدٌ
        على قاعدةٍ خالية لا يستطيع السقوطَ لأجلِ ما يسمّيه.
        """
        self._make_invoices(sales=3, purchases=2)
        for key, spec in LIMITS.items():
            if not spec.sums:
                continue
            with self.subTest(limit=key):
                parts = sum(current_usage(self.tenant, source) for source in spec.sums)
                self.assertEqual(
                    current_usage(self.tenant, key), parts,
                    f"«{spec.label}» لا يساوي مجموعَ {spec.sums}.",
                )
                rows = {row["key"]: row["usage"] for row in limit_rows(self.tenant)}
                self.assertEqual(rows[key], parts, "صفُّ اللوحة يخالف العدَّ المباشر.")

    def test_the_composite_counts_this_company_alone(self):
        """رقمٌ مطلق، لأنّ المساواةَ لا تكشف **تركيبةً خاطئة**.

        `test_the_composite_equals_the_sum_of_its_sources` يقارن طرفَين يقرآن
        `sums` نفسَها: فلو صارت `("sales.invoices", "sales.invoices")` لتضخّم
        الطرفان معاً وبقي أخضرَ. هنا العددُ مكتوبٌ — ثلاثُ مبيعاتٍ وشراءان — فمصدرٌ
        مكرَّرٌ أو مبدَّلٌ يسقط عند `6 != 5`.

        **وبالطريقين**: `current_usage` تعدّ بـ`spec.count` و`limit_rows` بـ
        `spec.bulk` — دالّتان مستقلّتان لكلّ حدّ، والثانيةُ هي التي تُغذّي صفوفَ
        اللوحة. وصفُّ شركةٍ أخرى معها يثبت أنّ الرقمَ **لكلّ شركةٍ رقمُها**: عزلُ
        المسار المجمَّع بنيويٌّ (`values("tenant_id").annotate`) فمخرجُه مفهرسٌ
        بالشركة، وهذا التأكيدُ يمسك مَن يستبدله بجمعٍ على الكلّ.
        """
        self._make_invoices(sales=3, purchases=2)
        self.assertEqual(current_usage(self.tenant, "documents.invoices"), 5)
        self.assertEqual(current_usage(self.other, "documents.invoices"), 1)
        mine = {row["key"]: row["usage"] for row in limit_rows(self.tenant)}
        theirs = {row["key"]: row["usage"] for row in limit_rows(self.other)}
        self.assertEqual(
            (mine["documents.invoices"], theirs["documents.invoices"]), (5, 1),
            "صفوفُ اللوحة تخلط فواتيرَ الشركتين.",
        )

    def test_a_shared_source_is_counted_once_per_read(self):
        """جدولٌ يطلبه حدّان يُستعلَم عنه مرّةً واحدةً في القراءة المجمَّعة."""
        self._make_invoices(sales=1, purchases=1)
        with CaptureQueriesContext(connection) as captured:
            bulk_usage(tenant_ids=[self.tenant.pk])
        seen = Counter(query["sql"] for query in captured.captured_queries)
        repeated = {sql[:90]: n for sql, n in seen.items() if n > 1}
        self.assertEqual(repeated, {}, f"استعلامٌ مكرَّرٌ حرفيّاً: {repeated}")

    def _make_invoices(self, *, sales: int, purchases: int) -> None:
        """صفوفٌ لهذه الشركة وصفٌّ لشركةٍ أخرى — كي يُقاس العزلُ مع المجموع."""
        from django.utils import timezone

        from accounting.models import Currency
        from logistics.models import PurchaseInvoice
        from partners.models import Partner
        from sales.models import SalesInvoice

        today = timezone.localdate()
        currency, _ = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True},
        )
        customer = Partner.objects.create(
            tenant=self.tenant, name="عميل المركَّب", partner_type="Customer",
        )
        supplier = Partner.objects.create(
            tenant=self.tenant, name="مورّد المركَّب", partner_type="Supplier",
        )
        for index in range(sales):
            SalesInvoice.objects.create(
                tenant=self.tenant, invoice_number=f"S{index}", customer=customer,
                currency=currency, invoice_date=today, grand_total=100,
            )
        for index in range(purchases):
            PurchaseInvoice.objects.create(
                tenant=self.tenant, invoice_number=f"P{index}", partner=supplier,
                currency=currency, invoice_date=today, grand_total=100,
            )
        SalesInvoice.objects.create(
            tenant=self.other, invoice_number="X1",
            customer=Partner.objects.create(
                tenant=self.other, name="عميل غريب", partner_type="Customer",
            ),
            currency=currency, invoice_date=today, grand_total=100,
        )


class PlanLimitGuardTest(APITestCase):
    """الحارس على نقاط الإنشاء الحقيقية عبر الـAPI."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            CompanyName="شركة الحدود", SubscriptionPlan="Basic", Status="Active",
        )
        cls.manager = User.objects.create_user(username="limit-manager", password="x")
        UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.tenant, role="manager",
        )

    def setUp(self):
        invalidate_limit_cache(self.tenant.pk)
        self.client.force_authenticate(user=self.manager)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def test_warehouse_creation_is_blocked_at_the_limit(self):
        TenantLimit.objects.create(
            tenant=self.tenant, limit_key="inventory.warehouses", max_value=1,
        )
        invalidate_limit_cache(self.tenant.pk)

        first = self.client.post(
            "/api/inventory/warehouses/", {"name": "الرئيسي"}, format="json",
        )
        self.assertEqual(first.status_code, 201, first.content)

        second = self.client.post(
            "/api/inventory/warehouses/", {"name": "الثاني"}, format="json",
        )
        self.assertEqual(second.status_code, 400, second.content)
        self.assertIn("plan_limit", second.data)
        self.assertEqual(Warehouse.objects.filter(tenant=self.tenant).count(), 1)

    def test_sales_invoice_creation_is_blocked_at_the_monthly_limit(self):
        """حدّ فواتير البيع الشهري — الطلب المُتخطّي لا يُحفظ أصلاً."""
        from inventory.models import Product
        from partners.models import Partner
        from sales.models import SalesInvoice
        from tenants.models import Currency

        currency = Currency.objects.create(
            Code="LIM", Name="عملة الحدود", IsBaseCurrency=False,
        )
        customer = Partner.objects.create(
            tenant=self.tenant, name="عميل الحدود", partner_type="Customer",
        )
        product = Product.objects.create(
            tenant=self.tenant, sku="LIMIT-1", name_ar="منتج الحدود",
            quantity_on_hand=10, avg_cost=1,
        )
        TenantLimit.objects.create(
            tenant=self.tenant, limit_key="sales.invoices", max_value=1,
        )
        invalidate_limit_cache(self.tenant.pk)
        body = {
            "customer": customer.id,
            "currency": currency.CurrencyID,
            "invoice_date": "2026-07-01",
            "auto_post": False,
            "lines": [{
                "product": product.id,
                "quantity": "1",
                "unit_price": "10",
                "line_discount": "0",
            }],
        }

        first = self.client.post("/api/sales/invoices/", body, format="json")
        self.assertEqual(first.status_code, 201, first.content)

        second = self.client.post("/api/sales/invoices/", body, format="json")
        self.assertEqual(second.status_code, 400, second.content)
        self.assertIn("plan_limit", second.data)
        self.assertEqual(SalesInvoice.objects.filter(tenant=self.tenant).count(), 1)

    def test_partner_creation_is_blocked_at_the_limit(self):
        TenantLimit.objects.create(
            tenant=self.tenant, limit_key="partners.records", max_value=0,
        )
        invalidate_limit_cache(self.tenant.pk)

        response = self.client.post(
            "/api/partners/",
            {"name": "عميل جديد", "partner_type": "Customer"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("plan_limit", response.data)


class PlatformLimitApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="limits-root", email="limits-root@example.com", password="x",
        )
        cls.member = User.objects.create_user(username="limits-member", password="x")
        cls.tenant = Tenant.objects.create(
            CompanyName="شركة اللوحة", SubscriptionPlan="Basic", Status="Active",
        )
        UserCompanyMembership.objects.create(
            user=cls.member, tenant=cls.tenant, role="manager",
        )

    def setUp(self):
        invalidate_limit_cache(self.tenant.pk)

    def url(self):
        return f"/api/platform/companies/{self.tenant.pk}/limits/"

    def test_company_manager_is_denied(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_super_admin_reads_defaults_with_usage(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["plan"], "Basic")
        rows = {row["key"]: row for row in response.data["results"]}
        self.assertEqual(set(rows), set(LIMITS))
        warehouses = rows["inventory.warehouses"]
        self.assertEqual(
            warehouses["plan_default"], plan_default("Basic", "inventory.warehouses"),
        )
        self.assertFalse(warehouses["has_override"])
        self.assertEqual(warehouses["usage"], 0)

    def test_super_admin_sets_then_resets_an_override(self):
        self.client.force_authenticate(self.superuser)

        setting = self.client.post(
            self.url(),
            {"limit_key": "company.members", "max_value": 25, "note": "اتفاق خاص"},
            format="json",
        )
        self.assertEqual(setting.status_code, 200, setting.content)
        self.assertEqual(limit_value(self.tenant, "company.members"), 25)

        reset = self.client.post(
            self.url(), {"limit_key": "company.members", "reset": True}, format="json",
        )
        self.assertEqual(reset.status_code, 200, reset.content)
        self.assertFalse(
            TenantLimit.objects.filter(
                tenant=self.tenant, limit_key="company.members",
            ).exists()
        )
        self.assertEqual(
            limit_value(self.tenant, "company.members"),
            plan_default("Basic", "company.members"),
        )

    def test_unknown_limit_key_is_rejected(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.post(
            self.url(), {"limit_key": "made.up", "max_value": 5}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)


class LimitMessagePointsAtADoorTheUserCanOpenTest(APITestCase):
    """رسالةُ بلوغ الحدّ كما يقرؤها **مستخدمُ الشركة** — لا موظّفُ المنصّة.

    الرسالةُ ليست سطرَ سجلّ: `enforce_limits` يرفعها في `plan_limit` فتظهر منذ
    211-P في حوارٍ كامل أمام من مُنع من الإنشاء. وهي آخرُ ما يقرؤه قبل أن
    يتوقّف، فكلُّ كلمةٍ فيها إمّا تدلّه على مخرجٍ أو تحبسه.

    ومقياسُ السوق واحد (Odoo · Zoho Books · QuickBooks · Xero): تُذكَر الحقيقةُ
    ثمّ **فعلٌ واحدٌ يملكه الزبونُ نفسُه** — ولا واحدٌ منها يحيل الزبونَ إلى
    لوحة إدارة المزوّد الداخليّة.
    """

    @classmethod
    def setUpTestData(cls):
        cls.basic = Tenant.objects.create(
            CompanyName="شركة أساسية", SubscriptionPlan="Basic", Status="Active",
        )
        cls.trial = Tenant.objects.create(
            CompanyName="شركة تجريبية", SubscriptionPlan="Trial", Status="Active",
        )

    def _message(self, tenant):
        from core.plans import limit_exceeded_message
        return limit_exceeded_message(tenant, "sales.invoices", 200)

    def test_it_does_not_send_the_customer_to_a_door_only_ktra_can_open(self):
        """«لوحة المنصة» شاشةُ كترا خلفَ `IsPlatformAdmin` — لا يفتحها زبونٌ أبداً.

        رسالةٌ تقول له «ارفع الحدّ من لوحة المنصة» تصف طريقاً غيرَ موجودٍ في
        حسابه: يبحث عنه فلا يجده، فيقرأ العجزَ عيباً في فهمه لا في الرسالة.
        """
        message = self._message(self.basic)
        self.assertNotIn(
            "لوحة المنصة", message,
            "الرسالةُ تحيل زبوناً إلى شاشةٍ لا يملك صلاحيّةَ فتحها.",
        )

    def test_it_names_the_plan_in_arabic_not_by_its_english_key(self):
        """`PLAN_LABELS` موجودةٌ منذ 211-M لهذا بالضبط.

        مفتاحُ الخطّة قيمةُ قاعدةِ بيانات (`Basic`)، وطباعتُه داخل نثرٍ عربيٍّ
        تُظهر داخلَ النظام لمن لا شأنَ له به — والاسمُ العربيُّ معروضٌ له في
        صفحة الأسعار وفي «خطّتي»، فيقرأ اسمين لخطّةٍ واحدة.
        """
        message = self._message(self.basic)
        self.assertIn("الأساسية", message)
        self.assertNotIn("Basic", message)

    def test_the_trial_company_gets_an_arabic_name_too(self):
        """التجريبيّةُ مخفيّةٌ عن العرض، لا عن الرسائل.

        هي **مستبعدةٌ عمداً** من `PUBLIC_PLAN_ORDER` و`PLAN_PRICING_DEFAULTS`
        (خطّةٌ لا تُباع)، فمن السهل أن تُنسى في جدول الأسماء — وشركةٌ تجريبيّةٌ
        تبلغ حدَّها تقرأ كلمة `Trial` عاريةً في منتصف جملةٍ عربيّة.
        """
        message = self._message(self.trial)
        self.assertNotIn("Trial", message)

    def test_it_still_says_which_limit_and_how_much(self):
        """ما تحسّنَ في الصياغة لا يُفقِد ما كان صحيحاً: الحدُّ ورقمُه ودورتُه."""
        message = self._message(self.basic)
        self.assertIn("فواتير البيع", message)
        self.assertIn("200", message)
        self.assertIn("شهرياً", message)
