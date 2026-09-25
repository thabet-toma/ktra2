"""تدقيق حسابات الأطراف في الشجرة: طرفٌ بلا حساب ذمم، أو حسابه تحت أبٍ لا يطابق نوعه.

قراءةٌ افتراضاً؛ `--apply` يصلح عبر `sync_partner_accounting` نفسِها التي يستدعيها
حفظ الطرف (تُكمل الأب المعياري الغائب مثل 2109، تنشئ الحساب أو تنقله لأبيه) — لا
منطق إصلاحٍ ثانٍ هنا. كل إصلاحٍ يُسجَّل في `AccountingAuditLog`. idempotent: الطرف
السليم لا يُمسّ، وتشغيلٌ ثانٍ بعد الإصلاح لا يجد شيئاً.

    python manage.py audit_partner_accounts --tenant 1
    python manage.py audit_partner_accounts --tenant 1 --apply
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from accounting.api import partner_account_problem, sync_partner_accounting
from accounting.services import create_audit_log
from partners.models import Partner
from tenants.models import Tenant


class Command(BaseCommand):
    help = "يعرض الأطراف بلا حساب ذمم أو تحت أبٍ لا يطابق نوعهم، ويصلحهم بـ--apply."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True, help="TenantID")
        parser.add_argument("--apply", action="store_true", help="نفّذ الإصلاح (افتراضاً قراءة فقط)")

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(TenantID=options["tenant"]).first()
        if tenant is None:
            raise CommandError(f"الشركة {options['tenant']} غير موجودة.")
        apply = options["apply"]

        partners = (
            Partner.objects.filter(tenant=tenant)
            .select_related("linked_account__parent")
            .order_by("partner_type", "id")
        )
        found = fixed = 0
        for partner in partners:
            problem = partner_account_problem(partner)
            if not problem:
                continue
            found += 1
            self.stdout.write(f"#{partner.id} [{partner.partner_type}] {problem}")
            if not apply:
                continue
            before = partner.linked_account.code if partner.linked_account_id else "—"
            sync_partner_accounting(partner)
            partner = Partner.objects.select_related("linked_account__parent").get(pk=partner.pk)
            after_problem = partner_account_problem(partner)
            if after_problem:
                self.stdout.write(self.style.WARNING(f"   لم يُصلَح: {after_problem}"))
                continue
            fixed += 1
            account = partner.linked_account
            create_audit_log(
                tenant=tenant, user=None, action="UPDATE",
                model_name="Partner", object_id=partner.id,
                change_details=(
                    f"audit_partner_accounts: حساب الطرف {before} ← {account.code} "
                    f"تحت {account.parent.code if account.parent_id else '—'}"
                ),
            )
            self.stdout.write(self.style.SUCCESS(
                f"   أُصلح: {account.code} تحت {account.parent.code if account.parent_id else '—'}"))

        mode = "تنفيذ" if apply else "قراءة فقط"
        self.stdout.write(f"\n{mode}: {found} طرفاً بخلل" + (f"، أُصلح {fixed}" if apply else ""))
