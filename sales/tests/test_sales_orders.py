"""طلبيات الزبائن (SalesOrder) — الحلقة الناقصة بين عرض السعر والفاتورة.

الثوابت التي يحرسها هذا الملف:
1. **الطلبية ليست قيداً**: تأكيدها لا يُنشئ أي قيد يومية — القيد يبدأ من الفاتورة.
2. **الحجز مشتقّ لا مخزَّن**: الكمية المحجوزة تُحسب من طلبيات مؤكَّدة لم ينتهِ
   حجزها، فلا عمود ثانٍ يفسد المخزون، والانتهاء يحرّر الكمية بلا مهمة خلفية.
3. **الإلغاء لا يحذف**: المستند يبقى بحالة «ملغاة» ويُفرَج عن حجزه.
4. **العربون سند قبض حقيقي**: «على الحساب» مربوط بالطلبية، لا حقل رقمي معلّق.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounting.models import Account, FiscalPeriod, JournalHeader
from core.models import ActivityLog
from inventory.models import Product
from partners.models import Partner
from sales.models import (
    CustomerPayment,
    SalesOrder,
    SalesQuotation,
    SalesQuotationLine,
    SalesSettings,
)
from sales.services import (
    cancel_sales_order,
    cancel_quotation,
    confirm_sales_order,
    convert_order_to_invoice,
    convert_quotation_to_order,
    default_quotation_valid_until,
    record_order_deposit,
    reserved_quantity_map,
)
from tenants.models import Currency, Tenant, UserCompanyMembership


class SalesOrderFlowTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="order-boss", password="x")
        cls.tenant = Tenant.objects.create(TenantID=161, CompanyName="Orders Co")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110", name="صندوق", account_type="Asset", is_active=True)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101", name="ذمم عملاء", account_type="Asset", is_active=True)
        Account.objects.create(
            tenant=cls.tenant, code="4101", name="إيرادات", account_type="Revenue", is_active=True)
        Account.objects.create(
            tenant=cls.tenant, code="2101", name="ضريبة", account_type="Liability", is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون الطلبيات", partner_type="Customer",
            linked_account=cls.ar)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="ORD-1", name_ar="منتج", quantity_on_hand=Decimal("20"),
            is_service=True)
        FiscalPeriod.objects.create(
            tenant=cls.tenant, name="2026", start_date="2026-01-01",
            end_date="2026-12-31", is_closed=False)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _quotation(self, qty="5", price="100"):
        q = SalesQuotation.objects.create(
            tenant=self.tenant, quotation_number=f"Q-{SalesQuotation.objects.count() + 1}",
            customer=self.customer, quotation_date=date(2026, 7, 1),
            currency=self.currency, grand_total=Decimal(qty) * Decimal(price),
        )
        SalesQuotationLine.objects.create(
            tenant=self.tenant, quotation=q, product=self.product,
            quantity=Decimal(qty), unit_price=Decimal(price),
        )
        return q

    # ── صلاحية العرض ────────────────────────────────────────────────────
    def test_quotation_validity_defaults_to_two_weeks(self):
        assert default_quotation_valid_until(
            self.tenant.TenantID, date(2026, 7, 1)) == date(2026, 7, 15)

    def test_quotation_validity_follows_the_company_setting(self):
        SalesSettings.objects.update_or_create(
            tenant=self.tenant, defaults={"quotation_valid_days": 30})
        assert default_quotation_valid_until(
            self.tenant.TenantID, date(2026, 7, 1)) == date(2026, 7, 31)

    # ── عرض ← طلبية ─────────────────────────────────────────────────────
    def test_quotation_converts_to_order_with_its_lines(self):
        q = self._quotation(qty="5", price="100")
        order = convert_quotation_to_order(q, user=self.user)
        q.refresh_from_db()
        assert q.status == SalesQuotation.STATUS_CONVERTED
        assert order.quotation_id == q.pk
        assert order.customer_id == self.customer.pk
        assert order.status == SalesOrder.STATUS_CONFIRMED
        assert order.grand_total == Decimal("500.00")
        assert [(l.product_id, l.quantity) for l in order.lines.all()] == [
            (self.product.pk, Decimal("5.0000"))
        ]

    def test_converting_the_same_quotation_twice_is_refused(self):
        q = self._quotation()
        convert_quotation_to_order(q, user=self.user)
        q.refresh_from_db()
        with self.assertRaises(ValidationError):
            convert_quotation_to_order(q, user=self.user)

    def test_order_creates_no_journal(self):
        before = JournalHeader.objects.count()
        convert_quotation_to_order(self._quotation(), user=self.user)
        assert JournalHeader.objects.count() == before

    # ── الحجز ───────────────────────────────────────────────────────────
    def test_confirmed_order_reserves_its_quantity_for_a_limited_period(self):
        order = convert_quotation_to_order(self._quotation(qty="5"), user=self.user)
        assert order.reserved_until == date.today() + timedelta(days=7)
        assert reserved_quantity_map(self.tenant.TenantID) == {
            self.product.pk: Decimal("5.0000")
        }

    def test_expired_reservation_frees_the_quantity_without_any_job(self):
        order = convert_quotation_to_order(self._quotation(qty="5"), user=self.user)
        SalesOrder.objects.filter(pk=order.pk).update(
            reserved_until=date.today() - timedelta(days=1))
        assert reserved_quantity_map(self.tenant.TenantID) == {}

    def test_cancelled_order_frees_the_quantity(self):
        order = convert_quotation_to_order(self._quotation(qty="5"), user=self.user)
        cancel_sales_order(order, user=self.user, reason="طلب الزبون")
        order.refresh_from_db()
        assert order.status == SalesOrder.STATUS_CANCELLED
        assert SalesOrder.objects.filter(pk=order.pk).exists()  # لم تُحذف
        assert reserved_quantity_map(self.tenant.TenantID) == {}

    # ── العربون ─────────────────────────────────────────────────────────
    def test_deposit_creates_a_posted_on_account_receipt_linked_to_the_order(self):
        order = convert_quotation_to_order(self._quotation(qty="5"), user=self.user)
        payment = record_order_deposit(
            order, amount=Decimal("150"), cash_account_id=self.cash.pk, user=self.user)
        order.refresh_from_db()
        assert order.deposit_amount == Decimal("150.00")
        assert payment.is_posted
        assert payment.sales_order_id == order.pk
        assert CustomerPayment.objects.filter(sales_order=order).count() == 1

    def test_deposit_may_not_exceed_the_order_total(self):
        order = convert_quotation_to_order(self._quotation(qty="5", price="100"), user=self.user)
        with self.assertRaises(ValidationError):
            record_order_deposit(
                order, amount=Decimal("600"), cash_account_id=self.cash.pk, user=self.user)

    def test_deposit_is_rejected_after_order_conversion(self):
        order = convert_quotation_to_order(self._quotation(qty="5"), user=self.user)
        convert_order_to_invoice(order, user=self.user)
        order.refresh_from_db()
        with self.assertRaises(ValidationError):
            record_order_deposit(
                order, amount=Decimal("50"), cash_account_id=self.cash.pk, user=self.user)

    # ── طلبية ← فاتورة ──────────────────────────────────────────────────
    def test_order_converts_to_invoice_and_releases_the_reservation(self):
        order = convert_quotation_to_order(self._quotation(qty="5"), user=self.user)
        invoice = convert_order_to_invoice(order, user=self.user)
        order.refresh_from_db()
        assert order.status == SalesOrder.STATUS_CONVERTED
        assert order.invoice_id == invoice.pk
        assert invoice.customer_id == self.customer.pk
        # الحجز انتهى بالتحويل — البضاعة صارت على الفاتورة.
        assert reserved_quantity_map(self.tenant.TenantID) == {}

    def test_cancelled_order_cannot_be_converted(self):
        order = convert_quotation_to_order(self._quotation(), user=self.user)
        cancel_sales_order(order, user=self.user)
        order.refresh_from_db()
        with self.assertRaises(ValidationError):
            convert_order_to_invoice(order, user=self.user)

    # ── إلغاء العرض ─────────────────────────────────────────────────────
    def test_quotation_cancel_keeps_the_document(self):
        q = self._quotation()
        cancel_quotation(q, user=self.user, reason="الزبون اعتذر")
        q.refresh_from_db()
        assert q.status == SalesQuotation.STATUS_CANCELLED
        assert SalesQuotation.objects.filter(pk=q.pk).exists()

    # ── سجل النشاط ──────────────────────────────────────────────────────
    def test_order_lifecycle_is_written_to_the_activity_log(self):
        order = convert_quotation_to_order(self._quotation(), user=self.user)
        cancel_sales_order(order, user=self.user)
        actions = set(
            ActivityLog.objects.filter(entity_type="sales_order").values_list("action", flat=True)
        )
        assert {"create", "cancel"} <= actions


class SalesOrderApiTest(APITestCase):
    """عقد الواجهة: قائمة/إنشاء/تأكيد/إلغاء/تحويل + حارس الحذف بالإعداد."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="order-api", password="x")
        cls.tenant = Tenant.objects.create(TenantID=162, CompanyName="Orders API Co")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101", name="ذمم عملاء", account_type="Asset", is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون", partner_type="Customer", linked_account=cls.ar)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="ORD-API", name_ar="منتج",
            quantity_on_hand=Decimal("20"), is_service=False)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _create(self, **over):
        body = {
            "customer": self.customer.pk,
            "order_date": "2026-07-10",
            "currency": self.currency.CurrencyID,
            "lines": [{"product": self.product.pk, "quantity": "3", "unit_price": "50"}],
        }
        body.update(over)
        res = self.client.post("/api/sales/orders/", body, format="json", **self.h)
        assert res.status_code == 201, res.content
        return res.json()

    def _siblings(self, size, brand_a, brand_b, sku_prefix):
        """أخوان تحت أبٍ واحد ببراندين مختلفين (#43) — عبر الخدمة مباشرةً."""
        from inventory.services import add_brand_to_family, create_product_with_family

        family, _first = create_product_with_family(
            tenant=self.tenant, name_ar=size, sku=f"{sku_prefix}-1")
        p1, _ = add_brand_to_family(family=family, brand_name=brand_a, tenant=self.tenant)
        p2, _ = add_brand_to_family(
            family=family, brand_name=brand_b, tenant=self.tenant, sku=f"{sku_prefix}-2")
        return p1, p2

    def test_create_order_directly_without_a_quotation(self):
        row = self._create()
        assert row["grand_total"] == "150.00"
        assert row["status"] == "draft"
        assert row["order_number"]

    # ── #43 — sales/services/orders.py: حارس الكمية بعد الحجوزات (confirm_sales_order) ──

    def test_confirm_shortage_message_shows_sibling_brand(self):
        p1, p2 = self._siblings("215/65/16", "دانتير ايكو جرين", "دانتير جريبماكس A/T", "ORD-SIB")
        Product.objects.filter(pk=p2.pk).update(quantity_on_hand=Decimal("2"))
        row = self._create(lines=[{"product": p2.pk, "quantity": "10", "unit_price": "50"}])

        res = self.client.post(
            f"/api/sales/orders/{row['id']}/confirm/", {}, format="json", **self.h)
        assert res.status_code == 400, res.content
        assert "دانتير جريبماكس A/T" in str(res.data)

    def test_confirm_shortage_fallback_to_id_is_unchanged_when_product_row_is_absent(self):
        """احتياطٌ حرفيّ كما كان: منتجٌ لا ينتمي لشركة الطلبية ⇒ `#{id}` لا اسمٌ (#39)."""
        other_tenant = Tenant.objects.create(TenantID=990, CompanyName="Ghost Co")
        row = self._create()
        order = SalesOrder.objects.get(pk=row["id"])
        product_id = order.lines.get().product_id
        Product.objects.filter(pk=product_id).update(tenant_id=other_tenant.TenantID)

        with self.assertRaises(ValidationError) as ctx:
            confirm_sales_order(order, user=self.user)
        message = str(ctx.exception)
        assert f"#{product_id}" in message
        assert "غير متاح في الشركة الحالية" in message

    def test_sales_quotation_create_and_update_use_amount_discount_without_forced_tax(self):
        create = self.client.post(
            "/api/sales/quotations/",
            {
                "customer": self.customer.pk,
                "quotation_date": "2026-07-10",
                "currency": self.currency.CurrencyID,
                "lines": [{
                    "product": self.product.pk,
                    "quantity": "3",
                    "unit_price": "50",
                    "line_discount": "10",
                    "tax_rate": None,
                }],
            },
            format="json",
            **self.h,
        )
        assert create.status_code == 201, create.content
        assert create.json()["subtotal"] == "140.00"
        assert create.json()["tax_amount"] == "0.00"
        assert create.json()["grand_total"] == "140.00"

        update = self.client.patch(
            f"/api/sales/quotations/{create.json()['id']}/",
            {
                "lines": [{
                    "product": self.product.pk,
                    "quantity": "2",
                    "unit_price": "80",
                    "line_discount": "10",
                    "tax_rate": None,
                }],
            },
            format="json",
            **self.h,
        )
        assert update.status_code == 200, update.content
        assert update.json()["subtotal"] == "150.00"
        assert update.json()["grand_total"] == "150.00"

    def test_update_draft_order_replaces_lines_and_recalculates_totals(self):
        row = self._create()
        res = self.client.patch(
            f"/api/sales/orders/{row['id']}/",
            {
                "lines": [{
                    "product": self.product.pk,
                    "quantity": "2",
                    "unit_price": "80",
                    "line_discount": "10",
                }],
            },
            format="json",
            **self.h,
        )
        assert res.status_code == 200, res.content
        assert res.json()["grand_total"] == "150.00"
        assert res.json()["lines"][0]["line_total"] == "150.00"
        assert SalesOrder.objects.get(pk=row["id"]).lines.count() == 1

    def test_order_rejects_customer_and_product_from_another_company(self):
        other_tenant = Tenant.objects.create(TenantID=163, CompanyName="Other Orders Co")
        other_customer = Partner.objects.create(
            tenant=other_tenant, name="زبون شركة أخرى", partner_type="Customer")
        other_product = Product.objects.create(
            tenant=other_tenant, sku="ORD-OTHER", name_ar="منتج شركة أخرى", is_service=True)

        wrong_customer = self.client.post(
            "/api/sales/orders/",
            {
                "customer": other_customer.pk,
                "order_date": "2026-07-10",
                "currency": self.currency.CurrencyID,
                "lines": [{"product": self.product.pk, "quantity": "1", "unit_price": "10"}],
            },
            format="json",
            **self.h,
        )
        assert wrong_customer.status_code == 400, wrong_customer.content

        wrong_product = self.client.post(
            "/api/sales/orders/",
            {
                "customer": self.customer.pk,
                "order_date": "2026-07-10",
                "currency": self.currency.CurrencyID,
                "lines": [{"product": other_product.pk, "quantity": "1", "unit_price": "10"}],
            },
            format="json",
            **self.h,
        )
        assert wrong_product.status_code == 400, wrong_product.content

    def test_confirmed_order_is_locked_against_line_edits(self):
        row = self._create()
        confirm = self.client.post(
            f"/api/sales/orders/{row['id']}/confirm/", {}, format="json", **self.h)
        assert confirm.status_code == 200, confirm.content
        res = self.client.patch(
            f"/api/sales/orders/{row['id']}/",
            {"lines": [{"product": self.product.pk, "quantity": "9", "unit_price": "50"}]},
            format="json",
            **self.h,
        )
        assert res.status_code == 400, res.content
        assert SalesOrder.objects.get(pk=row["id"]).lines.get().quantity == Decimal("3")

    def test_confirm_rejects_quantity_already_reserved_by_another_order(self):
        first = self._create(lines=[{
            "product": self.product.pk, "quantity": "15", "unit_price": "10",
        }])
        first_confirm = self.client.post(
            f"/api/sales/orders/{first['id']}/confirm/", {}, format="json", **self.h)
        assert first_confirm.status_code == 200, first_confirm.content
        lookup = self.client.get(
            "/api/inventory/products/?view=lookup", **self.h)
        assert lookup.status_code == 200, lookup.content
        product_row = next(
            row for row in lookup.json() if row["id"] == self.product.pk)
        assert Decimal(product_row["reserved_quantity"]) == Decimal("15")
        assert Decimal(product_row["available_quantity"]) == Decimal("5")

        second = self._create(lines=[{
            "product": self.product.pk, "quantity": "6", "unit_price": "10",
        }])
        second_confirm = self.client.post(
            f"/api/sales/orders/{second['id']}/confirm/", {}, format="json", **self.h)
        assert second_confirm.status_code == 400, second_confirm.content
        assert SalesOrder.objects.get(pk=second["id"]).status == SalesOrder.STATUS_DRAFT

    def test_cancel_endpoint_keeps_the_row(self):
        row = self._create()
        res = self.client.post(
            f"/api/sales/orders/{row['id']}/cancel/", {}, format="json", **self.h)
        assert res.status_code == 200, res.content
        assert res.json()["status"] == "cancelled"
        assert SalesOrder.objects.filter(pk=row["id"]).exists()

    def test_delete_is_blocked_unless_the_company_allows_it(self):
        row = self._create()
        SalesSettings.objects.update_or_create(
            tenant=self.tenant, defaults={"allow_document_delete": False})
        res = self.client.delete(f"/api/sales/orders/{row['id']}/", **self.h)
        assert res.status_code == 403, res.content
        assert SalesOrder.objects.filter(pk=row["id"]).exists()

        SalesSettings.objects.update_or_create(
            tenant=self.tenant, defaults={"allow_document_delete": True})
        res = self.client.delete(f"/api/sales/orders/{row['id']}/", **self.h)
        assert res.status_code == 204, res.content

    def test_confirmed_order_cannot_be_deleted_even_when_delete_setting_is_enabled(self):
        row = self._create()
        SalesSettings.objects.update_or_create(
            tenant=self.tenant, defaults={"allow_document_delete": True})
        confirm = self.client.post(
            f"/api/sales/orders/{row['id']}/confirm/", {}, format="json", **self.h)
        assert confirm.status_code == 200, confirm.content
        res = self.client.delete(f"/api/sales/orders/{row['id']}/", **self.h)
        assert res.status_code == 400, res.content
        assert SalesOrder.objects.filter(pk=row["id"]).exists()

    def test_orders_are_filtered_by_customer_for_the_partner_card(self):
        self._create()
        other = Partner.objects.create(
            tenant=self.tenant, name="زبون آخر", partner_type="Customer")
        self._create(customer=other.pk)
        res = self.client.get(
            f"/api/sales/orders/?customer={self.customer.pk}", **self.h)
        assert res.status_code == 200
        rows = res.json()
        assert len(rows) == 1
        assert rows[0]["customer"] == self.customer.pk
