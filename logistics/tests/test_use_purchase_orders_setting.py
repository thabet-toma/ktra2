"""ISSUE #117: إعداد «أمر الشراء اختياري» (PurchaseSettings.use_purchase_orders).

القاعدة الحاسمة: المفتاح يحكم **الإنشاء لا الرؤية**. مطفأً (الافتراضي
الجديد): لا يُنشأ أمر شراء جديد — لا مباشرةً عبر `POST /purchase-orders/`
ولا عبر «تحويل عرض سعر إلى طلبية» (`convert_local_quotation_to_order`) — لكن
أمرَ شراءٍ قائماً يبقى مقروءاً بلا حجب.

وهجرة `0082_backfill_use_purchase_orders` تُشعله لشركةٍ لها أمرُ شراءٍ قائم
بالفعل، وتترك الشركة الخالية منه مطفأةً.
"""
import importlib
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from logistics.models import PurchaseOrder, PurchaseSettings, SupplierQuotation
from logistics.services import get_or_create_purchase_settings
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class UsePurchaseOrdersSettingTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=991, CompanyName='Use PO Co')
        cls.currency = Currency.objects.create(
            Code='UPO', Name='Use purchase orders currency', IsBaseCurrency=False,
        )
        cls.user = User.objects.create_user(username='use-po', password='x')
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role='manager',
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name='Supplier UPO', partner_type='Supplier',
        )
        from inventory.models import Product
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku='UPO-ITEM-1', name_ar='منتج',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _set_use_purchase_orders(self, value):
        ps = get_or_create_purchase_settings(self.tenant)
        ps.use_purchase_orders = value
        ps.save(update_fields=['use_purchase_orders'])
        return ps

    def _make_existing_order(self):
        return PurchaseOrder.objects.create(
            tenant=self.tenant,
            order_number=f'PO-EXIST-{PurchaseOrder.objects.count() + 1}',
            supplier=self.supplier,
            order_date='2026-07-01',
            currency=self.currency,
            exchange_rate=Decimal('1'),
        )

    def order_payload(self):
        return {
            'supplier': self.supplier.id,
            'order_date': '2026-07-26',
            'currency': self.currency.pk,
            'exchange_rate': '1.000000',
            'lines': [{
                'product': self.product.id,
                'seq': 1,
                'quantity': '2.000',
                'unit_price': '10.0000',
            }],
        }

    # ── القاعدة الحاسمة: الإنشاء مرفوض، والقراءة مقبولة ──────────────────

    def test_default_is_off(self):
        ps = get_or_create_purchase_settings(self.tenant)
        self.assertFalse(ps.use_purchase_orders)

    def test_create_rejected_when_off(self):
        self._set_use_purchase_orders(False)
        resp = self.client.post(
            '/api/logistics/purchase-orders/', self.order_payload(), format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    def test_reading_existing_order_accepted_when_off(self):
        self._set_use_purchase_orders(False)
        order = self._make_existing_order()

        detail = self.client.get(f'/api/logistics/purchase-orders/{order.id}/')
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.data['id'], order.id)

        listing = self.client.get('/api/logistics/purchase-orders/')
        self.assertEqual(listing.status_code, 200, listing.content)
        rows = listing.data['results'] if isinstance(listing.data, dict) else listing.data
        ids = [row['id'] for row in rows]
        self.assertIn(order.id, ids)

    def test_create_accepted_when_on(self):
        self._set_use_purchase_orders(True)
        resp = self.client.post(
            '/api/logistics/purchase-orders/', self.order_payload(), format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(PurchaseOrder.objects.count(), 1)

    def test_convert_quotation_to_order_rejected_when_off(self):
        self._set_use_purchase_orders(False)
        quotation = SupplierQuotation.objects.create(
            tenant=self.tenant, scope=SupplierQuotation.SCOPE_LOCAL,
            supplier=self.supplier, quotation_date='2026-07-01',
            status=SupplierQuotation.STATUS_ACCEPTED,
            currency=self.currency, exchange_rate=Decimal('1'),
        )
        resp = self.client.post(
            f'/api/logistics/supplier-quotations/{quotation.id}/convert-to-purchase-order/',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(PurchaseOrder.objects.count(), 0)

    # ── هجرة البيانات: تُشعل الإعداد لمن له أمرٌ قائم فقط ─────────────────

    def test_migration_backfills_true_only_for_tenant_with_existing_order(self):
        tenant_with_order = Tenant.objects.create(
            TenantID=992, CompanyName='Has PO Co',
        )
        tenant_without_order = Tenant.objects.create(
            TenantID=993, CompanyName='No PO Co',
        )
        PurchaseOrder.objects.create(
            tenant=tenant_with_order, order_number='PO-MIG-1',
            supplier=self.supplier, order_date='2026-07-01',
            currency=self.currency, exchange_rate=Decimal('1'),
        )
        # طلبية محذوفة ناعماً وحدها — لا تُحتسب «قائمة».
        deleted_only_tenant = Tenant.objects.create(
            TenantID=994, CompanyName='Deleted PO Only Co',
        )
        deleted_order = PurchaseOrder.objects.create(
            tenant=deleted_only_tenant, order_number='PO-MIG-2',
            supplier=self.supplier, order_date='2026-07-01',
            currency=self.currency, exchange_rate=Decimal('1'),
        )
        deleted_order.delete()  # soft delete (SoftDeleteMixin)
        self.assertTrue(deleted_order.is_deleted)

        migration_module = importlib.import_module(
            'logistics.migrations.0082_backfill_use_purchase_orders'
        )
        migration_module.backfill_use_purchase_orders(django_apps, schema_editor=None)

        self.assertTrue(
            PurchaseSettings.objects.get(tenant=tenant_with_order).use_purchase_orders
        )
        # لا PurchaseSettings أُنشئت أصلاً لشركة بلا أمر شراء قائم.
        self.assertFalse(
            PurchaseSettings.objects.filter(tenant=tenant_without_order).exists()
        )
        self.assertFalse(
            PurchaseSettings.objects.filter(tenant=deleted_only_tenant).exists()
        )
