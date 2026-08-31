# -*- coding: utf-8 -*-
"""استيراد بيانات شركة «الجرابعه» من ملفات CSV (نسخة احتياطية من موقع محاسبة منتهٍ)
إلى قاعدة بيانات النظام (SQL) مع ترحيل محاسبي كامل.

خاص بشركة الجرابعه فقط (Tenant اسمه «الجرابعه»). يرفض الأمر العمل على أي شركة أخرى.

المراحل:
  1) البنية المحاسبية: عملات + شجرة حسابات + فترات مالية + مستودع + مجموعات شركاء + إعدادات مبيعات
  2) الشركاء: العملاء (Clients) + الموردون (Suppliers)
  3) المنتجات: Products → inventory.Product (+ فئات + شرائح أسعار)
  4) فواتير المبيعات: Invoices + Invoice_items → sales.SalesInvoice (ترحيل قيد + خصم مخزون + تسوية النقدي)
  5) فواتير الشراء: Purchase_orders + Purchase_order_items → logistics.PurchaseInvoice (استلام مخزون + قيد ذمم مورد)

الاستخدام:
  python manage.py import_jarabaa --csv-dir <path> [--limit N] [--wipe] [--stage infra,partners,products,sales,purchases]

الأمر idempotent وقابل للاستئناف: المستندات المستوردة سابقاً تُتخطّى. --wipe يمسح بيانات
شركة الجرابعه فقط لإعادة تشغيل نظيفة.
"""
from __future__ import annotations

import csv
import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

DEC = Decimal("0.01")

# شجرة الحسابات المهنية (مطابقة seed_professional_coa) + حساب COGS ورقي 5101.
COA = [
    ('1', 'الأصول (Assets)', 'Asset', None),
    ('2', 'الخصوم (Liabilities)', 'Liability', None),
    ('3', 'حقوق الملكية (Equity)', 'Equity', None),
    ('4', 'الإيرادات (Revenue)', 'Revenue', None),
    ('5', 'المصروفات (Expenses)', 'Expense', None),
    ('11', 'الأصول المتداولة (Current Assets)', 'Asset', '1'),
    ('1101', 'النقدية (Cash)', 'Asset', '11'),
    ('1102', 'البنوك (Banks)', 'Asset', '11'),
    ('1103', 'المدينون التجاريون (Trade Receivables)', 'Asset', '11'),
    ('1104', 'المخزون (Inventory)', 'Asset', '11'),
    ('1105', 'ضريبة القيمة المضافة - مدخلات (VAT Input)', 'Asset', '11'),
    ('12', 'الأصول الثابتة (Fixed Assets)', 'Asset', '1'),
    ('21', 'الالتزامات المتداولة (Current Liabilities)', 'Liability', '2'),
    ('2101', 'الدائنون التجاريون (Trade Payables)', 'Liability', '21'),
    ('2104', 'ضريبة القيمة المضافة - مخرجات (VAT Output)', 'Liability', '21'),
    ('31', 'رأس المال (Capital)', 'Equity', '3'),
    ('3101', 'رأس المال المدفوع (Paid-in Capital)', 'Equity', '31'),
    ('32', 'الأرباح المحتجزة (Retained Earnings)', 'Equity', '3'),
    ('3201', 'أرصدة افتتاحية (Opening Balances)', 'Equity', '32'),
    ('41', 'المبيعات (Sales)', 'Revenue', '4'),
    ('4101', 'مبيعات المنتجات (Product Sales)', 'Revenue', '41'),
    ('4102', 'مبيعات الخدمات (Service Sales)', 'Revenue', '41'),
    ('51', 'تكلفة المبيعات (Cost of Goods Sold)', 'Expense', '5'),
    ('5101', 'تكلفة البضاعة المباعة (COGS)', 'Expense', '51'),
    ('52', 'المصاريف التشغيلية (Operating Expenses)', 'Expense', '5'),
]

TENANT_NAME = 'الجرابعه'


def clean(v):
    """ينظّف قيمة نصية: يُرجع None للفراغ أو مسافة أو 0000-00-00."""
    if v is None:
        return None
    s = str(v).replace('\t', ' ').strip()
    if s in ('', '0000-00-00'):
        return None
    return s


def dec(v, default=Decimal('0')):
    s = clean(v)
    if s is None:
        return default
    s = s.replace(',', '')
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return default


def pdate(v):
    s = clean(v)
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return datetime.datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def norm_name(s):
    """تطبيع اسم منتج للمطابقة: إزالة التبويب وطي المسافات."""
    if not s:
        return ''
    return ' '.join(str(s).replace('\t', ' ').split())


def read_csv(path: Path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f, delimiter=';'):
            yield { (k.strip() if k else k): v for k, v in row.items() }


class Command(BaseCommand):
    help = 'استيراد بيانات شركة الجرابعه من CSV مع ترحيل محاسبي كامل (Tenant الجرابعه فقط).'

    def add_arguments(self, parser):
        parser.add_argument('--csv-dir', required=True, help='مجلد ملفات CSV')
        parser.add_argument('--tenant-id', type=int, default=None,
                            help='تجاوز اكتشاف الشركة (يُتحقق من الاسم = الجرابعه)')
        parser.add_argument('--limit', type=int, default=0,
                            help='حدّ أقصى لعدد الفواتير/أوامر الشراء المُعالَجة (0 = الكل) — للاختبار')
        parser.add_argument('--wipe', action='store_true',
                            help='مسح بيانات شركة الجرابعه المعاملاتية قبل الاستيراد (إعادة تشغيل نظيفة)')
        parser.add_argument('--stage', default='infra,partners,products,sales,purchases',
                            help='المراحل المطلوبة مفصولة بفواصل')

    # ────────────────────────────────────────────────────────────────
    def handle(self, *args, **opt):
        self.csv_dir = Path(opt['csv_dir'])
        if not self.csv_dir.is_dir():
            raise CommandError(f'مجلد CSV غير موجود: {self.csv_dir}')
        self.limit = opt['limit']
        stages = {s.strip() for s in opt['stage'].split(',') if s.strip()}

        from tenants.models import Tenant
        # ── حارس الأمان: شركة الجرابعه فقط ──
        if opt['tenant_id'] is not None:
            tenant = Tenant.objects.filter(TenantID=opt['tenant_id']).first()
        else:
            qs = Tenant.objects.filter(CompanyName=TENANT_NAME)
            if qs.count() > 1:
                raise CommandError(f'يوجد أكثر من شركة باسم «{TENANT_NAME}» — مرّر --tenant-id.')
            tenant = qs.first()
        if not tenant:
            raise CommandError(f'لم يُعثر على شركة «{TENANT_NAME}».')
        if (tenant.CompanyName or '').strip() != TENANT_NAME:
            raise CommandError(
                f'حارس الأمان: الشركة #{tenant.TenantID} اسمها «{tenant.CompanyName}» '
                f'وليست «{TENANT_NAME}». رُفض التنفيذ حمايةً لبيانات الشركات الأخرى.'
            )
        self.tenant = tenant
        self.tid = tenant.TenantID
        self.stdout.write(self.style.WARNING(
            f'الهدف: شركة #{self.tid} «{tenant.CompanyName}» — ستُكتب البيانات هنا حصراً.'))

        if opt['wipe']:
            self._wipe()

        self.summary = {}
        if 'infra' in stages:
            self._stage_infra()
        # لا بد من البنية دائماً للمراحل اللاحقة
        self._load_infra_refs()
        if 'partners' in stages:
            self._stage_partners()
        self._load_partner_maps()
        if 'products' in stages:
            self._stage_products()
        self._load_product_map()
        if 'sales' in stages:
            self._stage_sales()
        if 'purchases' in stages:
            self._stage_purchases()

        self.stdout.write(self.style.SUCCESS('\n=== ملخص الاستيراد ==='))
        for k, v in self.summary.items():
            self.stdout.write(f'  {k}: {v}')

    # ────────────────────────────────────────────────────────────────
    def _wipe(self):
        from accounting.models import JournalHeader, JournalLine
        from inventory.models import StockMovement, Product, ProductCategory, ProductPriceTier
        from sales.models import (SalesInvoice, SalesInvoiceLine, CustomerPayment,
                                   PaymentAllocation, SupplierPayment)
        from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
        from django.db import connection
        tid = self.tid
        with transaction.atomic():
            PaymentAllocation.objects.filter(tenant_id=tid).delete()
            CustomerPayment.objects.filter(tenant_id=tid).delete()
            SupplierPayment.objects.filter(tenant_id=tid).delete()
            SalesInvoiceLine.objects.filter(tenant_id=tid).delete()
            SalesInvoice.objects.filter(tenant_id=tid).delete()
            PurchaseInvoiceItem.objects.filter(invoice__tenant_id=tid).delete()
            PurchaseInvoice.objects.filter(tenant_id=tid).delete()
            StockMovement.objects.filter(tenant_id=tid).delete()
            JournalLine.objects.filter(journal__tenant_id=tid).delete()
            JournalHeader.objects.filter(tenant_id=tid).delete()
            ProductPriceTier.objects.filter(product__tenant_id=tid).delete()
            Product.objects.filter(tenant_id=tid).delete()
            ProductCategory.objects.filter(tenant_id=tid).delete()
            # حذف الشركاء عبر SQL خام: ORM يتتالى إلى partner_customer_notes
            # (migration 0007 غير مطبّق على هذه القاعدة فالجدول غير موجود).
            # القاعدة تعمل بـ foreign_key_checks=0 فالحذف الخام آمن ومقصور على الشركة.
            from accounting.models import FiscalPeriod
            FiscalPeriod.objects.filter(tenant_id=tid).delete()
            with connection.cursor() as cur:
                cur.execute("DELETE FROM partner_bank_accounts WHERE TenantID=%s", [tid])
                cur.execute("DELETE FROM partners WHERE TenantID=%s", [tid])
                cur.execute("DELETE FROM partner_groups WHERE TenantID=%s", [tid])
                # حسابات الشركة (شجرة + حسابات الشركاء الفرعية) — SQL خام مع fk_checks=0
                cur.execute("DELETE FROM chartofaccounts WHERE TenantID=%s", [tid])
        self.stdout.write(self.style.WARNING('  تم مسح بيانات شركة الجرابعه المعاملاتية.'))

    # ────────────────────────────────────────────────────────────────
    def _stage_infra(self):
        from tenants.models import Currency
        from accounting.models import Account, FiscalPeriod
        # عملات
        self.ils, _ = Currency.objects.get_or_create(
            Code='ILS', defaults={'Name': 'شيكل', 'Symbol': '₪', 'IsBaseCurrency': True})
        Currency.objects.get_or_create(Code='USD', defaults={'Name': 'دولار', 'Symbol': '$'})

        # شجرة الحسابات
        code_map = {a.code: a for a in Account.objects.filter(tenant_id=self.tid)}
        for code, name, atype, parent_code in COA:
            parent = code_map.get(parent_code) if parent_code else None
            acc, created = Account.objects.get_or_create(
                tenant=self.tenant, code=code,
                defaults={'name': name, 'account_type': atype, 'parent': parent, 'is_active': True})
            code_map[code] = acc

        # فترات مالية 2022..2027 (تغطي بيانات الملف) — مفتوحة
        for year in range(2022, 2028):
            FiscalPeriod.objects.get_or_create(
                tenant=self.tenant, name=str(year),
                defaults={'start_date': datetime.date(year, 1, 1),
                          'end_date': datetime.date(year, 12, 31),
                          'is_closed': False, 'status': 'Open'})
        self.summary['حسابات'] = Account.objects.filter(tenant_id=self.tid).count()
        self.stdout.write('  [infra] عملات + شجرة حسابات + فترات مالية جاهزة.')

        # مستودع افتراضي
        from inventory.models import Warehouse
        self.warehouse, _ = Warehouse.objects.get_or_create(
            tenant=self.tenant, code='MAIN',
            defaults={'name': 'المستودع الرئيسي', 'is_default': True, 'is_active': True})

        # مجموعات الشركاء
        from partners.models import PartnerGroup
        self.cust_group, _ = PartnerGroup.objects.get_or_create(
            tenant=self.tenant, name='عملاء', group_type='Customer',
            defaults={'account_receivable': code_map['1103']})
        if not self.cust_group.account_receivable_id:
            self.cust_group.account_receivable = code_map['1103']
            self.cust_group.save()
        self.supp_group, _ = PartnerGroup.objects.get_or_create(
            tenant=self.tenant, name='موردون', group_type='Supplier',
            defaults={'account_payable': code_map['2101']})
        if not self.supp_group.account_payable_id:
            self.supp_group.account_payable = code_map['2101']
            self.supp_group.save()

        # إعدادات المبيعات
        from sales.models import SalesSettings
        ss, _ = SalesSettings.objects.get_or_create(tenant=self.tenant)
        ss.default_currency = self.ils
        ss.default_revenue_account_product = code_map['4101']
        ss.default_revenue_account_service = code_map['4102']
        ss.default_cash_account = code_map['1101']
        ss.default_inventory_account = code_map['1104']
        ss.default_cogs_account = code_map['5101']
        ss.default_ar_account = code_map['1103']
        ss.vat_input_account = code_map['1105']
        ss.allow_negative_stock_default = True
        ss.block_loss_invoices = False
        ss.save()

        # إعدادات الشراء
        from logistics.services import get_or_create_purchase_settings
        get_or_create_purchase_settings(self.tenant)

    def _load_infra_refs(self):
        from accounting.models import Account
        from inventory.models import Warehouse
        from partners.models import PartnerGroup
        from tenants.models import Currency
        self.ils = Currency.objects.get(Code='ILS')
        self.acc = {a.code: a for a in Account.objects.filter(tenant_id=self.tid)}
        self.warehouse = Warehouse.objects.filter(tenant_id=self.tid, is_default=True).first() \
            or Warehouse.objects.filter(tenant_id=self.tid).first()
        self.cust_group = PartnerGroup.objects.filter(tenant_id=self.tid, group_type='Customer').first()
        self.supp_group = PartnerGroup.objects.filter(tenant_id=self.tid, group_type='Supplier').first()

    # ────────────────────────────────────────────────────────────────
    def _stage_partners(self):
        from partners.models import Partner
        n_c = n_s = 0
        # العملاء
        for r in read_csv(self.csv_dir / 'Clients.csv'):
            ext = clean(r.get('ClientNumber'))
            name = clean(r.get('BusinessName')) or (
                ' '.join(x for x in [clean(r.get('FirstName')), clean(r.get('LastName'))] if x)) or f'عميل {ext}'
            cl = dec(r.get('CreditLimitAmount'))
            p, created = Partner.objects.get_or_create(
                tenant=self.tenant, partner_type='Customer', name=name,
                defaults={
                    'group': self.cust_group,
                    'phone': clean(r.get('Phone1')) or clean(r.get('Phone2')),
                    'email': clean(r.get('Email')),
                    'city': clean(r.get('City')),
                    'country': clean(r.get('CountryCode')),
                    'tax_number': clean(r.get('NationalID')) or clean(r.get('BusinessNumber1')),
                    'credit_limit': cl if cl > 0 else None,
                })
            if created:
                n_c += 1
        # الموردون
        for r in read_csv(self.csv_dir / 'Suppliers.csv'):
            name = clean(r.get('BusinessName')) or (
                ' '.join(x for x in [clean(r.get('FirstName')), clean(r.get('LastName'))] if x)) \
                or f"مورد {clean(r.get('SupplierNumber'))}"
            p, created = Partner.objects.get_or_create(
                tenant=self.tenant, partner_type='Supplier', name=name,
                defaults={
                    'group': self.supp_group,
                    'phone': clean(r.get('Phone1')) or clean(r.get('Phone2')),
                    'email': clean(r.get('Email')),
                    'country': clean(r.get('CountryCode')),
                    'tax_number': clean(r.get('bn1')),
                })
            if created:
                n_s += 1
        self.summary['عملاء (جديد)'] = n_c
        self.summary['موردون (جديد)'] = n_s
        self.stdout.write(f'  [partners] عملاء+{n_c} موردون+{n_s}')

    def _load_partner_maps(self):
        """يبني خرائط رقم-خارجي→Partner لربط الفواتير/أوامر الشراء."""
        from partners.models import Partner
        self.cust_by_num = {}
        self.cust_by_name = {}
        clients_rows = list(read_csv(self.csv_dir / 'Clients.csv'))
        cust_by_name_db = {p.name: p for p in Partner.objects.filter(tenant_id=self.tid, partner_type='Customer')}
        for r in clients_rows:
            ext = clean(r.get('ClientNumber'))
            name = clean(r.get('BusinessName')) or (
                ' '.join(x for x in [clean(r.get('FirstName')), clean(r.get('LastName'))] if x)) or f'عميل {ext}'
            p = cust_by_name_db.get(name)
            if p and ext and ext.isdigit():
                self.cust_by_num[int(ext)] = p
            if p:
                self.cust_by_name[norm_name(name)] = p
        self.supp_by_num = {}
        self.supp_by_name = {}
        supp_by_name_db = {p.name: p for p in Partner.objects.filter(tenant_id=self.tid, partner_type='Supplier')}
        for r in read_csv(self.csv_dir / 'Suppliers.csv'):
            ext = clean(r.get('SupplierNumber'))
            name = clean(r.get('BusinessName')) or (
                ' '.join(x for x in [clean(r.get('FirstName')), clean(r.get('LastName'))] if x)) \
                or f"مورد {ext}"
            p = supp_by_name_db.get(name)
            if p and ext and ext.isdigit():
                self.supp_by_num[int(ext)] = p
            if p:
                self.supp_by_name[norm_name(name)] = p
        # عملاء/موردون افتراضيون للبنود غير المرتبطة
        self.default_customer = self.cust_by_num.get(1) or next(iter(self.cust_by_name.values()), None)
        self.default_supplier = next(iter(self.supp_by_name.values()), None)

    # ────────────────────────────────────────────────────────────────
    def _get_category(self, name):
        """فئة منتج بالاسم مع ربط حسابات الإيراد/التكلفة/المخزون."""
        from inventory.models import ProductCategory
        key = clean(name) or 'منتجات عامة'
        cat = self._cat_cache.get(key)
        if cat:
            return cat
        cat, _ = ProductCategory.objects.get_or_create(
            tenant=self.tenant, name=key,
            defaults={'revenue_account': self.acc['4101'],
                      'cogs_account': self.acc['5101'],
                      'inventory_account': self.acc['1104']})
        # تأكد من الربط (للفئات الموجودة مسبقاً بلا حسابات)
        changed = False
        if not cat.revenue_account_id:
            cat.revenue_account = self.acc['4101']; changed = True
        if not cat.cogs_account_id:
            cat.cogs_account = self.acc['5101']; changed = True
        if not cat.inventory_account_id:
            cat.inventory_account = self.acc['1104']; changed = True
        if changed:
            cat.save()
        self._cat_cache[key] = cat
        return cat

    def _stage_products(self):
        from inventory.models import Product, ProductPriceTier
        self._cat_cache = {}
        existing_skus = set(Product.objects.filter(tenant_id=self.tid).values_list('sku', flat=True))
        existing_names = {norm_name(x) for x in
                          Product.objects.filter(tenant_id=self.tid).values_list('name_ar', flat=True) if x}
        n = 0
        for r in read_csv(self.csv_dir / 'Products.csv'):
            name = norm_name(r.get('Name')) or f"منتج {clean(r.get('id'))}"
            # idempotency: إن كان منتج بنفس الاسم موجوداً مسبقاً (إعادة تشغيل) تخطّاه.
            if name in existing_names:
                continue
            sku = clean(r.get('ProductCode')) or f"P{clean(r.get('id'))}"
            if sku in existing_skus:
                sku = f"{sku}-{clean(r.get('id'))}"
            if sku in existing_skus:
                continue
            existing_skus.add(sku)
            existing_names.add(name)
            cat = self._get_category(r.get('Category'))
            tracking = clean(r.get('TrackingType')) or ''
            # #20: النقطة الموحّدة — حتى أمر الاستيراد التاريخي، فلا يبقى في
            # المستودع مسارٌ ينشئ براندًا بلا أبٍ فوقه.
            from inventory.services import create_product_with_family
            _fam, prod = create_product_with_family(
                tenant=self.tenant, sku=sku,
                barcode=clean(r.get('Barcode')),
                name_ar=name,
                brand=clean(r.get('Brand')) or '',
                category=cat,
                is_serialized=(tracking == 'serial'),
                allow_negative_stock=True,
                min_stock_level=int(dec(r.get('LowStockThershol'))) or None,
                quantity_on_hand=Decimal('0'),
                avg_cost=dec(r.get('AverageCost')) or dec(r.get('BuyPrice')),
            )
            # شرائح الأسعار: بيع#1 = UnitPrice، شراء#1 = BuyPrice
            up = dec(r.get('UnitPrice'))
            if up > 0:
                ProductPriceTier.objects.get_or_create(
                    product=prod, tier_type='sale', tier_number=1,
                    defaults={'price': up, 'currency': self.ils})
            bp = dec(r.get('BuyPrice'))
            if bp > 0:
                ProductPriceTier.objects.get_or_create(
                    product=prod, tier_type='purchase', tier_number=1,
                    defaults={'price': bp, 'currency': self.ils})
            n += 1
        self.summary['منتجات (من الملف)'] = n
        self.stdout.write(f'  [products] منتجات+{n}')

    def _load_product_map(self):
        from inventory.models import Product
        if not hasattr(self, '_cat_cache'):
            self._cat_cache = {}
        self.prod_by_name = {}
        self._auto_seq = 0
        for p in Product.objects.filter(tenant_id=self.tid):
            if p.name_ar:
                self.prod_by_name.setdefault(norm_name(p.name_ar), p)
            n = p.sku
            if n and n.startswith('AX-'):
                try:
                    self._auto_seq = max(self._auto_seq, int(n[3:]))
                except ValueError:
                    pass

    def _match_or_create_product(self, item_name):
        """يطابق اسم البند بمنتج موجود، وإلا يُنشئ منتجاً تلقائياً (AX-*)."""
        from inventory.models import Product
        key = norm_name(item_name)
        if not key:
            key = 'بند بلا اسم'
        p = self.prod_by_name.get(key)
        if p:
            return p, False
        self._auto_seq += 1
        cat = self._get_category('منتجات عامة')
        from inventory.services import create_product_with_family

        _fam, p = create_product_with_family(
            tenant=self.tenant, sku=f'AX-{self._auto_seq:05d}',
            name_ar=key[:200], category=cat,
            allow_negative_stock=True, quantity_on_hand=Decimal('0'), avg_cost=Decimal('0'))
        self.prod_by_name[key] = p
        return p, True

    # ────────────────────────────────────────────────────────────────
    def _group_items(self, filename):
        """يجمع بنود الفواتير/الشراء حسب العمود «no»."""
        groups = {}
        for r in read_csv(self.csv_dir / filename):
            key = clean(r.get('no'))
            if key is None:
                continue
            groups.setdefault(key, []).append(r)
        return groups

    def _stage_sales(self):
        from sales.models import SalesInvoice, SalesInvoiceLine
        from sales.services import post_sales_invoice
        items = self._group_items('Invoice_items.csv')
        rows = list(read_csv(self.csv_dir / 'Invoices.csv'))
        if self.limit:
            rows = rows[:self.limit]
        posted = skipped = failed = auto = 0
        errors = []
        for r in rows:
            inv_no = clean(r.get('InvoiceNo'))
            if not inv_no:
                continue
            if SalesInvoice.objects.filter(tenant_id=self.tid, invoice_number=inv_no).exists():
                skipped += 1
                continue
            line_rows = items.get(inv_no, [])
            if not line_rows:
                skipped += 1
                continue
            cno = clean(r.get('ClientNo'))
            customer = None
            if cno and cno.isdigit():
                customer = self.cust_by_num.get(int(cno))
            if not customer:
                customer = self.cust_by_name.get(norm_name(r.get('ClientBusinessName')))
            if not customer:
                customer = self.default_customer
            if not customer:
                failed += 1
                errors.append(f'{inv_no}: لا عميل')
                continue
            idate = pdate(r.get('Date')) or pdate(r.get('IssueDate')) or datetime.date(2023, 1, 1)
            paid = (clean(r.get('PaymentStatus')) or '').lower() == 'paid'
            try:
                with transaction.atomic():
                    inv = SalesInvoice.objects.create(
                        tenant=self.tenant, invoice_number=inv_no, customer=customer,
                        invoice_date=idate, currency=self.ils, exchange_rate=Decimal('1'),
                        invoice_type=SalesInvoice.INVOICE_CASH if paid else SalesInvoice.INVOICE_CREDIT,
                        invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
                        discount_percent=dec(r.get('DiscountPercent')),
                        notes=clean(r.get('Notes')) or '',
                        status=SalesInvoice.STATUS_DRAFT,
                    )
                    for lr in line_rows:
                        prod, is_auto = self._match_or_create_product(lr.get('item'))
                        if is_auto:
                            auto += 1
                        SalesInvoiceLine.objects.create(
                            tenant=self.tenant, invoice=inv, product=prod,
                            quantity=dec(lr.get('quantity'), Decimal('1')) or Decimal('1'),
                            unit_price=dec(lr.get('unit_price')),
                        )
                    post_sales_invoice(inv, user=None)
                posted += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                errors.append(f'{inv_no}: {e}')
            if (posted + failed) % 100 == 0 and (posted + failed) > 0:
                self.stdout.write(f'    ... مبيعات {posted+failed}/{len(rows)}')
        self.summary['فواتير مبيعات مُرحّلة'] = posted
        self.summary['فواتير مبيعات متخطّاة'] = skipped
        self.summary['فواتير مبيعات فاشلة'] = failed
        self.summary['منتجات مُنشأة تلقائياً (مبيعات)'] = auto
        if errors:
            self.summary['أخطاء مبيعات (عيّنة)'] = ' | '.join(errors[:8])
        self.stdout.write(f'  [sales] مُرحّل {posted} · متخطّى {skipped} · فاشل {failed}')

    def _resolve_supplier(self, r):
        """يحلّ مورد أمر الشراء بالاسم أولاً — عمود SupplierNo في الملف معطوب
        (يشير لمورد خاطئ في ~95٪ من الحالات)، بينما SupplierBusinessName موثوق.
        الأولوية: الاسم (كتالوج) ← إنشاء تلقائي للاسم غير الموجود ← الرقم (فقط إن
        غاب الاسم) ← المورد الافتراضي.
        """
        from partners.models import Partner
        name = norm_name(r.get('SupplierBusinessName'))
        if name:
            p = self.supp_by_name.get(name)
            if p:
                return p
            # اسم مورد غير موجود بالكتالوج ⇒ أنشئه (الاسم موثوق)
            p = Partner.objects.create(
                tenant=self.tenant, name=name[:150],
                partner_type='Supplier', group=self.supp_group)
            self.supp_by_name[name] = p
            return p
        # لا اسم ⇒ آخر ملاذ: الرقم (رغم عدم موثوقيته) ثم الافتراضي
        sno = clean(r.get('SupplierNo'))
        if sno and sno.isdigit():
            p = self.supp_by_num.get(int(sno))
            if p:
                return p
        return self.default_supplier

    def _stage_purchases(self):
        from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
        from logistics.services import receive_purchase_invoice
        from sales.models import SupplierPayment
        from sales.services import post_supplier_payment
        items = self._group_items('Purchase_order_items.csv')
        rows = list(read_csv(self.csv_dir / 'Purchase_orders.csv'))
        if self.limit:
            rows = rows[:self.limit]
        posted = skipped = failed = auto = settled = 0
        errors = []
        for r in rows:
            po_no = clean(r.get('PurchaseOrderNo'))
            if not po_no:
                continue
            number = f'PO-{po_no}'
            if PurchaseInvoice.objects.filter(tenant_id=self.tid, invoice_number=number).exists():
                skipped += 1
                continue
            line_rows = items.get(po_no, [])
            if not line_rows:
                skipped += 1
                continue
            supplier = self._resolve_supplier(r)
            if not supplier:
                failed += 1
                errors.append(f'{po_no}: لا مورد')
                continue
            idate = pdate(r.get('Date')) or datetime.date(2023, 1, 1)
            paid = (clean(r.get('PaymentStatus')) or '').lower() == 'paid'
            try:
                with transaction.atomic():
                    inv = PurchaseInvoice.objects.create(
                        tenant=self.tenant, invoice_number=number,
                        invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
                        partner=supplier, invoice_date=idate,
                        currency=self.ils, exchange_rate=Decimal('1'),
                        status='draft', notes=clean(r.get('Notes')) or '',
                    )
                    recv_lines = []
                    gross = Decimal('0')
                    for lr in line_rows:
                        prod, is_auto = self._match_or_create_product(lr.get('item'))
                        if is_auto:
                            auto += 1
                        qty = dec(lr.get('quantity'), Decimal('1')) or Decimal('1')
                        up = dec(lr.get('unit_price'))
                        line_total = (qty * up).quantize(DEC)
                        gross += line_total
                        it = PurchaseInvoiceItem.objects.create(
                            invoice=inv, product=prod, name=norm_name(lr.get('item'))[:255] or prod.name_ar,
                            quantity=qty, unit_price=up, total_price=line_total,
                            is_taxable=False,
                        )
                        recv_lines.append({'item_id': it.id, 'quantity': qty,
                                           'warehouse_id': self.warehouse.id})
                    receive_purchase_invoice(inv, lines=recv_lines, branch=None,
                                             user=None, movement_date=idate)
                    # تسوية المورد لأوامر الشراء المدفوعة (Dr ذمم مورد / Cr صندوق)
                    if paid and gross > 0:
                        sp = SupplierPayment.objects.create(
                            tenant=self.tenant, partner=supplier, payment_date=idate,
                            amount=gross, currency=self.ils, exchange_rate=Decimal('1'),
                            cash_or_bank_account=self.acc['1101'],
                            notes=f'دفع تلقائي — فاتورة شراء {number}')
                        post_supplier_payment(sp, user=None)
                        inv.status = 'fully_paid'
                        inv.save(update_fields=['status'])
                        settled += 1
                posted += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                errors.append(f'{po_no}: {e}')
            if (posted + failed) % 100 == 0 and (posted + failed) > 0:
                self.stdout.write(f'    ... مشتريات {posted+failed}/{len(rows)}')
        self.summary['فواتير شراء مُستلَمة'] = posted
        self.summary['فواتير شراء مُسوّاة (مدفوعة)'] = settled
        self.summary['فواتير شراء متخطّاة'] = skipped
        self.summary['فواتير شراء فاشلة'] = failed
        self.summary['منتجات مُنشأة تلقائياً (شراء)'] = auto
        if errors:
            self.summary['أخطاء شراء (عيّنة)'] = ' | '.join(errors[:8])
        self.stdout.write(f'  [purchases] مُستلَم {posted} · متخطّى {skipped} · فاشل {failed}')
