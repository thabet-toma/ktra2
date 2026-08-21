"""رحلة الأرقام التسلسلية عبر واجهة HTTP بحمولة المحرِّرين نفسها (S3).

اختبارات S1 تبني المستندات بالـORM فتثبت **المنطق**؛ هذا الملف يمرّ من حيث تمرّ
الشاشة: `POST /api/logistics/purchase-invoices/` بحمولة `items[].serials` كما
يبنيها `InvoiceForm`، ثم `POST /api/sales/invoices/` بحمولة `lines[].serials`
كما يبنيها `SalesInvoiceEditor` — فيثبت أن العقد الذي تكتبه الواجهة هو العقد
الذي يقرؤه الخادم، وأن ما يُقرَأ عائداً يملأ الشاشة كما حُفظ.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product, ProductSerial, StockMovement, Warehouse
from inventory.serials import SERIAL_MODE_OPTIONAL, SERIAL_MODE_REQUIRED
from logistics.services import get_or_create_purchase_settings
from partners.models import Partner
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company


class SerialInvoiceJourneyTest(APITestCase):
    """صنف تسلسلي → شراء بأرقام → استلام → بيع وحدة بعينها → تراجع."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='serial-journey', password='x')
        cls.ils = Currency.objects.create(Code='ILS', Name='شيكل', IsBaseCurrency=True)
        cls.tenant = create_company('شركة رحلة الأرقام', cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name='مورد اللابتوبات', partner_type='Supplier',
            linked_account=Account.objects.get(tenant=cls.tenant, code='2101'))
        ar = Account.objects.create(
            tenant=cls.tenant, code='1101-J', name='ذمم', account_type='Asset',
            is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name='زبون الرحلة', partner_type='Customer',
            linked_account=ar, phone='0599123456')
        ss = get_or_create_sales_settings(cls.tenant)
        ss.default_ar_account = ar
        ss.default_cogs_account = Account.objects.create(
            tenant=cls.tenant, code='5101-J', name='تكلفة', account_type='Expense',
            is_active=True)
        ss.default_inventory_account = Account.objects.create(
            tenant=cls.tenant, code='1104-J', name='مخزون', account_type='Asset',
            is_active=True)
        ss.save(update_fields=[
            'default_ar_account', 'default_cogs_account', 'default_inventory_account',
        ])

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {'HTTP_X_TENANT_ID': str(self.tenant.TenantID)}
        self.product = Product.objects.create(
            tenant=self.tenant, sku='LAP-1', name_ar='لابتوب',
            is_serialized=True, quantity_on_hand=Decimal('0'), avg_cost=Decimal('0'))

    # ── أدوات ──────────────────────────────────────────────────────────
    def _modes(self, *, purchase=None, sales=None):
        if purchase is not None:
            ps = get_or_create_purchase_settings(self.tenant)
            ps.serial_entry_mode = purchase
            ps.save(update_fields=['serial_entry_mode'])
        if sales is not None:
            ss = get_or_create_sales_settings(self.tenant)
            ss.serial_entry_mode = sales
            ss.save(update_fields=['serial_entry_mode'])

    def _create_purchase(self, serials, qty, price='1000'):
        """حمولة `InvoiceForm.sqlBody` مختصرةً على ما يلزم البند."""
        total = Decimal(str(qty)) * Decimal(price)
        res = self.client.post('/api/logistics/purchase-invoices/', {
            'partner': self.supplier.pk,
            'invoice_date': '2026-06-11',
            'currency': 'ILS',
            'subtotal': str(total),
            'grand_total': str(total),
            'invoice_type': 'local',
            'items': [{
                'product': self.product.pk,
                'name': self.product.name_ar,
                'quantity': str(qty),
                'unit_price': price,
                'total_price': str(total),
                'serials': list(serials),
            }],
        }, format='json', **self.headers)
        return res

    def _create_sale(self, serials, qty='1'):
        res = self.client.post('/api/sales/invoices/', {
            'customer': self.customer.pk,
            'invoice_date': '2026-06-15',
            'invoice_type': 'credit',
            'currency': self.ils.CurrencyID,
            'exchange_rate': 1,
            'stock_on_post': True,
            'lines': [{
                'product': self.product.pk,
                'quantity': qty,
                'unit_price': '2000',
                'line_discount': 0,
                'tax_rate': None,
                'serials': list(serials),
            }],
        }, format='json', **self.headers)
        return res

    def _card_serials(self, status=None):
        """تبويب «الأرقام التسلسلية» في كرت الصنف — نفس نقطة النهاية التي يقرؤها."""
        query = f'?status={status}' if status else ''
        res = self.client.get(
            f'/api/inventory/products/{self.product.pk}/serials/{query}', **self.headers)
        assert res.status_code == 200, res.content
        return res.json()

    # ── الرحلة الكاملة ─────────────────────────────────────────────────
    def test_full_journey_purchase_to_sale_and_back(self):
        self._modes(purchase=SERIAL_MODE_REQUIRED, sales=SERIAL_MODE_OPTIONAL)

        # 1) توليد السلسلة من الخادم — ما تفعله نافذة الإدخال بالضبط.
        gen = self.client.post('/api/inventory/products/generate_serials/',
                               {'start': 'SN-0098', 'count': 3},
                               format='json', **self.headers)
        assert gen.status_code == 200, gen.content
        serials = gen.json()['serials']
        assert serials == ['SN-0098', 'SN-0099', 'SN-0100']

        # 2) فاتورة شراء بالأرقام — الكمية = عدد الأرقام (قاعدة المحرِّر).
        created = self._create_purchase(serials, qty=len(serials))
        assert created.status_code == 201, created.content
        invoice_id = created.json()['id']
        # الحفظ يعيد الأرقام على البند، فتبقى ظاهرة عند إعادة الفتح.
        assert created.json()['items'][0]['serials'] == serials

        reopened = self.client.get(
            f'/api/logistics/purchase-invoices/{invoice_id}/', **self.headers)
        assert reopened.json()['items'][0]['serials'] == serials

        # 3) الترحيل يستلم البضاعة ويُجسّد الوحدات «في المخزن».
        posted = self.client.post(
            f'/api/logistics/purchase-invoices/{invoice_id}/post-to-accounting/',
            {}, format='json', **self.headers)
        assert posted.status_code == 201, posted.content
        units = ProductSerial.objects.filter(tenant=self.tenant).order_by('id')
        assert [u.serial for u in units] == serials
        assert {u.status for u in units} == {ProductSerial.STATUS_IN_STOCK}

        # 4) فاتورة بيع تختار الوحدة الوسطى بعينها.
        sale = self._create_sale(['SN-0099'])
        assert sale.status_code == 201, sale.content
        sale_id = sale.json()['id']
        assert sale.json()['lines'][0]['serials'] == ['SN-0099']

        sale_posted = self.client.post(
            f'/api/sales/invoices/{sale_id}/post/', {}, format='json', **self.headers)
        assert sale_posted.status_code in (200, 201), sale_posted.content

        # 5) كرت الصنف: الوحدة المختارة «مُباعة» ومعها مستنداها وطرفاهما.
        rows = {r['serial']: r for r in self._card_serials()}
        sold = rows['SN-0099']
        assert sold['status'] == 'sold'
        assert sold['customer_name'] == 'زبون الرحلة'
        assert sold['supplier_name'] == 'مورد اللابتوبات'
        assert sold['sales_invoice'] == sale_id
        assert sold['purchase_invoice'] == invoice_id
        # الوحدتان الأخريان لم تُمسّا — الاختيار كان صريحاً لا FIFO.
        assert rows['SN-0098']['status'] == 'in_stock'
        assert rows['SN-0100']['status'] == 'in_stock'
        assert [r['serial'] for r in self._card_serials('in_stock')] == ['SN-0098', 'SN-0100']

        # 6) إلغاء ترحيل البيع يعيد الوحدة للمخزن، والاختيار يبقى على البند.
        unposted = self.client.post(
            f'/api/sales/invoices/{sale_id}/unpost/', {}, format='json', **self.headers)
        assert unposted.status_code in (200, 201), unposted.content
        assert {r['serial'] for r in self._card_serials('in_stock')} == set(serials)
        reloaded_sale = self.client.get(f'/api/sales/invoices/{sale_id}/', **self.headers)
        assert reloaded_sale.json()['lines'][0]['serials'] == ['SN-0099']

        # 7) إعادة الترحيل تستهلك الوحدة ذاتها لا غيرها.
        assert self.client.post(
            f'/api/sales/invoices/{sale_id}/post/', {}, format='json', **self.headers
        ).status_code in (200, 201)
        rows = {r['serial']: r['status'] for r in self._card_serials()}
        assert rows == {'SN-0098': 'in_stock', 'SN-0099': 'sold', 'SN-0100': 'in_stock'}

    def test_sale_without_chosen_serials_lets_server_assign_fifo(self):
        """«تلقائي — أي وحدة»: البند بلا أرقام يخصّص الخادم أقدم المتاح."""
        self._modes(purchase=SERIAL_MODE_OPTIONAL, sales=SERIAL_MODE_OPTIONAL)
        created = self._create_purchase(['SN-1', 'SN-2'], qty=2)
        invoice_id = created.json()['id']
        self.client.post(
            f'/api/logistics/purchase-invoices/{invoice_id}/post-to-accounting/',
            {}, format='json', **self.headers)

        sale = self._create_sale([], qty='1')
        assert sale.json()['lines'][0]['serials'] == []
        sale_id = sale.json()['id']
        self.client.post(f'/api/sales/invoices/{sale_id}/post/', {},
                         format='json', **self.headers)

        rows = {r['serial']: r['status'] for r in self._card_serials()}
        assert rows == {'SN-1': 'sold', 'SN-2': 'in_stock'}

    # ── «إجباري» في البيع: الاختيار واقعةٌ لا تخمين ──────────────────────
    def _receive(self, serials):
        """شراء واستلام — يضع الوحدات «في المخزن» جاهزةً للبيع."""
        created = self._create_purchase(serials, qty=len(serials))
        assert created.status_code == 201, created.content
        invoice_id = created.json()['id']
        posted = self.client.post(
            f'/api/logistics/purchase-invoices/{invoice_id}/post-to-accounting/',
            {}, format='json', **self.headers)
        assert posted.status_code == 201, posted.content
        return invoice_id

    def test_required_sale_without_a_chosen_serial_is_refused_at_posting(self):
        """«إجباري» + بند بلا اختيار ⇒ الترحيل يفشل، ولا يترك أثراً نصفياً.

        قبل هذا الحارس كان التخصيص التلقائي (FIFO) يملأ الفراغ فينجح الترحيل —
        والواجهة تلوّن البند أحمر وتقول «الترحيل سيُرفض». الخادم هو الحَكَم، فصار
        يقول ما تقوله الشاشة.
        """
        self._modes(purchase=SERIAL_MODE_OPTIONAL, sales=SERIAL_MODE_REQUIRED)
        self._receive(['SN-A1', 'SN-A2'])

        sale = self._create_sale([], qty='1')
        assert sale.status_code == 201, sale.content
        sale_id = sale.json()['id']

        res = self.client.post(f'/api/sales/invoices/{sale_id}/post/', {},
                               format='json', **self.headers)
        assert res.status_code == 400, res.content
        body = res.content.decode()
        assert 'إجباري' in body
        assert 'لابتوب' in body            # البند الناقص مُسمّى لا مُلمَّح إليه
        assert 'المطلوب 1 والمختار 0' in body
        assert 'كرت الصنف' in body         # المخرج مذكور لا متروك للتخمين

        # لا أثر نصفي: الفاتورة مسوّدة، ولا وحدة استُهلكت، ولا حركة مخزون بيع.
        reloaded = self.client.get(f'/api/sales/invoices/{sale_id}/', **self.headers)
        assert reloaded.json()['status'] == 'draft'
        assert reloaded.json()['journal'] is None
        assert ProductSerial.objects.filter(
            tenant=self.tenant, status=ProductSerial.STATUS_SOLD).count() == 0
        assert not StockMovement.objects.filter(
            reference_type='SALE', reference_id=sale_id).exists()

    def test_required_sale_with_a_chosen_serial_binds_the_unit_to_the_customer(self):
        """نفس الوضع مع رقمٍ صحيح: يمرّ، ويربط الوحدة بالزبون في بطاقة الجهاز.

        «بطاقة الجهاز» هي ما يقرؤه تبويب الأرقام التسلسلية في كرت الصنف — وهو
        نفسه ما تجيب به مطالبة الكفالة: من اشترى، بأي هاتف، وبأي تاريخ.
        """
        self._modes(purchase=SERIAL_MODE_OPTIONAL, sales=SERIAL_MODE_REQUIRED)
        self._receive(['SN-B1', 'SN-B2'])

        sale = self._create_sale(['SN-B2'], qty='1')
        assert sale.status_code == 201, sale.content
        sale_id = sale.json()['id']
        posted = self.client.post(f'/api/sales/invoices/{sale_id}/post/', {},
                                  format='json', **self.headers)
        assert posted.status_code in (200, 201), posted.content

        rows = {r['serial']: r for r in self._card_serials()}
        sold = rows['SN-B2']
        assert sold['status'] == 'sold'
        assert sold['customer'] == self.customer.pk
        assert sold['customer_name'] == 'زبون الرحلة'
        assert sold['customer_phone'] == '0599123456'
        assert sold['sold_at'] == '2026-06-15'
        assert sold['sales_invoice'] == sale_id
        # الوحدة الأخرى لم تُمسّ — الاختيار صريح لا FIFO.
        assert rows['SN-B1']['status'] == 'in_stock'

    def test_off_mode_drops_serials_from_the_payload(self):
        """النمط الافتراضي: حتى لو أرسلت الواجهة أرقاماً، لا تُخزَّن ولا تُجسَّد."""
        created = self._create_purchase(['X1', 'X2'], qty=2)
        assert created.status_code == 201, created.content
        assert created.json()['items'][0]['serials'] == []
        invoice_id = created.json()['id']
        self.client.post(
            f'/api/logistics/purchase-invoices/{invoice_id}/post-to-accounting/',
            {}, format='json', **self.headers)
        assert ProductSerial.objects.filter(tenant=self.tenant).count() == 0

    def test_lookup_contract_exposes_is_serialized_for_the_editors(self):
        """المحرِّران يعرفان الصنف التسلسلي من عقد المنتقي — لا نداء إضافي لكل سطر."""
        res = self.client.get('/api/inventory/products/?view=lookup', **self.headers)
        assert res.status_code == 200, res.content
        rows = res.json()
        rows = rows['results'] if isinstance(rows, dict) else rows
        row = next(r for r in rows if r['id'] == self.product.pk)
        assert row['is_serialized'] is True
        assert 'barcode' in row
