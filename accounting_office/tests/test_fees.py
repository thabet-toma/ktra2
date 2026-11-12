"""الأتعاب ١ — الاشتراكُ والمسودّاتُ والاعتماد (#282، الجزء أ١).

**الخادمُ وحده**: فاتورةُ الأتعاب الورقية وحقولُها القانونية والترقيمُ والإشعارُ
الضامن ورابطُ PDF وشاشةُ «المسودّات» كلُّها أ٢ لاحقاً — وهذا الملفّ يقيس
الطبقةَ التي تُنتج المسودّةَ وتعتمدها، لا المستند.

**والقواعدُ التي يسقط عندها الاختبار:**
1. التوليدُ لأوّل تشغيلٍ في الشهر، **ومرّتان = مسودّةٌ واحدة** (فرادةُ
   `(زبون، سنة، شهر)`).
2. السعرُ بتاريخ سريان: التغييرُ **يضيف صفّاً** ولا يعدّل ما قبله.
3. التناسبُ بعدد أيام الشهر الفعليّ — لا بثلاثين.
4. لا مسودّةَ لزبونٍ منتهٍ، ولا لشهرٍ فوترتُه موقوفة، ولا لاشتراكٍ انتهى.
5. الاعتمادُ لصاحب المكتب و«مدير المكتب» وحدهما — وغيرُ المعتمدة لا تُمحى
   ولا تُلغى بعد الاعتماد.
6. تنبيهٌ **بعد ثلاثة أيام** عبر `OfficeAlert`، ويسقط من الجرس باعتماد المسودّة.
7. كلُّ مبلغٍ يمرّ بالقناع: من لا يملك «يرى المبالغ» يقرأ `null` ولا يكتب مبلغاً.
8. العزل: زبونُ مكتبٍ آخر **404**، وقائمةُ مكتبٍ لا ترى مسودّات غيره.
"""
import datetime
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting_office import fees, services
from accounting_office.models import (
    ClientService,
    ClientServicePrice,
    FeeDraft,
    FeeDraftLine,
    FeeExtraService,
    FeeSubscription,
    OfficeAlert,
    OfficeClient,
    TaxCard,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
SUBSCRIPTIONS = f"{BASE}fees/subscriptions/"
DRAFTS = f"{BASE}fees/drafts/"
EXTRAS = f"{BASE}fees/extras/"
SERVICE_PRICES = f"{BASE}fees/service-prices/"
SETTINGS = f"{BASE}settings/"
CLIENTS = f"{BASE}clients/"

MAR_FIRST = datetime.date(2026, 3, 1)
APRIL_FIRST = datetime.date(2026, 4, 1)


def decimal_of(value) -> Decimal:
    """المبلغُ كما يصل من الـAPI — عشريٌّ أو نصٌّ، لا فرق."""
    return Decimal(str(value))


class FeesTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.currency = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )[0]
        cls.owner = User.objects.create_user(username="fees_owner", password="x")
        cls.tenant = create_company("مكتب الأتعاب", cls.owner, template="accounting_office")
        invalidate_module_cache(cls.tenant.pk)
        services.set_office_setting(cls.tenant, "tax_system", "PS")
        services.set_office_setting(cls.tenant, "office_size", "small")

        cls.office_manager_user = User.objects.create_user(
            username="fees_office_manager", password="x",
        )
        UserCompanyMembership.objects.create(
            user=cls.office_manager_user, tenant=cls.tenant, role="office_manager",
        )
        cls.accountant_user = User.objects.create_user(
            username="fees_accountant", password="x",
        )
        UserCompanyMembership.objects.create(
            user=cls.accountant_user, tenant=cls.tenant, role="accountant",
        )

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def setUp(self):
        self.as_user(self.owner)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def make_client(self, name="زبون الأتعاب", *, responsible=None,
                    status=OfficeClient.STATUS_ACTIVE, ended_on=None):
        client = OfficeClient.objects.create(
            tenant=self.tenant,
            name=name,
            responsible=responsible,
            status=status,
            ended_on=ended_on,
        )
        TaxCard.objects.create(client=client)
        return client

    def subscribe(self, client, amount, starts_on, **kwargs):
        return FeeSubscription.objects.create(
            tenant=self.tenant,
            client=client,
            amount=Decimal(amount),
            currency=self.currency,
            starts_on=starts_on,
            **kwargs,
        )

    def refresh(self, day):
        return services.refresh_office(self.tenant, day=day)

    def draft_of(self, client, year=2026, month=3):
        return FeeDraft.objects.get(client=client, year=year, month=month)

    def draft_ids(self):
        return sorted(FeeDraft.objects.values_list("pk", flat=True))


class FeeMethodSettingTest(FeesTestCase):
    """طريقةُ الأتعاب إعدادٌ مكتب ← زبون، و«بالساعة» مرفوضةٌ برسالتها."""

    def test_the_default_is_a_subscription_and_the_client_may_override_it(self):
        client = self.make_client("زبون بطريقته")
        self.assertEqual(services.resolve_setting(self.tenant, "fee_method"), "subscription")
        self.assertEqual(
            services.resolve_setting(self.tenant, "fee_method", client=client),
            "subscription",
        )

        res = self.client.put(
            f"{SETTINGS}fee_method/", {"value": "per_service"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(services.resolve_setting(self.tenant, "fee_method"), "per_service")

        res = self.client.put(
            f"{CLIENTS}{client.pk}/settings/fee_method/", {"value": "subscription"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            services.resolve_setting(self.tenant, "fee_method", client=client),
            "subscription",
        )

    def test_hourly_is_refused_with_its_message_at_both_levels(self):
        client = self.make_client("زبون")
        office = self.client.put(
            f"{SETTINGS}fee_method/", {"value": "hourly"},
            format="json", **self.headers(),
        )
        self.assertEqual(office.status_code, 400, office.content)
        self.assertIn("بالساعة", str(office.data))
        self.assertEqual(services.resolve_setting(self.tenant, "fee_method"), "subscription")

        at_client = self.client.put(
            f"{CLIENTS}{client.pk}/settings/fee_method/", {"value": "hourly"},
            format="json", **self.headers(),
        )
        self.assertEqual(at_client.status_code, 400, at_client.content)
        self.assertIn("بالساعة", str(at_client.data))

    def test_the_auto_approve_setting_is_locked_off(self):
        on = self.client.put(
            f"{SETTINGS}fee_auto_approve/", {"value": True},
            format="json", **self.headers(),
        )
        self.assertEqual(on.status_code, 400, on.content)
        self.assertIn("الاعتماد التلقائي", str(on.data))

        off = self.client.put(
            f"{SETTINGS}fee_auto_approve/", {"value": False},
            format="json", **self.headers(),
        )
        self.assertEqual(off.status_code, 200, off.content)


class DraftGenerationTest(FeesTestCase):
    def test_the_first_run_of_the_month_makes_one_draft_and_a_second_changes_nothing(self):
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 1, 1))

        first = self.refresh(MAR_FIRST)
        self.assertEqual(first["created_fee_drafts"], 1)
        draft = self.draft_of(client)
        self.assertEqual(draft.status, FeeDraft.STATUS_DRAFT)
        self.assertEqual(decimal_of(draft.subtotal), Decimal("300.00"))
        self.assertEqual(decimal_of(draft.total), Decimal("300.00"))
        self.assertEqual(
            list(draft.lines.values_list("source", flat=True)), [FeeDraftLine.SOURCE_SUBSCRIPTION],
        )

        second = self.refresh(MAR_FIRST)
        self.assertEqual(second["created_fee_drafts"], 0)
        self.assertEqual(FeeDraft.objects.filter(client=client).count(), 1)

        # ويومٌ لاحقٌ في الشهر نفسه لا يولّد مسودّةً ثانية.
        self.assertEqual(self.refresh(MAR_FIRST + datetime.timedelta(days=9))["created_fee_drafts"], 0)
        self.assertEqual(FeeDraft.objects.filter(client=client).count(), 1)

    def test_a_price_change_adds_a_row_and_the_month_after_takes_it(self):
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 1, 1))
        self.subscribe(client, "350", APRIL_FIRST)

        self.refresh(MAR_FIRST)
        self.refresh(APRIL_FIRST)

        self.assertEqual(decimal_of(self.draft_of(client, month=3).total), Decimal("300.00"))
        self.assertEqual(decimal_of(self.draft_of(client, month=4).total), Decimal("350.00"))
        self.assertEqual(
            FeeSubscription.objects.filter(client=client).count(), 2,
            "تغييرُ السعر يعدّل صفاً بدل إضافة صفٍّ — تاريخُ الشهر السابق يضيع",
        )

    def test_subscription_on_reads_the_row_effective_in_the_month(self):
        """«السعرُ في شهرٍ ما» قاعدةٌ واحدة: أكبر `starts_on` لا يتجاوز الشهر."""
        client = self.make_client()
        older = self.subscribe(client, "300", datetime.date(2026, 1, 1))
        newer = self.subscribe(client, "350", APRIL_FIRST)

        self.assertEqual(fees.subscription_on(self.tenant, client, day=MAR_FIRST), older)
        self.assertEqual(fees.subscription_on(self.tenant, client, day=APRIL_FIRST), newer)
        self.assertIsNone(
            fees.subscription_on(self.tenant, client, day=datetime.date(2025, 12, 1)),
        )

    def test_the_start_of_a_month_is_prorated_by_its_real_day_count(self):
        thirty = self.make_client("زبون نيسان")
        thirty_one = self.make_client("زبون آذار")
        self.subscribe(thirty, "300", datetime.date(2026, 4, 16))
        self.subscribe(thirty_one, "300", datetime.date(2026, 3, 16))

        self.refresh(APRIL_FIRST)
        self.refresh(MAR_FIRST)

        # نيسان ثلاثون يوماً: من 16 إلى 30 = 15 يوماً = نصف الشهر تماماً.
        self.assertEqual(decimal_of(self.draft_of(thirty, month=4).total), Decimal("150.00"))
        # وآذار أحدٌ وثلاثون: 16 يوماً من 31 — لا 16/30.
        self.assertEqual(decimal_of(self.draft_of(thirty_one, month=3).total), Decimal("154.84"))

    def test_no_draft_for_an_ended_client_an_ended_subscription_or_a_paused_month(self):
        ended_client = self.make_client(
            "زبون منتهٍ", status=OfficeClient.STATUS_ENDED,
            ended_on=datetime.date(2026, 2, 1),
        )
        self.subscribe(ended_client, "300", datetime.date(2026, 1, 1))

        ended_subscription = self.make_client("اشتراك منتهٍ")
        self.subscribe(
            ended_subscription, "300", datetime.date(2026, 1, 1),
            ended_on=datetime.date(2026, 2, 28),
        )

        paused = self.make_client("فوترة موقوفة")
        self.subscribe(
            paused, "300", datetime.date(2026, 1, 1),
            paused_from=MAR_FIRST, paused_to=datetime.date(2026, 3, 31),
        )

        self.refresh(MAR_FIRST)

        self.assertEqual(self.draft_ids(), [], "مسودّةٌ لزبونٍ منتهٍ أو اشتراكٍ انتهى أو شهرٍ موقوف")

    def test_per_service_bills_the_services_whose_periods_start_in_the_month(self):
        services.set_office_setting(self.tenant, "fee_method", "per_service")
        client = self.make_client()
        catalog = services.ensure_default_services(self.tenant)
        service = catalog[0]
        client_service = services.add_client_service(
            client=client,
            service=service,
            starts_on=datetime.date(2026, 1, 1),
            responsible_from=datetime.date(2026, 1, 1),
            frequency="monthly",
        )
        fees.set_client_service_price(client_service, amount=Decimal("120"))
        # إضافةٌ نُفِّذت في شباط ⇒ مسودّةُ آذار.
        FeeExtraService.objects.create(
            tenant=self.tenant, client=client, service_name="تصديق شهادة",
            amount=Decimal("50"), performed_on=datetime.date(2026, 2, 20),
            draft=FeeExtraService.DESTINATION_NEXT_MONTH,
        )

        self.refresh(MAR_FIRST)

        draft = self.draft_of(client)
        self.assertEqual(decimal_of(draft.total), Decimal("170.00"))
        by_source = {
            line.source: (line.label, decimal_of(line.amount))
            for line in draft.lines.all()
        }
        self.assertEqual(by_source[FeeDraftLine.SOURCE_SERVICE], (service.name, Decimal("120.00")))
        self.assertEqual(by_source[FeeDraftLine.SOURCE_EXTRA], ("تصديق شهادة", Decimal("50.00")))

    def test_a_standalone_extra_never_enters_a_draft(self):
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 1, 1))
        FeeExtraService.objects.create(
            tenant=self.tenant, client=client, service_name="تأسيس شركة",
            amount=Decimal("900"), performed_on=datetime.date(2026, 2, 10),
            draft=FeeExtraService.DESTINATION_STANDALONE,
        )

        self.refresh(MAR_FIRST)

        self.assertEqual(decimal_of(self.draft_of(client).total), Decimal("300.00"))

    def test_an_extra_goes_to_the_draft_of_the_month_after_it_was_performed(self):
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 1, 1))
        FeeExtraService.objects.create(
            tenant=self.tenant, client=client, service_name="كشف حساب بنكي",
            amount=Decimal("80"), performed_on=datetime.date(2026, 3, 10),
            draft=FeeExtraService.DESTINATION_NEXT_MONTH,
        )

        self.refresh(MAR_FIRST)
        self.assertEqual(decimal_of(self.draft_of(client, month=3).total), Decimal("300.00"))

        self.refresh(APRIL_FIRST)
        self.assertEqual(decimal_of(self.draft_of(client, month=4).total), Decimal("380.00"))


class DraftApprovalTest(FeesTestCase):
    def pending_draft(self, name="زبون الاعتماد", amount="300", responsible=None):
        client = self.make_client(name, responsible=responsible)
        self.subscribe(client, amount, datetime.date(2026, 1, 1))
        self.refresh(MAR_FIRST)
        return self.draft_of(client)

    def test_the_owner_approves_and_the_state_is_recorded(self):
        draft = self.pending_draft()
        res = self.client.post(
            f"{DRAFTS}{draft.pk}/approve/", {"note": "اعتُمدت"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        draft.refresh_from_db()
        self.assertEqual(draft.status, FeeDraft.STATUS_APPROVED)
        self.assertEqual(draft.approved_by_id, self.owner.pk)
        self.assertIsNotNone(draft.approved_at)
        self.assertEqual(draft.approved_note, "اعتُمدت")

    def test_the_office_manager_approves_and_an_accountant_is_refused(self):
        # الزبونُ للمحاسب (فيراه ويبلغ دورَ الاعتماد لا 404)، والدورُ يمنعه.
        draft = self.pending_draft(responsible=self.accountant_user)
        self.as_user(self.accountant_user)
        refused = self.client.post(f"{DRAFTS}{draft.pk}/approve/", {}, format="json", **self.headers())
        self.assertEqual(refused.status_code, 403, refused.content)
        draft.refresh_from_db()
        self.assertEqual(draft.status, FeeDraft.STATUS_DRAFT)

        self.as_user(self.office_manager_user)
        allowed = self.client.post(f"{DRAFTS}{draft.pk}/approve/", {}, format="json", **self.headers())
        self.assertEqual(allowed.status_code, 200, allowed.content)
        draft.refresh_from_db()
        self.assertEqual(draft.approved_by_id, self.office_manager_user.pk)

    def test_approve_all_approves_every_pending_draft_of_the_office(self):
        first = self.pending_draft("زبون أول")
        second = self.pending_draft("زبون ثانٍ")
        approved = self.pending_draft("زبون ثالث")
        fees.approve_fee_draft(approved, actor=self.owner)

        res = self.client.post(f"{DRAFTS}approve-all/", {}, format="json", **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["approved"], 2)
        self.assertFalse(
            FeeDraft.objects.filter(status=FeeDraft.STATUS_DRAFT).exists(),
            "بقيت مسودّةٌ غير معتمدة بعد «اعتمد الكل»",
        )
        self.assertEqual(res.data["remaining"], 0)
        self.assertIn(first.pk, [row["id"] for row in res.data["drafts"]])
        self.assertIn(second.pk, [row["id"] for row in res.data["drafts"]])

    def test_cancel_is_before_approval_only(self):
        draft = self.pending_draft()
        res = self.client.post(f"{DRAFTS}{draft.pk}/cancel/", {}, format="json", **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        draft.refresh_from_db()
        self.assertEqual(draft.status, FeeDraft.STATUS_CANCELLED)

        approved = self.pending_draft("زبون آخر")
        fees.approve_fee_draft(approved, actor=self.owner)
        late = self.client.post(f"{DRAFTS}{approved.pk}/cancel/", {}, format="json", **self.headers())
        self.assertEqual(late.status_code, 400, late.content)

    def test_an_approved_draft_is_not_regenerated(self):
        draft = self.pending_draft()
        fees.approve_fee_draft(draft, actor=self.owner)

        self.refresh(MAR_FIRST)
        self.refresh(MAR_FIRST + datetime.timedelta(days=5))

        self.assertEqual(FeeDraft.objects.filter(client=draft.client).count(), 1)
        fresh = self.draft_of(draft.client)
        self.assertEqual(fresh.status, FeeDraft.STATUS_APPROVED)
        self.assertEqual(decimal_of(fresh.total), Decimal("300.00"))

    def test_only_the_manager_and_the_office_manager_may_approve(self):
        self.assertTrue(fees.can_approve_fee_drafts(self.tenant, self.owner))
        self.assertTrue(fees.can_approve_fee_drafts(self.tenant, self.office_manager_user))
        self.assertFalse(fees.can_approve_fee_drafts(self.tenant, self.accountant_user))


class PendingFeeAlertTest(FeesTestCase):
    def test_the_alert_waits_three_days_then_arrives_once_per_approver(self):
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 1, 1))
        self.refresh(MAR_FIRST)
        draft = self.draft_of(client)

        self.refresh(MAR_FIRST + datetime.timedelta(days=2))
        self.assertFalse(
            OfficeAlert.objects.filter(kind="fee_draft_pending").exists(),
            "التنبيهُ سبق ثلاثة أيام",
        )

        self.refresh(MAR_FIRST + datetime.timedelta(days=3))
        alerts = OfficeAlert.objects.filter(kind="fee_draft_pending")
        self.assertEqual(alerts.count(), 2, "التنبيهُ لم يبلغ صاحب المكتب ومدير المكتب")
        self.assertEqual(set(alerts.values_list("ref_key", flat=True)), {f"fee_draft:{draft.pk}"})
        self.assertEqual(
            set(alerts.values_list("recipient_id", flat=True)),
            {self.owner.pk, self.office_manager_user.pk},
        )
        message = alerts.first().message
        self.assertIn(client.name, message)
        self.assertNotIn("300", message, "مبلغٌ في نصّ التنبيه — الجرسُ لا يحمل مالاً")

        # ويومٌ رابع لا يُكرّر التنبيه للمستلِم نفسه.
        self.refresh(MAR_FIRST + datetime.timedelta(days=4))
        self.assertEqual(OfficeAlert.objects.filter(kind="fee_draft_pending").count(), 2)

    def test_the_alert_leaves_the_bell_once_the_draft_is_approved(self):
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 1, 1))
        self.refresh(MAR_FIRST)
        self.refresh(MAR_FIRST + datetime.timedelta(days=3))
        day = MAR_FIRST + datetime.timedelta(days=3)
        kinds = {
            row["kind"]
            for row in services.alerts_payload(self.tenant, user=self.owner, day=day)["rows"]
        }
        self.assertIn("fee_draft_pending", kinds)

        fees.approve_fee_draft(self.draft_of(client), actor=self.owner)

        kinds = {
            row["kind"]
            for row in services.alerts_payload(self.tenant, user=self.owner, day=day)["rows"]
        }
        self.assertNotIn(
            "fee_draft_pending", kinds,
            "تنبيهُ مسودّةٍ اعتُمدت ما زال في الجرس — يقول شيئاً غير صحيح",
        )


class FeeApiTest(FeesTestCase):
    def test_a_subscription_is_added_and_read_with_its_amount(self):
        client = self.make_client()
        created = self.client.post(
            SUBSCRIPTIONS,
            {
                "client": client.pk,
                "amount": "300.00",
                "starts_on": "2026-01-01",
            },
            format="json", **self.headers(),
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(decimal_of(created.data["amount"]), Decimal("300.00"))
        self.assertEqual(created.data["client"]["id"], client.pk)

        listed = self.client.get(SUBSCRIPTIONS, **self.headers())
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual([row["id"] for row in listed.data], [created.data["id"]])

    def test_two_price_changes_on_the_same_effective_date_are_refused(self):
        client = self.make_client()
        body = {"client": client.pk, "amount": "300.00", "starts_on": "2026-01-01"}
        self.assertEqual(
            self.client.post(SUBSCRIPTIONS, body, format="json", **self.headers()).status_code,
            201,
        )
        again = self.client.post(SUBSCRIPTIONS, body, format="json", **self.headers())
        self.assertEqual(again.status_code, 400, again.content)

    def test_an_extra_is_recorded_with_its_destination(self):
        client = self.make_client()
        res = self.client.post(
            EXTRAS,
            {
                "client": client.pk,
                "service_name": "تصديق شهادة",
                "amount": "50.00",
                "performed_on": "2026-03-10",
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["draft"], FeeExtraService.DESTINATION_NEXT_MONTH)
        self.assertEqual(res.data["draft_label"], "مسودّة الشهر القادم")
        self.assertEqual(decimal_of(res.data["amount"]), Decimal("50.00"))

        listed = self.client.get(EXTRAS, **self.headers())
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual([row["id"] for row in listed.data], [res.data["id"]])

    def test_the_drafts_are_read_masked_for_a_member_without_the_amounts_key(self):
        client = self.make_client("زبون المحاسب", responsible=self.accountant_user)
        self.subscribe(client, "300", datetime.date(2026, 1, 1))
        FeeExtraService.objects.create(
            tenant=self.tenant, client=client, service_name="تصديق شهادة",
            amount=Decimal("50"), performed_on=datetime.date(2026, 2, 20),
            draft=FeeExtraService.DESTINATION_NEXT_MONTH,
        )
        self.refresh(MAR_FIRST)
        self.refresh(MAR_FIRST + datetime.timedelta(days=3))

        self.as_user(self.accountant_user)
        res = self.client.get(DRAFTS, **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        row = res.data[0]
        self.assertIsNone(row["total"])
        self.assertIsNone(row["subtotal"])
        self.assertTrue(row["lines"], "مسودّةٌ بلا بنود — لا شيء يُقنَّع في الاختبار")
        self.assertEqual(
            {line["source"] for line in row["lines"]},
            {FeeDraftLine.SOURCE_SUBSCRIPTION, FeeDraftLine.SOURCE_EXTRA},
        )
        for line in row["lines"]:
            self.assertIsNone(line["amount"], line["label"])
            self.assertTrue(line["label"], "القناعُ محا البيانَ أيضاً")
            self.assertTrue(line["source_label"])

        subscriptions = self.client.get(SUBSCRIPTIONS, **self.headers())
        self.assertIsNone(subscriptions.data[0]["amount"])
        extras = self.client.get(EXTRAS, **self.headers())
        self.assertEqual(extras.status_code, 200, extras.content)
        self.assertTrue(extras.data, "إضافةُ الزبون لا تظهر لمن يراه")
        self.assertIsNone(extras.data[0]["amount"])
        self.assertEqual(extras.data[0]["service_name"], "تصديق شهادة")

        self.as_user(self.owner)
        full = self.client.get(DRAFTS, **self.headers())
        self.assertEqual(decimal_of(full.data[0]["total"]), Decimal("350.00"))
        self.assertEqual(
            {line["source"]: decimal_of(line["amount"]) for line in full.data[0]["lines"]},
            {
                FeeDraftLine.SOURCE_SUBSCRIPTION: Decimal("300.00"),
                FeeDraftLine.SOURCE_EXTRA: Decimal("50.00"),
            },
        )
        full_extras = self.client.get(EXTRAS, **self.headers())
        self.assertEqual(decimal_of(full_extras.data[0]["amount"]), Decimal("50.00"))

    def test_a_member_without_the_amounts_key_cannot_write_an_amount(self):
        client = self.make_client("زبون المحاسب", responsible=self.accountant_user)
        self.as_user(self.accountant_user)
        res = self.client.post(
            SUBSCRIPTIONS,
            {"client": client.pk, "amount": "300.00", "starts_on": "2026-01-01"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 403, res.content)
        self.assertFalse(FeeSubscription.objects.exists())

    def test_no_fee_route_accepts_delete(self):
        """**ولا `DELETE`** — لا على جمعٍ ولا على فعلٍ ولا على صفّ.

        الجموعُ وحدها لا تُسقط الحارس: `destroy` على الـviewset يُولّد مسارَ
        التفصيل فيمرّ الحذفُ من بابٍ لم يُطرق. ولهذا تُطرق الأفعالُ
        (`approve`/`cancel`/`approve-all`) أيضاً، ويُتحقَّق أن الصفَّ باقٍ بعد
        كلِّ محاولةٍ على مسار التفصيل — سواءٌ ردّ 405 (الطريقةُ مسدودة) أو 404
        (المسارُ غيرُ مولَّدٍ أصلاً، فالحذفُ غيرُ متاحٍ بالطريقة الأخرى).
        """
        client = self.make_client()
        subscription = self.subscribe(client, "300", datetime.date(2026, 1, 1))
        extra = FeeExtraService.objects.create(
            tenant=self.tenant, client=client, service_name="خدمة",
            amount=Decimal("50"), performed_on=datetime.date(2026, 3, 10),
        )
        self.refresh(MAR_FIRST)
        draft = self.draft_of(client)

        for path in (
            SUBSCRIPTIONS, DRAFTS, EXTRAS, SERVICE_PRICES,
            f"{DRAFTS}{draft.pk}/approve/",
            f"{DRAFTS}{draft.pk}/cancel/",
            f"{DRAFTS}approve-all/",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    self.client.delete(path, **self.headers()).status_code, 405,
                )

        for path, model, pk in (
            (f"{SUBSCRIPTIONS}{subscription.pk}/", FeeSubscription, subscription.pk),
            (f"{EXTRAS}{extra.pk}/", FeeExtraService, extra.pk),
            (f"{DRAFTS}{draft.pk}/", FeeDraft, draft.pk),
        ):
            with self.subTest(path=path):
                res = self.client.delete(path, **self.headers())
                self.assertIn(res.status_code, (404, 405), res.content)
                self.assertTrue(model.objects.filter(pk=pk).exists(), path)

    def test_another_office_and_another_office_client_are_404(self):
        other_owner = User.objects.create_user(username="fees_other_owner", password="x")
        other_tenant = create_company("مكتب آخر", other_owner, template="accounting_office")
        invalidate_module_cache(other_tenant.pk)
        foreign = OfficeClient.objects.create(tenant=other_tenant, name="زبون غيري")
        TaxCard.objects.create(client=foreign)

        created = self.client.post(
            SUBSCRIPTIONS,
            {"client": foreign.pk, "amount": "300.00", "starts_on": "2026-01-01"},
            format="json", **self.headers(),
        )
        self.assertEqual(created.status_code, 404, created.content)

        extra = self.client.post(
            EXTRAS,
            {
                "client": foreign.pk,
                "service_name": "خدمة",
                "amount": "10.00",
                "performed_on": "2026-03-10",
            },
            format="json", **self.headers(),
        )
        self.assertEqual(extra.status_code, 404, extra.content)

        # ومسودّةُ مكتبٍ آخر لا يقرؤها هذا المكتب ولا يعتمدها.
        foreign_subscription = FeeSubscription.objects.create(
            tenant=other_tenant, client=foreign, amount=Decimal("300"),
            starts_on=datetime.date(2026, 1, 1),
        )
        self.assertIsNotNone(foreign_subscription.pk)
        services.refresh_office(other_tenant, day=MAR_FIRST)
        foreign_draft = FeeDraft.objects.get(client=foreign)

        self.assertEqual(self.client.get(DRAFTS, **self.headers()).data, [])
        self.assertEqual(self.client.get(SUBSCRIPTIONS, **self.headers()).data, [])
        self.assertEqual(self.client.get(EXTRAS, **self.headers()).data, [])
        approved = self.client.post(
            f"{DRAFTS}{foreign_draft.pk}/approve/", {}, format="json", **self.headers(),
        )
        self.assertEqual(approved.status_code, 404, approved.content)
        foreign_draft.refresh_from_db()
        self.assertEqual(foreign_draft.status, FeeDraft.STATUS_DRAFT)


class ProrationTest(FeesTestCase):
    """التناسبُ على حدود الشهر — لا على كلّ صفٍّ بدأ في منتصفه.

    **القاعدة:** الصفُّ الساري يحكم الشهرَ كلَّه بسعره (قاعدةُ «السعر بتاريخ
    سريان»)، والتناسبُ للأيام التي وقعت فعلاً على حدود الاشتراك: أوّلُ صفٍّ
    (أو عودةٌ بعد `ended_on`) يبدأ من `starts_on`، والصفوفُ التي بعدها من أوّل
    الشهر لأن الصفَّ السابق يغطّي أيامه. والحدُّ الآخر: `ended_on` ينتهي به الشهر.
    """

    def test_a_mid_month_price_change_bills_the_months_price_in_full(self):
        """سعرٌ جديدٌ في 15/4 ⇒ 400.00 كاملة، لا 400 × 16/30 والأيام 1–14 ضائعة."""
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 1, 1))
        self.subscribe(client, "400", datetime.date(2026, 4, 15))

        self.refresh(APRIL_FIRST)

        draft = self.draft_of(client, month=4)
        self.assertEqual(decimal_of(draft.total), Decimal("400.00"))
        self.assertEqual(
            list(draft.lines.values_list("label", flat=True)),
            [fees.SUBSCRIPTION_LINE_LABEL],
            "سطرٌ متناسبٌ لصفٍّ يغطّي الصفُّ السابق بدايةَ الشهر",
        )

    def test_a_row_that_ends_mid_month_bills_its_days_from_the_first(self):
        """`starts_on = ended_on = 20/5` ⇒ 20/31 من المبلغ، لا يومٌ واحد."""
        client = self.make_client()
        self.subscribe(
            client, "300", datetime.date(2026, 1, 1),
            ended_on=datetime.date(2026, 5, 19),
        )
        self.subscribe(
            client, "310", datetime.date(2026, 5, 20),
            ended_on=datetime.date(2026, 5, 20),
        )

        self.refresh(datetime.date(2026, 5, 1))

        draft = self.draft_of(client, month=5)
        self.assertEqual(
            decimal_of(draft.total), Decimal("200.00"), "310 × 20/31",
        )
        self.assertEqual(
            list(draft.lines.values_list("label", flat=True)),
            [fees.SUBSCRIPTION_LINE_LABEL + fees.PRORATED_SUFFIX],
        )

    def test_a_return_after_a_terminating_row_is_prorated_from_its_start(self):
        """A مفتوحٌ ثم C ينهيه بصفٍّ جديد ثم D عودةٌ — الأصلُ يبقى `ended_on=None`.

        الصفوفُ إلحاقيّةٌ: الإنهاءُ **صفٌّ** `starts_on = ended_on` لا تعديلٌ على A،
        فيبقى A مفتوحاً إلى الأبد. والتغطيةُ تُحكم بالصفّ **الساري في اليوم
        السابق** (C، وقد انتهى) لا بأيّ صفٍّ يشبه أنّه مفتوح (A)، وإلا فُوتر تموزُ
        كاملاً (310) لعودةٍ في 10/7.
        """
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 1, 1))
        self.subscribe(
            client, "300", datetime.date(2026, 5, 20),
            ended_on=datetime.date(2026, 5, 20),
        )
        self.subscribe(client, "310", datetime.date(2026, 7, 10))

        self.refresh(datetime.date(2026, 6, 1))
        self.assertFalse(
            FeeDraft.objects.filter(client=client, year=2026, month=6).exists(),
            "حزيران بين الإنهاء والعودة — لا مسودّة",
        )

        self.refresh(datetime.date(2026, 7, 1))
        draft = self.draft_of(client, month=7)
        self.assertEqual(
            decimal_of(draft.total), Decimal("220.00"), "310 × 22/31 لا 310 كاملة",
        )
        self.assertEqual(
            list(draft.lines.values_list("label", flat=True)),
            [fees.SUBSCRIPTION_LINE_LABEL + fees.PRORATED_SUFFIX],
        )


class PauseTest(FeesTestCase):
    """الإيقافُ يمنع المسودّةَ **كلَّها**، وإضافاتُه تنتظر أوّلَ مسودّةٍ بعده."""

    def test_a_paused_month_makes_no_draft_and_its_extras_wait_for_the_next_one(self):
        client = self.make_client("زبون موقوف")
        self.subscribe(
            client, "300", datetime.date(2026, 1, 1),
            paused_from=APRIL_FIRST, paused_to=datetime.date(2026, 4, 30),
        )
        FeeExtraService.objects.create(
            tenant=self.tenant, client=client, service_name="تصديق شهادة",
            amount=Decimal("50"), performed_on=datetime.date(2026, 3, 20),
            draft=FeeExtraService.DESTINATION_NEXT_MONTH,
        )

        self.refresh(APRIL_FIRST)
        self.assertEqual(
            self.draft_ids(), [], "مسودّةٌ لشهرٍ موقوفٍ فيها الإضافاتُ وحدها",
        )

        # وبعد انتهاء الإيقاف تُلتقط الإضافةُ مع أوّل مسودّة — مرّةً واحدة.
        self.refresh(datetime.date(2026, 5, 1))
        draft = self.draft_of(client, month=5)
        self.assertEqual(decimal_of(draft.total), Decimal("350.00"))
        self.assertEqual(
            sorted(draft.lines.values_list("source", flat=True)),
            [FeeDraftLine.SOURCE_EXTRA, FeeDraftLine.SOURCE_SUBSCRIPTION],
        )


class ExtraBillingTest(FeesTestCase):
    """الإضافةُ لا تضيع بصمت: تُربط بمسودّتها، وإلغاؤها يُعيدها."""

    def test_an_extra_recorded_after_the_next_months_draft_reaches_a_draft_once(self):
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 1, 1))
        # مسودّةُ نيسان تُولَّد قبل تسجيل الإضافة — لقطةٌ لا تُعاد.
        self.refresh(APRIL_FIRST)
        extra = FeeExtraService.objects.create(
            tenant=self.tenant, client=client, service_name="تصديق شهادة",
            amount=Decimal("50"), performed_on=datetime.date(2026, 3, 31),
            draft=FeeExtraService.DESTINATION_NEXT_MONTH,
        )

        self.refresh(datetime.date(2026, 5, 1))
        may = self.draft_of(client, month=5)
        self.assertEqual(decimal_of(may.total), Decimal("350.00"))
        extra.refresh_from_db()
        self.assertEqual(extra.billed_draft_id, may.pk)
        self.assertEqual(
            decimal_of(self.draft_of(client, month=4).total), Decimal("300.00"),
            "مسودّةُ نيسان تُعاد كتابتها بعد التوليد",
        )

        # وتوليدٌ لاحقٌ لا يكرّر الإضافة.
        self.refresh(datetime.date(2026, 6, 1))
        self.assertEqual(
            decimal_of(self.draft_of(client, month=6).total), Decimal("300.00"),
        )

    def test_cancelling_the_draft_frees_its_extras_for_the_next_generation(self):
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 1, 1))
        self.refresh(MAR_FIRST)
        FeeExtraService.objects.create(
            tenant=self.tenant, client=client, service_name="تصديق شهادة",
            amount=Decimal("50"), performed_on=datetime.date(2026, 2, 20),
            draft=FeeExtraService.DESTINATION_NEXT_MONTH,
        )
        self.refresh(APRIL_FIRST)
        april = self.draft_of(client, month=4)
        self.assertEqual(decimal_of(april.total), Decimal("350.00"))
        extra = FeeExtraService.objects.get(client=client)

        fees.cancel_fee_draft(april, actor=self.owner)
        extra.refresh_from_db()
        self.assertIsNone(extra.billed_draft_id, "الإلغاءُ لم يُعِد الإضافة")

        self.refresh(datetime.date(2026, 5, 1))
        may = self.draft_of(client, month=5)
        self.assertEqual(decimal_of(may.total), Decimal("350.00"))
        extra.refresh_from_db()
        self.assertEqual(extra.billed_draft_id, may.pk)

    def test_an_extra_billed_by_a_concurrent_run_is_not_billed_again(self):
        """تشغيلان متزامنان لشهرين: الثاني يقرأ الإضافةَ حرّةً ثم يسبقه الأوّل.

        الحارسُ `billed_draft__isnull=True` على التحديث: ما ربطه غيرُنا لا نُعيد
        ربطه — ومسودّتُنا فيها سطرُه فتُتراجع كلُّها (تلتقطها دورةٌ تالية بلا
        الإضافة) بدل أن تُحسب الإضافةُ في مسودّتين.
        """
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 1, 1))
        extra = FeeExtraService.objects.create(
            tenant=self.tenant, client=client, service_name="تصديق شهادة",
            amount=Decimal("50"), performed_on=datetime.date(2026, 2, 20),
            draft=FeeExtraService.DESTINATION_NEXT_MONTH,
        )
        rival = FeeDraft.objects.create(
            tenant=self.tenant, client=client, year=2026, month=3,
            subtotal=Decimal("0"), total=Decimal("0"),
            generated_at=fees._generated_at(MAR_FIRST),
        )
        original = fees._extra_lines

        def rival_run_wins(extras):
            # بعد قراءتنا للإضافة حرّةً وقبل ربطها: تشغيلٌ آخر يربطها بمسودّته.
            FeeExtraService.objects.filter(pk=extra.pk).update(billed_draft=rival)
            return original(extras)

        with mock.patch.object(fees, "_extra_lines", side_effect=rival_run_wins):
            self.refresh(APRIL_FIRST)

        extra.refresh_from_db()
        self.assertEqual(extra.billed_draft_id, rival.pk, "أُعيد ربطُ إضافةٍ مربوطة")
        self.assertFalse(
            FeeDraft.objects.filter(client=client, year=2026, month=4).exists(),
            "مسودّةٌ تحسب إضافةً رُبطت بغيرها",
        )


class FeeDraftMonthConstraintTest(FeesTestCase):
    """فرادةُ `(زبون، سنة، شهر)` في القاعدة لا في ذاكرة العملية.

    التوليدُ يتخطّى صاحبَ المسودّة قبل الكتابة، وهذا الاختبارُ يثبت أن القاعدةَ
    تحرسه كذلك: لو حُذف القيدُ من النموذج مرّ الصفُّ الثاني. (`makemigrations
    --check` هو من يحرس وجودَه في `0012`.)
    """

    def test_a_second_draft_of_the_same_month_is_refused_by_the_database(self):
        client = self.make_client()
        FeeDraft.objects.create(
            tenant=self.tenant, client=client, year=2026, month=3,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FeeDraft.objects.create(
                    tenant=self.tenant, client=client, year=2026, month=3,
                )
        self.assertEqual(FeeDraft.objects.filter(client=client).count(), 1)


class ApproveAllCoverageTest(FeesTestCase):
    """«اعتمد الكل»: الملغاةُ لا تُعتمد، وغيرُ المعتمِد 403."""

    def test_approve_all_leaves_a_cancelled_draft_and_refuses_a_non_approver(self):
        cancelled_client = self.make_client("زبون ملغى")
        self.subscribe(cancelled_client, "300", datetime.date(2026, 1, 1))
        pending_client = self.make_client("زبون منتظر")
        self.subscribe(pending_client, "300", datetime.date(2026, 1, 1))
        self.refresh(MAR_FIRST)
        cancelled = self.draft_of(cancelled_client)
        fees.cancel_fee_draft(cancelled, actor=self.owner)

        self.as_user(self.accountant_user)
        refused = self.client.post(
            f"{DRAFTS}approve-all/", {}, format="json", **self.headers(),
        )
        self.assertEqual(refused.status_code, 403, refused.content)
        self.assertEqual(FeeDraft.objects.filter(status=FeeDraft.STATUS_DRAFT).count(), 1)

        self.as_user(self.owner)
        res = self.client.post(f"{DRAFTS}approve-all/", {}, format="json", **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["approved"], 1)
        self.assertEqual(res.data["remaining"], 0)
        self.assertEqual(
            [row["id"] for row in res.data["drafts"]],
            [self.draft_of(pending_client).pk],
        )
        cancelled.refresh_from_db()
        self.assertEqual(cancelled.status, FeeDraft.STATUS_CANCELLED)


class MonthBoundaryTest(FeesTestCase):
    """حدودُ التقويم والإيقاف: فبراير، وأوّلُ الشهر، وإيقافٌ مفتوح وحدُّه."""

    def test_february_prorates_by_its_twenty_eight_days(self):
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 2, 15))

        self.refresh(datetime.date(2026, 2, 1))

        self.assertEqual(
            decimal_of(self.draft_of(client, month=2).total), Decimal("150.00"),
        )

    def test_a_start_on_the_first_bills_the_whole_month(self):
        client = self.make_client()
        self.subscribe(client, "300", datetime.date(2026, 2, 1))

        self.refresh(datetime.date(2026, 2, 1))

        draft = self.draft_of(client, month=2)
        self.assertEqual(decimal_of(draft.total), Decimal("300.00"))
        self.assertEqual(
            list(draft.lines.values_list("label", flat=True)),
            [fees.SUBSCRIPTION_LINE_LABEL],
        )

    def test_an_open_pause_bills_nothing(self):
        client = self.make_client()
        self.subscribe(
            client, "300", datetime.date(2026, 1, 1),
            paused_from=MAR_FIRST, paused_to=None,
        )

        self.refresh(MAR_FIRST)
        self.refresh(APRIL_FIRST)

        self.assertEqual(self.draft_ids(), [])

    def test_a_pause_that_ends_on_the_last_day_of_the_previous_month_still_bills(self):
        client = self.make_client()
        self.subscribe(
            client, "300", datetime.date(2026, 1, 1),
            paused_from=datetime.date(2026, 2, 1),
            paused_to=datetime.date(2026, 3, 31),
        )

        self.refresh(APRIL_FIRST)

        self.assertEqual(
            decimal_of(self.draft_of(client, month=4).total), Decimal("300.00"),
        )


class ServicePriceApiTest(FeesTestCase):
    """نقطةُ أسعار الخدمات `fees/service-prices/`.

    `per_service` كانت تُختار بلا مدخلٍ لسعر الخدمة، فكلُّ مسودّات المكتب تتوقّف
    بصمت. النقطةُ تُدخل السعرَ بالمعرّف الخدميّ أو بالخدمة والزبون، والقناعُ
    والرؤيةُ كمّا في الاشتراكات، ولا حذفَ ولا تعديلَ (إعادةُ التسعير `POST`).
    """

    def setUp(self):
        super().setUp()
        services.set_office_setting(self.tenant, "fee_method", "per_service")
        self.priced_client = self.make_client("زبون الأسعار")
        self.service = services.ensure_default_services(self.tenant)[0]
        self.client_service = services.add_client_service(
            client=self.priced_client,
            service=self.service,
            starts_on=datetime.date(2026, 1, 1),
            responsible_from=datetime.date(2026, 1, 1),
            frequency="monthly",
        )

    def add_price(self, body):
        return self.client.post(
            SERVICE_PRICES, body, format="json", **self.headers(),
        )

    def test_the_owner_adds_a_price_by_client_service_and_reads_it_back(self):
        created = self.add_price(
            {"client_service": self.client_service.pk, "amount": "120.00"},
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(decimal_of(created.data["amount"]), Decimal("120.00"))
        self.assertEqual(created.data["client"]["id"], self.priced_client.pk)
        self.assertEqual(created.data["service"]["id"], self.service.pk)
        self.assertEqual(created.data["client_service"], self.client_service.pk)

        listed = self.client.get(SERVICE_PRICES, **self.headers())
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual([row["id"] for row in listed.data], [created.data["id"]])

    def test_a_price_may_be_added_by_service_and_client_and_reposting_updates_it(self):
        created = self.add_price(
            {
                "service": self.service.pk,
                "client": self.priced_client.pk,
                "amount": "90.00",
            },
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(
            ClientServicePrice.objects.get().client_service_id, self.client_service.pk,
        )

        # صفٌّ واحدٌ للخدمة (OneToOne): إعادةُ التسعير تُحدِّثه ولا تُضاعفه.
        again = self.add_price(
            {"client_service": self.client_service.pk, "amount": "95.00"},
        )
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(ClientServicePrice.objects.count(), 1)
        self.assertEqual(
            decimal_of(ClientServicePrice.objects.get().amount), Decimal("95.00"),
        )

    def test_a_member_without_the_clients_write_key_is_refused(self):
        staff = User.objects.create_user(username="fees_prices_staff", password="x")
        UserCompanyMembership.objects.create(
            user=staff, tenant=self.tenant, role="staff",
        )
        self.as_user(staff)

        refused = self.add_price(
            {"client_service": self.client_service.pk, "amount": "120.00"},
        )
        self.assertEqual(refused.status_code, 403, refused.content)
        self.assertFalse(ClientServicePrice.objects.exists())

    def test_another_office_client_service_is_404(self):
        other_owner = User.objects.create_user(username="fees_prices_other", password="x")
        other_tenant = create_company("مكتب أسعار آخر", other_owner, template="accounting_office")
        invalidate_module_cache(other_tenant.pk)
        services.set_office_setting(other_tenant, "tax_system", "PS")
        services.set_office_setting(other_tenant, "office_size", "small")
        foreign = OfficeClient.objects.create(tenant=other_tenant, name="زبون غيري")
        TaxCard.objects.create(client=foreign)
        foreign_service = services.add_client_service(
            client=foreign,
            service=services.ensure_default_services(other_tenant)[0],
            starts_on=datetime.date(2026, 1, 1),
            responsible_from=datetime.date(2026, 1, 1),
            frequency="monthly",
        )

        self.assertEqual(self.client.get(SERVICE_PRICES, **self.headers()).data, [])
        refused = self.add_price(
            {"client_service": foreign_service.pk, "amount": "120.00"},
        )
        self.assertEqual(refused.status_code, 404, refused.content)
        self.assertFalse(ClientServicePrice.objects.exists())

    def test_the_amount_is_masked_and_cannot_be_written_without_the_amounts_key(self):
        created = self.add_price(
            {"client_service": self.client_service.pk, "amount": "120.00"},
        )
        self.assertEqual(created.status_code, 201, created.content)
        # الزبونُ للمحاسب فيراه، والمبلغُ لا يملك مفتاحَه.
        OfficeClient.objects.filter(pk=self.priced_client.pk).update(
            responsible=self.accountant_user,
        )
        self.as_user(self.accountant_user)

        listed = self.client.get(SERVICE_PRICES, **self.headers())
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertTrue(listed.data, "سعرُ خدمةِ زبونٍ يراه العضو لا يظهر له")
        self.assertIsNone(listed.data[0]["amount"])

        refused = self.add_price(
            {"client_service": self.client_service.pk, "amount": "130.00"},
        )
        self.assertEqual(refused.status_code, 403, refused.content)
        self.assertEqual(
            decimal_of(ClientServicePrice.objects.get().amount), Decimal("120.00"),
        )

    def test_no_delete_on_the_service_prices(self):
        self.assertEqual(
            self.client.delete(SERVICE_PRICES, **self.headers()).status_code, 405,
        )

    def test_a_draft_is_generated_from_a_price_entered_through_the_api(self):
        created = self.add_price(
            {"client_service": self.client_service.pk, "amount": "120.00"},
        )
        self.assertEqual(created.status_code, 201, created.content)

        self.refresh(MAR_FIRST)

        draft = self.draft_of(self.priced_client)
        self.assertEqual(decimal_of(draft.total), Decimal("120.00"))
        self.assertEqual(
            [
                (label, decimal_of(amount))
                for label, amount in draft.lines.values_list("label", "amount")
            ],
            [(self.service.name, Decimal("120.00"))],
        )


class GenerationCostTest(FeesTestCase):
    """كلفةُ التوليد لا تكبر بعدد من له مسودّة، ولا بنودَ مسودّةٍ تُقرأ واحدةً واحدة."""

    def test_a_second_run_of_the_same_month_does_not_query_per_draft_owner(self):
        # التوليدُ يُقاس وحده لا عبر `refresh_office`: ذاك يحفظ التزاماتٍ وشغلاتٍ
        # لكل زبونٍ فتُخفى كلفةُ الأتعاب بين استعلاماته.
        first = self.make_client("زبون أول")
        self.subscribe(first, "300", datetime.date(2026, 1, 1))
        self.refresh(MAR_FIRST)

        with CaptureQueriesContext(connection) as one:
            self.assertEqual(
                fees.generate_fee_drafts(self.tenant, day=MAR_FIRST)["created_drafts"], 0,
            )

        for index in range(3):
            extra = self.make_client(f"زبون {index}")
            self.subscribe(extra, "300", datetime.date(2026, 1, 1))
            self.refresh(MAR_FIRST)

        with CaptureQueriesContext(connection) as four:
            self.assertEqual(
                fees.generate_fee_drafts(self.tenant, day=MAR_FIRST)["created_drafts"], 0,
            )

        self.assertEqual(
            len(four.captured_queries), len(one.captured_queries),
            "كلفةُ التوليد كبرت بعدد أصحاب المسودّات — استعلامٌ لكل زبون",
        )

    def test_approve_all_does_not_read_the_lines_of_each_draft_separately(self):
        """**العنوانُ هو القياس**: «اعتمد الكل» لا يقرأ بنودَ المسودّات واحدةً واحدة.

        كان القياسُ مجموعَ الاستعلامات كلِّها (١ مقابل ٣ مسودّات)، فسقط — كما
        يجب — يوم أُضيف ترحيلُ قيدِ دفاترٍ **لكل فاتورة** (#284/ب): نموٌّ مقصودٌ
        بعدد الفواتير لا بعدد المسودّات، وثمنُ «لا فاتورةَ مرقَّمةً بلا قيدها».
        فيقيس الاختبارُ اليومَ ما يسمّيه: قراءاتُ جدول بنود المسودّات وحدها —
        تُعدّ استعلاماتٍ تذكر `FeeDraftLine`، ويُشترط ألّا يتغيّر عددُها بعدد
        المسودّات. سقوطُ `prefetch_related` يجعلها استعلاماً لكل مسودّة فيسقط.
        """
        line_table = FeeDraftLine._meta.db_table

        def approve_all_and_count_line_reads():
            with CaptureQueriesContext(connection) as captured:
                res = self.client.post(
                    f"{DRAFTS}approve-all/", {}, format="json", **self.headers(),
                )
            self.assertEqual(res.status_code, 200, res.content)
            return res, [
                query["sql"] for query in captured.captured_queries
                if line_table in query["sql"]
            ]

        def pending(name):
            client = self.make_client(name)
            self.subscribe(client, "300", datetime.date(2026, 1, 1))
            self.refresh(MAR_FIRST)
            return client

        pending("زبون أول")
        one_res, one_reads = approve_all_and_count_line_reads()
        self.assertEqual(one_res.data["approved"], 1)

        for index in range(3):
            pending(f"زبون {index}")
        four_res, four_reads = approve_all_and_count_line_reads()
        self.assertEqual(four_res.data["approved"], 3)
        self.assertTrue(all(row["lines"] for row in four_res.data["drafts"]))

        self.assertEqual(
            len(four_reads), len(one_reads),
            "«اعتمد الكل» يقرأ بنودَ المسودّات واحدةً واحدة — بلا `prefetch_related`",
        )


class MemberVisibilityTest(FeesTestCase):
    """محاسبٌ يرى زبونَه وحده من زبونَي المكتب نفسه."""

    def test_the_three_lists_show_only_his_client_and_a_colleagues_post_is_404(self):
        mine = self.make_client("زبون المحاسب", responsible=self.accountant_user)
        colleagues = self.make_client("زبون الزميل", responsible=self.owner)
        my_subscription = self.subscribe(mine, "300", datetime.date(2026, 1, 1))
        self.subscribe(colleagues, "350", datetime.date(2026, 1, 1))
        my_extra = FeeExtraService.objects.create(
            tenant=self.tenant, client=mine, service_name="تصديق شهادة",
            amount=Decimal("50"), performed_on=datetime.date(2026, 3, 10),
        )
        FeeExtraService.objects.create(
            tenant=self.tenant, client=colleagues, service_name="خدمة الزميل",
            amount=Decimal("70"), performed_on=datetime.date(2026, 3, 11),
        )
        self.refresh(MAR_FIRST)

        self.as_user(self.accountant_user)
        subscriptions = self.client.get(SUBSCRIPTIONS, **self.headers())
        self.assertEqual([row["id"] for row in subscriptions.data], [my_subscription.pk])
        drafts = self.client.get(DRAFTS, **self.headers())
        self.assertEqual([row["client"]["id"] for row in drafts.data], [mine.pk])
        extras = self.client.get(EXTRAS, **self.headers())
        self.assertEqual([row["id"] for row in extras.data], [my_extra.pk])

        refused_subscription = self.client.post(
            SUBSCRIPTIONS,
            {"client": colleagues.pk, "amount": "300.00", "starts_on": "2026-02-01"},
            format="json", **self.headers(),
        )
        self.assertEqual(refused_subscription.status_code, 404, refused_subscription.content)
        refused_extra = self.client.post(
            EXTRAS,
            {
                "client": colleagues.pk,
                "service_name": "خدمة",
                "amount": "10.00",
                "performed_on": "2026-03-10",
            },
            format="json", **self.headers(),
        )
        self.assertEqual(refused_extra.status_code, 404, refused_extra.content)
