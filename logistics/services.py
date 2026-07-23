"""P-H-1/3: Business-logic services for logistics app.

Mirrors sales/services.py patterns for attached payment vouchers (M2-T3)
and AP account resolution.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.models import Account, Cheque
from core.payments import document_payment_summary

DEC = Decimal("0.01")


def purchase_invoice_payment_summary(invoice):
    """ملخص دفع فاتورة الشراء من السندات المرتبطة والمرحّلة فقط."""
    cached = getattr(invoice, "_payment_summary_cache", None)
    if cached is not None:
        return cached
    fees_total = sum(
        (Decimal(str(f.amount or 0)) for f in invoice.fees.all()),
        Decimal("0"),
    ).quantize(DEC)
    payable = (Decimal(str(invoice.grand_total or 0)) + fees_total).quantize(DEC)
    linked_paid = sum(
        (
            Decimal(str(payment.amount or 0))
            for payment in invoice.supplier_payments.all()
            if payment.is_posted
        ),
        Decimal("0"),
    )
    legacy_paid = sum(
        (
            Decimal(str(payment.amount or 0))
            for payment in invoice.payments.all()
            if payment.is_posted
        ),
        Decimal("0"),
    )
    recorded_paid = linked_paid + legacy_paid
    paid = recorded_paid if recorded_paid > 0 else Decimal(str(invoice.attached_cash_amount or 0))
    if invoice.payment_type == "cash" and invoice.is_posted:
        paid = max(paid, payable)
    summary = {
        "fees_total": fees_total,
        "payable_total": payable,
        **document_payment_summary(payable, paid),
    }
    invoice._payment_summary_cache = summary
    return summary


def annotate_purchase_invoice_payment_summary(queryset):
    """نسخة SQL لملخص الدفع تُستخدم في القوائم والفلترة قبل pagination."""
    from django.db.models import (
        Case, CharField, DecimalField, ExpressionWrapper, F, OuterRef,
        Subquery, Sum, Value, When,
    )
    from django.db.models.functions import Coalesce, Greatest
    from logistics.models import PurchaseInvoiceFee, PurchaseInvoicePayment
    from sales.models import SupplierPayment

    money = DecimalField(max_digits=18, decimal_places=2)

    def total_subquery(model, amount_field="amount", **filters):
        return (
            model.objects
            .filter(invoice_id=OuterRef("pk"), **filters)
            .values("invoice_id")
            .annotate(total=Sum(amount_field))
            .values("total")[:1]
        )

    fee_total = total_subquery(PurchaseInvoiceFee)
    linked_paid = (
        SupplierPayment.objects
        .filter(purchase_invoice_id=OuterRef("pk"), is_posted=True)
        .values("purchase_invoice_id")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )
    legacy_paid = total_subquery(PurchaseInvoicePayment, is_posted=True)
    zero = Value(Decimal("0.00"), output_field=money)

    queryset = queryset.annotate(
        list_fees_total=Coalesce(Subquery(fee_total, output_field=money), zero),
        list_linked_paid=Coalesce(Subquery(linked_paid, output_field=money), zero),
        list_legacy_paid=Coalesce(Subquery(legacy_paid, output_field=money), zero),
    ).annotate(
        list_payable_total=ExpressionWrapper(
            F("grand_total") + F("list_fees_total"), output_field=money,
        ),
        list_recorded_paid=ExpressionWrapper(
            F("list_linked_paid") + F("list_legacy_paid"), output_field=money,
        ),
    ).annotate(
        list_effective_paid=Case(
            When(
                payment_type="cash", is_posted=True,
                then=F("list_payable_total"),
            ),
            When(list_recorded_paid__gt=0, then=F("list_recorded_paid")),
            default=F("attached_cash_amount"),
            output_field=money,
        ),
    ).annotate(
        list_amount_paid=Case(
            When(
                list_effective_paid__gt=F("list_payable_total"),
                then=F("list_payable_total"),
            ),
            default=F("list_effective_paid"),
            output_field=money,
        ),
    ).annotate(
        list_remaining_balance=Greatest(
            ExpressionWrapper(
                F("list_payable_total") - F("list_amount_paid"),
                output_field=money,
            ),
            zero,
        ),
    ).annotate(
        list_payment_status=Case(
            When(list_payable_total__lte=0, then=Value("unpaid")),
            When(
                list_amount_paid__gte=F("list_payable_total"),
                then=Value("paid"),
            ),
            When(list_amount_paid__gt=0, then=Value("partially_paid")),
            default=Value("unpaid"),
            output_field=CharField(),
        ),
    )
    return queryset


def get_or_create_purchase_settings(tenant):
    """FEAT-1: يُعيد (أو يُنشئ) إعدادات الشراء للشركة بقيم افتراضية."""
    from logistics.models import PurchaseSettings

    tenant_id = getattr(tenant, "TenantID", tenant)
    obj = PurchaseSettings.objects.filter(tenant_id=tenant_id).first()
    if obj is None:
        obj = PurchaseSettings.objects.create(tenant_id=tenant_id)
    return obj


def _resolve_ap_account(partner) -> Account:
    """P-H-3: يحلّ حساب الذمم الدائنة للمورد بسلسلة أولويات.

    1. حساب مرتبط بالمورد مباشرة (partner.linked_account)
    2. حساب ذمم مجموعة المورد (partner.group.account_payable)
    3. حساب برمز 2101 (حساب ذمم موردين معياري)
    4. أول حساب خصوم (Liability) نشط في الشركة
    """
    if partner.linked_account_id:
        return partner.linked_account
    if partner.group_id:
        from partners.models import PartnerGroup
        g = PartnerGroup.objects.filter(pk=partner.group_id).first()
        if g and g.account_payable_id:
            return g.account_payable
    ap = Account.objects.filter(tenant_id=partner.tenant_id, code="2101").first()
    if ap:
        return ap
    ap = Account.objects.filter(
        tenant_id=partner.tenant_id, account_type="Liability", is_active=True,
    ).first()
    if ap:
        return ap
    raise ValidationError(
        f"لم يُعثر على حساب ذمم دائنة للمورد «{partner.name}». "
        "اربط المورد بحساب، أو حدد حساب ذمم للمجموعة، أو أنشئ حساب 2101."
    )


def attach_pi_payment_voucher(
    invoice,
    *,
    cash_amount: Decimal | str | float = 0,
    cash_account_id: int | None = None,
    cheques: list[dict] | None = None,
    user=None,
):
    """يربط سند مالي (نقدي + شيكات) بفاتورة الشراء قبل الترحيل.

    Mirror of sales/services.py:attach_payment_voucher for PurchaseInvoice.

    - Replace-semantics: each call replaces previously-attached Draft cheques.
    - The journal is NOT posted here — post handler reads the attached data.
    - Idempotent when called multiple times pre-post.

    cheques: list of dicts with keys:
        cheque_number (str), amount (Decimal/str), bank_name (str, optional),
        due_date (date/str, optional), issue_date (date/str, optional),
        payee_name (str, optional), notes (str, optional).
    """
    if invoice.is_posted:
        raise ValidationError("لا يمكن تعديل السند بعد ترحيل فاتورة الشراء.")

    cash_amount = Decimal(str(cash_amount or 0)).quantize(DEC)
    if cash_amount < 0:
        raise ValidationError("مبلغ النقدي لا يمكن أن يكون سالباً.")

    cheques = cheques or []
    for i, c in enumerate(cheques):
        if not str(c.get("cheque_number", "")).strip():
            raise ValidationError(f"الشيك #{i+1}: رقم الشيك مطلوب.")
        try:
            amt = Decimal(str(c.get("amount", 0)))
        except Exception:
            raise ValidationError(f"الشيك #{i+1}: مبلغ غير صالح.")
        if amt <= 0:
            raise ValidationError(f"الشيك #{i+1}: المبلغ يجب أن يكون أكبر من صفر.")

    cheques_total = sum(
        (Decimal(str(c.get("amount", 0))) for c in cheques), Decimal("0")
    ).quantize(DEC)

    grand = Decimal(str(invoice.grand_total or 0)).quantize(DEC)
    if (cash_amount + cheques_total) > grand:
        raise ValidationError(
            f"مجموع السند ({cash_amount} نقدي + {cheques_total} شيكات) "
            f"يتجاوز مبلغ الفاتورة {grand}."
        )

    if cash_amount > 0 and not cash_account_id:
        raise ValidationError("لا بدّ من تحديد حساب الصندوق عند وجود مبلغ نقدي.")

    with transaction.atomic():
        invoice.attached_cash_amount = cash_amount
        invoice.save(update_fields=["attached_cash_amount"])

        # Replace previously-linked Draft cheques
        Cheque.objects.filter(
            purchase_invoice=invoice, status="Draft"
        ).delete()
        for c in cheques:
            Cheque.objects.create(
                tenant_id=invoice.tenant_id,
                purchase_invoice=invoice,
                partner=invoice.partner,
                direction="Outgoing",
                status="Draft",
                cheque_number=str(c.get("cheque_number")).strip(),
                bank_name=(c.get("bank_name") or "")[:100],
                amount=Decimal(str(c.get("amount"))).quantize(DEC),
                currency_id=invoice.currency_id,
                due_date=c.get("due_date") or None,
                issue_date=c.get("issue_date") or None,
                payee_name=(c.get("payee_name") or "")[:150],
                notes=c.get("notes") or "",
                created_by=user if user and not getattr(user, "is_anonymous", False) else None,
            )


def _resolve_inventory_account(tenant) -> Account:
    """حساب المخزون لقيد استلام البضاعة — 1104 ثم مخزون بالاسم ثم أصل."""
    acc = (
        Account.objects.filter(tenant=tenant, code="1104").first()
        or Account.objects.filter(
            tenant=tenant, account_type="Asset", name__icontains="مخزون",
        ).first()
        or Account.objects.filter(
            tenant=tenant, account_type="Asset", is_active=True,
        ).first()
    )
    if not acc:
        raise ValidationError(
            "لم يُعثر على حساب مخزون (1104). أكمل شجرة الحسابات أولاً."
        )
    return acc


def _resolve_vat_input_account(tenant) -> Account:
    """حساب ضريبة المدخلات (1105) — مطلوب عند وجود ضريبة على الاستلام."""
    acc = (
        Account.objects.filter(tenant=tenant, code="1105").first()
        or Account.objects.filter(
            tenant=tenant, account_type="Asset", name__icontains="ضريبة",
        ).first()
    )
    if not acc or acc.account_type != "Asset":
        raise ValidationError(
            "ضريبة المدخلات > 0 تتطلب حساب «1105 ضريبة مدخلات» من نوع Asset."
        )
    return acc


def _resolve_gr_ir_account(tenant) -> Account:
    """الحساب الوسيط «بضاعة مُستلَمة لم تُفوتَر» (GR/IR Clearing، كود 2106).

    يفصل حدث استلام البضاعة عن الالتزام للمورّد: قيد الاستلام يدائنه، وقيد
    الفاتورة يدينه — فيُصفَّر عندما يُنشآن معاً. يُنشأ تلقائياً للمستأجرين الذين
    لم تُبذَر شجرتهم بعد (لا يتطلب إعادة seed).
    """
    acc = Account.objects.filter(tenant=tenant, code="2106").first()
    if acc:
        return acc
    parent = Account.objects.filter(tenant=tenant, code="21").first()
    acc, _ = Account.objects.get_or_create(
        tenant=tenant,
        code="2106",
        defaults={
            "name": "بضاعة مُستلَمة لم تُفوتَر (GR/IR Clearing)",
            "account_type": "Liability",
            "parent": parent,
            "is_active": True,
        },
    )
    return acc


def receive_purchase_invoice(invoice, *, lines, branch=None, user=None, movement_date=None):
    """استلام بضاعة فاتورة شراء محلية إلى المخزن (انعكاس على المستودع + قيد).

    حصري للفواتير المحلية (غير مستوردة: بلا صفقة/شحنة/تخليص) — مسار الاستيراد
    يستلم البضاعة عبر تخليص الشحنة، لا من هنا.

    lines: قائمة [{'item_id': int, 'quantity': Decimal, 'warehouse_id': int}].
    لكل بند ذي صنف مخزون: تُنشأ حركة IN (متوسط مرجح) موسومة بالفرع والمستودع،
    ويُحدَّث received_quantity. ثم يُرحَّل قيد استلام للقيمة المستلمة في هذا النداء
    (مدين مخزون + ضريبة مدخلات / دائن ذمم المورد أو صندوق/بنك).

    العملية ذرّية. إعادة الإرسال مرفوضة ضمنياً: لا يمكن استلام أكثر من المطلوب،
    فإن استُلمت الكميات كلها يرفض النداء التالي «لا يوجد ما يُستلَم».
    """
    import datetime
    import logging
    from inventory.models import Warehouse
    from inventory.services import record_stock_movement
    from accounting.services import post_journal
    from .models import PurchaseInvoice

    logger = logging.getLogger(__name__)

    if invoice.deal_id or invoice.shipment_id or invoice.clearance_id:
        raise ValidationError(
            "هذه فاتورة مستوردة — يتم استلام بضاعتها من تخليص الشحنة، لا من الفاتورة."
        )

    if not lines:
        raise ValidationError("حدّد البنود والكميات المراد استلامها.")

    if movement_date is None:
        movement_date = invoice.invoice_date or datetime.date.today()

    base_factor = Decimal(str(invoice.exchange_rate or 1))
    items_by_id = {it.id: it for it in invoice.items.select_related('product').all()}

    inv_net = Decimal('0')   # صافي قيمة المخزون المستلمة (بالعملة الأساس)
    inv_vat = Decimal('0')   # ضريبة المدخلات على المستلَم
    movements = []

    with transaction.atomic():
        for raw in lines:
            item_id = raw.get('item_id')
            item = items_by_id.get(int(item_id)) if item_id is not None else None
            if not item:
                raise ValidationError(f"البند {item_id} لا ينتمي لهذه الفاتورة.")
            if not item.product_id:
                raise ValidationError(
                    f"البند «{item.name}» بلا صنف مخزون مربوط — لا يمكن استلامه."
                )

            try:
                qty = Decimal(str(raw.get('quantity', 0)))
            except Exception:
                raise ValidationError(f"كمية غير صالحة للبند «{item.name}».")
            if qty <= 0:
                continue

            ordered = Decimal(str(item.quantity or 0))
            already = Decimal(str(item.received_quantity or 0))
            remaining = ordered - already
            if qty > remaining:
                raise ValidationError(
                    f"البند «{item.name}»: الكمية المطلوب استلامها ({qty}) "
                    f"تتجاوز المتبقي ({remaining})."
                )

            wh = Warehouse.objects.filter(
                pk=raw.get('warehouse_id'), tenant=invoice.tenant
            ).first()
            if not wh:
                raise ValidationError(f"المستودع المحدد للبند «{item.name}» غير موجود.")

            unit_price = Decimal(str(item.unit_price or 0))
            if unit_price <= 0:
                # احتياطي: اشتقاق تكلفة الوحدة من إجمالي السطر إن كان سعر الوحدة صفراً
                total_price = Decimal(str(item.total_price or 0))
                if total_price > 0 and ordered > 0:
                    unit_price = total_price / ordered
            unit_cost = (unit_price * base_factor)
            line_net = (qty * unit_cost).quantize(DEC)
            vat_pct = Decimal(str(item.vat_percent or 0)) if item.is_taxable else Decimal('0')
            line_vat = (line_net * vat_pct / Decimal('100')).quantize(DEC)

            mv = record_stock_movement(
                product=item.product,
                movement_type='IN',
                quantity=qty,
                unit_cost=unit_cost,
                reference_type='PURCHASE_INVOICE',
                reference_id=invoice.id,
                partner=invoice.partner,
                movement_date=movement_date,
                notes=f"استلام فاتورة {invoice.invoice_number} | مستودع {wh.name}",
                tenant=invoice.tenant,
                branch=branch,
                warehouse=wh,
            )
            movements.append(mv)

            item.received_quantity = already + qty
            item.warehouse = wh.name
            item.save(update_fields=['received_quantity', 'warehouse'])

            inv_net += line_net
            inv_vat += line_vat

        if not movements:
            raise ValidationError("لا يوجد ما يُستلَم — تحقق من الكميات.")

        # ── ترحيل قيد الاستلام للقيمة المستلمة في هذا النداء ──
        # استلام بقيمة صفرية (فاتورة كمية فقط بلا أسعار) مشروع: ينعكس على المخزن
        # دون قيد محاسبي (لا قيد فارغ يُرفض من post_journal).
        gross = (inv_net + inv_vat).quantize(DEC)
        journal = None
        if gross > 0:
            inventory_account = _resolve_inventory_account(invoice.tenant)
            # Feature 2: قيد الاستلام يدين المخزون/الضريبة ويدائن ذمم المورد بالكامل
            # فقط — لا يُسوّي النقدية. الدفع للمورد يُسجَّل كوصل دفع مستقل
            # (SupplierPayment، Dr ذمم المورد / Cr صندوق) بعد الاستلام.
            ap_account = _resolve_ap_account(invoice.partner)
            lines_payload = [
                {'account': inventory_account.id, 'debit': inv_net, 'credit': Decimal('0'),
                 'partner': invoice.partner_id},
            ]
            if inv_vat > 0:
                vat_acc = _resolve_vat_input_account(invoice.tenant)
                lines_payload.append({
                    'account': vat_acc.id, 'debit': inv_vat, 'credit': Decimal('0'),
                    'partner': invoice.partner_id,
                })

            # دائن ذمم المورد بكامل القيمة المستلمة
            lines_payload.append({
                'account': ap_account.id, 'debit': Decimal('0'), 'credit': gross,
                'partner': invoice.partner_id,
            })

            journal = post_journal(
                tenant_id=invoice.tenant_id,
                transaction_date=movement_date,
                reference_type='PURCHASE_INVOICE',
                reference_id=invoice.id,
                description=f"استلام بضاعة فاتورة {invoice.invoice_number} | {invoice.partner.name}"[:500],
                lines_data=lines_payload,
                branch_id=branch.id if branch else None,
                user=user if user and not getattr(user, 'is_anonymous', False) else None,
                idempotent=False,
            )

        # ── تحديث حالة الاستلام للفاتورة ──
        product_items = [it for it in items_by_id.values() if it.product_id]
        fully = all(
            Decimal(str(it.received_quantity or 0)) >= Decimal(str(it.quantity or 0))
            for it in product_items
        )
        any_received = any(
            Decimal(str(it.received_quantity or 0)) > 0 for it in product_items
        )
        invoice.receipt_status = (
            PurchaseInvoice.RECEIPT_FULL if fully
            else PurchaseInvoice.RECEIPT_PARTIAL if any_received
            else PurchaseInvoice.RECEIPT_NOT
        )
        update_fields = ['receipt_status']
        if journal is not None and not invoice.is_posted:
            invoice.is_posted = True
            invoice.journal = journal
            update_fields += ['is_posted', 'journal']
        invoice.save(update_fields=update_fields)

        # نموذج «تكلفة المنتجات»: اجعل avg_cost المتوسط المرجّح للمشتريات المرحّلة
        # (مصدر الحقيقة الجديد) كي يقرأ ترحيل COGS عند البيع القيمة الصحيحة.
        if invoice.is_posted:
            # النموذج الدوري يَضبط avg_cost من كل المشتريات؛ أما شركات المتوسط
            # المرجّح المتحرك فيُترك WAC الذي بناه record_stock_movement (تكلفة
            # لحظة البيع) كما هو. القرار مركزي في apply_purchase_cost_model.
            from inventory.services import apply_purchase_cost_model
            seen = set()
            for it in product_items:
                if it.product_id and it.product_id not in seen:
                    seen.add(it.product_id)
                    apply_purchase_cost_model(it.product)

    logger.info(
        "Purchase invoice #%s received: %d movement(s), receipt_status=%s, journal=%s",
        invoice.id, len(movements), invoice.receipt_status,
        journal.id if journal else None,
    )
    return {'movements': movements, 'journal': journal, 'receipt_status': invoice.receipt_status}


def returnable_lines_for_invoice(original_invoice):
    """W6: بنود الفاتورة الأصلية مع (المفوتر · المرتجع سابقاً · المتبقّي القابل للإرجاع)
    لكل صنف — يغذّي منتقي بنود المرجع في الواجهة. مصدر حقيقة واحد مع حارس الإنشاء.
    يُجمّع بالصنف (لو تكرّر الصنف في أسطر الفاتورة)."""
    from decimal import Decimal as _D
    from .models import PurchaseInvoiceItem

    if original_invoice is None:
        return []

    orig: dict[int, dict] = {}
    for it in original_invoice.items.all():
        if not it.product_id:
            continue
        row = orig.setdefault(it.product_id, {
            'product': it.product_id,
            'name': it.name or (getattr(it.product, 'name_ar', None) or str(it.product_id)),
            'unit_price': _D(str(it.unit_price or 0)),
            'invoiced_qty': _D('0'),
        })
        row['invoiced_qty'] += _D(str(it.quantity or 0))

    returned: dict[int, _D] = {}
    prior = PurchaseInvoiceItem.objects.filter(
        invoice__original_invoice=original_invoice,
        invoice__is_return=True,
    ).values_list('product_id', 'quantity')
    for pid, q in prior:
        if pid:
            returned[pid] = returned.get(pid, _D('0')) + _D(str(q or 0))

    out = []
    for pid, row in orig.items():
        ret_q = returned.get(pid, _D('0'))
        remaining = row['invoiced_qty'] - ret_q
        out.append({
            'product': pid,
            'name': row['name'],
            'unit_price': str(row['unit_price']),
            'invoiced_qty': str(row['invoiced_qty']),
            'returned_qty': str(ret_q),
            'remaining_qty': str(remaining if remaining > 0 else _D('0')),
        })
    return out


def create_purchase_return(
    tenant, *, original_invoice, partner, return_date, lines, notes='',
    invoice_number=None, currency=None, exchange_rate=None, user=None,
):
    """مرجع شراء: إنشاء فاتورة إرجاع للمورد **كمسودة** (بلا ترحيل).

    يُخزَّن المستند فقط (status='draft'، is_posted=False) — لا حركة مخزون ولا قيد.
    الترحيل خطوة منفصلة عبر `post_purchase_return` (زر «ترحيل» من فواتير الشراء).
    نسبة الضريبة تُشتق من بنود الفاتورة الأصلية وتُخزَّن على بند المرجع كي يقرأها
    الترحيل لاحقاً.

    lines: [{'product': int, 'quantity': Decimal, 'unit_price': Decimal}].
    """
    import datetime
    from decimal import Decimal as _D
    from inventory.models import Product
    from .models import PurchaseInvoice, PurchaseInvoiceItem

    if return_date is None:
        return_date = datetime.date.today()
    if partner is None:
        raise ValidationError("المورد مطلوب لمرجع الشراء.")
    if partner.tenant_id != tenant.TenantID:
        raise ValidationError("المورد لا يتبع نفس الشركة.")

    # نسبة الضريبة لكل صنف من الفاتورة الأصلية (لعكسها بدقة عند الترحيل).
    vat_by_product: dict[int, _D] = {}
    if original_invoice is not None:
        for it in original_invoice.items.all():
            if it.product_id and getattr(it, 'is_taxable', False):
                vat_by_product[it.product_id] = _D(str(it.vat_percent or 0))

    clean_lines = []
    for raw in lines or []:
        pid = raw.get('product')
        if not pid:
            continue
        try:
            qty = _D(str(raw.get('quantity', 0)))
            price = _D(str(raw.get('unit_price', 0)))
        except Exception:
            raise ValidationError("كمية أو سعر غير صالح في أحد البنود.")
        if qty <= 0:
            continue
        clean_lines.append({'product': int(pid), 'quantity': qty, 'unit_price': price})
    if not clean_lines:
        raise ValidationError("أضِف بنداً واحداً على الأقل بكمية موجبة.")

    products = {
        p.id: p for p in Product.objects.filter(
            tenant=tenant, id__in=[l['product'] for l in clean_lines],
        )
    }
    base_factor = _D(str(exchange_rate if exchange_rate is not None else 1))

    with transaction.atomic():
        # W6: منع تجاوز الكمية المرتجعة الكمية الأصلية المفوترة (لكل صنف). المتبقّي
        # القابل للإرجاع = المفوتر − (مجموع كل المراجيع السابقة لنفس الفاتورة الأصلية).
        if original_invoice is not None:
            orig_qty: dict[int, _D] = {}
            for it in original_invoice.items.all():
                if it.product_id:
                    orig_qty[it.product_id] = orig_qty.get(it.product_id, _D('0')) + _D(str(it.quantity or 0))
            returned_qty: dict[int, _D] = {}
            prior = PurchaseInvoiceItem.objects.filter(
                invoice__original_invoice=original_invoice,
                invoice__is_return=True,
            ).values_list('product_id', 'quantity')
            for pid, q in prior:
                if pid:
                    returned_qty[pid] = returned_qty.get(pid, _D('0')) + _D(str(q or 0))
            for l in clean_lines:
                pid = l['product']
                allowed = orig_qty.get(pid, _D('0')) - returned_qty.get(pid, _D('0'))
                if l['quantity'] > allowed:
                    prod = products.get(pid)
                    pname = (getattr(prod, 'name_ar', None) or getattr(prod, 'sku', None)
                             or f"#{pid}") if prod else f"#{pid}"
                    remaining = allowed if allowed > 0 else _D('0')
                    raise ValidationError(
                        f"الكمية المرتجعة للصنف «{pname}» ({l['quantity']}) تتجاوز المتبقّي "
                        f"القابل للإرجاع ({remaining}) من أصل {orig_qty.get(pid, _D('0'))} مفوترة."
                    )

        if not invoice_number:
            last = (
                PurchaseInvoice.objects.filter(tenant=tenant, is_return=True)
                .order_by('-id').values_list('invoice_number', flat=True).first()
            )
            if last and last.startswith('PRET-'):
                try:
                    seq = int(last.split('-')[1]) + 1
                except (ValueError, IndexError):
                    seq = PurchaseInvoice.objects.filter(tenant=tenant, is_return=True).count() + 1
            else:
                seq = PurchaseInvoice.objects.filter(tenant=tenant, is_return=True).count() + 1
            invoice_number = f"PRET-{seq:04d}"

        if currency is None:
            currency = getattr(original_invoice, 'currency', None)
        if currency is None:
            from tenants.models import Currency
            currency = Currency.objects.filter(IsBaseCurrency=True).first() \
                or Currency.objects.order_by('CurrencyID').first()
        if currency is None:
            raise ValidationError("لا توجد عملة معرّفة للمرجع.")

        ret = PurchaseInvoice.objects.create(
            tenant=tenant,
            invoice_number=invoice_number,
            invoice_date=return_date,
            invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
            partner=partner,
            currency=currency,
            exchange_rate=base_factor,
            is_return=True,
            original_invoice=original_invoice,
            payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT,
            status='draft',
            is_posted=False,
            notes=notes or '',
            created_by=user if user and not getattr(user, 'is_anonymous', False) else None,
        )

        inv_net = _D('0')
        inv_vat = _D('0')
        for l in clean_lines:
            prod = products.get(l['product'])
            if prod is None:
                raise ValidationError(f"الصنف {l['product']} غير موجود أو لا يتبع الشركة.")
            qty = l['quantity']
            line_net = (qty * l['unit_price'] * base_factor).quantize(DEC)
            vat_pct = vat_by_product.get(prod.id, _D('0'))
            inv_net += line_net
            inv_vat += (line_net * vat_pct / _D('100')).quantize(DEC)

            PurchaseInvoiceItem.objects.create(
                invoice=ret, product=prod,
                name=getattr(prod, 'name_ar', None) or getattr(prod, 'name', '') or str(prod),
                quantity=qty, unit_price=l['unit_price'],
                total_price=(qty * l['unit_price']).quantize(DEC),
                is_taxable=vat_pct > 0,
                vat_percent=vat_pct,
            )

        ret.subtotal = inv_net
        ret.tax_amount = inv_vat
        ret.grand_total = (inv_net + inv_vat).quantize(DEC)
        ret.save(update_fields=['subtotal', 'tax_amount', 'grand_total'])

    return ret


def post_purchase_return(invoice, *, user=None):
    """ترحيل مرجع شراء (مسودة): يُخرج الكمية من المخزن (RETURN_OUT) ويُرحّل قيداً
    عكسياً للشراء (Dr ذمم المورد الإجمالي / Cr مخزون الصافي + Cr ض.مدخلات).

    الأموال: المرجع يُخفّض ذمم المورد؛ إن كانت الفاتورة مدفوعة يصبح المورد مديناً
    لنا (رصيد سالب) يُحصَّل بسند صرف/قبض مستقل — مطابقةً لتدفّق النظام القائم.
    """
    import datetime
    import logging
    from decimal import Decimal as _D
    from inventory.services import record_stock_movement
    from accounting.services import post_journal, validate_fiscal_period

    logger = logging.getLogger(__name__)

    if not getattr(invoice, 'is_return', False):
        raise ValidationError("هذه ليست فاتورة مرجع شراء.")
    if invoice.is_posted:
        raise ValidationError("المرجع مرحّل مسبقاً.")

    tenant = invoice.tenant
    partner = invoice.partner
    return_date = invoice.invoice_date or datetime.date.today()
    base_factor = _D(str(invoice.exchange_rate or 1))

    with transaction.atomic():
        validate_fiscal_period(tenant.TenantID, return_date)

        items = list(invoice.items.select_related('product').all())
        if not items:
            raise ValidationError("المرجع بلا بنود.")

        inv_net = _D('0')
        inv_vat = _D('0')
        movements = []
        for it in items:
            qty = _D(str(it.quantity or 0))
            if qty <= 0:
                continue
            line_net = (qty * _D(str(it.unit_price or 0)) * base_factor).quantize(DEC)
            vat_pct = _D(str(it.vat_percent or 0)) if it.is_taxable else _D('0')
            inv_net += line_net
            inv_vat += (line_net * vat_pct / _D('100')).quantize(DEC)

            prod = it.product
            if prod and not getattr(prod, 'is_service', False):
                mv = record_stock_movement(
                    product=prod,
                    movement_type='RETURN_OUT',
                    quantity=qty,
                    unit_cost=_D(str(prod.avg_cost or 0)),
                    reference_type='PURCHASE_RETURN',
                    reference_id=invoice.id,
                    partner=partner,
                    movement_date=return_date,
                    notes=f"مرجع شراء {invoice.invoice_number}",
                    tenant=tenant,
                )
                movements.append(mv)

        gross = (inv_net + inv_vat).quantize(DEC)
        journal = None
        if gross > 0:
            ap_account = _resolve_ap_account(partner)
            inventory_account = _resolve_inventory_account(tenant)
            lines_payload = [
                {'account': ap_account.id, 'debit': gross, 'credit': _D('0'),
                 'partner': partner.id},
                {'account': inventory_account.id, 'debit': _D('0'), 'credit': inv_net,
                 'partner': partner.id},
            ]
            if inv_vat > 0:
                vat_acc = _resolve_vat_input_account(tenant)
                lines_payload.append({
                    'account': vat_acc.id, 'debit': _D('0'), 'credit': inv_vat,
                    'partner': partner.id,
                })
            journal = post_journal(
                tenant_id=tenant.TenantID,
                transaction_date=return_date,
                reference_type='PURCHASE_RETURN',
                reference_id=invoice.id,
                description=f"مرجع شراء {invoice.invoice_number} | {partner.name}"[:500],
                lines_data=lines_payload,
                currency=invoice.currency,
                exchange_rate=base_factor,
                user=user if user and not getattr(user, 'is_anonymous', False) else None,
                idempotent=False,
            )

        invoice.subtotal = inv_net
        invoice.tax_amount = inv_vat
        invoice.grand_total = gross
        invoice.is_posted = True
        invoice.journal = journal
        invoice.status = 'completed'
        invoice.save(update_fields=[
            'subtotal', 'tax_amount', 'grand_total', 'is_posted', 'journal', 'status',
        ])

    logger.info(
        "Purchase return #%s posted: %d movement(s), journal=%s, gross=%s",
        invoice.id, len(movements), journal.id if journal else None, gross,
    )
    return invoice
