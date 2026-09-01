"""صفّ المنتج في الشاشة الجدولية: مجموع **كل** برانداته أو لا يظهر (#30).

التجميع يقع عند الرسم (#23) على الصفوف الواصلة وحدها، والقائمة تُرقَّم. فمنتجٌ
تتوزّع براندَاته على صفحتين كان يُرسَم صفَّ منتجٍ بمجموعٍ جزئي معروضٍ على أنه
مجموع المنتج. الإصلاح لا ينقل التجميع بل يضمن اكتمال مدخلاته: الخادم يُكمل
عائلات الصفحة **بعد** التقسيم، باستعلامٍ واحدٍ ثابت.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from inventory.models import Product, ProductFamily
from tenants.services import create_company

URL = "/api/inventory/products/"


class PageCompletesFamiliesTest(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="page-fam", password="x")
        cls.tenant = create_company("شركة الصفحات", cls.owner)
        # عائلةٌ ببراندين، ومعرّفاهما متباعدان — بينهما حشوٌ يملأ الصفحة كاملةً،
        # فيقعان حتماً على صفحتين بترتيب `-id` الافتراضي. هذا شكل البيانات
        # الحقيقي: إخوةٌ فُتحوا على مدى شهور.
        cls.family = ProductFamily.objects.create(tenant=cls.tenant, name_ar="215/65/16")
        cls.first = Product.objects.create(
            tenant=cls.tenant, family=cls.family, sku="TIRE-1", brand="دانتير",
            name_ar="215/65/16", quantity_on_hand=Decimal("10"))
        cls.filler = [
            Product.objects.create(
                tenant=cls.tenant, sku=f"F-{i}", name_ar=f"حشو {i}",
                quantity_on_hand=Decimal("1"))
            for i in range(5)
        ]
        cls.second = Product.objects.create(
            tenant=cls.tenant, family=cls.family, sku="TIRE-2", brand="روك بيلد",
            name_ar="215/65/16", quantity_on_hand=Decimal("4"))

    def _get(self, **params):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(URL, params, HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        self.assertEqual(res.status_code, 200, res.content[:300])
        return res.json()

    def _ids(self, payload):
        rows = payload["results"] if isinstance(payload, dict) else payload
        return {r["id"] for r in rows}

    def test_a_family_split_across_pages_arrives_whole(self):
        """الصفحة الأولى بترتيب `-id` تحمل الأحدث؛ أخوه الأقدم خارجها — ويجب
        أن يصلها رغم ذلك، وإلا فصفّ المنتج مجموعٌ جزئي يدّعي المجموع."""
        page = self._get(page=1, page_size=3, complete_families=1)
        ids = self._ids(page)
        self.assertIn(self.second.id, ids)
        self.assertIn(
            self.first.id, ids,
            "الأخ الواقع خارج الصفحة لم يصل — صفّ المنتج سيعرض مجموعاً جزئياً")

    def test_without_the_flag_nothing_changes(self):
        """العقد القائم لا يُمَسّ: من لا يطلب الإكمال لا يراه — ومنه منتقي
        المستندات (`?view=lookup`) الذي يعمل على البراند عمداً."""
        ids = self._ids(self._get(page=1, page_size=3))
        self.assertIn(self.second.id, ids)
        self.assertNotIn(self.first.id, ids)

    def test_a_brand_selecting_filter_is_never_completed(self):
        """فلتر «نفد»/بحثٌ يختار **أيّ البراندات** — إكمالُه كان سيُدخل إخوةً
        لا يطابقون داخل صفٍّ يدّعي أنه المنتج (تفريق #26)."""
        ids = self._ids(self._get(
            page=1, page_size=3, complete_families=1, search="روك بيلد"))
        self.assertIn(self.second.id, ids)
        self.assertNotIn(self.first.id, ids)

    def test_completion_costs_one_query_no_matter_how_many_families(self):
        """استعلامٌ واحدٌ إضافي ثابت لا واحدٌ لكل صفّ — ضمان #23 يبقى."""
        self.client.force_authenticate(user=self.owner)
        headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
        params = {"page": 1, "page_size": 50, "complete_families": 1}

        with CaptureQueriesContext(connection) as first:
            self.client.get(URL, params, **headers)
        before = len(first)

        for i in range(6):
            fam = ProductFamily.objects.create(tenant=self.tenant, name_ar=f"مقاس {i}")
            for b in range(3):
                Product.objects.create(
                    tenant=self.tenant, family=fam, sku=f"M-{i}-{b}", brand=f"براند {b}",
                    name_ar=f"مقاس {i}", quantity_on_hand=Decimal("2"))

        with CaptureQueriesContext(connection) as second:
            self.client.get(URL, params, **headers)
        self.assertEqual(
            len(second), before,
            "عدد الاستعلامات نما مع عدد العائلات — الإكمال صار استعلاماً لكل عائلة")

    def test_completion_never_reaches_another_company(self):
        other_owner = User.objects.create_user(username="page-fam-out", password="x")
        other = create_company("شركة الجوار", other_owner)
        other_family = ProductFamily.objects.create(tenant=other, name_ar="215/65/16")
        intruder = Product.objects.create(
            tenant=other, family=other_family, sku="X-1", brand="غريب",
            name_ar="215/65/16", quantity_on_hand=Decimal("9"))

        ids = self._ids(self._get(page=1, page_size=50, complete_families=1))
        self.assertNotIn(intruder.id, ids)
