"""ISSUE #59 — حساب إيراد المنتجات كان يُثبَّت على رأس شجرة الإيرادات لا على 4101.

`get_or_create_sales_settings` (`sales/services/foundation.py`) كانت تُثبّت
`default_revenue_account_product` بأوّل حساب إيراد **بالكود**: الترتيب النصّي
`'4' < '41' < '4101' < '4102' < '42'` يجعله رأس شجرة الإيرادات «4» — حسابٌ
**أب** لا يصلح هدفاً للترحيل. كل شركة أُنشئت قبل الإصلاح
(`resolve_product_revenue_account` في `sales/services/calc.py`) تحمل هذا الخطأ
في صفّ `SalesSettings` القائم، وكل بند بضاعةٍ فيها يُرحَّل على الرأس.

هذا الأمر يُبدّل الحقل **حيث كان المُثبَّت أباً فقط** (له حسابات أبناء) إلى ما
يحلّه `resolve_product_revenue_account` (4101 أو ما يطابقه، يُنشأ إن غاب). لا
يمسّ صفاً كان صحيحاً أصلاً، ولا حساباً، ولا قيداً مُرحَّلاً — الإصلاح على
الإعداد الافتراضي وحده، فيصحّ مسار الفواتير القادمة لا الماضية.

idempotent مثل `import_jarabaa`/`migrate_accountant_offices`: بعد التشغيل يصير
الحساب المثبَّت ورقةً بلا أبناء، فلا يُعاد ترشيحه في المرة التالية.

    python manage.py fix_product_revenue_account_default            # يطبّق فوراً
    python manage.py fix_product_revenue_account_default --dry-run  # تقريرٌ فقط
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from accounting.models import Account
from sales.models import SalesSettings
from sales.services import resolve_product_revenue_account


class Command(BaseCommand):
    help = (
        "يُبدّل default_revenue_account_product من حسابٍ أبٍ (رأس شجرة الإيرادات) "
        "إلى ما يحلّه resolve_product_revenue_account — حيث كان المُثبَّت أباً فقط."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="تقريرٌ فقط بلا كتابة — للتشغيل على نسخة الإنتاج أولاً.",
        )

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]

        self.stdout.write(self.style.MIGRATE_HEADING("قبل الإصلاح:"))
        self._report_counts()

        fixed = 0
        with transaction.atomic():
            rows = list(
                SalesSettings.objects.filter(default_revenue_account_product__isnull=False)
                .select_related("default_revenue_account_product")
                .order_by("pk")
            )
            for ss in rows:
                account = ss.default_revenue_account_product
                # «أب» = له حسابات أبناء في نفس الشركة — لا يُخمَّن بالكود لأن
                # شركات كثيرة تخالف الشجرة المعيارية.
                is_parent = account.children.filter(tenant_id=ss.tenant_id).exists()
                if not is_parent:
                    continue
                ss.default_revenue_account_product = None
                ss.save(update_fields=["default_revenue_account_product"])
                new_account = resolve_product_revenue_account(ss.tenant_id)
                fixed += 1
                self.stdout.write(
                    f"  [{ss.tenant_id}] {account.code} ({account.name}) → "
                    f"{new_account.code} ({new_account.name})"
                )

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(f"\nأُصلح {fixed} صفّاً."))
        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run: لم يُكتب شيء."))

        self.stdout.write(self.style.MIGRATE_HEADING(
            "بعد الإصلاح:" if not dry_run else "المتوقَّع لو نُفِّذ فعلياً:"
        ))
        if dry_run:
            self.stdout.write("  (تقرير فقط — الأعداد أعلاه هي الأثر المتوقَّع، لا القاعدة الفعلية.)")
        else:
            self._report_counts()

    def _report_counts(self):
        rows = (
            SalesSettings.objects.filter(default_revenue_account_product__isnull=False)
            .select_related("default_revenue_account_product")
        )
        total = 0
        parents = 0
        for ss in rows:
            total += 1
            if ss.default_revenue_account_product.children.filter(tenant_id=ss.tenant_id).exists():
                parents += 1
        self.stdout.write(
            f"  SalesSettings بحساب منتج مُثبَّت: {total} (منها {parents} على حسابٍ أب)"
        )
