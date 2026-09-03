# -*- coding: utf-8 -*-
"""ISSUE #86 — مكانٌ واحد: عملاء المكتب أطرافٌ (`partners.Partner`) لا سجلٌّ
منفصل (`PracticeClient`). ينقل كل `PracticeClient` تابعٍ لمحاسبٍ له مكتبٌ
(`role=manager` على شركةٍ ليست دفتراً مُداراً — نتيجة `migrate_accountant_offices`
لو رُحِّل، ISSUE #55) إلى طرفٍ داخل شركة ذلك المكتب، ويُبقي `PracticeClient`
كما هو — لا كتابة ولا حذف عليه.

idempotent مثل `migrate_accountant_offices`: العلامة على النقل صفّ
`CustomerNote` بـ`target_type='practice_client_migration'` و`target_id` = رقم
`PracticeClient` الأصلي؛ وجودها يعني أن هذا الزبون نُقل، فإعادة التشغيل لا
تُنشئ طرفاً ثانياً — لكنها تُكمل ربط أي برنامج/موعد/مستند لم يُربط بعد (مثلاً
أُضيف بعد أول تشغيلة).

لا حذف لأي صفّ — `PracticeClient` يبقى تاريخاً مهنياً حتى تذكرة الحذف
الموثَّقة في `docs/decisions/practice_client_retirement.md`.

الاستخدام:
  python manage.py migrate_practice_clients_to_partners [--dry-run]
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.db import transaction

from accountant_portal.models import (
    AccountantProfile,
    PracticeClient,
    PracticeDocument,
    PracticeProgram,
    PracticeTask,
)
from accountant_portal.practice import (
    MIGRATION_MARKER_TARGET_TYPE as MARKER_TARGET_TYPE,
    PROFILE_NOTE_TARGET_TYPE,
)


class Command(BaseCommand):
    help = "ينقل زبائن سجلّ المكتب (PracticeClient) إلى أطراف شركة المكتب (Partner) — idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="تقريرٌ فقط بلا كتابة.",
        )

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]

        self.stdout.write(self.style.MIGRATE_HEADING("قبل النقل:"))
        self._report_counts()

        partners_created = partners_already = clients_without_office = 0
        children_backfilled = 0

        with transaction.atomic():
            for profile in AccountantProfile.objects.select_related("user").order_by("pk"):
                accountant = profile.user
                tenant_id = self._office_tenant_id(accountant)
                clients = PracticeClient.objects.filter(accountant=accountant).order_by("pk")
                for practice_client in clients:
                    if tenant_id is None:
                        clients_without_office += 1
                        continue
                    partner_id, created = self._ensure_partner(
                        practice_client, tenant_id=tenant_id, apply=not dry_run,
                    )
                    if created:
                        partners_created += 1
                    else:
                        partners_already += 1
                    children_backfilled += self._backfill_children(
                        practice_client, partner_id=partner_id, apply=not dry_run,
                    )

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"\nالزبائن: {partners_created} نُقلوا إلى أطراف، {partners_already} كانوا منقولين سلفاً، "
            f"{clients_without_office} بلا مكتب بعد (لم يُمَسّوا).\n"
            f"صفوف برامج/مواعيد/مستندات رُبطت بطرفها: {children_backfilled}."
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run: لم يُكتب شيء."))

        self.stdout.write(self.style.MIGRATE_HEADING(
            "بعد النقل:" if not dry_run else "المتوقَّع لو نُفِّذ فعلياً:"
        ))
        if dry_run:
            self.stdout.write("  (تقرير فقط — الأعداد أعلاه هي الأثر المتوقَّع، لا القاعدة الفعلية.)")
        else:
            self._report_counts()

    # ── المكتب ────────────────────────────────────────────────────────────

    def _office_tenant_id(self, user) -> int | None:
        """نفس شرط `accountant_portal.practice._office_tenant_ids`: عضوية
        `manager` على شركةٍ ليست دفتراً مُداراً — أول مكتبٍ لهذا المحاسب."""
        from tenants.models import UserCompanyMembership

        membership = (
            UserCompanyMembership.objects
            .filter(user=user, role="manager", tenant__managed_by__isnull=True)
            .order_by("tenant_id")
            .first()
        )
        return membership.tenant_id if membership else None

    # ── الزبون ────────────────────────────────────────────────────────────

    def _existing_marker(self, practice_client, *, tenant_id):
        from partners.models import CustomerNote

        return (
            CustomerNote.objects
            .filter(
                tenant_id=tenant_id,
                target_type=MARKER_TARGET_TYPE,
                target_id=str(practice_client.pk),
            )
            .select_related("partner")
            .first()
        )

    def _ensure_partner(self, practice_client, *, tenant_id, apply: bool) -> tuple[int | None, bool]:
        """يعيد (معرّف الطرف أو None، أُنشئ حديثاً؟). None فقط في --dry-run
        حين لا يوجد الطرف بعد (لا شيء لنُبني عليه استعلام الربط بلا كتابة)."""
        marker = self._existing_marker(practice_client, tenant_id=tenant_id)
        if marker is not None:
            return marker.partner_id, False

        if not apply:
            return None, True

        from partners.models import CustomerNote, Partner

        partner = Partner.objects.create(
            tenant_id=tenant_id,
            partner_type="Customer",
            name=practice_client.trade_name[:150],
            # حقول الطرف قد تكون أضيق من حقول سجلّ المكتب (`phone` هنا 20 محرفاً
            # مقابل 30 هناك) — تُقصّ لا تُسقَط، والقيمة كاملةً تبقى في السجلّ
            # التاريخي (`PracticeClient`) نفسه فلا فقد حقيقياً.
            phone=self._truncated(Partner, "phone", practice_client.phone),
            mobile=self._truncated(Partner, "mobile", practice_client.mobile),
            email=self._truncated(Partner, "email", practice_client.email),
            street_address=practice_client.address or None,
            sector=self._truncated(Partner, "sector", practice_client.sector),
            tax_number=self._truncated(Partner, "tax_number", practice_client.tax_number),
            engagement_id=practice_client.engagement_id,
            managed_tenant_id=practice_client.managed_tenant_id,
        )
        CustomerNote.objects.create(
            tenant_id=tenant_id,
            partner=partner,
            target_type=MARKER_TARGET_TYPE,
            target_id=str(practice_client.pk),
            target_label=practice_client.trade_name,
            title="مرحّل من سجلّ مكتب المحاسبة (ISSUE #86)",
            body=self._preserved_notes_body(practice_client),
            created_by=practice_client.accountant,
        )
        # جهة الاتصال والملاحظات الحرّة — بصيغةٍ حيّة (JSON) يقرؤها ويكتبها
        # `accountant_portal.practice` (`_load_profile_notes`/`_save_profile_note`)
        # لا نصّاً تاريخياً وحده كسابقتها أعلاه.
        CustomerNote.objects.create(
            tenant_id=tenant_id,
            partner=partner,
            target_type=PROFILE_NOTE_TARGET_TYPE,
            target_id=str(partner.pk),
            title="ملف تعريف زبون المكتب",
            body=json.dumps({
                "contact_first": practice_client.contact_first[:100],
                "contact_last": practice_client.contact_last[:100],
                "notes": practice_client.notes[:2000],
            }, ensure_ascii=False),
            created_by=practice_client.accountant,
        )
        return partner.pk, True

    def _truncated(self, model, field_name, value):
        if not value:
            return None
        limit = model._meta.get_field(field_name).max_length
        return value[:limit] if limit else value

    def _preserved_notes_body(self, practice_client) -> str:
        """يحفظ ما لا حقل مطابقاً له على الطرف: اسم جهة الاتصال والحالة
        والملاحظات الحرّة — «لا فقد حقل» رغم أن الطرف لا يحمل هذه الحقول."""
        contact = " ".join(
            part for part in (practice_client.contact_first, practice_client.contact_last) if part
        )
        lines = []
        if contact:
            lines.append(f"جهة الاتصال: {contact}")
        lines.append(f"حالة السجلّ الأصلي: {practice_client.get_status_display()}")
        if practice_client.notes:
            lines.append(f"ملاحظات: {practice_client.notes}")
        return "\n".join(lines)

    # ── البرامج/المواعيد/المستندات ────────────────────────────────────────

    def _backfill_children(self, practice_client, *, partner_id, apply: bool) -> int:
        """يربط صفوف البرامج/المواعيد/المستندات التابعة لهذا الزبون بالطرف —
        بلا مسّ `client` (يبقى تاريخاً)، وبلا الكتابة فوق `partner` مربوطة سلفاً.

        `partner_id` قد يكون `None` في `--dry-run` (الطرف لم يُنشأ بعد) — العدّ
        يبقى دقيقاً، والكتابة وحدها تُشترط بوجوده فعلاً.
        """
        total = 0
        for model in (PracticeProgram, PracticeTask, PracticeDocument):
            pending = model.objects.filter(client=practice_client, partner__isnull=True)
            count = pending.count()
            if count and apply and partner_id is not None:
                pending.update(partner_id=partner_id)
            total += count
        return total

    # ── التقرير ───────────────────────────────────────────────────────────

    def _report_counts(self):
        from partners.models import CustomerNote

        practice_clients = PracticeClient.objects.count()
        migrated = CustomerNote.objects.filter(target_type=MARKER_TARGET_TYPE).count()
        self.stdout.write(
            f"  PracticeClient: {practice_clients} (منها {migrated} نُقل إلى طرف)\n"
            f"  برامج بلا طرف بعد: {PracticeProgram.objects.filter(partner__isnull=True, client__isnull=False).count()}\n"
            f"  مواعيد بلا طرف بعد: {PracticeTask.objects.filter(partner__isnull=True, client__isnull=False).count()}\n"
            f"  مستندات بلا طرف بعد: {PracticeDocument.objects.filter(partner__isnull=True, client__isnull=False).count()}"
        )
