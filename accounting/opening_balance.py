"""الأرصدة الافتتاحية للشركة — الحسابات وبضاعة أول المدة في قيد موحّد واحد.

المستند (`OpeningBalance`) يجمع رِجلين: أرصدة الحسابات كما يُدخلها المحاسب،
وبضاعة أول المدة (كمية × تكلفة وحدة لكل منتج/مستودع). ترحيله ذرّيّ:

1. حرّاس — لا قيد افتتاحي مرحّل آخر للشركة، الحسابات المُدخلة خارج الممنوعات،
   فترة مالية مفتوحة عند `entry_date`.
2. حركة مخزون `IN` لكل بند بضاعة عبر `record_stock_movement` بمرجع
   `OPENING_BALANCE` وبتاريخ **`entry_date`** — فيتكوّن متوسط التكلفة صحيحاً من
   اليوم الأول وترتّب الحركة قبل أول شراء فعلي.
3. قيد واحد عبر `post_journal`: بنود الحسابات كما أُدخلت + مدين حسابات المخزون
   مجمَّعاً عبر `_resolve_line_account` نفسها التي يستعملها الجرد + سطر موازنة
   على «3300 أرصدة افتتاحية» بالفرق.

**التعادل بين المخزون والأستاذ يثبت بالبناء**: قيمة القيد على حسابات المخزون =
مجموع (كمية × تكلفة) = قيمة الحركات المسجَّلة، فلا مصدرَين للرقم نفسه.

**منع الازدواج مع أرصدة الأطراف**: أرصدة الذمم تأتي من آلية `PARTNER_OPENING`
القائمة (قيد لكل طرف على `3300` نفسه)، فتُرفض هنا الحسابات المصنَّفة
`receivable`/`payable`/`inventory`، وحساب `3300` نفسه، وأي حساب مربوط بطرف —
لا يوجد مسار يُدخل الرقم نفسه مرتين. ورِجل الأطراف تُقرأ من هنا وتُعكس من هنا:
`_partner_opening_rows` تعرض المبلغ المرحّل بجانب المُدخل،
و`reverse_partner_opening` تلغي ترحيل قيد طرف واحد بنفس `unpost_document`.

التراجع يمرّ من `unpost_document` فيرث حارس الاعتمادية (`find_stock_dependents`):
إن بيعت بضاعة الافتتاح، يُرفض العكس بقائمة المستندات المعتمِدة بدل أن يُيتّمها.
"""
import logging
from decimal import ROUND_CEILING, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .account_classification import (
    SUB_TYPE_INVENTORY,
    SUB_TYPE_PAYABLE,
    SUB_TYPE_RECEIVABLE,
)
from .api import ensure_account
from .models import (
    Account,
    JournalHeader,
    JournalLine,
    OpeningBalance,
    OpeningBalanceAccountLine,
    OpeningBalanceStockLine,
)
from .services import post_journal, unpost_document, validate_fiscal_period

logger = logging.getLogger(__name__)

#: مرجع القيد وحركات المخزون التي يولّدها المستند.
OPENING_REFERENCE_TYPE = 'OPENING_BALANCE'
#: مرجع قيد الرصيد الافتتاحي لطرف واحد — آلية قائمة لا تُمَسّ هنا.
PARTNER_OPENING_REFERENCE_TYPE = 'PARTNER_OPENING'

#: حساب موازنة الافتتاح — نفس الحساب الذي تستعمله أرصدة الأطراف.
OPENING_OFFSET_ACCOUNT_CODE = '3300'
OPENING_OFFSET_ACCOUNT_NAME = 'أرصدة افتتاحية (Opening Balances)'
OPENING_OFFSET_PARENT_CODE = '3'

#: تصنيفات لا تُدخل يدوياً في بنود الحسابات — أرقامها تأتي من رِجل أخرى.
FORBIDDEN_SUB_TYPES = {
    SUB_TYPE_RECEIVABLE: 'أرصدة الذمم المدينة تُدخل من تبويب «الأطراف»',
    SUB_TYPE_PAYABLE: 'أرصدة الذمم الدائنة تُدخل من تبويب «الأطراف»',
    SUB_TYPE_INVENTORY: 'أرصدة المخزون تُدخل من تبويب «المخزون»',
}

_MONEY = Decimal('0.01')
_QTY = Decimal('0.0001')


def resolve_opening_offset_account(tenant_id: int) -> Account:
    """حساب «3300 أرصدة افتتاحية» للشركة، يُنشأ تحت جذر حقوق الملكية إن غاب.

    نقطة واحدة لكل أرجل الافتتاح: القيد الموحّد وأرصدة الأطراف يقابلان الحساب
    نفسه، فيقرأ المستخدم أثر الافتتاح كلّه في رصيد واحد.
    """
    return ensure_account(
        tenant_id=tenant_id,
        code=OPENING_OFFSET_ACCOUNT_CODE,
        name=OPENING_OFFSET_ACCOUNT_NAME,
        account_type='Equity',
        parent_code=OPENING_OFFSET_PARENT_CODE,
    )


def company_opening_entry_date(tenant_id: int):
    """تاريخ القيد الافتتاحي للشركة إن وُجد مستند افتتاح — قراءة فقط، لا إنشاء.

    مصدر التاريخ الموحّد لأرجل الافتتاح: أرصدة الأطراف تتبعه حين لا يُدخل
    المستخدم تاريخاً لها، فلا يتفرّق افتتاح الشركة على تاريخين. `None` تعني
    «لا مستند افتتاح بعد» — والمستدعي يقرر بديله.
    """
    return (
        OpeningBalance.objects
        .filter(tenant_id=tenant_id, entry_date__isnull=False)
        .order_by('-id')
        .values_list('entry_date', flat=True)
        .first()
    )


def get_or_create_opening(tenant) -> OpeningBalance:
    """مستند الافتتاح الحالي للشركة — واحدٌ لكل شركة، يُنشأ مسودةً عند أول فتح."""
    opening = OpeningBalance.objects.filter(tenant=tenant).order_by('-id').first()
    if opening is not None:
        return opening
    return OpeningBalance.objects.create(tenant=tenant)


def assert_account_allowed(account: Account, *, offset_account_id: int) -> None:
    """يرفض حساباً لا يجوز إدخال رصيده الافتتاحي يدوياً — برسالة تقول البديل.

    الحارس خادميّ ويُستدعى عند الحفظ وعند الترحيل معاً: الواجهة تُخفي الحسابات
    الممنوعة، لكن الإخفاء ليس منعاً.
    """
    reason = FORBIDDEN_SUB_TYPES.get(account.sub_type)
    if reason:
        raise ValidationError(
            f"الحساب «{account.code} - {account.name}» لا يُدخل هنا: {reason} "
            f"— إدخاله مرتين يضاعف الرصيد."
        )
    if account.id == offset_account_id:
        raise ValidationError(
            f"الحساب «{account.code} - {account.name}» هو حساب موازنة القيد "
            f"الافتتاحي — يُحسب تلقائياً ولا يُدخل يدوياً."
        )
    from partners.models import Partner

    partner = (
        Partner.objects.filter(tenant_id=account.tenant_id, linked_account_id=account.id)
        .only('name')
        .first()
    )
    if partner is not None:
        raise ValidationError(
            f"الحساب «{account.code} - {account.name}» مربوط بالطرف "
            f"«{partner.name}» — أدخل رصيده من تبويب «الأطراف»."
        )


def _assert_draft(opening: OpeningBalance) -> None:
    if opening.status == OpeningBalance.STATUS_POSTED:
        raise ValidationError(
            "القيد الافتتاحي مرحَّل — ألغِ ترحيله أولاً قبل تعديل أرصدته."
        )


def save_opening_lines(
    opening: OpeningBalance,
    *,
    start_date=None,
    account_lines: list[dict] | None = None,
    stock_lines: list[dict] | None = None,
) -> OpeningBalance:
    """حفظ جماعي لمسودة الافتتاح — استبدال كامل للبنود المُرسلة.

    `None` تعني «لا تلمس هذه الرِّجل»؛ قائمة فارغة تعني «امسحها». المستند
    المرحَّل لا يُعدَّل إطلاقاً.
    """
    _assert_draft(opening)
    offset = resolve_opening_offset_account(opening.tenant_id)
    with transaction.atomic():
        if start_date is not None:
            opening.start_date = start_date
            opening.save(update_fields=['start_date', 'entry_date'])

        if account_lines is not None:
            seen_accounts = set()
            rows = []
            for raw in account_lines:
                account = raw['account']
                assert_account_allowed(account, offset_account_id=offset.id)
                if account.id in seen_accounts:
                    raise ValidationError(
                        f"الحساب «{account.code} - {account.name}» مكرّر في البنود."
                    )
                seen_accounts.add(account.id)
                debit = Decimal(str(raw.get('debit') or 0)).quantize(_MONEY)
                credit = Decimal(str(raw.get('credit') or 0)).quantize(_MONEY)
                if debit < 0 or credit < 0:
                    raise ValidationError("مبالغ الرصيد الافتتاحي لا تكون سالبة.")
                if debit > 0 and credit > 0:
                    raise ValidationError(
                        f"الحساب «{account.code} - {account.name}»: أدخل مديناً أو "
                        f"دائناً — لا الطرفين معاً."
                    )
                if debit == 0 and credit == 0:
                    continue
                rows.append(OpeningBalanceAccountLine(
                    tenant_id=opening.tenant_id,
                    opening=opening,
                    account=account,
                    debit=debit,
                    credit=credit,
                    notes=(raw.get('notes') or '')[:500],
                ))
            opening.account_lines.all().delete()
            OpeningBalanceAccountLine.objects.bulk_create(rows)

        if stock_lines is not None:
            seen_stock = set()
            rows = []
            for raw in stock_lines:
                product = raw['product']
                warehouse = raw['warehouse']
                key = (product.id, warehouse.id)
                if key in seen_stock:
                    raise ValidationError(
                        f"المنتج «{product}» مكرّر في المستودع «{warehouse.name}»."
                    )
                seen_stock.add(key)
                quantity = Decimal(str(raw.get('quantity') or 0)).quantize(_QTY)
                unit_cost = Decimal(str(raw.get('unit_cost') or 0)).quantize(_QTY)
                if quantity <= 0:
                    raise ValidationError(
                        f"كمية المنتج «{product}» يجب أن تكون أكبر من صفر."
                    )
                if unit_cost < 0:
                    raise ValidationError(
                        f"تكلفة وحدة المنتج «{product}» لا تكون سالبة."
                    )
                rows.append(OpeningBalanceStockLine(
                    tenant_id=opening.tenant_id,
                    opening=opening,
                    product=product,
                    warehouse=warehouse,
                    quantity=quantity,
                    unit_cost=unit_cost,
                ))
            opening.stock_lines.all().delete()
            OpeningBalanceStockLine.objects.bulk_create(rows)

    logger.info(
        "opening balance draft saved: tenant=%s opening=%s accounts=%s stock=%s",
        opening.tenant_id, opening.id,
        'unchanged' if account_lines is None else len(account_lines),
        'unchanged' if stock_lines is None else len(stock_lines),
    )
    return opening


def _stock_value(opening: OpeningBalance) -> Decimal:
    total = Decimal('0')
    for line in opening.stock_lines.all():
        total += (Decimal(str(line.quantity)) * Decimal(str(line.unit_cost)))
    return total.quantize(_MONEY)


def _partner_opening_rows(tenant) -> list[dict]:
    """أرصدة الأطراف الافتتاحية وحالة ترحيل كلٍّ منها — للعرض فقط.

    استعلامان ثابتان مهما كثر الأطراف: قيود `PARTNER_OPENING` كلها، ثم أسطرها
    التي تحمل الطرف — فيُعطى لكل صفّ رقم قيده و**المبلغ المرحَّل فعلاً**.

    `posted_amount` ليس تكراراً لـ`opening_balance`: تعديل رصيد طرف بعد ترحيله
    لا يُعيد ترحيله (المفتاح `(PARTNER_OPENING, id)` idempotent)، فيبقى في
    الدفاتر الرقم القديم. عرض الرقمين معاً هو ما يمنع المستخدم من تصديق أن
    تعديله وصل الدفاتر — والزرّ الوحيد الذي يوصله هو «إلغاء الترحيل».

    والطرف الذي صُفِّر رصيده بعد ترحيله يبقى في القائمة ما دام قيده قائماً،
    وإلا اختفى من الشاشة ومعه زرّ عكسه بينما قيده حيّ في الأستاذ.
    """
    from partners.models import Partner

    posted_journals = dict(
        JournalHeader.objects.filter(
            tenant=tenant, reference_type=PARTNER_OPENING_REFERENCE_TYPE,
        ).values_list('reference_id', 'id')
    )
    # المبلغ المرحّل كما هو في الدفاتر: سطر الطرف وحده يحمل `partner` (سطر 3300
    # المقابل لا يحمله)، فالفرق مدين−دائن عليه هو أثر الافتتاح على حسابه.
    journal_to_partner = {jid: pid for pid, jid in posted_journals.items()}
    posted_by_partner: dict[int, Decimal] = {}
    if journal_to_partner:
        for line in JournalLine.objects.filter(
            journal_id__in=list(journal_to_partner), partner_id__isnull=False,
        ).values('journal_id', 'debit', 'credit'):
            partner_id = journal_to_partner.get(line['journal_id'])
            if partner_id is None:
                continue
            net = Decimal(str(line['debit'] or 0)) - Decimal(str(line['credit'] or 0))
            posted_by_partner[partner_id] = (
                posted_by_partner.get(partner_id, Decimal('0')) + net
            )

    rows = []
    partners = (
        Partner.objects.filter(tenant=tenant)
        .filter(
            Q(id__in=list(posted_journals))
            | (Q(opening_balance__isnull=False) & ~Q(opening_balance=0))
        )
        .only('id', 'name', 'partner_type', 'opening_balance',
              'opening_balance_date', 'linked_account_id')
        .order_by('name', 'id')
    )
    for p in partners:
        journal_id = posted_journals.get(p.id)
        posted_amount = posted_by_partner.get(p.id)
        if posted_amount is not None:
            # الإشارة كإشارة `opening_balance`: موجبٌ للعميل مدين، وللمورّد دائن.
            if p.partner_type != 'Customer':
                posted_amount = -posted_amount
            posted_amount = posted_amount.quantize(_MONEY)
        rows.append({
            'id': p.id,
            'name': p.name,
            'partner_type': p.partner_type,
            'opening_balance': Decimal(str(p.opening_balance or 0)).quantize(_MONEY),
            'opening_balance_date': p.opening_balance_date,
            'linked_account': p.linked_account_id,
            'is_posted': journal_id is not None,
            'journal': journal_id,
            'posted_amount': posted_amount,
        })
    return rows


def reverse_partner_opening(tenant, partner_id: int, *, user=None) -> dict:
    """يلغي ترحيل قيد الرصيد الافتتاحي لطرف واحد — الطريق الوحيد لتعديل رصيد مرحّل.

    المفتاح `(PARTNER_OPENING, partner.id)` idempotent، فقيدٌ مرحّل لا يُعاد
    ترحيله بمبلغ جديد ما دام قائماً: يُعكس صراحةً هنا، ثم يُنشئه حفظُ الطرف
    التالي بالمبلغ الجديد. الحذف يمرّ من `unpost_document` فيرث حارس الفترة
    المالية وسجلّ التدقيق — لا حذف قيد من خارج المسار المركزي.
    """
    from partners.models import Partner

    partner = Partner.objects.filter(tenant=tenant, pk=partner_id).only('id', 'name').first()
    if partner is None:
        raise ValidationError("الطرف غير موجود في هذه الشركة.")

    has_journal = JournalHeader.objects.filter(
        tenant=tenant,
        reference_type=PARTNER_OPENING_REFERENCE_TYPE,
        reference_id=partner.id,
    ).exists()
    if not has_journal:
        raise ValidationError(
            f"لا يوجد قيد رصيد افتتاحي مرحّل للطرف «{partner.name}» — لا شيء يُلغى."
        )

    result = unpost_document(
        tenant_id=tenant.pk,
        reference_id=partner.id,
        journal_reference_types=[PARTNER_OPENING_REFERENCE_TYPE],
        user=user,
        document_label=f"الرصيد الافتتاحي للطرف «{partner.name}»",
    )
    logger.info(
        "partner opening reversed: tenant=%s partner=%s result=%s",
        tenant.pk, partner.id, result,
    )
    return result


def _serial_items(tenant, stock_lines: list) -> list[dict]:
    """منتجات الافتتاح المتتبَّعة تسلسلياً: المُسجَّل مقابل المطلوب — إرشاد لا حارس.

    الافتتاح يُدخل الكمية للمخزن ولا يُنشئ وحدةً مُرقَّمة واحدة (`ProductSerial`
    تُنشأ من استلام الشراء)، فشركةٌ نمط بيعها «إجباري» تُمنع من بيع بضاعة افتتاحها
    عند `consume_sales_serials` برسالة «المتوفر في المخزن 0 والمطلوب N» لا تقول أين
    تُرقَّم. هذه الصفوف هي التي تقولها وتصل بالمستخدم إلى المسار القائم
    `products/{id}/serials/register/`. ولا منعَ ترحيلٍ هنا: الافتتاح صحيح بلا
    أرقام، والبيع وحده هو ما يحتاجها.

    التجميع بالمنتج لا بالبند: `ProductSerial` بلا مستودع، فوحدةٌ مُرقَّمة تُحسب
    للمنتج كلّه — ومنتجٌ في مستودعين صفٌّ واحد بمجموع كميته.

    و«المُسجَّل» كل وحدات المنتج مهما كانت حالتها لا «في المخزن» وحدها: بيعُ وحدةٍ
    مُرقَّمة لا يجوز أن يُعيد المنتج ناقصَ الترقيم فيُطالب المستخدم بترقيمٍ أتمّه.
    الرقم الكامل لِما بقي بلا ترقيم (رصيد المخزن مقابل الوحدات) يعرضه كرت المنتج
    نفسه، وإليه يمضي الرابط. استعلامٌ واحد مهما كثرت البنود.
    """
    from django.db.models import Count

    from inventory.models import ProductSerial
    from inventory.serials import product_tracks_serials

    required: dict[int, Decimal] = {}
    products: dict[int, object] = {}
    for line in stock_lines:
        if not product_tracks_serials(line.product):
            continue
        products.setdefault(line.product_id, line.product)
        required[line.product_id] = (
            required.get(line.product_id, Decimal('0')) + Decimal(str(line.quantity))
        )
    if not required:
        return []

    registered = dict(
        ProductSerial.objects
        .filter(tenant=tenant, product_id__in=list(required))
        .values('product_id')
        .annotate(units=Count('id'))
        .values_list('product_id', 'units')
    )

    rows = []
    for product_id, quantity in required.items():
        product = products[product_id]
        rows.append({
            'product': product_id,
            'product_sku': product.sku,
            'product_name': product.name_ar or product.name_en or product.sku or '',
            # الوحدة المُرقَّمة لا تُجزَّأ: كميةٌ كسرية تُجبَر لأعلى فلا يُخفى نقص.
            'quantity': int(quantity.to_integral_value(rounding=ROUND_CEILING)),
            'serials_registered': int(registered.get(product_id, 0)),
        })
    return sorted(rows, key=lambda row: (row['product_name'], row['product']))


def opening_balance_summary(tenant) -> dict:
    """حالة الافتتاح كاملةً: المستند وبنوده ومجاميعه وأرصدة الأطراف.

    `equity_plug` هو «صافي حقوق الملكية الافتتاحية» الذي تعرضه الشاشة قبل
    الترحيل — موجبٌ يعني دائناً على `3300` (أصولٌ تفوق الالتزامات).

    و`serial_items` منتجات بضاعة الافتتاح المتتبَّعة تسلسلياً وحالة ترقيمها
    (`_serial_items`) — تُحسب في الحالتين ويعرضها التبويب بعد الترحيل، حيث صار
    للكمية رصيدٌ يُرقَّم.
    """
    opening = get_or_create_opening(tenant)
    account_lines = list(
        opening.account_lines.select_related('account').order_by('account__code', 'id')
    )
    stock_lines = list(
        opening.stock_lines.select_related('product', 'warehouse').order_by('id')
    )
    accounts_debit = sum(
        (Decimal(str(l.debit)) for l in account_lines), Decimal('0')
    ).quantize(_MONEY)
    accounts_credit = sum(
        (Decimal(str(l.credit)) for l in account_lines), Decimal('0')
    ).quantize(_MONEY)
    stock_value = sum(
        (Decimal(str(l.quantity)) * Decimal(str(l.unit_cost)) for l in stock_lines),
        Decimal('0'),
    ).quantize(_MONEY)
    equity_plug = (accounts_debit + stock_value - accounts_credit).quantize(_MONEY)
    return {
        'id': opening.id,
        'start_date': opening.start_date,
        'entry_date': opening.entry_date,
        'status': opening.status,
        'journal': opening.journal_id,
        'posted_at': opening.posted_at,
        'account_lines': account_lines,
        'stock_lines': stock_lines,
        'serial_items': _serial_items(tenant, stock_lines),
        'partners': _partner_opening_rows(tenant),
        'totals': {
            'accounts_debit': accounts_debit,
            'accounts_credit': accounts_credit,
            'stock_value': stock_value,
            'equity_plug': equity_plug,
        },
        'offset_account_code': OPENING_OFFSET_ACCOUNT_CODE,
    }


def post_opening_balance(opening: OpeningBalance, *, user=None) -> OpeningBalance:
    """يرحّل الافتتاح: حركات المخزون + القيد الموحّد + سطر الموازنة على 3300.

    العملية كلها داخل معاملة واحدة — فشل الفترة المالية (أو أي حارس) يُجهض
    حركات المخزون معه فلا تبقى بضاعة بلا قيدها.
    """
    from inventory.services import _resolve_line_account, record_stock_movement

    tenant_id = opening.tenant_id
    if not opening.entry_date:
        raise ValidationError(
            "حدّد تاريخ بدء التشغيل أولاً — تاريخ القيد الافتتاحي يُشتقّ منه."
        )

    offset = resolve_opening_offset_account(tenant_id)

    with transaction.atomic():
        # «قيد افتتاحي مرحّل واحد لكل شركة» — يُعاد فحصه تحت القفل داخل
        # المعاملة لأن القيد الفريد الشرطي غير متاح على MySQL (انظر
        # `OpeningBalance` في models.py).
        locked = list(
            OpeningBalance.objects.select_for_update()
            .filter(tenant_id=tenant_id)
            .only('id', 'status')
        )
        already = next(
            (o for o in locked if o.status == OpeningBalance.STATUS_POSTED), None
        )
        if already is not None:
            raise ValidationError(
                f"يوجد قيد افتتاحي مرحّل لهذه الشركة (#{already.id}). "
                f"ألغِ ترحيله صراحةً قبل ترحيل قيد افتتاحي آخر."
            )

        account_lines = list(
            opening.account_lines.select_related('account').order_by('account__code', 'id')
        )
        stock_lines = list(
            opening.stock_lines.select_related('product', 'warehouse').order_by('id')
        )
        if not account_lines and not stock_lines:
            raise ValidationError("لا توجد أرصدة افتتاحية لترحيلها — أضف بنداً واحداً على الأقل.")

        # الحارس نفسه يُعاد عند الترحيل: البنود قد تكون حُفظت قبل ربط الحساب بطرف
        # أو قبل تصنيفه.
        for line in account_lines:
            assert_account_allowed(line.account, offset_account_id=offset.id)

        # فحص الفترة مبكراً: `post_journal` يفحصها أيضاً، لكن الفشل هنا يوفّر
        # إنشاء حركات مخزون تُلغى بعد قليل ويصل بالرسالة قبل أي كتابة.
        validate_fiscal_period(tenant_id, opening.entry_date)

        lines_data = []
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        for line in account_lines:
            debit = Decimal(str(line.debit)).quantize(_MONEY)
            credit = Decimal(str(line.credit)).quantize(_MONEY)
            total_debit += debit
            total_credit += credit
            lines_data.append({
                'account': line.account_id,
                'debit': debit,
                'credit': credit,
                'description': line.notes or 'رصيد افتتاحي',
            })

        # بضاعة أول المدة: الحركة أولاً (فيتكوّن WAC)، ثم مدين حساب المخزون
        # مجمَّعاً — الرقمان مصدرهما واحد فلا يفترقان.
        inventory_debit: dict[int, Decimal] = {}
        for line in stock_lines:
            quantity = Decimal(str(line.quantity))
            unit_cost = Decimal(str(line.unit_cost))
            record_stock_movement(
                product=line.product,
                movement_type='IN',
                quantity=quantity,
                unit_cost=unit_cost,
                reference_type=OPENING_REFERENCE_TYPE,
                reference_id=opening.id,
                movement_date=opening.entry_date,
                tenant=opening.tenant,
                warehouse=line.warehouse,
                notes='بضاعة أول المدة',
            )
            value = (quantity * unit_cost).quantize(_MONEY)
            inv_account = _resolve_line_account(
                line.product, 'inventory', tenant_id=tenant_id,
            )
            inventory_debit[inv_account.id] = (
                inventory_debit.get(inv_account.id, Decimal('0')) + value
            )
        for account_id, value in inventory_debit.items():
            if value == 0:
                continue
            total_debit += value
            lines_data.append({
                'account': account_id,
                'debit': value,
                'credit': Decimal('0'),
                'description': 'بضاعة أول المدة',
            })

        # سطر الموازنة: الفرق هو أثر الافتتاح في حقوق الملكية، لا خطأ يُمنع.
        plug = (total_debit - total_credit).quantize(_MONEY)
        if plug != 0:
            lines_data.append({
                'account': offset.id,
                'debit': Decimal('0') if plug > 0 else -plug,
                'credit': plug if plug > 0 else Decimal('0'),
                'description': 'صافي حقوق الملكية الافتتاحية',
            })

        journal = post_journal(
            tenant_id=tenant_id,
            transaction_date=opening.entry_date,
            reference_type=OPENING_REFERENCE_TYPE,
            reference_id=opening.id,
            description=f"القيد الافتتاحي {opening.entry_date}",
            lines_data=lines_data,
            user=user,
        )

        opening.status = OpeningBalance.STATUS_POSTED
        opening.journal = journal
        opening.posted_at = timezone.now()
        if user is not None and getattr(user, 'is_authenticated', False):
            opening.created_by = user
        opening.save(update_fields=[
            'status', 'journal', 'posted_at', 'created_by', 'entry_date',
        ])

    logger.info(
        "opening balance posted: tenant=%s opening=%s journal=%s plug=%s",
        tenant_id, opening.id, journal.id, plug,
    )
    return opening


def unpost_opening_balance(opening: OpeningBalance, *, user=None) -> dict:
    """يلغي ترحيل الافتتاح: يحذف قيده ويعكس حركات مخزونه في نداء ذرّيّ واحد.

    يمرّ من `unpost_document` فيرث حارس الاعتمادية — بضاعة افتتاح بيعت تمنع
    العكس بقائمة المستندات المعتمِدة عليها.
    """
    if opening.status != OpeningBalance.STATUS_POSTED:
        raise ValidationError("القيد الافتتاحي غير مرحّل أصلاً.")

    with transaction.atomic():
        result = unpost_document(
            tenant_id=opening.tenant_id,
            reference_id=opening.id,
            journal_reference_types=[OPENING_REFERENCE_TYPE],
            stock_reference_types=[OPENING_REFERENCE_TYPE],
            user=user,
            document_label="القيد الافتتاحي",
        )
        opening.status = OpeningBalance.STATUS_DRAFT
        opening.journal = None
        opening.posted_at = None
        opening.save(update_fields=['status', 'journal', 'posted_at', 'entry_date'])

    logger.info(
        "opening balance unposted: tenant=%s opening=%s result=%s",
        opening.tenant_id, opening.id, result,
    )
    return result
