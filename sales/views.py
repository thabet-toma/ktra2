from datetime import date
from decimal import Decimal

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from core.api_defaults import ApiAuthAndUser
from core.tenant_utils import get_tenant
from .models import CustomerPayment, DeliveryOrder, SalesInvoice, SalesInvoiceLine, SalesSettings
from .serializers import (
    CustomerPaymentSerializer,
    DeliveryOrderSerializer,
    SalesInvoiceListSerializer,
    SalesInvoiceSerializer,
    SalesSettingsSerializer,
)
from .services import (
    credit_preview_for_sale,
    deliver_delivery_order,
    get_or_create_sales_settings,
    next_invoice_number,
    post_customer_payment,
    post_sales_invoice,
    recalculate_invoice_amounts,
    suggest_fifo_allocations,
)


class SalesInvoiceViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    queryset = SalesInvoice.objects.all().select_related(
        "customer", "currency", "journal", "tenant"
    ).prefetch_related("lines")

    def get_serializer_class(self):
        if self.action == "list":
            return SalesInvoiceListSerializer
        return SalesInvoiceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_tenant(self.request)
        if tenant:
            qs = qs.filter(tenant_id=tenant.TenantID)
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        cid = self.request.query_params.get("customer")
        if cid:
            qs = qs.filter(customer_id=cid)
        return qs.order_by("-invoice_date", "-id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        instance = serializer.instance
        headers = self.get_success_headers(serializer.data)
        data = serializer.data
        if hasattr(instance, "_auto_post_error") and instance._auto_post_error:
            data["auto_post_error"] = instance._auto_post_error
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if tenant is None:
            raise DRFValidationError(
                {
                    "tenant": (
                        "لم يتم تحديد الشركة أو أنها غير موجودة. تأكد من إرسال "
                        "X-Tenant-Id في الهيدر وأن الشركة بهذا المعرّف موجودة في قاعدة البيانات "
                        "(أنشئ/أضف Tenant، أو اضبط tenantId في إعدادات الواجهة)."
                    )
                }
            )
        invoice = serializer.save(
            tenant=tenant,
            created_by=self.request.user if self.request.user.is_authenticated else None,
        )
        # ترحيل تلقائي إذا فُعِّل الإعداد وطلب المستخدم ذلك (أو auto_post من الـ body)
        auto_flag = self.request.data.get("auto_post")
        ss = get_or_create_sales_settings(tenant) if tenant else None
        should_auto = False
        if auto_flag is True or str(auto_flag).lower() == "true":
            should_auto = True
        elif auto_flag in (None, "") and ss and ss.auto_post_invoices:
            should_auto = True
        if should_auto and invoice and invoice.status == SalesInvoice.STATUS_DRAFT:
            try:
                post_sales_invoice(invoice, user=self.request.user)
            except Exception as e:  # noqa: BLE001
                # Store error on invoice for later inspection
                invoice._auto_post_error = str(e)

    def perform_update(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != SalesInvoice.STATUS_DRAFT:
            return Response(
                {"detail": "يمكن حذف المسودات فقط. الفواتير المرحّلة لا تُحذف من هنا."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate_invoice(self, request, pk=None):
        """نسخ فاتورة كمسودة جديدة (نفس الأسطر والعميل)."""
        src = self.get_object()
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                inv = SalesInvoice.objects.create(
                    tenant=tenant,
                    invoice_number=next_invoice_number(tenant.TenantID),
                    customer=src.customer,
                    invoice_date=date.today(),
                    due_date=src.due_date,
                    invoice_type=src.invoice_type,
                    currency=src.currency,
                    exchange_rate=src.exchange_rate,
                    invoice_discount=src.invoice_discount,
                    stock_on_post=src.stock_on_post,
                    notes=src.notes,
                    revenue_account=src.revenue_account,
                    cash_or_bank_account=src.cash_or_bank_account,
                    accounts_receivable_account=src.accounts_receivable_account,
                    status=SalesInvoice.STATUS_DRAFT,
                )
                for line in src.lines.all():
                    SalesInvoiceLine.objects.create(
                        tenant=tenant,
                        invoice=inv,
                        product=line.product,
                        quantity=line.quantity,
                        unit_price=line.unit_price,
                        line_discount=line.line_discount,
                        tax_rate=line.tax_rate,
                    )
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
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        ser = SalesInvoiceSerializer(inv, context={"request": request})
        return Response(ser.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="post")
    def post_invoice(self, request, pk=None):
        invoice = self.get_object()
        try:
            post_sales_invoice(invoice, user=request.user)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        invoice.refresh_from_db()
        ser = SalesInvoiceSerializer(invoice, context={"request": request})
        return Response(ser.data)

    @action(detail=False, methods=["get"], url_path="credit-preview")
    def credit_preview(self, request):
        """معاينة ائتمان العميل أثناء إدخال المسودة."""
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST)
        cid = request.query_params.get("customer")
        if not cid:
            return Response({"error": "باراميتر customer مطلوب."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            proposed = Decimal(str(request.query_params.get("proposed_total", "0")))
        except Exception:
            proposed = Decimal("0")
        inv_param = request.query_params.get("exclude_invoice")
        excl = int(inv_param) if inv_param and inv_param.isdigit() else None
        try:
            data = credit_preview_for_sale(
                tenant_id=tenant.TenantID,
                partner_id=int(cid),
                proposed_total=proposed,
                exclude_invoice_id=excl,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data)

    @action(detail=True, methods=["post"], url_path="delivery-order")
    def create_delivery_order(self, request, pk=None):
        invoice = self.get_object()
        tenant = get_tenant(request)
        do = DeliveryOrder.objects.create(
            tenant_id=tenant.TenantID if tenant else invoice.tenant_id,
            invoice=invoice,
            notes=request.data.get("notes", "")[:500],
        )
        return Response(DeliveryOrderSerializer(do).data, status=status.HTTP_201_CREATED)


class DeliveryOrderViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    queryset = DeliveryOrder.objects.all().select_related("invoice", "tenant")
    serializer_class = DeliveryOrderSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة لهذا الطلب."})
        serializer.save(tenant=tenant)

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_tenant(self.request)
        if tenant:
            qs = qs.filter(tenant_id=tenant.TenantID)
        return qs.order_by("-id")

    @action(detail=True, methods=["post"], url_path="deliver")
    def deliver(self, request, pk=None):
        d = self.get_object()
        try:
            deliver_delivery_order(d, user=request.user)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DeliveryOrderSerializer(d).data)


class CustomerPaymentViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    queryset = CustomerPayment.objects.all().select_related(
        "partner", "currency", "cash_or_bank_account", "journal"
    ).prefetch_related("allocations")
    serializer_class = CustomerPaymentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_tenant(self.request)
        if tenant:
            qs = qs.filter(tenant_id=tenant.TenantID)
        return qs.order_by("-payment_date", "-id")

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة لهذا الطلب."})
        serializer.save(tenant=tenant)

    @action(detail=True, methods=["post"], url_path="post")
    def post_payment(self, request, pk=None):
        payment = self.get_object()
        try:
            post_customer_payment(payment, user=request.user)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CustomerPaymentSerializer(payment).data)

    @action(detail=False, methods=["post"], url_path="suggest-fifo-allocations")
    def suggest_fifo_allocations(self, request):
        """اقتراح توزيع المبلغ على الفواتير غير المسددة من الأقدم (FIFO)."""
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST)
        pid = request.data.get("partner")
        amt = request.data.get("amount")
        if pid is None or amt is None:
            return Response(
                {"error": "حقلا partner و amount مطلوبان."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            rows = suggest_fifo_allocations(
                tenant_id=tenant.TenantID,
                partner_id=int(pid),
                amount=Decimal(str(amt)),
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(rows)


class SalesSettingsViewSet(viewsets.ViewSet):
    """نقطة واحدة (GET/PUT) للحصول على/تحديث إعدادات المبيعات للشركة."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    @action(detail=False, methods=["get", "put", "patch"], url_path="current")
    def current(self, request):
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST)
        ss = get_or_create_sales_settings(tenant)
        if request.method == "GET":
            return Response(SalesSettingsSerializer(ss).data)
        ser = SalesSettingsSerializer(ss, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class SalesReportViewSet(viewsets.ViewSet):
    """تقارير مبسّطة."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    @action(detail=False, methods=["get"], url_path="aging")
    def aging(self, request):
        """أعمار الديون لكل مدين (فواتير آجل مرحّلة ومتبقي > 0)."""
        tenant = get_tenant(request)
        if not tenant:
            return Response([])
        qs = SalesInvoice.objects.filter(
            tenant_id=tenant.TenantID,
            status=SalesInvoice.STATUS_POSTED,
            invoice_type=SalesInvoice.INVOICE_CREDIT,
        )
        rows = []
        for inv in qs.select_related("customer"):
            remaining = inv.grand_total - inv.amount_paid
            if remaining <= 0:
                continue
            rows.append(
                {
                    "invoice_id": inv.id,
                    "invoice_number": inv.invoice_number,
                    "customer_id": inv.customer_id,
                    "customer_name": inv.customer.name,
                    "invoice_date": inv.invoice_date,
                    "due_date": inv.due_date,
                    "grand_total": str(inv.grand_total),
                    "amount_paid": str(inv.amount_paid),
                    "remaining": str(remaining),
                }
            )
        return Response(rows)
