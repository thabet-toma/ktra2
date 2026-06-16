from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from accounting.services import unpost_document
from core.api_defaults import ApiAuthAndUser, POSTED_DOC_WARNING
from core.tenant_utils import get_branch, get_tenant
from .models import (
    CreditDebitNote,
    CustomerPayment,
    DeliveryOrder,
    SalesInvoice,
    SalesInvoiceLine,
    SalesQuotation,
    SalesQuotationLine,
    SalesSettings,
)
from .serializers import (
    CreditDebitNoteSerializer,
    CustomerPaymentSerializer,
    DeliveryOrderSerializer,
    SalesInvoiceListSerializer,
    SalesInvoiceSerializer,
    SalesQuotationListSerializer,
    SalesQuotationSerializer,
    SalesSettingsSerializer,
)
from .services import (
    attach_payment_voucher,
    convert_quotation_to_invoice,
    credit_preview_for_sale,
    deliver_delivery_order,
    get_or_create_sales_settings,
    invoice_profits,
    last_sale_price,
    next_invoice_number,
    post_credit_debit_note,
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
            # task11 M4: الفرع النشط يرى فواتيره فقط (الرئيسي يشمل القديمة بلا فرع)
            branch = get_branch(self.request, tenant)
            if branch is not None:
                if branch.is_main:
                    qs = qs.filter(models.Q(branch=branch) | models.Q(branch__isnull=True))
                else:
                    qs = qs.filter(branch=branch)
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
            branch=get_branch(self.request, tenant),
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
        instance = serializer.instance
        if instance is not None and instance.status != SalesInvoice.STATUS_DRAFT:
            raise DRFValidationError(
                {"detail": POSTED_DOC_WARNING, "can_unpost": True},
            )
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != SalesInvoice.STATUS_DRAFT:
            return Response(
                {"detail": POSTED_DOC_WARNING, "can_unpost": True},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="unpost")
    def unpost_invoice(self, request, pk=None):
        """تراجع عن الترحيل: حذف كل قيود الفاتورة وحركات مخزونها وإرجاعها مسودة."""
        invoice = self.get_object()
        if invoice.status != SalesInvoice.STATUS_POSTED:
            return Response(
                {"error": "الفاتورة غير مرحّلة."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                result = unpost_document(
                    tenant_id=invoice.tenant_id,
                    reference_id=invoice.id,
                    journal_reference_types=["SALES_INVOICE", "SALES_DELIVERY_COGS"],
                    stock_reference_types=["SALE", "STOCK_ISSUE"],
                    user=request.user,
                    document_label=f"فاتورة مبيعات {invoice.invoice_number}",
                )
                invoice.status = SalesInvoice.STATUS_DRAFT
                invoice.journal = None
                invoice.amount_paid = Decimal("0")
                invoice.save(update_fields=["status", "journal", "amount_paid"])
                # إعادة الشيكات المرفقة إلى مسودة (عكس ترقيتها عند الترحيل)
                from accounting.models import Cheque
                Cheque.objects.filter(
                    sales_invoice=invoice, status="Under_Collection"
                ).update(status="Draft")
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        invoice.refresh_from_db()
        ser = SalesInvoiceSerializer(invoice, context={"request": request})
        return Response({**ser.data, "unpost_result": result})

    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate_invoice(self, request, pk=None):
        """نسخ فاتورة كمسودة جديدة (نفس الأسطر والعميل)."""
        src = self.get_object()
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                dup_branch = get_branch(request, tenant) or src.branch
                inv = SalesInvoice.objects.create(
                    tenant=tenant,
                    branch=dup_branch,
                    invoice_number=next_invoice_number(
                        tenant.TenantID, getattr(src, "book_number", 0), branch=dup_branch),
                    customer=src.customer,
                    invoice_date=date.today(),
                    due_date=src.due_date,
                    invoice_type=src.invoice_type,
                    currency=src.currency,
                    exchange_rate=src.exchange_rate,
                    invoice_discount=src.invoice_discount,
                    discount_percent=getattr(src, "discount_percent", 0) or 0,
                    stock_on_post=src.stock_on_post,
                    notes=src.notes,
                    revenue_account=src.revenue_account,
                    cash_or_bank_account=src.cash_or_bank_account,
                    accounts_receivable_account=src.accounts_receivable_account,
                    prices_include_tax=getattr(src, "prices_include_tax", False),
                    licensed_dealer_no=src.licensed_dealer_no or "",
                    settlement_invoice_no=src.settlement_invoice_no or "",
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
                        unit=line.unit or "",
                        warehouse=line.warehouse or "",
                        catalog_no=line.catalog_no or "",
                        expiry_date=line.expiry_date,
                        extra_quantity=line.extra_quantity,
                        line_tax_percent=line.line_tax_percent,
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

    @action(detail=True, methods=["post"], url_path="payment-voucher")
    def payment_voucher(self, request, pk=None):
        """M2-T3 — Attach the financial voucher (cash + cheques) to the invoice.

        Body:
            {
                "cash_amount": "100.00",
                "cash_account_id": 12,
                "cheques": [
                    {"cheque_number": "12345", "amount": "50", "bank_name": "...",
                     "due_date": "2026-06-01", "issue_date": "2026-05-20", "notes": ""}
                ]
            }
        Replaces previously-attached DRAFT cheques. Posting still happens via
        the `/post` endpoint, which produces ONE integrated journal (M2-T3).

        P-H-5: pass `"post": true` in the body to atomically attach + post in
        a single `transaction.atomic()` so a post failure rolls the cheques
        back too. Default `post: false` preserves the prior two-step flow.
        """
        invoice = self.get_object()
        want_post = bool(request.data.get("post"))
        try:
            if want_post:
                from sales.services import attach_voucher_and_post
                attach_voucher_and_post(
                    invoice,
                    cash_amount=request.data.get("cash_amount", 0),
                    cash_account_id=request.data.get("cash_account_id"),
                    cheques=request.data.get("cheques") or [],
                    user=request.user,
                )
            else:
                attach_payment_voucher(
                    invoice,
                    cash_amount=request.data.get("cash_amount", 0),
                    cash_account_id=request.data.get("cash_account_id"),
                    cheques=request.data.get("cheques") or [],
                    user=request.user,
                )
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

    @action(detail=False, methods=["get"], url_path="last-price")
    def last_price(self, request):
        """task18 DEF-C2: آخر سعر بيع لصنف (واختيارياً لعميل) من فواتير مرحَّلة."""
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST)
        pid = request.query_params.get("product")
        if not pid or not pid.isdigit():
            return Response({"error": "باراميتر product مطلوب."}, status=status.HTTP_400_BAD_REQUEST)
        cid = request.query_params.get("customer")
        data = last_sale_price(
            tenant_id=tenant.TenantID,
            product_id=int(pid),
            customer_id=int(cid) if cid and cid.isdigit() else None,
        )
        return Response(data)

    @action(detail=False, methods=["get"], url_path="profits")
    def profits(self, request):
        """task18 DEF-C4: تقرير أرباح الفواتير (إيراد/تكلفة/ربح لكل فاتورة + إجماليات)."""
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST)
        cid = request.query_params.get("customer")
        customer_id = int(cid) if cid and cid.isdigit() else None
        data = invoice_profits(
            tenant_id=tenant.TenantID,
            branch=get_branch(request, tenant),
            date_from=request.query_params.get("date_from") or None,
            date_to=request.query_params.get("date_to") or None,
            customer_id=customer_id,
        )
        return Response(data)

    @action(detail=False, methods=["get"], url_path="next-number")
    def next_number(self, request):
        """معاينة رقم الفاتورة التالي بدون استهلاكه."""
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            book = int(request.query_params.get("book", 0))
        except (TypeError, ValueError):
            book = 0
        from .services import preview_next_invoice_number
        branch = get_branch(request, tenant)
        next_num = preview_next_invoice_number(tenant.TenantID, book, branch=branch)
        return Response({"next_number": next_num})

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
        # P-H-9: shared cross-payment-type validation (amount, date, tenant,
        # partner-presence). The same gate is applied on deal / clearance /
        # shipment-agent payment surfaces so all four refuse the same set
        # of malformed inputs. Wrapped in atomic so the row is rolled back
        # if validate_payment rejects it.
        from django.db import transaction
        from core.payments import PaymentContext, validate_payment
        from rest_framework.exceptions import ValidationError as DRFValidationError
        with transaction.atomic():
            payment = serializer.save(tenant=tenant)
            ctx = PaymentContext.from_customer_payment(payment)
            errors = validate_payment(ctx)
            if errors:
                raise DRFValidationError({"payment": errors})

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


class SalesQuotationViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    queryset = SalesQuotation.objects.all().select_related(
        "customer", "currency", "tenant",
    ).prefetch_related("lines")
    serializer_class = SalesQuotationSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_tenant(self.request)
        if tenant:
            qs = qs.filter(tenant_id=tenant.TenantID)
        return qs.order_by("-quotation_date", "-id")

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة لهذا الطلب."})
        serializer.save(tenant=tenant, created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="convert")
    def convert(self, request, pk=None):
        quotation = self.get_object()
        try:
            invoice = convert_quotation_to_invoice(quotation, user=request.user)
            return Response({
                "status": "تم تحويل العرض إلى فاتورة.",
                "invoice": SalesInvoiceSerializer(invoice).data,
            })
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreditDebitNoteViewSet(viewsets.ModelViewSet):
    """M4-T4 — Credit / Debit notes (إشعارات مدينة/دائنة)."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = CreditDebitNoteSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        qs = CreditDebitNote.objects.select_related("customer", "related_invoice", "journal")
        if tenant:
            qs = qs.filter(tenant=tenant)
        return qs.order_by("-note_date", "-id")

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة."})
        serializer.save(tenant=tenant, created_by=self.request.user if self.request.user.is_authenticated else None)

    @action(detail=True, methods=["post"], url_path="post")
    def post_action(self, request, pk=None):
        """ترحيل الإشعار — قيد متوازن idempotent عبر post_journal()."""
        note = self.get_object()
        try:
            post_credit_debit_note(note, user=request.user)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        note.refresh_from_db()
        return Response(CreditDebitNoteSerializer(note).data)
