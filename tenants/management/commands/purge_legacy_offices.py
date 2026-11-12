"""تذكرة #291 — «الانتقال»: حذفُ شركات التجربة القديمة بأمر إدارةٍ يدويّ،
**لا بهجرة بيانات**.

قرار المالك: تُرى القائمةُ قبل التنفيذ، وتُؤخذ نسخةٌ احتياطية، ولا يُنفَّذ شيءٌ
بـ`migrate`. لذلك:

- الافتراضي **معاينةٌ** تُظهر لكل شركةٍ أثرَها (المستخدمون، الأطراف، القيود،
  زبائن المكتب، ملكيةُ الدفاتر) ثم **خطّةَ الحذف مرتَّبةً**: الدفاترُ المُدارة
  أوّلاً ثم مالكوها.
- `--apply` يشترط `--confirm PURGE` حرفياً **و**`--backup-file` موجوداً وغير فارغ.
- الحذفُ بالترتيب المحسوب لا بترتيب الوسائط: `Tenant.managed_by` على `PROTECT`،
  فحذفُ المكتب قبل دفاتره يرفع `ProtectedError` في منتصف العملية.
- كلُّ شركةٍ في `transaction.atomic()` مستقلة، و`ProtectedError` يُجمع ويُبلَّغ
  ولا يُبتلع.
- **قيودُ الشركة تُحذف معها صراحةً قبلها** (`accounting.api.purge_journals`)،
  بمعرّفات تلك الشركة وحدها. السبب: `JournalHeader.branch` على `PROTECT` إلى
  `tenants.Branch`، وحذفُ الشركة يحذف فروعها تتابعاً — فقيدٌ مربوطٌ بفرعٍ يرفع
  `ProtectedError` ولو كان القيدُ نفسُه داخل مجموعة الحذف، فيفشل حذفُ كل شركةٍ
  أصدرت مستنداً مُرحَّلاً. والقيودُ زائلةٌ مع شركتها حتماً، فحذفُها أوّلاً لا
  يُفقد شيئاً ويُنجح التذكرة. **قيودُ شركةٍ خارج القائمة لا تُمَسّ.**

**ما لا يمسّه هذا الأمر:** لا صفَّ `PracticeClient` ولا شيئاً من
`accountant_portal`، ولا ملفّاً واحداً من التخزين — مجلد Cloudinary للطبقة
القديمة (`ktra_practice_documents`) يُذكر في التحذير ولا يُحذف منه شيء.

    python manage.py purge_legacy_offices --tenant-id 16 --tenant-id 17
    python manage.py purge_legacy_offices --tenant-id 16 --tenant-id 17 \\
        --apply --confirm PURGE --backup-file /root/backups/before-291.sql
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import ProtectedError

from accounting.api import purge_journals
from tenants.models import Tenant

#: المكتبُ المحوَّل إلى الموديول الجديد لا يُحذف بهذا الأمر — حذفُه يُفقد التحويل.
PROTECTED_TEMPLATE = "accounting_office"
CONFIRM_TEXT = "PURGE"
#: مجلدُ ملفات الطبقة القديمة — يُطبع ولا يُمَسّ (صفرُ حذفٍ من التخزين).
LEGACY_FILES_FOLDER = "ktra_practice_documents"


def _office_client_count(tenant: Tenant) -> int:
    """زبائن/أوراق المكتب (موديول `accounting_office`) — صفرٌ إن لم يكن التطبيق مثبَّتاً."""
    manager = getattr(tenant, "office_clients", None)
    return 0 if manager is None else manager.count()


def _practice_client_count(tenant: Tenant) -> int:
    """زبائن بوابة المحاسب المرتبطون بهذا الدفتر (`managed_tenant`) — يُفرَّغ ربطهم
    (`SET_NULL`) ولا يُحذف أحدٌ منهم."""
    manager = getattr(tenant, "practice_clients", None)
    return 0 if manager is None else manager.count()


def _template_label(tenant: Tenant) -> str:
    return tenant.template or "general"


def _deletion_order(tenants: list[Tenant]) -> list[Tenant]:
    """الترتيب المحسوب: الدفاترُ المُدارة أوّلاً، ثم البقية (وفيها المالكون)."""
    managed_books = [tenant for tenant in tenants if tenant.managed_by_id is not None]
    rest = [tenant for tenant in tenants if tenant.managed_by_id is None]
    return managed_books + rest


def _protected_summary(error: ProtectedError) -> str:
    counts = Counter(obj.__class__.__name__ for obj in error.protected_objects)
    return "، ".join(f"{name}: {count}" for name, count in sorted(counts.items()))


#: سقفُ دورات كسر المراجع الداخلية — حارسُ حلقةٍ لا تتقارب، لا رقمٌ تشغيلي.
_MAX_PROTECT_BREAK_ATTEMPTS = 100


def _belongs_to(obj, tenant_id: int) -> bool:
    """أهذا الصفّ لهذه الشركة؟ صفٌّ بلا `tenant_id` لا يُثبت انتماءه ⇒ لا يُمَسّ."""
    return getattr(obj, "tenant_id", None) == tenant_id


def _delete_tenant_and_its_own_protectors(tenant: Tenant) -> Counter:
    """`tenant.delete()` مع حذف صفوف الشركة **نفسها** التي تمنع الحذف بـ`PROTECT`.

    المخطط هنا يستعمل `PROTECT` لحماية مرجعٍ **حيّ**: فرعٌ يحمله قيد، أو طرفٌ
    تحمله فاتورة، أو منتجٌ يحمله بند فاتورة (`SalesInvoice.customer` و
    `SalesInvoiceLine.product`). وحين تُحذف الشركة بكاملها فكلُّ هذه الصفوف
    زائلةٌ معها في المعاملة نفسها، فالمنعُ ليس حمايةً بل ترتيبَ حذفٍ مقلوب —
    فيُحذف الصفّ المانع أوّلاً ثم يُعاد الحذف.

    **حارسُ العزل:** كلُّ صفٍّ تُحذفه هذه الدالة يُثبت انتماءه للشركة بـ
    `tenant_id` مطابق. صفٌّ لشركةٍ أخرى (أو بلا `tenant_id`) يوقف الحذف
    ويُرفع `ProtectedError` كما هو — فالحذف لا يتعدّى الشركة المطلوبة أبداً.
    """
    removed: Counter = Counter()
    tenant_id = tenant.pk
    for _ in range(_MAX_PROTECT_BREAK_ATTEMPTS):
        try:
            tenant.delete()
            return removed
        except ProtectedError as error:
            blockers = [obj for obj in error.protected_objects if obj.pk is not None]
            if not blockers:
                raise
            foreign = [obj for obj in blockers if not _belongs_to(obj, tenant_id)]
            if foreign:
                raise ProtectedError(str(error), foreign) from error
            deleted_any = False
            for obj in blockers:
                if obj.pk is None:      # زال تتابعاً مع صفٍّ سابق في الموجة نفسها
                    continue
                obj.delete()
                removed[obj.__class__.__name__] += 1
                deleted_any = True
            if not deleted_any:
                raise
    raise CommandError(
        f"لم يتقارب حذف الشركة {tenant_id}: بقيت مراجعُ PROTECT داخلية بعد "
        f"{_MAX_PROTECT_BREAK_ATTEMPTS} دورة — لم يُحذف شيء (المعاملة تراجعت)."
    )


class Command(BaseCommand):
    help = (
        "معاينة أو تنفيذ حذف شركات التجربة القديمة — الدفاترُ المُدارة قبل "
        "مالكيها، بنسخةٍ احتياطية مؤكَّدة، وبلا هجرة (تذكرة #291)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id", type=int, action="append", dest="tenant_ids", metavar="ID",
            help="TenantID للشركة — قابل للتكرار",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="معاينةٌ فقط، وهي الافتراضي — لا تحذف شيئاً",
        )
        parser.add_argument(
            "--apply", action="store_true", help="نفّذ الحذف (يشترط التأكيد والنسخة)",
        )
        parser.add_argument(
            "--confirm", type=str, default=None, metavar="PURGE",
            help="تأكيدٌ حرفي: PURGE",
        )
        parser.add_argument(
            "--backup-file", type=str, default=None, metavar="PATH",
            help="مسار نسخةٍ احتياطية موجودة وغير فارغة",
        )

    def handle(self, *args, **options):
        apply_changes = self._resolve_mode(options)
        if apply_changes:
            self._assert_confirmation(options)
            self._assert_backup(options)

        tenant_ids = list(dict.fromkeys(options.get("tenant_ids") or []))
        if not tenant_ids:
            raise CommandError(
                "«--tenant-id» مطلوبٌ مرّةً واحدة على الأقل — لم تُحدَّد أيُّ شركة."
            )

        tenants = self._load_tenants(tenant_ids)
        self._refuse_ineligible(tenants, tenant_ids)
        for tenant in tenants:
            self._print_tenant(tenant)

        order = _deletion_order(tenants)
        self._print_plan(order)

        if not apply_changes:
            self.stdout.write(self.style.SUCCESS(
                "\n[معاينة فقط — لم يُحذف شيء. أضف --apply --confirm PURGE "
                "--backup-file <path> للتنفيذ.]"
            ))
            self._print_storage_warning()
            return

        self._purge(order)
        self._print_storage_warning()

    # ── الحرّاس ────────────────────────────────────────────────────────────

    def _resolve_mode(self, options) -> bool:
        apply_changes = bool(options.get("apply"))
        if apply_changes and options.get("dry_run"):
            raise CommandError(
                "لا تجمع «--dry-run» و«--apply»: المعاينةُ هي الافتراضي، "
                "و«--apply» وحده ينفّذ."
            )
        return apply_changes

    def _assert_confirmation(self, options) -> None:
        if options.get("confirm") != CONFIRM_TEXT:
            raise CommandError(
                "«--apply» يشترط «--confirm PURGE» حرفياً — لم يُؤكَّد الحذف."
            )

    def _assert_backup(self, options) -> None:
        backup_file = options.get("backup_file")
        if not backup_file:
            raise CommandError(
                "«--apply» يشترط «--backup-file <path>» لنسخةٍ احتياطية موجودة "
                "وغير فارغة — لم يُعطَ ملفّ."
            )
        path = Path(backup_file).expanduser()
        if not path.is_file():
            raise CommandError(f"ملف النسخة الاحتياطية غير موجود: {backup_file}")
        if path.stat().st_size <= 0:
            raise CommandError(
                f"ملف النسخة الاحتياطية فارغ: {backup_file} — خُذ نسخةً حقيقيةً أوّلاً."
            )

    def _load_tenants(self, tenant_ids: list[int]) -> list[Tenant]:
        tenants = {tenant.pk: tenant for tenant in Tenant.objects.filter(pk__in=tenant_ids)}
        missing = [tid for tid in tenant_ids if tid not in tenants]
        if missing:
            raise CommandError(
                "لا توجد شركة/شركات بهذه المعرّفات: "
                + "، ".join(f"TenantID={tid}" for tid in missing)
            )
        return [tenants[tid] for tid in tenant_ids]

    def _refuse_ineligible(self, tenants: list[Tenant], tenant_ids: list[int]) -> None:
        problems: list[str] = []
        for tenant in tenants:
            if tenant.template == PROTECTED_TEMPLATE:
                problems.append(
                    f"الشركة {tenant.TenantID} «{tenant.CompanyName}» قالبُها "
                    f"«{PROTECTED_TEMPLATE}» — المكتبُ المحوَّل لا يُحذف بهذا الأمر."
                )
            # مالكٌ لدفترٍ خارج القائمة: حذفه يرفع `ProtectedError` في منتصف العملية.
            outside = tenant.managed_books.exclude(pk__in=tenant_ids).order_by("TenantID")
            for book_id, book_name in outside.values_list("TenantID", "CompanyName"):
                problems.append(
                    f"الشركة {tenant.TenantID} «{tenant.CompanyName}» مالكةُ دفترٍ ليس "
                    f"في القائمة: TenantID={book_id} «{book_name}» — أضفه إلى الأمر "
                    "كي يُحذف قبل مالكه."
                )
        if problems:
            raise CommandError("\n".join(problems))

    # ── المعاينة ───────────────────────────────────────────────────────────

    def _print_tenant(self, tenant: Tenant) -> None:
        memberships = tenant.memberships.count()
        partners = tenant.partners.count()
        journals = tenant.journalheader_set.count()
        office_clients = _office_client_count(tenant)
        practice_clients = _practice_client_count(tenant)
        owned_books = list(
            tenant.managed_books.order_by("TenantID").values_list("TenantID", "CompanyName")
        )

        self.stdout.write(
            f"TenantID={tenant.TenantID} | «{tenant.CompanyName}» | "
            f"القالب: {_template_label(tenant)} | "
            f"managed_by: {'—' if tenant.managed_by_id is None else tenant.managed_by_id}"
        )
        self.stdout.write(f"   المستخدمون في عضوياتها: {memberships}")
        self.stdout.write(f"   Partner: {partners}")
        self.stdout.write(f"   JournalHeader: {journals}")
        # `JournalHeader.branch` على `PROTECT` إلى `tenants.Branch`، وحذفُ الشركة
        # يحذف فروعها تتابعاً — فقيدٌ مربوطٌ بفرعٍ يرفع `ProtectedError` ولو كان
        # القيدُ نفسُه داخل مجموعة الحذف. القيودُ تُحذف صراحةً مع شركتها في
        # `--apply`، فهذه معاينةُ ما سيُحذف لا تحذيرُ رفض.
        branch_bound = tenant.journalheader_set.filter(branch__isnull=False).count()
        self.stdout.write(
            f"   منها مربوطة بفرع: {branch_bound} — ستُحذف مع الشركة")
        self.stdout.write(f"   زبائن المكتب (accounting_office): {office_clients}")
        if owned_books:
            listed = "، ".join(f"{book_id} «{name}»" for book_id, name in owned_books)
            self.stdout.write(f"   دفاتر مُدارة تملكها: {len(owned_books)} — {listed}")
        else:
            self.stdout.write("   دفاتر مُدارة تملكها: 0")
        if practice_clients:
            self.stdout.write(
                f"   زبائن بوابة المحاسب المرتبطون (managed_tenant): {practice_clients} "
                "— يُفرَّغ ربطهم ولا يُحذف أحدٌ منهم"
            )

    def _print_plan(self, order: list[Tenant]) -> None:
        self.stdout.write("\n[خطة الحذف — بالترتيب المحسوب]:")
        for position, tenant in enumerate(order, start=1):
            if tenant.managed_by_id is not None:
                role = f"دفترٌ مُدار — يُحذف أوّلاً (مالكه {tenant.managed_by_id})"
            elif tenant.managed_books.exists():
                role = "مالكُ دفاتر — يُحذف بعد دفاتره"
            else:
                role = "شركةٌ مستقلّة"
            self.stdout.write(
                f"[خطة] {position}) TenantID={tenant.TenantID} «{tenant.CompanyName}» — {role}"
            )

    # ── التنفيذ ────────────────────────────────────────────────────────────

    def _purge(self, order: list[Tenant]) -> None:
        user_model = get_user_model()
        touched_user_ids: set[int] = set()
        failures: list[Tenant] = []

        for tenant in order:
            # `tenant.delete()` يُصفّر المفتاحَ الأساسيّ على الكائن بعد الحذف،
            # فالطباعةُ بعده تقرأ `TenantID=None` — تُلتقط التسمية قبله.
            tenant_id = tenant.TenantID
            company_name = tenant.CompanyName
            member_ids = set(tenant.memberships.values_list("user_id", flat=True))
            journal_ids = list(tenant.journalheader_set.values_list("pk", flat=True))
            try:
                # معاملةٌ مستقلّة لكل شركة: فشلُ واحدةٍ لا يُسقط البقية ولا
                # يترك نصفَ حذفٍ في القاعدة.
                with transaction.atomic():
                    # `JournalHeader.branch` على `PROTECT` إلى `tenants.Branch`،
                    # وحذفُ الشركة يحذف فروعها تتابعاً — فيرفع Django
                    # `ProtectedError` ولو كان القيدُ نفسُه داخل مجموعة الحذف.
                    # قيودُ الشركة محذوفةٌ معها حتماً، فتُحذف صراحةً أوّلاً —
                    # **بمعرّفات هذه الشركة وحدها**، فلا يُمَسّ قيدُ غيرها.
                    purge_journals(journal_ids)
                    protectors = _delete_tenant_and_its_own_protectors(tenant)
            except ProtectedError as error:
                failures.append(tenant)
                self.stdout.write(self.style.ERROR(
                    f"[فشل] TenantID={tenant_id} «{company_name}»: "
                    f"ProtectedError — {len(error.protected_objects)} صفّاً محميّاً "
                    f"({_protected_summary(error)}) — لم يُحذف شيءٌ منها."
                ))
                continue

            touched_user_ids |= member_ids
            self.stdout.write(self.style.SUCCESS(
                f"[حُذف] TenantID={tenant_id} «{company_name}»"
            ))
            self.stdout.write(f"      قيودٌ محذوفة معها: {len(journal_ids)}")
            if protectors:
                listed = "، ".join(
                    f"{name}: {count}" for name, count in sorted(protectors.items()))
                self.stdout.write(
                    f"      صفوفٌ حُذفت قبلها لأنها كانت تمنعها بـPROTECT داخلي: {listed}")

        self._print_orphan_users(user_model, touched_user_ids)

        if failures:
            raise CommandError(
                f"فشل حذف {len(failures)} من {len(order)} شركة — ProtectedError "
                "(التفاصيل أعلاه). الصفوفُ التي رفضت الحذف باقيةٌ كما هي، "
                "والبقية حُذفت."
            )

    def _print_orphan_users(self, user_model, user_ids: set[int]) -> None:
        if not user_ids:
            return
        orphans = (
            user_model.objects.filter(pk__in=user_ids, company_memberships__isnull=True)
            .order_by("pk")
        )
        orphans = list(orphans)
        if not orphans:
            return
        self.stdout.write(self.style.WARNING(
            "\n[تحذير] مستخدمون بقوا بلا أيّ شركة بعد الحذف — راجعهم قبل أن يدخلوا:"
        ))
        for user in orphans:
            full_name = user.get_full_name().strip()
            label = f"{full_name} ({user.username})" if full_name else user.username
            self.stdout.write(f"   - {label} — user_id={user.pk}")

    def _print_storage_warning(self) -> None:
        self.stdout.write(self.style.WARNING(
            f"\n[تحذير] ملفاتُ الطبقة القديمة في مجلد Cloudinary "
            f"«{LEGACY_FILES_FOLDER}» لا تُمَسّ في هذه الموجة — صفرُ حذفٍ لأيّ "
            "ملفٍّ من التخزين، ولا صفَّ `PracticeClient` ولا شيءَ من "
            "`accountant_portal`."
        ))
