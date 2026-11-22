"""Phase 8 (T-S2/T-S3): محرّك الإعدادات — حقل تنبيه التكرار + استعادة خريطة القيد.

`create_company` يبذر شجرة حسابات احترافية تلقائياً، فنعتمد عليها بدل إنشاء حسابات.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, TaxRate
from core.models import ActivityLog
from partners.models import Partner
from sales.models import SalesSettings
from sales.services import (
    COST_VARIANCE_RESOLVE_FAILED_ERROR,
    cost_variance_account_error,
    default_cost_variance_account_error,
    get_or_create_sales_settings,
    resolve_default_account,
    resolve_default_cost_variance_account,
)
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company


class SettingsEngineTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="seteng", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الإعدادات", cls.user)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_warn_on_duplicate_defaults_true_and_is_exposed(self):
        res = self.client.get("/api/sales/settings/current/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()["warn_on_duplicate_item"])

    def test_warn_on_duplicate_can_be_patched(self):
        res = self.client.patch(
            "/api/sales/settings/current/",
            {"warn_on_duplicate_item": False}, format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(res.json()["warn_on_duplicate_item"])
        self.assertFalse(SalesSettings.objects.get(tenant=self.tenant).warn_on_duplicate_item)

    def test_restore_defaults_maps_accounts_by_type(self):
        res = self.client.post("/api/sales/settings/restore-defaults/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        # كل الحسابات الأساسية أُعيد ضبطها (غير فارغة) ومن النوع الصحيح.
        for field, expected_type in [
            ("default_cash_account", "Asset"),
            ("default_revenue_account_product", "Revenue"),
            ("default_inventory_account", "Asset"),
            ("default_cogs_account", "Expense"),
        ]:
            self.assertIsNotNone(data[field], f"{field} لم يُحَل")
            acc = Account.objects.get(id=data[field])
            self.assertEqual(acc.account_type, expected_type, f"{field} → {acc.code} {acc.account_type}")


class SalesSettingsCogsCostMethodTest(APITestCase):
    """M1B-3a: إعداد طريقة تكلفة المبيعات وحساب الفروقات + التدقيق."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="cogs_set_owner", password="x")
        Currency.objects.get_or_create(Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True})
        cls.tenant = create_company("شركة إعدادات التكلفة", cls.user)

    def _auth(self, user=None, tenant=None):
        self.client.force_authenticate(user=user or self.user)
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).TenantID)}

    def _patch(self, payload, *, user=None, tenant=None):
        return self.client.patch(
            "/api/sales/settings/current/",
            payload, format="json", **self._auth(user=user, tenant=tenant),
        )

    def test_t1_patch_standard_without_variance_creates_5190_under_parent_of_51(self):
        cogs_51 = Account.objects.get(tenant=self.tenant, code="51")
        self.assertFalse(Account.objects.filter(tenant=self.tenant, parent=cogs_51).exists())

        res = self._patch({"cogs_cost_method": "standard"})
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertEqual(data["cogs_cost_method"], "standard")

        acc_5190 = Account.objects.get(tenant=self.tenant, code="5190")
        self.assertEqual(acc_5190.account_type, "Expense")
        self.assertIsNone(acc_5190.nature)
        self.assertTrue(acc_5190.is_active)
        self.assertEqual(acc_5190.name, "فروقات أسعار البضاعة المباعة")
        self.assertNotIn("تكلفة", acc_5190.name)
        self.assertEqual(acc_5190.parent_id, cogs_51.parent_id)
        # 51 لا يتحوّل إلى أب.
        self.assertFalse(Account.objects.filter(tenant=self.tenant, parent=cogs_51).exists())
        self.assertEqual(data["cost_variance_account"], acc_5190.id)
        self.assertEqual(data["cost_variance_account_name"], acc_5190.name)
        ss = SalesSettings.objects.get(tenant=self.tenant)
        self.assertEqual(ss.cogs_cost_method, "standard")
        self.assertEqual(ss.cost_variance_account_id, acc_5190.id)

    def test_t2_tenant_with_5101_under_51_creates_5190_under_51(self):
        other_user = User.objects.create_user(username="cogs_5101_owner", password="x")
        t2 = create_company("شركة 5101", other_user)
        acc_51 = Account.objects.get(tenant=t2, code="51")
        acc_5101 = Account.objects.create(
            tenant=t2, code="5101", name="تكلفة البضاعة المباعة",
            account_type="Expense", parent=acc_51, is_active=True,
        )
        # نُهيّئ الإعدادات بحيث يكون حساب التكلفة 5101.
        self.client.get("/api/sales/settings/current/", **self._auth(user=other_user, tenant=t2))
        ss = SalesSettings.objects.get(tenant=t2)
        ss.default_cogs_account = acc_5101
        ss.save(update_fields=["default_cogs_account"])

        res = self._patch({"cogs_cost_method": "last_purchase"}, user=other_user, tenant=t2)
        self.assertEqual(res.status_code, 200, res.content)
        acc_5190 = Account.objects.get(tenant=t2, code="5190")
        self.assertEqual(acc_5190.parent_id, acc_51.id)
        self.assertEqual(res.json()["cost_variance_account"], acc_5190.id)

    def test_t3_patch_twice_is_idempotent(self):
        res1 = self._patch({"cogs_cost_method": "standard"})
        self.assertEqual(res1.status_code, 200, res1.content)
        first_id = res1.json()["cost_variance_account"]

        res_clear = self._patch({"cogs_cost_method": "fifo", "cost_variance_account": None})
        self.assertEqual(res_clear.status_code, 200, res_clear.content)
        self.assertIsNone(res_clear.json()["cost_variance_account"])

        res2 = self._patch({"cogs_cost_method": "standard"})
        self.assertEqual(res2.status_code, 200, res2.content)
        self.assertEqual(Account.objects.filter(tenant=self.tenant, code="5190").count(), 1)
        self.assertEqual(res2.json()["cost_variance_account"], first_id)

    def test_t3b_existing_valid_5190_is_pinned_unchanged(self):
        self.client.get("/api/sales/settings/current/", **self._auth())
        acc_5 = Account.objects.get(tenant=self.tenant, code="5")
        existing_5190 = Account.objects.create(
            tenant=self.tenant,
            code="5190",
            name="فروقات قائمة صالحة",
            account_type="Expense",
            nature=None,
            parent=acc_5,
            is_active=True,
        )
        total_before = Account.objects.filter(tenant=self.tenant).count()

        res = self._patch({"cogs_cost_method": "standard"})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["cost_variance_account"], existing_5190.id)
        self.assertEqual(Account.objects.filter(tenant=self.tenant, code="5190").count(), 1)
        self.assertEqual(Account.objects.filter(tenant=self.tenant).count(), total_before)
        existing_5190.refresh_from_db()
        self.assertEqual(existing_5190.name, "فروقات قائمة صالحة")
        self.assertEqual(existing_5190.parent_id, acc_5.id)

    def test_t4_existing_invalid_5190_returns_400_without_changes(self):
        for label, bad_kwargs in [
            ("revenue", {"account_type": "Revenue", "nature": None}),
            ("debit_only", {"account_type": "Expense", "nature": Account.NATURE_DEBIT_ONLY}),
        ]:
            owner = User.objects.create_user(
                username=f"bad5190_{label}",
                password="x",
            )
            t = create_company("شركة 5190 فاسد", owner)
            self.client.get("/api/sales/settings/current/", **self._auth(user=owner, tenant=t))
            acc_5 = Account.objects.get(tenant=t, code="5")
            bad_acc = Account.objects.create(
                tenant=t, code="5190", name="حساب موجود", parent=acc_5, is_active=True, **bad_kwargs,
            )
            total_before = Account.objects.filter(tenant=t).count()
            res = self._patch({"cogs_cost_method": "standard"}, user=owner, tenant=t)
            self.assertEqual(res.status_code, 400, f"{label}: {res.content}")
            body = res.json()
            self.assertIn("cost_variance_account", body, f"{label}: {body}")
            self.assertIn("يدوياً", str(body["cost_variance_account"]), f"{label}: {body}")
            self.assertEqual(Account.objects.filter(tenant=t).count(), total_before)
            ss = SalesSettings.objects.get(tenant=t)
            self.assertEqual(ss.cogs_cost_method, "fifo")
            self.assertIsNone(ss.cost_variance_account_id)
            bad_acc.refresh_from_db()
            self.assertEqual(bad_acc.account_type, bad_kwargs["account_type"])
            self.assertEqual(bad_acc.nature, bad_kwargs["nature"])
            self.assertEqual(bad_acc.parent_id, acc_5.id)
            self.assertEqual(bad_acc.name, "حساب موجود")

        # موجود 5190 أب (له ابن)
        owner_p = User.objects.create_user(username="bad5190_parent", password="x")
        tp = create_company("شركة 5190 أب", owner_p)
        self.client.get("/api/sales/settings/current/", **self._auth(user=owner_p, tenant=tp))
        tp_5 = Account.objects.get(tenant=tp, code="5")
        parent_5190 = Account.objects.create(
            tenant=tp, code="5190", name="مجموعة 5190",
            account_type="Expense", parent=tp_5, is_active=True,
        )
        Account.objects.create(
            tenant=tp, code="51901", name="فرع",
            account_type="Expense", parent=parent_5190, is_active=True,
        )
        total_before_p = Account.objects.filter(tenant=tp).count()
        res = self._patch({"cogs_cost_method": "standard"}, user=owner_p, tenant=tp)
        self.assertEqual(res.status_code, 400, res.content)
        body_p = res.json()
        self.assertIn("cost_variance_account", body_p, body_p)
        self.assertIn("يدوياً", str(body_p["cost_variance_account"]), body_p)
        self.assertEqual(Account.objects.filter(tenant=tp).count(), total_before_p)
        ss_p = SalesSettings.objects.get(tenant=tp)
        self.assertEqual(ss_p.cogs_cost_method, "fifo")
        self.assertIsNone(ss_p.cost_variance_account_id)
        parent_5190.refresh_from_db()
        self.assertEqual(parent_5190.account_type, "Expense")
        self.assertIsNone(parent_5190.nature)
        self.assertEqual(parent_5190.parent_id, tp_5.id)
        self.assertEqual(parent_5190.name, "مجموعة 5190")

    def test_t5_explicit_valid_variance_account_is_saved_without_creating_5190(self):
        acc_5 = Account.objects.get(tenant=self.tenant, code="5")
        custom = Account.objects.create(
            tenant=self.tenant, code="5150", name="فروقات تكلفة مخصصة",
            account_type="Expense", parent=acc_5, is_active=True,
        )
        res = self._patch({
            "cogs_cost_method": "standard",
            "cost_variance_account": custom.id,
        })
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertEqual(data["cost_variance_account"], custom.id)
        self.assertEqual(data["cost_variance_account_name"], custom.name)
        self.assertFalse(Account.objects.filter(tenant=self.tenant, code="5190").exists())

    def test_t6_rejects_invalid_cost_variance_account(self):
        # تأكد أن الإعدادات منشأة بحساب التكلفة 51.
        self.client.get("/api/sales/settings/current/", **self._auth())
        acc_5 = Account.objects.get(tenant=self.tenant, code="5")
        acc_51 = Account.objects.get(tenant=self.tenant, code="51")

        other_owner = User.objects.create_user(username="other_t_owner", password="x")
        other_tenant = create_company("شركة أخرى", other_owner)
        foreign_acc = Account.objects.create(
            tenant=other_tenant, code="5150", name="أجنبي", account_type="Expense", is_active=True,
        )
        non_expense = Account.objects.get(tenant=self.tenant, code="4101")
        inactive_acc = Account.objects.create(
            tenant=self.tenant, code="5151", name="معطل",
            account_type="Expense", parent=acc_5, is_active=False,
        )
        parent_acc = Account.objects.create(
            tenant=self.tenant, code="5152", name="أب",
            account_type="Expense", parent=acc_5, is_active=True,
        )
        Account.objects.create(
            tenant=self.tenant, code="51521", name="ابن",
            account_type="Expense", parent=parent_acc, is_active=True,
        )
        credit_only = Account.objects.create(
            tenant=self.tenant, code="5153", name="دائن فقط",
            account_type="Expense", parent=acc_5, nature=Account.NATURE_CREDIT_ONLY, is_active=True,
        )
        outside_group = Account.objects.get(tenant=self.tenant, code="5201")

        nonexistent_pk = (Account.objects.order_by("-id").values_list("id", flat=True).first() or 0) + 1000
        missing_res = self._patch({"cost_variance_account": nonexistent_pk})
        self.assertEqual(missing_res.status_code, 400, missing_res.content)
        self.assertIn("cost_variance_account", missing_res.json(), missing_res.json())

        res_foreign = self._patch({"cost_variance_account": foreign_acc.id})
        self.assertEqual(res_foreign.status_code, 400, res_foreign.content)
        self.assertEqual(
            [m.replace(str(foreign_acc.id), "<PK>") for m in res_foreign.json()["cost_variance_account"]],
            [m.replace(str(nonexistent_pk), "<PK>") for m in missing_res.json()["cost_variance_account"]],
        )

        for label, bad_acc, expected_fragment in [
            ("non_expense", non_expense, "مصروفات"),
            ("inactive", inactive_acc, "نشطاً"),
            ("has_children", parent_acc, "ورقة"),
            ("credit_only", credit_only, "طبيعة"),
            ("equals_default_cogs", acc_51, "نفس حساب تكلفة"),
            ("outside_group", outside_group, "مجموعة"),
        ]:
            res = self._patch({"cost_variance_account": bad_acc.id})
            self.assertEqual(res.status_code, 400, f"{label}: {res.content}")
            body = res.json()
            self.assertIn("cost_variance_account", body, f"{label}: {body}")
            self.assertIn(expected_fragment, str(body["cost_variance_account"]), f"{label}: {body}")

        # غياب default_cogs_account يرفض تعيين حساب فروقات برسالة تطلب تعيينه أولاً.
        valid_5150 = Account.objects.create(
            tenant=self.tenant, code="5150", name="فروقات",
            account_type="Expense", parent=acc_5, is_active=True,
        )
        res_no_cogs = self._patch({
            "default_cogs_account": None,
            "cost_variance_account": valid_5150.id,
        })
        self.assertEqual(res_no_cogs.status_code, 400, res_no_cogs.content)
        self.assertIn("cost_variance_account", res_no_cogs.json(), res_no_cogs.json())
        self.assertIn(
            "عيّن حساب تكلفة المبيعات الافتراضي أولاً",
            str(res_no_cogs.json()["cost_variance_account"]),
        )

    def test_t7_fifo_without_variance_account_creates_nothing(self):
        res = self._patch({"cogs_cost_method": "fifo"})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIsNone(res.json()["cost_variance_account"])
        self.assertFalse(Account.objects.filter(tenant=self.tenant, code="5190").exists())

    def test_t8_clearing_variance_account_while_standard_repins_default(self):
        acc_5 = Account.objects.get(tenant=self.tenant, code="5")
        custom = Account.objects.create(
            tenant=self.tenant, code="5150", name="مخصص",
            account_type="Expense", parent=acc_5, is_active=True,
        )
        res1 = self._patch({"cogs_cost_method": "standard", "cost_variance_account": custom.id})
        self.assertEqual(res1.status_code, 200, res1.content)
        self.assertEqual(res1.json()["cost_variance_account"], custom.id)

        res2 = self._patch({"cost_variance_account": None})
        self.assertEqual(res2.status_code, 200, res2.content)
        acc_5190 = Account.objects.get(tenant=self.tenant, code="5190")
        self.assertEqual(res2.json()["cost_variance_account"], acc_5190.id)
        self.assertEqual(
            SalesSettings.objects.get(tenant=self.tenant).cost_variance_account_id,
            acc_5190.id,
        )

    def test_t9_audit_logs_cogs_changes_and_skips_unrelated_patch(self):
        self.client.get("/api/sales/settings/current/", **self._auth())
        ss = SalesSettings.objects.get(tenant=self.tenant)

        res = self._patch({"cogs_cost_method": "standard"})
        self.assertEqual(res.status_code, 200, res.content)
        logs = ActivityLog.objects.filter(
            tenant=self.tenant, entity_type="sales_settings", action="update",
        )
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.entity_id, ss.pk)
        self.assertEqual(log.entity_label, "إعدادات المبيعات")
        changes = log.metadata.get("changes")
        self.assertEqual(len(changes), 2)
        by_field = {c["field"]: c for c in changes}
        self.assertEqual(by_field["cogs_cost_method"], {
            "field": "cogs_cost_method",
            "label": "طريقة تكلفة المبيعات",
            "old": "الوارد أولاً صادر أولاً (FIFO)",
            "new": "تكلفة معيارية للمنتج",
        })
        self.assertEqual(by_field["cost_variance_account"], {
            "field": "cost_variance_account",
            "label": "حساب فروقات تكلفة المبيعات",
            "old": "",
            "new": "5190 — فروقات أسعار البضاعة المباعة",
        })

        # تعديل لا يمسّ الطريقة أو حساب الفروقات لا يكتب سجلّاً.
        res_other = self._patch({"warn_on_duplicate_item": False})
        self.assertEqual(res_other.status_code, 200, res_other.content)
        self.assertEqual(
            ActivityLog.objects.filter(tenant=self.tenant, entity_type="sales_settings").count(),
            1,
        )

    def test_t10_user_without_settings_manage_perm_gets_403(self):
        seller = User.objects.create_user(username="seller_no_settings_perm", password="x")
        UserCompanyMembership.objects.create(user=seller, tenant=self.tenant, role="sales")
        res = self._patch({"cogs_cost_method": "standard"}, user=seller)
        self.assertEqual(res.status_code, 403, res.content)
        self.assertEqual(SalesSettings.objects.get(tenant=self.tenant).cogs_cost_method, "fifo")

    def test_f1_unrelated_patch_succeeds_after_stored_variance_account_deactivated(self):
        res1 = self._patch({"cogs_cost_method": "standard"})
        self.assertEqual(res1.status_code, 200, res1.content)
        variance_id = res1.json()["cost_variance_account"]
        Account.objects.filter(pk=variance_id).update(is_active=False)

        res_unrelated = self._patch({"default_payment_type": SalesSettings.PAYMENT_CASH})
        self.assertEqual(res_unrelated.status_code, 200, res_unrelated.content)
        self.assertEqual(
            SalesSettings.objects.get(tenant=self.tenant).default_payment_type,
            SalesSettings.PAYMENT_CASH,
        )

        # تغيير حقل COGS فعلاً لا يزال يشغّل التحقّق فيرفض الحساب المعطَّل.
        res_cogs = self._patch({"cogs_cost_method": "last_purchase"})
        self.assertEqual(res_cogs.status_code, 400, res_cogs.content)
        self.assertIn("cost_variance_account", res_cogs.json())
        self.assertIn("نشطاً", str(res_cogs.json()["cost_variance_account"]))
        self.assertEqual(SalesSettings.objects.get(tenant=self.tenant).cogs_cost_method, "standard")

    def test_g1_save_with_unchanged_default_cogs_account_succeeds_when_stored_variance_inactive(self):
        res1 = self._patch({"cogs_cost_method": "standard"})
        self.assertEqual(res1.status_code, 200, res1.content)
        ss = SalesSettings.objects.get(tenant=self.tenant)
        variance_id = ss.cost_variance_account_id
        cogs_id = ss.default_cogs_account_id
        Account.objects.filter(pk=variance_id).update(is_active=False)

        res = self._patch({
            "default_cogs_account": cogs_id,
            "default_payment_type": SalesSettings.PAYMENT_CASH,
        })
        self.assertEqual(res.status_code, 200, res.content)
        ss.refresh_from_db()
        self.assertEqual(ss.default_payment_type, SalesSettings.PAYMENT_CASH)
        self.assertEqual(ss.cost_variance_account_id, variance_id)
        self.assertEqual(ss.cogs_cost_method, "standard")

    def test_g1_patch_with_unchanged_cogs_cost_method_succeeds_when_stored_variance_inactive(self):
        res1 = self._patch({"cogs_cost_method": "standard"})
        self.assertEqual(res1.status_code, 200, res1.content)
        variance_id = res1.json()["cost_variance_account"]
        Account.objects.filter(pk=variance_id).update(is_active=False)

        res = self._patch({"cogs_cost_method": "standard"})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(SalesSettings.objects.get(tenant=self.tenant).cogs_cost_method, "standard")

    def test_g2_accepts_avco_cogs_cost_method_and_audits_it(self):
        self.client.get("/api/sales/settings/current/", **self._auth())
        self.assertEqual(SalesSettings.objects.get(tenant=self.tenant).cogs_cost_method, "fifo")
        res = self._patch({"cogs_cost_method": "avco"})
        self.assertEqual(res.status_code, 200, res.content)
        settings = SalesSettings.objects.get(tenant=self.tenant)
        self.assertEqual(settings.cogs_cost_method, "avco")
        self.assertIsNone(settings.cost_variance_account_id)
        logs = ActivityLog.objects.filter(
            tenant=self.tenant, entity_type="sales_settings", action="update",
        )
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().metadata["changes"], [{
            "field": "cogs_cost_method",
            "label": "طريقة تكلفة المبيعات",
            "old": "الوارد أولاً صادر أولاً (FIFO)",
            "new": "متوسط مرجّح بالكميّة (AVCO)",
        }])

    def test_g3_standard_without_default_cogs_account_returns_400_and_creates_nothing(self):
        owner = User.objects.create_user(username="g3_no_cogs_owner", password="x")
        t = create_company("شركة بلا حساب تكلفة", owner)
        # نعطّل 51 كي لا يعيد get_or_create_sales_settings تعبئة default_cogs_account تلقائياً.
        Account.objects.filter(tenant=t, code="51").update(is_active=False)
        self.client.get("/api/sales/settings/current/", **self._auth(user=owner, tenant=t))
        ss = SalesSettings.objects.get(tenant=t)
        self.assertEqual(ss.cogs_cost_method, "fifo")
        self.assertIsNone(ss.default_cogs_account_id)
        self.assertIsNone(ss.cost_variance_account_id)
        count_before = Account.objects.filter(tenant=t).count()

        res = self._patch({"cogs_cost_method": "standard"}, user=owner, tenant=t)
        self.assertEqual(res.status_code, 400, res.content)
        body = res.json()
        self.assertIn("cost_variance_account", body, body)
        self.assertIn("يدوياً", str(body["cost_variance_account"]), body)
        self.assertEqual(Account.objects.filter(tenant=t).count(), count_before)
        self.assertEqual(SalesSettings.objects.get(tenant=t).cogs_cost_method, "fifo")

    def test_f2_rejects_other_tenant_default_cogs_account_on_patch_and_creates_nothing(self):
        self.client.get("/api/sales/settings/current/", **self._auth())
        other_owner = User.objects.create_user(username="other_cogs_owner", password="x")
        other_tenant = create_company("شركة تكلفة أجنبية", other_owner)
        foreign_cogs = Account.objects.get(tenant=other_tenant, code="51")

        self_count_before = Account.objects.filter(tenant=self.tenant).count()
        other_count_before = Account.objects.filter(tenant=other_tenant).count()

        res = self._patch({
            "default_cogs_account": foreign_cogs.id,
            "cogs_cost_method": "standard",
        })
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("default_cogs_account", res.json(), res.json())
        self.assertEqual(Account.objects.filter(tenant=self.tenant).count(), self_count_before)
        self.assertEqual(Account.objects.filter(tenant=other_tenant).count(), other_count_before)
        self.assertEqual(SalesSettings.objects.get(tenant=self.tenant).cogs_cost_method, "fifo")

    def test_f2_service_rejects_other_tenant_default_cogs_account(self):
        ss = get_or_create_sales_settings(self.tenant)
        other_owner = User.objects.create_user(username="other_svc_cogs_owner", password="x")
        other_tenant = create_company("شركة خدمة أجنبية", other_owner)
        foreign_cogs = Account.objects.get(tenant=other_tenant, code="51")
        total_before = Account.objects.count()

        resolved = resolve_default_cost_variance_account(ss, default_cogs_account=foreign_cogs)
        self.assertIsNone(resolved)
        self.assertEqual(Account.objects.count(), total_before)

        local_5150 = Account.objects.create(
            tenant=self.tenant, code="5150", name="فروقات محلية",
            account_type="Expense", parent=Account.objects.get(tenant=self.tenant, code="5"),
            is_active=True,
        )
        self.assertIsNotNone(
            cost_variance_account_error(
                local_5150, tenant_id=self.tenant.TenantID, default_cogs_account=foreign_cogs,
            )
        )


class SalesSettingsTenantScopeTest(APITestCase):
    """SEC-SETTINGS-FK: عزل الفهارس الأجنبية وصلاحية restore-defaults وفحص حساب الفروقات."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="sec_set_owner", password="x")
        Currency.objects.get_or_create(Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True})
        cls.tenant = create_company("شركة أمان الإعدادات", cls.user)

    def _auth(self, user=None, tenant=None):
        self.client.force_authenticate(user=user or self.user)
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).TenantID)}

    def _patch(self, payload, *, user=None, tenant=None):
        return self.client.patch(
            "/api/sales/settings/current/",
            payload, format="json", **self._auth(user=user, tenant=tenant),
        )

    def _post_restore(self, *, user=None, tenant=None):
        return self.client.post(
            "/api/sales/settings/restore-defaults/",
            {}, format="json", **self._auth(user=user, tenant=tenant),
        )

    @staticmethod
    def _account_snapshot(ss):
        return (
            ss.default_cash_account_id,
            ss.default_ar_account_id,
            ss.default_revenue_account_product_id,
            ss.default_revenue_account_service_id,
            ss.default_inventory_account_id,
            ss.default_cogs_account_id,
            ss.cost_variance_account_id,
        )

    def test_sec_s1_patch_rejects_foreign_tenant_fk_fields(self):
        self.client.get("/api/sales/settings/current/", **self._auth())
        other_owner = User.objects.create_user(username="sec_other_owner", password="x")
        other_tenant = create_company("شركة أجنبية للإعدادات", other_owner)

        foreign_partner = Partner.objects.create(
            tenant=other_tenant, name="عميل شركة أخرى", partner_type="Customer",
        )
        foreign_asset = Account.objects.create(
            tenant=other_tenant, code="9101", name="أصل أجنبي",
            account_type="Asset", is_active=True,
        )
        foreign_rev = Account.objects.create(
            tenant=other_tenant, code="9401", name="إيراد أجنبي",
            account_type="Revenue", is_active=True,
        )
        foreign_vat_acc = Account.objects.create(
            tenant=other_tenant, code="9204", name="ضريبة أجنبية",
            account_type="Liability", is_active=True,
        )
        foreign_tax = TaxRate.objects.create(
            tenant=other_tenant, code="FVAT16", name="ضريبة أجنبية 16%",
            rate=Decimal("16.00"), tax_account=foreign_vat_acc,
            direction="sales", is_active=True,
        )

        foreign_targets = [
            ("default_customer", foreign_partner.id),
            ("default_revenue_account_product", foreign_rev.id),
            ("default_revenue_account_service", foreign_rev.id),
            ("default_cash_account", foreign_asset.id),
            ("default_inventory_account", foreign_asset.id),
            ("default_ar_account", foreign_asset.id),
            ("vat_input_account", foreign_asset.id),
            ("default_vat_rate", foreign_tax.id),
        ]

        for field, foreign_pk in foreign_targets:
            with self.subTest(field=field):
                before_id = getattr(SalesSettings.objects.get(tenant=self.tenant), f"{field}_id")
                res = self._patch({field: foreign_pk})
                self.assertEqual(res.status_code, 400, f"{field}: {res.content}")
                self.assertIn(field, res.json(), f"{field}: {res.json()}")
                self.assertEqual(res.data[field][0].code, "does_not_exist", f"{field}: {res.data}")
                after_id = getattr(SalesSettings.objects.get(tenant=self.tenant), f"{field}_id")
                self.assertEqual(after_id, before_id, f"{field} تغيّر رغم الرفض")

    def test_sec_s2_patch_accepts_same_company_customer_and_vat_rate(self):
        self.client.get("/api/sales/settings/current/", **self._auth())
        local_customer = Partner.objects.create(
            tenant=self.tenant, name="عميل محلي", partner_type="Customer",
        )
        vat_acc = Account.objects.get(tenant=self.tenant, code="2104")
        local_tax = TaxRate.objects.create(
            tenant=self.tenant, code="LVAT16", name="ضريبة محلية 16%",
            rate=Decimal("16.00"), tax_account=vat_acc,
            direction="sales", is_active=True,
        )
        res = self._patch({
            "default_customer": local_customer.id,
            "default_vat_rate": local_tax.id,
        })
        self.assertEqual(res.status_code, 200, res.content)
        ss = SalesSettings.objects.get(tenant=self.tenant)
        self.assertEqual(ss.default_customer_id, local_customer.id)
        self.assertEqual(ss.default_vat_rate_id, local_tax.id)

    def test_sec_s3_restore_defaults_requires_settings_manage_permission(self):
        ss = get_or_create_sales_settings(self.tenant)
        SalesSettings.objects.filter(pk=ss.pk).update(
            default_cash_account=None,
            default_cogs_account=None,
        )
        ss.refresh_from_db()
        before_snapshot = self._account_snapshot(ss)

        seller = User.objects.create_user(username="sec_seller_no_perm", password="x")
        UserCompanyMembership.objects.create(user=seller, tenant=self.tenant, role="sales")
        res = self._post_restore(user=seller)
        self.assertEqual(res.status_code, 403, res.content)

        ss.refresh_from_db()
        after_snapshot = self._account_snapshot(ss)
        self.assertEqual(after_snapshot, before_snapshot)

    def test_sec_s4_restore_defaults_standard_replaces_invalid_variance_and_logs(self):
        ss = get_or_create_sales_settings(self.tenant)
        expected_cogs = resolve_default_account(
            self.tenant.TenantID, ["5101"], "Expense", "تكلفة", allow_parent=False,
        )
        self.assertIsNotNone(expected_cogs)
        SalesSettings.objects.filter(pk=ss.pk).update(
            cogs_cost_method="standard",
            cost_variance_account=expected_cogs,
        )
        ActivityLog.objects.filter(tenant=self.tenant, entity_type="sales_settings").delete()

        res = self._post_restore()
        self.assertEqual(res.status_code, 200, res.content)

        ss.refresh_from_db()
        self.assertEqual(ss.default_cogs_account_id, expected_cogs.id)
        self.assertIsNotNone(ss.cost_variance_account_id)
        self.assertNotEqual(ss.cost_variance_account_id, ss.default_cogs_account_id)
        self.assertIsNone(
            cost_variance_account_error(
                ss.cost_variance_account,
                tenant_id=self.tenant.TenantID,
                default_cogs_account=ss.default_cogs_account,
            )
        )

        logs = ActivityLog.objects.filter(
            tenant=self.tenant, entity_type="sales_settings", action="update",
        )
        self.assertEqual(logs.count(), 1)
        changes = logs.first().metadata.get("changes") or []
        by_field = {c["field"]: c for c in changes}
        self.assertIn("cost_variance_account", by_field)
        self.assertIn(expected_cogs.code, by_field["cost_variance_account"]["old"])
        self.assertIn(ss.cost_variance_account.code, by_field["cost_variance_account"]["new"])

    def test_sec_s5_restore_defaults_fifo_clears_invalid_variance_account(self):
        ss = get_or_create_sales_settings(self.tenant)
        expected_cogs = resolve_default_account(
            self.tenant.TenantID, ["5101"], "Expense", "تكلفة", allow_parent=False,
        )
        self.assertIsNotNone(expected_cogs)
        SalesSettings.objects.filter(pk=ss.pk).update(
            cogs_cost_method="fifo",
            cost_variance_account=expected_cogs,
        )
        ActivityLog.objects.filter(tenant=self.tenant, entity_type="sales_settings").delete()

        res = self._post_restore()
        self.assertEqual(res.status_code, 200, res.content)
        ss.refresh_from_db()
        self.assertIsNone(ss.cost_variance_account_id)
        logs = ActivityLog.objects.filter(
            tenant=self.tenant, entity_type="sales_settings", action="update",
        )
        self.assertEqual(logs.count(), 1)
        changes = logs.first().metadata.get("changes") or []
        by_field = {c["field"]: c for c in changes}
        self.assertIn("cost_variance_account", by_field)
        self.assertEqual(by_field["cost_variance_account"]["new"], "")

    def test_sec_s5b_restore_defaults_avco_clears_invalid_variance_account(self):
        ss = get_or_create_sales_settings(self.tenant)
        expected_cogs = resolve_default_account(
            self.tenant.TenantID, ["5101"], "Expense", "تكلفة", allow_parent=False,
        )
        self.assertIsNotNone(expected_cogs)
        SalesSettings.objects.filter(pk=ss.pk).update(
            cogs_cost_method="avco",
            cost_variance_account=expected_cogs,
        )
        ActivityLog.objects.filter(tenant=self.tenant, entity_type="sales_settings").delete()

        res = self._post_restore()
        self.assertEqual(res.status_code, 200, res.content)
        ss.refresh_from_db()
        self.assertEqual(ss.cogs_cost_method, "avco")
        self.assertIsNone(ss.cost_variance_account_id)
        logs = ActivityLog.objects.filter(
            tenant=self.tenant, entity_type="sales_settings", action="update",
        )
        self.assertEqual(logs.count(), 1)
        changes = logs.first().metadata.get("changes") or []
        by_field = {c["field"]: c for c in changes}
        self.assertIn("cost_variance_account", by_field)
        self.assertEqual(by_field["cost_variance_account"]["new"], "")

    def test_sec_s6_restore_defaults_standard_keeps_valid_variance_without_log(self):
        ss = get_or_create_sales_settings(self.tenant)
        acc_5 = Account.objects.get(tenant=self.tenant, code="5")
        valid_variance = Account.objects.create(
            tenant=self.tenant, code="5155", name="فروقات تكلفة صالحة",
            account_type="Expense", parent=acc_5, is_active=True,
        )
        SalesSettings.objects.filter(pk=ss.pk).update(
            cogs_cost_method="standard",
            cost_variance_account=valid_variance,
        )
        ActivityLog.objects.filter(tenant=self.tenant, entity_type="sales_settings").delete()

        res = self._post_restore()
        self.assertEqual(res.status_code, 200, res.content)
        ss.refresh_from_db()
        self.assertEqual(ss.cost_variance_account_id, valid_variance.id)
        self.assertEqual(
            ActivityLog.objects.filter(tenant=self.tenant, entity_type="sales_settings").count(),
            0,
        )

    def test_sec_s7_restore_defaults_standard_400_and_saves_nothing_when_default_variance_ineligible(self):
        ss = get_or_create_sales_settings(self.tenant)
        acc_5 = Account.objects.get(tenant=self.tenant, code="5")
        Account.objects.create(
            tenant=self.tenant, code="5190", name="حساب 5190 معطل",
            account_type="Expense", parent=acc_5, is_active=False,
        )
        acc_4 = Account.objects.get(tenant=self.tenant, code="4")
        custom_rev = Account.objects.create(
            tenant=self.tenant, code="4199", name="إيراد مخصص",
            account_type="Revenue", parent=acc_4, is_active=True,
        )
        SalesSettings.objects.filter(pk=ss.pk).update(
            default_cash_account=None,
            default_ar_account=None,
            default_revenue_account_product=custom_rev,
            default_revenue_account_service=None,
            default_inventory_account=None,
            default_cogs_account=None,
            cost_variance_account=None,
            cogs_cost_method="standard",
        )
        ss.refresh_from_db()
        before_accounts = self._account_snapshot(ss)
        account_count_before = Account.objects.filter(tenant=self.tenant).count()
        ActivityLog.objects.filter(tenant=self.tenant, entity_type="sales_settings").delete()

        resolved_cogs = resolve_default_account(
            self.tenant.TenantID, ["5101"], "Expense", "تكلفة", allow_parent=False,
        )
        expected_err = default_cost_variance_account_error(
            resolved_cogs, tenant_id=self.tenant.TenantID,
        )
        self.assertIsNotNone(expected_err)
        self.assertNotEqual(expected_err, COST_VARIANCE_RESOLVE_FAILED_ERROR)

        res = self._post_restore()
        self.assertEqual(res.status_code, 400, res.content)
        body = res.json()
        self.assertIn("cost_variance_account", body, body)
        self.assertEqual(body["cost_variance_account"], [expected_err])

        ss.refresh_from_db()
        after_accounts = self._account_snapshot(ss)
        self.assertEqual(after_accounts, before_accounts)
        # حارس انحدار: الفحص المحدّد (`default_cost_variance_account_error`) يرفض `5190` المعطّل قبل بلوغ المحلّل، فلا يُنشأ حساب اليوم.
        self.assertEqual(Account.objects.filter(tenant=self.tenant).count(), account_count_before)
        self.assertEqual(
            ActivityLog.objects.filter(tenant=self.tenant, entity_type="sales_settings").count(),
            0,
        )

    def test_sec_s8_restore_defaults_last_purchase_replaces_invalid_variance_and_logs(self):
        ss = get_or_create_sales_settings(self.tenant)
        expected_cogs = resolve_default_account(
            self.tenant.TenantID, ["5101"], "Expense", "تكلفة", allow_parent=False,
        )
        self.assertIsNotNone(expected_cogs)
        SalesSettings.objects.filter(pk=ss.pk).update(
            cogs_cost_method="last_purchase",
            cost_variance_account=expected_cogs,
        )
        ActivityLog.objects.filter(tenant=self.tenant, entity_type="sales_settings").delete()

        res = self._post_restore()
        self.assertEqual(res.status_code, 200, res.content)

        ss.refresh_from_db()
        self.assertEqual(ss.default_cogs_account_id, expected_cogs.id)
        self.assertIsNotNone(ss.cost_variance_account_id)
        self.assertNotEqual(ss.cost_variance_account_id, ss.default_cogs_account_id)
        self.assertIsNone(
            cost_variance_account_error(
                ss.cost_variance_account,
                tenant_id=self.tenant.TenantID,
                default_cogs_account=ss.default_cogs_account,
            )
        )

        logs = ActivityLog.objects.filter(
            tenant=self.tenant, entity_type="sales_settings", action="update",
        )
        self.assertEqual(logs.count(), 1)
        changes = logs.first().metadata.get("changes") or []
        by_field = {c["field"]: c for c in changes}
        self.assertIn("cost_variance_account", by_field)
        self.assertIn(expected_cogs.code, by_field["cost_variance_account"]["old"])
        self.assertIn(ss.cost_variance_account.code, by_field["cost_variance_account"]["new"])


class SalesSettingsProductPriceColumnTest(APITestCase):
    """M3-COGS: إعداد عمود السعر الأساسي في جدول المنتجات."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="price_col_owner", password="x")
        Currency.objects.get_or_create(Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True})
        cls.tenant = create_company("شركة عمود السعر", cls.user)

    def _auth(self, user=None, tenant=None):
        self.client.force_authenticate(user=user or self.user)
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).TenantID)}

    def test_product_price_column_defaults_to_last_purchase(self):
        res = self.client.get("/api/sales/settings/current/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["product_price_column"], "last_purchase")

    def test_product_price_column_patch_persists_and_rejects_unknown_value(self):
        res = self.client.patch(
            "/api/sales/settings/current/",
            {"product_price_column": "inventory_avg"},
            format="json",
            **self._auth(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["product_price_column"], "inventory_avg")
        self.assertEqual(
            SalesSettings.objects.get(tenant=self.tenant).product_price_column,
            "inventory_avg",
        )

        bad = self.client.patch(
            "/api/sales/settings/current/",
            {"product_price_column": "bogus"},
            format="json",
            **self._auth(),
        )
        self.assertEqual(bad.status_code, 400, bad.content)
        self.assertIn("product_price_column", bad.json())

    def test_product_price_column_requires_manage_perm_and_writes_no_cogs_audit_row(self):
        seller = User.objects.create_user(username="price_col_seller", password="x")
        UserCompanyMembership.objects.create(user=seller, tenant=self.tenant, role="sales")
        denied = self.client.patch(
            "/api/sales/settings/current/",
            {"product_price_column": "standard"},
            format="json",
            **self._auth(user=seller),
        )
        self.assertEqual(denied.status_code, 403, denied.content)
        self.assertEqual(
            SalesSettings.objects.get(tenant=self.tenant).product_price_column,
            "last_purchase",
        )

        res = self.client.patch(
            "/api/sales/settings/current/",
            {"product_price_column": "method_cost"},
            format="json",
            **self._auth(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            ActivityLog.objects.filter(
                tenant=self.tenant, entity_type="sales_settings",
            ).count(),
            0,
        )
