"""تذكرة #291 — «الانتقال»: تحويل مكتب محاسبةٍ قديم (`accounting_firm`) إلى
الموديول الجديد (`accounting_office`) بأمر إدارةٍ يدويّ، **لا بهجرة بيانات**.

القرار للمالك: تُرى القائمةُ قبل التنفيذ. فالافتراضي **معاينةٌ** لا تكتب شيئاً،
و`--apply` وحده يبدّل القالب ويمنح الترخيص.

التحويل = تبديلُ القالب + ترخيصُ `accounting_office` فقط:
`tenants.services.switch_company_template` تزرع الحسابات وأنواع الدفاتر الناقصة
وتضبط `tenant.template` وتكتب سجلَّ `AccountingAuditLog` — **ولا تمنح تراخيص**
(منطق الزرع عند الإنشاء في `tenants/services.py` وحده، وتبديلُ القالب لا يمرّ به
عمداً). فالترخيص هنا مرّةً واحدة على القيد الفريد `(tenant, module_key)`، ولا
يُكتب في `AccountingAuditLog` سطرٌ ثانٍ من هذا الأمر.

    python manage.py switch_office_to_new_module --tenant-id 22
    python manage.py switch_office_to_new_module --tenant-id 22 --apply
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import TenantModule
from core.modules import invalidate_module_cache
from tenants.models import Tenant
from tenants.services import switch_company_template

TARGET_TEMPLATE = "accounting_office"
#: ما يُقبل التحويل منه: القالبُ القديم، والقالبُ المقصود نفسه (idempotent).
SOURCE_TEMPLATES = ("accounting_firm", TARGET_TEMPLATE)
MODULE_KEY = "accounting_office"
#: يُقرأ بشرٍ إنسان — يفرّق ترخيصَ التحويل اليدويّ عن زرع الإنشاء التلقائي.
PLAN_NOTE = "زُرعت بأمر switch_office_to_new_module — تذكرة #291"


def _licensed_modules(tenant) -> list[str]:
    return sorted(
        TenantModule.objects.filter(tenant=tenant, enabled=True)
        .values_list("module_key", flat=True)
    )


def _template_label(tenant) -> str:
    return tenant.template or "general"


class Command(BaseCommand):
    help = (
        "معاينة أو تنفيذ تحويل مكتب محاسبة قديم (accounting_firm) إلى الموديول "
        "الجديد (accounting_office) بترخيصه (تذكرة #291)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id", type=int, action="append", dest="tenant_ids", metavar="ID",
            help="TenantID للشركة — قابل للتكرار (المكتبُ الذي يُحوَّل)",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="معاينةٌ فقط، وهي الافتراضي — لا تكتب شيئاً",
        )
        parser.add_argument(
            "--apply", action="store_true", help="نفّذ تبديل القالب ومنح الترخيص",
        )

    def handle(self, *args, **options):
        apply_changes = self._resolve_mode(options)

        tenant_ids = list(dict.fromkeys(options.get("tenant_ids") or []))
        if not tenant_ids:
            raise CommandError(
                "«--tenant-id» مطلوبٌ مرّةً واحدة على الأقل — لم تُحدَّد أيُّ شركة."
            )

        tenants = self._load_tenants(tenant_ids)
        self._refuse_ineligible(tenants)

        if not apply_changes:
            self._print_preview(tenants)
            return

        for tenant in tenants:
            self._switch_one(tenant)

    # ── الحرّاس ────────────────────────────────────────────────────────────

    def _resolve_mode(self, options) -> bool:
        apply_changes = bool(options.get("apply"))
        if apply_changes and options.get("dry_run"):
            raise CommandError(
                "لا تجمع «--dry-run» و«--apply»: المعاينةُ هي الافتراضي، "
                "و«--apply» وحده ينفّذ."
            )
        return apply_changes

    def _load_tenants(self, tenant_ids: list[int]) -> list[Tenant]:
        tenants = {tenant.pk: tenant for tenant in Tenant.objects.filter(pk__in=tenant_ids)}
        missing = [tid for tid in tenant_ids if tid not in tenants]
        if missing:
            raise CommandError(
                "لا توجد شركة/شركات بهذه المعرّفات: "
                + "، ".join(f"TenantID={tid}" for tid in missing)
            )
        return [tenants[tid] for tid in tenant_ids]

    def _refuse_ineligible(self, tenants: list[Tenant]) -> None:
        """الدفترُ المُدار ليس مكتباً، والقالبُ غير قالبَي المكتب لا يُحوَّل.

        الشركةُ المُدارة (`managed_by` غير فارغ) دفترٌ يملكه مكتبٌ آخر — تحويلُ
        قالبِ دفترٍ إلى قالب الموديول الجديد يفتح عليه شاشاتِ مكتبٍ لا يملكها.
        """
        problems: list[str] = []
        for tenant in tenants:
            if tenant.managed_by_id is not None:
                problems.append(
                    f"الشركة {tenant.TenantID} «{tenant.CompanyName}» دفترٌ مُدار "
                    f"(managed_by={tenant.managed_by_id}) — المكتبُ مالكٌ لا دفتر: "
                    "حوِّل المكتبَ المالك بدلاً منه."
                )
            if tenant.template not in SOURCE_TEMPLATES:
                problems.append(
                    f"الشركة {tenant.TenantID} «{tenant.CompanyName}» قالبُها "
                    f"«{_template_label(tenant)}» — التحويل يقبل قالب «accounting_firm» "
                    "أو «accounting_office» وحدهما."
                )
        if problems:
            raise CommandError("\n".join(problems))

    # ── المعاينة ───────────────────────────────────────────────────────────

    def _print_preview(self, tenants: list[Tenant]) -> None:
        self.stdout.write(
            "TenantID | CompanyName | القالب الحالي | managed_by | "
            "الوحدات المرخّصة | ما سيتغيّر"
        )
        for tenant in tenants:
            licensed = _licensed_modules(tenant)
            self.stdout.write(" | ".join([
                str(tenant.TenantID),
                tenant.CompanyName,
                _template_label(tenant),
                "—" if tenant.managed_by_id is None else str(tenant.managed_by_id),
                "، ".join(licensed) if licensed else "—",
                self._pending_changes(tenant),
            ]))
        self.stdout.write(self.style.SUCCESS(
            "\n[معاينة فقط — لم يُعدَّل شيء. أضف --apply للتنفيذ.]"
        ))

    @staticmethod
    def _pending_changes(tenant: Tenant) -> str:
        changes: list[str] = []
        if tenant.template != TARGET_TEMPLATE:
            changes.append(f"القالب: {_template_label(tenant)} → {TARGET_TEMPLATE}")
        if not TenantModule.objects.filter(
            tenant=tenant, module_key=MODULE_KEY, enabled=True,
        ).exists():
            changes.append(f"الترخيص: يُضاف {MODULE_KEY}")
        return "؛ ".join(changes) if changes else "لا شيء"

    # ── التنفيذ ────────────────────────────────────────────────────────────

    def _switch_one(self, tenant: Tenant) -> None:
        """شركةٌ واحدة في معاملةٍ مستقلّة: تبديلُها لا يجرّ غيره معه."""
        with transaction.atomic():
            switched = tenant.template != TARGET_TEMPLATE
            old_template = _template_label(tenant)
            if switched:
                result = switch_company_template(tenant, TARGET_TEMPLATE)
                tenant = result["tenant"]
                accounts_created = result["accounts_created"]
                book_types_created = result["book_types_created"]

            licence, created = TenantModule.objects.get_or_create(
                tenant=tenant,
                module_key=MODULE_KEY,
                defaults={
                    "enabled": True,
                    "enabled_at": timezone.now(),
                    "plan_note": PLAN_NOTE,
                },
            )
            # صفٌّ موجودٌ لكنه معطّل: الترخيص يبقى مُشترَطاً للتحويل، فيُفعّل.
            flipped = False
            if not created and not licence.enabled:
                licence.enabled = True
                licence.enabled_at = timezone.now()
                licence.save(update_fields=["enabled", "enabled_at"])
                flipped = True

        # الكاش المشترك `modules:<id>` يعيش 300 ثانية؛ بلا إبطاله يبقى المكتبُ
        # بلا ترخيصٍ عند التشغيل حتى انتهاء المدّة رغم أن الصفّ في القاعدة.
        invalidate_module_cache(tenant.pk)

        if switched:
            self.stdout.write(self.style.SUCCESS(
                f"[تم] TenantID={tenant.TenantID} «{tenant.CompanyName}»: "
                f"القالب {old_template} → {tenant.template} | "
                f"حسابات مُنشأة ({len(accounts_created)}): {accounts_created} | "
                f"أنواع دفاتر مُنشأة ({len(book_types_created)}): {book_types_created}"
            ))
        else:
            self.stdout.write(
                f"[تخطّي] TenantID={tenant.TenantID} «{tenant.CompanyName}»: "
                f"القالب {TARGET_TEMPLATE} مسبقاً — لا تبديلَ ولا سجلَّ تدقيقٍ ثانٍ."
            )

        licence_state = "أُضيف" if created else ("فُعّل" if flipped else "موجودٌ مسبقاً")
        self.stdout.write(f"      الترخيص {MODULE_KEY}: {licence_state}")
