"""أمر الإسناد الخلفي لمرتجعات الشراء القديمة وأساس العكس (PRET-M1-MODELS).

الأمر معاينةٌ افتراضياً: بلا علَمٍ لا يُكتب شيء، و`--apply` وحده يكتب.

الاستعمال:
    python manage.py backfill_purchase_returns                          # معاينة
    python manage.py backfill_purchase_returns --tenant 6               # معاينة شركة
    python manage.py backfill_purchase_returns --tenant 6 --apply       # كتابة فعلية
    python manage.py backfill_purchase_returns --rollback <run_id>      # معاينة التراجع
    python manage.py backfill_purchase_returns --rollback <run_id> --apply   # تراجع فعلي

`--dry-run` مرادفٌ للافتراضي، ومعه `--apply` خطأ (`CommandError`).
"""
from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand, CommandError

from logistics.models import PurchaseReturnBackfill
from logistics.purchase_return_basis import (
    rollback_backfill_for_tenant,
    run_backfill_for_tenant,
)
from tenants.models import Tenant

PREVIEW_NOTICE = "معاينة فقط — مرّر --apply للكتابة. لم يُكتب شيء في قاعدة البيانات."


class Command(BaseCommand):
    help = (
        "إسناد خلفي قابل للتراجع لكميات المرتجعات المرحّلة القديمة وأساس العكس "
        "لفواتير الشراء المرحّلة (PRET-M1-MODELS). معاينةٌ افتراضياً؛ --apply للكتابة."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="الكتابة الفعلية (إسناداً أو تراجعاً). بدونه الأمر معاينةٌ لا تكتب شيئاً.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="معاينة كاملة دون كتابة أي صف (مرادفٌ للسلوك الافتراضي؛ لا يُجمع مع --apply).",
        )
        parser.add_argument(
            "--tenant", type=int,
            help="معرّف الشركة (افتراضياً كل الشركات).",
        )
        parser.add_argument(
            "--rollback", type=str,
            help="معرّف التشغيل (run_id) للتراجع عنه.",
        )

    def handle(self, *args, **options):
        if options.get("apply") and options.get("dry_run"):
            raise CommandError("--apply و--dry-run متعارضان: اختر أحدهما.")
        dry_run = not options.get("apply")
        rollback_run_id = options.get("rollback")
        tenants = Tenant.objects.all().order_by("TenantID")
        if options.get("tenant") is not None:
            tenants = tenants.filter(TenantID=options["tenant"])
            if not tenants.exists():
                raise CommandError(f"الشركة غير موجودة (tenant={options['tenant']}).")

        if rollback_run_id is not None:
            if not rollback_run_id.strip():
                raise CommandError("معرّف التشغيل (--rollback) فارغ.")
            self._handle_rollback(tenants, run_id=rollback_run_id, dry_run=dry_run)
            return

        run_id = str(uuid.uuid4())
        tot_returns = 0
        tot_groups = 0
        tot_applied = 0
        tot_exc = 0
        tot_basis_ok = 0
        tot_basis_diff = 0

        for tenant in tenants:
            r = run_backfill_for_tenant(tenant, run_id=run_id, dry_run=dry_run)
            tot_returns += r.returns_assigned
            tot_groups += r.groups_assigned
            tot_applied += r.applied_rows
            tot_exc += r.exceptions_count
            tot_basis_ok += r.basis_matched
            tot_basis_diff += r.basis_mismatched
            if (
                r.returns_assigned
                or r.groups_assigned
                or r.applied_rows
                or r.exceptions_count
                or r.basis_matched
                or r.basis_mismatched
            ):
                self.stdout.write(
                    f"شركة {r.tenant_id} ({r.company_name}): "
                    f"مرتجعات_مسندة={r.returns_assigned} · أسطر_applied={r.applied_rows} · "
                    f"استثناءات_كميات={r.exceptions_count} · أساس_مطابق={r.basis_matched} · "
                    f"أساس_مختلف={r.basis_mismatched} · مجموعات_مسندة={r.groups_assigned}"
                )
                for exc in r.exceptions:
                    if exc.kind == "quantities":
                        self.stdout.write(
                            f"  استثناء كميات · فاتورة {exc.invoice_number} (#{exc.invoice_id}) · "
                            f"بند مرتجع #{exc.return_item_id} · منتج #{exc.product_id} · {exc.reason}"
                        )
                    else:
                        self.stdout.write(
                            f"  استثناء أساس · فاتورة {exc.invoice_number} (#{exc.invoice_id}) · {exc.reason}"
                        )

        self.stdout.write(
            f"الإجمالي: مرتجعات_مسندة={tot_returns} · أسطر_applied={tot_applied} · "
            f"استثناءات_كميات={tot_exc} · أساس_مطابق={tot_basis_ok} · أساس_مختلف={tot_basis_diff} · "
            f"مجموعات_مسندة={tot_groups}"
        )
        self.stdout.write(f"run_id={run_id}")
        if dry_run:
            self.stdout.write(PREVIEW_NOTICE)

    def _handle_rollback(self, tenants, *, run_id: str, dry_run: bool):
        if not PurchaseReturnBackfill.objects.filter(tenant__in=tenants, run_id=run_id).exists():
            raise CommandError(
                f"لا توجد صفوف إسناد خلفي لمعرّف التشغيل run_id={run_id} ضمن النطاق المحدّد."
            )
        tot_rolled = 0
        tot_conflicts = 0
        for tenant in tenants:
            r = rollback_backfill_for_tenant(tenant, run_id=run_id, dry_run=dry_run)
            tot_rolled += r.rolled_back
            tot_conflicts += r.conflicts
            if r.rolled_back or r.conflicts:
                self.stdout.write(
                    f"شركة {r.tenant_id} ({r.company_name}): "
                    f"متراجَع={r.rolled_back} · تعارضات={r.conflicts}"
                )
                for msg in r.conflict_messages:
                    self.stdout.write(f"  {msg}")
        self.stdout.write(
            f"إجمالي التراجع (run_id={run_id}): متراجَع={tot_rolled} · تعارضات={tot_conflicts}"
        )
        if dry_run:
            self.stdout.write(PREVIEW_NOTICE)
