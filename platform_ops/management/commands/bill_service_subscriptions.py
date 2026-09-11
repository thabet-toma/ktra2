"""أمر إدارة فوترة اشتراكات خدمة عمليات المنصة (المرحلة 8A - Issue #207).

يقوم بفوترة الاشتراكات المستحقة وإصدار فواتير مبيعات حقيقية في شركة المنصة
وترحيلها محاسبياً، وتدوير دورة الاشتراك بأمان وذرية تامة.
"""
from django.core.management.base import BaseCommand, CommandError

from platform_ops.services import (
    BillingError,
    apply_due_subscription_cancellations,
    billing_preflight,
    bill_subscriptions_for_period,
    resolve_billing_period_bounds,
    resolve_subscription_billing_products,
)


class Command(BaseCommand):
    help = "إصدار فواتير اشتراكات خدمة المتابعة والإدخال الشهرية وترحيلها محاسبياً."

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            required=True,
            help="دورة الفوترة بصيغة YYYY-MM (مثال: 2026-08)",
        )
        parser.add_argument(
            "--fixed-fee-product-id",
            type=int,
            default=None,
            help=(
                "تجاوز صريح لصنف الرسم الشهري لكل اشتراكات هذا التشغيل؛ بدونه يُقرأ صنف لقطة كل اشتراك "
                "من سياسته، ثم PLATFORM_OPS_BILLING_FIXED_FEE_PRODUCT_ID للصفوف القديمة"
            ),
        )
        parser.add_argument(
            "--overage-product-id",
            type=int,
            default=None,
            help="تجاوز صريح لصنف العمليات الزائدة؛ بدونه لقطة الاشتراك ثم PLATFORM_OPS_BILLING_OVERAGE_PRODUCT_ID",
        )
        parser.add_argument(
            "--subscription-id",
            type=int,
            default=None,
            help="تحديد اشتراك معين للفوترة",
        )
        parser.add_argument(
            "--tenant-id",
            type=int,
            default=None,
            help="تحديد شركة معينة للفوترة",
        )
        parser.add_argument(
            "--currency-id",
            type=int,
            default=None,
            help="معرّف العملة (اختياري، يتبع افتراضي شركة المنصة)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="معاينة الفوترة دون إنشاء فواتير أو تعديل الاشتراكات",
        )

    def handle(self, *args, **options):
        period_str = options["period"]
        try:
            period_start, period_end = resolve_billing_period_bounds(period_str)
        except BillingError as e:
            raise CommandError(f"خطأ في تحديد دورة الفوترة: {e.detail}")

        # غياب الصنف لم يعد خطأ تشغيل عاماً: كل اشتراك يحمل صنفَي سياسته، ومن ينقصه يُبلَّغ عنه
        # بكود `missing_fixed_fee_product` من `billing_preflight` نفسه.
        fixed_fee_product_id = options.get("fixed_fee_product_id")

        overage_product_id = options.get("overage_product_id")
        subscription_id = options.get("subscription_id")
        tenant_id = options.get("tenant_id")
        currency_id = options.get("currency_id")
        dry_run = options.get("dry_run", False)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"--- وضع المعاينة (Dry-Run) لدورة {period_start} إلى {period_end} ---"
                )
            )
            # المعاينةُ تطبّق **نفسَ بوّابات التشغيل الحقيقيّ** عبر billing_preflight الموحدة
            from platform_ops.models import ServiceSubscription
            from platform_ops.services import calculate_subscription_billing

            qs = ServiceSubscription.objects.all()
            if subscription_id:
                qs = qs.filter(pk=subscription_id)
            if tenant_id:
                qs = qs.filter(tenant_id=tenant_id)

            candidates = list(qs.order_by("id"))
            self.stdout.write(f"عدد الاشتراكات المرشحة: {len(candidates)}")
            would_bill = 0
            for sub in candidates:
                sub_fixed_fee_product_id, sub_overage_product_id = resolve_subscription_billing_products(
                    sub, fixed_fee_product_id=fixed_fee_product_id, overage_product_id=overage_product_id,
                )
                err = billing_preflight(
                    subscription=sub,
                    period_start=period_start,
                    period_end=period_end,
                    fixed_fee_product_id=sub_fixed_fee_product_id,
                    overage_product_id=sub_overage_product_id,
                    check_already_billed=True,
                )
                if err is not None:
                    skip_reason = err.detail if hasattr(err, "detail") else str(err)
                    self.stdout.write(f"    [تخطي] اشتراك #{sub.id} (شركة {sub.tenant}): {skip_reason}")
                    continue

                would_bill += 1
                calc = calculate_subscription_billing(sub)
                self.stdout.write(
                    f"  الاشتراك #{sub.id} (شركة {sub.tenant}): "
                    f"ثابت={calc['monthly_fee']} | مستهلك={calc['consumed_quota']}/{calc['included_quota']} | "
                    f"زائد={calc['overage_units']} × {calc['overage_unit_price']} = {calc['overage_fee']} | "
                    f"الإجمالي={calc['total_amount']}"
                )
            self.stdout.write(f"سيُفوتر فعلياً: {would_bill}")
            return

        result = bill_subscriptions_for_period(
            period_start=period_start,
            period_end=period_end,
            fixed_fee_product_id=fixed_fee_product_id,
            overage_product_id=overage_product_id,
            currency_id=currency_id,
            subscription_id=subscription_id,
            tenant_id=tenant_id,
        )

        # الإلغاءاتُ المجدولة تُطبَّق **بعد** تمرير الفوترة لا قبله: الأمر يُشغَّل
        # صباح أوّل يومٍ من الشهر ليفوتر الدورة المنتهية للتوّ، وشركةٌ جُدول
        # إلغاؤها لنهاية تلك الدورة نفسها لا تزال تستحقّ فاتورتها الأخيرة —
        # §١ يمنع أيّ استرداد أو إسقاط جزئي لآخر شهرٍ خدمَته الخدمة فعلاً.
        applied = apply_due_subscription_cancellations()
        if applied["applied_count"]:
            self.stdout.write(
                f"تم تطبيق {applied['applied_count']} إلغاء مجدولاً بعد الفوترة: "
                f"{applied['applied_subscription_ids']}"
            )
        if applied["failed"]:
            self.stdout.write(
                self.style.ERROR(f"تعذّر تطبيق إلغاءات مجدولة: {applied['failed']}")
            )
        if applied["awaiting_final_billing_subscription_ids"]:
            self.stdout.write(
                self.style.WARNING(
                    "إلغاءات مؤجلة لأن دورتها الأخيرة لم تُفوتر بعد: "
                    f"{applied['awaiting_final_billing_subscription_ids']}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"اكتملت فوترة دورة {period_start} إلى {period_end}:\n"
                f"  - تم إصدار فواتير جديدة: {result['billed_count']}\n"
                f"  - مفوترة مسبقاً (idempotent): {result['already_billed_count']}\n"
                f"  - تم تخطيها: {result['skipped_count']}\n"
                f"  - أخطاء: {result['error_count']}"
            )
        )

        for b in result["billed"]:
            inv_str = f"فاتورة #{b['invoice_number']}" if b.get("invoice_number") else "بلا فاتورة — لا مبلغ"
            self.stdout.write(
                f"    [جديد] اشتراك #{b['subscription_id']} -> {inv_str} بمبلغ {b['total_amount']}"
            )

        for a in result["already_billed"]:
            inv_str = f"فاتورة #{a['invoice_number']}" if a.get("invoice_number") else "بلا فاتورة — لا مبلغ"
            self.stdout.write(
                f"    [مفوتر مسبقاً] اشتراك #{a['subscription_id']} -> {inv_str}"
            )

        for s in result["skipped"]:
            self.stdout.write(
                f"    [تخطي] اشتراك #{s['subscription_id']}: {s['reason']}"
            )

        for err in result["errors"]:
            self.stdout.write(
                self.style.ERROR(
                    f"    [خطأ] اشتراك #{err['subscription_id']}: {err['error']}"
                )
            )

        if result["error_count"] > 0:
            first_err = result["errors"][0]["error"] if result["errors"] else "فشلت الفوترة"
            raise CommandError(f"فشلت فوترة بعض الاشتراكات: {first_err}")
