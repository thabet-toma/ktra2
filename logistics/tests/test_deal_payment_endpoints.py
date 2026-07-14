"""ج8 — الدفعة مورد REST مستقل + مبدأ «الصفقة لا تُرحَّل، الدفعات فقط».

يغطي شكوى المالك الحرفية (المحاولة الرابعة):
- «دفعت الدفعة الأولى وجيت أأكدها → هذا المستند مرحَّل» ⇒ تأكيد المورد على
  دفعة مرحّلة يجب أن ينجح (حقل توثيقي لا مالي).
- «ما عاد أقدر أساوي شي بالصفقة» ⇒ إضافة دفعة ثانية وتعديل وصفي يجب أن ينجحا
  مع وجود دفعة مرحّلة.
- الحماية المالية الوحيدة: أرضية الإجمالي (لا يهبط تحت مجموع المرحّل) +
  قفل مبلغ الدفعة المرحّلة + سقف مجموع الدفعات ≤ الإجمالي.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from tenants.models import Tenant, Currency, UserCompanyMembership
from partners.models import Partner
from inventory.models import Product
from logistics.models import LogisticsDeal, LogisticsPayment


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=930, CompanyName='Pay Co')
        cls.cur, _ = Currency.objects.get_or_create(
            Code='ILS', defaults={'Symbol': '₪', 'IsBaseCurrency': True}
        )
        cls.user = User.objects.create_user(username='pay_user', password='x')
        Token.objects.create(user=cls.user)
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant, role='manager')
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name='Supplier P', partner_type='Supplier'
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku='DP-1', name_ar='صنف صفقة',
            quantity_on_hand=Decimal('0'), avg_cost=Decimal('0'))

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _mk_deal(self, ref, total='1000'):
        return LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number=ref, partner=self.partner,
            order_date='2026-07-01', currency=self.cur,
            total_amount=Decimal(total),
        )

    def _mk_payment(self, deal, number=1, amount='500', posted=False):
        return LogisticsPayment.objects.create(
            deal=deal, payment_number=number, title=f'دفعة {number}',
            amount=Decimal(amount), is_posted=posted,
        )

    def _payments_url(self, deal, payment=None):
        base = f'/api/logistics/deals/{deal.id}/payments/'
        return f'{base}{payment.id}/' if payment else base


class CreatePaymentEndpointTest(_Base):
    def test_create_returns_real_sql_id(self):
        deal = self._mk_deal('D-0801')
        resp = self.client.post(
            self._payments_url(deal),
            {'payment_number': 1, 'title': 'الدفعة 1', 'amount': '400'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        pid = resp.json()['id']
        self.assertTrue(LogisticsPayment.objects.filter(pk=pid, deal=deal).exists())

    def test_create_second_payment_with_first_posted(self):
        """جوهر الشكوى: بعد ترحيل الدفعة الأولى، الدفعة الثانية كانت مستحيلة."""
        deal = self._mk_deal('D-0802')
        self._mk_payment(deal, number=1, amount='500', posted=True)
        resp = self.client.post(
            self._payments_url(deal),
            {'payment_number': 2, 'title': 'الدفعة 2', 'amount': '300'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(deal.payments.count(), 2)

    def test_create_over_cap_rejected(self):
        deal = self._mk_deal('D-0803', total='1000')
        self._mk_payment(deal, number=1, amount='800')
        resp = self.client.post(
            self._payments_url(deal),
            {'payment_number': 2, 'title': 'الدفعة 2', 'amount': '300'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(deal.payments.count(), 1)

    def test_duplicate_installment_number_rejected(self):
        deal = self._mk_deal('D-0804')
        self._mk_payment(deal, number=1, amount='100')
        resp = self.client.post(
            self._payments_url(deal),
            {'payment_number': 1, 'title': 'مكررة', 'amount': '100'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)


class UpdatePaymentEndpointTest(_Base):
    def test_confirm_supplier_on_posted_payment_allowed(self):
        """جوهر الشكوى: تأكيد المورد بعد الترحيل كان يرد «هذا المستند مرحَّل»."""
        deal = self._mk_deal('D-0811')
        pay = self._mk_payment(deal, number=1, amount='500', posted=True)
        resp = self.client.patch(
            self._payments_url(deal, pay),
            {
                'confirmed_by_supplier': True,
                'supplier_notes': 'وصل التأكيد',
                'confirmation_date': '2026-07-12',
                'status': 'Confirmed',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        pay.refresh_from_db()
        self.assertTrue(pay.confirmed_by_supplier)
        self.assertEqual(pay.status, 'Confirmed')

    def test_posted_payment_amount_locked(self):
        deal = self._mk_deal('D-0812')
        pay = self._mk_payment(deal, number=1, amount='500', posted=True)
        resp = self.client.patch(
            self._payments_url(deal, pay), {'amount': '999'}, format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        pay.refresh_from_db()
        self.assertEqual(Decimal(pay.amount), Decimal('500'))

    def test_posted_payment_resend_same_amount_tolerated(self):
        """الواجهة تعيد إرسال الصف كاملاً — نفس القيمة لا تُعد تعديلاً مالياً."""
        deal = self._mk_deal('D-0813')
        pay = self._mk_payment(deal, number=1, amount='500', posted=True)
        resp = self.client.patch(
            self._payments_url(deal, pay),
            {'amount': '500.00', 'supplier_notes': 'ملاحظة'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_unposted_payment_amount_editable_within_cap(self):
        deal = self._mk_deal('D-0814', total='1000')
        pay = self._mk_payment(deal, number=1, amount='500')
        resp = self.client.patch(
            self._payments_url(deal, pay), {'amount': '700'}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        pay.refresh_from_db()
        self.assertEqual(Decimal(pay.amount), Decimal('700'))

    def test_update_over_cap_rejected(self):
        deal = self._mk_deal('D-0815', total='1000')
        self._mk_payment(deal, number=1, amount='600')
        pay2 = self._mk_payment(deal, number=2, amount='300')
        resp = self.client.patch(
            self._payments_url(deal, pay2), {'amount': '500'}, format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)


class DealNotPostedDocTest(_Base):
    """«الصفقة لا تُرحَّل — الدفعات فقط» (قرار المالك Q3)."""

    def test_deal_patch_with_posted_payment_no_longer_blocked(self):
        deal = self._mk_deal('D-0821')
        self._mk_payment(deal, number=1, amount='500', posted=True)
        resp = self.client.patch(
            f'/api/logistics/deals/{deal.id}/',
            {'description': 'وصف جديد', 'notes': 'ملاحظات'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        deal.refresh_from_db()
        self.assertEqual(deal.description, 'وصف جديد')

    def test_total_floor_guard_blocks_items_below_posted(self):
        """تخفيض بنود الصفقة تحت مجموع المرحّل يُرفض ويرتد الحفظ كاملاً."""
        deal = self._mk_deal('D-0822', total='0')
        patch_items = lambda qty: self.client.patch(
            f'/api/logistics/deals/{deal.id}/',
            {'items': [{'product': self.product.id, 'quantity': qty, 'unit_price': '100'}]},
            format='json',
        )
        resp = patch_items('10')  # total = 1000
        self.assertEqual(resp.status_code, 200, resp.content)
        deal.refresh_from_db()
        self.assertEqual(Decimal(deal.total_amount), Decimal('1000.00'))

        self._mk_payment(deal, number=1, amount='800', posted=True)
        resp = patch_items('5')  # total = 500 < 800 المرحّل
        self.assertEqual(resp.status_code, 400, resp.content)
        deal.refresh_from_db()
        self.assertEqual(Decimal(deal.total_amount), Decimal('1000.00'))
        self.assertEqual(deal.items.count(), 1)
        self.assertEqual(Decimal(deal.items.first().quantity), Decimal('10'))

    def test_nested_payments_in_deal_patch_ignored(self):
        """الدفعات قراءة فقط في serializer الصفقة — إرسالها لا يعدّل ولا يحذف."""
        deal = self._mk_deal('D-0823')
        pay = self._mk_payment(deal, number=1, amount='500')
        resp = self.client.patch(
            f'/api/logistics/deals/{deal.id}/',
            {'payments': [], 'notes': 'تجاهل الدفعات المتداخلة'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(LogisticsPayment.objects.filter(pk=pay.pk).exists())
