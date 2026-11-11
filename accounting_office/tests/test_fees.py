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

from django.contrib.auth.models import User
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

    def test_no_collection_accepts_delete(self):
        for path in (SUBSCRIPTIONS, DRAFTS, EXTRAS):
            with self.subTest(path=path):
                self.assertEqual(
                    self.client.delete(path, **self.headers()).status_code, 405,
                )

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
