from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from inventory.models import Product
from partners.models import Partner
from tenants.models import Currency

from .models import (
    CustomerPayment,
    DeliveryOrder,
    PaymentAllocation,
    SalesInvoice,
    SalesInvoiceLine,
    SalesQuotation,
    SalesQuotationLine,
    SalesSettings,
)
from .services import next_invoice_number, recalculate_invoice_amounts


def _as_product(value):
    """Normalize a line's ``product`` to a Product instance.

    DRF's PrimaryKeyRelatedField already resolves the FK to a Product
    instance during validation, so re-querying with ``pk=<instance>``
    raises TypeError on Django 6. Accept either a resolved instance or a
    raw pk (defensive for non-DRF callers); return None if not found.
    """
    if value is None:
        return None
    if isinstance(value, Product):
        return value
    return Product.objects.filter(pk=value).first()


def _validate_stock_lines(tenant, lines_data, stock_on_post: bool) -> None:
    """يمنع بيع كمية أكبر من الرصيد عند تفعيل خصم المخزون عند الترحيل."""
    if not stock_on_post or not lines_data:
        return
    for row in lines_data:
        d = dict(row) if isinstance(row, dict) else row
        pid = d.get("product")
        qty = Decimal(str(d.get("quantity", 0)))
        if qty <= 0:
            raise serializers.ValidationError(
                {"lines": "الكمية يجب أن تكون أكبر من صفر لكل سطر."}
            )
        if not pid:
            raise serializers.ValidationError({"lines": "يجب اختيار صنف لكل سطر."})
        prod = _as_product(pid)
        if prod is None:
            raise serializers.ValidationError({"lines": f"صنف غير موجود: {pid}"})
        if prod.tenant_id != tenant.TenantID:
            raise serializers.ValidationError(
                {"lines": f"الصنف {prod.sku} لا يتبع نفس الشركة."}
            )
        # M2-14: allow_negative_stock يتجاوز فحص الرصيد (الخدمة هي المرجع الوحيد)
        if getattr(prod, "allow_negative_stock", False):
            continue
        if qty > prod.quantity_on_hand + Decimal("0.0001"):
            raise serializers.ValidationError(
                {
                    "lines": (
                        f"«{prod.sku}»: الكمية ({qty}) تتجاوز المتوفر في المخزون ({prod.quantity_on_hand})."
                    )
                }
            )


class SalesInvoiceLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = SalesInvoiceLine
        fields = [
            "id",
            "product",
            "quantity",
            "unit_price",
            "line_discount",
            "tax_rate",
            "line_total_excl_tax",
            "line_tax_amount",
        ]
        read_only_fields = ["line_total_excl_tax", "line_tax_amount"]


class SalesInvoiceListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = SalesInvoice
        fields = [
            "id",
            "invoice_number",
            "customer",
            "customer_name",
            "invoice_date",
            "due_date",
            "invoice_type",
            "status",
            "grand_total",
            "amount_paid",
            "currency",
            "stock_on_post",
        ]


class SalesInvoiceSerializer(serializers.ModelSerializer):
    lines = SalesInvoiceLineSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    invoice_number = serializers.CharField(required=False, allow_blank=True)
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Partner.objects.all(), required=False, allow_null=True
    )
    currency = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = SalesInvoice
        fields = [
            "id",
            "invoice_number",
            "customer",
            "customer_name",
            "invoice_date",
            "due_date",
            "invoice_type",
            "currency",
            "exchange_rate",
            "status",
            "subtotal_excl_tax",
            "invoice_discount",
            "tax_amount",
            "grand_total",
            "amount_paid",
            "revenue_account",
            "cash_or_bank_account",
            "accounts_receivable_account",
            "journal",
            "stock_on_post",
            "notes",
            "lines",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "subtotal_excl_tax",
            "tax_amount",
            "grand_total",
            "amount_paid",
            "created_at",
            "journal",
            "customer_name",
        ]

    def create(self, validated_data):
        from .services import get_or_create_sales_settings

        lines_data = validated_data.pop("lines")
        tenant = validated_data["tenant"]

        # تطبيق القيم الافتراضية من إعدادات المبيعات (requirement #1)
        ss = get_or_create_sales_settings(tenant)
        if not validated_data.get("customer") and ss.default_customer_id:
            validated_data["customer"] = ss.default_customer
        if not validated_data.get("currency") and ss.default_currency_id:
            validated_data["currency"] = ss.default_currency
        if not validated_data.get("invoice_type"):
            validated_data["invoice_type"] = ss.default_payment_type
        if "stock_on_post" not in validated_data:
            validated_data["stock_on_post"] = ss.stock_on_post_default
        if (
            validated_data.get("invoice_type") == SalesInvoice.INVOICE_CASH
            and not validated_data.get("cash_or_bank_account")
            and ss.default_cash_account_id
        ):
            validated_data["cash_or_bank_account"] = ss.default_cash_account

        cust = validated_data.get("customer")
        if cust is None:
            raise serializers.ValidationError(
                {"customer": "لم يتم تحديد عميل ولا يوجد عميل افتراضي."}
            )
        if cust.tenant_id != tenant.TenantID:
            raise serializers.ValidationError({"customer": "العميل لا يتبع نفس الشركة."})
        inv_num = validated_data.get("invoice_number") or ""
        if not str(inv_num).strip():
            validated_data["invoice_number"] = next_invoice_number(tenant.TenantID)
        if not lines_data:
            raise serializers.ValidationError({"lines": "يجب إضافة بند واحد على الأقل."})
        for row in lines_data:
            prod = _as_product(row.get("product"))
            if prod is None:
                raise serializers.ValidationError(
                    {"lines": f"صنف غير موجود: {row.get('product')}"}
                )
            if prod.tenant_id != tenant.TenantID:
                raise serializers.ValidationError(
                    {"lines": f"الصنف {prod.sku} لا يتبع نفس الشركة."}
                )
        _validate_stock_lines(tenant, lines_data, validated_data.get("stock_on_post", True))
        with transaction.atomic():
            inv = SalesInvoice.objects.create(**validated_data)
            for row in lines_data:
                rw = dict(row)
                rw.pop("id", None)
                SalesInvoiceLine.objects.create(tenant=tenant, invoice=inv, **rw)
            lines = list(inv.lines.select_related("tax_rate", "tax_rate__tax_account"))
            recalculate_invoice_amounts(inv, lines)
            SalesInvoiceLine.objects.bulk_update(
                lines,
                ["line_total_excl_tax", "line_tax_amount"],
            )
            inv.save(
                update_fields=[
                    "subtotal_excl_tax",
                    "tax_amount",
                    "grand_total",
                ]
            )
        return inv

    def update(self, instance, validated_data):
        if instance.status != SalesInvoice.STATUS_DRAFT:
            raise serializers.ValidationError("لا يمكن تعديل فاتورة مرحّلة أو ملغاة.")
        lines_data = validated_data.pop("lines", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        tenant = instance.tenant
        if lines_data is not None:
            if not lines_data:
                raise serializers.ValidationError({"lines": "يجب إضافة بند واحد على الأقل."})
            for row in lines_data:
                raw = dict(row)
                prod = _as_product(raw.get("product"))
                if prod is None:
                    raise serializers.ValidationError(
                        {"lines": f"صنف غير موجود: {raw.get('product')}"}
                    )
                if prod.tenant_id != tenant.TenantID:
                    raise serializers.ValidationError(
                        {"lines": f"الصنف {prod.sku} لا يتبع نفس الشركة."}
                    )
            stock_flag = validated_data.get("stock_on_post", instance.stock_on_post)
            _validate_stock_lines(tenant, lines_data, stock_flag)
            kept: set[int] = set()
            for row in lines_data:
                raw = dict(row)
                lid = raw.pop("id", None)
                if lid is not None and str(lid).strip() == "":
                    lid = None
                if lid:
                    line = SalesInvoiceLine.objects.filter(pk=lid, invoice=instance).first()
                    if not line:
                        raise serializers.ValidationError(
                            {"lines": f"سطر غير موجود أو لا يتبع الفاتورة: {lid}"}
                        )
                    for key, val in raw.items():
                        setattr(line, key, val)
                    line.save()
                    kept.add(line.id)
                else:
                    line = SalesInvoiceLine.objects.create(
                        tenant=tenant, invoice=instance, **raw
                    )
                    kept.add(line.id)
            SalesInvoiceLine.objects.filter(invoice=instance).exclude(pk__in=kept).delete()
        lines = list(instance.lines.select_related("tax_rate", "tax_rate__tax_account"))
        recalculate_invoice_amounts(instance, lines)
        SalesInvoiceLine.objects.bulk_update(
            lines,
            ["line_total_excl_tax", "line_tax_amount"],
        )
        instance.save(
            update_fields=[
                "subtotal_excl_tax",
                "tax_amount",
                "grand_total",
            ]
        )
        return instance


class PaymentAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAllocation
        fields = [
            "id",
            "invoice",
            "amount",
            "amount_in_invoice_currency",
            "conversion_rate",
        ]
        read_only_fields = ["id", "amount_in_invoice_currency", "conversion_rate"]


class CustomerPaymentSerializer(serializers.ModelSerializer):
    allocations = PaymentAllocationSerializer(many=True, required=False)

    def validate(self, attrs):
        if self.instance is None and self.initial_data.get("allocations") is not None:
            data = self.initial_data.get("allocations") or []
            total = sum(Decimal(str(x.get("amount", 0))) for x in data)
            if total != attrs["amount"]:
                raise serializers.ValidationError(
                    {"allocations": "مجموع التوزيعات يجب أن يساوي مبلغ الدفعة."}
                )
        return attrs

    class Meta:
        model = CustomerPayment
        fields = [
            "id",
            "partner",
            "payment_date",
            "amount",
            "currency",
            "exchange_rate",
            "cash_or_bank_account",
            "journal",
            "is_posted",
            "notes",
            "allocations",
            "created_at",
        ]
        read_only_fields = ["id", "journal", "is_posted", "created_at"]

    def create(self, validated_data):
        allocs = validated_data.pop("allocations", [])
        pay = CustomerPayment.objects.create(**validated_data)
        for a in allocs:
            PaymentAllocation.objects.create(tenant=pay.tenant, payment=pay, **a)
        return pay


class SalesSettingsSerializer(serializers.ModelSerializer):
    default_customer_name = serializers.CharField(
        source="default_customer.name", read_only=True
    )
    default_currency_code = serializers.CharField(
        source="default_currency.Code", read_only=True
    )
    default_revenue_account_product_name = serializers.CharField(
        source="default_revenue_account_product.name", read_only=True
    )
    default_revenue_account_service_name = serializers.CharField(
        source="default_revenue_account_service.name", read_only=True
    )
    default_cash_account_name = serializers.CharField(
        source="default_cash_account.name", read_only=True
    )
    default_vat_rate_code = serializers.CharField(
        source="default_vat_rate.code", read_only=True
    )
    default_vat_rate_value = serializers.DecimalField(
        source="default_vat_rate.rate",
        max_digits=6,
        decimal_places=3,
        read_only=True,
    )
    vat_input_account_name = serializers.CharField(
        source="vat_input_account.name", read_only=True, default=None
    )

    class Meta:
        model = SalesSettings
        fields = [
            "id",
            "default_customer",
            "default_customer_name",
            "default_currency",
            "default_currency_code",
            "default_revenue_account_product",
            "default_revenue_account_product_name",
            "default_revenue_account_service",
            "default_revenue_account_service_name",
            "default_cash_account",
            "default_cash_account_name",
            "default_inventory_account",
            "default_cogs_account",
            "default_ar_account",
            "default_payment_type",
            "stock_on_post_default",
            "default_vat_rate",
            "default_vat_rate_code",
            "default_vat_rate_value",
            "vat_input_account",
            "vat_input_account_name",
            "prices_include_tax",
            "auto_post_invoices",
            "show_journal_preview",
            "default_shipping_origin",
            "default_shipping_destination",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "updated_at",
            "default_customer_name",
            "default_currency_code",
            "default_revenue_account_product_name",
            "default_revenue_account_service_name",
            "default_cash_account_name",
            "default_vat_rate_code",
            "default_vat_rate_value",
            "vat_input_account_name",
        ]


class DeliveryOrderSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)

    class Meta:
        model = DeliveryOrder
        fields = [
            "id",
            "tenant",
            "invoice",
            "invoice_number",
            "status",
            "notes",
            "delivered_at",
            "created_at",
        ]
        read_only_fields = ["id", "tenant", "delivered_at", "created_at", "invoice_number"]


class SalesQuotationLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = SalesQuotationLine
        fields = [
            "id",
            "product",
            "quantity",
            "unit_price",
            "line_discount",
            "tax_rate",
            "line_total",
        ]
        read_only_fields = ["line_total"]


class SalesQuotationSerializer(serializers.ModelSerializer):
    lines = SalesQuotationLineSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    invoice_number = serializers.CharField(
        source="invoice.invoice_number", read_only=True, allow_null=True,
    )
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Partner.objects.all(),
    )
    currency = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(),
    )

    class Meta:
        model = SalesQuotation
        fields = [
            "id",
            "quotation_number",
            "customer",
            "customer_name",
            "quotation_date",
            "valid_until",
            "status",
            "currency",
            "exchange_rate",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "grand_total",
            "notes",
            "invoice",
            "invoice_number",
            "lines",
            "created_at",
            "created_by",
        ]
        read_only_fields = [
            "id",
            "status",
            "subtotal",
            "tax_amount",
            "grand_total",
            "created_at",
            "created_by",
            "invoice",
            "invoice_number",
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")
        tenant = validated_data["tenant"]
        subtotal = Decimal("0")
        for ln in lines_data:
            qty = Decimal(str(ln.get("quantity", 0)))
            price = Decimal(str(ln.get("unit_price", 0)))
            disc = Decimal(str(ln.get("line_discount", 0)))
            ln_total = (qty * price * (1 - disc / 100)).quantize(Decimal("0.01"))
            ln["line_total"] = ln_total
            subtotal += ln_total
        tax_amount = (subtotal * Decimal("0.17")).quantize(Decimal("0.01"))
        grand_total = subtotal + tax_amount - Decimal(str(validated_data.get("discount_amount", 0)))
        validated_data["subtotal"] = subtotal
        validated_data["tax_amount"] = tax_amount
        validated_data["grand_total"] = grand_total
        quotation = SalesQuotation.objects.create(**validated_data)
        for ln in lines_data:
            SalesQuotationLine.objects.create(quotation=quotation, **ln)
        return quotation


class SalesQuotationListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = SalesQuotation
        fields = [
            "id",
            "quotation_number",
            "customer",
            "customer_name",
            "quotation_date",
            "valid_until",
            "status",
            "grand_total",
            "currency",
            "created_at",
        ]
