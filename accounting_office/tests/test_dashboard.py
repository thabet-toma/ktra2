"""لوحة صاحب المكتب — #289.

**ما يثبته هذا الملف:**

1. **`due_total` = مجموعُ `payments.client_due`** لزباين المكتب المرئيّين — لا
   صيغةَ مبلغٍ ثانيةً في اللوحة.
2. **المحاسبُ يُرفَض 403 من الخادم** على النقطتين: قراءةِ اللوحة وتحويلِ الزبون.
3. **القناع**: بلا `office.amounts.view` المبلغُ `null` (والواجهة ترسم «—»).
4. **الاحمرارُ بعتبةٍ من السجلّ** لا بثابتٍ مكتوب: موظّفٌ بـ3 متأخّرين من 10
   زباين يحمرّ بالعتبة الافتراضية (20٪ و1.5)، وموظّفٌ بـ1 من 10 لا يحمرّ.
5. **مكتبُ شخصٍ واحدٍ ⇒ `single_person=True`** فلا جدولَ موظفين في الواجهة.
6. **«اعتمد الكل» من «بانتظارك» يعتمد المسودّات فعلاً** — لا يعدّها فقط.
7. **التحويلُ `{responsible}`**: ينجح للمدير، ويُرفض لعضوٍ ليس بدور مكتب،
   ويُسجَّل حدثاً في سجلّ النشاط.
8. **`late` عددُ الزبائن المتأخّرين لا الالتزامات**: زبونٌ واحدٌ بالتزامين من
   عشرة لا يُحمرّ صفَّ مسؤوله، وثلاثةُ زبائن من عشرة يُحمرّونه؛ والمتوسطُ من
   العدد نفسه، و`late_total` يبقى عددَ الالتزامات.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting_office import dashboard, fee_invoices, fees, payments, services
from accounting_office.models import (
    OFFICE_ALERT_KIND_SCHEDULE_DATES_CHANGED,
    DeadlineRule,
    FeeDraft,
    FeeSubscription,
    OfficeAlert,
    OfficeClient,
)
from accounting_office.tests.test_alerts import (
    add_obligation_row,
    office_client_without_periods,
)
from accounting_office.tests.test_obligations import (
    catalog,
    ready_office,
    seed_deadline_schedules,
    seed_published_thresholds,
)
from core.models import ActivityLog
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
DASHBOARD = f"{BASE}dashboard/"
CLIENTS = f"{BASE}clients/"
DRAFTS = f"{BASE}fees/drafts/"
SETTINGS = f"{BASE}settings/"

#: يومُ القياس الصريح — التأخيرُ يُحسب عنه لا عن ساعة التشغيل.
DAY = datetime.date(2026, 2, 12)
MAR_FIRST = datetime.date(2026, 3, 1)

#: 10 زبائنَ لكل موظّف: 3 متأخّرين لصاحب الأول وواحدٌ لصاحب الثاني — الأرقام
#: التي تُثبت الاحمرار وعدمَه بالعتبة الافتراضية.
CLIENTS_PER_EMPLOYEE = 10
LATE_FOR_FIRST = 3
LATE_FOR_SECOND = 1


class OfficeDashboardTestCase(APITestCase):
    """مكتبٌ بزبائن: صاحبُ المكتب، ومحاسبان بعشرة زبائنَ لكلٍّ، وقارئ."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        cls.owner = User.objects.create_user(username="dash_owner", password="x")
        cls.tenant = create_company(
            "مكتب اللوحة", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        # #292: قياسُ مجموع «اللي عليه» لا حسابَ ضريبة الورقة — بلا ضريبةٍ تبقى
        # أرقامُ الاختبار (100/250/400) كما هي، ونظيرُ المسار بالضريبة في
        # `test_fee_due_vat.py`.
        services.set_office_setting(cls.tenant, "office_licensed_dealer", False)
        catalog(cls.tenant)
        cls.currency = Currency.objects.get(Code="ILS")

        def member(username, role):
            user = User.objects.create_user(username=username, password="x")
            UserCompanyMembership.objects.create(
                user=user, tenant=cls.tenant, role=role,
            )
            return user

        cls.accountant = member("dash_accountant", "accountant")
        cls.colleague = member("dash_colleague", "accountant")
        cls.reader = member("dash_reader", "viewer")
        cls.rule = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_vat_periodic",
        )

        # زبائنُ الموظفين: عشرةٌ لكلٍّ، ثم التزاماتٌ متأخّرةٌ على أوّل ما فيها.
        cls.first_clients = [
            office_client_without_periods(
                cls.tenant, f"زبون أول {index}", responsible=cls.accountant,
            )
            for index in range(CLIENTS_PER_EMPLOYEE)
        ]
        cls.second_clients = [
            office_client_without_periods(
                cls.tenant, f"زبون ثانٍ {index}", responsible=cls.colleague,
            )
            for index in range(CLIENTS_PER_EMPLOYEE)
        ]
        for client in cls.first_clients[:LATE_FOR_FIRST]:
            cls._late_obligation(client)
        for client in cls.second_clients[:LATE_FOR_SECOND]:
            cls._late_obligation(client)

    @classmethod
    def _late_obligation(cls, client):
        """التزامٌ تجاوز موعده الرسميّ وشغلتُه لم تتجاوز موعدها الداخليّ.

        فالصفُّ **أحمر** وحدَه: شغلةٌ داخليّةٌ متأخّرةٌ كانت ستُضاعف عدّ المتأخّر
        فيُحمرّ الموظّفُ ذو المتأخّر الواحد بلا سبب.
        """
        return add_obligation_row(
            tenant=cls.tenant,
            client=client,
            rule=cls.rule,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY + datetime.timedelta(days=20),
        )

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def payload(self, user=None):
        return dashboard.dashboard_payload(
            self.tenant, user=user or self.owner, day=DAY,
        )

    def staff_row(self, payload, user):
        return next(
            row for row in payload["staff"] if row["id"] == user.pk
        )

    def approved_draft(self, client, total, *, year=2026, month=1):
        draft = FeeDraft.objects.create(
            tenant=self.tenant,
            client=client,
            year=year,
            month=month,
            subtotal=Decimal(total),
            total=Decimal(total),
            status=FeeDraft.STATUS_APPROVED,
            approved_by=self.owner,
        )
        # #292: «اللي عليه» يُقرأ من الورقة الصادرة، والاعتمادُ في الإنتاج يُصدرها
        # في المعاملة نفسها — والترخيصُ مطفأً هنا فإجماليُها = مجموعُ المسودّة.
        fee_invoices.issue_for_draft(draft, actor=self.owner)
        return draft


class DueTotalTest(OfficeDashboardTestCase):
    """`due_total` من الدالّة الواحدة — لا صيغةَ ثانية."""

    def test_due_total_equals_the_sum_of_client_due_over_visible_clients(self):
        self.approved_draft(self.first_clients[0], "100.00")
        self.approved_draft(self.first_clients[1], "250.00")
        self.approved_draft(self.second_clients[0], "400.00")
        # دفعةٌ تُسقِط جزءاً من فاتورة: `due` مشتقٌّ لا مجموعُ `total`.
        payments.create_payment(
            self.tenant,
            self.first_clients[0],
            amount="40.00",
            method="cash",
            paid_at=datetime.date(2026, 2, 1),
            actor=self.owner,
        )

        visible = OfficeClient.objects.filter(tenant=self.tenant)
        expected = sum(
            due.due for due in payments.client_due_map(self.tenant, visible).values()
        )
        self.assertEqual(expected, Decimal("710.00"))

        self.as_user(self.owner)
        res = self.client.get(DASHBOARD, **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(Decimal(str(res.data["due_total"])), expected)

    def test_due_total_is_zero_when_the_office_owes_nothing(self):
        self.as_user(self.owner)
        res = self.client.get(DASHBOARD, **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(Decimal(str(res.data["due_total"])), Decimal("0.00"))


class RoleGateTest(OfficeDashboardTestCase):
    """**دورٌ لا مفتاح**: المحاسبُ يعمل في المكتب وليس له لوحةُ صاحبه."""

    def test_the_accountant_is_refused_the_dashboard_by_the_server(self):
        self.as_user(self.accountant)
        res = self.client.get(DASHBOARD, **self.headers())
        self.assertEqual(res.status_code, 403, res.content)

    def test_the_accountant_is_refused_the_transfer_by_the_server(self):
        self.as_user(self.accountant)
        res = self.client.post(
            f"{CLIENTS}{self.first_clients[0].pk}/assign/",
            {"responsible": self.colleague.pk},
            format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, 403, res.content)

    def test_the_reader_is_refused_the_dashboard_too(self):
        self.as_user(self.reader)
        res = self.client.get(DASHBOARD, **self.headers())
        self.assertEqual(res.status_code, 403, res.content)

    def test_the_owner_reads_it(self):
        self.as_user(self.owner)
        self.assertEqual(
            self.client.get(DASHBOARD, **self.headers()).status_code, 200,
        )


class AmountMaskTest(OfficeDashboardTestCase):
    """بلا `office.amounts.view` المبلغُ `null` — بالمفتاح نفسه لا محذوفاً."""

    def test_the_total_is_masked_for_a_member_without_the_key(self):
        self.approved_draft(self.first_clients[0], "100.00")
        self.assertIsNone(self.payload(user=self.accountant)["due_total"])
        self.assertIsNotNone(self.payload(user=self.owner)["due_total"])

    def test_the_masked_payload_keeps_the_key(self):
        masked = self.payload(user=self.accountant)
        self.assertIn("due_total", masked)
        self.assertIsNone(masked["due_total"])


class RedRowTest(OfficeDashboardTestCase):
    """الاحمرارُ بعتبةٍ من السجلّ: النسبةُ **أو** مضاعفُ متوسط المكتب."""

    def test_three_late_of_ten_clients_turns_the_row_red_by_default(self):
        row = self.staff_row(self.payload(), self.accountant)
        self.assertEqual(row["clients"], CLIENTS_PER_EMPLOYEE)
        self.assertEqual(row["late"], LATE_FOR_FIRST)
        self.assertTrue(row["red"])

    def test_one_late_of_ten_clients_keeps_the_row_plain_by_default(self):
        row = self.staff_row(self.payload(), self.colleague)
        self.assertEqual(row["late"], LATE_FOR_SECOND)
        self.assertFalse(row["red"])

    def test_the_threshold_is_read_from_the_registry_not_hardcoded(self):
        # رفعُ العتبة إلى 100٪ يُسكِت النسبة، والمضاعفُ إلى أقصاه يُسكِت الثانية.
        services.set_office_setting(self.tenant, "dashboard_late_share_percent", 100)
        services.set_office_setting(self.tenant, "dashboard_late_ratio", "100")
        payload = self.payload()
        self.assertFalse(self.staff_row(payload, self.accountant)["red"])
        # وإنزالُ النسبة إلى 5٪ يُحمرّ ذا المتأخّر الواحد من عشرة (10٪).
        services.set_office_setting(self.tenant, "dashboard_late_share_percent", 5)
        self.assertTrue(self.staff_row(self.payload(), self.colleague)["red"])

    def test_late_total_counts_late_obligations_and_late_tasks(self):
        self.assertEqual(self.payload()["late_total"], 4)
        # شغلةٌ تجاوزت موعدها الداخليّ وحده تزيد العددَ ولا تُحمرّ صاحبَها.
        late_task = add_obligation_row(
            tenant=self.tenant,
            client=self.second_clients[5],
            rule=self.rule,
            actual=DAY + datetime.timedelta(days=30),
            internal=DAY - datetime.timedelta(days=2),
        )
        self.assertIsNotNone(late_task)
        self.assertEqual(self.payload()["late_total"], 5)
        self.assertFalse(self.staff_row(self.payload(), self.colleague)["red"])


class LateClientsNotObligationsTest(OfficeDashboardTestCase):
    """`late` عددُ **الزبائن** المتأخّرين — والمقامُ نفسُه، لا عددُ الالتزامات.

    فزبونٌ واحدٌ يتأخّر مرّتين في الفترة نفسها (ق.م والمقدّمات معاً على شغلةٍ
    واحدة) يُعدّ **واحداً**؛ وعدُّه اثنين كان يُحمرّ صفَّ مسؤولِه بالعتبة
    الافتراضية وحدَه — ويُلوم الشخصَ الخطأ إن حُوّلت الشغلةُ إلى غيره.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.advances_rule = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026,
            code="il_income_advances",
        )
        cls.pair_member = User.objects.create_user(username="dash_pair", password="x")
        UserCompanyMembership.objects.create(
            user=cls.pair_member, tenant=cls.tenant, role="accountant",
        )
        cls.pair_clients = [
            office_client_without_periods(
                cls.tenant, f"زبون مزدوج {index}", responsible=cls.pair_member,
            )
            for index in range(CLIENTS_PER_EMPLOYEE)
        ]
        # التزامان متأخّران لزبونٍ واحدٍ على شغلةٍ واحدة: قيدُ `PeriodTask`
        # يمنع شغلتين لنفس (الخدمة × الفترة)، والفرادةُ في `Obligation` على
        # (`client_service` × `rule_code` × `period_end`) فتسمح بسطرَي لائحة.
        first = cls._late_obligation(cls.pair_clients[0])
        add_obligation_row(
            tenant=cls.tenant,
            client=cls.pair_clients[0],
            rule=cls.advances_rule,
            actual=DAY - datetime.timedelta(days=3),
            internal=DAY + datetime.timedelta(days=20),
            task=first.task,
        )

    def test_two_late_obligations_for_one_client_of_ten_keep_the_row_plain(self):
        payload = self.payload()
        row = self.staff_row(payload, self.pair_member)
        self.assertEqual(row["clients"], CLIENTS_PER_EMPLOYEE)
        # الزبونُ الواحدُ متأخّرٌ مرّتين: لا يُحمرّ صفُّ مسؤوله بالعتبة الافتراضية.
        self.assertFalse(row["red"], row)
        self.assertEqual(row["late"], 1)
        # المتوسطُ من العدد نفسه: (3 + 1 + 1) ÷ 3 — لا (3 + 1 + 2) ÷ 3.
        self.assertEqual(payload["thresholds"]["office_average_late"], "1.67")
        # `late_total` — حرفُ التذكرة — يبقى عددَ الالتزامات: 6 لا 5.
        self.assertEqual(payload["late_total"], 6)

    def test_three_late_clients_of_ten_turn_the_row_red(self):
        for client in self.pair_clients[1:3]:
            self._late_obligation(client)
        row = self.staff_row(self.payload(), self.pair_member)
        # ثلاثةُ زبائن متأخّرين من عشرة، والمكتبُ كله بثمانية التزاماتٍ حمراء.
        self.assertEqual(row["late"], 3)
        self.assertTrue(row["red"])


class SinglePersonTest(OfficeDashboardTestCase):
    """مكتبُ شخصٍ واحد: لا جدولَ موظفين — الواجهةُ تقرأ العلمَ ولا تخمّن."""

    def test_a_solo_office_says_single_person(self):
        services.set_office_setting(self.tenant, "office_size", "solo")
        self.assertTrue(self.payload()["single_person"])

    def test_a_small_office_does_not(self):
        self.assertFalse(self.payload()["single_person"])


class WaitingTest(OfficeDashboardTestCase):
    """«بانتظارك» يعدّ ما ينتظر صاحبَ المكتب فعلاً، و«اعتمد الكل» يعتمده."""

    def pending_draft(self, name, amount="300"):
        client = office_client_without_periods(
            self.tenant, name, responsible=self.accountant,
        )
        FeeSubscription.objects.create(
            tenant=self.tenant,
            client=client,
            amount=Decimal(amount),
            currency=self.currency,
            starts_on=datetime.date(2026, 1, 1),
        )
        return client

    def waiting_group(self, payload, key):
        """عدّادُ مجموعةٍ في «بانتظارك» — **الغائبةُ صفراً**: المجموعةُ الفارغةُ لا تُرسَل."""
        for group in payload["waiting"]["groups"]:
            if group["kind"] == key:
                return group
        return {"kind": key, "count": 0, "action": ""}

    def test_the_pending_drafts_are_counted_and_named(self):
        self.pending_draft("زبون أول")
        self.pending_draft("زبون ثانٍ")
        services.refresh_office(self.tenant, day=MAR_FIRST)
        self.assertEqual(fees.pending_drafts(self.tenant).count(), 2)

        group = self.waiting_group(self.payload(), "fee_drafts")
        self.assertEqual(group["count"], 2)
        self.assertEqual(group["action"], "approve_all")

    def test_approve_all_from_waiting_approves_the_drafts_for_real(self):
        self.pending_draft("زبون أول")
        self.pending_draft("زبون ثانٍ")
        services.refresh_office(self.tenant, day=MAR_FIRST)

        self.as_user(self.owner)
        res = self.client.post(f"{DRAFTS}approve-all/", {}, format="json", **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["approved"], 2)
        self.assertFalse(
            FeeDraft.objects.filter(status=FeeDraft.STATUS_DRAFT).exists(),
            "بقيت مسودّةٌ غير معتمدة بعد «اعتمد الكل»",
        )
        self.assertEqual(self.waiting_group(self.payload(), "fee_drafts")["count"], 0)

    def test_a_schedule_change_alert_is_counted_from_the_bell(self):
        """تغيّرُ اللائحة من **الجرس نفسه**: ما لا يراه المالك هناك لا يُعدّ هنا."""
        OfficeAlert.objects.create(
            tenant=self.tenant,
            recipient=self.owner,
            kind=OFFICE_ALERT_KIND_SCHEDULE_DATES_CHANGED,
            ref_key="schedule:v2",
            message="تغيّرت مواعيد اللائحة",
            day=DAY,
        )
        group = self.waiting_group(self.payload(), "schedule_changes")
        self.assertEqual(group["count"], 1)
        self.assertEqual(group["action"], "open_deadline_rules")

    def test_an_alert_of_someone_else_is_not_waiting_for_the_owner(self):
        """«بانتظارك» لصاحب المكتب: تنبيهُ موظّفٍ آخر ليس على طاولته."""
        OfficeAlert.objects.create(
            tenant=self.tenant,
            recipient=self.accountant,
            kind=OFFICE_ALERT_KIND_SCHEDULE_DATES_CHANGED,
            ref_key="schedule:v2",
            message="تغيّرت مواعيد اللائحة",
            day=DAY,
        )
        self.assertEqual(self.waiting_group(self.payload(), "schedule_changes")["count"], 0)


class TransferTest(OfficeDashboardTestCase):
    """التحويلُ `{responsible: <id>}`: عضوٌ بدور مكتبٍ وحده، ويُسجَّل حدثاً."""

    def transfer(self, client, responsible):
        return self.client.post(
            f"{CLIENTS}{client.pk}/assign/",
            {"responsible": responsible},
            format="json",
            **self.headers(),
        )

    def test_the_owner_transfers_with_the_responsible_key_and_it_is_logged(self):
        self.as_user(self.owner)
        res = self.transfer(self.first_clients[0], self.colleague.pk)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["responsible_id"], self.colleague.pk)
        self.assertEqual(
            OfficeClient.objects.get(pk=self.first_clients[0].pk).responsible_id,
            self.colleague.pk,
        )
        event = ActivityLog.objects.filter(
            entity_type="office_client", entity_id=self.first_clients[0].pk,
        ).order_by("-id").first()
        self.assertIsNotNone(event, "التحويلُ بلا سطرٍ في سجلّ النشاط")
        self.assertEqual(event.metadata["to"], self.colleague.pk)

    def test_a_user_outside_the_company_is_refused(self):
        outsider = User.objects.create_user(username="dash_outsider", password="x")
        self.as_user(self.owner)
        res = self.transfer(self.first_clients[0], outsider.pk)
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(
            OfficeClient.objects.get(pk=self.first_clients[0].pk).responsible_id,
            self.accountant.pk,
        )

    def test_a_member_without_an_office_role_is_refused(self):
        self.as_user(self.owner)
        res = self.transfer(self.first_clients[0], self.reader.pk)
        self.assertEqual(res.status_code, 400, res.content)
        # الرسالةُ عن الدور لا عن حقلٍ ناقص: العضويّةُ قائمةٌ والدورُ ليس دورَ مكتب.
        self.assertIn("دور مكتب", str(res.data))
        self.assertEqual(
            OfficeClient.objects.get(pk=self.first_clients[0].pk).responsible_id,
            self.accountant.pk,
        )


class ClientListResponsibleFilterTest(OfficeDashboardTestCase):
    """كبسةُ الموظف تفتح زبائنه: القائمةُ تُفلتر بالمسؤول في الخادم."""

    def test_the_list_can_be_narrowed_to_one_responsible(self):
        self.as_user(self.owner)
        res = self.client.get(
            CLIENTS,
            {"responsible": self.accountant.pk, "status": "active"},
            **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            sorted(row["id"] for row in res.data),
            sorted(client.pk for client in self.first_clients),
        )
