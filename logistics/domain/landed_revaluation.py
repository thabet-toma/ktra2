"""إعادة تقييم فواتير الاستيراد المرحّلة حين يُعدَّل استحقاقٌ في شحنتها.

«تعديل الاستحقاق» (`domain/accrual_adjust.py`) يغيّر تكلفة الشحن أو التخليص أو النقل،
فتتغيّر حصّة كل فاتورة دولية منها. المسودة يُعاد بناؤها (`recalculate_landed_for_shipment`)؛
والمرحّلة لا يُلغى ترحيلها — يُرحَّل لها قيدُ فرقٍ واحد (`PURCHASE_INVOICE_LANDED_ADJ`):

    دائن/مدين حسابات الاستحقاق بفرق حصّة الفاتورة منها (المصدر: `import_invoice_accrual_credits`
    قبل التعديل وبعده — فتنتقل التكلفة إلى البضاعة مرّةً واحدة كما في الترحيل)
    ومقابله لكل بند بفرق تكلفته المستوردة:
      - الباقي في المخزن  ← حساب المخزون، وترتفع/تنخفض كلفة طبقته (FIFO)
      - المبيع (استُهلكت طبقته) ← تكلفة البضاعة المباعة، وتُحدَّث كلفة حركة البيع
      - الذي لم يُستلَم بعد ← وسيط الاستلام (GR/IR) فيدخل المخزن بالكلفة الجديدة
      - بندٌ بحساب مصروف صريح ← حسابه

قرار المالك (2026-09-26، الخيار «ج»): المبيع قيدُ تسويةٍ واحد على ت.ب.م لا عكسُ قيود البيع
وإعادتها — مرآة Odoo (landed cost بعد البيع: الباقي على المخزون والمبيع على ت.ب.م).

حدٌّ معروف: إلغاء ترحيل بيعةٍ بعد التسوية يُعيد الكمية إلى طبقتها بالكلفة الجديدة بينما قيد
البيع المحذوف كان بالقديمة — فيفترق حساب المخزون عن الطبقات بفرق الوحدة × الكمية. نادرٌ،
ويكشفه `layer_balance_gaps`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

REVALUATION_REFERENCE_TYPE = 'PURCHASE_INVOICE_LANDED_ADJ'
Q2 = Decimal('0.01')
ZERO = Decimal('0.00')

STALE_INVOICE_MESSAGE = (
    'الفاتورة {number} مرحّلة وتكاليفها متأخّرة عن الشحنة من قبل هذا التعديل — '
    'أعد احتسابها وترحيلها أولاً («أعد الاحتساب والترحيل»)، ثم عدّل الاستحقاق.'
)


def _q(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


@dataclass
class InvoiceSnapshot:
    """حصّة فاتورةٍ مرحّلة من حسابات الاستحقاق قبل التعديل."""
    tenant_id: int
    invoice_id: int
    invoice_number: str
    credits: dict


@dataclass
class InvoicePlan:
    invoice_id: int
    invoice_number: str
    amount: Decimal = ZERO
    credit_deltas: dict = field(default_factory=dict)
    buckets: dict = field(default_factory=dict)   # (نوع، حساب) ← مبلغ مدين موقَّع
    row: dict | None = None
    warnings: list = field(default_factory=list)
    journal_id: int | None = None

    def summary(self) -> dict:
        totals = {'inventory': ZERO, 'cogs': ZERO, 'clearing': ZERO, 'expense': ZERO}
        for (kind, _acc), amount in self.buckets.items():
            totals[kind] += amount
        return {
            'invoice_id': self.invoice_id, 'invoice_number': self.invoice_number,
            'amount': str(self.amount), **{k: str(v) for k, v in totals.items()},
            'journal_id': self.journal_id, 'warnings': self.warnings,
        }


def _credits_map(rows) -> dict:
    return {(r['component'], r['account']): _q(r['amount']) for r in rows}


def _posted_import_invoices(tenant_id: int, shipment_id: int):
    from logistics.models import PurchaseInvoice

    return list(PurchaseInvoice.objects.filter(
        tenant_id=tenant_id, shipment_id=shipment_id,
        invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
        is_return=False, is_posted=True, journal__isnull=False,
    ).select_related('deal', 'shipment', 'clearance').order_by('pk'))


def capture(tenant_id: int, shipment_id: int | None) -> list[InvoiceSnapshot]:
    """حصص الفواتير المرحّلة قبل تعديل المستند. فاتورةٌ متأخّرة سلفاً تُوقف التعديل:
    فرقٌ يُبنى عليها يخلط تأخّرها القديم بالتعديل الجديد."""
    from logistics.accruals import import_invoice_accrual_credits
    from logistics.landed_cost import import_invoice_cost_shares
    from logistics.payment_posting import invoice_archive_locks

    if not shipment_id:
        return []
    invoices = _posted_import_invoices(tenant_id, shipment_id)
    locks = invoice_archive_locks(invoices)
    out = []
    for inv in invoices:
        if inv.pk in locks:
            continue
        shares = import_invoice_cost_shares(inv)
        if shares is None:
            continue
        if not shares['matches_invoice']:
            raise ValidationError(STALE_INVOICE_MESSAGE.format(number=inv.invoice_number))
        out.append(InvoiceSnapshot(
            inv.tenant_id, inv.pk, inv.invoice_number, _credits_map(import_invoice_accrual_credits(inv, shares))))
    return out


def _gr_ir_in_use(invoice) -> bool:
    from logistics.services import open_goods_clearing

    _acc, total, _open = open_goods_clearing(invoice)
    return total > 0


def _dest_transfer_layer(movement):
    """طبقة الاستلام المقابلة لصرف تحويلٍ بين المستودعات — أو None إن لم تتعيّن."""
    from inventory.models import StockLayer

    layers = list(StockLayer.objects.filter(
        tenant_id=movement.tenant_id, product_id=movement.product_id,
        source_movement__reference_type='WAREHOUSE_TRANSFER',
        source_movement__reference_id=movement.reference_id,
    ).exclude(source_movement_id=movement.pk)[:2])
    return layers[0] if len(layers) == 1 else None


def _walk_layer(layer, unit_delta: Decimal, *, apply: bool, depth: int = 0) -> tuple:
    """(قيمةٌ باقية في المخزن، قيمةٌ مبيعة) لفرق كلفة الوحدة على طبقةٍ وما استهلكها.

    التحويل بين المستودعات يستهلك الطبقة ويُنشئ طبقةً في الوجهة: الفرق يتبعها إليها.
    `apply=True` يكتب: كلفة الطبقة ولقطات استهلاكها وكلفة حركات الصرف.
    """
    from decimal import Decimal as D

    new_cost = D(str(layer.unit_cost)) + unit_delta
    if new_cost < 0:
        raise ValidationError(
            f'التعديل يجعل كلفة وحدة الصنف #{layer.product_id} سالبة — راجع المبلغ.')
    in_stock = unit_delta * D(str(layer.remaining_qty))
    sold = ZERO
    for cons in layer.consumptions.select_related('movement').order_by('id'):
        value = unit_delta * D(str(cons.quantity))
        movement = cons.movement
        dest = (
            _dest_transfer_layer(movement)
            if movement.reference_type == 'WAREHOUSE_TRANSFER' and depth < 5 else None
        )
        if dest is not None and D(str(dest.original_qty)) > 0:
            sub_stock, sub_sold = _walk_layer(
                dest, value / D(str(dest.original_qty)), apply=apply, depth=depth + 1)
            in_stock += sub_stock
            sold += sub_sold
        elif movement.reference_type == 'WAREHOUSE_TRANSFER':
            # وجهةٌ لا تتعيّن: القيمة باقية في المخزون على الأقل.
            in_stock += value
        else:
            sold += value
            if apply:
                total = (D(str(movement.total_cost or 0)) + value).quantize(Q2)
                qty = D(str(movement.quantity or 0))
                movement.total_cost = total
                movement.unit_cost = (total / qty).quantize(D('0.0001')) if qty > 0 else D('0')
                movement.save(update_fields=['total_cost', 'unit_cost'])
        if apply:
            cons.unit_cost = (D(str(cons.unit_cost)) + unit_delta).quantize(D('0.0001'))
            cons.save(update_fields=['unit_cost'])
    if apply:
        layer.unit_cost = new_cost.quantize(D('0.0001'))
        layer.save(update_fields=['unit_cost'])
    return in_stock, sold


def _product_split(invoice, product, qty: Decimal, delta: Decimal, *, apply: bool) -> tuple:
    """(في المخزن، مبيع، لم يُستلَم) لفرق تكلفة صنفٍ في الفاتورة — مجموعها = الفرق."""
    from inventory.models import StockLayer, StockLayerReconciliation, StockMovement

    unit_delta = delta / qty if qty > 0 else ZERO
    movements = list(StockMovement.objects.filter(
        tenant_id=invoice.tenant_id, reference_type='PURCHASE_INVOICE', reference_id=invoice.pk,
        product_id=product.pk, movement_type='IN',
    ).order_by('id'))
    received = sum((Decimal(str(m.quantity)) for m in movements), Decimal('0'))
    in_stock = sold = Decimal('0')
    for m in movements:
        # بيعٌ سبق وصول البضاعة (مخزون سالب) سدّه هذا الاستلام: مبيعٌ لا مخزون.
        for rec in StockLayerReconciliation.objects.filter(movement=m):
            sold += unit_delta * Decimal(str(rec.quantity))
        for layer in StockLayer.objects.filter(source_movement=m).order_by('id'):
            s, c = _walk_layer(layer, unit_delta, apply=apply)
            in_stock += s
            sold += c
    unreceived = unit_delta * max(qty - received, Decimal('0'))
    in_stock, sold, unreceived = _q(in_stock), _q(sold), _q(unreceived)
    residual = delta - (in_stock + sold + unreceived)
    if residual:
        # كسور التقريب على الوعاء الأكبر.
        parts = {'stock': in_stock, 'sold': sold, 'unreceived': unreceived}
        biggest = max(parts, key=lambda k: abs(parts[k]))
        parts[biggest] += residual
        in_stock, sold, unreceived = parts['stock'], parts['sold'], parts['unreceived']
    return in_stock, sold, unreceived


def _plan_invoice(snapshot: InvoiceSnapshot, *, apply: bool) -> InvoicePlan | None:
    from inventory.services import _resolve_line_account, product_display_name
    from logistics.accruals import import_invoice_accrual_credits
    from logistics.landed_cost import _rebuild_import_invoice_row, import_invoice_cost_shares
    from logistics.models import PurchaseInvoice
    from logistics.services import _resolve_gr_ir_account, _resolve_inventory_account

    inv = PurchaseInvoice.objects.select_related('deal', 'shipment', 'clearance', 'tenant').get(
        pk=snapshot.invoice_id, tenant_id=snapshot.tenant_id)
    plan = InvoicePlan(inv.pk, inv.invoice_number)
    shares = import_invoice_cost_shares(inv)
    row = _rebuild_import_invoice_row(inv)
    if shares is None or row is None:
        return None
    after = _credits_map(import_invoice_accrual_credits(inv, shares))
    deltas = {
        key: after.get(key, ZERO) - snapshot.credits.get(key, ZERO)
        for key in set(after) | set(snapshot.credits)
    }
    plan.credit_deltas = {k: v for k, v in deltas.items() if v}
    total = sum(plan.credit_deltas.values(), ZERO)

    items = list(inv.items.select_related('product').order_by('id'))
    live = row.get('items') or []
    if len(items) != len(live) or any(
            (it.product_id or None) != (r.get('product') or None) for it, r in zip(items, live)):
        raise ValidationError(
            f'بنود الفاتورة {inv.invoice_number} لا تطابق صفقتها الآن — أعد احتسابها وترحيلها أولاً.')
    item_deltas = [_q(r.get('landed_line_total_ils')) - _q(it.landed_line_total_ils)
                   for it, r in zip(items, live)]
    goods_delta = (_q(row.get('subtotal')) - _q(inv.subtotal)) + (
        _q(row.get('shipping_cost')) - _q(inv.shipping_cost))
    if not total and not any(item_deltas) and not goods_delta:
        return None

    tolerance = max(Q2 * len(items), Decimal('0.05'))
    if abs(goods_delta - total) > tolerance or abs(sum(item_deltas, ZERO) - total) > tolerance:
        # جزءٌ من الفرق على مكوّنٍ غير مستحقّ (يخصّ المورد): قيد التسوية لا يلمس ذمّته.
        raise ValidationError(
            f'الفاتورة {inv.invoice_number}: فرق تكلفتها ({goods_delta}) لا يطابق فرق حصّتها من '
            f'الاستحقاقات ({total}) — أثبت استحقاقات الشحنة كلّها أو أعد احتساب الفاتورة وترحيلها.')
    residual = total - sum(item_deltas, ZERO)
    if residual and items:
        idx = max(range(len(items)), key=lambda i: abs(item_deltas[i]))
        item_deltas[idx] += residual
    plan.amount = total
    plan.row = row

    tenant = inv.tenant
    uses_clearing = _gr_ir_in_use(inv)
    clearing_account = _resolve_gr_ir_account(tenant) if uses_clearing else None
    default_inventory = _resolve_inventory_account(tenant)

    def add(kind: str, account_id: int, amount: Decimal):
        if amount:
            key = (kind, account_id)
            plan.buckets[key] = plan.buckets.get(key, ZERO) + amount

    by_product: dict = {}
    for it, delta in zip(items, item_deltas):
        if not delta:
            continue
        if it.expense_account_id:
            add('expense', it.expense_account_id, delta)
        elif not it.product_id:
            add('clearing' if uses_clearing else 'inventory',
                clearing_account.id if uses_clearing else default_inventory.id, delta)
        else:
            entry = by_product.setdefault(it.product_id, [it.product, Decimal('0'), ZERO])
            entry[1] += Decimal(str(it.quantity or 0))
            entry[2] += delta

    for product, qty, delta in by_product.values():
        try:
            inventory_account = _resolve_line_account(product, 'inventory', tenant_id=inv.tenant_id)
        except Exception:
            inventory_account = default_inventory
        cogs_account = _resolve_line_account(product, 'cogs', tenant_id=inv.tenant_id)
        in_stock, sold, unreceived = _product_split(inv, product, qty, delta, apply=apply)
        add('inventory', inventory_account.id, in_stock)
        add('cogs', cogs_account.id, sold)
        if unreceived:
            if uses_clearing:
                add('clearing', clearing_account.id, unreceived)
            else:
                # دولية دينت المخزون مباشرةً وبضاعتها لم تدخل بحركة استلامٍ للفاتورة.
                add('inventory', inventory_account.id, unreceived)
                plan.warnings.append(
                    f'{product_display_name(product)}: بضاعةٌ بلا حركة استلامٍ للفاتورة — عُدِّل حساب المخزون '
                    'وحده دون طبقات الكلفة.')
    return plan


def plan(snapshots: list[InvoiceSnapshot]) -> list[InvoicePlan]:
    """فروق الفواتير المرحّلة بعد تعديل المستند — بلا كتابة."""
    return [p for p in (_plan_invoice(s, apply=False) for s in snapshots) if p is not None]


def apply(snapshots: list[InvoiceSnapshot], *, adjust_date, user=None) -> list[InvoicePlan]:
    """يرحّل قيد تسوية لكل فاتورة مرحّلة تغيّرت حصّتها، ويحدّث طبقاتها وأرقامها المحفوظة."""
    from accounting.services import post_journal
    from inventory.fifo import derived_avg_cost
    from inventory.models import Product
    from inventory.services import apply_purchase_cost_model
    from logistics.landed_cost import _import_row_drifted
    from logistics.models import PurchaseInvoice
    from tenants.models import Currency

    base_currency = (Currency.objects.filter(IsBaseCurrency=True).first()
                     or Currency.objects.filter(Code__iexact='ILS').first())
    done = []
    for snapshot in snapshots:
        p = _plan_invoice(snapshot, apply=True)
        if p is None:
            continue
        inv = PurchaseInvoice.objects.select_related('tenant').get(
            pk=p.invoice_id, tenant_id=snapshot.tenant_id)
        lines = []
        labels = {'inventory': 'مخزون', 'cogs': 'تكلفة المبيع', 'clearing': 'وسيط الاستلام',
                  'expense': 'مصروف'}
        for (kind, account_id), amount in sorted(p.buckets.items(), key=lambda kv: kv[0]):
            amount = _q(amount)
            if not amount:
                continue
            lines.append({
                'account': account_id, 'partner': None,
                'debit': amount if amount > 0 else ZERO, 'credit': -amount if amount < 0 else ZERO,
                'description': f"تعديل تكلفة مستوردة ({labels[kind]}) — {inv.invoice_number}"[:500],
            })
        from logistics.accruals import IMPORT_COMPONENT_LABELS
        for (component, account_id), amount in sorted(p.credit_deltas.items(), key=lambda kv: kv[0]):
            amount = _q(amount)
            if not amount:
                continue
            lines.append({
                'account': account_id, 'partner': None,
                'debit': -amount if amount < 0 else ZERO, 'credit': amount if amount > 0 else ZERO,
                'description': (f"تعديل حصّة الفاتورة من {IMPORT_COMPONENT_LABELS[component]} "
                                f"— {inv.invoice_number}")[:500],
            })
        journal = None
        if lines:
            journal = post_journal(
                tenant_id=inv.tenant_id, transaction_date=adjust_date,
                reference_type=REVALUATION_REFERENCE_TYPE, reference_id=inv.pk,
                description=f"تعديل تكلفة الفاتورة {inv.invoice_number} بعد تعديل الاستحقاق"[:500],
                lines_data=lines, currency=base_currency, exchange_rate=Decimal('1'),
                user=user, idempotent=False,
            )
        _store_row(inv, p.row)
        if _import_row_drifted(inv, p.row):
            raise ValidationError(f'تعذّر مطابقة أرقام الفاتورة {inv.invoice_number} بعد التعديل.')
        for pid in {it.product_id for it in inv.items.all() if it.product_id and not it.expense_account_id}:
            prod = Product.objects.select_for_update().get(pk=pid, tenant_id=inv.tenant_id)
            prod.avg_cost = derived_avg_cost(tenant_id=inv.tenant_id, product_id=pid)
            prod.save(update_fields=['avg_cost'])
            apply_purchase_cost_model(prod)
        p.journal_id = journal.pk if journal else None
        logger.info(
            'landed revaluation invoice=%s journal=%s amount=%s buckets=%s',
            inv.pk, getattr(journal, 'pk', None), p.amount,
            {f'{k}:{a}': str(v) for (k, a), v in p.buckets.items()},
        )
        done.append(p)
    return done


def _store_row(inv, row: dict) -> None:
    """أرقام الفاتورة المحفوظة من الصفّ الحيّ — ما يقارن به `_import_row_drifted`.
    ضريبتها وخصمها ورسومها ملكُها ولا تُمسّ؛ الإجمالي يتحرّك بفرق التكلفة وحده."""
    delta = (_q(row.get('subtotal')) - _q(inv.subtotal)) + (
        _q(row.get('shipping_cost')) - _q(inv.shipping_cost))
    inv.subtotal = row['subtotal']
    inv.shipping_cost = row['shipping_cost']
    inv.grand_total = (_q(inv.grand_total) + delta).quantize(Q2)
    inv.save(update_fields=['subtotal', 'shipping_cost', 'grand_total'])
    for it, r in zip(inv.items.order_by('id'), row.get('items') or []):
        it.landed_unit_price_ils = r.get('landed_unit_price_ils')
        it.landed_line_total_ils = r.get('landed_line_total_ils')
        it.save(update_fields=['landed_unit_price_ils', 'landed_line_total_ils'])
