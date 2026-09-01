"""#34: المقابض السبعة عبر `/api/logistics/purchase-settings/current/`.

كانت الثلاثة القائمة (`default_lead_time_days`/`review_period_days`) مضبوطةً
بقيمة دائمة في قاعدة البيانات بلا شاشةٍ تعدّلها، والخمسة الجديدة
(`forecast_*`) ثوابت وحدة في `core/replenishment.py`. يُثبت هنا: أن السبعة
تُقرأ وتُكتَب من هذه النقطة الآن، وأن α/β محروسان بين صفر وواحد حصراً، وأن
إعدادات شركةٍ لا تُطبَّق على حساب أخرى.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from logistics.models import PurchaseSettings
from tenants.services import create_company


class ForecastKnobsSerializerExposureTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="knobs_api", password="x")
        cls.tenant = create_company("شركة مقابض API", cls.user)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_get_returns_all_seven_knobs_with_their_defaults(self):
        res = self.client.get(
            "/api/logistics/purchase-settings/current/", **self._auth())
        assert res.status_code == 200, res.content
        body = res.json()
        assert body["default_lead_time_days"] == 14
        assert body["review_period_days"] == 30
        assert Decimal(body["forecast_alpha"]) == Decimal("0.25")
        assert Decimal(body["forecast_beta"]) == Decimal("0.15")
        assert body["forecast_history_weeks"] == 26
        assert Decimal(body["forecast_trend_cap_ratio"]) == Decimal("0.33")
        assert Decimal(body["forecast_safety_factor"]) == Decimal("1.28")

    def test_patch_updates_a_knob_and_persists_it(self):
        res = self.client.patch(
            "/api/logistics/purchase-settings/current/",
            {"forecast_alpha": "0.40", "forecast_history_weeks": 12},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        row = PurchaseSettings.objects.get(tenant=self.tenant)
        assert row.forecast_alpha == Decimal("0.40")
        assert row.forecast_history_weeks == 12

    def test_alpha_zero_is_rejected(self):
        res = self.client.patch(
            "/api/logistics/purchase-settings/current/",
            {"forecast_alpha": "0"}, format="json", **self._auth())
        assert res.status_code == 400, res.content

    def test_alpha_one_is_rejected(self):
        res = self.client.patch(
            "/api/logistics/purchase-settings/current/",
            {"forecast_alpha": "1"}, format="json", **self._auth())
        assert res.status_code == 400, res.content

    def test_beta_out_of_range_is_rejected(self):
        res = self.client.patch(
            "/api/logistics/purchase-settings/current/",
            {"forecast_beta": "1.5"}, format="json", **self._auth())
        assert res.status_code == 400, res.content

    def test_alpha_within_range_is_accepted(self):
        res = self.client.patch(
            "/api/logistics/purchase-settings/current/",
            {"forecast_alpha": "0.5"}, format="json", **self._auth())
        assert res.status_code == 200, res.content

    def test_tenant_isolation_a_patch_never_touches_another_companys_settings(self):
        stranger = User.objects.create_user(username="knobs_stranger", password="x")
        other = create_company("شركة مقابض أخرى", stranger)

        res = self.client.patch(
            "/api/logistics/purchase-settings/current/",
            {"forecast_alpha": "0.90"}, format="json", **self._auth())
        assert res.status_code == 200, res.content

        other_row = PurchaseSettings.objects.filter(tenant=other).first()
        assert other_row is None or other_row.forecast_alpha == Decimal("0.25")
