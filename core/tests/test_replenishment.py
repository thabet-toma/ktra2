"""T-REORDER: محرّك التجديد — المعادلات، وشحّ البيانات، وقرار «النوع».

يُثبت هنا ما لا تُثبته قراءة الكود: أن الرقم المقترَح هو بعينه ما تعطيه المعادلة
بالورقة والقلم، وأن الصنف الذي لا نعرفه بعد لا يُقترَح له صفرٌ صامت، وأن نفاد
موديلٍ قديمٍ يقف بجانبه موديلٌ جديد لا يُقرأ «اطلب».
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from inventory.models import Product, StockMovement
from core.replenishment import (
    MIN_HISTORY_DAYS,
    REASON_NO_SALES,
    REASON_SHORT_HISTORY,
    URGENCY_DEAD,
    URGENCY_DEFERRED,
    URGENCY_URGENT,
    replenishment_rows,
    suggest_levels,
)
from tenants.models import UserCompanyMembership
from tenants.services import create_company

TODAY = datetime.date(2026, 6, 30)


class ReplenishmentEngineTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="repl_owner", password="x")
        cls.tenant = create_company("شركة التجديد", cls.owner)

    # ── أدوات ──
    def _product(self, sku, *, qty="0", group="", **kw):
        return Product.objects.create(
            tenant=self.tenant, sku=sku, name_ar=kw.pop("name", sku),
            variant_group=group, quantity_on_hand=Decimal(qty), **kw,
        )

    def _move(self, product, mtype, qty, days_ago):
        StockMovement.objects.create(
            tenant=self.tenant, product=product, movement_type=mtype,
            quantity=Decimal(str(qty)),
            movement_date=TODAY - datetime.timedelta(days=days_ago),
        )

    def _steady_seller(self, sku, *, qty="50", group=""):
        """90 وحدة صافية على 90 يوماً ⇒ ADU = 1، وذروة أسبوعية 14 ⇒ الذروة = 2."""
        p = self._product(sku, qty=qty, group=group)
        self._move(p, "IN", 1000, 89)          # أوّل حركة: يحدّد أيام السجل = 90
        for week in range(1, 7):               # ستّ أسابيع × 14 = 84
            self._move(p, "OUT", 14, week * 7)
        self._move(p, "OUT", 6, 49)            # الأسبوع السابع: 6 ⇒ المجموع 90
        return p

    def _rows(self, **kw):
        return replenishment_rows(self.tenant.TenantID, today=TODAY, **kw)

    def _row_for(self, product, **kw):
        return next(r for r in self._rows(**kw) if r["product_id"] == product.id)

    # ── (1) المعادلة كما تُحسب بالورقة ──
    def test_regular_seller_matches_hand_computed_levels(self):
        p = self._steady_seller("R-1")
        row = self._row_for(p)
        assert row["adu"] == Decimal("1"), row["adu"]
        assert row["lead_days"] == Decimal("14")      # لا طلبيات ⇒ الافتراضي
        # الأمان = (2 × 21) − (1 × 14) = 28 ؛ الأدنى = 14 + 28 = 42
        assert row["safety_stock"] == Decimal("28"), row["safety_stock"]
        assert row["suggested_min"] == 42, row["suggested_min"]
        # الأقصى = 42 + (1 × 30) = 72
        assert row["suggested_max"] == 72, row["suggested_max"]
        assert row["reason"] == ""

    def test_suggest_levels_is_pure_arithmetic(self):
        out = suggest_levels(
            adu=Decimal("1"), adu_peak=Decimal("2"),
            lead_days=Decimal("14"), lead_max_days=Decimal("21"), review_days=30,
        )
        assert out == {"safety_stock": Decimal("28"), "suggested_min": 42, "suggested_max": 72}

    # ── (2) سجلٌّ أقصر من الحدّ ⇒ لا اقتراح، وسببٌ مكتوب ──
    def test_short_history_yields_no_suggestion_with_a_reason(self):
        p = self._product("R-2", qty="10")
        self._move(p, "IN", 30, 5)
        self._move(p, "OUT", 10, 3)
        row = self._row_for(p)
        assert row["history_days"] < MIN_HISTORY_DAYS
        assert row["reason"] == REASON_SHORT_HISTORY
        assert row["suggested_min"] == 0
        assert row["adu"] == Decimal("0")

    # ── (3) رصيدٌ بلا حركةٍ في النافذة ⇒ راكد، لا «اطلب» ──
    def test_dead_stock_is_flagged_not_ordered(self):
        p = self._product("R-3", qty="20")
        self._move(p, "IN", 20, 200)
        row = self._row_for(p)
        assert row["reason"] == REASON_NO_SALES
        assert row["urgency"] == URGENCY_DEAD
        assert row["order_qty"] == Decimal("0")

    # ── (4) النوع مغطّى بموديلٍ أحدث ⇒ مؤجَّل + تسميةُ البديل ──
    def test_group_covered_by_newer_model_defers_the_order(self):
        old = self._steady_seller("R-4-OLD", qty="0", group="205/65/16")
        new = self._steady_seller("R-4-NEW", qty="400", group="205/65/16")
        row = self._row_for(old)
        assert row["status"] == "out_of_stock"
        assert row["alternatives"] == 1
        assert row["newest_alternative"] == new.name_ar
        assert row["urgency"] == URGENCY_DEFERRED, (
            row["urgency"], row["group_available"], row["group_effective_min"])

    # ── (5) النوع كلّه نفد ⇒ عاجل ──
    def test_whole_group_out_of_stock_is_urgent(self):
        old = self._steady_seller("R-5-OLD", qty="0", group="195/65/15")
        self._steady_seller("R-5-NEW", qty="0", group="195/65/15")
        row = self._row_for(old)
        assert row["urgency"] == URGENCY_URGENT
        assert row["alternatives"] == 0
        assert row["order_qty"] > Decimal("0")

    # ── (6) مرتجع البيع يخفض المعدّل ──
    def test_sales_return_lowers_the_daily_rate(self):
        p = self._steady_seller("R-6")
        self._move(p, "RETURN_IN", 6, 49)      # يلغي صرف الأسبوع السابع
        row = self._row_for(p)
        assert row["adu"] == Decimal("84") / Decimal("90"), row["adu"]
        # الأدنى يبقى 42: الذروة الأسبوعية لم تتغيّر (14) فمخزون الأمان يمتصّ
        # الفرق — والأثر يظهر في الأقصى الذي يمتدّ بمعدّل الصرف: 42 + 0.933×30 = 70.
        assert row["suggested_max"] == 70, row["suggested_max"]

    # ── (7) عدّ الاستعلامات ثابت مهما بلغ عدد الأصناف ──
    def test_query_count_does_not_grow_with_catalog_size(self):
        for i in range(20):
            self._steady_seller(f"R-7-{i}", group=f"G{i % 4}")
        with CaptureQueriesContext(connection) as small:
            replenishment_rows(self.tenant.TenantID, today=TODAY)
        for i in range(20, 60):
            self._steady_seller(f"R-7-{i}", group=f"G{i % 4}")
        with CaptureQueriesContext(connection) as large:
            rows = replenishment_rows(self.tenant.TenantID, today=TODAY)
        assert len(rows) >= 60
        assert len(large) == len(small), (len(small), len(large))

    # ── مستوى النوع: صفٌّ واحد لكل نوع ──
    def test_group_level_collapses_to_one_row_per_type(self):
        self._steady_seller("R-8-A", qty="0", group="215/60/17")
        self._steady_seller("R-8-B", qty="0", group="215/60/17")
        rows = self._rows(level="group")
        target = next(r for r in rows if r["group_key"] == "215/60/17")
        assert target["products_count"] == 2
        assert target["out_of_stock_count"] == 2
        # طلب النوع = ضعف طلب الفرد ⇒ ADU = 2
        assert target["adu"] == Decimal("2")
        assert target["urgency"] == URGENCY_URGENT
        # أرقام النوع مجاميعُ أفراده — فمجموع التفصيل يساوي رقم الصفّ
        items = [r for r in self._rows() if r["group_key"] == "215/60/17"]
        assert target["suggested_min"] == sum(r["suggested_min"] for r in items) == 84
        assert target["order_qty"] == sum((r["order_qty"] for r in items), Decimal("0"))


class ApplyReplenishmentApiTest(APITestCase):
    """نقطة التطبيق: تكتب، فتُحرَس بصلاحية الكتابة وبحدّ الشركة."""

    URL = "/api/inventory/products/apply-replenishment/"

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="apply_owner", password="x")
        cls.tenant = create_company("شركة التطبيق", cls.owner)
        cls.stranger = User.objects.create_user(username="apply_stranger", password="x")
        cls.other = create_company("شركة الغير", cls.stranger)

        cls.seller = Product.objects.create(
            tenant=cls.tenant, sku="AP-1", name_ar="صنف يبيع",
            quantity_on_hand=Decimal("50"),
        )
        today = datetime.date.today()
        StockMovement.objects.create(
            tenant=cls.tenant, product=cls.seller, movement_type="IN",
            quantity=Decimal("1000"),
            movement_date=today - datetime.timedelta(days=89),
        )
        for week in range(1, 7):
            StockMovement.objects.create(
                tenant=cls.tenant, product=cls.seller, movement_type="OUT",
                quantity=Decimal("14"),
                movement_date=today - datetime.timedelta(days=week * 7),
            )
        StockMovement.objects.create(     # الأسبوع السابع ⇒ المجموع 90 على 90 يوماً
            tenant=cls.tenant, product=cls.seller, movement_type="OUT",
            quantity=Decimal("6"), movement_date=today - datetime.timedelta(days=49),
        )
        cls.newborn = Product.objects.create(
            tenant=cls.tenant, sku="AP-2", name_ar="صنف حديث",
            quantity_on_hand=Decimal("5"),
        )
        StockMovement.objects.create(
            tenant=cls.tenant, product=cls.newborn, movement_type="IN",
            quantity=Decimal("5"), movement_date=today - datetime.timedelta(days=3),
        )
        cls.foreign = Product.objects.create(
            tenant=cls.other, sku="AP-X", name_ar="صنف شركة أخرى",
            quantity_on_hand=Decimal("7"), min_stock_level=3,
        )

    def _post(self, ids, tenant=None, user=None):
        self.client.force_authenticate(user=user or self.owner)
        return self.client.post(
            self.URL, {"product_ids": ids}, format="json",
            HTTP_X_TENANT_ID=str((tenant or self.tenant).TenantID),
        )

    def test_applies_the_suggested_pair_and_says_what_it_skipped(self):
        res = self._post([self.seller.id, self.newborn.id])
        assert res.status_code == 200, res.content[:300]
        body = res.json()
        assert body["applied"] == 1
        self.seller.refresh_from_db()
        assert self.seller.min_stock_level == 42
        assert self.seller.max_stock_level == 72
        # الصنف الحديث لا يُكتب عليه صفر — «لا أعرف بعد» ليست «لا تطلب».
        self.newborn.refresh_from_db()
        assert self.newborn.min_stock_level is None
        assert [s["product_id"] for s in body["skipped"]] == [self.newborn.id]
        assert REASON_SHORT_HISTORY in body["skipped"][0]["reason"]

    def test_viewer_role_is_refused(self):
        viewer = User.objects.create_user(username="apply_viewer", password="x")
        UserCompanyMembership.objects.create(
            user=viewer, tenant=self.tenant, role="viewer")
        res = self._post([self.seller.id], user=viewer)
        assert res.status_code == 403, res.status_code

    def test_other_company_product_is_untouched(self):
        res = self._post([self.foreign.id])
        assert res.status_code == 200, res.content[:300]
        assert res.json()["applied"] == 0
        self.foreign.refresh_from_db()
        assert self.foreign.min_stock_level == 3
        assert self.foreign.max_stock_level is None

    def test_empty_selection_is_a_client_error_not_a_silent_success(self):
        res = self._post([])
        assert res.status_code == 400, res.status_code


class BulkSetGroupApiTest(APITestCase):
    """«النوع» بلا مدخلٍ جماعي = حقلٌ يبقى فارغاً أبداً، وبفراغه يسقط التجميع كلّه."""

    URL = "/api/inventory/products/bulk-set-group/"

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="grp_owner", password="x")
        cls.tenant = create_company("شركة النوع", cls.owner)
        cls.stranger = User.objects.create_user(username="grp_stranger", password="x")
        cls.other = create_company("شركة أخرى للنوع", cls.stranger)
        cls.a = Product.objects.create(tenant=cls.tenant, sku="G-1", name_ar="ايفون 14 عادي")
        cls.b = Product.objects.create(tenant=cls.tenant, sku="G-2", name_ar="ايفون 14 برو")
        cls.untouched = Product.objects.create(tenant=cls.tenant, sku="G-3", name_ar="شاحن")
        cls.foreign = Product.objects.create(
            tenant=cls.other, sku="G-X", name_ar="صنف الغير", variant_group="أصلي")

    def _post(self, body, user=None, tenant=None):
        self.client.force_authenticate(user=user or self.owner)
        return self.client.post(
            self.URL, body, format="json",
            HTTP_X_TENANT_ID=str((tenant or self.tenant).TenantID),
        )

    def test_sets_the_type_on_the_selected_items_only(self):
        res = self._post({"product_ids": [self.a.id, self.b.id], "variant_group": "ايفون 14"})
        assert res.status_code == 200, res.content[:300]
        assert res.json()["updated"] == 2
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.untouched.refresh_from_db()
        assert self.a.variant_group == self.b.variant_group == "ايفون 14"
        assert self.untouched.variant_group == ""

    def test_absent_field_is_not_touched(self):
        self._post({"product_ids": [self.a.id], "variant_group": "ايفون 14"})
        res = self._post({"product_ids": [self.a.id], "brand": "أبل"})
        assert res.status_code == 200, res.content[:300]
        self.a.refresh_from_db()
        assert self.a.brand == "أبل"
        assert self.a.variant_group == "ايفون 14"   # لم يُمرَّر ⇒ لم يُمَسّ

    def test_body_without_any_field_is_refused(self):
        res = self._post({"product_ids": [self.a.id]})
        assert res.status_code == 400, res.status_code

    def test_viewer_role_is_refused(self):
        viewer = User.objects.create_user(username="grp_viewer", password="x")
        UserCompanyMembership.objects.create(user=viewer, tenant=self.tenant, role="viewer")
        res = self._post({"product_ids": [self.a.id], "variant_group": "س"}, user=viewer)
        assert res.status_code == 403, res.status_code

    def test_other_company_product_is_untouched(self):
        res = self._post({"product_ids": [self.foreign.id], "variant_group": "مسروق"})
        assert res.status_code == 200, res.content[:300]
        assert res.json()["updated"] == 0
        self.foreign.refresh_from_db()
        assert self.foreign.variant_group == "أصلي"

    # ── الدليل الحقيقي: تعيين النوع يُشغِّل البدائل من طرفٍ لطرف ──
    def test_setting_the_type_turns_alternatives_on_end_to_end(self):
        """قبل التعيين لا بديل لأن كل صنفٍ نوعٌ بذاته؛ وبعده يصيران نوعاً واحداً."""
        Product.objects.filter(pk=self.b.pk).update(quantity_on_hand=Decimal("40"))
        before = {r["product_id"]: r for r in replenishment_rows(self.tenant.TenantID)}
        assert before[self.a.id]["alternatives"] == 0
        assert before[self.a.id]["group_key"] == "ايفون 14 عادي"   # الاسم، لا نوع

        self._post({"product_ids": [self.a.id, self.b.id], "variant_group": "ايفون 14"})

        after = {r["product_id"]: r for r in replenishment_rows(self.tenant.TenantID)}
        assert after[self.a.id]["group_key"] == "ايفون 14"
        assert after[self.a.id]["alternatives"] == 1
        assert after[self.a.id]["newest_alternative"] == "ايفون 14 برو"
        assert after[self.a.id]["group_available"] == Decimal("40")


@override_settings(CACHES={"default": {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "reorder-test",
}})
class ReportCacheInvalidationTest(APITestCase):
    """كاش التقارير 60ث: بلا إبطاله يبدو زرّ «تثبيت الحدود» معطّلاً."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="cache_owner", password="x")
        cls.tenant = create_company("شركة الكاش", cls.owner)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="C-1", name_ar="صنف الكاش",
            quantity_on_hand=Decimal("5"),
        )
        today = datetime.date.today()
        StockMovement.objects.create(
            tenant=cls.tenant, product=cls.product, movement_type="IN",
            quantity=Decimal("500"), movement_date=today - datetime.timedelta(days=89),
        )
        for week in range(1, 7):
            StockMovement.objects.create(
                tenant=cls.tenant, product=cls.product, movement_type="OUT",
                quantity=Decimal("14"), movement_date=today - datetime.timedelta(days=week * 7),
            )

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.client.force_authenticate(user=self.owner)

    def _run(self):
        res = self.client.get(
            "/api/reports/stock-replenishment/",
            HTTP_X_TENANT_ID=str(self.tenant.TenantID),
        )
        assert res.status_code == 200, res.content[:300]
        return res.json()["rows"][0]

    def test_applying_levels_busts_the_report_cache(self):
        first = self._run()
        assert first["manual_min"] == ""          # لا حدّ يدوي بعد

        res = self.client.post(
            "/api/inventory/products/apply-replenishment/",
            {"product_ids": [self.product.id]}, format="json",
            HTTP_X_TENANT_ID=str(self.tenant.TenantID),
        )
        assert res.status_code == 200, res.content[:300]
        assert res.json()["applied"] == 1

        second = self._run()
        # بلا الإبطال تعود هذه القيمة "" من الكاش لستّين ثانية.
        assert second["manual_min"] == first["suggested_min"], (first, second)

    def test_plain_rerun_still_hits_the_cache(self):
        """الإبطال جرّاحيّ: لا يُلغي الكاش، فإعادة التشغيل بلا كتابة تبقى مخدومة."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        self._run()
        with CaptureQueriesContext(connection) as ctx:
            self._run()
        assert len(ctx) <= 3, len(ctx)   # مصادقة/عضوية فقط — لا استعلامات التقرير
