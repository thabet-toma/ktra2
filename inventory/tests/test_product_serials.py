"""تتبّع الأرقام التسلسلية للوحدة + توليد الباركود (S1).

يثبت:
  1. مولّد السلسلة يحفظ البادئة وخانات الصفر، ويرفض بدايةً بلا جزء رقمي.
  2. مصفوفة الأنماط (بدون/اختياري/إجباري) على **الجانبين**: الشراء يُنشئ الوحدات
     عند الاستلام، والبيع يستهلكها عند الترحيل.
  3. إلغاء الإرسالية/التراجع عن ترحيل فاتورة الشراء يحرّر وحداتها — ويُمنع إن
     بِيعت إحداها (لا بيع لوحدة يُمحى أصلها).
  4. دورة البيع: ترحيل ⇒ «مُباع» مرتبط ببنده، إلغاء الترحيل ⇒ رجوع للمخزن،
     وإعادة الترحيل تستهلك الوحدات ذاتها. غير المختار يُخصَّص FIFO.
  5. الباركود: EAN-13 ببادئة 2 وخانة تحقق سليمة وغير مستخدم، ورفضُ تكراره.
  6. النمط الافتراضي `off` على الجانبين ⇒ لا صفّ وحدة واحد (صفر تغيير سلوك).
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product, ProductSerial, Warehouse
from inventory.serials import (
    SERIAL_MODE_OFF,
    SERIAL_MODE_OPTIONAL,
    SERIAL_MODE_REQUIRED,
    ean13_check_digit,
    generate_product_barcode,
    generate_serial_range,
    is_valid_ean13,
    normalize_serials,
    strip_serials_when_off,
)
from inventory.services import record_stock_movement
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import get_or_create_purchase_settings
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company


# ══════════════════════════════════════════════════════════════════════════
# مولّد السلسلة وخانة التحقق — دوال صافية بلا قاعدة بيانات
# ══════════════════════════════════════════════════════════════════════════

def test_generate_serial_range_keeps_prefix_and_zero_padding():
    assert generate_serial_range('SN-0098', 3) == ['SN-0098', 'SN-0099', 'SN-0100']


def test_generate_serial_range_widens_when_digits_overflow():
    # 99 → 100: عدد الخانات لا يُقطع، والبادئة تبقى كما هي.
    assert generate_serial_range('A-99', 2) == ['A-99', 'A-100']


def test_generate_serial_range_handles_bare_number_and_single_unit():
    assert generate_serial_range('0007', 1) == ['0007']
    assert generate_serial_range('  12 ', 3) == ['12', '13', '14']


def test_generate_serial_range_rejects_start_without_trailing_digits():
    with pytest.raises(DjangoValidationError):
        generate_serial_range('SN-', 3)
    with pytest.raises(DjangoValidationError):
        generate_serial_range('', 3)


def test_generate_serial_range_rejects_bad_count():
    with pytest.raises(DjangoValidationError):
        generate_serial_range('SN-1', 0)
    with pytest.raises(DjangoValidationError):
        generate_serial_range('SN-1', 'x')


def test_normalize_serials_trims_and_rejects_duplicates():
    assert normalize_serials([' A1 ', '', 'A2', None]) == ['A1', 'A2']
    with pytest.raises(DjangoValidationError):
        normalize_serials(['A1', 'A1'])
    with pytest.raises(DjangoValidationError):
        normalize_serials({'a': 1})


def test_strip_serials_when_off_only_clears_in_off_mode():
    rows = [{'serials': ['A1']}, {'serials': []}]
    strip_serials_when_off(rows, SERIAL_MODE_OPTIONAL)
    assert rows[0]['serials'] == ['A1']
    strip_serials_when_off(rows, SERIAL_MODE_OFF)
    assert rows[0]['serials'] == []


def test_ean13_check_digit_matches_known_barcode():
    # 4006381333931 باركود EAN-13 صحيح معروف.
    assert ean13_check_digit('400638133393') == '1'
    assert is_valid_ean13('4006381333931')
    assert not is_valid_ean13('4006381333930')
    assert not is_valid_ean13('123')


# ══════════════════════════════════════════════════════════════════════════
# التكامل: الشراء ⇄ المخزن ⇄ البيع
# ══════════════════════════════════════════════════════════════════════════

class ProductSerialFlowTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='serials', password='x')
        cls.ils = Currency.objects.create(Code='ILS', Name='شيكل', IsBaseCurrency=True)
        cls.tenant = create_company('شركة الأرقام التسلسلية', cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.ap = Account.objects.get(tenant=cls.tenant, code='2101')
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name='مورد', partner_type='Supplier',
            linked_account=cls.ap)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code='1101-SN', name='ذمم', account_type='Asset',
            is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name='زبون', partner_type='Customer',
            linked_account=cls.ar)
        cogs = Account.objects.create(
            tenant=cls.tenant, code='5101-SN', name='تكلفة', account_type='Expense',
            is_active=True)
        inv_acc = Account.objects.create(
            tenant=cls.tenant, code='1104-SN', name='مخزون', account_type='Asset',
            is_active=True)
        ss = get_or_create_sales_settings(cls.tenant)
        ss.default_cogs_account = cogs
        ss.default_inventory_account = inv_acc
        ss.default_ar_account = cls.ar
        ss.save(update_fields=[
            'default_cogs_account', 'default_inventory_account', 'default_ar_account',
        ])

    def setUp(self):
        self.product = Product.objects.create(
            tenant=self.tenant, sku=f'SN-{Product.objects.count() + 1}',
            name_ar='لابتوب', is_serialized=True,
            quantity_on_hand=Decimal('0'), avg_cost=Decimal('0'))
        self.plain = Product.objects.create(
            tenant=self.tenant, sku=f'PL-{Product.objects.count() + 1}',
            name_ar='ورق', is_serialized=False,
            quantity_on_hand=Decimal('0'), avg_cost=Decimal('0'))

    # ── أدوات ──────────────────────────────────────────────────────────
    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {'HTTP_X_TENANT_ID': str(self.tenant.TenantID)}

    def _set_modes(self, *, purchase=None, sales=None):
        if purchase is not None:
            ps = get_or_create_purchase_settings(self.tenant)
            ps.serial_entry_mode = purchase
            ps.save(update_fields=['serial_entry_mode'])
        if sales is not None:
            ss = get_or_create_sales_settings(self.tenant)
            ss.serial_entry_mode = sales
            ss.save(update_fields=['serial_entry_mode'])

    def _purchase_invoice(self, *, serials=None, qty='3', price='1000', product=None):
        product = product or self.product
        grand = Decimal(qty) * Decimal(price)
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f'P-{PurchaseInvoice.objects.count() + 1:04d}',
            partner=self.supplier, currency=self.ils, invoice_date='2026-06-11',
            exchange_rate=Decimal('1'), grand_total=grand)
        item = PurchaseInvoiceItem.objects.create(
            invoice=inv, product=product, name=product.name_ar,
            quantity=Decimal(qty), unit_price=Decimal(price), total_price=grand,
            serials=list(serials or []))
        return inv, item

    def _post_purchase(self, invoice):
        return self.client.post(
            f'/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/',
            {}, format='json', **self._auth())

    def _receive(self, invoice, item, qty):
        return self.client.post(
            f'/api/logistics/purchase-invoices/{invoice.pk}/receive/',
            {'lines': [{'item_id': item.pk, 'quantity': qty,
                        'warehouse_id': self.warehouse.pk}]},
            format='json', **self._auth())

    def _stock_serials(self, *serials, qty=None, product=None):
        """يُدخل وحدات للمخزن عبر فاتورة شراء مرحّلة — الطريق الطبيعي الوحيد."""
        product = product or self.product
        self._set_modes(purchase=SERIAL_MODE_OPTIONAL)
        inv, item = self._purchase_invoice(
            serials=list(serials), qty=str(qty or len(serials)), product=product)
        res = self._post_purchase(inv)
        assert res.status_code == 201, res.content
        return inv, item

    def _sales_invoice(self, *, qty='1', serials=None, product=None):
        product = product or self.product
        inv = SalesInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f'S-{SalesInvoice.objects.count() + 1:04d}',
            customer=self.customer, currency=self.ils, invoice_date='2026-06-15',
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True)
        line = SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=inv, product=product,
            quantity=Decimal(qty), unit_price=Decimal('2000'),
            serials=list(serials or []))
        return inv, line

    def _post_sale(self, invoice):
        return self.client.post(
            f'/api/sales/invoices/{invoice.pk}/post/', {}, format='json', **self._auth())

    def _unpost_sale(self, invoice):
        return self.client.post(
            f'/api/sales/invoices/{invoice.pk}/unpost/', {}, format='json', **self._auth())

    def _units(self, **filters):
        return ProductSerial.objects.filter(tenant=self.tenant, **filters)

    # ── الشراء: مصفوفة الأنماط ────────────────────────────────────────
    def test_off_mode_stores_no_units_even_when_lines_carry_serials(self):
        """الافتراضي: أرقام على البند بلا إعداد ⇒ صفر وحدات (صفر تغيير سلوك)."""
        inv, _item = self._purchase_invoice(serials=['A1', 'A2', 'A3'])
        assert self._post_purchase(inv).status_code == 201
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal('3.0000')
        assert self._units().count() == 0

    def test_required_mode_blocks_receiving_without_enough_serials(self):
        self._set_modes(purchase=SERIAL_MODE_REQUIRED)
        inv, _item = self._purchase_invoice(serials=['A1', 'A2'], qty='3')
        res = self._post_purchase(inv)
        assert res.status_code == 400, res.content
        assert 'إجباري' in res.json()['error']
        # ذرّية: لا مخزون ولا وحدات ولا ترحيل
        inv.refresh_from_db()
        assert not inv.is_posted
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal('0.0000')
        assert self._units().count() == 0

    def test_required_mode_receives_one_unit_per_serial(self):
        self._set_modes(purchase=SERIAL_MODE_REQUIRED)
        inv, item = self._purchase_invoice(serials=['A1', 'A2', 'A3'], qty='3')
        assert self._post_purchase(inv).status_code == 201
        units = self._units().order_by('id')
        assert [u.serial for u in units] == ['A1', 'A2', 'A3']
        assert {u.status for u in units} == {ProductSerial.STATUS_IN_STOCK}
        assert {u.purchase_item_id for u in units} == {item.pk}

    def test_required_mode_ignores_lines_of_untracked_products(self):
        """الإلزام يخصّ الأصناف التسلسلية وحدها — لا يعطّل بقية الفواتير."""
        self._set_modes(purchase=SERIAL_MODE_REQUIRED)
        inv, _item = self._purchase_invoice(qty='5', product=self.plain)
        assert self._post_purchase(inv).status_code == 201
        assert self._units().count() == 0

    def test_optional_mode_accepts_partial_serial_entry(self):
        self._set_modes(purchase=SERIAL_MODE_OPTIONAL)
        inv, _item = self._purchase_invoice(serials=['B1'], qty='3')
        assert self._post_purchase(inv).status_code == 201
        assert [u.serial for u in self._units()] == ['B1']
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal('3.0000')

    def test_duplicate_serial_for_same_product_is_rejected(self):
        self._stock_serials('C1')
        self._set_modes(purchase=SERIAL_MODE_OPTIONAL)
        inv, _item = self._purchase_invoice(serials=['C1'], qty='1')
        res = self._post_purchase(inv)
        assert res.status_code == 400, res.content
        assert 'C1' in res.json()['error']
        assert self._units(serial='C1').count() == 1

    def test_partial_receive_materializes_serials_in_order(self):
        self._set_modes(purchase=SERIAL_MODE_REQUIRED)
        ps = get_or_create_purchase_settings(self.tenant)
        ps.receive_on_post = False
        ps.save(update_fields=['receive_on_post'])
        inv, item = self._purchase_invoice(serials=['D1', 'D2', 'D3'], qty='3')
        assert self._post_purchase(inv).status_code == 201
        assert self._units().count() == 0  # لم تدخل المخزن بعد

        assert self._receive(inv, item, 2).status_code == 200
        assert [u.serial for u in self._units().order_by('id')] == ['D1', 'D2']
        assert self._receive(inv, item, 1).status_code == 200
        assert [u.serial for u in self._units().order_by('id')] == ['D1', 'D2', 'D3']

    # ── الشراء: التحرير والحظر ────────────────────────────────────────
    def test_voiding_a_receipt_releases_only_its_units(self):
        self._set_modes(purchase=SERIAL_MODE_REQUIRED)
        ps = get_or_create_purchase_settings(self.tenant)
        ps.receive_on_post = False
        ps.save(update_fields=['receive_on_post'])
        inv, item = self._purchase_invoice(serials=['E1', 'E2', 'E3'], qty='3')
        self._post_purchase(inv)
        first = self.client.post(
            '/api/logistics/goods-receipts/',
            {'invoice': inv.pk,
             'lines': [{'item_id': item.pk, 'quantity': 2,
                        'warehouse_id': self.warehouse.pk}]},
            format='json', **self._auth()).json()
        assert self._receive(inv, item, 1).status_code == 200
        assert self._units().count() == 3

        res = self.client.delete(
            f"/api/logistics/goods-receipts/{first['id']}/", **self._auth())
        assert res.status_code == 200, res.content
        # الإرسالية الأولى جاءت بوحدتين ⇒ يبقى واحدة
        assert self._units().count() == 1

    def test_unposting_purchase_invoice_releases_its_units(self):
        self._stock_serials('F1', 'F2')
        inv = PurchaseInvoice.objects.order_by('-pk').first()
        assert self._units().count() == 2
        res = self.client.post(
            f'/api/logistics/purchase-invoices/{inv.pk}/unpost/', {},
            format='json', **self._auth())
        assert res.status_code == 200, res.content
        assert self._units().count() == 0

    def test_sold_unit_blocks_unposting_its_purchase_invoice(self):
        self._set_modes(sales=SERIAL_MODE_OPTIONAL)
        purchase, _item = self._stock_serials('G1', 'G2')
        sale, _line = self._sales_invoice(qty='1', serials=['G1'])
        assert self._post_sale(sale).status_code == 200

        res = self.client.post(
            f'/api/logistics/purchase-invoices/{purchase.pk}/unpost/', {},
            format='json', **self._auth())
        assert res.status_code == 400, res.content
        assert 'G1' in res.json()['error']
        # لا شيء تغيّر: الفاتورة مرحّلة ووحداتها قائمة
        purchase.refresh_from_db()
        assert purchase.is_posted
        assert self._units().count() == 2

    # ── البيع: الاستهلاك والتحرير ─────────────────────────────────────
    def test_sale_marks_the_chosen_unit_sold_and_links_it(self):
        self._set_modes(sales=SERIAL_MODE_OPTIONAL)
        self._stock_serials('H1', 'H2', 'H3')
        sale, line = self._sales_invoice(qty='1', serials=['H2'])
        assert self._post_sale(sale).status_code == 200

        sold = self._units(status=ProductSerial.STATUS_SOLD)
        assert [u.serial for u in sold] == ['H2']
        assert sold.first().sales_line_id == line.pk
        assert self._units(status=ProductSerial.STATUS_IN_STOCK).count() == 2

    def test_sale_auto_assigns_unchosen_units_fifo(self):
        self._set_modes(sales=SERIAL_MODE_OPTIONAL)
        self._stock_serials('I1', 'I2', 'I3')
        sale, _line = self._sales_invoice(qty='2')  # بلا اختيار صريح
        assert self._post_sale(sale).status_code == 200
        sold = [u.serial for u in self._units(status=ProductSerial.STATUS_SOLD).order_by('id')]
        assert sold == ['I1', 'I2']  # الأقدم أولاً

    def test_sale_mixes_explicit_choice_with_fifo_remainder(self):
        self._set_modes(sales=SERIAL_MODE_OPTIONAL)
        self._stock_serials('J1', 'J2', 'J3')
        sale, _line = self._sales_invoice(qty='2', serials=['J3'])
        assert self._post_sale(sale).status_code == 200
        sold = {u.serial for u in self._units(status=ProductSerial.STATUS_SOLD)}
        assert sold == {'J3', 'J1'}  # المختار + أقدم المتاح

    def test_unpost_returns_units_to_stock_and_repost_takes_the_same_ones(self):
        self._set_modes(sales=SERIAL_MODE_OPTIONAL)
        self._stock_serials('K1', 'K2')
        sale, line = self._sales_invoice(qty='1', serials=['K2'])
        assert self._post_sale(sale).status_code == 200

        assert self._unpost_sale(sale).status_code == 200
        assert self._units(status=ProductSerial.STATUS_SOLD).count() == 0
        assert self._units(sales_line__isnull=False).count() == 0

        assert self._post_sale(sale).status_code == 200
        sold = self._units(status=ProductSerial.STATUS_SOLD)
        assert [u.serial for u in sold] == ['K2']
        assert sold.first().sales_line_id == line.pk

    def test_required_sales_mode_blocks_when_the_pool_is_short(self):
        """مخزون قديم سابق للتتبّع: وحدتان مطلوبتان وواحدة مُرقَّمة ⇒ يُرفض الترحيل."""
        self._set_modes(sales=SERIAL_MODE_REQUIRED)
        self._stock_serials('L1')
        # كمية إضافية بلا أرقام (كالمخزون القديم)
        record_stock_movement(
            product=self.product, movement_type='IN', quantity=Decimal('5'),
            unit_cost=Decimal('1000'), reference_type='OPENING', reference_id=0,
            movement_date='2026-06-01', tenant=self.tenant)
        sale, _line = self._sales_invoice(qty='2')
        res = self._post_sale(sale)
        assert res.status_code == 400, res.content
        assert 'إجباري' in res.json()['error']
        sale.refresh_from_db()
        assert sale.status == SalesInvoice.STATUS_DRAFT
        assert self._units(status=ProductSerial.STATUS_SOLD).count() == 0

    def test_optional_sales_mode_assigns_what_exists_when_the_pool_is_short(self):
        self._set_modes(sales=SERIAL_MODE_OPTIONAL)
        self._stock_serials('M1')
        record_stock_movement(
            product=self.product, movement_type='IN', quantity=Decimal('5'),
            unit_cost=Decimal('1000'), reference_type='OPENING', reference_id=0,
            movement_date='2026-06-01', tenant=self.tenant)
        sale, _line = self._sales_invoice(qty='2')
        assert self._post_sale(sale).status_code == 200
        assert [u.serial for u in self._units(status=ProductSerial.STATUS_SOLD)] == ['M1']

    def test_sale_rejects_a_serial_that_is_not_in_stock(self):
        self._set_modes(sales=SERIAL_MODE_OPTIONAL)
        self._stock_serials('N1')
        sale, _line = self._sales_invoice(qty='1', serials=['NOPE'])
        res = self._post_sale(sale)
        assert res.status_code == 400, res.content
        assert 'NOPE' in res.json()['error']

    def test_off_sales_mode_consumes_nothing(self):
        self._stock_serials('O1')
        self._set_modes(sales=SERIAL_MODE_OFF)
        sale, _line = self._sales_invoice(qty='1', serials=['O1'])
        assert self._post_sale(sale).status_code == 200
        assert self._units(status=ProductSerial.STATUS_SOLD).count() == 0

    # ── القراءة ────────────────────────────────────────────────────────
    def test_product_serials_endpoint_filters_by_status(self):
        self._set_modes(sales=SERIAL_MODE_OPTIONAL)
        self._stock_serials('P1', 'P2')
        sale, _line = self._sales_invoice(qty='1', serials=['P1'])
        self._post_sale(sale)

        res = self.client.get(
            f'/api/inventory/products/{self.product.pk}/serials/', **self._auth())
        assert res.status_code == 200, res.content
        assert {r['serial'] for r in res.json()} == {'P1', 'P2'}

        res = self.client.get(
            f'/api/inventory/products/{self.product.pk}/serials/?status=sold',
            **self._auth())
        rows = res.json()
        assert [r['serial'] for r in rows] == ['P1']
        assert rows[0]['customer_name'] == 'زبون'
        assert rows[0]['sales_invoice_number'] == sale.invoice_number
        assert rows[0]['supplier_name'] == 'مورد'

    def test_tenant_wide_serial_lookup_answers_where_the_unit_went(self):
        self._set_modes(sales=SERIAL_MODE_OPTIONAL)
        purchase, _item = self._stock_serials('Q1', 'Q2')
        sale, _line = self._sales_invoice(qty='1', serials=['Q1'])
        self._post_sale(sale)

        res = self.client.get('/api/inventory/serials/?q=Q1', **self._auth())
        assert res.status_code == 200, res.content
        rows = res.json()
        assert len(rows) == 1
        assert rows[0]['serial'] == 'Q1'
        assert rows[0]['status'] == 'sold'
        assert rows[0]['purchase_invoice_number'] == purchase.invoice_number
        assert rows[0]['sales_invoice_number'] == sale.invoice_number

    def test_serial_lookup_is_tenant_scoped(self):
        self._stock_serials('R1')
        other_owner = User.objects.create_user(username='other-sn', password='x')
        other = create_company('شركة أخرى', other_owner)
        self.client.force_authenticate(user=other_owner)
        res = self.client.get(
            '/api/inventory/serials/?q=R1', HTTP_X_TENANT_ID=str(other.TenantID))
        assert res.status_code == 200, res.content
        assert res.json() == []

    # ── الباركود ───────────────────────────────────────────────────────
    def test_generate_barcode_endpoint_returns_a_unique_valid_ean13(self):
        res = self.client.post(
            '/api/inventory/products/generate_barcode/', {}, format='json', **self._auth())
        assert res.status_code == 200, res.content
        barcode = res.json()['barcode']
        assert barcode.startswith('2')
        assert is_valid_ean13(barcode)
        assert not Product.objects.filter(tenant=self.tenant, barcode=barcode).exists()

    def test_generated_barcode_never_reuses_an_existing_one(self):
        # نستهلك الفضاء المتاح: باركود موجود لا يجوز أن يُعاد توليده.
        taken = generate_product_barcode(self.tenant.TenantID)
        self.product.barcode = taken
        self.product.save(update_fields=['barcode'])
        for _ in range(5):
            assert generate_product_barcode(self.tenant.TenantID) != taken

    def test_product_serializer_rejects_a_barcode_used_by_another_product(self):
        self.product.barcode = '2000000000009'
        self.product.save(update_fields=['barcode'])
        res = self.client.patch(
            f'/api/inventory/products/{self.plain.pk}/',
            {'barcode': '2000000000009'}, format='json', **self._auth())
        assert res.status_code == 400, res.content
        assert 'barcode' in res.json()

    def test_product_keeps_its_own_barcode_on_edit(self):
        self.product.barcode = '2000000000009'
        self.product.save(update_fields=['barcode'])
        res = self.client.patch(
            f'/api/inventory/products/{self.product.pk}/',
            {'barcode': '2000000000009', 'name_ar': 'لابتوب معدّل'},
            format='json', **self._auth())
        assert res.status_code == 200, res.content

    def test_generate_serials_endpoint_mirrors_the_service(self):
        res = self.client.post(
            '/api/inventory/products/generate_serials/',
            {'start': 'SN-0098', 'count': 3}, format='json', **self._auth())
        assert res.status_code == 200, res.content
        assert res.json()['serials'] == ['SN-0098', 'SN-0099', 'SN-0100']

        res = self.client.post(
            '/api/inventory/products/generate_serials/',
            {'start': 'SN-', 'count': 3}, format='json', **self._auth())
        assert res.status_code == 400, res.content

    # ══════════════════════════════════════════════════════════════════
    # S4: إغلاق اعتراضات مراجعة النيّة الخمسة
    # ══════════════════════════════════════════════════════════════════

    # ── (1) «إجباري» يحرس الترحيل لا الاستلام وحده ────────────────────
    def test_required_mode_blocks_posting_when_receive_on_post_is_off(self):
        """الاستلام مع الترحيل مُطفأ ⇒ لا يمرّ الترحيل بحارس الاستلام أصلاً.

        كانت الفاتورة تُرحَّل بلا رقم واحد رغم «إجباري»، ثم يمنع `perform_update`
        تعديلها فلا سبيل لإضافة الأرقام إلا بإلغاء الترحيل.
        """
        self._set_modes(purchase=SERIAL_MODE_REQUIRED)
        ps = get_or_create_purchase_settings(self.tenant)
        ps.receive_on_post = False
        ps.save(update_fields=['receive_on_post'])

        inv, _item = self._purchase_invoice(serials=[], qty='2')
        res = self._post_purchase(inv)
        assert res.status_code == 400, res.content
        error = res.json()['error']
        assert 'إجباري' in error and 'لابتوب' in error
        inv.refresh_from_db()
        assert not inv.is_posted
        assert inv.journal_id is None

    def test_required_mode_blocks_posting_when_the_line_has_no_inventory_debit(self):
        """بندٌ مربوط بحساب مصروف ⇒ `goods_clearing_amt` صفر فلا استلام مع الترحيل."""
        self._set_modes(purchase=SERIAL_MODE_REQUIRED)
        expense = Account.objects.create(
            tenant=self.tenant, code='5999-SN', name='مصروف', account_type='Expense',
            is_active=True)
        inv, item = self._purchase_invoice(serials=['Z1'], qty='2')
        item.expense_account = expense
        item.save(update_fields=['expense_account'])

        res = self._post_purchase(inv)
        assert res.status_code == 400, res.content
        assert 'المطلوب 2 والمُدخَل 1' in res.json()['error']
        inv.refresh_from_db()
        assert not inv.is_posted

    def test_required_mode_lets_a_complete_invoice_post_on_the_no_receive_path(self):
        """الحارس يمنع الناقص فقط: الفاتورة المكتملة تُرحَّل كما كانت."""
        self._set_modes(purchase=SERIAL_MODE_REQUIRED)
        ps = get_or_create_purchase_settings(self.tenant)
        ps.receive_on_post = False
        ps.save(update_fields=['receive_on_post'])
        inv, item = self._purchase_invoice(serials=['Y1', 'Y2'], qty='2')
        assert self._post_purchase(inv).status_code == 201
        # الوحدات تُجسَّد عند الاستلام لا عند الترحيل (خط الدفاع الثاني كما هو).
        assert self._units().count() == 0
        assert self._receive(inv, item, 2).status_code == 200
        assert [u.serial for u in self._units().order_by('id')] == ['Y1', 'Y2']

    # ── (2) ترقيم مخزون قائم: مخرج «إجباري» في البيع ──────────────────
    def _stock_without_serials(self, qty, product=None):
        record_stock_movement(
            product=product or self.product, movement_type='IN', quantity=Decimal(qty),
            unit_cost=Decimal('1000'), reference_type='OPENING', reference_id=0,
            movement_date='2026-06-01', tenant=self.tenant)

    def _register(self, serials, product=None):
        product = product or self.product
        return self.client.post(
            f'/api/inventory/products/{product.pk}/serials/register/',
            {'serials': serials}, format='json', **self._auth())

    def test_registering_existing_stock_creates_units_without_a_purchase_line(self):
        self._stock_without_serials('2')
        res = self._register(['OLD-1', 'OLD-2'])
        assert res.status_code == 201, res.content
        assert res.json()['created'] == 2
        assert {r['serial'] for r in res.json()['serials']} == {'OLD-1', 'OLD-2'}

        units = self._units().order_by('id')
        assert [u.serial for u in units] == ['OLD-1', 'OLD-2']
        assert {u.status for u in units} == {ProductSerial.STATUS_IN_STOCK}
        assert {u.purchase_item_id for u in units} == {None}
        # الترقيم يصف مخزوناً قائماً — لا يزيد الرصيد ولا يُنشئ حركة.
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal('2.0000')

    def test_registration_is_capped_by_stock_on_hand(self):
        self._stock_without_serials('2')
        assert self._register(['OLD-1', 'OLD-2']).status_code == 201
        res = self._register(['OLD-3'])
        assert res.status_code == 400, res.content
        assert 'رصيد المخزن 2' in res.json()['error']
        assert self._units().count() == 2

    def test_registration_rejects_a_serial_already_used(self):
        self._stock_without_serials('3')
        assert self._register(['OLD-1']).status_code == 201
        res = self._register(['OLD-1'])
        assert res.status_code == 400, res.content
        assert 'OLD-1' in res.json()['error']
        assert self._units().count() == 1

    def test_registration_rejects_an_untracked_product(self):
        self._stock_without_serials('5', product=self.plain)
        res = self._register(['PL-1'], product=self.plain)
        assert res.status_code == 400, res.content
        assert 'لا يتتبّع' in res.json()['error']

    def test_registered_units_unblock_selling_legacy_stock_under_required(self):
        """الاعتراض الأصلي: «إجباري» في البيع كان يُجمّد كل المخزون السابق للميزة.

        الترقيم يفتح الطريق، والاختيار يمشيه: تحت «إجباري» لا يُخصَّص شيء تلقائياً
        (`assert_sales_serials_declared`) — فالوحدة المُسندة لزبون تُختار لا
        تُخمَّن. المُسجَّل حديثاً يصير قابلاً للاختيار، وهذا هو فكّ التجميد.
        """
        self._set_modes(sales=SERIAL_MODE_REQUIRED)
        self._stock_without_serials('2')
        blocked = self._post_sale(self._sales_invoice(qty='1')[0])
        assert blocked.status_code == 400, blocked.content

        assert self._register(['LEG-1', 'LEG-2']).status_code == 201
        # ولو بقي البند بلا اختيار بعد الترقيم لظلّ مرفوضاً — الترقيم وحده لا يبيع.
        still_blocked = self._post_sale(self._sales_invoice(qty='1')[0])
        assert still_blocked.status_code == 400, still_blocked.content

        sale, _line = self._sales_invoice(qty='1', serials=['LEG-1'])
        assert self._post_sale(sale).status_code == 200
        assert [u.serial for u in self._units(status=ProductSerial.STATUS_SOLD)] == ['LEG-1']

    # ── (3) سند الاستلام المستقل لا يتجاوز «إجباري» ───────────────────
    def _standalone_receipt(self, product=None, qty=2):
        return self.client.post(
            '/api/logistics/goods-receipts/',
            {'partner': self.supplier.pk,
             'lines': [{'product_id': (product or self.product).pk, 'quantity': qty,
                        'unit_price': 100, 'warehouse_id': self.warehouse.pk}]},
            format='json', **self._auth())

    def test_standalone_receipt_is_rejected_for_serialized_goods_under_required(self):
        self._set_modes(purchase=SERIAL_MODE_REQUIRED)
        res = self._standalone_receipt()
        assert res.status_code == 400, res.content
        assert 'لابتوب' in res.json()['error']
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal('0.0000')

    def test_standalone_receipt_still_works_for_untracked_goods_and_other_modes(self):
        self._set_modes(purchase=SERIAL_MODE_REQUIRED)
        assert self._standalone_receipt(product=self.plain).status_code in (200, 201)
        self._set_modes(purchase=SERIAL_MODE_OPTIONAL)
        assert self._standalone_receipt().status_code in (200, 201)

    # ── (4) المراجيع تُبقي حالة الوحدة صادقة ──────────────────────────
    def _purchase_return(self, original, qty=1, product=None):
        return self.client.post(
            '/api/logistics/purchase-invoices/returns/',
            {'original_invoice': original.pk, 'supplier': self.supplier.pk,
             'return_date': '2026-06-20',
             'lines': [{'product': (product or self.product).pk,
                        'quantity': qty, 'unit_price': 1000}]},
            format='json', **self._auth())

    def test_posting_a_purchase_return_releases_the_newest_units(self):
        purchase, _item = self._stock_serials('T1', 'T2', 'T3')
        ret = self._purchase_return(purchase, qty=2)
        assert ret.status_code == 201, ret.content
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{ret.json()['id']}/post-to-accounting/",
            {}, format='json', **self._auth())
        assert res.status_code == 200, res.content
        # الأحدث أولاً — نفس قاعدة إلغاء الإرسالية.
        assert [u.serial for u in self._units().order_by('id')] == ['T1']

    def test_unposting_a_purchase_return_restores_its_units(self):
        """التراجع يعيد الكمية للمخزن — فوحداتها تعود، وإلا ضاعت أرقامها نهائياً."""
        purchase, _item = self._stock_serials('W1', 'W2', 'W3')
        ret = self._purchase_return(purchase, qty=2).json()
        assert self.client.post(
            f"/api/logistics/purchase-invoices/{ret['id']}/post-to-accounting/",
            {}, format='json', **self._auth()).status_code == 200
        assert [u.serial for u in self._units()] == ['W1']

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{ret['id']}/unpost/", {},
            format='json', **self._auth())
        assert res.status_code == 200, res.content
        assert {u.serial for u in self._units()} == {'W1', 'W2', 'W3'}
        assert {u.status for u in self._units()} == {ProductSerial.STATUS_IN_STOCK}

    def test_purchase_return_is_blocked_when_a_returned_unit_was_sold(self):
        self._set_modes(sales=SERIAL_MODE_OPTIONAL)
        purchase, _item = self._stock_serials('U1', 'U2')
        sale, _line = self._sales_invoice(qty='1', serials=['U2'])
        assert self._post_sale(sale).status_code == 200

        ret = self._purchase_return(purchase, qty=1)
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{ret.json()['id']}/post-to-accounting/",
            {}, format='json', **self._auth())
        assert res.status_code == 400, res.content
        assert 'U2' in res.json()['error']
        assert self._units().count() == 2
        assert self._units(status=ProductSerial.STATUS_SOLD).count() == 1

    def _sales_return(self, original, *, qty='1', product=None):
        product = product or self.product
        inv = SalesInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f'SR-{SalesInvoice.objects.count() + 1:04d}',
            customer=self.customer, currency=self.ils, invoice_date='2026-06-20',
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
            original_invoice=original)
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=inv, product=product,
            quantity=Decimal(qty), unit_price=Decimal('2000'))
        return inv

    def test_posting_a_sale_return_puts_the_sold_unit_back_in_stock(self):
        self._set_modes(sales=SERIAL_MODE_OPTIONAL)
        self._stock_serials('V1', 'V2')
        sale, _line = self._sales_invoice(qty='2')
        assert self._post_sale(sale).status_code == 200
        assert self._units(status=ProductSerial.STATUS_SOLD).count() == 2

        ret = self._sales_return(sale, qty='1')
        assert self._post_sale(ret).status_code == 200
        # الأقدم استهلاكاً يعود أولاً، والرابط بالبند يُفرَّغ.
        back = self._units(status=ProductSerial.STATUS_IN_STOCK)
        assert [u.serial for u in back] == ['V1']
        assert back.first().sales_line_id is None
        assert [u.serial for u in self._units(status=ProductSerial.STATUS_SOLD)] == ['V2']

    def test_sale_return_of_untracked_stock_changes_nothing(self):
        self._set_modes(sales=SERIAL_MODE_OPTIONAL)
        self._stock_without_serials('3')
        sale, _line = self._sales_invoice(qty='1')
        assert self._post_sale(sale).status_code == 200
        ret = self._sales_return(sale, qty='1')
        assert self._post_sale(ret).status_code == 200
        assert self._units().count() == 0

    # ── (5) رسالة الرفض في البيع جملةٌ لا تمثيل بايثون ────────────────
    def test_sales_rejection_message_reaches_the_user_as_a_sentence(self):
        self._set_modes(sales=SERIAL_MODE_REQUIRED)
        self._stock_without_serials('2')
        res = self._post_sale(self._sales_invoice(qty='1')[0])
        assert res.status_code == 400, res.content
        error = res.json()['error']
        # جملةٌ عربية تسمّي البند الناقص — لا `ErrorList` ولا تمثيل بايثون.
        assert 'لابتوب' in error, error
        assert 'إجباري' in error, error
        assert '[' not in error and ']' not in error and "'" not in error
