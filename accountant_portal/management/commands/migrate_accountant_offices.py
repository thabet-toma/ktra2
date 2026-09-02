# -*- coding: utf-8 -*-
"""ISSUE #55 — ترحيل العالم القائم إلى المكتب: كل محاسبٍ مسجَّل يصير مديرَ
مكتبٍ (قالب `accounting_firm`)، وكل ارتباطٍ نشط (`AccountantEngagement`) يصير
زبونَ مكتبٍ من نوع «مربوطٌ بإذنه» — دون قطع ارتباطٍ قائم أو حذف صفٍّ واحد.

idempotent مثل `import_jarabaa`: يفحص وجود المكتب/الربط قبل الإنشاء، فإعادة
التشغيل لا تضاعف شيئاً.

الاستخدام:
  python manage.py migrate_accountant_offices [--dry-run]
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from accountant_portal.audit import write_financial_audit
from accountant_portal.models import AccountantEngagement, AccountantProfile, PracticeClient
from tenants.models import Tenant, UserCompanyMembership
from tenants.services import create_company

OFFICE_TEMPLATE = "accounting_firm"


class Command(BaseCommand):
    help = "يرحّل المحاسبين وزبائنهم القائمين إلى مكاتب accounting_firm — idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="تقريرٌ فقط بلا كتابة — للتشغيل على نسخة الإنتاج أولاً.",
        )

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]

        self.stdout.write(self.style.MIGRATE_HEADING("قبل الترحيل:"))
        self._report_counts()

        offices_created = offices_reused = 0
        clients_created = clients_linked = clients_already = 0

        with transaction.atomic():
            for profile in AccountantProfile.objects.select_related("user").order_by("pk"):
                created = self._ensure_office(profile.user, apply=not dry_run)
                if created:
                    offices_created += 1
                else:
                    offices_reused += 1

            engagements = (
                AccountantEngagement.objects
                .filter(status="active")
                .select_related("tenant", "accountant")
                .order_by("pk")
            )
            for engagement in engagements:
                outcome = self._ensure_engaged_client(engagement, apply=not dry_run)
                if outcome == "created":
                    clients_created += 1
                elif outcome == "linked_manual":
                    clients_linked += 1
                else:
                    clients_already += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"\nالمكاتب: {offices_created} أُنشئت، {offices_reused} كانت موجودة.\n"
            f"زبائن الارتباط: {clients_created} أُنشئت، {clients_linked} رُبطت بزبون يدوي قائم، "
            f"{clients_already} كانت مرتبطة سلفاً."
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run: لم يُكتب شيء."))

        self.stdout.write(self.style.MIGRATE_HEADING(
            "بعد الترحيل:" if not dry_run else "المتوقَّع لو نُفِّذ فعلياً:"
        ))
        if dry_run:
            self.stdout.write("  (تقرير فقط — الأعداد أعلاه هي الأثر المتوقَّع، لا القاعدة الفعلية.)")
        else:
            self._report_counts()

    # ── المكتب ────────────────────────────────────────────────────────────

    def _existing_office(self, user) -> Tenant | None:
        """مكتبٌ قائم لهذا المحاسب — عضوية `manager` على شركةٍ ليست دفتراً مُداراً.

        نفس شرط `_office_tenant_ids` في `practice.py`: `managed_by__isnull=True`
        يستثني دفاتر الزبائن المُدارة كي لا يُحسب دفترُ زبونٍ مكتباً للمحاسب.
        """
        membership = (
            UserCompanyMembership.objects
            .filter(user=user, role="manager", tenant__managed_by__isnull=True)
            .select_related("tenant")
            .order_by("tenant_id")
            .first()
        )
        return membership.tenant if membership else None

    def _ensure_office(self, user, *, apply: bool) -> bool:
        """يعيد True إن أُنشئ مكتبٌ جديد، False إن وُجد مسبقاً — بلا لمسه."""
        existing = self._existing_office(user)
        if existing is not None:
            return False
        if not apply:
            return True
        full_name = user.get_full_name() or user.username
        office = create_company(f"مكتب {full_name}", user, template=OFFICE_TEMPLATE)
        write_financial_audit(
            tenant=office, user=user, action="OFFICE_MIGRATED",
            model_name="Tenant", object_id=office.pk,
            change_details="issue-55: ترحيل محاسبٍ مسجَّل إلى مكتب accounting_firm",
        )
        return True

    # ── زبائن الارتباط النشط ─────────────────────────────────────────────

    def _ensure_engaged_client(self, engagement: AccountantEngagement, *, apply: bool) -> str:
        """يعيد: 'already' (مرتبط سلفاً) · 'linked_manual' (رُبط بزبونٍ يدوي قائم)
        · 'created' (أُنشئ زبونٌ جديد). لا حذف ولا كسر لربطٍ قائم أبداً."""
        if PracticeClient.objects.filter(engagement=engagement).exists():
            return "already"

        base_name = engagement.tenant.CompanyName
        # زبونٌ يدويٌّ أدخله المحاسب سابقاً بنفس الاسم ولم يُربط بعد — يُربط لا يُكرَّر.
        unlinked = PracticeClient.objects.filter(
            accountant=engagement.accountant, trade_name=base_name,
            engagement__isnull=True, managed_tenant__isnull=True,
        ).first()
        if unlinked is not None:
            if apply:
                unlinked.engagement = engagement
                unlinked.save(update_fields=["engagement", "updated_at"])
            return "linked_manual"

        if not apply:
            return "created"
        trade_name = base_name
        # تصادم اسمٍ نادر (قيد الفرادة accountant+trade_name) — التمييز برقم الشركة.
        if PracticeClient.objects.filter(accountant=engagement.accountant, trade_name=trade_name).exists():
            trade_name = f"{base_name} #{engagement.tenant_id}"
        PracticeClient.objects.create(
            accountant=engagement.accountant, trade_name=trade_name,
            status="active", engagement=engagement,
        )
        return "created"

    # ── التقرير ───────────────────────────────────────────────────────────

    def _report_counts(self):
        offices = UserCompanyMembership.objects.filter(
            role="manager", tenant__managed_by__isnull=True,
            user__accountant_profile__isnull=False,
        ).values("user_id").distinct().count()
        active_engagements = AccountantEngagement.objects.filter(status="active").count()
        practice_clients = PracticeClient.objects.count()
        engaged_clients = PracticeClient.objects.filter(engagement__isnull=False).count()
        self.stdout.write(
            f"  محاسبون: {AccountantProfile.objects.count()} · مكاتبهم القائمة: {offices}\n"
            f"  ارتباطات نشطة: {active_engagements}\n"
            f"  PracticeClient: {practice_clients} (منها {engaged_clients} مربوط بارتباط)"
        )
