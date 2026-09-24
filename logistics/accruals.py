"""استحقاقات أطراف الاستيراد (المخلّص، الناقل المحلي، وكيل الشحن).

قاعدة المالك: **الإفراج هو لحظة الاستحقاق**. عند ترحيل الشحنة إلى فاتورة يصبح
كل طرف قدّم خدمته دائناً بقيده الخاص، ويبقى الدفع لاحقاً حركة مدينة مستقلة
(داخل الشحنة أو بسند دفع خارجها — لا فرق).

كل دالة هنا **idempotent وصامتة عند عدم اللزوم**: ترجع None إن كان الاستحقاق
مرحّلاً سلفاً أو كانت مقوّماته غائبة (لا طرف، أو مبلغ صفر)، فلا تُسقط الإفراج
بسبب مستند ناقص. الأزرار اليدوية في `views.py` تفوّض إليها كي لا يوجد منطق
ترحيل مكرر يتفرّق مع الزمن (DRY).
"""
from __future__ import annotations

import datetime
import logging
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from accounting.models import Account, JournalHeader
from accounting.api import ensure_partner_account
from accounting.services import create_audit_log, post_journal, validate_fiscal_period
from tenants.models import Currency
from django.utils import timezone

logger = logging.getLogger(__name__)


class AccrualSkipped(Exception):
    """مقوّمات الاستحقاق غائبة — سبب مقروء للمستخدم عند الطلب اليدوي."""


DELETED_SHIPMENT_MESSAGE = 'الشحنة محذوفة — لا يُثبت عليها استحقاق ولا تُسجَّل لها دفعة.'


def assert_shipment_alive(shipment) -> None:
    """شحنة محذوفة لا تقبل استحقاقاً ولا دفعة (إنتاج: استحقاق 1,500 على تخليص S-0016
    المحذوفة — التخليص لا يُخفى مع شحنته فبقيت أزراره تعمل)."""
    if shipment is not None and getattr(shipment, 'is_deleted', False):
        raise AccrualSkipped(DELETED_SHIPMENT_MESSAGE)


def _as_decimal(value, default="0") -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


# ── التخليص الجمركي ───────────────────────────────────────────────────────────

CLEARANCE_DEFAULT_ACCOUNT_CODES = {
    'vat': '1105',
    'declaration_fee': '5303',
    'terminal': '5306',
    'permits': '5302',
    'broker_commission': '5302',
    'customs_system': '5303',
    'other': '5307',
}
SHIPPING_COST_LINE_LABEL = 'دفعة الشحن (الناقل)'


def clearance_line_account(line, tenant):
    """حساب مدين بند التخليص في قيد استحقاقه: الصريح وإلا افتراضيُّ نوعه.

    مصدرٌ واحد يقرؤه الاستحقاق نفسه وترحيلُ الفاتورة الدولية حين يُعيد حصّتها
    إلى الحسابات التي دينها الاستحقاق — فلا يفترقان على حساب."""
    if line.account_id:
        return line.account
    return Account.objects.filter(
        tenant=tenant,
        code=CLEARANCE_DEFAULT_ACCOUNT_CODES.get(line.line_type, '5307'),
        is_active=True,
    ).first()


def is_vat_clearance_line(line) -> bool:
    """ضريبة الاستيراد: ضريبةُ مدخلاتٍ تُسترد (1105) لا تكلفةُ بضاعة."""
    if getattr(line, 'line_type', None) == 'vat':
        return True
    account = line.account if getattr(line, 'account_id', None) else None
    return bool(account and account.code == CLEARANCE_DEFAULT_ACCOUNT_CODES['vat'])


def post_clearance_accrual(clearance, user=None) -> Optional[JournalHeader]:
    """Dr بنود التخليص / Cr ذمم المخلّص. None إن كان مرحّلاً أو بلا مقوّمات."""
    if clearance.journal_id:
        return None
    assert_shipment_alive(clearance.shipment)
    broker = clearance.customs_broker
    if not broker:
        raise AccrualSkipped('حدّد المخلّص الجمركي قبل إثبات الاستحقاق.')
    try:
        ensure_partner_account(broker)
    except Exception:
        logger.exception('ensure_partner_account failed broker=%s', broker.pk)
    if not broker.linked_account_id:
        raise AccrualSkipped('المخلّص غير مربوط بحساب ذمم في المحاسبة.')

    lines_data = []
    for line in clearance.lines.select_related('account').all():
        amount = (_as_decimal(line.debit) - _as_decimal(line.credit)).quantize(Decimal('0.01'))
        if amount <= 0 or line.description == SHIPPING_COST_LINE_LABEL:
            continue
        account = clearance_line_account(line, clearance.tenant)
        if not account:
            raise AccrualSkipped(f'لا يوجد حساب محاسبي مناسب لبند «{line.description}».')
        lines_data.append({
            'account': account.id,
            'partner': None,
            'debit': amount,
            'credit': Decimal('0'),
            'description': f"{line.description} — {clearance.shipment.shipment_number}"[:500],
        })

    total = sum((row['debit'] for row in lines_data), Decimal('0'))
    if total <= 0:
        raise AccrualSkipped('أضف بند تخليص واحداً على الأقل بمبلغ أكبر من صفر.')

    lines_data.append({
        'account': broker.linked_account_id,
        'partner': broker.id,
        'debit': Decimal('0'),
        'credit': total,
        'description': f"استحقاق تخليص — {clearance.shipment.shipment_number}"[:500],
    })

    transaction_date = clearance.clearance_date or timezone.localdate()
    validate_fiscal_period(clearance.tenant, transaction_date)
    journal = post_journal(
        tenant_id=clearance.tenant_id,
        transaction_date=transaction_date,
        reference_type='LOGISTICS_CLEARANCE',
        reference_id=clearance.id,
        description=f"استحقاق تخليص {clearance.shipment.shipment_number} | {broker.name}"[:500],
        lines_data=lines_data,
        currency=clearance.currency or Currency.objects.filter(Code__iexact='ILS').first(),
        exchange_rate=_as_decimal(clearance.exchange_rate, '1'),
        user=user,
    )
    clearance.journal = journal
    clearance.save(update_fields=['journal'])
    logger.info(
        'clearance accrual posted clearance=%s journal=%s total=%s',
        clearance.pk, journal.pk, total,
    )
    return journal


# ── النقل المحلي («ارسالية») ──────────────────────────────────────────────────

def post_local_shipment_accrual(shipment, user=None) -> Optional[JournalHeader]:
    """Dr مصروف النقل / Cr ذمم الناقل. None إن كان مرحّلاً أو بلا مقوّمات."""
    if shipment.is_posted:
        return None
    if shipment.status == 'cancelled':
        raise AccrualSkipped('لا يمكن ترحيل شحنة ملغاة.')
    tenant = shipment.tenant
    amt = _as_decimal(shipment.amount)
    if amt <= 0:
        raise AccrualSkipped('مبلغ الشحنة يجب أن يكون أكبر من صفر.')

    expense_account = shipment.expense_account or (
        Account.objects.filter(tenant=tenant, code='5305', is_active=True).first()
        or Account.objects.filter(tenant=tenant, code='5301', is_active=True).first()
    )
    if not expense_account:
        raise AccrualSkipped('لا يوجد حساب مصروف للشحن المحلي (5305).')

    try:
        ensure_partner_account(shipment.carrier)
    except Exception:
        logger.exception('ensure_partner_account failed carrier=%s', shipment.carrier_id)
    credit_account = getattr(shipment.carrier, 'linked_account', None)
    if not credit_account:
        raise AccrualSkipped('الناقل لا يملك حساب محاسبي مرتبط.')

    td = shipment.delivery_date or shipment.pickup_date or timezone.localdate()
    validate_fiscal_period(tenant, td)

    # تسمية القيود: المدين «استحقاق نقل» والدائن «ارسالية» (مصطلح المالك) —
    # الأستاذ العام يعرض وصف السطر الخام، فالتفريق يجب أن يكون في النص نفسه.
    # المرحلة 2: عبر post_journal مثل بقية استحقاقات الملف — يستعيد idempotency
    # المرجع (LOCAL_SHIPMENT, pk) وقفل السباق بدل الإنشاء اليدوي.
    journal = post_journal(
        tenant_id=tenant.TenantID,
        transaction_date=td,
        reference_type='LOCAL_SHIPMENT',
        reference_id=shipment.pk,
        description=f"ارسالية {shipment.shipment_number} | {shipment.carrier.name}"[:500],
        lines_data=[
            # سطرُ الذمة وحده يحمل الناقل: المصروفُ الموسومُ به يُلغي دائنَه في
            # `partner_posted_balance` وكشفه (إنتاج: قيد #10961 — الهجرة 0090).
            {
                'account': expense_account.id, 'partner': None,
                'debit': amt, 'credit': Decimal('0'),
                'description': f"استحقاق نقل محلي — {shipment.shipment_number}"[:255],
            },
            {
                'account': credit_account.id, 'partner': shipment.carrier_id,
                'debit': Decimal('0'), 'credit': amt,
                'description': (
                    f"ارسالية {shipment.shipment_number} — {shipment.carrier.name}"
                )[:255],
            },
        ],
        currency=shipment.currency,
        exchange_rate=shipment.exchange_rate,
        user=user,
    )
    shipment.is_posted = True
    shipment.journal = journal
    shipment.save(update_fields=['is_posted', 'journal'])
    create_audit_log(
        tenant=tenant, user=user, action='local_shipment_posted',
        model_name='LocalShipment', object_id=shipment.pk,
        change_details=f"ترحيل شحن محلي {shipment.shipment_number} بمبلغ {amt}",
    )
    logger.info(
        'local shipment accrual posted shipment=%s journal=%s amount=%s',
        shipment.pk, journal.pk, amt,
    )
    return journal


# ── شحن الوكيل الدولي ─────────────────────────────────────────────────────────

def post_freight_accrual(shipment, rate, user=None) -> Optional[JournalHeader]:
    """Dr مصاريف الشحن الدولي / Cr ذمم الوكيل. None إن كان مرحّلاً أو بلا مقوّمات."""
    if shipment.freight_is_posted:
        return None
    assert_shipment_alive(shipment)
    tenant = shipment.tenant
    agent = shipment.shipping_agent
    if not agent:
        raise AccrualSkipped('حدّد وكيل الشحن قبل إثبات الاستحقاق.')
    try:
        ensure_partner_account(agent)
    except Exception:
        logger.exception('ensure_partner_account failed agent=%s', agent.pk)
    if not agent.linked_account_id:
        raise AccrualSkipped('وكيل الشحن غير مربوط بحساب ذمم في المحاسبة.')

    rate = _as_decimal(rate)
    if rate <= 0:
        raise AccrualSkipped('أدخل سعر صرف الدولار للشيكل لاستحقاق الشحن (أكبر من صفر).')
    total_usd = _as_decimal(shipment.total_shipping_cost_usd)
    if total_usd <= 0:
        # شحنة بتكلفة شحن صفر لا تُنشئ ذمّة ولا قيداً — ولا تحتاج دفعة وهمية.
        raise AccrualSkipped('تكلفة الشحن صفر — لا يوجد استحقاق على الوكيل ولا حاجة لأي دفعة.')
    amount_ils = (total_usd * rate).quantize(Decimal('0.01'))

    expense_account = Account.objects.filter(
        tenant=tenant, code='5301', is_active=True,
    ).first()
    if not expense_account:
        raise AccrualSkipped('لا يوجد حساب «مصاريف الشحن الدولي» (5301) في شجرة الحسابات.')

    td = shipment.departure_date or shipment.arrival_date or timezone.localdate()
    validate_fiscal_period(tenant, td)

    desc = f"استحقاق شحن دولي | شحنة: {shipment.shipment_number} | وكيل: {agent.name}"
    journal = post_journal(
        tenant_id=tenant.TenantID,
        transaction_date=td,
        reference_type='SHIPMENT_FREIGHT_ACCRUAL',
        reference_id=shipment.pk,
        description=desc[:500],
        lines_data=[
            {
                'account': expense_account.id, 'debit': amount_ils, 'credit': Decimal('0'),
                'partner': None, 'description': desc[:500],
            },
            {
                'account': agent.linked_account_id, 'debit': Decimal('0'), 'credit': amount_ils,
                'partner': agent.id, 'description': desc[:500],
            },
        ],
    )
    shipment.freight_exchange_rate = rate
    shipment.freight_is_posted = True
    shipment.freight_journal = journal
    shipment.save(update_fields=[
        'freight_exchange_rate', 'freight_is_posted', 'freight_journal',
    ])
    create_audit_log(
        tenant=tenant, user=user, action='FREIGHT_ACCRUAL',
        model_name='LogisticsShipment', object_id=shipment.pk,
        change_details=f"استحقاق شحن {shipment.shipment_number} بمبلغ {amount_ils} (سعر {rate})",
    )
    logger.info(
        'shipment freight accrual posted shipment=%s journal=%s usd=%s rate=%s ils=%s',
        shipment.pk, journal.pk, total_usd, rate, amount_ils,
    )
    return journal


# ── الإفراج: استحقاق كل الأطراف دفعة واحدة ────────────────────────────────────

def accrue_all_on_release(clearance, freight_rate=None, user=None) -> List[str]:
    """يُستدعى عند ترحيل الشحنة إلى فاتورة — «الإفراج لحظة الاستحقاق».

    يُثبت ما لم يُثبت بعد لكل طرف قدّم خدمته. المستند الناقص (بلا مخلّص، بلا
    بنود، تكلفة صفر) يُتخطّى بصمت مع تسجيله — الإفراج لا يسقط بسببه.
    """
    from .models import LocalShipment

    posted: List[str] = []
    shipment = clearance.shipment

    for label, fn in (
        ('clearance', lambda: post_clearance_accrual(clearance, user=user)),
        ('freight', lambda: post_freight_accrual(shipment, freight_rate, user=user)),
    ):
        try:
            if fn() is not None:
                posted.append(label)
        except AccrualSkipped as exc:
            logger.info('release accrual skipped kind=%s clearance=%s: %s', label, clearance.pk, exc)
        except Exception:
            logger.exception('release accrual failed kind=%s clearance=%s', label, clearance.pk)

    locals_qs = LocalShipment.objects.filter(
        tenant=clearance.tenant, is_posted=False,
    ).filter(clearance=clearance) | LocalShipment.objects.filter(
        tenant=clearance.tenant, is_posted=False, shipment=shipment,
    )
    for local in locals_qs.select_related('carrier', 'expense_account', 'currency').distinct():
        try:
            if post_local_shipment_accrual(local, user=user) is not None:
                posted.append(f'local:{local.pk}')
        except AccrualSkipped as exc:
            logger.info('release accrual skipped kind=local id=%s: %s', local.pk, exc)
        except Exception:
            logger.exception('release accrual failed kind=local id=%s', local.pk)

    return posted


# ── الفاتورة الدولية: حصّتها من الاستحقاقات تعود إلى البضاعة ─────────────────

IMPORT_COMPONENT_LABELS = {
    'freight': 'الشحن الدولي',
    'clearance': 'التخليص',
    'local': 'النقل المحلي',
}


def _journal_debit_sources(journal_id, weight=None) -> List[tuple]:
    """(حساب، وزن) لكل سطر مدين في قيد استحقاق — الحساب الذي دينه فعلاً."""
    from accounting.models import JournalLine
    rows = list(
        JournalLine.objects.filter(journal_id=journal_id, debit__gt=0)
        .values_list('account_id', 'debit')
    )
    total = sum((_as_decimal(d) for _a, d in rows), Decimal('0'))
    if not rows or total <= 0:
        return []
    if weight is None:
        return [(acc, _as_decimal(d)) for acc, d in rows]
    return [(acc, weight * _as_decimal(d) / total) for acc, d in rows]


def import_invoice_accrual_credits(invoice, shares) -> List[dict]:
    """أسطر الدائن التي تُعيد حصّة الفاتورة الدولية من كل تكلفة مشتركة إلى
    الحسابات التي دينها استحقاقُها عند الإفراج.

    الاستحقاق دين 5301/بنود التخليص/مصروف النقل ودائن الوكيل والمخلّص والناقل؛
    والفاتورة ترسمل التكلفة نفسها في البضاعة. لو دائنت المورد بها أيضاً لثبتت
    التكلفة مرّتين (مصروفاً ومخزوناً) وتضخّمت ذمّته بما لا يدين به. فالحصّة
    تُقسَم على حسابات الاستحقاق بأوزان أسطره (مجموعها = الحصّة بالضبط)، وما لم
    يُستحقّ بعد يبقى على المورد كما كان — مع تحذيرٍ في السجل.

    shares: ناتج `landed_cost.import_invoice_cost_shares`. يُرجع
    [{'account', 'amount', 'component'}] لكلّ حساب؛ فارغاً إن لا استحقاق مرحّل.
    """
    from .landed_cost import LOCAL_SHIPPING_CLEARANCE_LINE_LABELS, distribute_by_weights
    from .models import LocalShipment, LogisticsClearance

    tenant = invoice.tenant
    shipment = invoice.shipment
    clearance = invoice.clearance or LogisticsClearance.objects.filter(
        tenant_id=invoice.tenant_id, shipment_id=invoice.shipment_id,
    ).first()
    local_source = shares.get('local_source') or 'none'
    sources = {'freight': [], 'clearance': [], 'local': []}

    if shipment is not None and shipment.freight_is_posted and shipment.freight_journal_id:
        sources['freight'] = _journal_debit_sources(shipment.freight_journal_id)

    if clearance is not None:
        accrued = bool(clearance.journal_id)
        for line in clearance.lines.select_related('account').all():
            amount = _as_decimal(line.debit) - _as_decimal(line.credit)
            if amount <= 0 or is_vat_clearance_line(line):
                continue
            label = (line.description or '').strip()
            if label == SHIPPING_COST_LINE_LABEL:
                # بند الناقل لا يدخل قيد استحقاق التخليص أصلاً.
                bucket, account = 'local', None
            elif label in LOCAL_SHIPPING_CLEARANCE_LINE_LABELS:
                bucket = 'local'
                account = clearance_line_account(line, tenant) if accrued else None
            else:
                bucket = 'clearance'
                account = clearance_line_account(line, tenant) if accrued else None
            if bucket == 'local' and local_source != 'clearance_lines':
                continue
            sources[bucket].append((account.id if account else None, amount))

    if local_source == 'local_shipment' and shipment is not None:
        from django.db.models import Q
        # فلتر `domain.inland.transport_pool_ils` نفسه — الحوض الذي بُنيت منه الحصّة.
        cond = Q(shipment=shipment) | (Q(clearance=clearance) if clearance else Q())
        for ls in (
            LocalShipment.objects.filter(cond, tenant=tenant, capitalize_to_inventory=True)
            .exclude(status='cancelled').distinct()
        ):
            weight = _as_decimal(ls.amount) * (_as_decimal(ls.exchange_rate, '1') or Decimal('1'))
            if weight <= 0:
                continue
            accrued = _journal_debit_sources(ls.journal_id, weight) if (
                ls.is_posted and ls.journal_id) else []
            sources['local'].extend(accrued or [(None, weight)])

    credits: dict = {}
    for component in ('freight', 'clearance', 'local'):
        share = _as_decimal(shares.get(component)).quantize(Decimal('0.01'))
        if share <= 0:
            continue
        srcs = sources[component] or [(None, Decimal('1'))]
        parts = distribute_by_weights(share, [w for _a, w in srcs])
        unaccrued = Decimal('0')
        for (account_id, _w), part in zip(srcs, parts):
            if account_id is None:
                unaccrued += part
                continue
            key = (component, account_id)
            credits[key] = credits.get(key, Decimal('0')) + part
        if unaccrued > 0:
            logger.warning(
                'import invoice %s: %s share %s has no posted accrual — stays on supplier',
                invoice.pk, component, unaccrued,
            )
    return [
        {'component': component, 'account': account_id, 'amount': amount}
        for (component, account_id), amount in credits.items() if amount > 0
    ]
