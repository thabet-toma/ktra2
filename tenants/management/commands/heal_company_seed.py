"""task11 M7 — heal_company_seed

يصلح أي شركة أُنشئت بدون التأسيس الكامل (مثلاً عبر كود قديم أو admin):
  - شجرة حسابات معيارية إذا كانت **صفر حسابات** (لا يدمج أبداً في شجرة موجودة)
  - TenantSettings إن غابت
  - الفرع الرئيسي إن غاب
  - دفاتر الترقيم (idempotent)
  - السنة المالية الجارية إن لم تكن للشركة فترة تغطي اليوم (#213-أ)

آمن للتشغيل المتكرر: كل خطوة get_or_create / تتحقق قبل الإنشاء.

    python manage.py heal_company_seed            # كل الشركات
    python manage.py heal_company_seed --tenant 5 # شركة واحدة
"""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounting.models import Account, FiscalPeriod
from accounting.services import create_fiscal_year
from tenants.models import Branch, Tenant, TenantBook, TenantSettings
from tenants.services import COA_DATA, ensure_operational_accounts


class Command(BaseCommand):
    help = "يزرع COA/الفرع الرئيسي/الدفاتر/الإعدادات لأي شركة ناقصة التأسيس (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None, help="TenantID لشركة واحدة فقط")

    def handle(self, *args, **options):
        qs = Tenant.objects.all().order_by("TenantID")
        if options["tenant"]:
            qs = qs.filter(TenantID=options["tenant"])
            if not qs.exists():
                self.stderr.write(self.style.ERROR(f"لا توجد شركة TenantID={options['tenant']}"))
                return

        for tenant in qs:
            with transaction.atomic():
                fixed = []

                # 1) TenantSettings
                _, created = TenantSettings.objects.get_or_create(
                    tenant=tenant,
                    defaults={"company_name_primary": tenant.CompanyName},
                )
                if created:
                    fixed.append("settings")

                # 2) الفرع الرئيسي
                if not Branch.objects.filter(tenant=tenant, is_main=True).exists():
                    Branch.objects.create(
                        tenant=tenant, name="الفرع الرئيسي", code="MAIN",
                        is_main=True, is_active=True,
                    )
                    fixed.append("main-branch")

                # 3) شجرة الحسابات — فقط إذا كانت فارغة تماماً
                if not Account.objects.filter(tenant=tenant).exists():
                    account_map = {}
                    for code, acc_name, acc_type, parent_code in COA_DATA:
                        parent = account_map.get(parent_code) if parent_code else None
                        account_map[code] = Account.objects.create(
                            tenant=tenant, code=code, name=acc_name,
                            account_type=acc_type, parent=parent, is_active=True,
                        )
                    fixed.append(f"coa({len(COA_DATA)})")

                # 3b) الحسابات التشغيلية الناقصة في الشجرات القائمة (task13 M2)
                added_codes = ensure_operational_accounts(tenant)
                if added_codes:
                    fixed.append(f"ops-accounts(+{','.join(added_codes)})")

                # 4) دفاتر الترقيم (تُستكمل الناقصة فقط)
                created_books = 0
                for doc_type, doc_label in TenantBook.DOCUMENT_TYPES:
                    for book_number in range(1, 11):
                        _, was_created = TenantBook.objects.get_or_create(
                            tenant=tenant,
                            branch=None,
                            document_type=doc_type,
                            book_number=book_number,
                            defaults={
                                "name": f"{doc_label} — دفتر {book_number}",
                                "last_used_number": 0,
                                "is_active": True,
                            },
                        )
                        if was_created:
                            created_books += 1
                if created_books:
                    fixed.append(f"books(+{created_books})")

                # 5) السنة المالية الجارية (#213-أ) — شركات أُنشئت قبل أن تصير
                # الفترة تولد مع الشركة تبقى عمياء حتى أول ترحيل. لا يُلمَس
                # ماضٍ: إن وُجدت فترة تغطي اليوم (ولو مقفلة) لا نكتب شيئاً —
                # القفل قرار محاسب لا عطب تأسيس.
                today = timezone.localdate()
                has_today = FiscalPeriod.objects.filter(
                    tenant=tenant, start_date__lte=today, end_date__gte=today,
                ).exists()
                if not has_today:
                    try:
                        periods = create_fiscal_year(tenant, today.year)
                    except ValidationError as exc:
                        # سنةٌ فيها فتراتٌ بمدَياتٍ يدويّةٍ لا تطابق الأشهر: لا
                        # نكسر التشغيلة كلَّها على شركةٍ واحدة — تُسمّى ويُكمَل،
                        # فالفترات المخصّصة قرار محاسب لا شيء يُصلَح تلقائياً.
                        fixed.append(f"fiscal-year({today.year}: تعذّر — {'؛ '.join(exc.messages)})")
                    else:
                        fixed.append(f"fiscal-year({today.year}: {len(periods)})")

                label = "، ".join(fixed) if fixed else "سليمة — لا تغيير"
                self.stdout.write(
                    self.style.SUCCESS(f"[{tenant.TenantID}] {tenant.CompanyName}: {label}")
                )
