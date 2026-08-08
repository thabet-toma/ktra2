"""T-CHQ3 — ضمّ الشيكات السائبة إلى سند قبض/صرف كي تدخل الدفاتر.

الشيك ليس مستنداً محاسبياً مستقلاً: في الأنظمة المهنية يُسجَّل داخل سند
قبض/صرف (أو من الفاتورة)، وبلا توزيع يكون **دفعةً على الحساب**. الشيكات التي
أُنشئت سابقاً من شاشة الشيكات وحدها بقيت بلا سند ⇒ بلا قيد، وحتى ضغط «تحويل»
لم يكن يرحّل شيئاً لأن `transfer_cheque` يتخطّى الشيك غير المربوط بمستند.

هذا الأمر ينشئ لكل شيك سائب سنده المقابل (بلا توزيع = على الحساب) ويُرحّله،
فيظهر الشيك في القيود وكشف الطرف، ويصير قابلاً لإغلاق دورته لاحقاً:
  - وارد → `CustomerPayment` : مدين «شيكات برسم التحصيل» ÷ دائن ذمم العميل
  - صادر → `SupplierPayment` : مدين ذمم المورد ÷ دائن «شيكات برسم الدفع»

التوزيع على فاتورة بعينها يبقى قرار المستخدم — يُوزَّع بعدها من السند نفسه.
الافتراضي **معاينة فقط**؛ الكتابة تحتاج --apply.

    python manage.py wrap_orphan_cheques_in_vouchers --tenant-id 1
    python manage.py wrap_orphan_cheques_in_vouchers --tenant-id 1 --apply
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounting.models import Cheque
from accounting.services import cheque_is_linked_to_document
from accounting.services import resolve_default_cash_account


class Command(BaseCommand):
    help = "Wrap standalone cheques in a customer/supplier payment voucher and post it."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, required=True)
        parser.add_argument("--cheque-id", type=int, default=None,
                            help="اقتصر على شيك واحد.")
        parser.add_argument("--apply", action="store_true",
                            help="اكتب السندات فعلاً (الافتراضي معاينة فقط).")

    def handle(self, *args, **opts):
        tenant_id = opts["tenant_id"]
        apply_changes = opts["apply"]
        qs = Cheque.objects.filter(tenant_id=tenant_id).select_related(
            'partner', 'currency',
        ).order_by('pk')
        if opts["cheque_id"]:
            qs = qs.filter(pk=opts["cheque_id"])
        if not qs.exists():
            raise CommandError(f"لا توجد شيكات للشركة {tenant_id}.")

        cash_account = resolve_default_cash_account(tenant_id)
        if cash_account is None:
            raise CommandError(
                "لا يوجد صندوق افتراضي للشركة — عيّن default_cash_account أولاً.")

        wrapped = skipped = failed = 0
        for cheque in qs:
            reason = self._skip_reason(cheque)
            if reason:
                skipped += 1
                self.stdout.write(f"  — تخطّي شيك {cheque.cheque_number}: {reason}")
                continue
            kind = "سند قبض" if cheque.direction == "Incoming" else "سند صرف"
            self.stdout.write(
                f"  • شيك {cheque.cheque_number} ({cheque.amount} "
                f"{cheque.partner.name}) → {kind} على الحساب"
            )
            if not apply_changes:
                wrapped += 1
                continue
            try:
                with transaction.atomic():
                    self._wrap(cheque, cash_account)
            except ValidationError as e:
                failed += 1
                msgs = e.messages if hasattr(e, "messages") else [str(e)]
                self.stderr.write(
                    f"    ✗ تعذّر إنشاء سند شيك {cheque.cheque_number}: {'؛ '.join(msgs)}")
            else:
                wrapped += 1

        head = "تم الإنشاء والترحيل" if apply_changes else "معاينة (بلا كتابة — أضف --apply)"
        self.stdout.write(self.style.SUCCESS(
            f"{head}: {wrapped} شيك · تخطّي {skipped} · فشل {failed}"))

    def _skip_reason(self, cheque):
        if cheque_is_linked_to_document(cheque):
            return "مربوط بسند/فاتورة أصلاً"
        if Decimal(str(cheque.amount or 0)) <= 0:
            return "بلا مبلغ"
        if not cheque.partner_id:
            return "بلا طرف — لا يمكن تحديد حساب الذمم"
        if cheque.status in ("Returned", "Settled"):
            return f"حالة «{cheque.status}» منتهية — يحتاج مراجعة يدوية"
        return None

    def _wrap(self, cheque, cash_account):
        """ينشئ السند المقابل ويربط الشيك به ثم يُرحّله — بلا توزيع."""
        from sales.models import CustomerPayment, SupplierPayment
        from sales.services import post_customer_payment, post_supplier_payment

        when = cheque.issue_date or cheque.due_date
        common = dict(
            tenant_id=cheque.tenant_id,
            partner=cheque.partner,
            payment_date=when,
            amount=cheque.amount,
            currency=cheque.currency,
            cash_or_bank_account=cash_account,
            notes=f"سند مُنشأ لضمّ شيك {cheque.cheque_number} إلى الدفاتر",
        )
        if cheque.direction == "Incoming":
            payment = CustomerPayment.objects.create(**common)
            cheque.customer_payment = payment
            cheque.save(update_fields=["customer_payment"])
            post_customer_payment(payment)
        else:
            payment = SupplierPayment.objects.create(**common)
            cheque.supplier_payment = payment
            cheque.save(update_fields=["supplier_payment"])
            post_supplier_payment(payment)
        return payment
