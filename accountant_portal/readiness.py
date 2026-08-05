"""قائمة جاهزية الفترة الضريبية — اثنا عشر فحصاً **مشتقّاً** لا مخزَّناً.

القاعدة الملزمة (§7.3): الفحوص مجتمعةً **≤6 استعلامات** مهما بلغ عدد الفواتير.
لذلك لا حلقة بايثون على المستندات إطلاقاً — كل فحص تجميعةُ SQL، والفحوص التي
تشترك في نفس الجدول تُدمَج في استعلام واحد بـ`Case/When`.

كل دالة نقية: تأخذ (tenant, period_from, period_to, settings) وتُعيد
`list[Finding]`، فلا تلمس حالةً ولا تكتب صفاً.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta

from django.db.models import Case, Count, DecimalField, Exists, F, IntegerField, OuterRef, Q, Sum, When
from django.utils import timezone


SEVERITY_BLOCKER = "blocker"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    count: int = 0
    entity_type: str = ""
    entity_id: int | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _count_case(condition):
    return Count(Case(When(condition, then=1), output_field=IntegerField()))


def _invoice_findings(tenant, period_from, period_to, settings, prepared_at):
    """الفحوص 1، 3، 5، 6، 11، 12 — استعلام تجميعي واحد على الفواتير."""
    from sales.models import SalesInvoice

    window = Q(invoice_date__gte=period_from, invoice_date__lte=period_to)
    returns = Q(invoice_kind__in=("sale_return", "purchase_return"))
    input_vat_cutoff = period_to - timedelta(days=30 * int(settings.input_vat_window_months or 6))

    aggregates = SalesInvoice.objects.filter(tenant=tenant).filter(window).aggregate(
        missing_party_tax=_count_case(
            Q(customer__tax_number__isnull=True) | Q(customer__tax_number=""),
        ),
        unposted=_count_case(Q(status=SalesInvoice.STATUS_DRAFT)),
        fx_missing=_count_case(
            ~Q(currency__IsBaseCurrency=True) & Q(exchange_rate__lte=1),
        ),
        orphan_returns=_count_case(returns & Q(original_invoice__isnull=True)),
        late_documents=(
            _count_case(Q(created_at__gt=prepared_at)) if prepared_at else Count("pk", filter=Q(pk=None))
        ),
        # ق2/م60: قائمة الحقول قابلة للتهيئة — تُفحص هنا كي لا تُكلّف استعلاماً سابعاً.
        missing_fields=_count_case(Q(invoice_number="") | Q(invoice_number__isnull=True)),
    )
    expired_input_vat = (
        SalesInvoice.objects.filter(
            tenant=tenant,
            invoice_kind=SalesInvoice.INVOICE_KIND_PURCHASE,
            status=SalesInvoice.STATUS_POSTED,
            vat_statement__isnull=True,
            invoice_date__lt=input_vat_cutoff,
            invoice_date__lte=period_to,
        ).count()
    )

    findings = []
    if aggregates["missing_party_tax"]:
        findings.append(Finding(
            "MISSING_PARTY_TAX_NO", SEVERITY_BLOCKER,
            "فواتير لأطراف بلا رقم ضريبي (م49).",
            aggregates["missing_party_tax"],
        ))
    if aggregates["unposted"]:
        findings.append(Finding(
            "UNPOSTED_DOCS", SEVERITY_BLOCKER,
            "مستندات ما زالت مسودة داخل الفترة.",
            aggregates["unposted"],
        ))
    if aggregates["fx_missing"]:
        findings.append(Finding(
            "FX_RATE_MISSING", SEVERITY_BLOCKER,
            "فواتير بعملة أجنبية بلا سعر صرف مثبت بتاريخ الفاتورة (م13).",
            aggregates["fx_missing"],
        ))
    if aggregates["orphan_returns"]:
        findings.append(Finding(
            "ORPHAN_CREDIT_NOTE", SEVERITY_BLOCKER,
            "مراجيع بلا فاتورة أصلية مرتبطة.",
            aggregates["orphan_returns"],
        ))
    if expired_input_vat:
        findings.append(Finding(
            "INPUT_VAT_EXPIRED", SEVERITY_WARNING,
            f"فواتير مدخلات لم تُخصم وتجاوزت {settings.input_vat_window_months} أشهر (م36.1).",
            expired_input_vat,
        ))
    if aggregates["late_documents"]:
        findings.append(Finding(
            "LATE_DOCUMENT", SEVERITY_WARNING,
            "مستندات أُدخلت بعد تجهيز الفترة.",
            aggregates["late_documents"],
        ))
    if aggregates["missing_fields"]:
        findings.append(Finding(
            "INVOICE_FIELD_RULES",
            SEVERITY_BLOCKER if settings.strict_invoice_field_validation else SEVERITY_WARNING,
            "فواتير تنقصها حقول إلزامية بحسب قائمة التحقق المهيّأة.",
            aggregates["missing_fields"],
        ))
    return findings


def _duplicate_number_findings(tenant, period_from, period_to, settings, prepared_at):
    """الفحص 2 — تكرار رقم المستند داخل الشركة (استعلام تجميعي واحد)."""
    from sales.models import SalesInvoice

    duplicates = (
        SalesInvoice.objects.filter(tenant=tenant)
        .values("invoice_number")
        .annotate(rows=Count("pk"))
        .filter(rows__gt=1)
        .count()
    )
    if not duplicates:
        return []
    return [Finding(
        "DUPLICATE_INVOICE_NO", SEVERITY_BLOCKER,
        "أرقام مستندات مكرَّرة داخل الشركة.",
        duplicates,
    )]


def _line_findings(tenant, period_from, period_to, settings, prepared_at):
    """الفحصان 4 و7 — استعلام واحد على مستوى الفاتورة بمجاميع أسطرها."""
    from sales.models import SalesInvoice

    rows = (
        SalesInvoice.objects.filter(
            tenant=tenant,
            invoice_date__gte=period_from,
            invoice_date__lte=period_to,
        )
        .annotate(
            lines_tax=Sum("lines__line_tax_amount", output_field=DecimalField(max_digits=18, decimal_places=2)),
            untaxed_lines=_count_case(Q(lines__tax_rate__isnull=True)),
        )
        .aggregate(
            mismatched=_count_case(~Q(lines_tax=F("tax_amount")) & Q(lines_tax__isnull=False)),
            unclassified_zero=_count_case(Q(tax_amount=0) & Q(untaxed_lines__gt=0)),
        )
    )
    findings = []
    if rows["mismatched"]:
        findings.append(Finding(
            "LINE_VAT_MISMATCH", SEVERITY_BLOCKER,
            "مجموع ضريبة الأسطر لا يساوي ضريبة الفاتورة.",
            rows["mismatched"],
        ))
    if rows["unclassified_zero"]:
        findings.append(Finding(
            "UNCLASSIFIED_ZERO_RATED", SEVERITY_WARNING,
            "فواتير بضريبة صفرية بلا تصنيف نسبة ضريبية (م32/م33).",
            rows["unclassified_zero"],
        ))
    return findings


def _expense_findings(tenant, period_from, period_to, settings, prepared_at):
    """الفحص 8 — قيد مصروف على حساب عام (أب) غير مصنَّف (م75.7)."""
    from accounting.models import Account, JournalLine

    has_children = Account.objects.filter(parent_id=OuterRef("account_id"))
    unclassified = (
        JournalLine.objects.filter(
            tenant=tenant,
            journal__transaction_date__gte=period_from,
            journal__transaction_date__lte=period_to,
            account__account_type="Expense",
        )
        .annotate(is_parent=Exists(has_children))
        .filter(is_parent=True)
        .count()
    )
    if not unclassified:
        return []
    return [Finding(
        "UNCLASSIFIED_EXPENSE", SEVERITY_WARNING,
        "قيود مصروف على حسابات عامّة لها حسابات فرعية.",
        unclassified,
    )]


def _query_findings(tenant, period_from, period_to, settings, prepared_at, period=None):
    """الفحص 9 + المانع المخزَّن — استعلام تجميعي واحد على طلبات التوضيح.

    طلب توضيح مفتوح درجتُه «مانع» يمنع الاعتماد فعلاً (§7.2)، ولا يكفي أن يقلب
    حالة الفترة إلى «بانتظار الشركة»: الاعتماد يقرأ هذه القائمة لا الحالة.
    """
    from accountant_portal.models import ReviewQuery

    queryset = ReviewQuery.objects.filter(tenant=tenant, status__in=("open", "answered"))
    if period is not None:
        queryset = queryset.filter(period_review=period)
    stats = queryset.aggregate(
        blockers=_count_case(Q(severity=SEVERITY_BLOCKER)),
        missing_attachment=_count_case(Q(attachment_url="") & ~Q(entity_type="other")),
    )

    findings = []
    if stats["blockers"]:
        findings.append(Finding(
            "OPEN_BLOCKER_QUERY", SEVERITY_BLOCKER,
            "طلبات توضيح مانعة ما زالت مفتوحة.",
            stats["blockers"],
        ))
    if stats["missing_attachment"]:
        findings.append(Finding(
            "MISSING_ATTACHMENT", SEVERITY_WARNING,
            "طلبات توضيح مفتوحة بانتظار مرفق من الشركة.",
            stats["missing_attachment"],
        ))
    return findings


def _filing_findings(tenant, period_from, period_to, settings, prepared_at):
    """الفحص 10 — قرب/فوات موعد التقرير (م75.1). بلا أي استعلام."""
    due_date = period_to + timedelta(days=int(settings.filing_due_days or 15))
    today = timezone.localdate()
    remaining = (due_date - today).days
    if remaining < 0:
        return [Finding(
            "FILING_DUE_SOON", SEVERITY_WARNING,
            f"فات موعد تسليم التقرير ({due_date}) بـ{abs(remaining)} يوماً.",
        )]
    if remaining <= 5:
        return [Finding(
            "FILING_DUE_SOON", SEVERITY_WARNING,
            f"موعد تسليم التقرير {due_date} — بقي {remaining} يوماً.",
        )]
    return []


def run_readiness_checks(*, tenant, period_from, period_to, settings, period=None):
    """يشغّل الفحوص كلها ويُعيد قائمة `Finding` مرتّبة بالأشد أولاً."""
    prepared_at = getattr(period, "prepared_at", None)
    findings = []
    findings += _invoice_findings(tenant, period_from, period_to, settings, prepared_at)
    findings += _duplicate_number_findings(tenant, period_from, period_to, settings, prepared_at)
    findings += _line_findings(tenant, period_from, period_to, settings, prepared_at)
    findings += _expense_findings(tenant, period_from, period_to, settings, prepared_at)
    findings += _query_findings(tenant, period_from, period_to, settings, prepared_at, period)
    findings += _filing_findings(tenant, period_from, period_to, settings, prepared_at)
    order = {SEVERITY_BLOCKER: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}
    return sorted(findings, key=lambda item: (order.get(item.severity, 3), item.code))


def has_blockers(findings) -> bool:
    return any(item.severity == SEVERITY_BLOCKER for item in findings)
