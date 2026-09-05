from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from accounting.models import Account, Cheque
from inventory.models import Product
from partners.models import Partner
from tenants.models import Currency
from core.api_defaults import TenantScopedPrimaryKeyRelatedField
from core.payments import (
    apply_default_cash_account,
    document_partner_balance_summary,
    document_overdue_state,
    resolve_due_date,
    document_payment_summary,
)

from .models import (
    CreditDebitNote,
    CustomerPayment,
    DeliveryOrder,
    DeliveryOrderLine,
    PaymentAllocation,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderLine,
    SalesQuotation,
    SalesQuotationLine,
    SalesSettings,
)
from .services import (
    allocate_invoice_discount,
    guard_loss_invoice,
    invoice_pending_payment_total,
    next_credit_debit_note_number,
    next_invoice_number,
    recalculate_invoice_amounts,
)


def _run_loss_guard(invoice, lines):
    """W1: يشغّل حارس الخسارة على مستوى السطر عند الحفظ (لا الترحيل فقط). يفترض أن
    `lines` جُلبت بـ select_related('product') وأن `recalculate_invoice_amounts`
    مُلئت مسبقاً. لا يفعل شيئاً إن كان الإعداد مطفأً أو الفاتورة مرجعاً."""
    products_by_id = {l.product_id: l.product for l in lines}
    guard_loss_invoice(invoice, lines, products_by_id)


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


def _validate_stock_lines(tenant, lines_data, stock_on_post: bool, *, is_return: bool = False) -> None:
    """يمنع بيع كمية أكبر من الرصيد عند تفعيل خصم المخزون عند الترحيل.

    للمراجيع (`is_return`) البضاعة تدخل للمخزون (مرجع بيع) — لا فحص توفّر، بل
    يُكتفى بالتحقق من الكمية الموجبة ووجود المنتج (يتم أدناه في create/update).
    """
    if not stock_on_post or not lines_data or is_return:
        return
    # M3: resolve the global negative-stock policy once (not per line — avoids N+1).
    # Default to allowing negative stock when no settings row exists yet.
    from .models import SalesSettings
    ss = SalesSettings.objects.filter(tenant_id=tenant.TenantID).first()
    global_allow = ss.allow_negative_stock_default if ss else True
    for row in lines_data:
        d = dict(row) if isinstance(row, dict) else row
        pid = d.get("product")
        qty = Decimal(str(d.get("quantity", 0)))
        if qty <= 0:
            raise serializers.ValidationError(
                {"lines": "الكمية يجب أن تكون أكبر من صفر لكل سطر."}
            )
        if not pid:
            raise serializers.ValidationError({"lines": "يجب اختيار منتج لكل سطر."})
        prod = _as_product(pid)
        if prod is None:
            raise serializers.ValidationError({"lines": f"منتج غير موجود: {pid}"})
        if prod.tenant_id != tenant.TenantID:
            raise serializers.ValidationError(
                {"lines": f"المنتج {prod.sku} لا يتبع نفس الشركة."}
            )
        # M2-14 + M3: المخزون السالب مسموح إن سمح الإعداد العام أو المنتج.
        # **والخدمة معفاةٌ صراحةً**: كان الإعفاء متروكاً لـ`allow_negative_stock`
        # وحده على أساس أن الخدمة تُنشأ به، وهو `default=False` — فخدمةٌ أُنشئت
        # بالافتراضي (ومنها الخدماتُ المزروعة مع القوالب) كانت تُردّ بـ«الكمية
        # تتجاوز المتوفر» على شيءٍ لا مخزون له أصلاً. بقيّة المستودع تعفيها
        # صراحةً (`sales/services/orders.py`، `sales/services/numbering.py`)
        # وهذا الموضع وحده كان شاذّاً.
        if (
            getattr(prod, "is_service", False)
            or global_allow
            or getattr(prod, "allow_negative_stock", False)
        ):
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
    # اسم المنتج (قراءة فقط) لعرض بنود الفاتورة في «تفاصيل الحركة» بكشف الحساب —
    # لقطةُ الترحيل إن وُجدت، وإلا Product.__str__ (name_ar ← name_en ← sku).
    product_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = SalesInvoiceLine
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "delivered_quantity",
            "unit_price",
            "line_discount",
            "tax_rate",
            "line_total_excl_tax",
            "line_tax_amount",
            "unit",
            "warehouse",
            "catalog_no",
            "expiry_date",
            "extra_quantity",
            "line_tax_percent",
            "serials",
            "internal_note",
            "customer_note",
            # THA-18: تخرج **خاماً** لا مطويّةً في `product_name` — الواجهة تحتاج
            # أن تفرّق بين «لقطةٌ مجمَّدة فاعرضها كما هي» و«لا لقطة فاشتقّ الاسم
            # حياً بصيغة الشاشة»، وطيُّهما في حقل واحد يغيّر ما تعرضه المسودّات.
            "name_snapshot",
        ]
        read_only_fields = [
            "line_total_excl_tax", "line_tax_amount", "delivered_quantity",
            "name_snapshot",
        ]

    def validate_serials(self, value):
        from inventory.serials import normalize_serials
        return normalize_serials(value)

    def get_product_name(self, obj):
        # THA-18: الفاتورة المرحّلة تعرض لقطتها المجمَّدة؛ غير المرحَّلة (لقطة
        # فارغة) تتبع اسم المنتج الحي.
        # #22: `product_display_name` لا `str(product)` — وإلا اختلفت المسودّة
        # عن المرحَّلة في ظهور البراند (راجع قرار #22 على التذكرة).
        if obj.name_snapshot:
            return obj.name_snapshot
        if not obj.product_id:
            return None
        from inventory.services import product_display_name
        return product_display_name(obj.product)


class _SalesInvoicePaymentSummarySerializer(serializers.Serializer):
    remaining_balance = serializers.SerializerMethodField()
    # T-DUE: «متأخرة» بُعدٌ فوق حالة الدفع لا قيمةٌ رابعة فيها — قاعدة واحدة
    # مع جانب الشراء (`core.payments.document_overdue_state`).
    is_overdue = serializers.SerializerMethodField()
    days_overdue = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payment_status_display = serializers.SerializerMethodField()
    # T-INTENT: دفعةٌ مرفقة بمسودة لم تُرحَّل بعد. لا تدخل `amount_paid` ولا
    # `payment_status` — فما لم يُرحَّل ليس مدفوعاً في الدفاتر — لكن الفاتورة
    # تعرضها كي لا تكذب شاشةٌ أدخل فيها المستخدم دفعةً فلم يرَ لها أثراً.
    pending_payment_total = serializers.SerializerMethodField()
    customer_balance = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True,
    )

    @staticmethod
    def _payment_summary(obj):
        return document_payment_summary(obj.grand_total, obj.amount_paid)

    def get_pending_payment_total(self, obj) -> str:
        return str(invoice_pending_payment_total(obj))

    def get_remaining_balance(self, obj):
        return str(self._payment_summary(obj)["remaining_balance"])

    def get_payment_status(self, obj):
        return self._payment_summary(obj)["payment_status"]

    def get_payment_status_display(self, obj):
        return self._payment_summary(obj)["payment_status_display"]

    def get_is_overdue(self, obj) -> bool:
        return document_overdue_state(
            obj.due_date, self._payment_summary(obj)["remaining_balance"],
        )["is_overdue"]

    def get_days_overdue(self, obj) -> int:
        return document_overdue_state(
            obj.due_date, self._payment_summary(obj)["remaining_balance"],
        )["days_overdue"]


class _SalesInvoicePaymentDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="payment.id")
    payment_date = serializers.DateField(source="payment.payment_date")
    allocated_amount = serializers.SerializerMethodField()
    total_payment_amount = serializers.DecimalField(
        source="payment.amount", max_digits=18, decimal_places=2,
    )
    currency_code = serializers.CharField(source="payment.currency.Code")
    exchange_rate = serializers.DecimalField(
        source="payment.exchange_rate", max_digits=18, decimal_places=6,
    )
    is_posted = serializers.BooleanField(source="payment.is_posted")
    journal = serializers.IntegerField(source="payment.journal_id", allow_null=True)
    notes = serializers.CharField(source="payment.notes", allow_blank=True)

    def get_allocated_amount(self, obj):
        return str(obj.amount_in_invoice_currency if obj.amount_in_invoice_currency is not None else obj.amount)


class SalesInvoiceListSerializer(
    _SalesInvoicePaymentSummarySerializer, serializers.ModelSerializer,
):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    delivery_status_display = serializers.CharField(
        source="get_delivery_status_display", read_only=True,
    )

    class Meta:
        model = SalesInvoice
        fields = [
            "id",
            "invoice_number",
            # T-RETURNUI: القائمة تميّز مرجع البيع عن الفاتورة (شارة/فلتر).
            "invoice_kind",
            "customer",
            "customer_name",
            "invoice_date",
            "due_date",
            "payment_terms_days",
            "is_overdue",
            "days_overdue",
            "invoice_type",
            "status",
            "grand_total",
            "amount_paid",
            "remaining_balance",
            "pending_payment_total",
            "payment_status",
            "payment_status_display",
            "customer_balance",
            "currency",
            "stock_on_post",
            "delivery_status",
            "delivery_status_display",
            "book_number",
        ]


class _AttachedChequeSerializer(serializers.Serializer):
    """Read-only nested view of an invoice's attached cheques (M2-T3)."""
    id = serializers.IntegerField()
    cheque_number = serializers.CharField()
    bank_name = serializers.CharField(allow_blank=True)
    account_number = serializers.CharField(allow_blank=True, allow_null=True)
    bank_branch = serializers.CharField(allow_blank=True, allow_null=True)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    due_date = serializers.DateField(allow_null=True)
    issue_date = serializers.DateField(allow_null=True)
    payee_name = serializers.CharField(allow_blank=True, allow_null=True)
    status = serializers.CharField()
    notes = serializers.CharField(allow_blank=True, allow_null=True)


class SalesInvoiceSerializer(
    _SalesInvoicePaymentSummarySerializer, serializers.ModelSerializer,
):
    lines = SalesInvoiceLineSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    invoice_number = serializers.CharField(required=False, allow_blank=True)
    # N8-T11: نوع الفاتورة (بيع/مرجع بيع…) + الفاتورة الأصلية للمرجع. مكشوفان
    # للكتابة كي تُنشئ شاشة «مرجع البيع» فاتورة من نوع sale_return مربوطة بأصلها.
    invoice_kind = serializers.ChoiceField(
        choices=SalesInvoice.INVOICE_KIND_CHOICES,
        default=SalesInvoice.INVOICE_KIND_SALE, required=False,
    )
    # P1-8: مقيّد بشركة الطلب — كان يقبل فاتورة أي شركة كأصلٍ للمرتجع.
    original_invoice = TenantScopedPrimaryKeyRelatedField(
        queryset=SalesInvoice.objects.all(), required=False, allow_null=True,
    )
    original_invoice_number = serializers.CharField(
        source="original_invoice.invoice_number", read_only=True, allow_null=True,
    )
    delivery_status_display = serializers.CharField(
        source="get_delivery_status_display", read_only=True,
    )
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Partner.objects.all(), required=False, allow_null=True
    )
    currency = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(), required=False, allow_null=True
    )
    # M2-T3: attached cheques (read-only). Posting/clearing handled via
    # the `payment-voucher` endpoint.
    cheques = _AttachedChequeSerializer(many=True, read_only=True)
    customer_balance_before_invoice = serializers.SerializerMethodField()
    customer_balance_after_invoice = serializers.SerializerMethodField()
    payment_details = _SalesInvoicePaymentDetailSerializer(
        source="payment_allocations", many=True, read_only=True,
    )
    # T-SLINEAGE: المستند الذي وُلدت منه الفاتورة (طلبية أو عرض سعر) — الرابطان
    # كانا في القاعدة (`SalesOrder.invoice` / `SalesQuotation.invoice`) ومقطوعين
    # عن الواجهة من جهة الفاتورة، فلا سبيل للرجوع منها إلى أصلها.
    source_document = serializers.SerializerMethodField()

    def get_source_document(self, obj):
        order = obj.order_backref.select_related("quotation").first()
        if order is not None:
            return {
                "kind": "order",
                "id": order.pk,
                "number": order.order_number,
                "origin_kind": "quotation" if order.quotation_id else None,
                "origin_id": order.quotation_id,
                "origin_number": (
                    order.quotation.quotation_number if order.quotation_id else None
                ),
            }
        quotation = obj.quotation_backref.first()
        if quotation is not None:
            return {
                "kind": "quotation",
                "id": quotation.pk,
                "number": quotation.quotation_number,
                "origin_kind": None,
                "origin_id": None,
                "origin_number": None,
            }
        return None

    # THA-132: «رقم الحركة» — يضعه الأصيل على وجه الفاتورة مدخلاً «للاستعلام عن
    # الحركات» (`docs/aseel_reference/invoices.txt`). استعلامٌ واحد مفهرس على
    # المستند المفتوح وحده (لا يمسّ سيريالايزر القائمة).
    stock_movement_no = serializers.SerializerMethodField()

    def get_stock_movement_no(self, obj):
        from inventory.models import StockMovement
        from .services import SALES_STOCK_REFERENCE_TYPES

        return (
            StockMovement.objects
            .filter(
                tenant_id=obj.tenant_id,
                reference_type__in=SALES_STOCK_REFERENCE_TYPES,
                reference_id=obj.id,
            )
            .order_by("id")
            .values_list("id", flat=True)
            .first()
        )

    def _balance_summary(self, obj):
        # THA-132 — **تقريبٌ لا يطابق كشف الحساب؛ لا تعرضه على أنه «قبل/بعد».**
        # `document_partner_balance_summary` يطرح «المتبقّي» من رصيد **اليوم**،
        # وكلا الأساسين خاطئ للفاتورة المرحّلة: قيدها يدين الذمم بكامل الإجمالي
        # (التحصيل قيدٌ منفصل) فالمدفوعةُ بالكامل تُظهر أثراً صفرياً وهي ليست
        # كذلك؛ ومرساتُه اليومُ لا موضعُ الفاتورة زمنياً. الجواب الصحيح في
        # `GET /api/sales/invoices/{id}/customer-ledger/` — من
        # `partner_account_statement` نفسه الذي يبني كشف الحساب.
        # الحقلان باقيان لعقد الـAPI وحده (مسار المسودّة إسقاطٌ مشروع).
        summary = self._payment_summary(obj)
        direction = -1 if obj.invoice_kind == SalesInvoice.INVOICE_KIND_SALE_RETURN else 1
        return document_partner_balance_summary(
            getattr(obj, "customer_balance", 0),
            summary["remaining_balance"],
            obj.exchange_rate,
            is_posted=obj.status == SalesInvoice.STATUS_POSTED,
            direction=direction,
        )

    def get_customer_balance_before_invoice(self, obj):
        return str(self._balance_summary(obj)["balance_before"])

    def get_customer_balance_after_invoice(self, obj):
        return str(self._balance_summary(obj)["balance_after"])

    class Meta:
        model = SalesInvoice
        fields = [
            "id",
            "invoice_number",
            "invoice_kind",
            "original_invoice",
            "original_invoice_number",
            "customer",
            "customer_name",
            "invoice_date",
            "due_date",
            "payment_terms_days",
            "is_overdue",
            "days_overdue",
            "invoice_type",
            "currency",
            "exchange_rate",
            "status",
            "subtotal_excl_tax",
            "invoice_discount",
            "tax_amount",
            "grand_total",
            "amount_paid",
            # ISSUE #121 (مواصفة #109 §٩): ختمُ تعديل المستند يُقارَن بختم
            # المسودّة المحلية — بدونه تُستعاد مسودّةٌ متأخّرةٌ فوق تعديلٍ
            # أحدثَ منها بصمت.
            "updated_at",
            "remaining_balance",
            "pending_payment_total",
            "payment_status",
            "payment_status_display",
            "customer_balance",
            "customer_balance_before_invoice",
            "customer_balance_after_invoice",
            "stock_movement_no",
            "payment_details",
            "revenue_account",
            "cash_or_bank_account",
            "accounts_receivable_account",
            "journal",
            "stock_on_post",
            "delivery_status",
            "delivery_status_display",
            "source_document",
            "notes",
            "lines",
            "created_at",
            # M2-T1: Aseel fields
            "book_number",
            "second_date",
            "licensed_dealer_no",
            "settlement_invoice_no",
            "prices_include_tax",
            "discount_percent",
            # M2-T3: Financial instrument
            "financial_document_no",
            # M2-T4: Source-discount overrides (null → use customer default)
            "source_discount_percent_override",
            "source_discount_amount_override",
            # M2-T3: Attached payment voucher (cash + cheques)
            "attached_cash_amount",
            "attached_cash_account",
            "cheques",
        ]
        read_only_fields = [
            "id",
            "status",
            "subtotal_excl_tax",
            "tax_amount",
            "grand_total",
            "amount_paid",
            "updated_at",
            "remaining_balance",
            "pending_payment_total",
            "payment_status",
            "payment_status_display",
            "customer_balance",
            "customer_balance_before_invoice",
            "customer_balance_after_invoice",
            "stock_movement_no",
            "payment_details",
            "created_at",
            "journal",
            "customer_name",
            "original_invoice_number",
            "delivery_status",  # مشتقّ من الكميات المسلَّمة — لا يُحرَّر يدوياً
            "delivery_status_display",
            "cheques",  # mutated only via /payment-voucher endpoint
            # T2: كانا يُقبلان كتابةً من الـAPI ولا يُرحَّلان شيئاً — مالٌ يدخل
            # الصندوق بلا أثر في الدفاتر. التحصيل صار من `/collect/` بسند قبض
            # حقيقي، والعمودان للقراءة القديمة فقط.
            "attached_cash_amount",
            "attached_cash_account",
        ]

    def validate(self, attrs):
        # T-DUE: الاستحقاق يُشتقّ من مهلة السداد حين لا يُكتب صراحةً — قاعدة
        # واحدة مع جانب الشراء (`core.payments.resolve_due_date`).
        invoice_date = attrs.get("invoice_date") or getattr(self.instance, "invoice_date", None)
        terms = attrs.get(
            "payment_terms_days", getattr(self.instance, "payment_terms_days", None))
        due = attrs.get("due_date", getattr(self.instance, "due_date", None))
        resolved = resolve_due_date(invoice_date, due, terms)
        if resolved != due:
            attrs["due_date"] = resolved
        # نمط «بدون» في إعدادات البيع: لا تُخزَّن أرقام تسلسلية على البنود إطلاقاً.
        from core.tenant_utils import get_tenant
        from inventory.serials import sales_serial_mode, strip_serials_when_off

        request = self.context.get("request")
        tenant = get_tenant(request) if request is not None else None
        if tenant is not None and attrs.get("lines"):
            strip_serials_when_off(
                attrs["lines"], sales_serial_mode(tenant.TenantID),
            )
        attrs = self._enforce_return_party(attrs)
        self._enforce_return_quantities(attrs)
        return attrs

    def _enforce_return_quantities(self, attrs):
        """T-RETQTY: مرجعٌ لا يتجاوز الكمية القابلة للإرجاع من فاتورته الأصلية.

        الحارس هنا لا في الشاشة: مرجعُ فاتورةٍ بها 10 كان يقبل 100 فيُدائن ذمم
        العميل بما لم يُبَع ويُدخل المخزنَ كميةً لم تخرج. القياس من
        `returnable_lines_for_invoice` نفسها التي تغذّي منتقي البنود — رقمٌ واحد
        يراه المستخدم ويحكم به الخادم. مرآة `create_purchase_return`.
        """
        from sales.services import guard_sales_return_quantities

        def _current(field, default=None):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field, default) if self.instance else default

        kind = _current("invoice_kind", SalesInvoice.INVOICE_KIND_SALE)
        if kind not in (
            SalesInvoice.INVOICE_KIND_SALE_RETURN,
            SalesInvoice.INVOICE_KIND_PURCHASE_RETURN,
        ):
            return
        original = _current("original_invoice")
        if original is None:
            return
        lines = attrs.get("lines")
        if lines is None:
            return  # تعديلٌ لا يمسّ البنود — الكميات المحفوظة سبق أن مرّت بالحارس
        try:
            guard_sales_return_quantities(
                original, lines,
                exclude_invoice_id=self.instance.pk if self.instance else None,
            )
        except DjangoValidationError as exc:
            message = exc.message if hasattr(exc, "message") else "؛ ".join(exc.messages)
            raise serializers.ValidationError({"lines": message})

    def _enforce_return_party(self, attrs):
        """مرجعٌ مربوطٌ بأصلٍ يُقيَّد على مشتري الأصل — لا على طرفٍ آخر.

        شاشة «مرجع البيع» تُعبّئ العميل من الفاتورة الأصلية ثم تتركه قابلاً
        للتغيير، ولم يكن في الخادم ما يمنع الفارق: مرجع فاتورة زيدٍ يُقيَّد على
        ذمم عمرو فيَنقص دينُ من لم يُرجِع شيئاً. الحارس هنا لا في الشاشة، فكل
        مسارٍ يكتب عبر الـAPI محكومٌ به. والعميل **مشتقٌّ** حين يُغفَل: يأخذه من
        الأصل لا من «العميل الافتراضي» في الإعدادات.
        """
        def _current(field, default=None):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field, default) if self.instance else default

        kind = _current("invoice_kind", SalesInvoice.INVOICE_KIND_SALE)
        if kind not in (
            SalesInvoice.INVOICE_KIND_SALE_RETURN,
            SalesInvoice.INVOICE_KIND_PURCHASE_RETURN,
        ):
            return attrs
        original = _current("original_invoice")
        if original is None or original.customer_id is None:
            return attrs
        customer = _current("customer")
        if customer is None:
            attrs["customer"] = original.customer
            return attrs
        if customer.pk != original.customer_id:
            raise serializers.ValidationError({
                "customer": (
                    f"مرتجع الفاتورة «{original.invoice_number}» يُقيَّد على "
                    f"مشتريها «{original.customer.name}» — لا على طرفٍ آخر."
                )
            })
        return attrs

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
            book_num = validated_data.get("book_number", 0)
            validated_data["invoice_number"] = next_invoice_number(
                tenant.TenantID, book_num, branch=validated_data.get("branch"))
        if not lines_data:
            raise serializers.ValidationError({"lines": "يجب إضافة بند واحد على الأقل."})
        for row in lines_data:
            prod = _as_product(row.get("product"))
            if prod is None:
                raise serializers.ValidationError(
                    {"lines": f"منتج غير موجود: {row.get('product')}"}
                )
            if prod.tenant_id != tenant.TenantID:
                raise serializers.ValidationError(
                    {"lines": f"المنتج {prod.sku} لا يتبع نفس الشركة."}
                )
        _is_return = validated_data.get("invoice_kind") in (
            SalesInvoice.INVOICE_KIND_SALE_RETURN,
            SalesInvoice.INVOICE_KIND_PURCHASE_RETURN,
        )
        _validate_stock_lines(
            tenant, lines_data, validated_data.get("stock_on_post", True),
            is_return=_is_return,
        )
        from django.db import IntegrityError

        def _create_with_lines():
            """الإنشاء الكامل ذرّياً — يُستعمل من المحاولة الأولى ومن حلقة التصادم."""
            with transaction.atomic():
                inv = SalesInvoice.objects.create(**validated_data)
                for row in lines_data:
                    rw = dict(row)
                    rw.pop("id", None)
                    SalesInvoiceLine.objects.create(tenant=tenant, invoice=inv, **rw)
                lines = list(inv.lines.select_related(
                    "tax_rate", "tax_rate__tax_account", "product"))
                recalculate_invoice_amounts(inv, lines)
                SalesInvoiceLine.objects.bulk_update(
                    lines,
                    ["line_total_excl_tax", "line_tax_amount"],
                )
                _run_loss_guard(inv, lines)
                inv.save(
                    update_fields=[
                        "subtotal_excl_tax",
                        "tax_amount",
                        "grand_total",
                    ]
                )
            return inv

        try:
            return _create_with_lines()
        except IntegrityError:
            # T-NUMGAP: رقمٌ أرسله العميل صراحةً — التصادم قراره لا قرارنا.
            if inv_num and str(inv_num).strip():
                raise
            # عدّاد الدفتر قد يتخلّف عن الواقع بأكثر من رقم (فواتير أُدخلت
            # بأرقامٍ يدوية، أو استيراد قديم) — إعادة محاولةٍ **واحدة** كانت
            # تسقط على الرقم المحجوز التالي فيخرج 500 «Duplicate entry» على
            # المستخدم. الحلقة تتقدّم بالعدّاد حتى أوّل رقمٍ حرّ — كلُّ نداءٍ
            # لـ`next_invoice_number` يزيد العدّاد فيتجاوز الفجوة ولا يعود
            # إليها، والسقف يمنع الدوران إلى الأبد على قيدٍ آخر غير الرقم.
            book_num = validated_data.get("book_number", 0)
            last_err: IntegrityError | None = None
            for _ in range(50):
                validated_data["invoice_number"] = next_invoice_number(
                    tenant.TenantID, book_num, branch=validated_data.get("branch"))
                try:
                    return _create_with_lines()
                except IntegrityError as e:
                    last_err = e
                    continue
            raise last_err

    def update(self, instance, validated_data):
        if instance.status != SalesInvoice.STATUS_DRAFT:
            raise serializers.ValidationError("لا يمكن تعديل فاتورة مرحّلة أو ملغاة.")
        lines_data = validated_data.pop("lines", None)
        # W1: التعديل ذرّي — حارس الخسارة على مستوى السطر يرفع ValidationError داخل
        # المعاملة فيتراجع كل الحفظ (لا تُحفظ مسودة بخسارة).
        with transaction.atomic():
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
                            {"lines": f"منتج غير موجود: {raw.get('product')}"}
                        )
                    if prod.tenant_id != tenant.TenantID:
                        raise serializers.ValidationError(
                            {"lines": f"المنتج {prod.sku} لا يتبع نفس الشركة."}
                        )
                stock_flag = validated_data.get("stock_on_post", instance.stock_on_post)
                _upd_is_return = instance.invoice_kind in (
                    SalesInvoice.INVOICE_KIND_SALE_RETURN,
                    SalesInvoice.INVOICE_KIND_PURCHASE_RETURN,
                )
                _validate_stock_lines(tenant, lines_data, stock_flag, is_return=_upd_is_return)
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
            lines = list(instance.lines.select_related("tax_rate", "tax_rate__tax_account", "product"))
            recalculate_invoice_amounts(instance, lines)
            SalesInvoiceLine.objects.bulk_update(
                lines,
                ["line_total_excl_tax", "line_tax_amount"],
            )
            _run_loss_guard(instance, lines)
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


# T-CHQ3/ط: رسالة واحدة لشرط تاريخ الاستحقاق — يستهلكها سند القبض وسند الصرف
# ومسار إرفاق الشيكات بالفاتورة، فلا تتفرّع صياغتها بين الشاشات.
CHEQUE_DUE_DATE_REQUIRED = (
    "تاريخ استحقاق الشيك مطلوب — عليه تقوم المحفظة والتحصيل عند الموعد."
)


class _PaymentChequeInputSerializer(serializers.Serializer):
    """شيك داخل سند القبض — مبلغه جزء من مبلغ السند لا إضافة عليه."""
    cheque_number = serializers.CharField(max_length=50)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    bank_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    account_number = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    bank_branch = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    # T-CHQ3/ط: دورة الشيك كلها مبنية على موعده (المحفظة · الآجال · «تم
    # التحصيل» عند الاستحقاق)، فشيك بلا موعد ورقة لا تُدار.
    due_date = serializers.DateField(
        error_messages={
            "null": CHEQUE_DUE_DATE_REQUIRED,
            "required": CHEQUE_DUE_DATE_REQUIRED,
            "invalid": CHEQUE_DUE_DATE_REQUIRED,
        },
    )
    issue_date = serializers.DateField(required=False, allow_null=True)
    payee_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class CustomerPaymentSerializer(serializers.ModelSerializer):
    allocations = PaymentAllocationSerializer(many=True, required=False)
    # الشيكات تُكتب مع إنشاء السند وتُقرأ من الشيكات المرتبطة به.
    cheques = _PaymentChequeInputSerializer(many=True, required=False, write_only=True)
    attached_cheques = _AttachedChequeSerializer(
        many=True, read_only=True, source="cheques",
    )
    partner_name = serializers.CharField(source="partner.name", read_only=True)
    allocated_amount = serializers.SerializerMethodField()
    unallocated_amount = serializers.SerializerMethodField()

    # T-DEFACC: الصندوق يُملأ من افتراضي الشركة حين لا يُرسَل — سند القبض
    # كان يُرفَض بـ«هذا الحقل مطلوب» في كل شاشة تنسى تمرير الحساب.
    # P1-8: مقيّد بشركة الطلب — كان يقبل حساب صندوق/بنك من أي شركة.
    cash_or_bank_account = TenantScopedPrimaryKeyRelatedField(
        queryset=Account.objects.all(), required=False, allow_null=True,
    )

    def validate(self, attrs):
        # T-ONACC: التوزيع اختياري وجزئي مسموح — الباقي يُسجَّل على حساب العميل.
        # الممنوع فقط أن يتجاوز مجموع التوزيعات مبلغ السند.
        if self.instance is None and self.initial_data.get("allocations") is not None:
            data = self.initial_data.get("allocations") or []
            total = sum(Decimal(str(x.get("amount", 0))) for x in data)
            if total > attrs["amount"]:
                raise serializers.ValidationError(
                    {"allocations": "مجموع التوزيعات لا يجوز أن يتجاوز مبلغ الدفعة."}
                )
        cheques_total = sum(
            (Decimal(str(c["amount"])) for c in attrs.get("cheques", [])),
            Decimal("0"),
        )
        if cheques_total > attrs.get("amount", Decimal("0")):
            raise serializers.ValidationError(
                {"cheques": "مجموع الشيكات لا يجوز أن يتجاوز مبلغ السند."}
            )
        return apply_default_cash_account(self, attrs)

    def _allocated(self, obj) -> Decimal:
        # allocations مُحمَّلة مسبقاً (prefetch_related) — لا استعلام لكل صف.
        return sum(
            (Decimal(str(a.amount)) for a in obj.allocations.all()), Decimal("0")
        )

    def get_allocated_amount(self, obj) -> str:
        return str(self._allocated(obj))

    def get_unallocated_amount(self, obj) -> str:
        return str(Decimal(str(obj.amount)) - self._allocated(obj))

    class Meta:
        model = CustomerPayment
        fields = [
            "id",
            "partner",
            "partner_name",
            "payment_date",
            "amount",
            "currency",
            "exchange_rate",
            "cash_or_bank_account",
            "journal",
            "is_posted",
            "notes",
            "allocations",
            "cheques",
            "attached_cheques",
            "allocated_amount",
            "unallocated_amount",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "journal",
            "is_posted",
            "created_at",
            "partner_name",
            "attached_cheques",
            "allocated_amount",
            "unallocated_amount",
        ]

    def create(self, validated_data):
        allocs = validated_data.pop("allocations", [])
        cheques = validated_data.pop("cheques", [])
        pay = CustomerPayment.objects.create(**validated_data)
        for a in allocs:
            PaymentAllocation.objects.create(tenant=pay.tenant, payment=pay, **a)
        for c in cheques:
            Cheque.objects.create(
                tenant=pay.tenant,
                customer_payment=pay,
                partner=pay.partner,
                direction="Incoming",
                status="Draft",  # يصير «برسم التحصيل» عند ترحيل السند
                cheque_number=c["cheque_number"].strip(),
                amount=c["amount"],
                currency=pay.currency,
                bank_name=c.get("bank_name") or "",
                account_number=c.get("account_number") or "",
                bank_branch=c.get("bank_branch") or "",
                due_date=c.get("due_date") or None,
                issue_date=c.get("issue_date") or None,
                payee_name=c.get("payee_name") or "",
                notes=c.get("notes") or "",
            )
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
            "allow_negative_stock_default",
            "default_vat_rate",
            "default_vat_rate_code",
            "default_vat_rate_value",
            "vat_input_account",
            "vat_input_account_name",
            "prices_include_tax",
            "auto_post_invoices",
            "auto_post_payments",
            "show_journal_preview",
            "warn_on_duplicate_item",
            "block_loss_invoices",
            "serial_entry_mode",
            "dormant_customer_days",
            # T-ORDERS: صلاحية العرض، مدة حجز الطلبية، وإظهار زر الحذف.
            "quotation_valid_days",
            "order_reserve_days",
            "allow_document_delete",
            # T-RESERVEGUARD: منع بيع الكمية المحجوزة لطلبية زبون آخر.
            "block_reserved_stock_sale",
            "default_shipping_origin",
            "default_shipping_destination",
            # مستند التسليم: تسميته، وسند التسليم المستقل، وصلاحية التعديل.
            "delivery_doc_label",
            "standalone_delivery_label",
            "allow_standalone_delivery",
            "allow_edit_delivery",
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


class DeliveryOrderLineSerializer(serializers.ModelSerializer):
    """بند إرسالية بيع — المفوتر والمسلَّم تراكمياً والباقي، لسياق المراجعة."""

    product_name = serializers.SerializerMethodField(read_only=True)
    ordered_quantity = serializers.SerializerMethodField()
    delivered_total = serializers.SerializerMethodField()
    remaining_quantity = serializers.SerializerMethodField()
    warehouse_name = serializers.CharField(
        source="warehouse.name", read_only=True, default=None,
    )

    class Meta:
        model = DeliveryOrderLine
        fields = [
            "id", "invoice_line", "product", "product_name",
            "ordered_quantity", "delivered_total", "remaining_quantity", "quantity",
            "warehouse", "warehouse_name",
        ]
        read_only_fields = fields

    def get_product_name(self, obj):
        if not obj.product_id:
            return None
        from inventory.services import product_display_name
        return product_display_name(obj.product)

    def get_ordered_quantity(self, obj):
        # السند المستقل بلا سطر فاتورة ⇒ المفوتر = المسلَّم نفسه (لا باقي).
        return str(obj.invoice_line.quantity if obj.invoice_line_id else obj.quantity)

    def get_delivered_total(self, obj):
        return str(
            obj.invoice_line.delivered_quantity if obj.invoice_line_id else obj.quantity
        )

    def get_remaining_quantity(self, obj):
        if not obj.invoice_line_id:
            return "0"
        ordered = Decimal(str(obj.invoice_line.quantity or 0))
        delivered = Decimal(str(obj.invoice_line.delivered_quantity or 0))
        return str(max(Decimal("0"), ordered - delivered))


class DeliveryOrderListSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(
        source="invoice.invoice_number", read_only=True, default=None,
    )
    customer = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_standalone = serializers.BooleanField(read_only=True)
    doc_label = serializers.SerializerMethodField()
    lines_count = serializers.SerializerMethodField()
    total_quantity = serializers.SerializerMethodField()
    total_remaining = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryOrder
        fields = [
            "id", "delivery_number", "delivery_date", "invoice", "invoice_number",
            "customer", "customer_name", "customer_ref", "is_standalone", "doc_label",
            "status", "status_display", "auto_created", "notes",
            "lines_count", "total_quantity", "total_remaining",
            "delivered_at", "created_at",
        ]
        read_only_fields = fields

    def _labels(self, obj):
        cached = getattr(self, "_label_cache", None)
        if cached is None:
            from .services import get_or_create_sales_settings
            ss = get_or_create_sales_settings(obj.tenant_id)
            cached = (ss.delivery_doc_label, ss.standalone_delivery_label)
            self._label_cache = cached
        return cached

    def get_doc_label(self, obj):
        linked, standalone = self._labels(obj)
        return standalone if obj.invoice_id is None else linked

    def get_customer(self, obj):
        return obj.partner_id or (obj.invoice.customer_id if obj.invoice_id else None)

    def get_customer_name(self, obj):
        if obj.partner_id:
            return obj.partner.name
        return obj.invoice.customer.name if obj.invoice_id else ""

    def get_lines_count(self, obj):
        return obj.lines.count()

    def get_total_quantity(self, obj):
        return str(sum((line.quantity for line in obj.lines.all()), Decimal("0")))

    def get_total_remaining(self, obj):
        """الباقي على الفاتورة المرتبطة بعد هذه الإرسالية (0 للسند المستقل)."""
        if obj.invoice_id is None:
            return "0"
        total = Decimal("0")
        for line in obj.invoice.lines.all():
            ordered = Decimal(str(line.quantity or 0))
            delivered = Decimal(str(line.delivered_quantity or 0))
            total += max(Decimal("0"), ordered - delivered)
        return str(total)


class DeliveryOrderSerializer(DeliveryOrderListSerializer):
    lines = DeliveryOrderLineSerializer(many=True, read_only=True)

    class Meta(DeliveryOrderListSerializer.Meta):
        fields = DeliveryOrderListSerializer.Meta.fields + ["tenant", "lines"]
        read_only_fields = fields


class SalesQuotationLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    # اسم المنتج (قراءة فقط) لعرض بنود عرض السعر بوضوح — يتبع product_display_name.
    product_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = SalesQuotationLine
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "unit_price",
            "line_discount",
            "tax_rate",
            "line_total",
        ]
        read_only_fields = ["line_total"]

    def get_product_name(self, obj):
        if not obj.product_id:
            return None
        from inventory.services import product_display_name
        return product_display_name(obj.product)


class SalesOrderLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    product_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = SalesOrderLine
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "unit_price",
            "line_discount",
            "tax_rate",
            "line_total",
        ]
        read_only_fields = ["line_total"]

    def get_product_name(self, obj):
        if not obj.product_id:
            return None
        from inventory.services import product_display_name
        return product_display_name(obj.product)


class SalesOrderSerializer(serializers.ModelSerializer):
    """طلبية زبون — نفس عقد عرض السعر مع الحجز والعربون (T-ORDERS)."""

    lines = SalesOrderLineSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    invoice_number = serializers.CharField(
        source="invoice.invoice_number", read_only=True, allow_null=True,
    )
    quotation_number = serializers.CharField(
        source="quotation.quotation_number", read_only=True, allow_null=True,
    )
    remaining_amount = serializers.SerializerMethodField()
    customer = serializers.PrimaryKeyRelatedField(queryset=Partner.objects.all())
    order_number = serializers.CharField(required=False, allow_blank=True)
    currency = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = SalesOrder
        fields = [
            # ISSUE #121 (مواصفة #109 §٩): ختمُ تعديل المستند يُقارَن بختم
            # المسودّة المحلية — بدونه تُستعاد مسودّةٌ متأخّرةٌ فوق تعديلٍ
            # أحدثَ منها بصمت.
            "updated_at",
            "id",
            "order_number",
            "customer",
            "customer_name",
            "order_date",
            "delivery_date",
            "reserved_until",
            "status",
            "status_display",
            "currency",
            "exchange_rate",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "grand_total",
            "deposit_amount",
            "remaining_amount",
            "quotation",
            "quotation_number",
            "invoice",
            "invoice_number",
            "notes",
            "cancel_reason",
            "lines",
            "created_at",
            "created_by",
        ]
        read_only_fields = [
            "updated_at",
            "id",
            "status",
            "status_display",
            "subtotal",
            "tax_amount",
            "grand_total",
            "deposit_amount",
            "remaining_amount",
            "reserved_until",
            "quotation_number",
            "invoice",
            "invoice_number",
            "cancel_reason",
            "created_at",
            "created_by",
        ]

    def get_remaining_amount(self, obj) -> str:
        return str(
            (Decimal(str(obj.grand_total or 0)) - Decimal(str(obj.deposit_amount or 0)))
            .quantize(Decimal("0.01"))
        )

    def validate(self, attrs):
        from core.tenant_utils import get_tenant

        request = self.context.get("request")
        # الاستخدام البرمجي (خدمات/اختبارات) بلا request يمرّر الشركة عبر
        # context={"tenant": ...} — المسار الإنتاجي (viewset يمرّر request)
        # لم يتغيّر. نفس بديل SalesQuotationSerializer أدناه، للاتساق.
        tenant = (
            get_tenant(request) if request is not None
            else attrs.get("tenant") or self.context.get("tenant")
        )
        if tenant is None:
            raise serializers.ValidationError({"tenant": "لا توجد شركة محددة."})

        customer = attrs.get("customer") or getattr(self.instance, "customer", None)
        if customer and customer.tenant_id != tenant.TenantID:
            raise serializers.ValidationError(
                {"customer": "الزبون المختار لا يتبع الشركة الحالية."}
            )
        if customer and customer.partner_type != "Customer":
            raise serializers.ValidationError({"customer": "يجب اختيار زبون."})

        lines = attrs.get("lines")
        if self.instance is None and not lines:
            raise serializers.ValidationError({"lines": "أضف بنداً واحداً على الأقل."})
        if lines is not None:
            if self.instance is not None and self.instance.status != SalesOrder.STATUS_DRAFT:
                raise serializers.ValidationError(
                    {"lines": "لا يمكن تعديل بنود الطلبية بعد تأكيدها؛ ألغِها وأنشئ طلبية جديدة."}
                )
            if not lines:
                raise serializers.ValidationError({"lines": "أضف بنداً واحداً على الأقل."})
            for index, line in enumerate(lines, start=1):
                product = line.get("product")
                if product and product.tenant_id != tenant.TenantID:
                    raise serializers.ValidationError({
                        "lines": f"المنتج في السطر {index} لا يتبع الشركة الحالية."
                    })
                quantity = Decimal(str(line.get("quantity", 0) or 0))
                unit_price = Decimal(str(line.get("unit_price", 0) or 0))
                discount = Decimal(str(line.get("line_discount", 0) or 0))
                if quantity <= 0:
                    raise serializers.ValidationError({
                        "lines": f"كمية السطر {index} يجب أن تكون أكبر من صفر."
                    })
                if unit_price < 0:
                    raise serializers.ValidationError({
                        "lines": f"سعر السطر {index} لا يمكن أن يكون سالباً."
                    })
                if discount < 0 or discount > quantity * unit_price:
                    raise serializers.ValidationError({
                        "lines": f"خصم السطر {index} غير صالح."
                    })
        return attrs

    @staticmethod
    def _prepare_lines(lines_data):
        subtotal = Decimal("0")
        tax_amount = Decimal("0")
        for line in lines_data:
            quantity = Decimal(str(line.get("quantity", 0)))
            unit_price = Decimal(str(line.get("unit_price", 0)))
            discount = Decimal(str(line.get("line_discount", 0)))
            line["line_total"] = (quantity * unit_price - discount).quantize(Decimal("0.01"))
            subtotal += line["line_total"]
            tax_rate = line.get("tax_rate")
            if tax_rate:
                tax_amount += (
                    line["line_total"] * Decimal(str(tax_rate.rate)) / Decimal("100")
                ).quantize(Decimal("0.01"))
        return subtotal.quantize(Decimal("0.01")), tax_amount.quantize(Decimal("0.01"))

    @staticmethod
    def _apply_totals(validated_data, subtotal, tax_amount):
        validated_data["subtotal"] = subtotal
        validated_data["tax_amount"] = tax_amount
        validated_data["grand_total"] = (
            subtotal
            - Decimal(str(validated_data.get("discount_amount", 0) or 0))
            + tax_amount
        ).quantize(Decimal("0.01"))

    def create(self, validated_data):
        from .services import next_order_number

        lines_data = validated_data.pop("lines")
        tenant = validated_data["tenant"]
        if not validated_data.get("order_number"):
            validated_data["order_number"] = next_order_number(tenant.TenantID)
        if not validated_data.get("currency"):
            base = Currency.objects.filter(IsBaseCurrency=True).first()
            if not base:
                raise serializers.ValidationError(
                    {"currency": "لا توجد عملة أساسية معرّفة. عيّن عملة أساسية أو اختر عملة."}
                )
            validated_data["currency"] = base
        self._apply_totals(validated_data, *self._prepare_lines(lines_data))
        with transaction.atomic():
            order = SalesOrder.objects.create(**validated_data)
            SalesOrderLine.objects.bulk_create([
                SalesOrderLine(order=order, tenant=tenant, **line)
                for line in lines_data
            ])
        return order

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lines", None)
        tenant = instance.tenant
        with transaction.atomic():
            locked = SalesOrder.objects.select_for_update().get(pk=instance.pk)
            if lines_data is not None:
                if locked.status != SalesOrder.STATUS_DRAFT:
                    raise serializers.ValidationError({
                        "lines": "لا يمكن تعديل بنود الطلبية بعد تأكيدها."
                    })
                subtotal, tax_amount = self._prepare_lines(lines_data)
                effective = {
                    "discount_amount": validated_data.get(
                        "discount_amount", locked.discount_amount),
                }
                self._apply_totals(effective, subtotal, tax_amount)
                if effective["grand_total"] < locked.deposit_amount:
                    raise serializers.ValidationError({
                        "lines": "لا يمكن خفض إجمالي الطلبية عن العربون المقبوض."
                    })
                validated_data.update(effective)
            for field, value in validated_data.items():
                setattr(locked, field, value)
            locked.save()
            if lines_data is not None:
                locked.lines.all().delete()
                SalesOrderLine.objects.bulk_create([
                    SalesOrderLine(order=locked, tenant=tenant, **line)
                    for line in lines_data
                ])
            instance = locked
        return instance


class SalesQuotationSerializer(serializers.ModelSerializer):
    lines = SalesQuotationLineSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    invoice_number = serializers.CharField(
        source="invoice.invoice_number", read_only=True, allow_null=True,
    )
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Partner.objects.all(),
    )
    # رقم العرض يُولَّد خادمياً، والعملة تُفترَض الأساسية — فالواجهة لا تُدخلهما.
    quotation_number = serializers.CharField(required=False, allow_blank=True)
    currency = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = SalesQuotation
        fields = [
            # ISSUE #121 (مواصفة #109 §٩): ختمُ تعديل المستند يُقارَن بختم
            # المسودّة المحلية — بدونه تُستعاد مسودّةٌ متأخّرةٌ فوق تعديلٍ
            # أحدثَ منها بصمت.
            "updated_at",
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
            "updated_at",
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

    def validate(self, attrs):
        from core.tenant_utils import get_tenant

        request = self.context.get("request")
        # الاستخدام البرمجي (خدمات/اختبارات) بلا request يمرّر الشركة عبر
        # context={"tenant": ...} — المسار الإنتاجي (viewset يمرّر request)
        # لم يتغيّر. أُضيف لأن validate هذا (227c51a) كسر نمط
        # ser.save(tenant=...) الذي تعتمده اختبارات العروض الثلاثة.
        tenant = (
            get_tenant(request) if request is not None
            else attrs.get("tenant") or self.context.get("tenant")
        )
        if tenant is None:
            raise serializers.ValidationError({"tenant": "لا توجد شركة محددة."})
        customer = attrs.get("customer") or getattr(self.instance, "customer", None)
        if customer and (
            customer.tenant_id != tenant.TenantID or customer.partner_type != "Customer"
        ):
            raise serializers.ValidationError(
                {"customer": "يجب اختيار زبون من الشركة الحالية."}
            )
        # خصم المستند سالباً = زيادةٌ متنكّرة في هيئة خصم — تُرفض عند الباب.
        if Decimal(str(attrs.get("discount_amount", 0) or 0)) < 0:
            raise serializers.ValidationError(
                {"discount_amount": "خصم العرض لا يمكن أن يكون سالباً."}
            )
        lines = attrs.get("lines")
        if self.instance is None and not lines:
            raise serializers.ValidationError({"lines": "أضف بنداً واحداً على الأقل."})
        if lines is not None:
            if self.instance is not None and self.instance.status in {
                SalesQuotation.STATUS_CONVERTED,
                SalesQuotation.STATUS_CANCELLED,
                SalesQuotation.STATUS_REJECTED,
                SalesQuotation.STATUS_EXPIRED,
            }:
                raise serializers.ValidationError(
                    {"lines": "لا يمكن تعديل بنود عرض منتهٍ أو ملغى أو محوّل."}
                )
            if not lines:
                raise serializers.ValidationError({"lines": "أضف بنداً واحداً على الأقل."})
            for index, line in enumerate(lines, start=1):
                product = line.get("product")
                if product and product.tenant_id != tenant.TenantID:
                    raise serializers.ValidationError({
                        "lines": f"المنتج في السطر {index} لا يتبع الشركة الحالية."
                    })
                tax_rate = line.get("tax_rate")
                if tax_rate and tax_rate.tenant_id != tenant.TenantID:
                    raise serializers.ValidationError({
                        "lines": f"الضريبة في السطر {index} لا تتبع الشركة الحالية."
                    })
                quantity = Decimal(str(line.get("quantity", 0) or 0))
                unit_price = Decimal(str(line.get("unit_price", 0) or 0))
                discount = Decimal(str(line.get("line_discount", 0) or 0))
                if quantity <= 0 or unit_price < 0:
                    raise serializers.ValidationError({
                        "lines": f"كمية أو سعر السطر {index} غير صالح."
                    })
                if discount < 0 or discount > quantity * unit_price:
                    raise serializers.ValidationError({
                        "lines": f"خصم السطر {index} غير صالح."
                    })
        return attrs

    @staticmethod
    def _prepare_lines(lines_data):
        """يكتب `line_total` لكل سطر ويعيد [(الصافي، نسبة الضريبة)].

        الصافي هنا **قبل** خصم المستند — كما يُخزَّن على السطر تماماً، فالسطر
        المطبوع يبقى `كمية × سعر − خصم السطر` والخصم العام يُعلَن على الرأس.
        """
        pairs = []
        for line in lines_data:
            quantity = Decimal(str(line.get("quantity", 0)))
            unit_price = Decimal(str(line.get("unit_price", 0)))
            discount = Decimal(str(line.get("line_discount", 0)))
            line_total = (quantity * unit_price - discount).quantize(Decimal("0.01"))
            line["line_total"] = line_total
            tax_rate = line.get("tax_rate")
            pairs.append((
                line_total,
                Decimal(str(tax_rate.rate)) if tax_rate else Decimal("0"),
            ))
        return pairs

    @staticmethod
    def _apply_totals(validated_data, pairs):
        """خصم المستند يسبق الضريبة — نفس قاعدة `recalculate_invoice_amounts`.

        كان الخصم يُطرح **بعد** الضريبة (`subtotal + tax − discount`) فتُحسب
        ض.ق.م على أساسٍ لم يُدفع، ويختلف إجمالي العرض عن إجمالي فاتورته بعد
        التحويل. الآن: الخصم يُوزَّع على الأسطر بـ`allocate_invoice_discount`
        (القاعدة المشتركة نفسها التي يقسّم بها الإيراد)، ثم تُحسب الضريبة على
        الصافي المخصوم، والإجمالي = مجموع الأسطر المخصومة + الضريبة بالقرش.
        يحرس التطابقَ `test_quotation_discount.py::test_quotation_totals_match_invoice_math`.
        """
        cent = Decimal("0.01")
        subtotal = sum((net for net, _rate in pairs), Decimal("0")).quantize(cent)
        discount = Decimal(str(validated_data.get("discount_amount", 0) or 0))
        # خصمٌ يتجاوز مجموع البنود لا يصنع إجمالياً سالباً (كما في الفاتورة).
        if subtotal > 0 and discount > subtotal:
            discount = subtotal
        after_discount = Decimal("0.00")
        tax_amount = Decimal("0.00")
        for net, rate in pairs:
            adjusted = allocate_invoice_discount(net, discount, subtotal).quantize(cent)
            after_discount += adjusted
            if rate:
                tax_amount += (adjusted * rate / Decimal("100")).quantize(cent)
        validated_data["subtotal"] = subtotal
        validated_data["tax_amount"] = tax_amount.quantize(cent)
        validated_data["grand_total"] = (after_discount + tax_amount).quantize(cent)

    @staticmethod
    def _sync_customer_prices(quotation, lines_data):
        from .models import CustomerProductQuote

        for line in lines_data:
            product = line.get("product")
            unit_price = Decimal(str(line.get("unit_price", 0) or 0))
            if product and unit_price > 0:
                CustomerProductQuote.objects.get_or_create(
                    tenant=quotation.tenant,
                    customer=quotation.customer,
                    product=product,
                    defaults={"unit_price": unit_price},
                )

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")
        tenant = validated_data["tenant"]
        # رقم العرض يُولَّد خادمياً إن لم تُرسله الواجهة (تسلسل مستقل للعروض).
        if not validated_data.get("quotation_number"):
            from .services import next_quotation_number
            validated_data["quotation_number"] = next_quotation_number(tenant.TenantID)
        # العملة تُفترَض الأساسية عند غيابها (لا منتقي عملة في شاشة العروض).
        if not validated_data.get("currency"):
            base = Currency.objects.filter(IsBaseCurrency=True).first()
            if not base:
                raise serializers.ValidationError(
                    {"currency": "لا توجد عملة أساسية معرّفة. عيّن عملة أساسية أو اختر عملة."}
                )
            validated_data["currency"] = base
        self._apply_totals(validated_data, self._prepare_lines(lines_data))
        with transaction.atomic():
            quotation = SalesQuotation.objects.create(**validated_data)
            SalesQuotationLine.objects.bulk_create([
                SalesQuotationLine(quotation=quotation, tenant=tenant, **line)
                for line in lines_data
            ])
            self._sync_customer_prices(quotation, lines_data)
        return quotation

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lines", None)
        with transaction.atomic():
            locked = SalesQuotation.objects.select_for_update().get(pk=instance.pk)
            # تعديل الخصم وحده (بلا بنود) يعيد الحساب من بنود العرض المحفوظة —
            # وإلا بقيت الإجماليات على خصمها القديم بصمت.
            recompute = lines_data is not None or "discount_amount" in validated_data
            if recompute:
                pairs = (
                    self._prepare_lines(lines_data) if lines_data is not None
                    else [
                        (line.line_total,
                         Decimal(str(line.tax_rate.rate)) if line.tax_rate_id else Decimal("0"))
                        for line in locked.lines.select_related("tax_rate")
                    ]
                )
                effective = {
                    "discount_amount": validated_data.get(
                        "discount_amount", locked.discount_amount)
                }
                self._apply_totals(effective, pairs)
                validated_data.update(effective)
            for field, value in validated_data.items():
                setattr(locked, field, value)
            locked.save()
            if lines_data is not None:
                locked.lines.all().delete()
                SalesQuotationLine.objects.bulk_create([
                    SalesQuotationLine(
                        quotation=locked, tenant=locked.tenant, **line)
                    for line in lines_data
                ])
                self._sync_customer_prices(locked, lines_data)
        return locked


class SalesQuotationListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    # حالة العرض بالعربية كما في الطلبية — كرت الزبون كان يعرض المفتاح الخام.
    status_display = serializers.CharField(
        source="get_status_display", read_only=True,
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
            "status_display",
            "grand_total",
            "currency",
            "created_at",
        ]


# ─────────────────────────────────────────────────────────────────────────
# M4-T4 — Credit/Debit notes
# ─────────────────────────────────────────────────────────────────────────

class CreditDebitNoteSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    related_invoice_number = serializers.CharField(
        source="related_invoice.invoice_number", read_only=True, allow_null=True,
    )
    note_number = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = CreditDebitNote
        fields = [
            "id",
            "note_number",
            "note_date",
            "note_type",
            "customer",
            "customer_name",
            "related_invoice",
            "related_invoice_number",
            "amount",
            "reason",
            "status",
            "journal",
            "created_at",
        ]
        read_only_fields = ["id", "status", "journal", "created_at", "customer_name", "related_invoice_number"]

    def validate(self, attrs):
        amt = attrs.get("amount")
        if amt is None or Decimal(str(amt)) <= 0:
            raise serializers.ValidationError({"amount": "المبلغ يجب أن يكون أكبر من صفر."})
        nt = attrs.get("note_type")
        if nt not in (CreditDebitNote.TYPE_CREDIT, CreditDebitNote.TYPE_DEBIT):
            raise serializers.ValidationError({"note_type": "نوع غير صالح."})
        return attrs

    def create(self, validated_data):
        # Auto-generate the note number atomically using the per-tenant
        # `select_for_update` helper — same race-safety pattern as invoices.
        if not validated_data.get("note_number"):
            tenant = validated_data.get("tenant")
            tenant_id = getattr(tenant, "TenantID", None) or getattr(tenant, "pk", None)
            if tenant_id is None:
                raise serializers.ValidationError({"tenant": "Tenant is required."})
            validated_data["note_number"] = next_credit_debit_note_number(
                tenant_id, validated_data["note_type"]
            )
        return super().create(validated_data)
