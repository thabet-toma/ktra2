"""THA-60/م2: تكلفة المبيع في «حسب المنتج» و«حسب الماركة» تاريخية لا لحظية.

الجذر الذي تحرسه هذه الاختبارات: التقريران كانا يحسبان التكلفة `الكمية ×
avg_cost` — متوسط **اليوم** — فكل فاتورة شراء لاحقة تحرّك ربح فواتير مضت
ورُحّلت. المصدر الصحيح حركة المخزون المسجَّلة لحظة الترحيل (`sales_cogs_map`).

ثلاثة عقود:
  A ثبات تاريخي — شراء لاحق يرفع المتوسط ولا يمسّ ربحاً مُعلَناً.
  B تكافؤ — Σ ربح المنتجات == ربح «أرباح الفواتير» على الفواتير نفسها.
  C إعلان — ما لا حركة له يظهر في «كمية بلا تكلفة»، لا صفراً صامتاً.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from core.reports import REPORTS
from inventory.models import Product, StockMovement
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import invoice_profits
from tenants.models import Currency
from tenants.services import create_company

PARAMS = {"from": "2026-01-01", "to": "2026-12-31"}


class SalesCogsHistoricalTest(TestCase):
    """التكلفة تُقرأ من الحركة، فلا يحرّكها شراء لاحق."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="cogs-reporter", password="x")
        cls.currency, _ = Currency.objects.get_or_create(
            Code="CGS", defaults={"Name": "Cogs", "Symbol": "C"})
        cls.tenant = create_company("شركة تكلفة المبيع", cls.user)
        cls.tid = cls.tenant.TenantID
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون التكلفة", partner_type="Customer")

    # ── أدوات بناء ────────────────────────────────────────────────────
    def _product(self, sku, *, avg_cost="10", brand="ماركة أ", is_service=False):
        return Product.objects.create(
            tenant=self.tenant, sku=sku, name_ar=f"منتج {sku}", brand=brand,
            quantity_on_hand=Decimal("100"), avg_cost=Decimal(avg_cost),
            is_service=is_service,
        )

    def _invoice(self, number, *, subtotal, discount="0"):
        return SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, customer=self.customer,
            currency=self.currency, invoice_date="2026-06-10",
            invoice_type=SalesInvoice.INVOICE_CREDIT,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
            status=SalesInvoice.STATUS_POSTED,
            subtotal_excl_tax=Decimal(subtotal),
            invoice_discount=Decimal(discount),
            grand_total=Decimal(subtotal) - Decimal(discount),
        )

    def _line(self, invoice, product, *, qty, net):
        return SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=invoice, product=product,
            quantity=Decimal(qty), unit_price=Decimal(net) / Decimal(qty),
            line_total_excl_tax=Decimal(net), line_tax_amount=Decimal("0"),
        )

    def _movement(self, invoice, product, *, qty, total_cost):
        """حركة صرف البيع كما يكتبها الترحيل: كمية موجبة وتكلفة لحظتها."""
        return StockMovement.objects.create(
            tenant=self.tenant, product=product, movement_type="OUT",
            quantity=Decimal(qty), unit_cost=Decimal(total_cost) / Decimal(qty),
            total_cost=Decimal(total_cost), reference_type="SALE",
            reference_id=invoice.id, movement_date="2026-06-10",
        )

    def _rows(self, key="sales-by-product"):
        return REPORTS[key].build(self.tid, dict(PARAMS))

    def _row_for(self, sku, key="sales-by-product"):
        rows = [r for r in self._rows(key) if r["sku"] == sku]
        self.assertEqual(len(rows), 1, f"صف واحد متوقَّع لـ{sku}، وُجد {len(rows)}")
        return rows[0]

    # ── A: ثبات الربح التاريخي ────────────────────────────────────────
    def test_later_purchase_does_not_move_a_posted_invoice_profit(self):
        """شراء 10@10 ⇒ بيع 5@20 ⇒ ربح 50؛ شراء لاحق @30 لا يغيّره."""
        product = self._product("CGS-A", avg_cost="10")
        invoice = self._invoice("SI-CGS-A", subtotal="100")
        self._line(invoice, product, qty="5", net="100")
        self._movement(invoice, product, qty="5", total_cost="50")

        before = self._row_for("CGS-A")
        self.assertEqual(Decimal(before["cost"]), Decimal("50.00"))
        self.assertEqual(Decimal(before["profit"]), Decimal("50.00"))

        # فاتورة شراء لاحقة بسعر أعلى ترفع متوسط التكلفة — هذا كل ما تفعله.
        product.avg_cost = Decimal("30")
        product.save(update_fields=["avg_cost"])

        after = self._row_for("CGS-A")
        self.assertEqual(
            Decimal(after["cost"]), Decimal("50.00"),
            "تكلفة المبيع تاريخية — لا يحرّكها شراء بعد الترحيل")
        self.assertEqual(Decimal(after["profit"]), Decimal("50.00"))

    def test_brand_report_is_historical_too(self):
        """«حسب الماركة» يقرأ القاعدة نفسها — لا صيغة ثانية."""
        product = self._product("CGS-B", avg_cost="10", brand="ماركة ب")
        invoice = self._invoice("SI-CGS-B", subtotal="100")
        self._line(invoice, product, qty="5", net="100")
        self._movement(invoice, product, qty="5", total_cost="50")

        product.avg_cost = Decimal("30")
        product.save(update_fields=["avg_cost"])

        rows = [r for r in self._rows("sales-by-brand") if r["name"] == "ماركة ب"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(Decimal(rows[0]["cost"]), Decimal("50.00"))
        self.assertEqual(Decimal(rows[0]["profit"]), Decimal("50.00"))

    # ── B: تكافؤ مع «أرباح الفواتير» ──────────────────────────────────
    def test_product_profit_sum_matches_invoice_profits(self):
        """خصم فاتورة موزَّع تناسبياً ⇒ مساواة تامة بين التقريرين."""
        p1 = self._product("CGS-C1", avg_cost="7")
        p2 = self._product("CGS-C2", avg_cost="9")
        invoice = self._invoice("SI-CGS-C", subtotal="100", discount="10")
        self._line(invoice, p1, qty="6", net="60")
        self._line(invoice, p2, qty="4", net="40")
        self._movement(invoice, p1, qty="6", total_cost="30")
        self._movement(invoice, p2, qty="4", total_cost="20")

        rows = [r for r in self._rows() if r["sku"].startswith("CGS-C")]
        self.assertEqual(len(rows), 2)
        # صافي السطر = السطر − نصيبه من خصم الفاتورة (60% و40%).
        by_sku = {r["sku"]: r for r in rows}
        self.assertEqual(Decimal(by_sku["CGS-C1"]["net_sales"]), Decimal("54.00"))
        self.assertEqual(Decimal(by_sku["CGS-C2"]["net_sales"]), Decimal("36.00"))

        summed = sum(Decimal(r["profit"]) for r in rows)
        totals = invoice_profits(tenant_id=self.tid, **{
            "date_from": PARAMS["from"], "date_to": PARAMS["to"]})["totals"]
        self.assertEqual(summed, Decimal(totals["profit"]),
                         "رقما ربح مختلفان في المنصة أسوأ من رقم واحد ناقص")
        self.assertEqual(summed, Decimal("40.00"))

    def test_line_sum_equals_invoice_subtotal_assumption(self):
        """افتراض الخطة: Σ line_total_excl_tax == subtotal_excl_tax."""
        p1 = self._product("CGS-D1")
        p2 = self._product("CGS-D2")
        invoice = self._invoice("SI-CGS-D", subtotal="100", discount="10")
        self._line(invoice, p1, qty="6", net="60")
        self._line(invoice, p2, qty="4", net="40")
        lines_total = sum(
            l.line_total_excl_tax for l in invoice.lines.all())
        self.assertEqual(lines_total, invoice.subtotal_excl_tax)

    # ── C: إعلان ما لا تكلفة له ───────────────────────────────────────
    def test_invoice_without_movements_declares_uncosted_quantity(self):
        """مستورَد بلا حركات ⇒ الكمية تُعلَن، لا تكلفة صفر صامتة."""
        product = self._product("CGS-E", avg_cost="10")
        invoice = self._invoice("SI-CGS-E", subtotal="100")
        self._line(invoice, product, qty="5", net="100")
        # لا حركة مخزون البتة — محاكاة صفوف SQL خام المستورَدة.

        row = self._row_for("CGS-E")
        self.assertEqual(Decimal(row["cost"]), Decimal("0.00"))
        self.assertEqual(Decimal(row["uncosted_qty"]), Decimal("5"),
                         "الكمية بلا مصدر تكلفة تُعلَن كما هي")

    def test_service_line_is_not_counted_as_uncosted(self):
        """الخدمة بلا تكلفة بحقّ — لا تُعدّ نقصاً في الإعلان."""
        service = self._product("CGS-F", is_service=True)
        invoice = self._invoice("SI-CGS-F", subtotal="100")
        self._line(invoice, service, qty="3", net="100")

        row = self._row_for("CGS-F")
        self.assertEqual(Decimal(row["uncosted_qty"]), Decimal("0"))

    def test_partially_delivered_invoice_declares_the_remainder(self):
        """سُلّم بعضه ⇒ التكلفة المعترَفة جزئية والباقي مُعلَن."""
        product = self._product("CGS-G", avg_cost="10")
        invoice = self._invoice("SI-CGS-G", subtotal="100")
        self._line(invoice, product, qty="5", net="100")
        self._movement(invoice, product, qty="2", total_cost="20")

        row = self._row_for("CGS-G")
        self.assertEqual(Decimal(row["cost"]), Decimal("20.00"))
        self.assertEqual(Decimal(row["uncosted_qty"]), Decimal("3"))

    def test_uncosted_never_goes_negative(self):
        """حركات أكثر من الكمية (تسليم زائد/بيانات قديمة) ⇒ صفر لا سالب."""
        product = self._product("CGS-H", avg_cost="10")
        invoice = self._invoice("SI-CGS-H", subtotal="100")
        self._line(invoice, product, qty="5", net="100")
        self._movement(invoice, product, qty="8", total_cost="80")

        row = self._row_for("CGS-H")
        self.assertEqual(Decimal(row["uncosted_qty"]), Decimal("0"))
