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

from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.utils import timezone

from core.modules import module_enabled

from .models import (
    AfterSalesSettings,
    WarrantyCard,
    WarrantyCardEvent,
    WarrantyPolicy,
    add_months,
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


def _supersede_stale_cards(invoice, unit_ids: list[int]) -> int:
    """شفاءٌ ذاتي: بطاقةٌ تلقائية حيّة لهذه الوحدة على فاتورةٍ **أخرى** تُنهى.

    تُغطّي مرجعاً وقع والوحدة مطفأة، وبياناتٍ قديمة انقطعت مرساتها. البطاقة
    **اليدوية لا تُمَسّ**: صاحبها كتبها بيده ولا علاقة لترحيلنا بها.
    """
    ended = (
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
      2. **سطر شراء الوحدة** (`PurchaseLineWarranty`) — لم يُبنَ بعد (#235)؛
         هذا هو السَّم الذي يُدخِل خطوته بين (١) و(٣) حين يُبنى، بلا لمس
         الدالتين الأخريين.
      3. **السياسة نفسها** (`manufacturer_warrantor`/`manufacturer_months`)،
         ببداية تاريخ الفاتورة — وحدها إن غابت الجهة («لا يوجد») أو لم تبقَ
         بطاقةٌ سابقة مؤهَّلة.
    """
    unit_ids = [u.pk for u in units]
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
        previous = previous_by_unit.get(unit.pk)
        if previous is not None:
            layers[unit.pk] = {
                "manufacturer_warrantor_id": previous.manufacturer_warrantor_id,
                "manufacturer_start_date": previous.manufacturer_start_date,
                "manufacturer_duration_months": previous.manufacturer_duration_months,
                "manufacturer_end_date": previous.manufacturer_end_date,
            }
            continue
        policy = policies.get(unit.product_id)
        layers[unit.pk] = _policy_manufacturer_layer(policy, invoice_date)
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
        supplier_id, supplier_end = _supplier_side(unit, policy.supplier_months)
        terms_text = policy.terms_override or settings_row.default_terms
        manufacturer_layer = manufacturer_layers.get(unit.pk, {})
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
        return {"serial": "", "covered": False, "cards": [], "unit": None}

    cards = list(
        WarrantyCard.objects
        .filter(tenant_id=tenant_id, serial=serial, ended_on__isnull=True)
        .select_related("product", "manufacturer_warrantor")
        .order_by("-end_date", "-id")
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
    return {
        "serial": serial,
        "covered": any(s["status"] == "active" for s in summaries),
        "supplier_covered": any(s["supplier_warranty_active"] for s in summaries),
        "cards": summaries,
        "unit": unit_info,
    }
