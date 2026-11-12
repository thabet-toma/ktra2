"""تذكرة #291 — «الانتقال»: أمران يدويّان لتحويل المكتب القديم إلى الموديول
الجديد وحذف شركات التجربة، **لا بهجرة بيانات**.

الملاحظة على الأثر في قاعدة البيانات — `tenant.template` · صفوف `TenantModule` ·
بقاءُ صفوف `Tenant` أو زوالها — لا على شكل الطباعة ولا على استدعاء الخدمة
مباشرةً. والأهم فيها: المعاينةُ الافتراضية لا تغيّر شيئاً إطلاقاً، وهو الشرط
الذي بُني عليه قرار المالك «تُرى القائمة قبل التنفيذ».
"""
import pytest
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from accounting.models import AccountingAuditLog, JournalHeader
from accounting.services import create_fiscal_year
from core.models import TenantModule
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import post_sales_invoice
from tenants.models import Currency, Tenant, UserCompanyMembership
from tenants.services import create_company

pytestmark = pytest.mark.django_db

SWITCH_COMMAND = "switch_office_to_new_module"
PURGE_COMMAND = "purge_legacy_offices"


@pytest.fixture
def creator():
    return User.objects.create_user(username="legacy-office-founder", password="x")


@pytest.fixture
def office(creator):
    """صورة المكتب 22: قالب `accounting_firm` وبلا أيّ صفّ `TenantModule`."""
    return create_company(
        "مكتب الساعة للمحاسبة والاستشارات الضريبية", creator, template="accounting_firm",
    )


@pytest.fixture
def backup_file(tmp_path):
    path = tmp_path / "ktra-before-purge.sqlite3"
    path.write_text("-- نسخةٌ احتياطية قبل الحذف\n", encoding="utf-8")
    return str(path)


def _licensed_modules(tenant):
    return set(
        TenantModule.objects.filter(tenant=tenant, enabled=True)
        .values_list("module_key", flat=True)
    )


def _lines_with(marker, output):
    return [line for line in output.splitlines() if marker in line]


def _company_with_a_posted_service_invoice(creator, name):
    """شركةٌ واقعية: زبون + خدمة + فاتورةٌ مُرحَّلةٌ **بالخدمة القائمة**
    (`post_sales_invoice`)، لا هيكلٌ ناقص.

    الخدمة تحسب القيد بـ`branch_id=invoice.branch_id`، فقيودُ الشركة مربوطةٌ
    بفرع MAIN — وهي الحالة التي كانت ترفع `ProtectedError` عند حذف الشركة
    (`JournalHeader.branch` على `PROTECT` إلى `tenants.Branch`).
    """
    tenant = create_company(name, creator)
    create_fiscal_year(tenant, 2026)
    currency = Currency.objects.filter(IsBaseCurrency=True).first()
    branch = tenant.branches.get(code="MAIN")
    customer = Partner.objects.create(
        tenant=tenant, name=f"زبون {name}", partner_type="Customer")
    service = Product.objects.create(
        tenant=tenant, sku=f"SVC-{tenant.TenantID}", name_ar="خدمة محاسبية",
        is_service=True)
    invoice = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=f"INV-{tenant.TenantID}", customer=customer,
        currency=currency, invoice_date="2026-06-15", branch=branch,
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=invoice, product=service,
        quantity=Decimal("1"), unit_price=Decimal("100.00"),
    )
    post_sales_invoice(invoice)
    return tenant, invoice


# ── ١) المعاينة لا تغيّر شيئاً — أهمُّ اختبار في التذكرة ────────────────────

def test_switch_dry_run_changes_nothing(creator, office, capsys):
    before_template = office.template
    before_tenant_count = Tenant.objects.count()

    call_command(SWITCH_COMMAND, "--tenant-id", str(office.TenantID))
    # والعلَم الصريح `--dry-run` لا يفعل أكثر من الافتراضي.
    call_command(SWITCH_COMMAND, "--tenant-id", str(office.TenantID), "--dry-run")

    office.refresh_from_db()
    assert before_template == "accounting_firm"
    assert office.template == "accounting_firm"
    assert _licensed_modules(office) == set()
    assert TenantModule.objects.filter(tenant=office).count() == 0
    assert Tenant.objects.count() == before_tenant_count
    assert AccountingAuditLog.objects.filter(tenant=office).count() == 0

    out = capsys.readouterr().out
    assert str(office.TenantID) in out
    assert office.CompanyName in out
    assert "accounting_firm" in out
    assert "accounting_office" in out
    assert "معاينة" in out


def test_switch_dry_run_says_nothing_will_change_for_a_converted_office(creator, capsys):
    """مكتبٌ على القالب الجديد ومعه ترخيصه: المعاينة تقول «لا شيء» صراحةً."""
    converted = create_company("مكتبٌ محوَّل سابقاً", creator, template="accounting_office")

    call_command(SWITCH_COMMAND, "--tenant-id", str(converted.TenantID))

    out = capsys.readouterr().out
    assert "لا شيء" in out
    converted.refresh_from_db()
    assert converted.template == "accounting_office"


# ── ٢) التنفيذ: قالبٌ + ترخيصٌ واحد، والثانية idempotent ─────────────────────

def test_switch_apply_converts_and_licenses_exactly_once(creator, office, capsys):
    call_command(SWITCH_COMMAND, "--tenant-id", str(office.TenantID), "--apply")

    office.refresh_from_db()
    assert office.template == "accounting_office"
    assert _licensed_modules(office) == {"accounting_office"}
    assert TenantModule.objects.filter(
        tenant=office, module_key="accounting_office", enabled=True).count() == 1
    # سجلُّ التدقيق يكتبه `switch_company_template` وحده — لا سطرَ ثانٍ من الأمر.
    assert AccountingAuditLog.objects.filter(
        tenant=office, action="TEMPLATE_SWITCH").count() == 1

    first_run = capsys.readouterr().out
    assert "accounting_firm → accounting_office" in first_run
    assert "حسابات مُنشأة" in first_run
    assert "أنواع دفاتر مُنشأة" in first_run

    call_command(SWITCH_COMMAND, "--tenant-id", str(office.TenantID), "--apply")

    office.refresh_from_db()
    assert office.template == "accounting_office"
    assert TenantModule.objects.filter(
        tenant=office, module_key="accounting_office").count() == 1
    assert AccountingAuditLog.objects.filter(
        tenant=office, action="TEMPLATE_SWITCH").count() == 1

    second_run = capsys.readouterr().out
    assert "تخطّي" in second_run


# ── ٣) حرّاس التحويل ────────────────────────────────────────────────────────

def test_switch_refuses_a_managed_book(creator, office):
    book = create_company("دفتر زبون", creator, template="client_book", managed_by=office)

    with pytest.raises(CommandError) as error:
        call_command(SWITCH_COMMAND, "--tenant-id", str(book.TenantID), "--apply")

    message = str(error.value)
    assert str(book.TenantID) in message
    assert "مُدار" in message
    book.refresh_from_db()
    assert book.template == "client_book"
    assert _licensed_modules(book) == {"accountant_portal"}


def test_switch_refuses_a_template_that_is_neither_firm_nor_office(creator):
    general = create_company("شركة تجارية", creator, template="general")

    with pytest.raises(CommandError) as error:
        call_command(SWITCH_COMMAND, "--tenant-id", str(general.TenantID))

    message = str(error.value)
    assert "general" in message
    assert str(general.TenantID) in message
    general.refresh_from_db()
    assert general.template == "general"


def test_switch_refuses_an_unknown_tenant(creator):
    with pytest.raises(CommandError) as error:
        call_command(SWITCH_COMMAND, "--tenant-id", "999999", "--apply")

    assert "999999" in str(error.value)


def test_switch_refuses_apply_without_a_tenant_id():
    with pytest.raises(CommandError) as error:
        call_command(SWITCH_COMMAND, "--apply")

    assert "--tenant-id" in str(error.value)


def test_both_commands_refuse_apply_and_dry_run_together(office):
    with pytest.raises(CommandError) as error:
        call_command(
            SWITCH_COMMAND, "--tenant-id", str(office.TenantID), "--apply", "--dry-run",
        )
    assert "--dry-run" in str(error.value)

    with pytest.raises(CommandError) as error:
        call_command(
            PURGE_COMMAND, "--tenant-id", str(office.TenantID), "--apply", "--dry-run",
        )
    assert "--dry-run" in str(error.value)

    office.refresh_from_db()
    assert office.template == "accounting_firm"
    assert Tenant.objects.filter(pk=office.pk).exists()


# ── ٤) حذف الدفتر المُدار قبل مالكه — بالترتيب المحسوب لا بترتيب الوسائط ─────

def test_purge_deletes_a_managed_book_before_its_owner_despite_reversed_arguments(
    creator, backup_file, capsys,
):
    owner = create_company("مكتب محاسبة قديم", creator, template="accounting_firm")
    book = create_company("دفتر زبون قديم", creator, template="client_book", managed_by=owner)

    call_command(
        PURGE_COMMAND,
        "--tenant-id", str(owner.TenantID),   # ترتيبٌ معكوسٌ عمداً
        "--tenant-id", str(book.TenantID),
        "--apply",
        "--confirm", "PURGE",
        "--backup-file", backup_file,
    )

    assert not Tenant.objects.filter(pk__in=[owner.pk, book.pk]).exists()

    out = capsys.readouterr().out
    assert not _lines_with("[فشل]", out)
    deleted = _lines_with("[حُذف]", out)
    assert len(deleted) == 2, out
    assert str(book.TenantID) in deleted[0]
    assert str(owner.TenantID) in deleted[1]


# ── ٥) حرّاس `--apply`: التأكيد والنسخة الاحتياطية ──────────────────────────

def test_purge_apply_refuses_without_the_literal_confirm(office, backup_file):
    with pytest.raises(CommandError) as error:
        call_command(
            PURGE_COMMAND, "--tenant-id", str(office.TenantID),
            "--apply", "--backup-file", backup_file,
        )

    assert "PURGE" in str(error.value)
    assert Tenant.objects.filter(pk=office.pk).exists()


def test_purge_apply_refuses_without_a_backup_file(office):
    with pytest.raises(CommandError) as error:
        call_command(
            PURGE_COMMAND, "--tenant-id", str(office.TenantID),
            "--apply", "--confirm", "PURGE",
        )

    assert "--backup-file" in str(error.value)
    assert Tenant.objects.filter(pk=office.pk).exists()


def test_purge_apply_refuses_a_missing_or_empty_backup_file(office, tmp_path):
    with pytest.raises(CommandError) as error:
        call_command(
            PURGE_COMMAND, "--tenant-id", str(office.TenantID),
            "--apply", "--confirm", "PURGE",
            "--backup-file", str(tmp_path / "does-not-exist.sqlite3"),
        )
    assert "does-not-exist.sqlite3" in str(error.value)

    empty = tmp_path / "empty.sqlite3"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(CommandError) as error:
        call_command(
            PURGE_COMMAND, "--tenant-id", str(office.TenantID),
            "--apply", "--confirm", "PURGE", "--backup-file", str(empty),
        )
    assert "empty.sqlite3" in str(error.value)

    assert Tenant.objects.filter(pk=office.pk).exists()


# ── ٦) المكتبُ المحوَّل لا يُحذف ─────────────────────────────────────────────

def test_purge_refuses_a_company_whose_template_is_accounting_office(creator, backup_file):
    converted = create_company("مكتب الساعة المحوَّل", creator, template="accounting_office")

    with pytest.raises(CommandError) as error:
        call_command(
            PURGE_COMMAND, "--tenant-id", str(converted.TenantID),
            "--apply", "--confirm", "PURGE", "--backup-file", backup_file,
        )

    message = str(error.value)
    assert str(converted.TenantID) in message
    assert "accounting_office" in message
    assert Tenant.objects.filter(pk=converted.pk).exists()


# ── ٧) مالكُ دفترٍ خارج القائمة يُرفض برسالةٍ تسمّي الدفتر ───────────────────

def test_purge_refuses_an_owner_whose_managed_book_is_outside_the_list(
    creator, backup_file,
):
    owner = create_company("مكتبٌ يملك دفتراً", creator, template="accounting_firm")
    book = create_company("دفتر خارج القائمة", creator, template="client_book", managed_by=owner)

    with pytest.raises(CommandError) as error:
        call_command(
            PURGE_COMMAND, "--tenant-id", str(owner.TenantID),
            "--apply", "--confirm", "PURGE", "--backup-file", backup_file,
        )

    message = str(error.value)
    assert book.CompanyName in message
    assert str(book.TenantID) in message
    assert Tenant.objects.filter(pk=owner.pk).exists()


# ── معاينة الحذف: تُرى الخطة، ولا يُحذف شيء ─────────────────────────────────

def test_purge_dry_run_deletes_nothing_and_prints_the_plan(creator, office, capsys):
    book = create_company("دفترٌ سيُحذف", creator, template="client_book", managed_by=office)
    before_tenant_count = Tenant.objects.count()

    call_command(
        PURGE_COMMAND,
        "--tenant-id", str(office.TenantID),
        "--tenant-id", str(book.TenantID),
    )

    assert Tenant.objects.count() == before_tenant_count
    assert Tenant.objects.filter(pk__in=[office.pk, book.pk]).count() == 2

    out = capsys.readouterr().out
    assert str(office.TenantID) in out
    assert str(book.TenantID) in out
    assert "خطة" in out
    assert "معاينة" in out
    assert "ktra_practice_documents" in out


# ── شركةٌ واقعيةٌ بقيودٍ مربوطةٍ بفرع: تُحذف هي وقيودُها ────────────────────

def test_purge_deletes_a_real_company_with_its_branch_bound_journals(
    creator, backup_file, capsys,
):
    """`JournalHeader.branch` على `PROTECT` إلى `tenants.Branch`، وحذفُ الشركة
    يحذف فروعها تتابعاً — فشركةٌ لها قيدٌ مربوطٌ بفرع كانت ترفع `ProtectedError`
    ولا تُحذف أبداً. القيودُ محذوفةٌ مع شركتها حتماً، فحذفُها صراحةً أوّلاً لا
    يُفقد شيئاً ويُنجح التذكرة."""
    tenant, invoice = _company_with_a_posted_service_invoice(
        creator, "شركة تجربة بفاتورة مُرحَّلة")
    journal_ids = set(tenant.journalheader_set.values_list("pk", flat=True))
    assert journal_ids, "الخدمة لم تكتب قيداً — الاختبار لا يحرس شيئاً."
    assert tenant.journalheader_set.filter(branch__isnull=False).count() == len(journal_ids)

    # المعاينة تقول إنها ستُحذف مع الشركة، لا إن الحذف سيُرفض.
    call_command(PURGE_COMMAND, "--tenant-id", str(tenant.TenantID))
    preview = capsys.readouterr().out
    assert f"JournalHeader: {len(journal_ids)}" in preview
    assert f"منها مربوطة بفرع: {len(journal_ids)}" in preview
    assert "ستُحذف مع الشركة" in preview
    assert "سيُرفض" not in preview
    assert Tenant.objects.filter(pk=tenant.pk).exists()

    call_command(
        PURGE_COMMAND, "--tenant-id", str(tenant.TenantID),
        "--apply", "--confirm", "PURGE", "--backup-file", backup_file,
    )

    assert not Tenant.objects.filter(pk=tenant.pk).exists()
    assert not JournalHeader.objects.filter(pk__in=journal_ids).exists()
    assert not SalesInvoice.objects.filter(pk=invoice.pk).exists()

    out = capsys.readouterr().out
    assert not _lines_with("[فشل]", out), out
    assert f"قيودٌ محذوفة معها: {len(journal_ids)}" in out


def test_purge_leaves_a_company_outside_the_list_and_its_journals_untouched(
    creator, backup_file,
):
    """شركةٌ خارج القائمة لها قيدٌ مُرحَّل: تبقى هي وقيدُها — الحذفُ لا يتعدّى
    الشركات المطلوبة."""
    purged, _ = _company_with_a_posted_service_invoice(creator, "شركة التجربة")
    outside, _ = _company_with_a_posted_service_invoice(creator, "شركة الإنتاج")
    outside_journals = set(outside.journalheader_set.values_list("pk", flat=True))
    assert outside_journals

    call_command(
        PURGE_COMMAND, "--tenant-id", str(purged.TenantID),
        "--apply", "--confirm", "PURGE", "--backup-file", backup_file,
    )

    assert not Tenant.objects.filter(pk=purged.pk).exists()
    assert Tenant.objects.filter(pk=outside.pk).exists()
    assert JournalHeader.objects.filter(pk__in=outside_journals).count() == len(outside_journals)
    assert outside.journalheader_set.filter(branch__isnull=False).exists()


# ── `ProtectedError` يُبلَّغ ولا يُبتلع ──────────────────────────────────────

def test_purge_reports_a_protected_error_and_rolls_that_company_back(
    creator, backup_file, capsys,
):
    """قيدُ شركةٍ **خارج القائمة** يشير إلى فرعِ شركةٍ داخلها (حالةُ تلفِ بيانات):
    حذفُ الفرع يرفع `ProtectedError`. الأمر يُبلّغ ولا يبتلع، ويُبقي الشركة —
    ولا يحذف قيدَ الغيرِ ولو كان هو المانع."""
    victim = create_company("شركة تُحذف", creator)
    outsider = create_company("شركة خارج القائمة", creator)
    stray = JournalHeader.objects.create(
        tenant=outsider, branch=victim.branches.get(code="MAIN"),
        transaction_date="2026-01-01",
    )

    with pytest.raises(CommandError) as error:
        call_command(
            PURGE_COMMAND, "--tenant-id", str(victim.TenantID),
            "--apply", "--confirm", "PURGE", "--backup-file", backup_file,
        )

    assert "ProtectedError" in str(error.value)
    assert Tenant.objects.filter(pk=victim.pk).exists()
    assert JournalHeader.objects.filter(pk=stray.pk).exists()

    out = capsys.readouterr().out
    failed = _lines_with("[فشل]", out)
    assert len(failed) == 1, out
    assert "ProtectedError" in failed[0]


# ── ما بعد الحذف: المستخدمون بلا شركة، والملفات لا تُمَسّ ────────────────────

def test_purge_warns_about_users_left_without_any_company(creator, office, backup_file, capsys):
    ghost = User.objects.create_user(
        username="ghost-user-291", password="x", first_name="شبح", last_name="٢٩١",
    )
    UserCompanyMembership.objects.create(user=ghost, tenant=office, role="staff")

    call_command(
        PURGE_COMMAND, "--tenant-id", str(office.TenantID),
        "--apply", "--confirm", "PURGE", "--backup-file", backup_file,
    )

    assert not Tenant.objects.filter(pk=office.pk).exists()
    out = capsys.readouterr().out
    assert "ghost-user-291" in out
    assert str(ghost.pk) in out
    assert "ktra_practice_documents" in out
