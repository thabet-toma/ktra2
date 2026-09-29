"""محرّك الكفالة — دورة حياة بطاقة الكفالة التلقائية وفحص التغطية.

**تعطيلٌ لا حذف (#222).** البطاقة التلقائية لا تُحذف أبداً: هويّتها (`id`) هي
ما تتعلّق به أوامر الصيانة ورمزُ التحقّق المطبوع على الشهادة، وحذفُها عند إلغاء
ترحيل الفاتورة كان يكسر الاثنين ثم يُنشئ بديلاً بـ`id` جديد. بدلاً من ذلك
تُسجَّل على البطاقة **واقعةُ انتهاء** مؤرَّخة (`ended_on` + `end_reason`)،
ويُحييها إعادةُ الترحيل بنفسها.

خمس نقاط التحام، كلّها كسولةٌ من `sales` ومحروسةٌ بترخيص الوحدة:

- `create_auto_warranty_cards` — ترحيل البيع: يُحيي المعلَّق ثم يُنشئ الناقص.
- `on_sale_unposted` — إلغاء الترحيل: تعليقٌ بـ`invoice_unposted`.
- `on_sale_cancelled` — حذف المسودّة: المعلَّق يصير `sale_cancelled` بلا رجعة.
- `on_sales_return_posted` — مرجع البيع: الوحدات المرتجعة وحدها تُنهى بـ`returned`
  (وبطاقة الفاتورة #234 تُنقَص كميتها المكفولة بدل واقعة انتهاءٍ مباشرة).
- `on_sales_return_unposted` — إلغاء ترحيل المرجع: إحياءُ ما أنهاه.

**صفر أثر على شركة غير مرخّصة:** كلّها تخرج فوراً إن لم تكن الوحدة مرخّصة، فلا
يكتب النظامُ ولا يُعدِّل صفاً في جدولٍ لا تراه الشركة أصلاً.
"""
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from core.modules import module_enabled

from .models import (
    AfterSalesSettings,
    ManufacturerWarrantor,
    PurchaseLineWarranty,
    ServiceOrder,
    ServiceOrderEvent,
    WarrantyCard,
    WarrantyCardEvent,
    WarrantyPolicy,
    add_months,
    phone_key_of,
)

logger = logging.getLogger(__name__)

MODULE_KEY = "after_sales"


def get_or_create_after_sales_settings(tenant_id: int) -> AfterSalesSettings:
    settings_row, _ = AfterSalesSettings.objects.get_or_create(tenant_id=tenant_id)
    return settings_row


def log_warranty_event(
    card: WarrantyCard,
    *,
    event_type: str,
    reason_code: str = "",
    text: str = "",
    service_order=None,
    user=None,
    old_end_date=None,
    new_end_date=None,
    quantity=None,
) -> WarrantyCardEvent:
    """حدثٌ إلحاقي مؤرَّخ **من الخادم** — على نمط `service_orders.log_event`.

    نقطة كتابةٍ واحدة يُعاد استعمالها من كل تذكرة لاحقة تكتب على السجل
    (الإلغاء، الإصدار، الإحالة، تمديد أيام الصيانة…) بدل أن يكرّر كلٌّ منها
    `WarrantyCardEvent.objects.create` بنفسه.
    """
    return WarrantyCardEvent.objects.create(
        tenant_id=card.tenant_id,
        card=card,
        event_type=event_type,
        reason_code=reason_code,
        text=(text or "")[:2000],
        service_order=service_order,
        actor=user if (user is not None and getattr(user, "is_authenticated", False)) else None,
        old_end_date=old_end_date,
        new_end_date=new_end_date,
        quantity=quantity,
    )


def _supplier_side(unit, supplier_months: int):
    """(المورد، نهاية كفالته) من نسب الوحدة الشرائي — لا تخمين ولا افتراضي.

    الوحدة تحمل بند فاتورة الشراء الذي أدخلها المخزن؛ منه تاريخ الشراء والمورد.
    وحدة بلا نسب (مخزون سابق للتتبّع) تُعطي بطاقةً بلا جانب مورد، وهذا أصدق من
    اشتقاق تاريخٍ من فاتورة البيع.
    """
    item = unit.purchase_item if unit.purchase_item_id else None
    purchase_invoice = item.invoice if (item and item.invoice_id) else None
    if purchase_invoice is None:
        return None, None

    supplier_id = purchase_invoice.partner_id
    purchase_date = purchase_invoice.invoice_date
    if not supplier_months or purchase_date is None:
        return supplier_id, None
    return supplier_id, add_months(purchase_date, supplier_months)


def _invoice_cards(invoice):
    """بطاقات هذه الفاتورة التلقائية — بالمرساتين معاً.

    `sales_invoice` هي المرساة منذ #222، لكن بطاقاتٍ أقدم منها قد تحمل البند
    وحده (لو فشل الـbackfill لانقطاع بندها)، فتبقى المرساة الثانية احتياطاً.
    """
    return WarrantyCard.objects.filter(
        tenant_id=invoice.tenant_id, source=WarrantyCard.SOURCE_AUTO_SALE,
    ).filter(
        Q(sales_invoice=invoice) | Q(sales_invoice_line__invoice=invoice)
    )


#: مخرجات `_revive`: أُحييت · كانت حيّةً فحُدِّثت · رُفضت (واقعتها خارج الفاتورة).
REVIVED, KEPT, REFUSED = "revived", "kept", ""


def _revive(card, invoice, unit, customer) -> str:
    """يُعيد بطاقةً معلَّقة إلى الحياة على فاتورتها — بنفس الـ`id`.

    يبقى: الـ`id` والشروط المجمَّدة والمدّة والتمديدات والملاحظات وروابط أوامر
    الصيانة. ويُحدَّث: لقطة الزبون و`partner` و`sales_invoice_line`. وإن تغيّر
    تاريخ الفاتورة بين الإلغاء وإعادة الترحيل أُزيح طرفا البطاقة بالفرق نفسه،
    فيبقى التمديد اليدوي فوقهما كما مُنح.

    **المنتهية بمرجعٍ لا تُحيا هنا أبداً** — ولا المُستبدَلة ببطاقةِ مشترٍ ثانٍ:
    كلتاهما واقعةٌ خارج هذه الفاتورة، وإحياؤها يسحب شهادةً من صاحبها الحالي.
    تُترك على حالها وتأخذ الوحدةُ بطاقةً جديدة لبيعها الجديد.
    """
    fields = ["sales_invoice_line", "partner", "customer_name", "customer_phone"]
    reviving = card.ended_on is not None
    if reviving:
        if card.end_reason not in (
            WarrantyCard.END_INVOICE_UNPOSTED, WarrantyCard.END_SALE_CANCELLED,
        ):
            return REFUSED
        card.ended_on = None
        card.end_reason = ""
        card.end_return_line = None
        fields += ["ended_on", "end_reason", "end_return_line"]

    shift = (invoice.invoice_date - card.start_date).days
    if shift:
        card.start_date = invoice.invoice_date
        card.end_date = card.end_date + timedelta(days=shift)
        fields += ["start_date", "end_date"]
        # طبقة المصنع تُزاح بالفرق نفسه — البطاقة نفسها تُحيا لا تُستبدَل،
        # وتمديدٌ يدويٌّ سابق على طبقة المصنع (#232) يبقى فوق الإزاحة كما مُنح.
        if card.manufacturer_warrantor_id and card.manufacturer_start_date:
            card.manufacturer_start_date = card.manufacturer_start_date + timedelta(days=shift)
            card.manufacturer_end_date = card.manufacturer_end_date + timedelta(days=shift)
            fields += ["manufacturer_start_date", "manufacturer_end_date"]

    card.sales_invoice_line_id = unit.sales_line_id
    card.partner_id = invoice.customer_id
    card.customer_name = (customer.name if customer else "")[:150]
    card.customer_phone = (
        (getattr(customer, "phone", "") or "")[:32] if customer else ""
    )
    card.save(update_fields=fields + ["updated_at"])
    return REVIVED if reviving else KEPT


def _revive_invoice_card(card, invoice, customer, quantity: int) -> str:
    """يُحيي بطاقة «كفالة على الفاتورة» معلَّقة — بنفس الـ`id`، مطابقةً على
    `(sales_invoice, product)` لا على وحدة (بطاقة الفاتورة بلا `product_serial`).

    **الكمية تُعاد حسابها دائماً** من بنود الفاتورة الحالية — بند عُدِّل بين
    الإلغاء وإعادة الترحيل يجب أن ينعكس على البطاقة. `returned_quantity` لا
    تُمَسّ هنا: مرجعُ بيعٍ أنقص منها واقعةٌ مستقلة عن تعليق هذه الفاتورة وإحيائها.

    المنتهية بمرجعٍ (`END_RETURNED`) لا تُحيا هنا أبداً — نفس قاعدة `_revive`.
    """
    fields = ["quantity", "partner", "customer_name", "customer_phone"]
    reviving = card.ended_on is not None
    if reviving:
        if card.end_reason not in (
            WarrantyCard.END_INVOICE_UNPOSTED, WarrantyCard.END_SALE_CANCELLED,
        ):
            return REFUSED
        card.ended_on = None
        card.end_reason = ""
        fields += ["ended_on", "end_reason"]

    card.quantity = quantity
    card.partner_id = invoice.customer_id
    card.customer_name = (customer.name if customer else "")[:150]
    card.customer_phone = (
        (getattr(customer, "phone", "") or "")[:32] if customer else ""
    )
    card.save(update_fields=fields + ["updated_at"])
    return REVIVED if reviving else KEPT


def _live_repair_cards_by_unit(tenant_id: int, unit_ids) -> list:
    """بطاقات الإصلاح الحيّة للوحدات، مقرونةً بـ`pk` وحدتها: `[(card, unit_pk)]`.

    بطاقة الإصلاح لا تحمل مفتاح الوحدة (تُنشأ من أمر صيانةٍ يعرف الرقم التسلسلي نصّاً)،
    فتُطابَق على (الرقم، المنتج) — الوحدة نفسها إن حمل الأمر منتجاً، وبالرقم وحده إن لم يحمل.
    """
    from inventory.models import ProductSerial

    units = list(
        ProductSerial.objects
        .filter(tenant_id=tenant_id, pk__in=list(unit_ids))
        .values_list("pk", "serial", "product_id")
    )
    if not units:
        return []
    cards = WarrantyCard.objects.filter(
        tenant_id=tenant_id, source=WarrantyCard.SOURCE_REPAIR,
        ended_on__isnull=True, serial__in={serial for _pk, serial, _product in units},
    )
    matched = []
    for card in cards:
        for unit_pk, serial, product_id in units:
            if card.serial == serial and card.product_id in (None, product_id):
                matched.append((card, unit_pk))
                break
    return matched


def _supersede_stale_cards(invoice, unit_ids: list[int]) -> int:
    """شفاءٌ ذاتي: بطاقةٌ تلقائية حيّة لهذه الوحدة على فاتورةٍ **أخرى** تُنهى.

    تُغطّي مرجعاً وقع والوحدة مطفأة، وبياناتٍ قديمة انقطعت مرساتها. البطاقة
    **اليدوية لا تُمَسّ**: صاحبها كتبها بيده ولا علاقة لترحيلنا بها. وكفالة
    الإصلاح (#244) تُحَلّ محلّها إعادةُ البيع كذلك: زبونٌ جديد لا يرث إصلاح سابقه.
    """
    repair_ids = [
        card.pk for card, _unit in _live_repair_cards_by_unit(invoice.tenant_id, unit_ids)
    ]
    repair_ended = (
        WarrantyCard.objects.filter(pk__in=repair_ids).update(
            ended_on=invoice.invoice_date, end_reason=WarrantyCard.END_SUPERSEDED,
        )
        if repair_ids else 0
    )
    ended = repair_ended + (
        WarrantyCard.objects
        .filter(
            tenant_id=invoice.tenant_id,
            source=WarrantyCard.SOURCE_AUTO_SALE,
            product_serial_id__in=unit_ids,
            ended_on__isnull=True,
        )
        .exclude(sales_invoice=invoice)
        .update(
            ended_on=invoice.invoice_date,
            end_reason=WarrantyCard.END_SUPERSEDED,
        )
    )
    if ended:
        logger.info(
            "after_sales.warranty_cards_superseded invoice=%s tenant=%s cards=%d",
            invoice.pk, invoice.tenant_id, ended,
        )
    return ended


def _policy_manufacturer_layer(policy, invoice_date) -> dict:
    """طبقة المصنع من السياسة وحدها — خطوة (٣) في `_resolve_manufacturer_layer`،
    وهي أيضاً المصدر **الوحيد** لبطاقة الفاتورة (#234): لا وحدة واحدة تحمل
    بطاقةً سابقة تُنسَخ منها (خطوة ١)، فلا معنى لخطوتَي الوحدة هناك أصلاً.

    تقبل أيَّ كائنٍ بحقلَي `manufacturer_warrantor_id`/`manufacturer_months`؛
    فصفّ سطر الشراء (خطوة ٢) يمرّ من الدالة نفسها بلا نسخةٍ ثانية من المنطق.
    """
    if policy is not None and policy.manufacturer_warrantor_id:
        return {
            "manufacturer_warrantor_id": policy.manufacturer_warrantor_id,
            "manufacturer_start_date": invoice_date,
            "manufacturer_duration_months": policy.manufacturer_months,
            "manufacturer_end_date": add_months(invoice_date, policy.manufacturer_months),
        }
    return {
        "manufacturer_warrantor_id": None,
        "manufacturer_start_date": None,
        "manufacturer_duration_months": 0,
        "manufacturer_end_date": None,
    }


def _resolve_manufacturer_layer(
    tenant_id: int, units: list, policies: dict, invoice_date,
) -> dict:
    """طبقة المصنع لكل وحدة **جديدة**، دفعة واحدة — استعلامٌ واحد لا لكل وحدة (#232).

    الترتيب:
      1. **آخر بطاقة تلقائية سابقة لهذه الوحدة نفسها** (إعادة بيع) — تُنسخ
         كما هي حرفياً (الجهة والبداية والمدة والنهاية)، حتى لو انتهت تلك
         البطاقة `returned` أو `superseded`: طبقة المصنع ملكُ الجهاز لا صاحبه.
         **لا تصلح مصدراً** بطاقةٌ انتهت `sale_cancelled` (مسودّة بيعها
         حُذفت — بيعها لم يقع أصلاً) أو `invoice_unposted` (بيعها معلَّقٌ،
         غير نافذ الآن): تُتجاوَزان إلى بطاقةٍ أقدم مؤهَّلة لنفس الوحدة، لا
         إلى فراغ — الجهاز نفسه قد يحمل تاريخاً أصدق خلفهما.
      2. **سطر شراء الوحدة** (`PurchaseLineWarranty` على `unit.purchase_item`،
         #235) — استعلامٌ واحد للدفعة. الصفّ حاضرٌ ⇒ هو الجواب حتى لو جهته
         فارغة (صراحةً «لا يوجد» ولو كانت السياسة تذكر جهة)، وبدايته تاريخ
         فاتورة البيع كالسياسة. وصفٌّ غائب (سطرٌ من تخليص أو أمرٍ أو نسخٍ أو
         مرتجع، أو الشراء قبل #235) ⇒ الخطوة التالية.
      3. **السياسة نفسها** (`manufacturer_warrantor`/`manufacturer_months`)،
         ببداية تاريخ الفاتورة — وحدها إن غابت الجهة («لا يوجد») أو لم تبقَ
         بطاقةٌ سابقة مؤهَّلة.

    ويحمل كلُّ ناتجٍ مفتاحاً إضافياً `supplier_months`: مدة كفالة المورّد
    لهذه الوحدة (`supplier_months` السطر إن ذُكرت، وإلا السياسة). تُحلّ من
    الاستعلام نفسه بصرف النظر عن مصدر طبقة المصنع — فالنسخ من بطاقةٍ سابقة
    يخصّ المصنع وحده، وطرف المورّد يُحتسب دائماً من شراء هذه الوحدة.
    """
    unit_ids = [u.pk for u in units]
    item_ids = [u.purchase_item_id for u in units if u.purchase_item_id]
    line_rows = {}
    if item_ids:
        line_rows = {
            row.purchase_item_id: row
            for row in PurchaseLineWarranty.objects.filter(
                tenant_id=tenant_id, purchase_item_id__in=item_ids,
            )
        }
    previous_by_unit = {}
    if unit_ids:
        for card in (
            WarrantyCard.objects
            .filter(
                tenant_id=tenant_id,
                source=WarrantyCard.SOURCE_AUTO_SALE,
                product_serial_id__in=unit_ids,
            )
            # بيعٌ لم يقف لا يصلح مصدراً — استبعادٌ في الاستعلام نفسه فيبقى
            # واحداً، ويسقط تلقائياً إلى الصفّ الأقدم المؤهَّل التالي.
            .exclude(end_reason__in=[
                WarrantyCard.END_SALE_CANCELLED, WarrantyCard.END_INVOICE_UNPOSTED,
            ])
            .order_by("product_serial_id", "-id")
        ):
            previous_by_unit.setdefault(card.product_serial_id, card)

    layers = {}
    for unit in units:
        policy = policies.get(unit.product_id)
        line = line_rows.get(unit.purchase_item_id)
        previous = previous_by_unit.get(unit.pk)
        if previous is not None:
            layer = {
                "manufacturer_warrantor_id": previous.manufacturer_warrantor_id,
                "manufacturer_start_date": previous.manufacturer_start_date,
                "manufacturer_duration_months": previous.manufacturer_duration_months,
                "manufacturer_end_date": previous.manufacturer_end_date,
            }
        elif line is not None:
            layer = _policy_manufacturer_layer(line, invoice_date)
        else:
            layer = _policy_manufacturer_layer(policy, invoice_date)
        if line is not None and line.supplier_months is not None:
            layer["supplier_months"] = line.supplier_months
        else:
            layer["supplier_months"] = policy.supplier_months if policy is not None else 0
        layers[unit.pk] = layer
    return layers


def create_auto_warranty_cards(invoice) -> int:
    """يُحيي بطاقات هذه الفاتورة المعلَّقة، ثم يُنشئ ما ينقص من وحداتها.

    البداية = **تاريخ الفاتورة** لا تاريخ الترحيل ولا التسليم: تاريخ المستند هو
    ما تُقيَّد به الدفاتر كلها، وحالة التسليم مشتقّة وقد تغيب أصلاً.

    غير المتسلسل بسياسة `serial` لا بطاقة تلقائية له: كمية بلا هوية وحدة تجعل
    البطاقة بلا معنى، والتغطية تُفحص عندها من فاتورة الزبون لحظة الاستقبال.
    أما `method=invoice` (#234) فبطاقة كمية واحدة **لكل (فاتورة، منتج)** —
    بلا `product_serial`، ومطابقتها عند الإحياء على المنتج لا على وحدة.

    **المطابقة على `(sales_invoice, product_serial)` لا على البند**: تعديل
    المسودّة بين الإلغاء وإعادة الترحيل يحذف البنود التي تُرسَل بلا `id`، فتبقى
    الفاتورة وحدها مرساةً صامدة. وما بقي معلَّقاً بعد الإحياء (وحدةٌ استُبدلت أو
    بندٌ حُذف) يصير `sale_cancelled`: البيع الذي وَلَّده لم يعد قائماً.

    وحارس «بطاقة حيّة واحدة لكل وحدة» صار مقيَّداً بهذه الفاتورة: كان مطلقاً
    فمنع المشتري الثاني لوحدةٍ أُرجعت من أن يأخذ شهادته أصلاً.
    """
    from inventory.models import ProductSerial
    from inventory.services import product_display_name

    if not module_enabled(invoice.tenant_id, MODULE_KEY):
        return 0

    units = list(
        ProductSerial.objects
        .filter(
            tenant_id=invoice.tenant_id,
            sales_line__invoice=invoice,
            status=ProductSerial.STATUS_SOLD,
        )
        .select_related("product", "purchase_item__invoice")
        .order_by("id")
    )
    customer = invoice.customer if invoice.customer_id else None
    unit_ids = [u.pk for u in units]

    # ١) الإحياء أولاً — بطاقةٌ لهذه الوحدة على هذه الفاتورة تعود بنفسها.
    existing = {
        card.product_serial_id: card
        for card in _invoice_cards(invoice).filter(product_serial_id__in=unit_ids)
    }
    revived = 0
    carried = set()
    carried_card_ids = set()
    for unit in units:
        card = existing.get(unit.pk)
        if card is None:
            continue
        outcome = _revive(card, invoice, unit, customer)
        if outcome == REFUSED:
            continue  # واقعتها أصدق من هذا الترحيل — والوحدة تأخذ بطاقةً جديدة
        if outcome == REVIVED:
            revived += 1
        carried.add(unit.pk)
        carried_card_ids.add(card.pk)

    # #234: بطاقات «كفالة على الفاتورة» — تُحيا هي أيضاً هنا، بمطابقة المنتج
    # لا وحدة (بلا `product_serial` أصلاً). كمية كل منتج = مجموع بنوده الحالية.
    line_qty_by_product = {}
    for line in invoice.lines.all():
        line_qty_by_product[line.product_id] = (
            line_qty_by_product.get(line.product_id, 0) + line.quantity
        )
    invoice_policies = {}
    if line_qty_by_product:
        invoice_policies = {
            policy.product_id: policy
            for policy in WarrantyPolicy.objects.filter(
                tenant_id=invoice.tenant_id,
                product_id__in=list(line_qty_by_product),
                method=WarrantyPolicy.METHOD_INVOICE,
            ).select_related("product")
        }
    # #234-review (٣): الحقل عددٌ صحيح دائماً — `int()` كان يقصّ كسر منتجٍ
    # بيع بكميةٍ كسرية (كيلوغرامات مثلاً) صامتاً فتكذب البطاقة على كميتها.
    # يُرفَض الترحيل بوضوح بدل ذلك، لا لكل بند بل لمجموع بنود المنتج نفسه.
    for product_id, policy in invoice_policies.items():
        total = line_qty_by_product[product_id]
        if total % 1 != 0:
            raise ValidationError(
                f"المنتج «{product_display_name(policy.product)}»: كفالة الفاتورة "
                f"تتطلب كميةً صحيحة، وهذا المنتج بكمية {total} على الفاتورة."
            )
    line_qty_by_product = {
        product_id: int(total) for product_id, total in line_qty_by_product.items()
    }
    # #234-review (١ب): الإحياء يطابق **بطاقةً موجودة لهذا المنتج على هذه
    # الفاتورة** بصرف النظر عن سياسته الحالية — سياسةٌ عُدِّلت أو حُذفت بعد
    # البيع لا تُسقط بطاقةً صُرفت أيام كانت `invoice`. السياسة الحالية
    # (`invoice_policies` أعلاه) تقرّر وحدها إنشاء بطاقةٍ **جديدة** أسفله
    # (`new_invoice_products`)، لا إحياء القائم.
    existing_invoice_cards = {
        card.product_id: card
        for card in _invoice_cards(invoice).filter(
            product_serial__isnull=True, product_id__in=list(line_qty_by_product),
        )
    }
    invoice_revived = 0
    carried_products = set()
    for product_id, card in existing_invoice_cards.items():
        outcome = _revive_invoice_card(
            card, invoice, customer, line_qty_by_product[product_id],
        )
        if outcome == REFUSED:
            continue  # منتهيةٌ بمرجعٍ — واقعتها أصدق، ومنتجها يأخذ بطاقةً جديدة
        if outcome == REVIVED:
            invoice_revived += 1
        carried_products.add(product_id)
        carried_card_ids.add(card.pk)

    # ٢) ما بقي معلَّقاً على هذه الفاتورة لم يعد له بيعٌ يحمله.
    cancelled = (
        _invoice_cards(invoice)
        .filter(end_reason=WarrantyCard.END_INVOICE_UNPOSTED)
        .exclude(pk__in=carried_card_ids)
        .update(end_reason=WarrantyCard.END_SALE_CANCELLED)
    )

    # ٣) الوحدات الجديدة: شفاءٌ ذاتي لبطاقةٍ قديمة حيّة، ثم بطاقةٌ لهذا الزبون.
    fresh = [u for u in units if u.pk not in carried]
    if fresh:
        _supersede_stale_cards(invoice, [u.pk for u in fresh])

    # #231: السياسة وحدها تقرّر وجود البطاقة — استعلامٌ واحد لكل منتجات
    # الوحدات الجديدة، لا استعلامٌ لكل وحدة. لا صفّ = لا بطاقة.
    policies = {
        policy.product_id: policy
        for policy in WarrantyPolicy.objects.filter(
            tenant_id=invoice.tenant_id,
            product_id__in={u.product_id for u in fresh},
        )
    }
    # #234: منتجات «الفاتورة» الجديدة — من طُلبت بطاقتها ولم تُحيَ (منتجٌ لم
    # يكن له صفّ، أو صفّه انتهى بمرجعٍ فلا يُحيا).
    new_invoice_products = set(invoice_policies) - carried_products
    settings_row = (
        get_or_create_after_sales_settings(invoice.tenant_id)
        if (policies or new_invoice_products) else None
    )
    # #232: طبقة المصنع لكل الوحدات الجديدة معاً — استعلامٌ واحد للدفعة، لا
    # واحد لكل وحدة (`_resolve_manufacturer_layer`).
    manufacturer_layers = (
        _resolve_manufacturer_layer(invoice.tenant_id, fresh, policies, invoice.invoice_date)
        if fresh else {}
    )

    created = []
    for unit in fresh:
        policy = policies.get(unit.product_id)
        if policy is None:
            continue
        manufacturer_layer = manufacturer_layers.get(unit.pk, {})
        supplier_id, supplier_end = _supplier_side(
            unit, manufacturer_layer.get("supplier_months", policy.supplier_months),
        )
        terms_text = policy.terms_override or settings_row.default_terms
        created.append(WarrantyCard(
            tenant_id=invoice.tenant_id,
            product=unit.product,
            # #42: `product_display_name` لا `str(product)` — بطاقةٌ مجمَّدة من الآن
            # فصاعداً بلا backfill (قرار #38 نفسه)؛ قصٌّ بحدّ العمود يتّبع عادة
            # `customer_name[:150]`/`customer_phone[:32]` المجاورتين لا اختراعاً.
            device_name=product_display_name(unit.product)[
                :WarrantyCard._meta.get_field('device_name').max_length
            ],
            serial=unit.serial,
            product_serial=unit,
            sales_invoice=invoice,
            sales_invoice_line_id=unit.sales_line_id,
            partner_id=invoice.customer_id,
            customer_name=(customer.name if customer else "")[:150],
            customer_phone=(getattr(customer, "phone", "") or "")[:32] if customer else "",
            start_date=invoice.invoice_date,
            duration_months=policy.dealer_months,
            end_date=add_months(invoice.invoice_date, policy.dealer_months),
            source=WarrantyCard.SOURCE_AUTO_SALE,
            supplier_id=supplier_id,
            supplier_warranty_end_date=supplier_end,
            terms_text=terms_text,
            manufacturer_warrantor_id=manufacturer_layer.get("manufacturer_warrantor_id"),
            manufacturer_start_date=manufacturer_layer.get("manufacturer_start_date"),
            manufacturer_duration_months=manufacturer_layer.get("manufacturer_duration_months") or 0,
            manufacturer_end_date=manufacturer_layer.get("manufacturer_end_date"),
        ))

    # #234: بطاقات فاتورة جديدة — منتجٌ عليه سياسة `invoice` لم تُحيَ بطاقته.
    for product_id in new_invoice_products:
        policy = invoice_policies[product_id]
        manufacturer_layer = _policy_manufacturer_layer(policy, invoice.invoice_date)
        terms_text = policy.terms_override or settings_row.default_terms
        created.append(WarrantyCard(
            tenant_id=invoice.tenant_id,
            product_id=product_id,
            device_name=product_display_name(policy.product)[
                :WarrantyCard._meta.get_field('device_name').max_length
            ],
            sales_invoice=invoice,
            partner_id=invoice.customer_id,
            customer_name=(customer.name if customer else "")[:150],
            customer_phone=(getattr(customer, "phone", "") or "")[:32] if customer else "",
            start_date=invoice.invoice_date,
            duration_months=policy.dealer_months,
            end_date=add_months(invoice.invoice_date, policy.dealer_months),
            source=WarrantyCard.SOURCE_AUTO_SALE,
            quantity=line_qty_by_product[product_id],
            terms_text=terms_text,
            manufacturer_warrantor_id=manufacturer_layer["manufacturer_warrantor_id"],
            manufacturer_start_date=manufacturer_layer["manufacturer_start_date"],
            manufacturer_duration_months=manufacturer_layer["manufacturer_duration_months"],
            manufacturer_end_date=manufacturer_layer["manufacturer_end_date"],
        ))

    if created:
        for card in created:
            card.phone_key = phone_key_of(card.customer_phone)  # bulk_create لا يمرّ بـsave()
        WarrantyCard.objects.bulk_create(created)
    total_revived = revived + invoice_revived
    if created or total_revived or cancelled:
        logger.info(
            "after_sales.warranty_cards_synced invoice=%s tenant=%s "
            "created=%d revived=%d cancelled=%d",
            invoice.pk, invoice.tenant_id, len(created), total_revived, cancelled,
        )
    return len(created)


def on_sale_unposted(invoice) -> int:
    """إلغاء ترحيل البيع **يُعلّق** بطاقاته الحيّة ولا يحذف واحدة.

    البطاقة المنتهية بمرجعٍ لا تُمَسّ: واقعتها أصدق من هذه، ولا يجوز أن يمحوها
    إلغاءُ ترحيلٍ ثم يعيدها الترحيل «سارية» لزبونٍ أعاد جهازه.
    """
    if not module_enabled(invoice.tenant_id, MODULE_KEY):
        return 0
    suspended = _invoice_cards(invoice).filter(ended_on__isnull=True).update(
        ended_on=timezone.localdate(),
        end_reason=WarrantyCard.END_INVOICE_UNPOSTED,
    )
    if suspended:
        logger.info(
            "after_sales.warranty_cards_suspended invoice=%s tenant=%s cards=%d",
            invoice.pk, invoice.tenant_id, suspended,
        )
    return suspended


def on_sale_cancelled(invoice) -> int:
    """حذف مسودّة الفاتورة: بطاقاتها المعلَّقة لن يعود لها بيعٌ أبداً."""
    if not module_enabled(invoice.tenant_id, MODULE_KEY):
        return 0
    cancelled = (
        _invoice_cards(invoice)
        .filter(end_reason=WarrantyCard.END_INVOICE_UNPOSTED)
        .update(end_reason=WarrantyCard.END_SALE_CANCELLED)
    )
    if cancelled:
        logger.info(
            "after_sales.warranty_cards_cancelled invoice=%s tenant=%s cards=%d",
            invoice.pk, invoice.tenant_id, cancelled,
        )
    return cancelled


def on_sales_return_posted(return_invoice) -> int:
    """مرجع البيع يُنهي بطاقات **الوحدات المرتجعة وحدها** على فاتورتها الأصلية.

    الوحدة المرتجعة تُعرف من `ProductSerial.return_line` الذي كتبه
    `inventory/serials.py` (`restore_returned_sales_serials`) للتوّ — لا من
    كميات المرجع ولا من ترتيبٍ مُخمَّن. فالمرجع الجزئي يمسّ ما أُرجع فعلاً،
    وبقية البطاقات تبقى سارية.

    مرجعٌ بلا فاتورة أصلية لا وحدة تُستعاد فيه، فلا بطاقة تُمسّ — سلوك المخزون
    نفسه.

    **بطاقات «كفالة على الفاتورة» (#234)** تُمسّ هنا أيضاً — لا بواقعة انتهاءٍ
    مباشرة كالوحدة المُرقَّمة، بل بزيادة `returned_quantity` بقدر الكمية
    المُرجَعة من كل منتج؛ البطاقة لا تُنهى `returned` إلا حين تبلغ الكمية
    المُرجَعة كامل كمية البطاقة (`_apply_invoice_card_return`).
    """
    from inventory.models import ProductSerial

    if not module_enabled(return_invoice.tenant_id, MODULE_KEY):
        return 0
    original_id = getattr(return_invoice, "original_invoice_id", None)
    if not original_id:
        return 0

    return_line_by_unit = dict(
        ProductSerial.objects
        .filter(
            tenant_id=return_invoice.tenant_id,
            return_line__invoice=return_invoice,
        )
        .values_list("pk", "return_line_id")
    )
    cards = []
    if return_line_by_unit:
        cards = list(
            WarrantyCard.objects
            .filter(
                tenant_id=return_invoice.tenant_id,
                product_serial_id__in=list(return_line_by_unit),
                ended_on__isnull=True,
            )
            .filter(
                Q(sales_invoice_id=original_id)
                | Q(sales_invoice_line__invoice_id=original_id)
            )
        )
        for card in cards:
            card.ended_on = return_invoice.invoice_date
            card.end_reason = WarrantyCard.END_RETURNED
            card.end_return_line_id = return_line_by_unit[card.product_serial_id]
            card.save(update_fields=[
                "ended_on", "end_reason", "end_return_line", "updated_at",
            ])
        if cards:
            logger.info(
                "after_sales.warranty_cards_returned return=%s original=%s tenant=%s cards=%d",
                return_invoice.pk, original_id, return_invoice.tenant_id, len(cards),
            )
        # #244: كفالة الإصلاح على الوحدة المرتجعة تنتهي معها؛ `end_return_line` هو ما يُحييها
        # عند إلغاء ترحيل المرجع (`on_sales_return_unposted`) فلا مسار موازٍ.
        for card, unit_pk in _live_repair_cards_by_unit(
            return_invoice.tenant_id, list(return_line_by_unit),
        ):
            card.ended_on = return_invoice.invoice_date
            card.end_reason = WarrantyCard.END_RETURNED
            card.end_return_line_id = return_line_by_unit[unit_pk]
            card.save(update_fields=[
                "ended_on", "end_reason", "end_return_line", "updated_at",
            ])
            cards.append(card)

    invoice_touched = _apply_invoice_card_return(return_invoice, original_id, reverse=False)
    return len(cards) + invoice_touched


def on_sales_return_unposted(return_invoice) -> int:
    """إلغاء ترحيل المرجع يُحيي ما أنهاه هو وحده — بدلالة `end_return_line`.

    ولا سباق على وحدةٍ بِيعت ثانيةً: الحارس القائم
    (`inventory/serials.py` — `revert_returned_sales_serials`) يرفض الإلغاء
    أصلاً قبل أن نصل إلى هنا.

    وبطاقات «كفالة على الفاتورة» (#234) تُنقَص كميتها المُرجَعة بالمقدار نفسه
    الذي أضافه ترحيل هذا المرجع — تناظرٌ تامّ، لا حساب ثانٍ.
    """
    if not module_enabled(return_invoice.tenant_id, MODULE_KEY):
        return 0
    revived = WarrantyCard.objects.filter(
        tenant_id=return_invoice.tenant_id,
        end_return_line__invoice=return_invoice,
    ).update(ended_on=None, end_reason="", end_return_line=None)
    if revived:
        logger.info(
            "after_sales.warranty_cards_unreturned return=%s tenant=%s cards=%d",
            return_invoice.pk, return_invoice.tenant_id, revived,
        )

    original_id = getattr(return_invoice, "original_invoice_id", None)
    invoice_revived = _apply_invoice_card_return(return_invoice, original_id, reverse=True)
    return revived + invoice_revived


def _apply_invoice_card_return(return_invoice, original_id, *, reverse: bool) -> int:
    """يُطبّق أثر مرجع بيعٍ على بطاقات «كفالة على الفاتورة» — ترحيلاً وتراجعاً.

    #234-review (١أ): البطاقات تُطلَب أولاً **بمرساة الفاتورة الأصلية وحدها**
    (`sales_invoice_id=original_id`) — لا بسياسة المنتج الحالية: سياسةٌ عُدِّلت
    أو حُذفت بعد البيع لا يجوز أن توقف مرجعاً عن إنقاص بطاقةٍ صُرفت أيام كانت
    `invoice`. كمية كل منتج تُحسَب بعدها من بنود **مرجع البيع نفسه** لهذه
    المنتجات وحدها، في كلا الاتجاهين — تناظرٌ تامّ بين الترحيل والتراجع، على
    نمط استهلاك الوحدات المُرقَّمة وإعادتها. بلوغ `returned_quantity` كاملَ
    `quantity` يُنهي البطاقة `returned`، والتراجع الذي يُعيد فتح تغطيةٍ يُعيدها
    سارية.

    #234-review (٢): لا قصّ (`min`) على الزيادة — الحارس الخادميّ
    `guard_sales_return_quantities` (`sales/services/flow.py`، T-RETQTY) يمنع
    أي مرجعٍ من تجاوز القابل للإرجاع من الفاتورة الأصلية **عند كل حفظ لبنوده**،
    عبر كل مراجيعها الشقيقة معاً (مسودةً أو مرحّلة)، فتجاوز `returned_quantity`
    لـ`quantity` هنا مستحيلٌ بالبناء لا حالةٌ تُقاس. القصّ كان يخفي عدم تناظرٍ
    كامن: لو فعلاً قُصّت الزيادة يوماً لأعاد التراجع فتح تغطيةٍ أكبر مما أُنقص.
    بلا قصٍّ، حدث الاتجاهين يحمل الكمية المُطبَّقة فعلاً دائماً.

    كل استدعاء يكتب حدثاً جزئياً واحداً لكل بطاقةٍ مسّها — `ended` عند الزيادة
    (ولو بقيت التغطية جزئياً)، و`revived` عند الإنقاص.
    """
    if not original_id:
        return 0

    cards = {
        card.product_id: card
        for card in WarrantyCard.objects.filter(
            tenant_id=return_invoice.tenant_id,
            source=WarrantyCard.SOURCE_AUTO_SALE,
            product_serial__isnull=True,
            sales_invoice_id=original_id,
        )
    }
    if not cards:
        return 0

    from inventory.services import product_display_name

    rows = (
        return_invoice.lines
        .filter(product_id__in=list(cards))
        .values("product_id")
        .annotate(total=Sum("quantity"))
    )
    # #234-review (٣): نفس رفض الكسر عند الترحيل — مرتجعٌ بكميةٍ كسرية لمنتج
    # بطاقة فاتورة يُرفَض بوضوح بدل أن يُقصّ `int()` كسره صامتاً.
    quantity_by_product = {}
    for row in rows:
        total = row["total"]
        if not total:
            continue
        if total % 1 != 0:
            card = cards[row["product_id"]]
            raise ValidationError(
                f"المنتج «{product_display_name(card.product)}»: كفالة الفاتورة "
                f"تتطلب كميةً صحيحة على مرجع البيع، وهذا السطر بكمية {total}."
            )
        quantity_by_product[row["product_id"]] = int(total)
    if not quantity_by_product:
        return 0

    touched = 0
    for product_id, quantity in quantity_by_product.items():
        card = cards[product_id]
        if reverse:
            was_ended = (
                card.ended_on is not None and card.end_reason == WarrantyCard.END_RETURNED
            )
            card.returned_quantity = max(0, card.returned_quantity - quantity)
            fields = ["returned_quantity", "updated_at"]
            if was_ended and card.returned_quantity < card.quantity:
                card.ended_on = None
                card.end_reason = ""
                fields += ["ended_on", "end_reason"]
            card.save(update_fields=fields)
            log_warranty_event(
                card, event_type=WarrantyCardEvent.TYPE_REVIVED, quantity=quantity,
            )
        else:
            card.returned_quantity = card.returned_quantity + quantity
            fields = ["returned_quantity", "updated_at"]
            if card.returned_quantity >= card.quantity and card.ended_on is None:
                card.ended_on = return_invoice.invoice_date
                card.end_reason = WarrantyCard.END_RETURNED
                fields += ["ended_on", "end_reason"]
            card.save(update_fields=fields)
            log_warranty_event(
                card, event_type=WarrantyCardEvent.TYPE_ENDED, quantity=quantity,
            )
        touched += 1

    if touched:
        logger.info(
            "after_sales.warranty_card_quantity_%s return=%s original=%s tenant=%s cards=%d",
            "reversed" if reverse else "returned",
            return_invoice.pk, original_id, return_invoice.tenant_id, touched,
        )
    return touched


# ══════════════════════════════════════════════════════════════════════════
# فحص التغطية — الجواب الواحد على «هل هذه الوحدة تحت الكفالة؟»
# ══════════════════════════════════════════════════════════════════════════

def _card_summary(card, today: date) -> dict:
    return {
        "id": card.pk,
        "serial": card.serial,
        "product": card.product_id,
        "device_name": card.device_name,
        "start_date": card.start_date,
        "end_date": card.end_date,
        "duration_months": card.duration_months,
        "source": card.source,
        "source_label": card.get_source_display(),
        "coverage_scope": card.coverage_scope,
        "origin_order_number": (
            card.origin_service_order.order_number if card.origin_service_order_id else ""
        ),
        "status": card.status_on(today),
        "days_remaining": card.days_remaining(today),
        "customer_name": card.customer_name,
        "partner": card.partner_id,
        "supplier": card.supplier_id,
        "supplier_warranty_end_date": card.supplier_warranty_end_date,
        "supplier_warranty_active": card.supplier_active_on(today),
        # #232: طبقة المصنع — مستقلةٌ عن طبقة التاجر أعلاه، و`None` صراحةً حين
        # لا جهة («لا يوجد») لا فراغ بيانات.
        "manufacturer_warrantor": card.manufacturer_warrantor_id,
        "manufacturer_warrantor_name": (
            card.manufacturer_warrantor.name if card.manufacturer_warrantor_id else ""
        ),
        "manufacturer_start_date": card.manufacturer_start_date,
        "manufacturer_duration_months": card.manufacturer_duration_months,
        "manufacturer_end_date": card.manufacturer_end_date,
        "manufacturer_status": card.manufacturer_status_on(today),
        "manufacturer_days_remaining": card.manufacturer_days_remaining(today),
        # #234: بطاقة الفاتورة — صفرٌ على بطاقة وحدة مُرقَّمة (لا معنى له هناك).
        "quantity": card.quantity,
        "returned_quantity": card.returned_quantity,
        "covered_quantity": card.covered_quantity,
    }


def replacement_summary(old_card) -> dict:
    """«استُبدل بـ…» لبطاقةٍ انتهت بالاستبدال — للموظف وحده، لا للصفحة العامة (#245).

    يتطلب `select_related("replaced_by__replacement_order")` كي لا يستعلم لكل بطاقة.
    """
    new = old_card.replaced_by
    order = new.replacement_order if new.replacement_order_id else None
    return {
        "card": new.pk,
        "serial": new.serial,
        "date": old_card.ended_on,
        "order_number": order.order_number if order else "",
    }


def warranty_coverage(tenant_id: int, serial: str, today: date | None = None) -> dict:
    """التغطية بحسب رقم تسلسلي واحد — البطاقة أولاً، ثم نسب الوحدة.

    وحدةٌ بعناها قبل ترخيص الوحدة (أو منتجٌ بلا سياسة كفالة) لا بطاقة لها؛ نردّ
    عندها ما نعرفه عن الوحدة نفسها (منتجها وفاتورتها وزبونها) كي يقرّر موظف
    الاستقبال بدل أن يرى «غير موجود» على وحدةٍ بعناها بأنفسنا.

    **والمنتهية بواقعة لا تُعدّ تغطية** (#222): جهازٌ أُرجع، أو بيعٌ أُلغي
    ترحيله، ليس مكفولاً عندنا مهما بقي من مدّته — وهذه هي النقطة التي كان
    الاستقبال يقول منها «مغطّى» عن وحدةٍ راجعة في المخزن.
    """
    from inventory.models import ProductSerial
    from inventory.services import product_display_name

    today = today or timezone.localdate()
    serial = (serial or "").strip()
    if not serial:
        return {
            "serial": "", "covered": False, "repair_covered": False, "cards": [], "unit": None,
            "replaced_by": None,
        }

    # #245: البطاقة المستبدَلة منتهيةٌ لكنها تُقرأ هنا لتقول «استُبدل بـ…» — في الاستعلام
    # نفسه (لا استعلامَ إضافياً على مسار المسح الساخن)، ولا تدخل قائمة `cards`.
    rows = list(
        WarrantyCard.objects
        .filter(tenant_id=tenant_id, serial=serial)
        .filter(Q(ended_on__isnull=True) | Q(replaced_by__isnull=False))
        .select_related(
            "product", "manufacturer_warrantor", "origin_service_order",
            "replaced_by__replacement_order",
        )
        .order_by("-end_date", "-id")
    )
    cards = [c for c in rows if c.ended_on is None]
    replaced_by = next(
        (replacement_summary(c) for c in rows if getattr(c, "replaced_by", None)), None,
    )
    unit = (
        ProductSerial.objects
        .filter(tenant_id=tenant_id, serial=serial)
        .select_related("product", "sales_line__invoice__customer")
        .order_by("-id")
        .first()
    )

    unit_info = None
    if unit is not None:
        # وحدةٌ في المخزن ليست لزبون ولو بقي أثرُ بيعها الأصلي بعد مرجعه
        # (`inventory/serials.py` — `restore_returned_sales_serials`).
        sales_line = (
            unit.sales_line
            if unit.sales_line_id and unit.status == ProductSerial.STATUS_SOLD
            else None
        )
        sales_invoice = (
            sales_line.invoice if (sales_line and sales_line.invoice_id) else None
        )
        # #231: المدد لم تعد على المنتج — السياسة، إن وُجدت، هي المصدر.
        policy = (
            WarrantyPolicy.objects
            .filter(tenant_id=tenant_id, product_id=unit.product_id)
            .first()
        )
        unit_info = {
            "id": unit.pk,
            "serial": unit.serial,
            "status": unit.status,
            "status_display": unit.get_status_display(),
            "product": unit.product_id,
            "product_name": product_display_name(unit.product),
            "dealer_months": policy.dealer_months if policy else None,
            "supplier_months": policy.supplier_months if policy else None,
            "sales_invoice": sales_invoice.pk if sales_invoice else None,
            "sales_invoice_number": (
                sales_invoice.invoice_number if sales_invoice else None
            ),
            "sale_date": sales_invoice.invoice_date if sales_invoice else None,
            "customer_name": (
                sales_invoice.customer.name
                if sales_invoice and sales_invoice.customer_id else None
            ),
        }

    summaries = [_card_summary(c, today) for c in cards]
    repair_source = WarrantyCard.SOURCE_REPAIR
    # #244: كفالة الإصلاح لا تجعل الجهاز «مغطّى» — صاحبها يسأل عن العطل نفسه، لا عن كفالة البيع.
    return {
        "serial": serial,
        "covered": any(
            s["status"] == "active" and s["source"] != repair_source for s in summaries
        ),
        "repair_covered": any(
            s["status"] == "active" and s["source"] == repair_source for s in summaries
        ),
        "supplier_covered": any(s["supplier_warranty_active"] for s in summaries),
        "cards": summaries,
        "unit": unit_info,
        "replaced_by": replaced_by,
    }


# ══════════════════════════════════════════════════════════════════════════
# إلغاء كفالة التاجر ورفضها لهذا العطل وتقصيرها (#236)
# ══════════════════════════════════════════════════════════════════════════

MIN_UNDO_REASON_CHARS = 5
_VOID_REASON_LABELS = dict(WarrantyCard.VOID_REASON_CHOICES)


def _clean_void_reason(reason, note) -> tuple[str, str]:
    reason = (reason or "").strip()
    note = (note or "").strip()
    if reason not in _VOID_REASON_LABELS:
        raise ValidationError({"reason": "اختر سبباً من القائمة."})
    if reason == WarrantyCard.VOID_OTHER and not note:
        raise ValidationError({"note": "السبب «أخرى» يحتاج ملاحظةً تشرحه."})
    return reason, note


def _clean_undo_reason(reason) -> str:
    reason = (reason or "").strip()
    if len(reason) < MIN_UNDO_REASON_CHARS:
        raise ValidationError(
            {"reason": f"اكتب سبب التراجع ({MIN_UNDO_REASON_CHARS} أحرف على الأقل)."}
        )
    return reason


def _reason_text(reason: str, note: str) -> str:
    label = _VOID_REASON_LABELS.get(reason, reason)
    return f"{label} — {note}" if note else label


def _bill_price(part) -> tuple[Decimal, bool]:
    """(السعر، هل هو فارغ) — سعر الأمر إن وُجد، وإلا سعر بيع المنتج، وإلا صفر.

    يطابق ما تفعله الواجهة حين يحوّل الموظف قطعةً من «مغطاة» إلى «مفوترة».
    """
    unit = part.unit_price or Decimal("0")
    if unit > 0:
        return unit, False
    sale = getattr(part.product, "sale_price", None) if part.product_id else None
    if sale is not None and sale > 0:
        return sale, False
    return Decimal("0"), True


def _pending_covered_parts(order) -> list:
    return list(
        order.parts.select_related("product")
        .filter(billing="covered", materialized_at__isnull=True)
        .order_by("id")
    )


def _posted_covered_count(order) -> int:
    return order.parts.filter(billing="covered", materialized_at__isnull=False).count()


def _card_blocker(card) -> str:
    status = card.status_on()
    if status == WarrantyCard.STATUS_VOIDED:
        return "كفالة التاجر ملغاة أصلاً."
    if status == WarrantyCard.STATUS_ENDED:
        return "البطاقة منتهية — الكفالة لم تعد قائمة."
    return ""


def void_impact(card) -> dict:
    """ما سيحدث لو أُلغيت الكفالة الآن — المعاينة والتنفيذ يقرآن هذه الدالة نفسها.

    الأوامر المفتوحة وحدها (`delivered`/`cancelled` لا تُمسّ). أمرٌ فيه قطعٌ
    مغطاة **مرحّلة** يمنع الإلغاء كلَّه: ترحيلها قيدٌ ومخزونٌ لا يُقلَب بصمت.
    """
    from inventory.services import product_display_name

    from .service_orders import TERMINAL_STATUSES

    blockers = []
    card_blocker = _card_blocker(card)
    if card_blocker:
        blockers.append(card_blocker)

    rows = []
    open_orders = (
        ServiceOrder.objects
        .filter(tenant_id=card.tenant_id, warranty_card=card)
        .exclude(status__in=TERMINAL_STATUSES)
        .order_by("id")
    )
    for order in open_orders:
        posted = _posted_covered_count(order)
        if posted:
            blockers.append(
                f"الأمر {order.order_number or order.pk} فيه {posted} قطعة مغطاة مرحّلة — "
                "تراجع عن ترحيلها أولاً."
            )
        pending = _pending_covered_parts(order)
        if not (order.warranty_covered or pending):
            continue
        parts = []
        for part in pending:
            price, empty = _bill_price(part)
            parts.append({
                "id": part.pk,
                "product_name": product_display_name(part.product),
                "quantity": str(part.quantity),
                "unit_price": str(part.unit_price),
                "will_bill_price": str(price),
                "empty_price": empty,
            })
        rows.append({
            "id": order.pk,
            "order_number": order.order_number,
            "status": order.status,
            "status_label": order.get_status_display(),
            "returns_to_approval": order.status in (
                ServiceOrder.STATUS_IN_REPAIR, ServiceOrder.STATUS_READY,
            ),
            "parts": parts,
        })
    return {
        "card_id": card.pk,
        "can_void": not blockers,
        "blockers": blockers,
        "orders": rows,
    }


def _bill_order_parts(order, *, user, headline: str) -> str:
    """يُسقط تغطية الأمر: قطعه المغطاة غير المرحّلة تصير مفوترة، ويُسجَّل الأثر.

    موافقة الزبون كانت على إصلاحٍ مجاني — فأمرٌ في الإصلاح أو الجاهزية يعود إلى
    «بانتظار الموافقة» في الإلغاء والرفض معاً (قصة ٨٧).
    """
    from inventory.services import product_display_name

    from .service_orders import log_event, transition_status

    flipped = 0
    empty_names = []
    for part in _pending_covered_parts(order):
        price, empty = _bill_price(part)
        part.billing = "billable"
        part.unit_price = price
        part.save(update_fields=["billing", "unit_price"])
        flipped += 1
        if empty:
            empty_names.append(product_display_name(part.product))

    was_open_work = order.status in (
        ServiceOrder.STATUS_IN_REPAIR, ServiceOrder.STATUS_READY,
    )
    order.warranty_covered = False
    order.save(update_fields=["warranty_covered", "updated_at"])

    lines = [headline]
    if flipped:
        lines.append(f"{flipped} قطعة صارت مفوترة على الزبون بسعر البيع")
    if empty_names:
        lines.append(
            "بلا سعر (صفر): " + "، ".join(empty_names) + " — حدّد سعرها قبل الفوترة"
        )
    if was_open_work:
        transition_status(
            order, ServiceOrder.STATUS_AWAITING_APPROVAL, user=user,
            note="سقوط الكفالة يغيّر التكلفة على الزبون",
        )
        order = ServiceOrder.objects.get(pk=order.pk)
        order.approved_at = None
        order.approved_by = None
        order.save(update_fields=["approved_at", "approved_by", "updated_at"])
        lines.append("عاد الأمر إلى «بانتظار الموافقة» — يوافق الزبون على التكلفة من جديد")

    summary = " — ".join(lines)
    log_event(order, event_type=ServiceOrderEvent.TYPE_WARRANTY, text=summary, user=user)
    return summary


@transaction.atomic
def void_dealer_warranty(card, *, reason, note="", user=None, service_order=None):
    """يُلغي كفالة التاجر لهذه البطاقة (المصنع لا يُمسّ) ويُسقط تغطية أوامرها المفتوحة."""
    reason, note = _clean_void_reason(reason, note)
    card = WarrantyCard.objects.select_for_update().get(
        pk=card.pk, tenant_id=card.tenant_id,
    )
    if service_order is not None and (
        service_order.tenant_id != card.tenant_id
        or service_order.warranty_card_id != card.pk
    ):
        raise ValidationError({"service_order": "أمر الصيانة ليس على بطاقة الكفالة هذه."})

    impact = void_impact(card)
    if not impact["can_void"]:
        raise ValidationError(" • ".join(impact["blockers"]))

    headline = "أُلغيت كفالة التاجر — " + _reason_text(reason, note)
    for row in impact["orders"]:
        order = ServiceOrder.objects.select_for_update().get(
            pk=row["id"], tenant_id=card.tenant_id,
        )
        _bill_order_parts(order, user=user, headline=headline)

    card.voided_at = timezone.now()
    card.voided_by = user if (user is not None and getattr(user, "is_authenticated", False)) else None
    card.void_reason = reason
    card.void_note = note
    card.void_service_order = service_order
    card.save(update_fields=[
        "voided_at", "voided_by", "void_reason", "void_note", "void_service_order",
        "updated_at",
    ])
    log_warranty_event(
        card, event_type=WarrantyCardEvent.TYPE_VOID, reason_code=reason,
        text=_reason_text(reason, note), service_order=service_order, user=user,
    )
    logger.info(
        "after_sales.warranty_voided tenant=%s card=%s reason=%s orders=%s",
        card.tenant_id, card.pk, reason, len(impact["orders"]),
    )
    return card


@transaction.atomic
def unvoid_dealer_warranty(card, *, reason, user=None):
    """التراجع عن الإلغاء — القطع التي تحوّلت إلى مفوترة **لا** تعود مغطاة."""
    reason = _clean_undo_reason(reason)
    card = WarrantyCard.objects.select_for_update().get(
        pk=card.pk, tenant_id=card.tenant_id,
    )
    if card.voided_at is None:
        raise ValidationError("كفالة التاجر ليست ملغاة.")
    previous = _reason_text(card.void_reason, card.void_note)
    card.voided_at = None
    card.voided_by = None
    card.void_reason = ""
    card.void_note = ""
    card.void_service_order = None
    card.save(update_fields=[
        "voided_at", "voided_by", "void_reason", "void_note", "void_service_order",
        "updated_at",
    ])
    log_warranty_event(
        card, event_type=WarrantyCardEvent.TYPE_UNVOID,
        text=f"{reason} (سبب الإلغاء السابق: {previous})", user=user,
    )
    return card


def _lock_order_with_card(order):
    from .service_orders import TERMINAL_STATUSES

    order = ServiceOrder.objects.select_for_update().get(
        pk=order.pk, tenant_id=order.tenant_id,
    )
    if not order.warranty_card_id:
        raise ValidationError("الأمر غير مرتبط ببطاقة كفالة.")
    if order.status in TERMINAL_STATUSES:
        raise ValidationError(
            f"الأمر في حالة «{order.get_status_display()}» النهائية — لا يُعدَّل فيه."
        )
    return order, order.warranty_card


def order_coverage_refused(order, card) -> bool:
    """هل آخر حدثٍ (رفض/استعادة) لهذا الأمر على هذه البطاقة رفضٌ؟ — تقرؤها الاستعادة والواجهة."""
    last = (
        WarrantyCardEvent.objects
        .filter(
            tenant_id=card.tenant_id, card=card, service_order=order,
            event_type__in=[
                WarrantyCardEvent.TYPE_COVERAGE_REFUSED,
                WarrantyCardEvent.TYPE_COVERAGE_RESTORED,
            ],
        )
        .order_by("-created_at", "-id")
        .values_list("event_type", flat=True)
        .first()
    )
    return last == WarrantyCardEvent.TYPE_COVERAGE_REFUSED


@transaction.atomic
def refuse_order_coverage(order, *, reason, note="", user=None):
    """«رفض الكفالة لهذا العطل» — على الأمر لا على البطاقة؛ البطاقة تبقى فعّالة."""
    reason, note = _clean_void_reason(reason, note)
    order, card = _lock_order_with_card(order)
    blocker = _card_blocker(card)
    if blocker:
        raise ValidationError(blocker)
    label = order.order_number or order.pk
    if _posted_covered_count(order):
        raise ValidationError(
            f"الأمر {label} فيه قطع مغطاة مرحّلة — تراجع عن ترحيلها أولاً."
        )
    if not (order.warranty_covered or _pending_covered_parts(order)):
        raise ValidationError(f"الأمر {label} ليس مغطى بالكفالة أصلاً.")

    text = _reason_text(reason, note)
    _bill_order_parts(
        order, user=user, headline="رُفضت الكفالة لهذا العطل — " + text,
    )
    log_warranty_event(
        card, event_type=WarrantyCardEvent.TYPE_COVERAGE_REFUSED,
        reason_code=reason, text=text, service_order=order, user=user,
    )
    return order


@transaction.atomic
def restore_order_coverage(order, *, reason, user=None):
    """استعادة التغطية لأمرٍ رُفضت كفالته — القطع المفوترة **لا** تعود مغطاة."""
    from .service_orders import log_event

    reason = _clean_undo_reason(reason)
    order, card = _lock_order_with_card(order)
    blocker = _card_blocker(card)
    if blocker:
        raise ValidationError(
            "لا تُستعاد التغطية على هذه البطاقة: " + blocker.rstrip(".")
            + " — تراجع عن الإلغاء أولاً إن كان هو السبب."
        )
    if not order_coverage_refused(order, card):
        raise ValidationError(
            f"لم تُرفض الكفالة على الأمر {order.order_number or order.pk} كي تُستعاد."
        )
    order.warranty_covered = True
    order.save(update_fields=["warranty_covered", "updated_at"])
    log_warranty_event(
        card, event_type=WarrantyCardEvent.TYPE_COVERAGE_RESTORED,
        text=reason, service_order=order, user=user,
    )
    log_event(
        order, event_type=ServiceOrderEvent.TYPE_WARRANTY, user=user,
        text=f"استُعيدت الكفالة لهذا العطل — {reason} (القطع المفوترة تبقى مفوترة)",
    )
    return order


@transaction.atomic
def shorten_dealer_warranty(card, *, end_date, reason, user=None):
    """تقصير نهاية كفالة التاجر — قرارٌ موثَّق بسببه، وليس «تمديداً» بتاريخ أقصر."""
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "سبب التقصير مطلوب."})
    card = WarrantyCard.objects.select_for_update().get(
        pk=card.pk, tenant_id=card.tenant_id,
    )
    blocker = _card_blocker(card)
    if blocker:
        raise ValidationError(blocker)
    if end_date >= card.end_date:
        raise ValidationError({
            "end_date": (
                f"التقصير يُقدّم النهاية — التاريخ الجديد ({end_date}) ليس قبل "
                f"نهايتها الحالية ({card.end_date})."
            )
        })
    if end_date < card.start_date:
        raise ValidationError({"end_date": "لا تسبق النهايةُ بدايةَ الكفالة."})
    old_end = card.end_date
    card.end_date = end_date
    card.save(update_fields=["end_date", "updated_at"])
    log_warranty_event(
        card, event_type=WarrantyCardEvent.TYPE_EXTEND,
        reason_code=WarrantyCardEvent.EXTEND_REASON_SHORTEN,
        text=f"تقصير الكفالة من {old_end} إلى {end_date} — {reason}",
        user=user, old_end_date=old_end, new_end_date=end_date,
    )
    return card


# ══════════════════════════════════════════════════════════════════════════
# كفالة المصنع من سطر الشراء (#235)
# ══════════════════════════════════════════════════════════════════════════

LINE_WARRANTY_MAX_MONTHS = 600


def _line_months(value, label: str, field_label: str, *, nullable: bool = False):
    if value is None or value == "":
        if nullable:
            return None
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValidationError(f"{label}: {field_label} عددٌ صحيح من الأشهر.")
    try:
        months = int(value)
    except ValueError:
        raise ValidationError(f"{label}: {field_label} عددٌ صحيح من الأشهر.") from None
    if not 0 <= months <= LINE_WARRANTY_MAX_MONTHS:
        raise ValidationError(
            f"{label}: {field_label} بين 0 و{LINE_WARRANTY_MAX_MONTHS} شهراً."
        )
    return months


def clean_purchase_line_warranty(tenant_id: int, payload, label: str) -> dict:
    """يتحقّق من كفالة سطر شراء ويعيدها منظَّفة — القاعدة نفسها لـ`WarrantyPolicySerializer`.

    `label` اسم السطر («السطر 2») يتصدّر كل رسالة. الجهة تُقرأ بشركة الفاتورة وحدها
    فجهةُ شركةٍ أخرى «غير موجودة»، والمؤرشفة تُرفض.
    """
    if not isinstance(payload, dict):
        raise ValidationError(f"{label}: كفالة السطر غير صالحة.")
    warrantor_id = payload.get("manufacturer_warrantor")
    manufacturer = _line_months(payload.get("manufacturer_months"), label, "مدة كفالة المصنع")
    supplier = _line_months(
        payload.get("supplier_months"), label, "مدة كفالة المورّد", nullable=True,
    )

    warrantor = None
    if warrantor_id not in (None, ""):
        try:
            warrantor = ManufacturerWarrantor.objects.filter(
                tenant_id=tenant_id, pk=int(warrantor_id),
            ).first()
        except (TypeError, ValueError):
            warrantor = None
        if warrantor is None:
            raise ValidationError(f"{label}: جهة كفالة المصنع غير موجودة.")
        if not warrantor.is_active:
            raise ValidationError(
                f"{label}: جهة كفالة المصنع «{warrantor.name}» مؤرشفة — اختر جهةً فعّالة."
            )

    if warrantor is None and manufacturer:
        raise ValidationError(f"{label}: بلا جهة كفالة مصنع، مدتها يجب أن تكون صفراً.")
    if warrantor is not None and not manufacturer:
        raise ValidationError(
            f"{label}: اخترت جهة كفالة مصنع — حدّد مدتها بالأشهر، أو أزل الجهة."
        )
    return {
        "manufacturer_warrantor": warrantor,
        "manufacturer_months": manufacturer,
        "supplier_months": supplier,
    }


def save_purchase_line_warranty(tenant_id: int, item, payload, user, label: str):
    """يتحقّق ثم يحفظ (upsert) كفالة سطر شراء — لا يمسّ بطاقةً صدرت."""
    cleaned = clean_purchase_line_warranty(tenant_id, payload, label)
    row, _ = PurchaseLineWarranty.objects.update_or_create(
        purchase_item=item,
        defaults={
            "tenant_id": tenant_id,
            "updated_by": user if getattr(user, "pk", None) else None,
            **cleaned,
        },
    )
    return row


def purchase_line_label(item) -> str:
    """«السطر N» — ترتيب البند بين بنود فاتورته."""
    position = item.invoice.items.filter(pk__lte=item.pk).count()
    return f"السطر {position}"


def latest_purchase_line_warranties(tenant_id: int, product_ids) -> dict:
    """`{product_id: آخر كفالة سطر}` من فواتير الشراء المرحَّلة — استعلامٌ واحد للصفحة.

    «الأحدث» بتاريخ الفاتورة ثم رقم البند؛ المسودّة لا تُحسب شراءً بعد.
    """
    from django.db.models import F, Window
    from django.db.models.functions import RowNumber

    product_ids = list(product_ids)
    if not product_ids:
        return {}
    rows = (
        PurchaseLineWarranty.objects
        .filter(
            tenant_id=tenant_id,
            purchase_item__product_id__in=product_ids,
            purchase_item__invoice__is_posted=True,
        )
        .annotate(
            product_id=F("purchase_item__product_id"),
            invoice_date=F("purchase_item__invoice__invoice_date"),
            invoice_number=F("purchase_item__invoice__invoice_number"),
            recency=Window(
                RowNumber(),
                partition_by=[F("purchase_item__product_id")],
                order_by=[
                    F("purchase_item__invoice__invoice_date").desc(nulls_last=True),
                    F("purchase_item_id").desc(),
                ],
            ),
        )
        .select_related("manufacturer_warrantor")
    )
    return {row.product_id: row for row in rows.filter(recency=1)}


# ══════════════════════════════════════════════════════════════════════════
# إصدار الشهادة وسحب البطاقة اليدوية (#238)
# ══════════════════════════════════════════════════════════════════════════

ISSUE_CHANNEL_PRINT = "print"
ISSUE_CHANNEL_SHARE = "share"
WITHDRAWN_REASON_CODE = "withdrawn"


def _lock_card(card):
    return WarrantyCard.objects.select_for_update().get(
        pk=card.pk, tenant_id=card.tenant_id,
    )


def mark_card_referred(card, channel, user=None):
    """يكتب حدث `referred` عن كل ورقة إحالة تُطبع — لا يُنشئ أمر صيانة (#241).

    بخلاف `issued` لا يُكتب مرةً واحدة: كل إحالة واقعةٌ مستقلّة في سجل البطاقة،
    واسم الجهة يُكتب نصاً ليبقى مقروءاً بعد أن تُغيَّر الجهة أو تُؤرشف.
    """
    warrantor = card.manufacturer_warrantor if card.manufacturer_warrantor_id else None
    return log_warranty_event(
        card,
        event_type=WarrantyCardEvent.TYPE_REFERRED,
        reason_code=channel,
        text=f"أُحيل إلى الوكيل: {warrantor.name}" if warrantor else "أُحيل إلى الوكيل",
        user=user,
    )


@transaction.atomic
def mark_card_issued(card, channel, user=None):
    """يكتب حدث `issued` **مرةً واحدة** للبطاقة — الطباعة الثانية لا تكتب شيئاً.

    وجود الحدث هو ما يمنع الحذف ويُظهر وسم «إعادة طباعة»؛ القفل على صفّ
    البطاقة يمنع طباعتين متزامنتين من كتابته مرتين. يعيد الحدث الجديد أو `None`.
    """
    card = _lock_card(card)
    already = WarrantyCardEvent.objects.filter(
        tenant_id=card.tenant_id, card=card, event_type=WarrantyCardEvent.TYPE_ISSUED,
    ).exists()
    if already:
        return None
    return log_warranty_event(
        card, event_type=WarrantyCardEvent.TYPE_ISSUED, reason_code=channel, user=user,
    )


@transaction.atomic
def withdraw_card(card, *, reason, user=None):
    """سحب بطاقةٍ يدويةٍ صدرت للزبون: تنتهي بسببٍ موثَّق ولا تُحذف — هويتها ورمزها يبقيان."""
    reason = (reason or "").strip()
    if len(reason) < MIN_UNDO_REASON_CHARS:
        raise ValidationError(
            {"reason": f"اكتب سبب السحب ({MIN_UNDO_REASON_CHARS} أحرف على الأقل)."}
        )
    card = _lock_card(card)
    if card.source == WarrantyCard.SOURCE_AUTO_SALE:
        raise ValidationError("بطاقة تلقائية تتبع فاتورتها — لا تُسحب؛ تُنهيها الفاتورة نفسها.")
    if card.ended_on is not None:
        raise ValidationError("البطاقة منتهية أصلاً.")
    card.ended_on = timezone.localdate()
    card.end_reason = WarrantyCard.END_WITHDRAWN
    card.save(update_fields=["ended_on", "end_reason", "updated_at"])
    log_warranty_event(
        card, event_type=WarrantyCardEvent.TYPE_ENDED,
        reason_code=WITHDRAWN_REASON_CODE, text=reason, user=user,
    )
    logger.info("after_sales.warranty_withdrawn tenant=%s card=%s", card.tenant_id, card.pk)
    return card


@transaction.atomic
def unwithdraw_card(card, *, reason, user=None):
    """التراجع عن السحب — البطاقة نفسها بهويتها ورمزها، لا بطاقة جديدة."""
    reason = _clean_undo_reason(reason)
    card = _lock_card(card)
    if card.end_reason != WarrantyCard.END_WITHDRAWN or card.ended_on is None:
        raise ValidationError("البطاقة ليست مسحوبة.")
    card.ended_on = None
    card.end_reason = ""
    card.save(update_fields=["ended_on", "end_reason", "updated_at"])
    log_warranty_event(
        card, event_type=WarrantyCardEvent.TYPE_REVIVED,
        reason_code=WITHDRAWN_REASON_CODE, text=reason, user=user,
    )
    return card
