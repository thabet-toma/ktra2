"""اختبارات فوترة اشتراكات خدمة عمليات المنصة الشهرية (المرحلة 8A - Issue #207).

تغطي الاختبارات السلوكية الثمانية الإلزامية:
1. معادلة الفوترة (الرسم الثابت + الزيادة الدقيقة) وفصل سطور الفاتورة.
2. استهلاك أقل من أو مساوٍ للباقة يفوتر الرسم الثابت فقط ويحذف سطر الزيادة الصفرية.
3. ترحيل الفاتورة الناتجة محاسبياً عبر post_sales_invoice وحظر القيود المباشرة في platform_ops.
4. عدم التكرار (Idempotency): تشغيل الخدمة/الأمر مرتين لنفس الدورة يُنتج فاتورة واحدة ولا يكرر تدوير العداد.
5. الذرية (Atomicity): الفشل يُرجع المعاملة بالكامل ولا يترك نصف فاتورة ويحفظ العداد والدورة.
6. رفض الإعدادات الناقصة أو المتعارضة بين الشركات (cross-tenant) قبل أي تعديل.
7. فوترة الاشتراكات النشطة والمستحقة فقط للدورة المطلوبة، وبقاء الشركات الأخرى دون لمس.
8. سلامة رسم الهجرات وأطوال الحقول والقيود الفريدة.
"""
import ast
import datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from tenants.models import Currency, Tenant

from platform_ops.models import ServiceSubscription, SubscriptionBillingRecord
from platform_ops.services import (
    BillingConfigurationError,
    BillingError,
    BillingPeriodError,
    bill_subscription_for_period,
    bill_subscriptions_for_period,
    calculate_subscription_billing,
    resolve_billing_period_bounds,
)

User = get_user_model()
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class SubscriptionBillingServiceTests(TestCase):
    """مجموعة الاختبارات السلوكية لفوترة اشتراكات المنصة."""

    def _create_tenant(self, name: str) -> Tenant:
        return Tenant.objects.create(
            CompanyName=name,
            SubscriptionPlan="Pro",
            Status="Active",
        )

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="billing_admin", password="password123")
        self.currency, _ = Currency.objects.get_or_create(
            Code="ILS",
            defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True},
        )

        Account = apps.get_model("accounting", "Account")
        FiscalPeriod = apps.get_model("accounting", "FiscalPeriod")

        # 1. شركة المنصة المفوترة (Platform Tenant)
        self.platform_tenant = self._create_tenant("شركة المنصة للخدمات الرقمية")
        FiscalPeriod.objects.create(
            tenant=self.platform_tenant,
            name="FY 2026-08",
            start_date=datetime.date(2026, 8, 1),
            end_date=datetime.date(2026, 8, 31),
            is_closed=False,
        )

        self.ar_account = Account.objects.create(
            tenant=self.platform_tenant,
            code="1101-AR",
            name="ذمم عملاء المنصة",
            account_type="Asset",
            is_active=True,
        )
        self.rev_account = Account.objects.create(
            tenant=self.platform_tenant,
            code="4101-REV",
            name="إيراد اشتراكات المنصة",
            account_type="Revenue",
            is_active=True,
        )

        self.sales_settings = get_or_create_sales_settings(self.platform_tenant)
        self.sales_settings.default_ar_account = self.ar_account
        self.sales_settings.default_revenue_account_service = self.rev_account
        self.sales_settings.default_currency = self.currency
        self.sales_settings.save()

        self.fixed_fee_product = Product.objects.create(
            tenant=self.platform_tenant,
            sku="SUB-FIXED-FEE",
            name_ar="الرسم الشهري الثابت لاشتراك المنصة",
            is_service=True,
        )
        self.overage_product = Product.objects.create(
            tenant=self.platform_tenant,
            sku="SUB-OVERAGE-FEE",
            name_ar="رسوم عمليات زائدة لاشتراك المنصة",
            is_service=True,
        )

        # 2. شركة الزبون المشترك (Client Tenant A)
        self.client_tenant = self._create_tenant("شركة التقنية المتقدمة")
        self.billing_customer = Partner.objects.create(
            tenant=self.platform_tenant,
            name="شركة التقنية المتقدمة (زبون)",
            partner_type="Customer",
            linked_account=self.ar_account,
        )

        self.sub_a = ServiceSubscription.objects.create(
            tenant=self.client_tenant,
            status=ServiceSubscription.Status.ACTIVE,
            plan="growth",
            monthly_fee=Decimal("200.00"),
            included_quota=100,
            overage_unit_price=Decimal("3.00"),
            consumed_quota=130,  # 30 عمليات زائدة
            billing_customer=self.billing_customer,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
        )

        # 3. شركة أخرى غير مرتبطة (Unrelated Tenant)
        self.unrelated_tenant = self._create_tenant("شركة أخرى معزولة")
        self.unrelated_product = Product.objects.create(
            tenant=self.unrelated_tenant,
            sku="OTHER-PROD",
            name_ar="صنف لشركة أخرى",
            is_service=True,
        )

    def test_1_fee_plus_exact_overage_arithmetic_and_separate_lines(self):
        """1. حساب المعادلة بدقة: الرسم الثابت + العمليات الزائدة، وفصل السطور."""
        record, created = bill_subscription_for_period(
            subscription_id=self.sub_a.id,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
            fixed_fee_product_id=self.fixed_fee_product.id,
            overage_product_id=self.overage_product.id,
        )
        self.assertTrue(created)
        self.assertEqual(record.monthly_fee, Decimal("200.00"))
        self.assertEqual(record.included_quota, 100)
        self.assertEqual(record.consumed_quota, 130)
        self.assertEqual(record.overage_units, 30)
        self.assertEqual(record.overage_unit_price, Decimal("3.00"))
        self.assertEqual(record.overage_fee, Decimal("90.00"))
        self.assertEqual(record.total_amount, Decimal("290.00"))

        invoice = record.invoice
        self.assertEqual(invoice.tenant_id, self.platform_tenant.TenantID)
        self.assertEqual(invoice.customer_id, self.billing_customer.id)
        self.assertEqual(invoice.grand_total, Decimal("290.00"))

        # التحقق من وجود سطرين منفصلين تماماً
        lines = list(invoice.lines.order_by("id"))
        self.assertEqual(len(lines), 2)

        # سطر الرسم الثابت
        self.assertEqual(lines[0].product_id, self.fixed_fee_product.id)
        self.assertEqual(lines[0].quantity, Decimal("1.00"))
        self.assertEqual(lines[0].unit_price, Decimal("200.00"))

        # سطر الزيادة
        self.assertEqual(lines[1].product_id, self.overage_product.id)
        self.assertEqual(lines[1].quantity, Decimal("30"))
        self.assertEqual(lines[1].unit_price, Decimal("3.00"))

        # التحقق من تدوير الدورة وتصفير العداد على الاشتراك
        self.sub_a.refresh_from_db()
        self.assertEqual(self.sub_a.consumed_quota, 0)
        self.assertEqual(self.sub_a.period_start, datetime.date(2026, 9, 1))
        self.assertEqual(self.sub_a.period_end, datetime.date(2026, 9, 30))

    def test_2_below_quota_bills_only_fixed_fee_and_omits_zero_overage_line(self):
        """2. استهلاك أقل من الباقة يفوتر الرسم الثابت فقط ويحذف سطر الزيادة الصفرية."""
        self.sub_a.consumed_quota = 75  # أقل من 100
        self.sub_a.save()

        record, created = bill_subscription_for_period(
            subscription_id=self.sub_a.id,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
            fixed_fee_product_id=self.fixed_fee_product.id,
            overage_product_id=self.overage_product.id,
        )
        self.assertTrue(created)
        self.assertEqual(record.overage_units, 0)
        self.assertEqual(record.overage_fee, Decimal("0.00"))
        self.assertEqual(record.total_amount, Decimal("200.00"))

        invoice = record.invoice
        self.assertEqual(invoice.grand_total, Decimal("200.00"))

        # سطر واحد فقط — تم حذف سطر الزيادة الصفرية تماماً
        lines = list(invoice.lines.all())
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].product_id, self.fixed_fee_product.id)
        self.assertEqual(lines[0].unit_price, Decimal("200.00"))

    def test_3_sales_invoice_is_posted_and_routes_through_post_journal(self):
        """3. الفاتورة الناتجة مرحلة وبها أثر محاسبي طبيعي، مع حظر كتابة القيود مباشرة في platform_ops."""
        record, _ = bill_subscription_for_period(
            subscription_id=self.sub_a.id,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
            fixed_fee_product_id=self.fixed_fee_product.id,
            overage_product_id=self.overage_product.id,
        )
        invoice = record.invoice
        self.assertEqual(invoice.status, SalesInvoice.STATUS_POSTED)
        self.assertIsNotNone(invoice.journal)

        # التحقق من القيد المحاسبي المتوازن في دفتر الأستاذ
        JournalLine = apps.get_model("accounting", "JournalLine")
        lines = list(JournalLine.objects.filter(journal=invoice.journal))
        self.assertTrue(len(lines) >= 2)
        debit_sum = sum(l.debit for l in lines)
        credit_sum = sum(l.credit for l in lines)
        self.assertEqual(debit_sum, Decimal("290.00"))
        self.assertEqual(credit_sum, Decimal("290.00"))

        # حارسُ الكود: لا كتابةَ قيدٍ مباشرةً من هذه الوحدة بأيّ طريق.
        #
        # فحصُ `ImportFrom` وحدَه **لا يستطيع السقوط** للسبب الذي يحمله اسمُه:
        # `apps.get_model("accounting", "JournalHeader")` و`from accounting import models`
        # كلاهما يمرّ من تحته. فيُفحَص الثلاثةُ معاً.
        banned = {"JournalHeader", "JournalLine", "post_journal"}
        offenders = []
        platform_ops_dir = REPO_ROOT / "platform_ops"
        for py_path in platform_ops_dir.rglob("*.py"):
            if "tests" in py_path.parts:
                continue
            source = py_path.read_text(encoding="utf-8")
            rel = py_path.relative_to(REPO_ROOT).as_posix()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                # (أ) `from accounting… import JournalLine`
                if isinstance(node, ast.ImportFrom) and node.module and "accounting" in node.module:
                    for n in node.names:
                        if n.name in banned:
                            offenders.append(f"{rel} → import {n.name} من {node.module}")
                # (ب) `import accounting.models` — يفتح `accounting.models.JournalLine`
                if isinstance(node, ast.Import):
                    for n in node.names:
                        if n.name.startswith("accounting"):
                            offenders.append(f"{rel} → import {n.name}")
                # (ج) `apps.get_model("accounting", "JournalHeader")` — الطريق الملتفّ
                if isinstance(node, ast.Call):
                    func = node.func
                    name = getattr(func, "attr", None) or getattr(func, "id", None)
                    if name == "get_model":
                        args = [a.value for a in node.args if isinstance(a, ast.Constant)]
                        if any(str(a) in banned for a in args):
                            offenders.append(f"{rel} → get_model{tuple(args)}")

        self.assertEqual(
            offenders, [],
            "قيد محاسبي يُكتب من `platform_ops` مباشرة بدل `post_journal`: "
            + " | ".join(offenders),
        )

    def test_13_zero_amount_subscription_creates_record_without_invoice_and_advances_period(self):
        """أ٤. رسم صفري وتحت الحد: صف سجل بلا فاتورة، الدورة تقدمت، العداد صفر، لا SalesInvoice، إعادة التشغيل لا تنشئ صفاً ثانياً، الشهر التالي يعالج طبيعياً."""
        self.sub_a.monthly_fee = Decimal("0.00")
        self.sub_a.consumed_quota = 10  # دون المشمول (100)
        self.sub_a.save(update_fields=["monthly_fee", "consumed_quota"])

        # 1. التشغيل الأول للدورة الحالية (2026-08)
        record, created = bill_subscription_for_period(
            subscription_id=self.sub_a.pk,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
            fixed_fee_product_id=self.fixed_fee_product.pk,
            overage_product_id=self.overage_product.pk,
        )
        self.assertTrue(created)
        self.assertIsNone(record.invoice)
        self.assertEqual(record.total_amount, Decimal("0.00"))
        self.assertFalse(SalesInvoice.objects.filter(tenant=self.platform_tenant).exists())

        # الدورة تقدمت والعداد صُفّر
        self.sub_a.refresh_from_db()
        self.assertEqual(self.sub_a.consumed_quota, 0)
        self.assertEqual(self.sub_a.period_start, datetime.date(2026, 9, 1))
        self.assertEqual(self.sub_a.period_end, datetime.date(2026, 9, 30))

        # 2. إعادة التشغيل لنفس الدورة (2026-08) لا تنشئ صفاً ثانياً
        record2, created2 = bill_subscription_for_period(
            subscription_id=self.sub_a.pk,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
            fixed_fee_product_id=self.fixed_fee_product.pk,
            overage_product_id=self.overage_product.pk,
        )
        self.assertFalse(created2)
        self.assertEqual(record.pk, record2.pk)
        self.assertEqual(SubscriptionBillingRecord.objects.filter(subscription=self.sub_a).count(), 1)

        # 3. الشهر التالي (2026-09) يُعالج طبيعياً
        FiscalPeriod = apps.get_model("accounting", "FiscalPeriod")
        FiscalPeriod.objects.create(
            tenant=self.platform_tenant,
            name="FY 2026-09",
            start_date=datetime.date(2026, 9, 1),
            end_date=datetime.date(2026, 9, 30),
            is_closed=False,
        )
        self.sub_a.consumed_quota = 120  # تجاوز بـ 20 عملية
        self.sub_a.save(update_fields=["consumed_quota"])
        record_sept, created_sept = bill_subscription_for_period(
            subscription_id=self.sub_a.pk,
            period_start=datetime.date(2026, 9, 1),
            period_end=datetime.date(2026, 9, 30),
            fixed_fee_product_id=self.fixed_fee_product.pk,
            overage_product_id=self.overage_product.pk,
        )
        self.assertTrue(created_sept)
        self.assertIsNotNone(record_sept.invoice)
        # 20 عملية × 3.00 = 60.00
        self.assertEqual(record_sept.total_amount, Decimal("60.00"))
        self.assertEqual(SubscriptionBillingRecord.objects.filter(subscription=self.sub_a).count(), 2)

    def test_command_bills_final_period_before_applying_scheduled_cancellation(self):
        FiscalPeriod = apps.get_model("accounting", "FiscalPeriod")
        FiscalPeriod.objects.create(
            tenant=self.platform_tenant,
            name="FY 2026-01",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 1, 31),
            is_closed=False,
        )
        self.sub_a.period_start = datetime.date(2026, 1, 1)
        self.sub_a.period_end = datetime.date(2026, 1, 31)
        self.sub_a.consumed_quota = 0
        self.sub_a.scheduled_cancellation_date = datetime.date(2026, 1, 31)
        self.sub_a.cancellation_reason = "نهاية الخدمة"
        self.sub_a.save(
            update_fields=[
                "period_start",
                "period_end",
                "consumed_quota",
                "scheduled_cancellation_date",
                "cancellation_reason",
            ]
        )
        command_now = timezone.make_aware(datetime.datetime(2026, 2, 1, 10, 0, 0))

        with patch("platform_ops.services.timezone.now", return_value=command_now):
            call_command(
                "bill_service_subscriptions",
                period="2026-01",
                fixed_fee_product_id=self.fixed_fee_product.pk,
                dry_run=True,
            )
        self.assertFalse(
            SubscriptionBillingRecord.objects.filter(
                subscription=self.sub_a,
                period_start=datetime.date(2026, 1, 1),
                period_end=datetime.date(2026, 1, 31),
            ).exists()
        )
        self.sub_a.refresh_from_db()
        self.assertEqual(self.sub_a.status, ServiceSubscription.Status.ACTIVE)

        with patch("platform_ops.services.timezone.now", return_value=command_now):
            call_command(
                "bill_service_subscriptions",
                period="2026-01",
                fixed_fee_product_id=self.fixed_fee_product.pk,
            )

        record = SubscriptionBillingRecord.objects.get(
            subscription=self.sub_a,
            period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 1, 31),
        )
        self.assertIsNotNone(record.invoice)
        self.sub_a.refresh_from_db()
        self.assertEqual(self.sub_a.status, ServiceSubscription.Status.CANCELLED)

    def test_billing_uses_the_products_snapshotted_on_the_subscription_when_none_are_passed(self):
        """أصناف الفوترة تأتي من لقطة الاشتراك (سياسته) لا من معامل الأمر — لا إعداد يدوي لكل تشغيل."""
        self.sub_a.fixed_fee_product = self.fixed_fee_product
        self.sub_a.overage_product = self.overage_product
        self.sub_a.save(update_fields=["fixed_fee_product", "overage_product"])
        record, created = bill_subscription_for_period(
            subscription_id=self.sub_a.id,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
        )
        self.assertTrue(created)
        self.assertEqual(record.total_amount, Decimal("290.00"))

    def test_4_idempotency_running_service_and_command_twice_creates_single_invoice(self):
        """4. تشغيل الخدمة والأمر مرتين لنفس الدورة يُنتج فاتورة وسجل تدقيق واحداً ولا يكرر التدوير."""
        # المرة الأولى
        record1, created1 = bill_subscription_for_period(
            subscription_id=self.sub_a.id,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
            fixed_fee_product_id=self.fixed_fee_product.id,
            overage_product_id=self.overage_product.id,
        )
        self.assertTrue(created1)

        # المرة الثانية لنفس الاشتراك والدورة
        record2, created2 = bill_subscription_for_period(
            subscription_id=self.sub_a.id,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
            fixed_fee_product_id=self.fixed_fee_product.id,
            overage_product_id=self.overage_product.id,
        )
        self.assertFalse(created2)
        self.assertEqual(record1.id, record2.id)

        # التحقق من وجود فاتورة واحدة وسجل تدقيق واحد في قاعدة البيانات
        self.assertEqual(
            SalesInvoice.objects.filter(customer=self.billing_customer).count(),
            1,
        )
        self.assertEqual(
            SubscriptionBillingRecord.objects.filter(subscription=self.sub_a).count(),
            1,
        )

        # لم يتم تدوير الدورة مرتين
        self.sub_a.refresh_from_db()
        self.assertEqual(self.sub_a.period_start, datetime.date(2026, 9, 1))

        # تشغيل أمر الإدارة لنفس الفترة أيضاً
        out = StringIO()
        call_command(
            "bill_service_subscriptions",
            "--period", "2026-08",
            "--fixed-fee-product-id", str(self.fixed_fee_product.id),
            "--overage-product-id", str(self.overage_product.id),
            "--subscription-id", str(self.sub_a.id),
            stdout=out,
        )
        # لا تزال فاتورة واحدة
        self.assertEqual(
            SalesInvoice.objects.filter(customer=self.billing_customer).count(),
            1,
        )

    def test_5_failure_rolls_back_invoice_and_preserves_quota_and_period(self):
        """5. الفشل أثناء الفوترة يلف المعاملة بالكامل ويحفظ العداد ودورة الاشتراك دون تغيير."""
        with patch("sales.services.post_sales_invoice", side_effect=ValueError("محاكاة فشل الترحيل")):
            with self.assertRaises(ValueError):
                bill_subscription_for_period(
                    subscription_id=self.sub_a.id,
                    period_start=datetime.date(2026, 8, 1),
                    period_end=datetime.date(2026, 8, 31),
                    fixed_fee_product_id=self.fixed_fee_product.id,
                    overage_product_id=self.overage_product.id,
                )

        # لم تُنشأ أي فاتورة ولا سجل تدقيق
        self.assertEqual(
            SalesInvoice.objects.filter(customer=self.billing_customer).count(),
            0,
        )
        self.assertEqual(
            SubscriptionBillingRecord.objects.filter(subscription=self.sub_a).count(),
            0,
        )

        # العداد والدورة لم يتغيرا
        self.sub_a.refresh_from_db()
        self.assertEqual(self.sub_a.consumed_quota, 130)
        self.assertEqual(self.sub_a.period_start, datetime.date(2026, 8, 1))
        self.assertEqual(self.sub_a.period_end, datetime.date(2026, 8, 31))

    def test_6_missing_or_cross_tenant_config_rejected_before_mutation(self):
        """6. رفض الإعدادات الناقصة أو المتعارضة بين الشركات (cross-tenant) قبل أي تعديل."""
        # حالة أ: اشتراك بلا عميل فوترة
        self.sub_a.billing_customer = None
        self.sub_a.save()
        with self.assertRaises(BillingConfigurationError):
            bill_subscription_for_period(
                subscription_id=self.sub_a.id,
                period_start=datetime.date(2026, 8, 1),
                period_end=datetime.date(2026, 8, 31),
                fixed_fee_product_id=self.fixed_fee_product.id,
                overage_product_id=self.overage_product.id,
            )

        self.sub_a.billing_customer = self.billing_customer
        self.sub_a.save()

        # حالة ب: صنف الرسم الثابت يتبع شركة أخرى (cross-tenant)
        with self.assertRaises(BillingConfigurationError):
            bill_subscription_for_period(
                subscription_id=self.sub_a.id,
                period_start=datetime.date(2026, 8, 1),
                period_end=datetime.date(2026, 8, 31),
                fixed_fee_product_id=self.unrelated_product.id,
                overage_product_id=self.overage_product.id,
            )

        # حالة ج: صنف العمليات الزائدة يتبع شركة أخرى (cross-tenant)
        with self.assertRaises(BillingConfigurationError):
            bill_subscription_for_period(
                subscription_id=self.sub_a.id,
                period_start=datetime.date(2026, 8, 1),
                period_end=datetime.date(2026, 8, 31),
                fixed_fee_product_id=self.fixed_fee_product.id,
                overage_product_id=self.unrelated_product.id,
            )

        # حالة د: الصنف ليس صنفاً خدمياً
        physical_product = Product.objects.create(
            tenant=self.platform_tenant,
            sku="PHYSICAL-1",
            name_ar="صنف مخزني بضاعة",
            is_service=False,
        )
        with self.assertRaises(BillingConfigurationError):
            bill_subscription_for_period(
                subscription_id=self.sub_a.id,
                period_start=datetime.date(2026, 8, 1),
                period_end=datetime.date(2026, 8, 31),
                fixed_fee_product_id=physical_product.id,
                overage_product_id=self.overage_product.id,
            )

        # تأكيد عدم إنشاء أي فاتورة
        self.assertEqual(
            SalesInvoice.objects.filter(customer=self.billing_customer).count(),
            0,
        )

    def test_7_only_active_subscriptions_due_for_period_billed_others_untouched(self):
        """7. فوترة الاشتراكات النشطة والمستحقة للدورة فقط، وبقاء الاشتراكات المعلقة أو لغير الدورة دون لمس."""
        # اشتراك معلق
        tenant_suspended = self._create_tenant("شركة معلقة")
        sub_suspended = ServiceSubscription.objects.create(
            tenant=tenant_suspended,
            status=ServiceSubscription.Status.SUSPENDED,
            plan="standard",
            monthly_fee=Decimal("100.00"),
            billing_customer=self.billing_customer,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
            consumed_quota=5,
        )

        # اشتراك دورته في شهر سبتمبر (غير مستحق لأغسطس)
        tenant_september = self._create_tenant("شركة سبتمبر")
        sub_september = ServiceSubscription.objects.create(
            tenant=tenant_september,
            status=ServiceSubscription.Status.ACTIVE,
            plan="standard",
            monthly_fee=Decimal("100.00"),
            billing_customer=self.billing_customer,
            period_start=datetime.date(2026, 9, 1),
            period_end=datetime.date(2026, 9, 30),
            consumed_quota=10,
        )

        result = bill_subscriptions_for_period(
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
            fixed_fee_product_id=self.fixed_fee_product.id,
            overage_product_id=self.overage_product.id,
        )

        self.assertEqual(result["billed_count"], 1)
        self.assertEqual(result["billed"][0]["subscription_id"], self.sub_a.id)

        # المعلق وسبتمبر لم يُفوّترا ولم تتغير بياناتهما
        sub_suspended.refresh_from_db()
        self.assertEqual(sub_suspended.consumed_quota, 5)
        self.assertEqual(sub_suspended.period_start, datetime.date(2026, 8, 1))

        sub_september.refresh_from_db()
        self.assertEqual(sub_september.consumed_quota, 10)
        self.assertEqual(sub_september.period_start, datetime.date(2026, 9, 1))

    def test_8_migration_graph_and_field_definitions(self):
        """8. التحقق من اتساع الحقول والقيود الفريدة على مستوى النموذج."""
        record_meta = SubscriptionBillingRecord._meta

        # سعة المبالغ المالية 12 خانة وخانتان عشريتان
        fee_field = record_meta.get_field("monthly_fee")
        self.assertEqual(fee_field.max_digits, 12)
        self.assertEqual(fee_field.decimal_places, 2)

        total_field = record_meta.get_field("total_amount")
        self.assertEqual(total_field.max_digits, 12)
        self.assertEqual(total_field.decimal_places, 2)

        # قيد الفرادة DB UniqueConstraint على (subscription, period_start, period_end)
        constraint_names = [c.name for c in record_meta.constraints]
        self.assertIn("platform_ops_sub_billing_sub_period_uniq", constraint_names)

        # حقل عميل الفوترة nullable ForeignKey
        sub_meta = ServiceSubscription._meta
        bc_field = sub_meta.get_field("billing_customer")
        self.assertTrue(bc_field.null)
        self.assertTrue(bc_field.blank)

    def test_9_unique_constraint_conflict_rolls_back_the_posted_invoice(self):
        """9. سقوطُ قيد الفرادة يُرجع الفاتورة المرحّلة ولا يعتمدها بلا سجلّ فوترة.

        القفلُ على صفّ الاشتراك يجعل هذا السقوطَ نادراً، لكنّ مسارَ التعافي كان
        يعود بـ«السجلّ القائم» **بعد أن رُحّلت فاتورةٌ في المعاملة نفسِها** — فتُعتمد
        فاتورةٌ مكرَّرةٌ على الزبون لا يذكرها أيُّ سجلّ. نحاكي هنا معاملةً متزامنةً
        كتبت السجلَّ قبلنا: يجب أن ترتدّ معاملتُنا كاملةً بالفاتورة وقيدِها.
        """
        invoices_before = SalesInvoice.objects.filter(tenant=self.platform_tenant).count()
        original_create = SubscriptionBillingRecord.objects.create
        calls = {"n": 0}

        def create_then_conflict(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                original_create(**kwargs)  # صفُّ المعاملة «المتزامنة»
                raise IntegrityError("duplicate key value violates unique constraint")
            return original_create(**kwargs)

        with patch.object(
            SubscriptionBillingRecord.objects, "create", side_effect=create_then_conflict
        ):
            with self.assertRaises(BillingError) as ctx:
                bill_subscription_for_period(
                    subscription_id=self.sub_a.pk,
                    period_start=datetime.date(2026, 8, 1),
                    period_end=datetime.date(2026, 8, 31),
                    fixed_fee_product_id=self.fixed_fee_product.pk,
                    overage_product_id=self.overage_product.pk,
                    user=self.owner,
                )

        self.assertEqual(ctx.exception.code, "billing_record_conflict")
        self.assertEqual(
            SalesInvoice.objects.filter(tenant=self.platform_tenant).count(),
            invoices_before,
            "فاتورةٌ مرحَّلةٌ بقيت في دفاتر المنصّة رغم ارتداد الفوترة.",
        )
        self.assertFalse(
            SubscriptionBillingRecord.objects.filter(subscription=self.sub_a).exists(),
            "سجلُّ الفوترة لم يرتدّ مع المعاملة.",
        )

        self.sub_a.refresh_from_db()
        self.assertEqual(self.sub_a.consumed_quota, 130)
        self.assertEqual(self.sub_a.period_start, datetime.date(2026, 8, 1))
        self.assertEqual(self.sub_a.period_end, datetime.date(2026, 8, 31))

    def test_10_dry_run_preview_matches_what_the_real_run_would_bill(self):
        """10. المعاينةُ لا تَعِد بفوترة صفٍّ يتخطّاه التشغيلُ الحقيقيّ.

        كانت المعاينةُ تُصفّي بالحالة وحدَها، فتَعرض اشتراكاً دورتُه لا تطابق
        الدورةَ المطلوبة على أنّه «مرشَّح» بينما التشغيلُ الحقيقيّ يتخطّاه.
        """
        mismatched = ServiceSubscription.objects.create(
            tenant=self.unrelated_tenant,
            status=ServiceSubscription.Status.ACTIVE,
            plan="basic",
            monthly_fee=Decimal("50.00"),
            included_quota=10,
            overage_unit_price=Decimal("1.00"),
            consumed_quota=0,
            billing_customer=self.billing_customer,
            period_start=datetime.date(2026, 9, 1),
            period_end=datetime.date(2026, 9, 30),
        )

        out = StringIO()
        call_command(
            "bill_service_subscriptions",
            "--period", "2026-08",
            "--fixed-fee-product-id", str(self.fixed_fee_product.pk),
            "--overage-product-id", str(self.overage_product.pk),
            "--dry-run",
            stdout=out,
        )
        preview = out.getvalue()

        self.assertIn(f"[تخطي] اشتراك #{mismatched.pk}", preview)
        self.assertIn("سيُفوتر فعلياً: 1", preview)
        # ولا كتابةَ في وضع المعاينة
        self.assertFalse(SubscriptionBillingRecord.objects.exists())
        self.assertFalse(SalesInvoice.objects.filter(tenant=self.platform_tenant).exists())

    def test_11_billed_records_are_readable_on_the_platform_surface(self):
        """11. ما فُوتر يُرى: نقطةُ القراءة تعرض السجلَّ وفاتورتَه وتُصفّى بالشركة."""
        from rest_framework.test import APIClient

        from platform_ops.models import PlatformEmployee

        record, created = bill_subscription_for_period(
            subscription_id=self.sub_a.pk,
            period_start=datetime.date(2026, 8, 1),
            period_end=datetime.date(2026, 8, 31),
            fixed_fee_product_id=self.fixed_fee_product.pk,
            overage_product_id=self.overage_product.pk,
            user=self.owner,
        )
        self.assertTrue(created)

        manager_user = User.objects.create_user(
            username="ops_manager_billing", password="password123", is_superuser=True, is_staff=True
        )
        PlatformEmployee.objects.create(
            user=manager_user,
            specialty="operations_manager",
            status=PlatformEmployee.Status.ACTIVE,
        )

        client = APIClient()
        client.force_authenticate(user=manager_user)
        resp = client.get("/api/platform/ops/billing-records/")
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], record.pk)
        self.assertEqual(rows[0]["invoice"], record.invoice_id)
        self.assertEqual(rows[0]["invoice_number"], record.invoice.invoice_number)
        self.assertEqual(rows[0]["total_amount"], "290.00")
        self.assertEqual(rows[0]["tenant_id"], self.client_tenant.pk)
        self.assertEqual(rows[0]["company_name"], self.client_tenant.CompanyName)

        # التصفيةُ بشركةٍ أخرى لا تُعيد سجلَّ هذه الشركة
        resp_other = client.get(f"/api/platform/ops/billing-records/?company={self.unrelated_tenant.pk}")
        self.assertEqual(resp_other.status_code, 200)
        other_rows = (
            resp_other.data["results"]
            if isinstance(resp_other.data, dict) and "results" in resp_other.data
            else resp_other.data
        )
        self.assertEqual(other_rows, [])

    def test_12_the_company_owner_can_see_its_own_quota_usage(self):
        """12. القصّة ٦٢: صاحبُ الشركة يرى استهلاكَه واقترابَه من الحدّ قبل الفاتورة.

        والأرقامُ من دالّة الفوترة نفسِها: لو تباعدت الشاشةُ عن الفاتورة لَفوجئ
        الزبونُ بما لم يرَه.
        """
        from rest_framework.test import APIClient

        from tenants.models import UserCompanyMembership

        owner = User.objects.create_user(username="quota_owner", password="password123")
        UserCompanyMembership.objects.create(
            user=owner, tenant=self.client_tenant, role="manager"
        )

        client = APIClient()
        client.force_authenticate(user=owner)
        resp = client.get("/api/my-agent/quota/")
        self.assertEqual(resp.status_code, 200, resp.data)

        data = resp.data
        self.assertTrue(data["has_subscription"])
        self.assertEqual(data["included_quota"], 100)
        self.assertEqual(data["consumed_quota"], 130)
        self.assertEqual(data["remaining_quota"], 0)
        self.assertEqual(data["overage_units"], 30)
        self.assertEqual(data["usage_percent"], 130.0)
        # الإجماليُّ المتوقّع = 200 + (30 × 3) = 290، وهو رقمُ الفاتورة نفسُه —
        # نصّاً عشريّاً مقرَّباً كبقيّة مبالغ الوحدة لا عدداً عائماً.
        self.assertEqual(data["projected_total"], "290.00")

        calc = calculate_subscription_billing(self.sub_a)
        self.assertEqual(data["projected_total"], str(calc["total_amount"]))
        self.assertEqual(data["overage_fee"], str(calc["overage_fee"]))

        # شركةٌ بلا اشتراك: حالةٌ لا خطأ.
        other_owner = User.objects.create_user(username="quota_owner_2", password="password123")
        UserCompanyMembership.objects.create(
            user=other_owner, tenant=self.unrelated_tenant, role="manager"
        )
        client.force_authenticate(user=other_owner)
        resp_none = client.get("/api/my-agent/quota/")
        self.assertEqual(resp_none.status_code, 200)
        self.assertFalse(resp_none.data["has_subscription"])

    def test_billing_customer_from_same_tenant_is_refused(self):
        """أ٥. عميل الفوترة من نفس شركة الاشتراك يُرفض بكود billing_customer_same_tenant ولا فاتورة ولا تقديم دورة."""
        partner_same_tenant = Partner.objects.create(
            tenant=self.client_tenant,
            name="عميل داخل نفس الشركة",
            partner_type="Customer",
        )
        self.sub_a.billing_customer = partner_same_tenant
        self.sub_a.save(update_fields=["billing_customer"])

        initial_quota = self.sub_a.consumed_quota
        initial_period = self.sub_a.period_start

        with self.assertRaises(BillingPeriodError) as ctx:
            bill_subscription_for_period(
                subscription_id=self.sub_a.pk,
                period_start=datetime.date(2026, 8, 1),
                period_end=datetime.date(2026, 8, 31),
                fixed_fee_product_id=self.fixed_fee_product.pk,
                overage_product_id=self.overage_product.pk,
            )
        self.assertEqual(ctx.exception.code, "billing_customer_same_tenant")

        self.assertFalse(SalesInvoice.objects.filter(tenant=self.platform_tenant).exists())
        self.assertFalse(SubscriptionBillingRecord.objects.filter(subscription=self.sub_a).exists())

        self.sub_a.refresh_from_db()
        self.assertEqual(self.sub_a.consumed_quota, initial_quota)
        self.assertEqual(self.sub_a.period_start, initial_period)

    def test_dry_run_matches_real_run_when_overage_product_missing_and_error_raises_command_error(self):
        """أ٦. اشتراك ينقصه صنف العمليات الزائدة مع تجاوز: عدد المعاينة يساوي billed_count، والتشغيل غير المستهدف يرفع CommandError."""
        # sub_a لديه 130 مستهلك ومشمول 100 فتوجد عمليات زائدة
        # نحذف أي اشتراكات أخرى للتأكد من المقارنة النظيفة
        ServiceSubscription.objects.exclude(pk=self.sub_a.pk).delete()

        out_dry = StringIO()
        call_command(
            "bill_service_subscriptions",
            period="2026-08",
            fixed_fee_product_id=self.fixed_fee_product.pk,
            dry_run=True,
            stdout=out_dry,
        )
        dry_output = out_dry.getvalue()
        self.assertIn("[تخطي]", dry_output)
        self.assertIn("سيُفوتر فعلياً: 0", dry_output)

        out_real = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "bill_service_subscriptions",
                period="2026-08",
                fixed_fee_product_id=self.fixed_fee_product.pk,
                stdout=out_real,
            )
        self.assertFalse(SubscriptionBillingRecord.objects.exists())
