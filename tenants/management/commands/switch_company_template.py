"""أمر نقل قالب شركة قائمة من الطرفية — مرآة زر «قالب الشركة» في
`CompanyManagementModal.tsx` (ISSUE #64)، لمن يفضّل السطر على الواجهة.

يستهلك سِجلّ `tenants.company_templates.COMPANY_TEMPLATES` ودالة
`tenants.services.switch_company_template` نفسيهما — **لا يعيد كتابة منطق
الزرع ولا ينسخه هنا**؛ نقطة الحقيقة الوحيدة تبقى في `tenants/services.py`.

افتراضياً **معاينة فقط** (بلا `--apply`، لا كتابة إطلاقاً): يطبع اسم الشركة،
قالبها الحالي، القالب المقصود، وعدد الحسابات وأنواع الدفاتر التي **ستُزرع**
لو نُفِّذ التبديل فعلاً. المعاينة تُحسَب بقراءتين فقط (مقارنة أكواد بذرة
القالب المقصود بما تملكه الشركة فعلاً) بلا فتح أي معاملة — أرخص من تنفيذ
داخل `transaction.atomic()` ثم استدعاء `rollback`، وأسلم: صفر خطر أن يتسرّب
أثرٌ جانبي (سطر `AccountingAuditLog` أو حفظ `tenant.template`) لو نُسي
التراجع يوماً بسبب استثناء غير متوقَّع في منتصف الحساب.

مع `--apply` ينادي `switch_company_template` القائمة حرفياً ويطبع ما أعادته.

    python manage.py switch_company_template --tenant-id 5 --template tyres
    python manage.py switch_company_template --tenant-id 5 --template tyres --apply
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from tenants.company_templates import COMPANY_TEMPLATES, assert_self_serve_template
from tenants.models import Tenant, TenantBook


class Command(BaseCommand):
    help = "معاينة أو تنفيذ نقل قالب شركة قائمة إلى قالب آخر (ISSUE #64)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, required=True, help="TenantID للشركة")
        parser.add_argument("--template", type=str, required=True, help="مفتاح القالب المقصود")
        parser.add_argument("--apply", action="store_true", help="نفّذ النقل (الافتراضي: معاينة فقط)")

    def handle(self, *args, **options):
        tenant_id = options["tenant_id"]
        template_key = options["template"]
        apply_switch = options["apply"]

        template_config = COMPANY_TEMPLATES.get(template_key)
        if template_config is None:
            raise CommandError(f"قالب الشركة «{template_key}» غير معروف.")

        try:
            assert_self_serve_template(template_key)
        except ValueError as exc:
            raise CommandError(str(exc))

        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            raise CommandError(f"لا توجد شركة TenantID={tenant_id}")

        from accounting.models import Account
        from tenants.services import COA_DATA

        coa_rows = template_config["coa"] or COA_DATA
        wanted_codes = {row[0] for row in coa_rows}
        existing_codes = set(
            Account.objects.filter(tenant=tenant, code__in=wanted_codes)
            .values_list("code", flat=True)
        )
        accounts_to_create = sorted(wanted_codes - existing_codes)

        doc_type_labels = dict(TenantBook.DOCUMENT_TYPES)
        doc_types = template_config["document_types"] or list(doc_type_labels)
        existing_doc_types = set(
            TenantBook.objects.filter(tenant=tenant, document_type__in=doc_types)
            .values_list("document_type", flat=True).distinct()
        )
        book_types_to_create = sorted(set(doc_types) - existing_doc_types)

        self.stdout.write(f"الشركة: {tenant.CompanyName} (TenantID={tenant.TenantID})")
        self.stdout.write(f"القالب الحالي: {tenant.template or 'general'}")
        self.stdout.write(
            f"القالب المقصود: {template_config['name']} ({template_config['key']})")
        self.stdout.write(
            f"حسابات ستُزرع ({len(accounts_to_create)}): {accounts_to_create}")
        self.stdout.write(
            f"أنواع دفاتر ستُزرع ({len(book_types_to_create)}): {book_types_to_create}")

        if not apply_switch:
            self.stdout.write(self.style.SUCCESS(
                "\n[معاينة فقط — لم يُعدَّل شيء. أضف --apply للتنفيذ.]"))
            return

        from tenants.services import switch_company_template

        result = switch_company_template(tenant, template_key)
        self.stdout.write(self.style.SUCCESS(
            f"\n[تم التنفيذ] القالب الآن: {result['tenant'].template} | "
            f"حسابات مُنشأة={result['accounts_created']} | "
            f"أنواع دفاتر مُنشأة={result['book_types_created']}"))
