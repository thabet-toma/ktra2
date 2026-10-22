"""K3: رابط عدّ عام لموظف مستودع مسمّى — قراءة نطاقه وكتابة العدّ على مسودّة الجرد.

السطح العام هنا **بلا مصادقة ويكتب بيانات**، فالحارسان الأهمّان في هذا الملف:
عزل الشركة (توكن شركة أ لا يقرأ ولا يكتب سطر شركة ب)، وقائمةُ مفاتيح صريحة
لمخرَج JSON (مفتاحٌ جديد يسقط الاختبار ولو كان بريئاً، فلا يمرّ حقلٌ ماليّ بصمت).
"""
import json
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.test import APITestCase

from accounting.models import Account
from core.models import ActivityLog
from core.throttles import ClientIpScopedThrottle
from docshare import services as docshare_services
from docshare.models import DOC_STOCKTAKE_COUNT, DocumentShare
from inventory.models import (
    Product, ProductCategory, Stocktake, StocktakeCountLink, StocktakeLine, Warehouse,
)
from inventory.services import post_stocktake
from tenants.models import UserCompanyMembership
from tenants.services import create_company

TOP_LEVEL_KEYS = {
    "company_name", "stocktake_number", "date", "warehouse",
    "counter_name", "finished", "lines",
}
LINE_KEYS = {
    "line_id", "sku", "name", "brand", "category_path", "uom",
    "system_quantity", "counted_quantity", "counted_by_name",
}
#: أيّ مفتاحٍ يحمل لغةَ مالٍ في أيّ عمق: السطح كلّه كمياتٌ لا قيم.
MONEY_MARKERS = ("cost", "price", "amount", "value", "total", "money", "currency")


class StocktakeCountLinkTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="k3-owner", password="x")
        cls.tenant = create_company("شركة رابط العدّ", cls.owner)
        cls.manager = User.objects.create_user(
            username="k3-manager", password="x", first_name="مدير", last_name="المخزون")
        cls.staff = User.objects.create_user(username="k3-staff", password="x")
        cls.viewer = User.objects.create_user(username="k3-viewer", password="x")
        UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.tenant, role="manager")
        UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.tenant, role="staff")
        UserCompanyMembership.objects.create(
            user=cls.viewer, tenant=cls.tenant, role="viewer")

        cls.inv_acct = Account.objects.create(
            tenant=cls.tenant, code="7104", name="مخزون العدّ",
            account_type="Asset", is_active=True)
        cls.cogs_acct = Account.objects.create(
            tenant=cls.tenant, code="7101", name="ت.ب.م العدّ",
            account_type="Expense", is_active=True)
        cls.cat_a = ProductCategory.objects.create(
            tenant=cls.tenant, name="إطارات", inventory_account=cls.inv_acct,
            cogs_account=cls.cogs_acct)
        cls.cat_child = ProductCategory.objects.create(
            tenant=cls.tenant, name="إطارات صغيرة", parent=cls.cat_a,
            inventory_account=cls.inv_acct, cogs_account=cls.cogs_acct)
        cls.cat_b = ProductCategory.objects.create(
            tenant=cls.tenant, name="بطاريات", inventory_account=cls.inv_acct,
            cogs_account=cls.cogs_acct)
        cls.cat_empty = ProductCategory.objects.create(
            tenant=cls.tenant, name="فارغ", inventory_account=cls.inv_acct,
            cogs_account=cls.cogs_acct)
        cls.warehouse = Warehouse.objects.create(
            tenant=cls.tenant, name="مستودع العدّ", code="K3-W")

        def product(sku, name, category=None, **extra):
            return Product.objects.create(
                tenant=cls.tenant, sku=sku, name_ar=name, category=category,
                quantity_on_hand=extra.pop("quantity_on_hand", Decimal("10")),
                avg_cost=extra.pop("avg_cost", Decimal("11")),
                **extra)

        cls.p_a = product(
            "K3-A", "إطار أ", cls.cat_a, brand="بيرجستون", avg_cost=Decimal("1234.56"))
        cls.p_child = product("K3-CH", "إطار ابن", cls.cat_child)
        cls.p_b = product(
            "K3-B", "بطارية ب", cls.cat_b, quantity_on_hand=Decimal("5"),
            sale_price=Decimal("9876.54"))
        cls.p_none = product("K3-N", "بلا تصنيف")

        cls.foreign_owner = User.objects.create_user(username="k3-foreign", password="x")
        cls.foreign_tenant = create_company("شركة عدّ أجنبية", cls.foreign_owner)
        cls.foreign_product = Product.objects.create(
            tenant=cls.foreign_tenant, sku="K3-F", name_ar="منتج أجنبي",
            quantity_on_hand=Decimal("9"))

        cls.stocktake = Stocktake.objects.create(
            tenant=cls.tenant, stocktake_date="2026-08-20",
            warehouse=cls.warehouse, notes="جرد رابط العدّ")
        cls.line_a = StocktakeLine.objects.create(
            stocktake=cls.stocktake, product=cls.p_a)
        cls.line_child = StocktakeLine.objects.create(
            stocktake=cls.stocktake, product=cls.p_child)
        cls.line_b = StocktakeLine.objects.create(
            stocktake=cls.stocktake, product=cls.p_b)
        cls.line_none = StocktakeLine.objects.create(
            stocktake=cls.stocktake, product=cls.p_none)

        cls.foreign_stocktake = Stocktake.objects.create(
            tenant=cls.foreign_tenant, stocktake_date="2026-08-20")
        cls.foreign_line = StocktakeLine.objects.create(
            stocktake=cls.foreign_stocktake, product=cls.foreign_product)

    def setUp(self):
        # خانق القراءة 60/دقيقة والكتابة 30/دقيقة على نفس الـIP: تاريخ الخانق
        # يُخزَّن في الكاش ويعبر بين الاختبارات، فيُصفَّر هنا لا في الإنتاج.
        cache.clear()

    # ── أدوات ──
    def _as(self, user):
        self.client.force_authenticate(user=user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _public(self):
        self.client.force_authenticate(user=None)
        self.client.credentials()

    def _link(self, stocktake=None, counter_name="أحمد", categories=None,
              days=3, expired=False, revoked=False, tenant=None):
        stocktake = stocktake or self.stocktake
        tenant = tenant or self.tenant
        share = docshare_services.create_share(
            tenant, DOC_STOCKTAKE_COUNT, stocktake.pk, days=days, dedupe=False)
        link = StocktakeCountLink.objects.create(
            tenant=tenant, stocktake=stocktake, share=share,
            counter_name=counter_name, categories=categories)
        if expired:
            share.expires_at = timezone.now() - timezone.timedelta(minutes=1)
            share.save(update_fields=["expires_at"])
        if revoked:
            docshare_services.revoke_share(share)
        return link

    def _public_url(self, link):
        return f"/api/share/{link.share.token}/count/"

    def _get_public(self, link):
        self._public()
        return self.client.get(self._public_url(link))

    def _post_public(self, link, body):
        self._public()
        return self.client.post(self._public_url(link), body, format="json")

    def _admin_create(self, user, stocktake=None, body=None):
        self._as(user)
        stocktake = stocktake or self.stocktake
        payload = {"counter_name": "أحمد", "days": 3}
        payload.update(body or {})
        return self.client.post(
            f"/api/inventory/stocktakes/{stocktake.id}/count-links/",
            payload, format="json")

    # ── الإداري: الإنشاء والقائمة والإبطال ──
    def test_admin_create_returns_the_contract_and_a_working_token(self):
        res = self._admin_create(self.manager, body={"categories": [self.cat_a.id]})
        self.assertEqual(res.status_code, 201, res.content)
        # قرار جولة التصليح ٩: 201 صار صفّ القائمة نفسه (لا مجموعةً جزئية منه).
        self.assertEqual(
            set(res.data),
            {"id", "token", "url_path", "counter_name", "categories", "status",
             "expires_at", "finished_at", "progress", "created_at"})
        self.assertEqual(res.data["counter_name"], "أحمد")
        self.assertEqual(res.data["categories"], [self.cat_a.id])
        self.assertEqual(res.data["status"], "active")
        self.assertEqual(res.data["progress"], {"lines": 1, "counted": 0})
        self.assertEqual(res.data["url_path"], f"/api/share/{res.data['token']}/count/")
        link = StocktakeCountLink.objects.get(pk=res.data["id"])
        self.assertEqual(link.tenant_id, self.tenant.pk)
        self.assertEqual(link.stocktake_id, self.stocktake.pk)
        self.assertEqual(link.share.expires_at > timezone.now(), True)

        self._public()
        public = self.client.get(res.data["url_path"])
        self.assertEqual(public.status_code, 200, public.content)
        self.assertEqual([ln["line_id"] for ln in public.data["lines"]],
                         [self.line_a.id])

    def test_admin_create_rejects_days_outside_the_three_choices(self):
        for days in (0, 2, 4, 30, "x", ""):
            with self.subTest(days=days):
                res = self._admin_create(self.manager, body={"days": days})
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("days", res.data)
        self.assertFalse(StocktakeCountLink.objects.exists())

    def test_admin_create_rejects_empty_or_foreign_or_out_of_scope_categories(self):
        cases = {
            "empty": ([], "تصنيف"),
            "foreign": ([self.cat_a.id, 999999], "تصنيف"),
            "out_of_stocktake": ([self.cat_empty.id], "تصنيف"),
        }
        for name, (categories, marker) in cases.items():
            with self.subTest(case=name):
                res = self._admin_create(
                    self.manager, body={"categories": categories})
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("categories", res.data)
                self.assertIn(marker, str(res.data))
        self.assertFalse(StocktakeCountLink.objects.exists())

    def test_admin_create_refuses_a_foreign_stocktake_and_a_viewer(self):
        res = self._admin_create(self.manager, stocktake=self.foreign_stocktake)
        self.assertEqual(res.status_code, 404, res.content)
        res = self._admin_create(self.viewer)
        self.assertEqual(res.status_code, 403, res.content)
        self.assertFalse(StocktakeCountLink.objects.exists())
        # وقراءةُ القائمة أيضاً: التوكن الحيّ يكتب، فمن لا يعدّل الجرد لا يراه.
        self._as(self.viewer)
        res = self.client.get(
            f"/api/inventory/stocktakes/{self.stocktake.id}/count-links/")
        self.assertEqual(res.status_code, 403, res.content)

    def test_admin_create_refuses_a_posted_stocktake(self):
        counted = StocktakeLine.objects.create(
            stocktake=self.stocktake, product=self.p_a, counted_quantity=Decimal("10"))
        self.stocktake.lines.exclude(pk=counted.pk).delete()
        post_stocktake(self.stocktake, user=self.manager)
        res = self._admin_create(self.manager)
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("مُرحَّل", str(res.data))

    def test_admin_list_shows_status_and_progress_over_each_links_scope(self):
        whole = self._link(counter_name="كل الجرد")
        scoped = self._link(counter_name="إطارات", categories=[self.cat_a.id])
        expired = self._link(counter_name="منتهٍ", expired=True)
        revoked = self._link(counter_name="مُبطَل", revoked=True)
        finished = self._link(counter_name="أنهى")
        finished.finished_at = timezone.now()
        finished.save(update_fields=["finished_at"])
        StocktakeLine.objects.filter(pk=self.line_a.pk).update(
            counted_quantity=Decimal("10"), counted_by_name="أحمد",
            counted_at=timezone.now())
        StocktakeLine.objects.filter(pk=self.line_b.pk).update(
            counted_quantity=Decimal("4"), counted_by_name="أحمد",
            counted_at=timezone.now())

        self._as(self.manager)
        res = self.client.get(
            f"/api/inventory/stocktakes/{self.stocktake.id}/count-links/")
        self.assertEqual(res.status_code, 200, res.content)
        rows = {row["counter_name"]: row for row in res.data}
        self.assertEqual(set(rows), {"كل الجرد", "إطارات", "منتهٍ", "مُبطَل", "أنهى"})
        self.assertEqual(rows["كل الجرد"]["status"], "active")
        self.assertEqual(rows["كل الجرد"]["progress"], {"lines": 4, "counted": 2})
        self.assertEqual(rows["إطارات"]["progress"], {"lines": 1, "counted": 1})
        self.assertEqual(rows["منتهٍ"]["status"], "expired")
        self.assertEqual(rows["مُبطَل"]["status"], "revoked")
        self.assertEqual(rows["أنهى"]["status"], "finished")
        self.assertIsNotNone(rows["أنهى"]["finished_at"])
        for row in rows.values():
            self.assertEqual(
                set(row),
                {"id", "token", "url_path", "counter_name", "categories", "status",
                 "expires_at", "finished_at", "progress", "created_at"})

    def test_generic_share_endpoint_cannot_create_a_count_link(self):
        """بابٌ واحد للرابط: مشاركةٌ بلا `StocktakeCountLink` توكنٌ ميت يردّ 404."""
        self._as(self.manager)
        res = self.client.post(
            "/api/document-shares/",
            {"doc_type": DOC_STOCKTAKE_COUNT, "doc_id": self.stocktake.id, "days": 3},
            format="json")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(DocumentShare.objects.filter(
            doc_type=DOC_STOCKTAKE_COUNT).exists())

    def test_admin_revoke_works_and_is_scoped_to_the_stocktake(self):
        link = self._link()
        self._as(self.manager)
        res = self.client.post(
            f"/api/inventory/stocktakes/{self.stocktake.id}/count-links/"
            f"{link.id}/revoke/")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["status"], "revoked")
        link.share.refresh_from_db()
        self.assertIsNotNone(link.share.revoked_at)

        other = StocktakeCountLink.objects.create(
            tenant=self.foreign_tenant, stocktake=self.foreign_stocktake,
            share=docshare_services.create_share(
                self.foreign_tenant, DOC_STOCKTAKE_COUNT,
                self.foreign_stocktake.pk, dedupe=False),
            counter_name="أجنبي")
        res = self.client.post(
            f"/api/inventory/stocktakes/{self.stocktake.id}/count-links/"
            f"{other.id}/revoke/")
        self.assertEqual(res.status_code, 404, res.content)
        other.share.refresh_from_db()
        self.assertIsNone(other.share.revoked_at)

    # ── العام: القراءة ──
    def test_public_get_returns_the_exact_allowlist_and_only_scope_lines(self):
        link = self._link(categories=[self.cat_a.id])
        res = self._get_public(link)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(set(res.data), TOP_LEVEL_KEYS)
        self.assertEqual(res.data["company_name"], "شركة رابط العدّ")
        self.assertEqual(res.data["counter_name"], "أحمد")
        self.assertFalse(res.data["finished"])
        self.assertEqual(len(res.data["lines"]), 1)
        line = res.data["lines"][0]
        self.assertEqual(set(line), LINE_KEYS)
        self.assertEqual(line["line_id"], self.line_a.id)
        self.assertEqual(line["sku"], "K3-A")
        self.assertEqual(line["name"], "إطار أ")
        self.assertEqual(line["brand"], "بيرجستون")
        self.assertEqual(line["category_path"], "إطارات")
        self.assertEqual(Decimal(line["system_quantity"]), Decimal("10"))

    def test_public_get_never_exposes_money_and_uses_current_on_hand(self):
        link = self._link()
        self.p_a.quantity_on_hand = Decimal("42")
        self.p_a.save(update_fields=["quantity_on_hand"])
        res = self._get_public(link)
        self.assertEqual(res.status_code, 200, res.content)
        raw = json.dumps(res.data, ensure_ascii=False)
        self.assertNotIn("1234.56", raw)
        self.assertNotIn("9876.54", raw)
        for marker in MONEY_MARKERS:
            self.assertNotIn(marker, raw.lower())
        rows = {row["line_id"]: row for row in res.data["lines"]}
        self.assertEqual(Decimal(rows[self.line_a.id]["system_quantity"]), Decimal("42"))

    def test_public_get_of_another_tenants_token_shows_nothing_foreign(self):
        link = self._link()
        foreign_link = self._link(
            stocktake=self.foreign_stocktake, tenant=self.foreign_tenant,
            counter_name="أجنبي")
        res = self._get_public(link)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertNotIn(self.foreign_line.id,
                         [row["line_id"] for row in res.data["lines"]])
        foreign = self._get_public(foreign_link)
        self.assertEqual(foreign.status_code, 200, foreign.content)
        self.assertEqual([row["line_id"] for row in foreign.data["lines"]],
                         [self.foreign_line.id])

    def test_public_get_unknown_expired_revoked_and_posted(self):
        unknown = self.client.get("/api/share/not-a-real-token/count/")
        self.assertEqual(unknown.status_code, 404, unknown.content)

        expired = self._get_public(self._link(expired=True))
        self.assertEqual(expired.status_code, 410, expired.content)
        revoked = self._get_public(self._link(revoked=True))
        self.assertEqual(revoked.status_code, 410, revoked.content)

        posted = self._link()
        self.stocktake.is_posted = True
        self.stocktake.save(update_fields=["is_posted"])
        res = self._get_public(posted)
        self.assertEqual(res.status_code, 410, res.content)

    def test_the_count_token_does_not_serve_the_public_page_and_records_no_view(self):
        """رمز العدّ سطحُ كتابةٍ JSON — لا يكسب صفحة `/s/` ولا يسجّل مشاهدة."""
        link = self._link()
        before = DocumentShare.objects.get(pk=link.share.pk)
        self._public()
        res = self.client.get(f"/api/share/{link.share.token}/")
        self.assertEqual(res.status_code, 404, res.content)
        self.assertIn("الرابط غير صالح", str(res.data))
        link.share.refresh_from_db()
        self.assertEqual(link.share.view_count, before.view_count)
        self.assertIsNone(link.share.last_viewed_at)
        self.assertIsNone(link.share.first_viewed_at)

    # ── العام: الكتابة ──
    def test_public_post_writes_stamps_and_moves_the_header_timestamp(self):
        link = self._link(categories=[self.cat_a.id])
        before = Stocktake.objects.get(pk=self.stocktake.pk).updated_at
        res = self._post_public(link, {
            "entries": [
                {"line_id": self.line_a.id, "counted_quantity": "7.5"},
                {"line_id": self.line_b.id, "counted_quantity": "3"},
                {"line_id": self.foreign_line.id, "counted_quantity": "2"},
                {"line_id": 999999, "counted_quantity": "1"},
            ],
        })
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data, {"written": 1, "ignored": 3, "finished": False})

        self.line_a.refresh_from_db()
        self.assertEqual(self.line_a.counted_quantity, Decimal("7.5000"))
        self.assertEqual(self.line_a.counted_by_name, "أحمد")
        self.assertIsNotNone(self.line_a.counted_at)
        self.line_b.refresh_from_db()
        self.assertIsNone(self.line_b.counted_quantity)
        self.assertEqual(self.line_b.counted_by_name, "")
        self.foreign_line.refresh_from_db()
        self.assertIsNone(self.foreign_line.counted_quantity)
        self.assertGreater(
            Stocktake.objects.get(pk=self.stocktake.pk).updated_at, before)
        self.assertTrue(ActivityLog.objects.filter(
            tenant=self.tenant, entity_type="stocktake",
            entity_id=self.stocktake.pk, user__isnull=True,
            description__contains="أحمد").exists())

    def test_a_foreign_tenants_token_counts_our_line_ids_as_ignored(self):
        """عزلٌ طرفيّ: توكن شركة B يكتب معرّفات بنود شركة A — تُتجاهل ولا تُلمس."""
        foreign_link = self._link(
            stocktake=self.foreign_stocktake, tenant=self.foreign_tenant,
            counter_name="أجنبي")
        res = self._post_public(foreign_link, {"entries": [
            {"line_id": self.line_a.id, "counted_quantity": "3"},
            {"line_id": self.line_b.id, "counted_quantity": "4"},
        ]})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data, {"written": 0, "ignored": 2, "finished": False})
        for line in (self.line_a, self.line_b):
            fresh = StocktakeLine.objects.get(pk=line.pk)
            self.assertIsNone(fresh.counted_quantity)
            self.assertEqual(fresh.counted_by_name, "")
            self.assertIsNone(fresh.counted_at)

    def test_public_write_makes_the_managers_etag_stale(self):
        link = self._link()
        self._as(self.manager)
        detail = self.client.get(f"/api/inventory/stocktakes/{self.stocktake.id}/")
        etag = detail["ETag"]

        res = self._post_public(
            link, {"entries": [{"line_id": self.line_a.id, "counted_quantity": "8"}]})
        self.assertEqual(res.status_code, 200, res.content)

        self._as(self.manager)
        stale = self.client.patch(
            f"/api/inventory/stocktakes/{self.stocktake.id}/",
            {"notes": "تعديل بتوكنٍ قديم"}, format="json", HTTP_IF_MATCH=etag)
        self.assertEqual(stale.status_code, 412, stale.content)
        fresh = self.client.get(f"/api/inventory/stocktakes/{self.stocktake.id}/")
        accepted = self.client.patch(
            f"/api/inventory/stocktakes/{self.stocktake.id}/",
            {"notes": "تعديل بتوكنٍ حديث"}, format="json",
            HTTP_IF_MATCH=fresh["ETag"])
        self.assertEqual(accepted.status_code, 200, accepted.content)

    def test_public_post_null_clears_the_count_and_stamps(self):
        link = self._link()
        self._post_public(
            link, {"entries": [{"line_id": self.line_a.id, "counted_quantity": "4"}]})
        res = self._post_public(
            link, {"entries": [{"line_id": self.line_a.id, "counted_quantity": None}]})
        self.assertEqual(res.status_code, 200, res.content)
        self.line_a.refresh_from_db()
        self.assertIsNone(self.line_a.counted_quantity)
        self.assertEqual(self.line_a.counted_by_name, "")
        self.assertIsNone(self.line_a.counted_at)

    def test_public_post_invalid_quantity_writes_nothing_atomic(self):
        link = self._link()
        cases = ["-1", "1.23456", "abc", "", True, "NaN"]
        for value in cases:
            with self.subTest(value=value):
                res = self._post_public(link, {"entries": [
                    {"line_id": self.line_a.id, "counted_quantity": "5"},
                    {"line_id": self.line_b.id, "counted_quantity": value},
                ]})
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("entries", res.data)
                self.assertIsNone(
                    StocktakeLine.objects.get(pk=self.line_a.pk).counted_quantity)
                self.assertIsNone(
                    StocktakeLine.objects.get(pk=self.line_b.pk).counted_quantity)

    def test_public_post_rejects_a_quantity_the_column_cannot_hold(self):
        """`max_digits=18, decimal_places=4` — 14 رقماً صحيحاً؛ أكثرُ منها كان
        يمرّ التفسير ثم يُسقط `bulk_update` على MySQL بخطأ 500."""
        link = self._link()
        for value in ("1e15", "123456789012345"):
            with self.subTest(value=value):
                res = self._post_public(link, {"entries": [
                    {"line_id": self.line_a.id, "counted_quantity": "5"},
                    {"line_id": self.line_b.id, "counted_quantity": value},
                ]})
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("counted_quantity", str(res.data))
                self.assertIsNone(
                    StocktakeLine.objects.get(pk=self.line_a.pk).counted_quantity)
                self.assertIsNone(
                    StocktakeLine.objects.get(pk=self.line_b.pk).counted_quantity)

    def test_public_post_accepts_the_largest_quantity_the_column_holds(self):
        """حدُّ العمود نفسه (14 صحيحاً + 4 منازل) يمرّ — لا سقفاً أدنى منه.

        لا نقرأ الصفّ بعدها: SQLite (قاعدة الاختبار) يحفظ 15 رقماً معنوياً وحده،
        فإعادةُ قراءة 18 رقماً منه لا تقيس العمود. MySQL الإنتاجي `DECIMAL(18,4)`
        يحفظها كما هي.
        """
        link = self._link()
        res = self._post_public(link, {"entries": [
            {"line_id": self.line_a.id, "counted_quantity": "99999999999999.9999"}]})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["written"], 1)

    def test_public_post_rejects_non_ascii_or_oversized_line_ids(self):
        """`isdigit` يقبل `²` و`①` ثم `int` يرمي، وسلسلةٌ أطول من 4300 خانة
        تتجاوز حدّ بايثون لتحويل النصّ إلى عدد — كلاهما 500 على سطحٍ بلا مصادقة."""
        link = self._link()
        for value in ("²", "①", "1" * 5000, 0, -3):
            with self.subTest(value=repr(value)[:12]):
                res = self._post_public(link, {"entries": [
                    {"line_id": self.line_a.id, "counted_quantity": "5"},
                    {"line_id": value, "counted_quantity": "2"},
                ]})
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("line_id", str(res.data))
                self.assertIsNone(
                    StocktakeLine.objects.get(pk=self.line_a.pk).counted_quantity)

    def test_public_post_limits_entries_and_body_size(self):
        link = self._link()
        too_many = self._post_public(link, {"entries": [
            {"line_id": self.line_a.id, "counted_quantity": "1"}] * 501})
        self.assertEqual(too_many.status_code, 400, too_many.content)
        self.assertIn("500", str(too_many.data))
        self.assertIsNone(
            StocktakeLine.objects.get(pk=self.line_a.pk).counted_quantity)

        padded = json.dumps({"entries": [], "pad": "x" * (256 * 1024 + 100)})
        self._public()
        oversized = self.client.post(
            self._public_url(link), data=padded, content_type="application/json")
        self.assertEqual(oversized.status_code, 413, oversized.content)

    def test_public_post_deeply_nested_json_is_a_400_not_a_crash(self):
        link = self._link()
        body = "[" * 100000 + "]" * 100000
        self._public()
        res = self.client.post(
            self._public_url(link), data=body, content_type="application/json")
        self.assertEqual(res.status_code, 400, res.content)

    def test_public_post_finishes_idempotently_and_keeps_writing(self):
        link = self._link()
        first = self._post_public(link, {"finished": True})
        self.assertEqual(first.status_code, 200, first.content)
        self.assertTrue(first.data["finished"])
        link.refresh_from_db()
        stamp = link.finished_at
        self.assertIsNotNone(stamp)

        second = self._post_public(
            link, {"entries": [{"line_id": self.line_b.id, "counted_quantity": "2"}],
                   "finished": True})
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.data["written"], 1)
        link.refresh_from_db()
        self.assertEqual(link.finished_at, stamp)
        self.line_b.refresh_from_db()
        self.assertEqual(self.line_b.counted_quantity, Decimal("2.0000"))

    def test_public_post_rejects_a_non_boolean_finished_and_non_object_body(self):
        link = self._link()
        res = self._post_public(link, {"entries": [], "finished": "yes"})
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("finished", res.data)
        res = self._post_public(link, ["not", "an", "object"])
        self.assertEqual(res.status_code, 400, res.content)

    def test_public_post_unknown_expired_revoked_and_posted(self):
        unknown = self.client.post(
            "/api/share/not-a-real-token/count/", {"entries": []}, format="json")
        self.assertEqual(unknown.status_code, 404, unknown.content)

        expired = self._post_public(self._link(expired=True), {"entries": []})
        self.assertEqual(expired.status_code, 410, expired.content)
        revoked = self._post_public(self._link(revoked=True), {"entries": []})
        self.assertEqual(revoked.status_code, 410, revoked.content)

        posted = self._link()
        self.stocktake.is_posted = True
        self.stocktake.save(update_fields=["is_posted"])
        res = self._post_public(
            posted, {"entries": [{"line_id": self.line_a.id, "counted_quantity": "-1"}]})
        self.assertEqual(res.status_code, 410, res.content)
        self.line_a.refresh_from_db()
        self.assertIsNone(self.line_a.counted_quantity)

    def test_posting_the_stocktake_revokes_every_count_link(self):
        first = self._link(counter_name="أول")
        second = self._link(counter_name="ثانٍ", categories=[self.cat_a.id])
        self.stocktake.lines.exclude(pk=self.line_a.pk).delete()
        StocktakeLine.objects.filter(pk=self.line_a.pk).update(
            counted_quantity=Decimal("10"))
        post_stocktake(self.stocktake, user=self.manager)
        first.share.refresh_from_db()
        second.share.refresh_from_db()
        self.assertIsNotNone(first.share.revoked_at)
        self.assertIsNotNone(second.share.revoked_at)
        self.assertEqual(self._get_public(first).status_code, 410)

    # ── الخانق والعقد ──
    def test_throttle_class_scope_and_configured_rates(self):
        from docshare.views import StocktakeCountView

        self.assertEqual(StocktakeCountView.authentication_classes, [])
        self.assertEqual(StocktakeCountView.permission_classes, [AllowAny])
        self.assertEqual(StocktakeCountView.throttle_classes, [ClientIpScopedThrottle])
        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertIn("doc_share_count_read", rates)
        self.assertIn("doc_share_count_write", rates)
        self.assertTrue(rates["doc_share_count_read"].endswith("/min"))
        self.assertTrue(rates["doc_share_count_write"].endswith("/min"))

    def test_public_read_is_throttled(self):
        link = self._link()
        # `SimpleRateThrottle.THROTTLE_RATES` لقطةٌ وقت الاستيراد، فتغيير
        # `settings.REST_FRAMEWORK` وحده لا يُحرّكها — نُضيّقها على الصنف هنا.
        rates = {"doc_share_count_read": "1/min", "doc_share_count_write": "30/min"}
        with (
            override_settings(CACHES={"default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}),
            mock.patch.object(ClientIpScopedThrottle, "THROTTLE_RATES", rates),
        ):
            cache.clear()
            self._public()
            first = self.client.get(self._public_url(link))
            second = self.client.get(self._public_url(link))
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(second.status_code, 429, second.content)

    def test_public_write_uses_the_write_scope_not_the_read_scope(self):
        """دلوٌ لكلّ سكوب: قراءةٌ مرتفعة لا تنقذ كتابةً مضبوطةً على 1/د."""
        link = self._link()
        rates = {"doc_share_count_read": "1000/min", "doc_share_count_write": "1/min"}
        with (
            override_settings(CACHES={"default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}),
            mock.patch.object(ClientIpScopedThrottle, "THROTTLE_RATES", rates),
        ):
            cache.clear()
            first = self._post_public(link, {"entries": [
                {"line_id": self.line_a.id, "counted_quantity": "1"}]})
            second = self._post_public(link, {"entries": [
                {"line_id": self.line_a.id, "counted_quantity": "2"}]})
            read = self._get_public(link)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(second.status_code, 429, second.content)
        self.assertEqual(read.status_code, 200, read.content)
