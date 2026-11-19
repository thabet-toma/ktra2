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
    revert_returned_sales_serials,
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
    tenant_id, code_prefixes=None, acc_type=None, name_kw=None, *,
    allow_any_of_type=True, allow_parent=True,
):
    """أفضل حساب مطابق من شجرة الشركة: الكود، ثم النوع+الاسم، ثم أول حساب من النوع.

    `allow_any_of_type=False` يمنع الرجوع الأعمى لأول حساب من النوع (قد يكون
    حساباً رئيسياً لا يصلح للترحيل) — يُستخدم عند تعبئة الافتراضيات تلقائياً.

    `allow_parent=False` يستبعد كلّ حسابٍ **له أبناء** في هذه الشركة. تُمرَّر من
    كل مستدعٍ يقصد **هدفَ ترحيل**، لأنّ مطابقة البادئة تُرجع الأبَ نفسَه قبل
    فروعه: `code__startswith("41")` يطابق `"41"`، و`order_by("code")` يقدّمه على
    `"4102"` لأنّ الأقصر يسبق ما هو امتدادٌ له نصّياً. فشركةٌ فيها `41` بلا
    `4101` كانت تُرحِّل إيرادَ كلّ بضاعةٍ تُباع على **رأس شجرة الإيرادات**.

    ولا تُمرَّر حيث يكون الأبُ **مقصوداً**: `1103` (المدينون التجاريون) أبُ
    حسابات الزبائن، وعليه يقع ما هو «على الحساب» بلا زبونٍ بعينه — واستبعادُه
    هناك يُرجع حسابَ زبونٍ عشوائيّ، وهو أفدح ممّا نتّقيه.

    والاستبعادُ استعلامٌ فرعيٌّ واحد لا فحصٌ لكل مرشَّح (`children.exists()` في
    حلقةٍ = استعلامٌ لكل صفّ — سابقة `correlated-subquery-on-lists`).
    """
    qs = Account.objects.filter(tenant_id=tenant_id, is_active=True)
    if not allow_parent:
        parents = Account.objects.filter(
            tenant_id=tenant_id, parent__isnull=False,
        ).values("parent_id")
        qs = qs.exclude(pk__in=parents)
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
            tenant_id, ["5101"], "Expense", "تكلفة",
            allow_any_of_type=False, allow_parent=False,
        )
        if acc:
            settings_obj.default_cogs_account = acc
            filled.append("default_cogs_account")
    if settings_obj.default_inventory_account_id is None:
        acc = resolve_default_account(
            tenant_id, ["1104"], "Asset", "مخزون",
            allow_any_of_type=False, allow_parent=False,
        )
        if acc:
            settings_obj.default_inventory_account = acc
            filled.append("default_inventory_account")
    if settings_obj.default_cash_account_id is None:
        acc = resolve_default_account(
            tenant_id, ["1101", "1102", "1110"], "Asset", "صندوق",
            allow_any_of_type=False, allow_parent=False,
        )
        if acc:
            settings_obj.default_cash_account = acc
            filled.append("default_cash_account")
    if settings_obj.default_ar_account_id is None:
        # 1103 = المدينون التجاريون (أب حسابات الزبائن). القائمة القديمة كانت
        # ["1201", "1106"] — أراضٍ ودفعات موردين، لا علاقة لهما بذمم العملاء.
        # **وحدَها هنا يبقى `allow_parent` على أصله**: الأبُ مقصود، وعليه يقع ما
        # هو «على الحساب» بلا زبونٍ بعينه. استبعادُه يُرجع حسابَ زبونٍ عشوائيّ.
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


def default_cost_variance_account_code(default_cogs_account: Account | None) -> str | None:
    """كود حساب فروقات تكلفة المبيعات الافتراضي: أوّل حرفين من كود التكلفة + «90» (مثل 5190)."""
    if default_cogs_account is None:
        return None
    cogs_code = (default_cogs_account.code or "").strip()
    if len(cogs_code) < 2:
        return None
    return f"{cogs_code[:2]}90"


def cost_variance_account_error(
    account: Account | None,
    *,
    tenant_id: int,
    default_cogs_account: Account | None,
) -> str | None:
    """يتحقّق من أهلية حساب فروقات تكلفة المبيعات — يعيد رسالة عربية أو None."""
    if account is None:
        return None
    if getattr(account, "tenant_id", None) != tenant_id:
        return "حساب فروقات التكلفة يجب أن يتبع الشركة نفسها."
    if account.account_type != "Expense":
        return "حساب فروقات التكلفة يجب أن يكون من نوع مصروفات (Expense)."
    if not account.is_active:
        return "حساب فروقات التكلفة يجب أن يكون نشطاً."
    if Account.objects.filter(tenant_id=tenant_id, parent_id=account.pk).exists():
        return "حساب فروقات التكلفة يجب أن يكون حساباً فرعياً (ورقة) بلا حسابات تابعة."
    if account.nature not in (None, "", Account.NATURE_BOTH):
        return "طبيعة حساب فروقات التكلفة يجب أن تقبل المدين والدائن."
    if default_cogs_account is None:
        return "عيّن حساب تكلفة المبيعات الافتراضي أولاً قبل تحديد حساب الفروقات."
    if getattr(default_cogs_account, "tenant_id", None) != tenant_id:
        return "حساب تكلفة المبيعات الافتراضي يجب أن يتبع الشركة نفسها."
    if account.pk == default_cogs_account.pk:
        return "حساب فروقات التكلفة لا يمكن أن يكون نفس حساب تكلفة المبيعات الافتراضي."
    cogs_code = (default_cogs_account.code or "").strip()
    if len(cogs_code) < 2:
        return "عيّن حساب تكلفة مبيعات بكود صالح (حرفان على الأقل) أولاً."
    group_code = cogs_code[:2]
    acc_code = (account.code or "").strip()
    if not acc_code.startswith(group_code):
        return f"حساب فروقات التكلفة يجب أن يكون ضمن مجموعة تكلفة المبيعات (يبدأ كوده بـ {group_code})."
    return None


_MISSING_COGS_VARIANCE_ACCOUNT_ERROR = (
    "تعذّر إنشاء حساب فروقات التكلفة تلقائياً لعدم وجود حساب تكلفة مبيعات صالح؛ "
    "يرجى اختيار حساب الفروقات يدوياً."
)
COST_VARIANCE_RESOLVE_FAILED_ERROR = (
    "تعذّر إنشاء أو استخدام حساب فروقات التكلفة الافتراضي؛ "
    "يرجى اختيار حساب الفروقات يدوياً."
)


def _inspect_default_cost_variance_account(
    default_cogs_account: Account | None,
    *,
    tenant_id: int,
) -> tuple[str | None, Account | None, str | None]:
    """يفحص أهلية الحساب الافتراضي (`G+90`): يعيد `(code, existing_valid_account, error_message)`."""
    if (
        default_cogs_account is None
        or getattr(default_cogs_account, "tenant_id", None) != tenant_id
    ):
        return None, None, _MISSING_COGS_VARIANCE_ACCOUNT_ERROR
    code = default_cost_variance_account_code(default_cogs_account)
    if code is None:
        return None, None, _MISSING_COGS_VARIANCE_ACCOUNT_ERROR
    existing = Account.objects.filter(tenant_id=tenant_id, code=code).first()
    if existing is not None:
        if (
            cost_variance_account_error(
                existing, tenant_id=tenant_id, default_cogs_account=default_cogs_account,
            )
            is not None
        ):
            return (
                code,
                None,
                f"الحساب الافتراضي ({code}) موجود لكنه لا يصلح كحساب فروقات تكلفة؛ "
                "يرجى اختيار حساب الفروقات يدوياً.",
            )
        return code, existing, None
    return code, None, None


def default_cost_variance_account_error(
    default_cogs_account: Account | None,
    *,
    tenant_id: int,
) -> str | None:
    """يتحقّق من إمكانية استخدام/إنشاء حساب الفروقات الافتراضي، وإلا يعيد رسالة الاختيار اليدوي."""
    _, _, err = _inspect_default_cost_variance_account(
        default_cogs_account, tenant_id=tenant_id,
    )
    return err


def resolve_default_cost_variance_account(
    settings_obj: SalesSettings,
    *,
    default_cogs_account: Account | None = None,
) -> Account | None:
    """يُعيد (أو يُنشئ) حساب فروقات تكلفة المبيعات الافتراضي للشركة بلا تحويل ورقةٍ إلى أب.

    إن وُجد حسابٌ بالكود المطلوب في الشركة، يُعاد استعماله فقط إن استوفى كل
    قواعد الأهلية، وإلا يعود `None` دون تعديل الحساب القائم.
    """
    tenant_id = settings_obj.tenant_id
    cogs_account = (
        default_cogs_account if default_cogs_account is not None else settings_obj.default_cogs_account
    )
    if cogs_account is None or getattr(cogs_account, "tenant_id", None) != tenant_id:
        return None
    code, existing, err = _inspect_default_cost_variance_account(
        cogs_account, tenant_id=tenant_id,
    )
    if err is not None:
        return None
    if existing is not None:
        return existing

    # البذرة تضع `51` تحت `5` فيكون الأب `5`، وفي شجرةٍ تحوي `5101` تحت `51` يكون
    # الأب `51`؛ ورقة تكلفة المبيعات نفسها لا تتحوّل إلى أب أبداً.
    parent = cogs_account.parent

    account, created = Account.objects.get_or_create(
        tenant_id=tenant_id,
        code=code,
        defaults={
            "name": "فروقات أسعار البضاعة المباعة",
            "account_type": "Expense",
            "nature": None,
            "is_active": True,
            "parent": parent,
        },
    )
    # حارس ضدّ الإنشاء المتزامن لحسابٍ غير صالح بين الفحص الأول وget_or_create.
    if not created and (
        cost_variance_account_error(
            account, tenant_id=tenant_id, default_cogs_account=cogs_account,
        )
        is not None
    ):
        return None
    if created:
        logger.info(
            "sales.cost_variance_account.created tenant=%s account=%s code=%s",
            tenant_id, account.pk, code,
        )
    return account


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
        # issue #53/#59: **لا يُثبَّت حسابا إيراد المنتج ولا الخدمة هنا.** أوّل
        # حساب إيراد بالكود هو رأس الشجرة «4» في دليل الحسابات المعياري (الترتيب
        # النصّي `'4' < '41' < '4101' < '4102'`) — حسابٌ أب لا يصلح هدفاً
        # للترحيل. وتثبيتُه هنا كان يُقصِر `resolve_service_revenue_account` و
        # `resolve_product_revenue_account` (`sales/services/calc.py`) عن عملهما:
        # هما تُصرّحان بأن حالهما الطبيعي «كل شركة لم تُضبط يدوياً»، وتحلّان
        # «4101»/«4102» أو تُنشئانهما إن غابا ثم تُثبّتانهما — فلا تصلان إليهما
        # شركةٌ قطّ لأن الحقلين مملوءان سلفاً بالرأس. فيُتركان فارغين لتقوما بذلك.
        default_revenue_account_product=None,
        default_revenue_account_service=None,
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


