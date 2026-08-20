"""CHQ-3 — جدول استحقاق الشيكات، وقيدُ كل خطوة في سجلّ الشيك.

قبل هذا: `cheque_wallet` يعطي دلاءً (متأخر / 7 / 30 / لاحقاً) — لا جدولاً
زمنياً مؤرَّخاً ولا صافياً تراكمياً، فالمالك يرى «كم» ولا يرى **متى** ولا أثر
ذلك على سيولته. وسجلّ حركات الشيك يقول «ماذا ومتى ومَن» ولا يقول «أي قيد»،
والواجهة تكرّر جدول الانتقالات وتسمياته محلياً (`movesFor` في
`AccountingChequesPage.tsx`) فيمكن للنسختين أن تفترقا بصمت.

يثبت:
  1. صفوف التقرير أسبوعاً بأسبوع **بأرقامها** وبصافيها التراكمي، والمتأخر
     أولاً وما بعد الأفق آخراً، وبلا تاريخ استحقاق خارج الخطّ الزمني.
  2. أرقام التقرير هي أرقام المحفظة نفسها — لا صيغة ثانية.
  3. الشيكات المغلقة وشيكات شركة أخرى خارج التقرير.
  4. `allowed_movements` يطابق جدولَي الخدمات لكل (حالة، اتجاه) — فلا تدرّج
     بين الخادم والواجهة.
  5. `status_label` يختلف باختلاف الاتجاه (الصادر «مصروف» لا «محصَّل»).
  6. سجلّ الحركات يحمل رقم القيد ومرجعه — وبلا أي مبلغ للقيد (THA-489: سند
     موزَّع على فاتورتين يُنتج قيدين، فمبلغ القيد قد لا يساوي مبلغ الشيك؛
     عرضه بجانب مبلغ الشيك يكذب على القارئ).
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque, ChequeMovement, JournalHeader
from accounting.serializers import ChequeSerializer
from accounting.services import (
    INCOMING_TRANSITIONS,
    OUTGOING_TRANSITIONS,
    cheque_maturity_timeline,
    cheque_wallet,
    create_fiscal_year,
    transitions_for,
)
from core.reports import run_report
from partners.models import Partner
from sales.models import SalesSettings, SupplierPayment
from tenants.models import Currency, Tenant
from tenants.services import create_company

AS_OF = datetime.date(2026, 3, 2)


def _d(offset):
    return AS_OF + datetime.timedelta(days=offset)


class ChequeMaturityReportTest(APITestCase):
    """التقرير المسجَّل `cheques-maturity` — أرقامه، لا مجرد استجابته."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chqmat", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الاستحقاق", cls.user)
        cls.other = create_company("شركة أخرى", cls.user)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل الاستحقاق", partner_type="Customer")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد الاستحقاق", partner_type="Supplier")

        def chq(tenant, direction, due, amount, status="Received"):
            return Cheque.objects.create(
                tenant=tenant, cheque_number=f"M-{Cheque.objects.count() + 1}",
                amount=Decimal(amount), currency=cls.ils, due_date=due,
                direction=direction, status=status,
            )

        chq(cls.tenant, "Incoming", _d(-10), "100.00")             # متأخر
        chq(cls.tenant, "Incoming", _d(0), "200.00")               # أسبوع 1
        chq(cls.tenant, "Incoming", _d(6), "50.00", "Under_Collection")
        chq(cls.tenant, "Outgoing", _d(3), "500.00", "Under_Collection")
        chq(cls.tenant, "Incoming", _d(7), "300.00")               # أسبوع 2
        chq(cls.tenant, "Outgoing", _d(20), "120.00", "Under_Collection")  # أسبوع 3
        chq(cls.tenant, "Incoming", _d(90), "400.00")              # أسبوع 13 — آخر يوم
        chq(cls.tenant, "Incoming", _d(91), "999.00")              # بعد الأفق
        chq(cls.tenant, "Incoming", None, "77.00")                 # بلا استحقاق
        # مغلق — خارج المحفظة وخارج التقرير.
        chq(cls.tenant, "Incoming", _d(2), "10000.00", "Collected")
        # شركة أخرى — لا تسرّب.
        chq(cls.other, "Incoming", _d(2), "8888.00")

    def _rows(self):
        return run_report("cheques-maturity", self.tenant.TenantID,
                          {"as_of": AS_OF.isoformat()})

    def test_weekly_rows_and_cumulative_net_are_numerically_exact(self):
        result = self._rows()
        rows = {r["period_key"]: r for r in result["rows"]}
        # متأخر + 13 أسبوعاً + ما بعد الأفق + بلا تاريخ = 16 صفاً.
        assert len(result["rows"]) == 16, result["rows"]

        assert (rows["overdue"]["incoming"], rows["overdue"]["outgoing"]) == ("100.00", "0.00")
        assert rows["overdue"]["net"] == "100.00"
        assert rows["overdue"]["cumulative_net"] == "100.00"

        # الأسبوع الأول: 200 + 50 وارد، 500 صادر ⇒ صافٍ سالب والتراكمي ينقلب.
        assert rows["w1"]["incoming"] == "250.00"
        assert rows["w1"]["outgoing"] == "500.00"
        assert rows["w1"]["net"] == "-250.00"
        assert rows["w1"]["cumulative_net"] == "-150.00"
        assert (rows["w1"]["incoming_count"], rows["w1"]["outgoing_count"]) == (2, 1)

        assert rows["w2"]["net"] == "300.00"
        assert rows["w2"]["cumulative_net"] == "150.00"
        assert rows["w3"]["net"] == "-120.00"
        assert rows["w3"]["cumulative_net"] == "30.00"
        # أسابيع فارغة تظهر بأصفار — الخطّ الزمني بلا ثقوب.
        assert rows["w4"]["net"] == "0.00"
        assert rows["w4"]["cumulative_net"] == "30.00"
        # اليوم 90 داخل الأفق (الأسبوع 13)، واليوم 91 خارجه.
        assert rows["w13"]["incoming"] == "400.00"
        assert rows["w13"]["cumulative_net"] == "430.00"
        assert rows["beyond"]["incoming"] == "999.00"
        assert rows["beyond"]["cumulative_net"] == "1429.00"

        # بلا تاريخ استحقاق: مبلغه يُعرض، وخانة التراكمي فارغة — ورقةٌ بلا
        # تاريخ لا موضع لها على خطّ زمني، والفراغ أصدق من رقم مفتعل.
        assert rows["no_due_date"]["incoming"] == "77.00"
        assert rows["no_due_date"]["cumulative_net"] == ""
        assert rows["no_due_date"]["due_from"] is None

        assert result["totals"]["net"] == "1506.00"
        assert result["totals"]["incoming"] == "2126.00"
        assert result["totals"]["outgoing"] == "620.00"

    def test_report_and_wallet_agree_because_the_number_is_computed_once(self):
        result = self._rows()
        wallet = cheque_wallet(self.tenant.TenantID)
        assert result["totals"]["incoming"] == wallet["incoming"]["open_total"]
        assert result["totals"]["outgoing"] == wallet["outgoing"]["open_total"]

    def test_closed_cheques_and_other_tenants_are_absent(self):
        result = self._rows()
        amounts = {r["incoming"] for r in result["rows"]} | {
            r["outgoing"] for r in result["rows"]}
        assert "10000.00" not in amounts
        assert "8888.00" not in amounts
        # والشركة الأخرى ترى شيكها وحده.
        other = run_report("cheques-maturity", self.other.TenantID,
                           {"as_of": AS_OF.isoformat()})
        assert other["totals"]["incoming"] == "8888.00"

    def test_row_boundaries_are_inclusive_at_both_ends_of_a_week(self):
        data = cheque_maturity_timeline(self.tenant.TenantID, today=AS_OF)
        by_key = {r["key"]: r for r in data["rows"]}
        assert by_key["w1"]["from"] == AS_OF
        assert by_key["w1"]["to"] == _d(6)
        assert by_key["w13"]["to"] == _d(90)
        assert by_key["overdue"]["to"] == _d(-1)
        assert by_key["beyond"]["from"] == _d(91)


class ChequeSerializerContractTest(APITestCase):
    """الخادم هو مصدر الانتقالات والتسميات — لا نسخة ثانية في الواجهة."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chqser", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة التسميات", cls.user)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل التسميات", partner_type="Customer")
        cls.cheque = Cheque.objects.create(
            tenant=cls.tenant, cheque_number="LBL-1", amount=Decimal("100.00"),
            currency=cls.ils, due_date=AS_OF, direction="Incoming", status="Draft",
            partner=cls.customer,
        )

    def test_allowed_movements_equals_the_services_table_for_every_pair(self):
        for direction, table in (("Incoming", INCOMING_TRANSITIONS),
                                 ("Outgoing", OUTGOING_TRANSITIONS)):
            for status, _label in Cheque.STATUS_CHOICES:
                self.cheque.direction = direction
                self.cheque.status = status
                data = ChequeSerializer(self.cheque).data
                values = {m["value"] for m in data["allowed_movements"]}
                assert values == table[status], (direction, status, values)
                assert values == transitions_for(direction)[status]
                for move in data["allowed_movements"]:
                    assert move["label"] and move["label"] != move["value"], move

    def test_bank_account_and_endorsee_requirements_travel_with_the_movement(self):
        self.cheque.direction = "Incoming"
        self.cheque.status = "Received"
        moves = {m["value"]: m for m in ChequeSerializer(self.cheque).data["allowed_movements"]}
        assert moves["collect"]["requires_bank_account"] is True
        assert moves["deposit"]["requires_bank_account"] is False
        assert moves["endorse"]["requires_endorsee"] is True
        assert moves["collect"]["requires_endorsee"] is False

    def test_status_label_reads_the_direction_not_only_the_code(self):
        self.cheque.direction = "Incoming"
        self.cheque.status = "Collected"
        incoming = ChequeSerializer(self.cheque).data["status_label"]
        self.cheque.direction = "Outgoing"
        outgoing = ChequeSerializer(self.cheque).data["status_label"]
        assert incoming != outgoing, (incoming, outgoing)
        assert incoming == "محصَّل"
        assert outgoing == "مصروف"

        self.cheque.status = "Under_Collection"
        assert ChequeSerializer(self.cheque).data["status_label"] == "مسلَّم — بانتظار الصرف"


class ChequeMovementJournalLinkTest(APITestCase):
    """سجلّ الشيك يقول أي قيد أنتجته كل خطوة — بلا مبلغٍ للقيد (THA-489)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chqjrn", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة سجل الشيك", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد السجل", partner_type="Supplier")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant, defaults={"default_cash_account": cls.cash},
        )
        cls.payment = SupplierPayment.objects.create(
            tenant=cls.tenant, partner=cls.supplier, currency=cls.ils,
            payment_date="2026-06-11", amount=Decimal("400.00"),
            cash_or_bank_account=cls.cash, is_posted=True,
        )
        cls.cheque = Cheque.objects.create(
            tenant=cls.tenant, cheque_number="JRN-1", amount=Decimal("400.00"),
            currency=cls.ils, partner=cls.supplier, direction="Outgoing",
            status="Under_Collection", supplier_payment=cls.payment,
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_movement_log_carries_its_journal_number_and_no_journal_amount(self):
        headers = self._auth()
        res = self.client.post(
            f"/api/accounting/cheques/{self.cheque.pk}/transfer/",
            {"movement_type": "collect", "movement_date": "2026-06-11"},
            format="json", **headers)
        assert res.status_code == 200, res.content

        movement = ChequeMovement.objects.get(cheque=self.cheque, movement_type="collect")
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_COLLECT", reference_id=movement.pk)

        log = self.client.get(
            f"/api/accounting/cheques/{self.cheque.pk}/movements/", **headers)
        assert log.status_code == 200, log.content
        row = next(r for r in log.json() if r["movement_type"] == "collect")
        assert row["journal"] == jh.pk
        assert row["journal_number"] == f"#{jh.pk}"
        assert row["journal_reference"] == "CHEQUE_COLLECT"
        assert row["journal_date"] == "2026-06-11"
        # التسمية بدلالة الاتجاه — «صرف من حسابنا» لا «تحصيل».
        assert row["movement_type_label"] == "صُرف من حسابنا — إغلاق الالتزام"

        # THA-489: سند موزَّع على فاتورتين يشقّ مبلغ الشيك على قيدين، فمبلغ
        # القيد قد لا يساوي مبلغ الشيك. السجلّ يربط ولا يزعم المساواة —
        # لا مبلغ للقيد في الحمولة أصلاً.
        assert not [k for k in row if "amount" in k], row

    def test_a_movement_without_a_journal_says_so_instead_of_faking_one(self):
        movement = ChequeMovement.objects.create(
            cheque=self.cheque, movement_type="issue", notes="ترحيل السند")
        log = self.client.get(
            f"/api/accounting/cheques/{self.cheque.pk}/movements/", **self._auth())
        row = next(r for r in log.json() if r["id"] == movement.pk)
        assert row["journal"] is None
        assert row["journal_number"] is None
        assert row["movement_type_label"] == "تسليم الشيك للمورد"
