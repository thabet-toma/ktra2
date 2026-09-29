"""أمر الصيانة — دورة الحالة، ومال قطع الغيار (THA-24 م3).

ثلاث قواعد تحكم هذا الملف، وكل سطر فيه خادمٌ لها:

1. **البند يتجسّد في مستند واحد بالضبط.** `materialized_at` قفلٌ يُوضَع لحظة
   التجسّد، ومسارا التجسّد يلتقطان غير المقفول من نوعهما وحده: الترحيل يلتقط
   `covered` غير المرحّل، والفوترة تلتقط `billable` غير المفوتر. الخصم المزدوج
   ممنوع **بالبناء** لا بالانضباط (THA-65 وقع حين تعدّد مسارا الصرف لنفس البند).
2. **مصروف الكفالة ليس تكلفة مبيع.** حركته `SERVICE_ISSUE` — نوعٌ لا تراه
   `sales_cogs_map` (تفلتر `SALE`/`STOCK_ISSUE`)، فلا يلوّث ربح أي فاتورة، وهو
   الصواب محاسبياً: مصروف تشغيلي لا COGS.
3. **القطعة المفوترة تمرّ في فاتورة البيع القائمة** بمسار `SALE` المجرَّب — لا
   مسار صرفٍ موازٍ. وبند الأجرة منتج خدمة فيقع إيراده في «إيرادات الخدمات»
   بحكم البناء (`_resolve_revenue_account_for_line`)، لا بالاتفاق.

الكتابة المحاسبية كلها عبر `accounting.api` — الواجهة العامة الوحيدة (المرحلة 2).
"""
import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounting.api import ensure_account, post_document, unpost_document, validate_fiscal_period
from core.modules import module_enabled
from inventory.serials import assert_issue_serials_declared, issue_serials, unissue_serials
from inventory.services import product_display_name, record_stock_movement

from .models import (
    PHONE_KEY_LENGTH,
    ServiceOrder,
    ServiceOrderEvent,
    ServiceOrderPart,
    WarrantyCard,
    looks_like_phone,
    phone_digits,
    phone_key_of,
)
from .services import MODULE_KEY, get_or_create_after_sales_settings, warranty_coverage

logger = logging.getLogger(__name__)

# نوع مرجع القيد — مستقل عن أي مستند آخر، فمرجعه لا يتقاطع مع فضاء معرّفاته.
JOURNAL_REF_WARRANTY_PARTS = "SERVICE_WARRANTY_PARTS"
# نوع حركة المخزون (`inventory.StockMovement.REFERENCE_TYPES`).
STOCK_REF_SERVICE_ISSUE = "SERVICE_ISSUE"

WARRANTY_EXPENSE_CODE = "5206"
WARRANTY_EXPENSE_NAME = "مصاريف صيانة الكفالة"
OPERATING_EXPENSES_CODE = "52"

LABOUR_PRODUCT_SKU = "SRV-REPAIR"
LABOUR_PRODUCT_NAME = "أجرة صيانة"

DEC = Decimal("0.01")


# ══════════════════════════════════════════════════════════════════════════
# الافتراضيات المثبَّتة — تُنشأ من الكود ولا تُردّ استفساراً على المستخدم
# ══════════════════════════════════════════════════════════════════════════

def resolve_warranty_expense_account(tenant_id: int):
    """حساب «مصاريف صيانة الكفالة» — يُطابَق أو يُنشأ تحت المصاريف التشغيلية.

    يُثبَّت في `AfterSalesSettings` بعد أول حلّ، فلا يُنشأ حسابٌ ثانٍ في المرة
    التالية ولو غيّر المستخدم اسمه.
    """
    settings_row = get_or_create_after_sales_settings(tenant_id)
    if settings_row.warranty_expense_account_id:
        return settings_row.warranty_expense_account

    account = ensure_account(
        tenant_id=tenant_id,
        code=WARRANTY_EXPENSE_CODE,
        name=WARRANTY_EXPENSE_NAME,
        account_type="Expense",
        parent_code=OPERATING_EXPENSES_CODE,
    )
    settings_row.warranty_expense_account = account
    settings_row.save(update_fields=["warranty_expense_account", "updated_at"])
    return account


def _resolve_inventory_account(tenant_id: int):
    """الطرف الدائن: حساب المخزون نفسه الذي تُدائنه تكلفة المبيعات.

    مصدرٌ واحد للحساب (`SalesSettings.default_inventory_account`) يمنع أن يصرف
    البيعُ من حسابٍ وتصرف الكفالةُ من آخر فيتباعد رصيد المخزون عن دفتره.
    """
    from sales.services import get_or_create_sales_settings

    settings_row = get_or_create_sales_settings(tenant_id)
    if settings_row.default_inventory_account_id:
        return settings_row.default_inventory_account
    raise ValidationError(
        "لا يوجد حساب مخزون افتراضي في إعدادات المبيعات — عيّنه قبل ترحيل قطع الكفالة."
    )


def resolve_labour_product(tenant_id: int):
    """منتج خدمة «أجرة صيانة» الافتراضي — يُنشأ مرة ويُثبَّت في الإعدادات.

    `is_service=True` ليس زينة: هو ما يجعل إيراد البند يقع في «إيرادات الخدمات»
    بدل إيراد البضائع، وهو ما يُبقيه خارج حركات المخزون.
    """
    from inventory.models import Product

    settings_row = get_or_create_after_sales_settings(tenant_id)
    if settings_row.default_labour_product_id:
        return settings_row.default_labour_product

    product = Product.objects.filter(
        tenant_id=tenant_id, sku=LABOUR_PRODUCT_SKU,
    ).first()
    if product is None:
        # #20: كل إنشاء منتجٍ يمرّ بالنقطة الموحّدة — منتج الأجرة ليس استثناءً،
        # وإلا صار براندًا بلا أبٍ فوقه يتسرّب من هذا الباب.
        from inventory.services import create_product_with_family

        _family, product = create_product_with_family(
            tenant_id=tenant_id,
            sku=LABOUR_PRODUCT_SKU,
            name_ar=LABOUR_PRODUCT_NAME,
            is_service=True,
            quantity_on_hand=Decimal("0"),
            avg_cost=Decimal("0"),
        )
        logger.info(
            "after_sales.labour_product.created tenant=%s product=%s",
            tenant_id, product.pk,
        )
    settings_row.default_labour_product = product
    settings_row.save(update_fields=["default_labour_product", "updated_at"])
    return product


# ══════════════════════════════════════════════════════════════════════════
# الترقيم والأحداث
# ══════════════════════════════════════════════════════════════════════════

def next_service_order_number(tenant_id: int) -> str:
    from accounting.services import next_document_number

    seq = next_document_number(tenant_id, "service_order")
    return f"SO-{tenant_id}-{seq}"


def log_event(
    order: ServiceOrder,
    *,
    event_type: str = ServiceOrderEvent.TYPE_NOTE,
    text: str = "",
    from_status: str = "",
    to_status: str = "",
    user=None,
) -> ServiceOrderEvent:
    """حدثٌ إلحاقي مؤرَّخ **من الخادم** — ساعة الجهاز ليست مصدر حقيقة.

    النص يبقى نصاً (لا مفاتيح مُرمَّزة وحدها) كي يعمل البحث عليه لاحقاً.
    """
    return ServiceOrderEvent.objects.create(
        order=order,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        text=(text or "")[:2000],
        actor=user if (user is not None and getattr(user, "is_authenticated", False)) else None,
    )


# ══════════════════════════════════════════════════════════════════════════
# دورة الحالة — FSM صغير، والنتيجة حقل منفصل
# ══════════════════════════════════════════════════════════════════════════

# المسار الخطّي: التقدّم والرجوع داخله مسموحان (الكاونتر يقفز عن التشخيص حين
# يكون العطل بيّناً، ويرجع خطوة حين يظهر عطل ثانٍ). ما هو محروس فعلاً طرفاه.
LINEAR_FLOW = [
    ServiceOrder.STATUS_RECEIVED,
    ServiceOrder.STATUS_IN_DIAGNOSIS,
    ServiceOrder.STATUS_AWAITING_APPROVAL,
    ServiceOrder.STATUS_IN_REPAIR,
    ServiceOrder.STATUS_READY,
]
TERMINAL_STATUSES = (ServiceOrder.STATUS_DELIVERED, ServiceOrder.STATUS_CANCELLED)


def _covered_parts_pending(order: ServiceOrder) -> int:
    return order.parts.filter(
        billing=ServiceOrderPart.BILLING_COVERED, materialized_at__isnull=True,
    ).count()


def _unbilled_billable_parts(order: ServiceOrder) -> list[ServiceOrderPart]:
    """قطع `billable` لم تدخل مستنداً بعد — وجود فاتورةٍ على الأمر لا يعنيها كلَّها.

    قطعةٌ أُضيفت **بعد** توليد الفاتورة لا تدخلها: الفاتورة وُلِّدت من التقاط
    `materialized_at__isnull=True` لحظتها، والإضافة اللاحقة بند جديد خارج
    ذلك الالتقاط (THA-223).
    """
    return list(
        order.parts
        .filter(billing=ServiceOrderPart.BILLING_BILLABLE, materialized_at__isnull=True)
        .select_related("product")
        .order_by("id")
    )


def billing_is_resolved(order: ServiceOrder) -> bool:
    """حُسم أمر المال: فاتورة قائمة أو سببُ إعفاءٍ مكتوب، **ولا قطعة مفوترة معلّقة**.

    التسليم بلا حسمٍ يترك مبلغاً معلّقاً بلا مستند ولا قرار — والجهاز يكون قد
    خرج. وجود الفاتورة وحده لا يكفي: قطعةٌ أُضيفت بعدها تبقى بلا مستند.
    """
    waived = bool((order.billing_waived_reason or "").strip())
    if waived:
        return True
    if not order.sales_invoice_id:
        return False
    return not _unbilled_billable_parts(order)


def delivery_blockers(order: ServiceOrder) -> list[str]:
    """أسباب منع التسليم — قائمة مقروءة لا رسالة واحدة مبهمة."""
    blockers = []
    pending = _covered_parts_pending(order)
    if pending:
        blockers.append(
            f"{pending} قطعة مغطاة بالكفالة لم تُرحَّل بعد — رحّل صرفها أولاً."
        )
    if not bool((order.billing_waived_reason or "").strip()):
        unbilled = _unbilled_billable_parts(order)
        if unbilled:
            names = "، ".join(product_display_name(p.product) for p in unbilled)
            blockers.append(
                f"قطع مفوترة لم تدخل فاتورة صيانة بعد — وَلِّد فاتورة تشملها أو "
                f"اكتب سبب الإعفاء من الفوترة: {names}."
            )
        elif not order.sales_invoice_id:
            blockers.append(
                "لم يُحسم أمر الفوترة — ولّد فاتورة الصيانة أو اكتب سبب الإعفاء من الفوترة."
            )
    return blockers


def cancellation_blockers(order: ServiceOrder) -> list[str]:
    """الإلغاء ممنوع ما دام في الأمر ترحيلٌ قائم — يُتراجَع عنه أولاً بصلاحيته."""
    blockers = []
    if order.covered_posted_at is not None:
        blockers.append(
            "صرف قطع الكفالة مرحَّل — تراجع عن ترحيله قبل الإلغاء."
        )
    if order.sales_invoice_id:
        blockers.append(
            "للأمر فاتورة صيانة مرتبطة — افصلها أو ألغِها قبل إلغاء الأمر."
        )
    return blockers


@transaction.atomic
def transition_status(
    order: ServiceOrder,
    to_status: str,
    *,
    user=None,
    outcome: str = "",
    note: str = "",
) -> ServiceOrder:
    """نقل الأمر إلى حالة جديدة مع حرّاسها، وتسجيل الانتقال حدثاً.

    `delivered` و`cancelled` نهائيتان ولكلٍّ بوابتها؛ ما عدا ذلك حركةٌ حرّة
    داخل المسار الخطّي. لا حالة بلا مخرج: رفض الزبون للتقدير لا يحتاج حالةً
    خاصة — `ready` بنتيجة `rejected_estimate` ثم `delivered` (يُعاد الجهاز كما هو).
    """
    order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
    valid = {choice for choice, _ in ServiceOrder.STATUS_CHOICES}
    if to_status not in valid:
        raise ValidationError(f"حالة غير معروفة: {to_status}")

    current = order.status
    if current in TERMINAL_STATUSES:
        raise ValidationError(
            f"الأمر في حالة «{order.get_status_display()}» النهائية — لا نقل بعدها."
        )
    if to_status == current:
        raise ValidationError("الأمر في هذه الحالة أصلاً.")

    if to_status == ServiceOrder.STATUS_DELIVERED:
        blockers = delivery_blockers(order)
        if blockers:
            raise ValidationError("تعذّر التسليم: " + " • ".join(blockers))
        if not outcome:
            raise ValidationError(
                {"outcome": "حدّد نتيجة الصيانة عند التسليم (أُصلح / تعذّر / رُفض التقدير / لا عطل)."}
            )
        if outcome not in {choice for choice, _ in ServiceOrder.OUTCOME_CHOICES}:
            raise ValidationError({"outcome": f"نتيجة غير معروفة: {outcome}"})
        order.outcome = outcome
        order.delivered_at = timezone.now()
    elif to_status == ServiceOrder.STATUS_CANCELLED:
        blockers = cancellation_blockers(order)
        if blockers:
            raise ValidationError("تعذّر الإلغاء: " + " • ".join(blockers))

    order.status = to_status
    order.save(update_fields=["status", "outcome", "delivered_at", "updated_at"])

    label = dict(ServiceOrder.STATUS_CHOICES)
    text = f"الحالة: {label.get(current, current)} ← {label.get(to_status, to_status)}"
    if to_status == ServiceOrder.STATUS_DELIVERED:
        text += f" (النتيجة: {dict(ServiceOrder.OUTCOME_CHOICES).get(outcome, outcome)})"
    if note:
        text += f" — {note}"
    log_event(
        order, event_type=ServiceOrderEvent.TYPE_STATUS, text=text,
        from_status=current, to_status=to_status, user=user,
    )
    logger.info(
        "after_sales.order_transition tenant=%s order=%s %s→%s",
        order.tenant_id, order.pk, current, to_status,
    )
    return order


def record_approval(order: ServiceOrder, *, user=None, note: str = "") -> ServiceOrder:
    """موافقة الزبون على التقدير — واقعة مؤرَّخة، لا مستند عرض سعر رسمي في هذه النسخة."""
    if order.status in TERMINAL_STATUSES:
        raise ValidationError("الأمر في حالة نهائية — لا تُسجَّل موافقة بعدها.")
    order.approved_at = timezone.now()
    order.approved_by = user if (user is not None and getattr(user, "is_authenticated", False)) else None
    order.save(update_fields=["approved_at", "approved_by", "updated_at"])
    amount = order.estimated_amount
    text = "وافق الزبون على التقدير"
    if amount is not None:
        text += f" ({amount})"
    if note:
        text += f" — {note}"
    log_event(order, event_type=ServiceOrderEvent.TYPE_APPROVAL, text=text, user=user)
    return order


# ══════════════════════════════════════════════════════════════════════════
# المال — أ. القطع المغطاة بالكفالة: صرفٌ بمصروف بلا إيراد
# ══════════════════════════════════════════════════════════════════════════

@transaction.atomic
def post_covered_parts(order: ServiceOrder, *, user=None) -> dict:
    """يصرف القطع المغطاة من المخزن ويقيّد كلفتها مصروفَ كفالة.

    التكلفة تاريخية بحقّ FIFO: `record_stock_movement` يستهلك أقدم طبقات
    المنتج المفتوحة لحظة الصرف — لا متوسطاً يحرّكه شراء لاحق.

    كلفةٌ صفرية (طبقاتٌ بسعر صفر) تُسجَّل حركةً بلا قيد: البضاعة خرجت فعلاً
    فحركتها واجبة، والقيد الصفري مرفوض من `post_journal` أصلاً — لكنها تمرّ
    بفحص الفترة المالية نفسه فلا يفلت صرفٌ صفري من فترة مقفلة بحجة أنه بلا قيد.

    **التاريخ يوم الترحيل لا يوم الاستلام** (`timezone.localdate()`، #223):
    الصرف قد يقع بعد إقفال شهر الاستلام، أو قبل شراء القطعة نفسها — نفس قاعدة
    فاتورة الصيانة المولَّدة (`generate_service_invoice`، تاريخها اليوم دائماً).
    """
    order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
    if order.status in TERMINAL_STATUSES:
        raise ValidationError(
            f"الأمر في حالة «{order.get_status_display()}» — لا ترحيل بعدها."
        )
    # #236: الكفالة الملغاة أو المنتهية لا تُصرف عليها قطعٌ بمصروف كفالة، أيّاً كان
    # ما بقي على الأمر من علامة التغطية.
    card = order.warranty_card if order.warranty_card_id else None
    if card is not None and card.status_on() in (
        WarrantyCard.STATUS_VOIDED, WarrantyCard.STATUS_ENDED,
    ):
        raise ValidationError(
            "بطاقة الكفالة "
            + ("ملغاة" if card.status_on() == WarrantyCard.STATUS_VOIDED else "منتهية")
            + " — لا تُرحَّل قطع مغطاة عليها. حوّل القطع إلى مفوترة."
        )

    parts = list(
        order.parts
        .select_related("product")
        .filter(
            billing=ServiceOrderPart.BILLING_COVERED, materialized_at__isnull=True,
        )
        .order_by("id")
    )
    if not parts:
        raise ValidationError("لا توجد قطع مغطاة بالكفالة بانتظار الترحيل.")

    posting_date = timezone.localdate()
    # الفحص يسبق أي كتابة ولو كانت الكلفة صفرية — `post_document` يفحصه من
    # تلقاء نفسه حين يوجد قيد، لكن الفرع الصفري لا يبني قيداً فيفلت بلا هذا.
    validate_fiscal_period(order.tenant_id, posting_date)
    # الأرقام التسلسلية: تأكيدٌ قبل أي كتابة تحت «إجباري» — مرآة ما يفعله البيع.
    assert_issue_serials_declared(order.tenant_id, parts)

    expense_account = resolve_warranty_expense_account(order.tenant_id)
    inventory_account = _resolve_inventory_account(order.tenant_id)

    total_cost = Decimal("0.00")
    part_costs: dict[int, Decimal] = {}
    for part in parts:
        movement = record_stock_movement(
            product=part.product,
            movement_type="OUT",
            quantity=Decimal(str(part.quantity)),
            reference_type=STOCK_REF_SERVICE_ISSUE,
            reference_id=order.pk,
            movement_date=posting_date,
            tenant=order.tenant,
            partner=order.partner,
            notes=f"قطع كفالة — أمر صيانة {order.order_number or order.pk}"[:500],
        )
        part_cost = Decimal(str(movement.total_cost)).quantize(DEC)
        part_costs[part.pk] = part_cost
        total_cost += part_cost

    total_cost = total_cost.quantize(DEC)
    stamp = timezone.now()
    journal = None
    if total_cost > 0:
        description = (
            f"مصروف قطع كفالة — أمر صيانة {order.order_number or order.pk}"
        )
        journal = post_document(
            tenant_id=order.tenant_id,
            transaction_date=posting_date,
            reference_type=JOURNAL_REF_WARRANTY_PARTS,
            reference_id=order.pk,
            description=description,
            lines_data=[
                {
                    "account": expense_account.pk,
                    "debit": total_cost,
                    "credit": Decimal("0"),
                    "description": description,
                },
                {
                    "account": inventory_account.pk,
                    "debit": Decimal("0"),
                    "credit": total_cost,
                    "description": description,
                },
            ],
            user=user,
        )
    else:
        logger.warning(
            "after_sales.covered_parts_zero_cost tenant=%s order=%s parts=%d",
            order.tenant_id, order.pk, len(parts),
        )

    # الأرقام التسلسلية تُستهلك بعد أن تُعرف كلفة كل بند — وحدةٌ `issued` لن
    # يخصّصها بيعٌ لاحق بـFIFO (`consume_sales_serials` يستعلم `in_stock` وحدها).
    issue_serials(order.tenant_id, parts)

    for part in parts:
        part.materialized_at = stamp
        part.issued_cost = part_costs[part.pk]
        part.save(update_fields=["materialized_at", "issued_cost"])
    order.covered_posted_at = stamp
    order.save(update_fields=["covered_posted_at", "updated_at"])

    log_event(
        order, event_type=ServiceOrderEvent.TYPE_POSTING,
        text=(
            f"رُحّل صرف {len(parts)} قطعة مغطاة بالكفالة بكلفة {total_cost}"
            + (f" — قيد #{journal.pk}" if journal is not None else " (بلا قيد: كلفة صفرية)")
        ),
        user=user,
    )
    logger.info(
        "after_sales.covered_parts_posted tenant=%s order=%s parts=%d cost=%s journal=%s",
        order.tenant_id, order.pk, len(parts), total_cost,
        journal.pk if journal is not None else None,
    )
    return {
        "parts": len(parts),
        "total_cost": total_cost,
        "journal_id": journal.pk if journal is not None else None,
    }


@transaction.atomic
def unpost_covered_parts(order: ServiceOrder, *, user=None) -> dict:
    """تراجع بالحذف — القيد وحركات المخزون معاً، ثم يُفتح قفل البنود.

    المستند السابع في سجلّ `accounting.services.unpost_document`، بنمطه نفسه:
    حذفٌ ذرّي محصورٌ بمرجع هذا الأمر وحده، لا قيدٌ عكسي.
    """
    order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
    if order.covered_posted_at is None:
        raise ValidationError("لا يوجد صرف قطع كفالة مرحَّل على هذا الأمر.")
    if order.status == ServiceOrder.STATUS_DELIVERED:
        raise ValidationError(
            "سُلّم الجهاز للزبون — لا تراجع عن صرف قطعه بعد خروجه."
        )

    parts = list(
        order.parts.filter(
            billing=ServiceOrderPart.BILLING_COVERED, materialized_at__isnull=False,
        )
    )

    result = unpost_document(
        tenant_id=order.tenant_id,
        reference_id=order.pk,
        journal_reference_types=[JOURNAL_REF_WARRANTY_PARTS],
        stock_reference_types=(STOCK_REF_SERVICE_ISSUE,),
        user=user,
        document_label=f"أمر صيانة {order.order_number or order.pk}",
    )

    # الأرقام التسلسلية تعود `in_stock` قبل فتح القفل — نفس ترتيب البيع
    # (`release_sales_serials` قبل تصفير `amount_paid`).
    unissue_serials(order.tenant_id, parts)

    unlocked = ServiceOrderPart.objects.filter(pk__in=[p.pk for p in parts]).update(
        materialized_at=None, issued_cost=None,
    )
    order.covered_posted_at = None
    order.save(update_fields=["covered_posted_at", "updated_at"])

    log_event(
        order, event_type=ServiceOrderEvent.TYPE_POSTING,
        text=(
            f"أُلغي ترحيل صرف قطع الكفالة — حُذف {result['journals_deleted']} قيداً "
            f"و{result['stock_movements_deleted']} حركة مخزون، وفُتح قفل {unlocked} بنداً"
        ),
        user=user,
    )
    result["parts_unlocked"] = unlocked
    return result


# ══════════════════════════════════════════════════════════════════════════
# المال — ب. القطع المفوترة: فاتورة بيع مسودة بمسار SALE القائم
# ══════════════════════════════════════════════════════════════════════════

@transaction.atomic
def generate_service_invoice(
    order: ServiceOrder,
    *,
    user=None,
    labour_amount=None,
):
    """يولّد فاتورة بيع **مسودة** ببنود القطع المفوترة وبند الأجرة.

    مسودة لا مرحّلة عمداً: المستخدم يراجعها ويرحّلها من شاشة الفواتير القائمة —
    لا شاشة فوترة ثانية ولا مسار ترحيل ثانٍ. والترحيل عندها يخصم المخزون ويأخذ
    التكلفة التاريخية عبر مسار `SALE` المجرَّب كأي بيع.
    """
    from sales.models import SalesInvoice, SalesInvoiceLine
    from sales.services import (
        get_or_create_default_customer,
        get_or_create_sales_settings,
        next_invoice_number,
        recalculate_invoice_amounts,
    )
    from tenants.models import Currency

    order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
    if order.status == ServiceOrder.STATUS_CANCELLED:
        raise ValidationError("الأمر ملغى — لا فاتورة له.")
    if order.sales_invoice_id:
        raise ValidationError(
            f"للأمر فاتورة صيانة مرتبطة أصلاً (#{order.sales_invoice_id}) — "
            "افصلها قبل توليد غيرها."
        )

    parts = list(
        order.parts
        .select_related("product")
        .filter(
            billing=ServiceOrderPart.BILLING_BILLABLE, materialized_at__isnull=True,
        )
        .order_by("id")
    )
    labour = Decimal(str(
        labour_amount if labour_amount is not None else (order.estimated_amount or 0)
    ))
    if labour < 0:
        raise ValidationError({"labour_amount": "أجرة الصيانة لا تكون سالبة."})
    if not parts and labour <= 0:
        raise ValidationError(
            "لا قطع مفوترة ولا أجرة صيانة — لا شيء يُفوتر على الزبون."
        )
    # منعٌ لا خصمٌ صامت: قطعةٌ بسعر صفر تخرج مجاناً في فاتورةٍ تدّعي أنها
    # مفوترة — القرار يُترك للمستخدم (سعرٌ حقيقي، أو تحويلها مغطاة، أو حذفها).
    zero_priced = [
        p for p in parts if Decimal(str(p.unit_price or 0)) <= 0
    ]
    if zero_priced:
        names = "، ".join(product_display_name(p.product) for p in zero_priced)
        raise ValidationError(
            f"قطع مفوترة بسعر صفر — اكتب سعرها، أو اجعلها مغطاة، أو احذفها: {names}."
        )

    sales_settings = get_or_create_sales_settings(order.tenant_id)
    customer = order.partner
    if customer is None:
        customer = get_or_create_default_customer(order.tenant_id)
    currency = sales_settings.default_currency or (
        Currency.objects.filter(IsBaseCurrency=True).order_by("CurrencyID").first()
        or Currency.objects.order_by("CurrencyID").first()
    )
    if currency is None:
        raise ValidationError("لا توجد عملة معرّفة للشركة — تعذّر توليد الفاتورة.")

    invoice = SalesInvoice.objects.create(
        tenant=order.tenant,
        invoice_number=next_invoice_number(order.tenant_id),
        customer=customer,
        currency=currency,
        invoice_date=timezone.localdate(),
        invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
        invoice_type=SalesInvoice.INVOICE_CREDIT,
        status=SalesInvoice.STATUS_DRAFT,
        notes=f"فاتورة صيانة — أمر {order.order_number or order.pk}",
        created_by=user if (user is not None and getattr(user, "is_authenticated", False)) else None,
    )

    lines = []
    if labour > 0:
        lines.append(SalesInvoiceLine.objects.create(
            tenant=order.tenant,
            invoice=invoice,
            product=resolve_labour_product(order.tenant_id),
            quantity=Decimal("1"),
            unit_price=labour,
        ))
    for part in parts:
        lines.append(SalesInvoiceLine.objects.create(
            tenant=order.tenant,
            invoice=invoice,
            product=part.product,
            quantity=Decimal(str(part.quantity)),
            unit_price=Decimal(str(part.unit_price)),
        ))

    recalculate_invoice_amounts(invoice, lines)
    for line in lines:
        line.save(update_fields=["line_total_excl_tax", "line_tax_amount"])
    invoice.save(update_fields=["subtotal_excl_tax", "tax_amount", "grand_total"])

    # القفل: البند تجسّد في سطر فاتورة بعينه، فلا يلتقطه مسار الصرف بعد اليوم.
    stamp = timezone.now()
    part_lines = lines[1:] if labour > 0 else lines
    for part, line in zip(parts, part_lines):
        part.sales_invoice_line = line
        part.materialized_at = stamp
        part.save(update_fields=["sales_invoice_line", "materialized_at"])

    order.sales_invoice = invoice
    order.save(update_fields=["sales_invoice", "updated_at"])

    log_event(
        order, event_type=ServiceOrderEvent.TYPE_INVOICE,
        text=(
            f"وُلّدت فاتورة صيانة مسودة {invoice.invoice_number} "
            f"({len(parts)} قطعة مفوترة، أجرة {labour}) — راجِعها ورحّلها من شاشة الفواتير"
        ),
        user=user,
    )
    logger.info(
        "after_sales.service_invoice_generated tenant=%s order=%s invoice=%s parts=%d",
        order.tenant_id, order.pk, invoice.pk, len(parts),
    )
    return invoice


@transaction.atomic
def detach_service_invoice(order: ServiceOrder, *, user=None) -> dict:
    """يفصل الفاتورة المولَّدة عن الأمر ويفتح قفل بنودها — ما دامت مسودة.

    فاتورةٌ مرحّلة لا تُفصَل: بنودها صارت واقعةً في الدفاتر والمخزون، وفصلها
    يعيد بنود الأمر إلى الالتقاط فيُصرَف ما بيع.
    """
    from sales.models import SalesInvoice

    order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
    invoice = order.sales_invoice
    if invoice is None:
        raise ValidationError("لا فاتورة مرتبطة بهذا الأمر.")
    if invoice.status == SalesInvoice.STATUS_POSTED:
        raise ValidationError(
            f"الفاتورة {invoice.invoice_number} مرحّلة — تراجع عن ترحيلها أولاً."
        )

    unlocked = order.parts.filter(
        billing=ServiceOrderPart.BILLING_BILLABLE, materialized_at__isnull=False,
    ).update(materialized_at=None, sales_invoice_line=None)
    order.sales_invoice = None
    order.save(update_fields=["sales_invoice", "updated_at"])

    log_event(
        order, event_type=ServiceOrderEvent.TYPE_INVOICE,
        text=f"فُصلت فاتورة الصيانة {invoice.invoice_number} — فُتح قفل {unlocked} بنداً",
        user=user,
    )
    return {"invoice_id": invoice.pk, "parts_unlocked": unlocked}


# ══════════════════════════════════════════════════════════════════════════
# الاستقبال — البحث الموحّد بمعرّف واحد
# ══════════════════════════════════════════════════════════════════════════

VERDICT_ENDED = "ended"
VERDICT_DEALER = "dealer"
# #244 (إصلاح مدفوع بكفالة إصلاح) يضيف حكمه هنا — بين `dealer` و`referral`.
VERDICT_REFERRAL = "referral"
VERDICT_VOIDED_PAID = "voided_paid"
VERDICT_EXPIRED_PAID = "expired_paid"

MATCH_SERIAL = "serial"
MATCH_INVOICE = "invoice"
MATCH_PHONE = "phone"

LOOKUP_SERIAL_CAP = 5
LOOKUP_INVOICE_CAP = 50
LOOKUP_PHONE_CAP = 20
LOOKUP_UNITS_CAP = 20
LOOKUP_ROW_ORDERS_CAP = 5
# رقمٌ أطول (IMEI = 15) ليس هاتفاً: لا يُبحث بآخر تسعة أرقامه.
MAX_PHONE_DIGITS = 14
SHORT_PHONE_MESSAGE = "اكتب الرقم كاملاً"


def is_invoice_card(card) -> bool:
    return card.product_serial_id is None and card.quantity > 0


def intake_verdict(card, today) -> str:
    """الحكم الوحيد للاستقبال — الواجهة ترسم ما يردّه هنا ولا تحسب شيئاً.

    الترتيب هو المواصفة: المنتهية بواقعة تغلب كل شيء، ثم كفالة التاجر السارية
    (وعلى بطاقة الفاتورة: بقيت قطعٌ مكفولة)، ثم إحالة المصنع، ثم الملغاة، ثم المنتهية.
    """
    status = card.status_on(today)
    if status == WarrantyCard.STATUS_ENDED:
        return VERDICT_ENDED
    if status == WarrantyCard.STATUS_ACTIVE and (
        not is_invoice_card(card) or card.covered_quantity > 0
    ):
        return VERDICT_DEALER
    if card.manufacturer_status_on(today) == WarrantyCard.STATUS_ACTIVE:
        return VERDICT_REFERRAL
    if status == WarrantyCard.STATUS_VOIDED:
        return VERDICT_VOIDED_PAID
    return VERDICT_EXPIRED_PAID


def _order_matches(order, card, serial: str) -> bool:
    if card is not None and order.warranty_card_id == card.pk:
        return True
    if card is not None and is_invoice_card(card):
        return False
    return bool(serial) and order.serial == serial


def _blocking_order(card, orders):
    """الأمر الذي يمنع فتح آخر — القاعدة نفسها للبحث وللإنشاء.

    وحدةٌ مُرقَّمة: أيُّ أمرٍ مفتوح. بطاقة فاتورة: لا يُمنع إلا حين تبلغ الأوامر
    المفتوحة عددَ القطع المكفولة (`covered_quantity`).
    """
    if not orders:
        return None
    if card is not None and is_invoice_card(card):
        if card.covered_quantity > 0 and len(orders) >= card.covered_quantity:
            return orders[0]
        return None
    return orders[0]


def find_duplicate_open_order(tenant_id: int, *, card, serial: str):
    """أمرٌ مفتوح (غير مسلَّم ولا ملغى) يمنع أمراً جديداً على البطاقة أو الرقم."""
    from django.db.models import Q

    serial = (serial or "").strip()
    condition = Q()
    if card is not None:
        condition |= Q(warranty_card=card)
    if serial:
        condition |= Q(serial=serial)
    if not condition:
        return None
    orders = [
        order for order in ServiceOrder.objects
        .filter(tenant_id=tenant_id).exclude(status__in=TERMINAL_STATUSES)
        .filter(condition).order_by("-id")
        if _order_matches(order, card, serial)
    ]
    return _blocking_order(card, orders)


def _order_summary(order) -> dict:
    return {
        "id": order.pk,
        "order_number": order.order_number,
        "order_date": order.order_date,
        "status": order.status,
        "status_display": order.get_status_display(),
        "complaint": order.complaint[:200],
    }


def _intake_prefill(card, verdict: str) -> dict:
    """ما يُعبَّأ في نموذج الأمر. `sales_invoice` لا يُعبَّأ أبداً: أمر الصيانة لا يحمل
    فاتورة بيع، والبطاقة (`warranty_card`) هي الرابط. والمنتهية لا تُعبّئ الزبون —
    الشهادة لم تعد له."""
    ended = verdict == VERDICT_ENDED
    partner = None if ended or not card.partner_id else card.partner
    if ended:
        name, phone = "", ""
    else:
        name = partner.name if partner else card.customer_name
        phone = (partner.phone if partner and partner.phone else card.customer_phone) or ""
    return {
        "partner": partner.pk if partner else None,
        "customer_name": name,
        "customer_phone": phone,
        "product": card.product_id,
        "serial": card.serial,
        "device_description": card.device_name,
        "warranty_card": card.pk,
        "warranty_covered": verdict == VERDICT_DEALER,
        "requires_item_confirm": is_invoice_card(card),
    }


def _intake_card_row(card, today, verdict: str) -> dict:
    invoice = card.sales_invoice if card.sales_invoice_id else None
    manufacturer = None
    if card.manufacturer_warrantor_id:
        manufacturer = {
            "warrantor": card.manufacturer_warrantor.name,
            "start_date": card.manufacturer_start_date,
            "end_date": card.manufacturer_end_date,
            "status": card.manufacturer_status_on(today),
            "days_remaining": card.manufacturer_days_remaining(today),
        }
    void = None
    if card.voided_at is not None:
        void = {
            "reason": card.void_reason,
            "reason_label": card.get_void_reason_display(),
            "voided_at": card.voided_at,
            "service_order_number": (
                card.void_service_order.order_number if card.void_service_order_id else ""
            ),
        }
    ended = None
    if card.ended_on is not None:
        line = card.end_return_line if card.end_return_line_id else None
        ended = {
            "ended_on": card.ended_on,
            "end_reason": card.end_reason,
            "end_reason_label": card.get_end_reason_display(),
            "document_number": (
                line.invoice.invoice_number if line and line.invoice_id else ""
            ),
        }
    return {
        "id": card.pk,
        "device_name": card.device_name,
        "serial": card.serial,
        "product": card.product_id,
        "quantity": card.quantity,
        "returned_quantity": card.returned_quantity,
        "covered_quantity": card.covered_quantity,
        "partner": (
            {"id": card.partner_id, "name": card.partner.name} if card.partner_id else None
        ),
        "customer_name": card.customer_name,
        "customer_phone": card.customer_phone,
        "sales_invoice_number": invoice.invoice_number if invoice else "",
        "sale_date": invoice.invoice_date if invoice else card.start_date,
        "dealer": {
            "start_date": card.start_date,
            "end_date": card.end_date,
            "status": card.status_on(today),
            "days_remaining": card.days_remaining(today),
        },
        "manufacturer": manufacturer,
        "void": void,
        "ended": ended,
    }


def _latest_per_unit(cards, cap: int) -> list:
    """أحدث بطاقة لكل وحدة (منتج + رقم)، وبطاقةُ الفاتورة وحدةٌ بذاتها."""
    seen, picked = set(), []
    for card in cards:
        key = (card.product_id, card.serial) if card.serial else ("card", card.pk)
        if key in seen:
            continue
        seen.add(key)
        picked.append(card)
        if len(picked) >= cap:
            break
    return picked


def _units_without_card(tenant_id: int, *, serial: str, invoice_ids, partner_ids) -> list:
    """وحداتٌ بعناها ولا بطاقة لها — يراها الاستقبال بدل «غير موجود» (منتجٌ بلا سياسة)."""
    from django.db.models import Q

    from inventory.models import ProductSerial

    condition = Q()
    if serial:
        condition |= Q(serial=serial)
    if invoice_ids:
        condition |= Q(sales_line__invoice_id__in=invoice_ids)
    if partner_ids:
        condition |= Q(sales_line__invoice__customer_id__in=partner_ids)
    if not condition:
        return []
    units = (
        ProductSerial.objects
        .filter(tenant_id=tenant_id, status=ProductSerial.STATUS_SOLD, warranty_cards__isnull=True)
        .filter(condition)
        .select_related("product", "sales_line__invoice__customer")
        .order_by("-id")[:LOOKUP_UNITS_CAP]
    )
    rows = []
    for unit in units:
        invoice = unit.sales_line.invoice if unit.sales_line_id and unit.sales_line.invoice_id else None
        customer = invoice.customer if invoice and invoice.customer_id else None
        rows.append({
            "id": unit.pk,
            "serial": unit.serial,
            "product": unit.product_id,
            "product_name": product_display_name(unit.product),
            "invoice_number": invoice.invoice_number if invoice else "",
            "sale_date": invoice.invoice_date if invoice else None,
            "partner": {"id": customer.pk, "name": customer.name} if customer else None,
        })
    return rows


MATCH_CARD = "card"


def _intake_cards(tenant_id: int):
    return WarrantyCard.objects.filter(tenant_id=tenant_id).select_related(
        "product", "partner", "sales_invoice", "manufacturer_warrantor",
        "void_service_order", "end_return_line__invoice",
    )


def _intake_rows(tenant_id: int, matches, today) -> list[dict]:
    """سطر الاستقبال لكل (بطاقة، سبب) — الطريق الوحيد لبنائه، بحثاً كان أم بمعرّف."""
    from django.db.models import Q

    cards = [card for card, _kind in matches]
    open_all = []
    if cards:
        condition = Q(warranty_card_id__in=[card.pk for card in cards])
        serials = {card.serial for card in cards if card.serial and not is_invoice_card(card)}
        if serials:
            condition |= Q(serial__in=serials)
        open_all = list(
            ServiceOrder.objects.filter(tenant_id=tenant_id)
            .exclude(status__in=TERMINAL_STATUSES).filter(condition)
            .order_by("-order_date", "-id")
        )
    rows = []
    for card, kind in matches:
        verdict = intake_verdict(card, today)
        mine = [order for order in open_all if _order_matches(order, card, card.serial)]
        rows.append({
            "card": _intake_card_row(card, today, verdict),
            "verdict": verdict,
            "matched_on": kind,
            "open_orders": [_order_summary(order) for order in mine[:LOOKUP_ROW_ORDERS_CAP]],
            "duplicate_blocked": _blocking_order(card, mine) is not None,
            "prefill": _intake_prefill(card, verdict),
        })
    return rows


def _empty_lookup(tenant_id: int, term: str) -> dict:
    return {
        "term": term,
        "warranty": warranty_coverage(tenant_id, term),
        "sensitive_devices": [],
        "open_orders": [],
        "results": [],
        "units_without_card": [],
        "matched_on": [],
        "truncated": False,
        "message": "",
    }


def intake_card_lookup(tenant, card_id) -> dict | None:
    """سطرٌ واحد لبطاقةٍ بعينها (الرابط العميق ومسح QR وزرّ «افتح أمر صيانة»).

    «أحدث بطاقة لكل وحدة» قاعدةُ **البحث**؛ معرّفٌ صريح يعني هذه البطاقة نفسها
    ولو سبقتها أحدث منها أو خلت من رقمٍ وفاتورة وهاتف. `None` ⇐ ليست في هذه الشركة.
    """
    tenant_id = getattr(tenant, "pk", tenant)
    card = _intake_cards(tenant_id).filter(pk=card_id).first()
    if card is None:
        return None
    result = _empty_lookup(tenant_id, "")
    result["results"] = _intake_rows(tenant_id, [(card, MATCH_CARD)], timezone.localdate())
    result["matched_on"] = [MATCH_CARD]
    return result


def _intake_matches(tenant_id: int, term: str):
    """(البطاقات المطابقة مع سبب كلٍّ، معرّفات الفواتير المطابقة، مقتطع؟، رسالة).

    مطابقة **تامّة** فقط — لا LIKE ولا icontains: بحثٌ بجزء رقمٍ يُظهر بطاقات
    زبائن لا علاقة لهم ولا يخدم أحداً. رقم الفاتورة `iexact` (كتابة الكاشير تختلف
    بالحالة) وهو مطابقةٌ تامّة تُهرَّب فيها `%` و`_`.
    """
    from sales.models import SalesInvoice

    base = _intake_cards(tenant_id)
    found: dict[int, tuple] = {}

    def add(cards, kind):
        for card in cards:
            found.setdefault(card.pk, (card, kind))

    add(
        _latest_per_unit(base.filter(serial=term).order_by("-id")[:200], LOOKUP_SERIAL_CAP),
        MATCH_SERIAL,
    )

    invoice_ids = list(
        SalesInvoice.objects.filter(tenant_id=tenant_id, invoice_number__iexact=term)
        .values_list("pk", flat=True)[:LOOKUP_INVOICE_CAP]
    )
    if invoice_ids:
        add(
            base.filter(sales_invoice_id__in=invoice_ids).order_by("-id")[:LOOKUP_INVOICE_CAP],
            MATCH_INVOICE,
        )

    truncated = False
    short_phone = False
    if looks_like_phone(term):
        digit_count = len(phone_digits(term))
        if digit_count < PHONE_KEY_LENGTH:
            short_phone = True
        elif digit_count <= MAX_PHONE_DIGITS:
            raw = list(
                base.filter(phone_key=phone_key_of(term))
                .order_by("-start_date", "-id")[:LOOKUP_PHONE_CAP + 1]
            )
            truncated = len(raw) > LOOKUP_PHONE_CAP
            add(_latest_per_unit(raw[:LOOKUP_PHONE_CAP], LOOKUP_PHONE_CAP), MATCH_PHONE)

    message = SHORT_PHONE_MESSAGE if short_phone and not found else ""
    return list(found.values()), invoice_ids, truncated, message


def intake_lookup(tenant, term: str) -> dict:
    """«ما الذي نعرفه عن هذا الرقم؟» — سطرٌ لكل بطاقة بحكمها وتعبئتها، وما عداها.

    `results` هو العقد الجديد (#240): بطاقة بطبقتيها + `verdict` + `open_orders` +
    `prefill`، وبجانبه `units_without_card` و`sensitive_devices`. والمفاتيح القديمة
    (`warranty` و`open_orders` و`term`) باقية كما كانت لمن يقرأها.

    الرابط بسجل الأجهزة الحساسة معرّفٌ نصي (تسلسلي/IMEI) لا FK: وحدةٌ مرخّصة
    مستقلة محايدة مالياً، وربطها بمستندٍ يمسّ المال يكسر إطفاءها المستقل
    (صفٌّ يشير إلى وحدة معطّلة). التطابق المزدوج يُعرض كلاهما والمستخدم يختار.
    """
    term = (term or "").strip()
    tenant_id = getattr(tenant, "pk", tenant)
    result = _empty_lookup(tenant_id, term)
    if not term:
        return result

    from django.db.models import Q

    matches, invoice_ids, truncated, message = _intake_matches(tenant_id, term)
    result["results"] = _intake_rows(tenant_id, matches, timezone.localdate())
    result["matched_on"] = sorted({kind for _card, kind in matches})
    result["truncated"] = truncated
    result["message"] = message
    result["units_without_card"] = _units_without_card(
        tenant_id, serial=term, invoice_ids=invoice_ids,
        partner_ids={
            card.partner_id for card, kind in matches
            if kind == MATCH_PHONE and card.partner_id
        },
    )

    if module_enabled(tenant, "sensitive_devices"):
        from device_registry.models import SensitiveDevice

        result["sensitive_devices"] = [
            {
                "id": device.pk,
                "model_name": device.model_name,
                "serial_number": device.serial_number,
                "imei": device.imei,
                "status": device.status,
                "status_display": device.get_status_display(),
                "customer_name": device.customer_name,
                "customer_phone": device.customer_phone,
                "registered_at": device.created_at,
            }
            for device in SensitiveDevice.objects
            .filter(tenant_id=tenant_id)
            .filter(Q(serial_number=term) | Q(imei=term))
            .order_by("-created_at")[:5]
        ]

    result["open_orders"] = [
        {
            "id": order.pk,
            "order_number": order.order_number,
            "order_date": order.order_date,
            "status": order.status,
            "status_display": order.get_status_display(),
            "complaint": order.complaint[:200],
        }
        for order in ServiceOrder.objects
        .filter(tenant_id=tenant_id, serial=term)
        .exclude(status=ServiceOrder.STATUS_CANCELLED)
        .order_by("-order_date", "-id")[:5]
    ]
    return result


def module_is_enabled(tenant) -> bool:
    return module_enabled(tenant, MODULE_KEY)


# ── سجل الصيانات في البطاقة (#242) ─────────────────────────────────────────
def _order_row(order) -> dict:
    return {
        "id": order.pk,
        "order_number": order.order_number,
        "order_date": order.order_date,
        "status": order.status,
        "status_label": order.get_status_display(),
        "covered": order.warranty_covered,
        "complaint": order.complaint,
    }


def card_service_history(card) -> dict:
    """ما حدث للجهاز: أوامر البطاقة وأحداثها في قائمة واحدة، الأحدث أولاً.

    الترتيب باليوم (`order_date` للأمر، ويوم `created_at` للحدث) ثم بلحظة
    الإنشاء ثم المعرّف — فيوم واحد يُرتَّب بما كُتب أولاً فعلاً لا بما اتّفق.
    و`maybe_related` أوامرُ **غير مربوطة** بالرقم التسلسلي نفسه (مطابقة تامة)
    للعرض فقط: لا يُربط شيء هنا ولا يُكتب. ثلاثة استعلامات ثابتة مهما كثر السجل.
    """
    from .models import WarrantyCardEvent
    from .serializers import WarrantyCardEventSerializer

    orders = list(
        ServiceOrder.objects.filter(tenant_id=card.tenant_id, warranty_card=card)
    )
    events = list(
        WarrantyCardEvent.objects
        .filter(tenant_id=card.tenant_id, card=card)
        .select_related("actor", "service_order")
    )

    entries = [
        (order.order_date, order.created_at, order.pk,
         {"kind": "order", "date": order.order_date, "at": order.created_at, **_order_row(order)})
        for order in orders
    ] + [
        (timezone.localtime(event.created_at).date(), event.created_at, event.pk,
         {"kind": "event", "date": timezone.localtime(event.created_at).date(),
          "at": event.created_at, **WarrantyCardEventSerializer(event).data})
        for event in events
    ]
    entries.sort(key=lambda entry: entry[:3], reverse=True)

    maybe_related = []
    # بطاقة الفاتورة (بالكمية) لا رقم لها — وبلا رقم لا مطابقة تُعتمد.
    if card.serial.strip():
        maybe_related = [
            _order_row(order)
            for order in ServiceOrder.objects
            .filter(tenant_id=card.tenant_id, serial=card.serial, warranty_card__isnull=True)
            .order_by("-order_date", "-id")
        ]
    return {"timeline": [entry[3] for entry in entries], "maybe_related": maybe_related}
