from decimal import Decimal, InvalidOperation

from django.db import migrations


def _decimal(value, default='0'):
    try:
        return Decimal(str(value if value not in (None, '') else default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _nonnegative_int(value):
    try:
        return max(0, int(Decimal(str(value or 0))))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def migrate_documents(apps, schema_editor):
    MirrorDoc = apps.get_model('bridge', 'FirestoreMirrorDoc')
    Currency = apps.get_model('tenants', 'Currency')
    Partner = apps.get_model('partners', 'Partner')
    Product = apps.get_model('inventory', 'Product')
    SupplierQuotation = apps.get_model('logistics', 'SupplierQuotation')
    SupplierQuotationLine = apps.get_model('logistics', 'SupplierQuotationLine')
    PurchaseOrder = apps.get_model('logistics', 'PurchaseOrder')
    PurchaseOrderLine = apps.get_model('logistics', 'PurchaseOrderLine')

    currencies = {
        str(row.Code or '').upper(): row
        for row in Currency.objects.all()
    }

    for mirror in MirrorDoc.objects.filter(
        path__regex=r'^(price_offers|import_price_offers)/[^/]+$',
        tenant__isnull=False,
    ).iterator():
        data = mirror.data if isinstance(mirror.data, dict) else {}
        root = mirror.path.split('/', 1)[0]
        scope = 'import' if root == 'import_price_offers' else 'local'
        doc_type = str(data.get('offerType') or 'incoming_offer')
        if doc_type not in ('incoming_offer', 'outgoing_order'):
            continue

        supplier_raw = str(data.get('supplierId') or '')
        if not supplier_raw.isdigit():
            continue
        supplier = Partner.objects.filter(
            pk=int(supplier_raw),
            tenant_id=mirror.tenant_id,
            partner_type='Supplier',
        ).first()
        if supplier is None:
            continue

        raw_lines = data.get('items') if isinstance(data.get('items'), list) else []
        lines = []
        valid = True
        for index, raw in enumerate(raw_lines, start=1):
            if not isinstance(raw, dict):
                valid = False
                break
            product_raw = str(raw.get('itemId') or raw.get('id') or '')
            if not product_raw.isdigit():
                valid = False
                break
            product = Product.objects.filter(
                pk=int(product_raw),
                tenant_id=mirror.tenant_id,
            ).first()
            quantity = _decimal(raw.get('quantity'))
            unit_price = _decimal(raw.get('unitPrice'))
            if product is None or quantity <= 0 or unit_price < 0:
                valid = False
                break
            lines.append({
                'product': product,
                'seq': index,
                'name_snapshot': str(
                    raw.get('name') or product.name_ar or product.name_en or ''
                )[:255],
                'description_line': str(raw.get('specifications') or ''),
                'quantity': quantity,
                'unit_price': unit_price,
                'line_total': (quantity * unit_price).quantize(Decimal('0.01')),
            })
        if not valid or not lines:
            continue

        currency = currencies.get(str(data.get('currency') or 'USD').upper())
        if currency is None:
            currency = Currency.objects.order_by('CurrencyID').first()
        if currency is None:
            continue

        subtotal = sum(
            (line['line_total'] for line in lines),
            Decimal('0'),
        ).quantize(Decimal('0.01'))
        discount = max(Decimal('0'), _decimal(data.get('discountAmount')))
        discount = min(discount, subtotal)
        tax_rate = (
            Decimal('0')
            if scope == 'import'
            else max(Decimal('0'), _decimal(data.get('taxRate')))
        )
        taxable = subtotal - discount
        tax_amount = (
            taxable * tax_rate / Decimal('100')
        ).quantize(Decimal('0.01'))
        shipping = max(Decimal('0'), _decimal(data.get('shippingCost')))
        shipping_included = bool(data.get('shippingIncluded'))
        grand_total = (
            taxable + tax_amount + (Decimal('0') if shipping_included else shipping)
        ).quantize(Decimal('0.01'))
        number = str(data.get('offerNumber') or '').strip()

        if doc_type == 'incoming_offer':
            prefix = 'IQ' if scope == 'import' else 'PQ'
            if not number:
                number = f'{prefix}-LEGACY-{mirror.pk}'
            if SupplierQuotation.objects.filter(
                tenant_id=mirror.tenant_id,
                scope=scope,
                quotation_number=number,
            ).exists():
                continue
            status = {
                'initial': 'draft',
                'pending_info': 'sent',
                'under_discussion': 'sent',
                'approved_for_shipping': 'accepted',
                'rejected': 'rejected',
            }.get(str(data.get('status') or ''), 'draft')
            quotation = SupplierQuotation.objects.create(
                tenant_id=mirror.tenant_id,
                quotation_number=number,
                scope=scope,
                supplier=supplier,
                quotation_date=data.get('offerDate') or mirror.created_at.date(),
                valid_until=data.get('validUntil') or None,
                status=status,
                currency=currency,
                exchange_rate=max(Decimal('0.000001'), _decimal(data.get('exchangeRate'), '1')),
                subtotal=subtotal,
                discount_amount=discount,
                tax_rate=tax_rate,
                tax_amount=tax_amount,
                grand_total=grand_total,
                shipping_cost_estimate=shipping,
                is_shipping_included=shipping_included,
                shipping_method=str(data.get('shippingMethod') or 'Sea')[:50],
                payment_method=str(data.get('paymentMethod') or 'T/T')[:50],
                production_days=_nonnegative_int(data.get('productionDays')),
                delivery_days=_nonnegative_int(data.get('deliveryDays')),
                total_weight_kg=max(Decimal('0'), _decimal(data.get('totalWeight'))),
                notes=str(data.get('internalNotes') or ''),
            )
            SupplierQuotationLine.objects.bulk_create([
                SupplierQuotationLine(
                    tenant_id=mirror.tenant_id,
                    quotation=quotation,
                    **line,
                )
                for line in lines
            ])
            continue

        # طلبية الاستيراد القانونية هي LogisticsDeal؛ لا ننشئ نسخة ثانية هنا.
        if scope == 'import':
            continue
        if not number:
            number = f'PO-LEGACY-{mirror.pk}'
        if PurchaseOrder.objects.filter(
            tenant_id=mirror.tenant_id,
            order_number=number,
        ).exists():
            continue
        order = PurchaseOrder.objects.create(
            tenant_id=mirror.tenant_id,
            order_number=number,
            supplier=supplier,
            order_date=data.get('offerDate') or mirror.created_at.date(),
            expected_delivery_date=data.get('validUntil') or None,
            status='draft',
            currency=currency,
            exchange_rate=max(Decimal('0.000001'), _decimal(data.get('exchangeRate'), '1')),
            subtotal=subtotal,
            discount_amount=discount,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            grand_total=grand_total,
            shipping_cost=shipping,
            is_shipping_included=shipping_included,
            shipping_method=str(data.get('shippingMethod') or '')[:50],
            payment_method=str(data.get('paymentMethod') or '')[:50],
            delivery_days=_nonnegative_int(data.get('deliveryDays')),
            notes=str(data.get('internalNotes') or ''),
        )
        PurchaseOrderLine.objects.bulk_create([
            PurchaseOrderLine(
                tenant_id=mirror.tenant_id,
                order=order,
                **line,
            )
            for line in lines
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('bridge', '0003_scope_tasks_to_tenant'),
        ('logistics', '0059_purchaseorder_purchaseorderline_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_documents, migrations.RunPython.noop),
    ]
