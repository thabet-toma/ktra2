"""P-H-1/3: Business-logic services for logistics app.

Mirrors sales/services.py patterns for attached payment vouchers (M2-T3)
and AP account resolution.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.models import Account, Cheque

DEC = Decimal("0.01")


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
            from inventory.services import set_avg_cost_from_purchases
            seen = set()
            for it in product_items:
                if it.product_id and it.product_id not in seen:
                    seen.add(it.product_id)
                    set_avg_cost_from_purchases(it.product)

    logger.info(
        "Purchase invoice #%s received: %d movement(s), receipt_status=%s, journal=%s",
        invoice.id, len(movements), invoice.receipt_status,
        journal.id if journal else None,
    )
    return {'movements': movements, 'journal': journal, 'receipt_status': invoice.receipt_status}
