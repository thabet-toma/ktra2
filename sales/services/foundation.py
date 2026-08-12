"""
ترحيل فواتير المبيعات، حركة المخزون، وتحصيل العملاء.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum

from accounting.models import Account, JournalLine
from accounting.services import (
    convert_amount,
    create_audit_log,
    post_journal,
    resolve_forex_account,
    unpost_document,
    validate_fiscal_period,
    validate_journal_entry,
)
from inventory.models import Product, StockMovement
from inventory.serials import (
    consume_sales_serials,
    release_sales_serials,
    restore_returned_sales_serials,
)
from inventory.services import record_stock_movement
from partners.models import Partner, PartnerGroup
from accounting.api import ensure_partner_account
from tenants.models import Tenant

from sales.models import (
    CreditDebitNote,
    CustomerPayment,
    DeliveryOrder,
    DeliveryOrderLine,
    PaymentAllocation,
    SalesInvoice,
    SalesInvoiceLine,
    SalesSettings,
)
from django.utils import timezone

logger = logging.getLogger("sales.services")

DEC = Decimal("0.01")



def get_or_create_default_customer(tenant) -> Partner:
    """يُعيد (أو يُنشئ) العميل الافتراضي «الزبون العام» لشركة معيّنة.

    - name = "الزبون العام"
    - partner_type = Customer
    - لا يُخصَّص له credit_limit
    """
    tenant_id = getattr(tenant, "TenantID", tenant)
    existing = (
        Partner.objects.filter(
            tenant_id=tenant_id,
            partner_type="Customer",
            name__in=["الزبون العام", "العميل الافتراضي", "General Customer", "Cash Customer"],
        )
        .order_by("id")
        .first()
    )
    if existing:
        return existing
    # إنشاء مجموعة افتراضية إن لم تكن موجودة
    group = (
        PartnerGroup.objects.filter(
            tenant_id=tenant_id, group_type="Customer"
        )
        .order_by("id")
        .first()
    )
    if not group:
        group = PartnerGroup.objects.create(
            tenant_id=tenant_id, name="عملاء عامون", group_type="Customer"
        )
    return Partner.objects.create(
        tenant_id=tenant_id,
        name="الزبون العام",
        legal_name="الزبون العام",
        partner_type="Customer",
        group=group,
    )


def resolve_default_account(
    tenant_id, code_prefixes=None, acc_type=None, name_kw=None, *, allow_any_of_type=True
):
    """أفضل حساب مطابق من شجرة الشركة: الكود، ثم النوع+الاسم، ثم أول حساب من النوع.

    `allow_any_of_type=False` يمنع الرجوع الأعمى لأول حساب من النوع (قد يكون
    حساباً رئيسياً لا يصلح للترحيل) — يُستخدم عند تعبئة الافتراضيات تلقائياً.
    """
    qs = Account.objects.filter(tenant_id=tenant_id, is_active=True)
    for cp in (code_prefixes or []):
        hit = qs.filter(code__startswith=cp).order_by("code").first()
        if hit:
            return hit
    if acc_type:
        typed = qs.filter(account_type=acc_type)
        if name_kw:
            hit = typed.filter(name__icontains=name_kw).order_by("code").first()
            if hit:
                return hit
        if allow_any_of_type:
            return typed.order_by("code").first()
    return None


def _fill_missing_default_accounts(settings_obj: SalesSettings, tenant_id) -> list[str]:
    """يملأ الحسابات الافتراضية الفارغة من الشجرة — يعيد الحقول المعدّلة.

    تركها NULL كان يوقف ترحيل أي فاتورة مبيعات في شركة جديدة برسالة «عيّن حساب
    تكلفة المبيعات والمخزون…»، مع أن شجرة الحسابات القياسية تحوي الحسابات أصلاً.
    T-DEFACC: الصندوق والذمم انضمّا للقائمة — كانا يبقيان فارغين فيُجبَر المستخدم
    على اختيار الصندوق يدوياً في كل سند.
    """
    filled: list[str] = []
    if settings_obj.default_cogs_account_id is None:
        acc = resolve_default_account(
            tenant_id, ["5101", "51"], "Expense", "تكلفة", allow_any_of_type=False
        )
        if acc:
            settings_obj.default_cogs_account = acc
            filled.append("default_cogs_account")
    if settings_obj.default_inventory_account_id is None:
        acc = resolve_default_account(
            tenant_id, ["1104"], "Asset", "مخزون", allow_any_of_type=False
        )
        if acc:
            settings_obj.default_inventory_account = acc
            filled.append("default_inventory_account")
    if settings_obj.default_cash_account_id is None:
        acc = resolve_default_account(
            tenant_id, ["1101", "1102", "1110"], "Asset", "صندوق", allow_any_of_type=False
        )
        if acc:
            settings_obj.default_cash_account = acc
            filled.append("default_cash_account")
    if settings_obj.default_ar_account_id is None:
        # 1103 = المدينون التجاريون (أب حسابات الزبائن). القائمة القديمة كانت
        # ["1201", "1106"] — أراضٍ ودفعات موردين، لا علاقة لهما بذمم العملاء.
        acc = resolve_default_account(
            tenant_id, ["1103"], "Asset", "مدينون", allow_any_of_type=False
        )
        if acc:
            settings_obj.default_ar_account = acc
            filled.append("default_ar_account")
    if filled:
        logger.info(
            "sales.settings.defaults_filled tenant=%s fields=%s", tenant_id, filled,
        )
    return filled


def get_or_create_sales_settings(tenant) -> SalesSettings:
    """يُعيد (أو يُنشئ) إعدادات المبيعات للشركة، ويضبط قيمًا افتراضية ذكية."""
    tenant_id = getattr(tenant, "TenantID", tenant)
    settings_obj = SalesSettings.objects.filter(tenant_id=tenant_id).first()
    if settings_obj:
        updates: list[str] = []
        # تأكد أن العميل الافتراضي موجود
        if settings_obj.default_customer_id is None:
            settings_obj.default_customer = get_or_create_default_customer(tenant_id)
            updates.append("default_customer")
        updates += _fill_missing_default_accounts(settings_obj, tenant_id)
        if updates:
            settings_obj.save(update_fields=updates)
        return settings_obj

    default_customer = get_or_create_default_customer(tenant_id)

    # محاولة استنتاج عملة أساسية
    default_currency = None
    try:
        from tenants.models import Currency
        default_currency = (
            Currency.objects.filter(IsBaseCurrency=True).order_by("CurrencyID").first()
            or Currency.objects.order_by("CurrencyID").first()
        )
    except (Currency.DoesNotExist, Currency.MultipleObjectsReturned):
        default_currency = None

    # محاولة استنتاج حساب إيرادات افتراضي
    default_rev = (
        Account.objects.filter(
            tenant_id=tenant_id, account_type="Revenue", is_active=True
        )
        .order_by("code")
        .first()
    )

    # ضريبة VAT افتراضية
    default_vat = None
    try:
        from accounting.models import TaxRate
        default_vat = (
            TaxRate.objects.filter(tenant_id=tenant_id, is_active=True)
            .filter(direction__in=["sales", "both", "output"])
            .order_by("id")
            .first()
            or TaxRate.objects.filter(tenant_id=tenant_id, is_active=True).order_by("id").first()
        )
    except (TaxRate.DoesNotExist, TaxRate.MultipleObjectsReturned):
        default_vat = None

    settings_obj = SalesSettings.objects.create(
        tenant_id=tenant_id,
        default_customer=default_customer,
        default_currency=default_currency,
        default_revenue_account_product=default_rev,
        default_revenue_account_service=default_rev,
        default_vat_rate=default_vat,
    )
    filled = _fill_missing_default_accounts(settings_obj, tenant_id)
    if filled:
        settings_obj.save(update_fields=filled)
    return settings_obj


def dormant_customers(*, tenant_id: int, days: int | None = None) -> list[dict]:
    """T-DORMANT: العملاء الذين توقّفوا عن الشراء منذ `days` يوماً أو أكثر.

    «حركة العميل» تُشتقّ من فواتير البيع **المرحّلة** وحدها (لا مسودات ولا مراجع
    بيع) — لا مخزن حركات موازٍ، فالنتيجة تتصالح دائماً مع دفتر المبيعات.
    من لم يشترِ قطّ لا يُعدّ «مختفياً» (لم يكن حاضراً أصلاً)، ومن انتهى تعامله
    (`end_of_dealing_date` حلّ) مستثنى — توقّفه معروف لا مفاجئ.
    `days=None` ⇒ العتبة من إعدادات المبيعات
    (`dormant_customer_days`)، و0 يعطّل التنبيه فتُعاد قائمة فارغة.

    يُعاد [{partner_id, partner_name, last_sale_date, last_invoice_number,
    days_since}] مرتّباً بالأطول صمتاً أولاً — يستهلكه مولّد إشعارات الموقع.
    """
    from datetime import date, timedelta

    from django.db.models import Max

    if days is None:
        days = get_or_create_sales_settings(tenant_id).dormant_customer_days
    days = int(days or 0)
    if days <= 0:
        logger.info("dormant_customers tenant=%s disabled (days=0)", tenant_id)
        return []

    today = timezone.localdate()
    cutoff = today - timedelta(days=days)
    latest = (
        SalesInvoice.objects.filter(
            tenant_id=tenant_id,
            status=SalesInvoice.STATUS_POSTED,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
        )
        .exclude(customer__end_of_dealing_date__lte=today)
        .values("customer_id", "customer__name")
        .annotate(last_sale_date=Max("invoice_date"))
        .filter(last_sale_date__lte=cutoff)
        .order_by("last_sale_date")
    )

    rows: list[dict] = []
    for entry in latest:
        last_date = entry["last_sale_date"]
        # رقم آخر فاتورة — للعرض داخل الإشعار (لا يُستعلم إلا للمختفين فعلاً).
        last_number = (
            SalesInvoice.objects.filter(
                tenant_id=tenant_id,
                customer_id=entry["customer_id"],
                status=SalesInvoice.STATUS_POSTED,
                invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
                invoice_date=last_date,
            )
            .order_by("-id")
            .values_list("invoice_number", flat=True)
            .first()
        )
        rows.append(
            {
                "partner_id": entry["customer_id"],
                "partner_name": entry["customer__name"],
                "last_sale_date": last_date.isoformat(),
                "last_invoice_number": last_number,
                "days_since": (today - last_date).days,
            }
        )

    logger.info(
        "dormant_customers tenant=%s days=%s -> %s customers",
        tenant_id, days, len(rows),
    )
    return rows


