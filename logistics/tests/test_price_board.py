"""PB-1 — لوحة أسعار الاستيراد (price board): جدولُ مقارنةٍ بحت.

صفوفٌ = بنود، أعمدة = موردون، خلايا = أسعار. منفصلةٌ تماماً عن
`SupplierQuotation`/`PurchaseRFQ`: لا قيد ولا مخزون ولا تحويل. سطح DRF وحده، على
نمط `test_purchase_rfq_award_and_comparison.py`.

يغطّي: عزل الشركات (لوحة شركةٍ أخرى 404، وشريكها/منتجها 400)، خليةٌ من لوحةٍ
أخرى 400، سعر الصرف (الأساس 1، وغيره بلا سعرٍ مسجَّل 400 **لا 1 صامتة**)،
`unit_price_base = السعر × سعر العمود`، السعر الفارغ يحذف الخلية، حذف المنتج
يُبقي البند باسمه، تجاهل المكرَّر في الإضافة الجماعية، فلتر الأرشيف، وسقف
استعلامات التفصيل.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting.models import ExchangeRate
from inventory.models import Product
from logistics.models import (
    PriceBoard, PriceBoardItem, PriceBoardPrice, PriceBoardSupplier,
)
from partners.models import Partner
from tenants.models import (
    Currency, MemberPermission, Tenant, UserCompanyMembership,
)

BASE = '/api/logistics/price-boards/'
NO_RATE_MESSAGE = 'لا يوجد سعر صرف مسجّل لهذه العملة — أدخله يدوياً'


class PriceBoardTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=7101, CompanyName='Price Board Co')
        cls.other_tenant = Tenant.objects.create(TenantID=7102, CompanyName='Other Board Co')
        cls.ils = Currency.objects.create(Code='ILS', Name='Shekel', IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code='USD', Name='US Dollar', IsBaseCurrency=False)
        cls.eur = Currency.objects.create(Code='EUR', Name='Euro', IsBaseCurrency=False)
        cls.user = User.objects.create_user(username='pb-manager', password='x')
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant, role='manager')
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name='Supplier One', partner_type='Supplier')
        cls.other_partner = Partner.objects.create(
            tenant=cls.other_tenant, name='Foreign Supplier', partner_type='Supplier')
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku='PB-1', name_ar='إطار ٢٠٥', brand='Brand')
        cls.other_product = Product.objects.create(
            tenant=cls.other_tenant, sku='PB-X', name_ar='صنف غريب')

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    # ── مساعدات ────────────────────────────────────────────────────────
    def make_board(self, title='لوحة أولى', tenant=None, **extra):
        return PriceBoard.objects.create(tenant=tenant or self.tenant, title=title, **extra)

    def add_item(self, board, name, seq=1, **extra):
        return PriceBoardItem.objects.create(
            tenant=board.tenant, board=board, seq=seq, name=name, **extra)

    def add_supplier(self, board, name='مورد', seq=1, currency=None, rate='1', **extra):
        return PriceBoardSupplier.objects.create(
            tenant=board.tenant, board=board, seq=seq, supplier_name=name,
            currency=currency or self.ils, exchange_rate=Decimal(rate), **extra)

    def add_rate(self, currency, rate, on=date(2026, 9, 1), tenant=None):
        return ExchangeRate.objects.create(
            tenant=tenant or self.tenant, from_currency=currency, to_currency=self.ils,
            rate=Decimal(rate), effective_date=on)


class PriceBoardCrudAndFilterTest(PriceBoardTestBase):
    def test_create_patch_delete_board(self):
        created = self.client.post(BASE, {'title': 'دفعة تموز', 'notes': 'ملاحظة'}, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        board_id = created.data['id']
        board = PriceBoard.objects.get(pk=board_id)
        self.assertEqual(board.tenant_id, self.tenant.pk)
        self.assertEqual(board.created_by_id, self.user.pk)
        self.assertFalse(board.is_archived)
        self.assertEqual(created.data['items_count'], 0)

        patched = self.client.patch(
            f'{BASE}{board_id}/', {'title': 'دفعة آب', 'is_archived': True}, format='json')
        self.assertEqual(patched.status_code, 200, patched.content)
        board.refresh_from_db()
        self.assertEqual(board.title, 'دفعة آب')
        self.assertTrue(board.is_archived)

        deleted = self.client.delete(f'{BASE}{board_id}/')
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(PriceBoard.objects.filter(pk=board_id).exists())

    def test_blank_title_rejected(self):
        for title in ('', '   '):
            response = self.client.post(BASE, {'title': title}, format='json')
            self.assertEqual(response.status_code, 400, (title, response.content))
            self.assertIn('title', response.data)

    def test_list_counts_and_archived_filter(self):
        live = self.make_board('حيّة')
        archived = self.make_board('مؤرشفة', is_archived=True)
        item = self.add_item(live, 'بند 1')
        self.add_item(live, 'بند 2', seq=2)
        supplier = self.add_supplier(live)
        PriceBoardPrice.objects.create(
            tenant=self.tenant, board_item=item, board_supplier=supplier,
            unit_price=Decimal('3'))

        default = self.client.get(BASE)
        self.assertEqual(default.status_code, 200, default.content)
        rows = default.data['results'] if isinstance(default.data, dict) else default.data
        self.assertEqual([r['id'] for r in rows], [live.pk])
        self.assertEqual(rows[0]['items_count'], 2)
        self.assertEqual(rows[0]['suppliers_count'], 1)
        self.assertEqual(rows[0]['prices_count'], 1)

        zero = self.client.get(f'{BASE}?archived=0')
        zero_rows = zero.data['results'] if isinstance(zero.data, dict) else zero.data
        self.assertEqual([r['id'] for r in zero_rows], [live.pk])

        one = self.client.get(f'{BASE}?archived=1')
        one_rows = one.data['results'] if isinstance(one.data, dict) else one.data
        self.assertEqual([r['id'] for r in one_rows], [archived.pk])


class PriceBoardTenantIsolationTest(PriceBoardTestBase):
    def test_other_tenants_board_is_404_everywhere(self):
        foreign = self.make_board('غريبة', tenant=self.other_tenant)
        foreign_item = self.add_item(foreign, 'x')
        foreign_supplier = self.add_supplier(foreign)
        self.assertEqual(self.client.get(f'{BASE}{foreign.pk}/').status_code, 404)
        self.assertEqual(
            self.client.patch(f'{BASE}{foreign.pk}/', {'title': 'x'}, format='json').status_code, 404)
        self.assertEqual(self.client.delete(f'{BASE}{foreign.pk}/').status_code, 404)
        self.assertEqual(self.client.post(
            f'{BASE}{foreign.pk}/items/', {'items': [{'name': 'a'}]}, format='json').status_code, 404)
        self.assertEqual(self.client.delete(
            f'{BASE}{foreign.pk}/items/{foreign_item.pk}/').status_code, 404)
        self.assertEqual(self.client.post(
            f'{BASE}{foreign.pk}/suppliers/',
            {'supplier_name': 'a', 'currency': self.ils.pk}, format='json').status_code, 404)
        self.assertEqual(self.client.delete(
            f'{BASE}{foreign.pk}/suppliers/{foreign_supplier.pk}/').status_code, 404)
        self.assertEqual(self.client.post(
            f'{BASE}{foreign.pk}/set-cell/',
            {'item': foreign_item.pk, 'board_supplier': foreign_supplier.pk, 'unit_price': '1'},
            format='json').status_code, 404)
        listed = self.client.get(BASE)
        rows = listed.data['results'] if isinstance(listed.data, dict) else listed.data
        self.assertEqual(rows, [])

    def test_other_tenants_partner_and_product_rejected_with_400(self):
        board = self.make_board()
        supplier = self.client.post(
            f'{BASE}{board.pk}/suppliers/',
            {'supplier_name': 'مورد', 'supplier': self.other_partner.pk,
             'currency': self.ils.pk}, format='json')
        self.assertEqual(supplier.status_code, 400, supplier.content)
        self.assertIn('supplier', supplier.data)
        self.assertEqual(board.suppliers.count(), 0)

        item = self.client.post(
            f'{BASE}{board.pk}/items/',
            {'items': [{'name': 'بند', 'product': self.other_product.pk}]}, format='json')
        self.assertEqual(item.status_code, 400, item.content)
        self.assertEqual(board.items.count(), 0)

        own = self.add_item(board, 'بند')
        patch = self.client.patch(
            f'{BASE}{board.pk}/items/{own.pk}/', {'product': self.other_product.pk}, format='json')
        self.assertEqual(patch.status_code, 400, patch.content)


class PriceBoardSupplierRateTest(PriceBoardTestBase):
    def post_supplier(self, board, **payload):
        body = {'supplier_name': 'مورد', 'currency': self.ils.pk}
        body.update(payload)
        return self.client.post(f'{BASE}{board.pk}/suppliers/', body, format='json')

    def test_base_currency_without_rate_gets_exactly_one(self):
        board = self.make_board()
        response = self.post_supplier(board)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Decimal(str(response.data['exchange_rate'])), Decimal('1'))
        self.assertEqual(response.data['currency_code'], 'ILS')
        self.assertEqual(response.data['seq'], 1)
        self.assertEqual(response.data['attachments'], [])

    def test_base_currency_rate_is_always_one_even_if_sent_otherwise(self):
        # عمودٌ بعملة الأساس بسعرٍ غير 1 يُضخِّم أسعاره في المقارنة بصمت.
        board = self.make_board()
        response = self.post_supplier(board, exchange_rate='3.7')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Decimal(str(response.data['exchange_rate'])), Decimal('1'))
        column = self.post_supplier(board, currency=self.usd.pk, exchange_rate='3.6').data
        moved = self.client.patch(
            f"{BASE}{board.pk}/suppliers/{column['id']}/",
            {'currency': self.ils.pk, 'exchange_rate': '3.6'}, format='json')
        self.assertEqual(moved.status_code, 200, moved.content)
        self.assertEqual(Decimal(str(moved.data['exchange_rate'])), Decimal('1'))

    def test_foreign_currency_without_registered_rate_is_400_never_one(self):
        board = self.make_board()
        response = self.post_supplier(board, currency=self.usd.pk, offer_date='2026-09-10')
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(list(response.data['exchange_rate']), [NO_RATE_MESSAGE])
        self.assertEqual(board.suppliers.count(), 0)

    def test_foreign_currency_uses_registered_rate_for_offer_date(self):
        board = self.make_board()
        self.add_rate(self.usd, '3.500000', on=date(2026, 9, 1))
        self.add_rate(self.usd, '3.700000', on=date(2026, 9, 20))
        response = self.post_supplier(board, currency=self.usd.pk, offer_date='2026-09-10')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Decimal(str(response.data['exchange_rate'])), Decimal('3.5'))

    def test_other_tenants_rate_is_not_used(self):
        board = self.make_board()
        self.add_rate(self.usd, '3.500000', tenant=self.other_tenant)
        response = self.post_supplier(board, currency=self.usd.pk, offer_date='2026-09-10')
        self.assertEqual(response.status_code, 400, response.content)

    def test_explicit_rate_is_kept_and_must_be_positive(self):
        board = self.make_board()
        ok = self.post_supplier(board, currency=self.usd.pk, exchange_rate='3.61')
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertEqual(Decimal(str(ok.data['exchange_rate'])), Decimal('3.61'))
        for bad in ('0', '-1'):
            response = self.post_supplier(board, currency=self.usd.pk, exchange_rate=bad)
            self.assertEqual(response.status_code, 400, (bad, response.content))

    def test_changing_currency_without_rate_reruns_lookup(self):
        board = self.make_board()
        supplier = self.add_supplier(board, currency=self.ils, rate='1')
        no_rate = self.client.patch(
            f'{BASE}{board.pk}/suppliers/{supplier.pk}/', {'currency': self.eur.pk}, format='json')
        self.assertEqual(no_rate.status_code, 400, no_rate.content)
        self.assertEqual(list(no_rate.data['exchange_rate']), [NO_RATE_MESSAGE])
        supplier.refresh_from_db()
        self.assertEqual(supplier.currency_id, self.ils.pk)

        self.add_rate(self.eur, '4.000000')
        ok = self.client.patch(
            f'{BASE}{board.pk}/suppliers/{supplier.pk}/', {'currency': self.eur.pk}, format='json')
        self.assertEqual(ok.status_code, 200, ok.content)
        supplier.refresh_from_db()
        self.assertEqual(supplier.currency_id, self.eur.pk)
        self.assertEqual(supplier.exchange_rate, Decimal('4'))

    def test_patch_without_currency_change_keeps_rate(self):
        board = self.make_board()
        supplier = self.add_supplier(board, currency=self.usd, rate='3.6')
        response = self.client.patch(
            f'{BASE}{board.pk}/suppliers/{supplier.pk}/', {'terms': 'FOB'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        supplier.refresh_from_db()
        self.assertEqual(supplier.exchange_rate, Decimal('3.6'))
        self.assertEqual(supplier.terms, 'FOB')

    def test_seq_is_appended_and_blank_name_rejected(self):
        board = self.make_board()
        self.add_supplier(board, seq=4)
        response = self.post_supplier(board, supplier_name='ثانٍ')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['seq'], 5)
        blank = self.post_supplier(board, supplier_name='  ')
        self.assertEqual(blank.status_code, 400, blank.content)

    def test_attachments_rules(self):
        board = self.make_board()
        good = self.post_supplier(board, attachments=[
            {'name': 'عرض', 'url': 'https://drive.google.com/file/d/abc/view'},
            {'name': 'ملف', 'url': 'http://files.example/x.pdf', 'type': 'pdf', 'size': 10},
        ])
        self.assertEqual(good.status_code, 201, good.content)
        self.assertEqual(len(good.data['attachments']), 2)
        for bad in (
            'not-a-list',
            ['https://x'],
            [{'name': 'بلا رابط'}],
            [{'url': '   '}],
            [{'url': 'javascript:alert(1)'}],
            [{'url': 'ftp://host/f'}],
        ):
            response = self.post_supplier(board, attachments=bad)
            self.assertEqual(response.status_code, 400, (bad, response.content))
            self.assertIn('attachments', response.data)

    def test_delete_supplier_reports_deleted_prices(self):
        board = self.make_board()
        item_a = self.add_item(board, 'أ')
        item_b = self.add_item(board, 'ب', seq=2)
        supplier = self.add_supplier(board)
        other = self.add_supplier(board, name='آخر', seq=2)
        for item in (item_a, item_b):
            PriceBoardPrice.objects.create(
                tenant=self.tenant, board_item=item, board_supplier=supplier, unit_price=Decimal('1'))
        PriceBoardPrice.objects.create(
            tenant=self.tenant, board_item=item_a, board_supplier=other, unit_price=Decimal('2'))
        response = self.client.delete(f'{BASE}{board.pk}/suppliers/{supplier.pk}/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['deleted_prices'], 2)
        self.assertEqual(PriceBoardPrice.objects.filter(board_item__board=board).count(), 1)

    def test_supplier_of_another_board_is_404(self):
        board = self.make_board()
        other_board = self.make_board('أخرى')
        foreign = self.add_supplier(other_board)
        self.assertEqual(self.client.patch(
            f'{BASE}{board.pk}/suppliers/{foreign.pk}/', {'terms': 'x'}, format='json').status_code, 404)
        self.assertEqual(self.client.delete(
            f'{BASE}{board.pk}/suppliers/{foreign.pk}/').status_code, 404)


class PriceBoardItemsTest(PriceBoardTestBase):
    def post_items(self, board, items):
        return self.client.post(f'{BASE}{board.pk}/items/', {'items': items}, format='json')

    def test_bulk_add_appends_seq_and_returns_created(self):
        board = self.make_board()
        self.add_item(board, 'موجود', seq=7)
        response = self.post_items(board, [
            {'name': 'إطار', 'unit_of_measure': 'حبة', 'quantity': '12.5', 'note': 'ن'},
            {'name': 'بطارية', 'product': self.product.pk},
        ])
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['skipped_duplicates'], 0)
        created = response.data['created']
        self.assertEqual([c['seq'] for c in created], [8, 9])
        self.assertEqual(created[0]['unit_of_measure'], 'حبة')
        self.assertEqual(Decimal(str(created[0]['quantity'])), Decimal('12.5'))
        self.assertIsNone(created[0]['product'])
        self.assertEqual(created[1]['product'], self.product.pk)
        self.assertEqual(created[1]['product_name'], 'إطار ٢٠٥ (Brand)')
        for key in ('id', 'seq', 'name', 'product', 'product_name', 'unit_of_measure',
                    'quantity', 'note'):
            self.assertIn(key, created[0])

    def test_duplicates_skipped_case_and_space_insensitive_including_in_batch(self):
        board = self.make_board()
        self.add_item(board, 'Tyre A')
        response = self.post_items(board, [
            {'name': '  tyre a  '},
            {'name': 'TYRE A'},
            {'name': 'Tyre B'},
            {'name': 'tyre b '},
            {'name': 'Tyre C'},
        ])
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual([c['name'] for c in response.data['created']], ['Tyre B', 'Tyre C'])
        self.assertEqual(response.data['skipped_duplicates'], 3)
        self.assertEqual(board.items.count(), 3)

    def test_dedupe_is_per_board(self):
        board = self.make_board()
        other = self.make_board('أخرى')
        self.add_item(other, 'نفس الاسم')
        response = self.post_items(board, [{'name': 'نفس الاسم'}])
        self.assertEqual(response.data['skipped_duplicates'], 0)
        self.assertEqual(len(response.data['created']), 1)

    def test_blank_name_and_empty_batch_rejected(self):
        board = self.make_board()
        self.assertEqual(self.post_items(board, [{'name': '   '}]).status_code, 400)
        self.assertEqual(self.post_items(board, []).status_code, 400)
        self.assertEqual(self.client.post(
            f'{BASE}{board.pk}/items/', {}, format='json').status_code, 400)
        self.assertEqual(board.items.count(), 0)

    def test_one_bad_entry_rejects_whole_batch(self):
        board = self.make_board()
        response = self.post_items(board, [{'name': 'جيد'}, {'name': 'x', 'quantity': 'abc'}])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(board.items.count(), 0)

    def test_patch_and_delete_item(self):
        board = self.make_board()
        item = self.add_item(board, 'قديم')
        supplier = self.add_supplier(board)
        PriceBoardPrice.objects.create(
            tenant=self.tenant, board_item=item, board_supplier=supplier, unit_price=Decimal('5'))
        patched = self.client.patch(
            f'{BASE}{board.pk}/items/{item.pk}/',
            {'name': 'جديد', 'quantity': '3', 'unit_of_measure': 'كرتون', 'note': 'ن',
             'product': self.product.pk}, format='json')
        self.assertEqual(patched.status_code, 200, patched.content)
        item.refresh_from_db()
        self.assertEqual(item.name, 'جديد')
        self.assertEqual(item.product_id, self.product.pk)
        self.assertEqual(self.client.patch(
            f'{BASE}{board.pk}/items/{item.pk}/', {'name': ' '}, format='json').status_code, 400)
        deleted = self.client.delete(f'{BASE}{board.pk}/items/{item.pk}/')
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(PriceBoardItem.objects.filter(pk=item.pk).exists())
        self.assertFalse(PriceBoardPrice.objects.filter(board_supplier=supplier).exists())

    def test_item_of_another_board_is_404(self):
        board = self.make_board()
        other = self.make_board('أخرى')
        foreign = self.add_item(other, 'x')
        self.assertEqual(self.client.patch(
            f'{BASE}{board.pk}/items/{foreign.pk}/', {'name': 'y'}, format='json').status_code, 404)
        self.assertEqual(self.client.delete(f'{BASE}{board.pk}/items/{foreign.pk}/').status_code, 404)

    def test_deleting_linked_product_keeps_item_with_name(self):
        board = self.make_board()
        item = self.add_item(board, 'إطار ٢٠٥', product=self.product)
        self.product.delete()
        item.refresh_from_db()
        self.assertIsNone(item.product_id)
        self.assertEqual(item.name, 'إطار ٢٠٥')
        detail = self.client.get(f'{BASE}{board.pk}/')
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertIsNone(detail.data['items'][0]['product'])
        self.assertEqual(detail.data['items'][0]['name'], 'إطار ٢٠٥')
        self.assertEqual(detail.data['items'][0]['product_name'], '')


class PriceBoardSetCellTest(PriceBoardTestBase):
    def setUp(self):
        super().setUp()
        self.board = self.make_board()
        self.item = self.add_item(self.board, 'إطار')
        self.usd_col = self.add_supplier(self.board, 'USD', currency=self.usd, rate='3.5')
        self.url = f'{BASE}{self.board.pk}/set-cell/'

    def set_cell(self, **payload):
        body = {'item': self.item.pk, 'board_supplier': self.usd_col.pk}
        body.update(payload)
        return self.client.post(self.url, body, format='json')

    def test_upsert_returns_price_with_base_value(self):
        first = self.set_cell(unit_price='10.2500', note='FOB')
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(Decimal(str(first.data['unit_price'])), Decimal('10.25'))
        self.assertEqual(Decimal(str(first.data['unit_price_base'])), Decimal('35.8750'))
        self.assertEqual(first.data['item'], self.item.pk)
        self.assertEqual(first.data['board_supplier'], self.usd_col.pk)
        self.assertEqual(first.data['note'], 'FOB')
        second = self.set_cell(unit_price='11')
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.data['id'], first.data['id'])
        self.assertEqual(PriceBoardPrice.objects.count(), 1)
        # الملاحظة لا تُمحى حين لا تُرسَل
        self.assertEqual(PriceBoardPrice.objects.get().note, 'FOB')

    def test_editing_contents_moves_board_to_top_of_list(self):
        # القائمة مرتّبة بـ`-updated_at`: لوحةٌ عُدِّلت خلاياها/بنودها/أعمدتها تصعد.
        older = self.make_board(title='أقدم')
        PriceBoard.objects.filter(pk=self.board.pk).update(updated_at=older.updated_at.replace(year=2020))
        writes = (
            lambda: self.set_cell(unit_price='5'),
            lambda: self.client.post(f'{BASE}{self.board.pk}/items/', {'items': [{'name': 'جديد'}]}, format='json'),
            lambda: self.client.post(
                f'{BASE}{self.board.pk}/suppliers/', {'supplier_name': 'م', 'currency': self.ils.pk}, format='json'),
        )
        def first_id():
            rows = self.client.get(BASE).data
            rows = rows.get('results', rows) if isinstance(rows, dict) else rows
            return rows[0]['id']

        for write in writes:
            PriceBoard.objects.filter(pk=self.board.pk).update(updated_at=older.updated_at.replace(year=2020))
            self.assertEqual(first_id(), older.pk)
            write()
            self.assertEqual(first_id(), self.board.pk)

    def test_null_price_deletes_cell(self):
        self.set_cell(unit_price='5')
        response = self.set_cell(unit_price=None)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data, {'deleted': True})
        self.assertEqual(PriceBoardPrice.objects.count(), 0)
        # حذف خليةٍ غير موجودة ليس خطأ
        self.assertEqual(self.set_cell(unit_price=None).status_code, 200)

    def test_missing_or_negative_price_rejected(self):
        self.assertEqual(self.set_cell().status_code, 400)
        self.assertEqual(self.set_cell(unit_price='-1').status_code, 400)
        self.assertEqual(self.set_cell(unit_price='abc').status_code, 400)
        self.assertEqual(PriceBoardPrice.objects.count(), 0)

    def test_zero_price_is_a_valid_price(self):
        response = self.set_cell(unit_price='0')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(PriceBoardPrice.objects.count(), 1)

    def test_item_and_supplier_from_different_boards_rejected(self):
        other = self.make_board('أخرى')
        other_item = self.add_item(other, 'x')
        other_col = self.add_supplier(other, 'y')
        mixed_item = self.client.post(self.url, {
            'item': other_item.pk, 'board_supplier': self.usd_col.pk, 'unit_price': '1',
        }, format='json')
        self.assertEqual(mixed_item.status_code, 400, mixed_item.content)
        mixed_col = self.client.post(self.url, {
            'item': self.item.pk, 'board_supplier': other_col.pk, 'unit_price': '1',
        }, format='json')
        self.assertEqual(mixed_col.status_code, 400, mixed_col.content)
        unknown = self.client.post(self.url, {
            'item': 999999, 'board_supplier': self.usd_col.pk, 'unit_price': '1',
        }, format='json')
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(PriceBoardPrice.objects.count(), 0)

    def test_unique_cell_constraint(self):
        PriceBoardPrice.objects.create(
            tenant=self.tenant, board_item=self.item, board_supplier=self.usd_col,
            unit_price=Decimal('1'))
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            PriceBoardPrice.objects.create(
                tenant=self.tenant, board_item=self.item, board_supplier=self.usd_col,
                unit_price=Decimal('2'))


class PriceBoardDetailTest(PriceBoardTestBase):
    def build_board(self, items=2, suppliers=2):
        board = self.make_board('تفصيل', notes='ن')
        item_rows = [
            self.add_item(board, f'بند {i}', seq=i + 1, product=self.product if i == 0 else None)
            for i in range(items)
        ]
        cols = [
            self.add_supplier(
                board, f'مورد {i}', seq=i + 1,
                currency=self.usd if i % 2 == 0 else self.ils,
                rate='3.5' if i % 2 == 0 else '1',
                offer_date=date(2026, 9, 1), terms='FOB',
                attachments=[{'name': 'a', 'url': 'https://x.example/a.pdf'}],
            )
            for i in range(suppliers)
        ]
        for item in item_rows:
            for col in cols:
                PriceBoardPrice.objects.create(
                    tenant=self.tenant, board_item=item, board_supplier=col,
                    unit_price=Decimal('10.1234'))
        return board

    def test_detail_shape_and_base_values(self):
        board = self.build_board()
        response = self.client.get(f'{BASE}{board.pk}/')
        self.assertEqual(response.status_code, 200, response.content)
        data = response.data
        for key in ('id', 'title', 'notes', 'is_archived', 'created_at', 'updated_at',
                    'base_currency_code', 'items', 'suppliers', 'prices'):
            self.assertIn(key, data)
        self.assertEqual(data['base_currency_code'], 'ILS')
        self.assertEqual([i['seq'] for i in data['items']], [1, 2])
        self.assertEqual(data['items'][0]['product_name'], 'إطار ٢٠٥ (Brand)')
        self.assertEqual(data['items'][1]['product_name'], '')
        for key in ('id', 'seq', 'supplier_name', 'supplier', 'currency', 'currency_code',
                    'exchange_rate', 'offer_date', 'terms', 'attachments'):
            self.assertIn(key, data['suppliers'][0])
        self.assertEqual(data['suppliers'][0]['currency_code'], 'USD')
        self.assertEqual(len(data['prices']), 4)
        by_supplier = {}
        for price in data['prices']:
            for key in ('id', 'item', 'board_supplier', 'unit_price', 'unit_price_base', 'note'):
                self.assertIn(key, price)
            by_supplier.setdefault(price['board_supplier'], set()).add(
                Decimal(str(price['unit_price_base'])))
        usd_col, ils_col = data['suppliers'][0]['id'], data['suppliers'][1]['id']
        self.assertEqual(by_supplier[usd_col], {Decimal('35.4319')})  # 10.1234 × 3.5 = 35.4319
        self.assertEqual(by_supplier[ils_col], {Decimal('10.1234')})

    def test_unit_price_base_is_quantized_to_four_places(self):
        board = self.make_board()
        item = self.add_item(board, 'x')
        col = self.add_supplier(board, currency=self.usd, rate='3.333333')
        PriceBoardPrice.objects.create(
            tenant=self.tenant, board_item=item, board_supplier=col, unit_price=Decimal('1.1111'))
        detail = self.client.get(f'{BASE}{board.pk}/').data
        # 1.1111 × 3.333333 = 3.70370... → 3.7037
        self.assertEqual(detail['prices'][0]['unit_price_base'], '3.7037')

    def test_query_count_does_not_grow_with_board_size(self):
        small = self.build_board(items=1, suppliers=1)
        big = self.build_board(items=6, suppliers=4)
        url_small, url_big = f'{BASE}{small.pk}/', f'{BASE}{big.pk}/'
        self.client.get(url_small)  # يسخّن أي كاش (عضوية/صلاحيات)
        with CaptureQueriesContext(connection) as small_q:
            self.client.get(url_small)
        with CaptureQueriesContext(connection) as big_q:
            response = self.client.get(url_big)
        self.assertEqual(len(response.data['prices']), 24)
        self.assertEqual(len(small_q), len(big_q), [q['sql'] for q in big_q.captured_queries])
        self.assertLessEqual(len(big_q), 15)


class PriceBoardPermissionTest(PriceBoardTestBase):
    """القراءة تشترط `import.procurement.view` — اللوحة تُعدّ «استيراداً» دائماً."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.staff = User.objects.create_user(username='pb-staff', password='x')
        UserCompanyMembership.objects.create(user=cls.staff, tenant=cls.tenant, role='staff')
        cls.importer = User.objects.create_user(username='pb-importer', password='x')
        membership = UserCompanyMembership.objects.create(
            user=cls.importer, tenant=cls.tenant, role='staff')
        MemberPermission.objects.create(
            membership=membership, permission_key='import.procurement.view', allowed=True)
        cls.viewer = User.objects.create_user(username='pb-viewer', password='x')
        UserCompanyMembership.objects.create(user=cls.viewer, tenant=cls.tenant, role='viewer')

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def test_member_without_import_view_cannot_list_or_read(self):
        board = self.make_board()
        self.as_user(self.staff)
        self.assertEqual(self.client.get(BASE).status_code, 403)
        self.assertEqual(self.client.get(BASE + '?scope=local').status_code, 403)
        self.assertEqual(self.client.get(f'{BASE}{board.pk}/').status_code, 403)

    def test_member_with_import_view_can_read(self):
        board = self.make_board()
        self.as_user(self.importer)
        self.assertEqual(self.client.get(BASE).status_code, 200)
        self.assertEqual(self.client.get(f'{BASE}{board.pk}/').status_code, 200)

    def test_viewer_role_cannot_write(self):
        board = self.make_board()
        self.as_user(self.viewer)
        self.assertEqual(self.client.post(BASE, {'title': 'x'}, format='json').status_code, 403)
        self.assertEqual(self.client.post(
            f'{BASE}{board.pk}/items/', {'items': [{'name': 'a'}]}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'{BASE}{board.pk}/').status_code, 403)
