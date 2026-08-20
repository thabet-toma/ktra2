import logging
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from accounting.services import attach_partner_posted_balance, unpost_document
from core.access import require_perm, requires_perm, user_has_perm
from core.activity import (
    build_activity_changes,
    build_line_changes,
    describe_activity_changes,
    log_activity,
    log_view,
    snapshot_document_lines,
    snapshot_fields,
)
from core.pagination import EnforcedPageNumberPagination
from core.api_defaults import ApiAuthAndUser, PagePartnerBalanceMixin, POSTED_DOC_WARNING
from core.plans import enforce_limits
from core.tenant_utils import get_branch, get_tenant
from .models import (
    CreditDebitNote,
    CustomerPayment,
    DeliveryOrder,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesQuotation,
    SalesQuotationLine,
    SalesSettings,
)
from .serializers import (
    CreditDebitNoteSerializer,
    CustomerPaymentSerializer,
    DeliveryOrderListSerializer,
    DeliveryOrderSerializer,
    SalesInvoiceListSerializer,
    SalesInvoiceSerializer,
    SalesOrderSerializer,
    SalesQuotationListSerializer,
    SalesQuotationSerializer,
    SalesSettingsSerializer,
)
from .services import (
    allocate_customer_payment,
    attach_payment_voucher,
    collect_invoice_payment,
    cancel_quotation,
    cancel_sales_order,
    confirm_sales_order,
    convert_order_to_invoice,
    convert_quotation_to_invoice,
    convert_quotation_to_order,
    document_delete_allowed,
    log_order_activity,
    record_order_deposit,
    credit_preview_for_sale,
    customer_price_list,
    save_customer_quotes,
    deliver_delivery_order,
    deliver_invoice_lines,
    get_or_create_sales_settings,
    guard_invoice_payments_before_unpost,
    invoice_profits,
    last_sale_price,
    next_invoice_number,
    post_credit_debit_note,
    post_customer_payment,
    post_sales_invoice,
    recalculate_invoice_amounts,
    release_auto_cash_settlement,
    release_sales_serials,
    remaining_delivery_lines,
    suggest_fifo_allocations,
    unpost_customer_payment,
)
from django.utils import timezone

logger = logging.getLogger(__name__)

# تفصيل حركة التعديل في سجل النشاط: ما الذي يُقارَن قبل الحفظ وبعده، وبأي اسم
# عربي يُعرض. البنود تُقارَن بالصنف فيظهر «أضاف/حذف صنفاً» و«غيّر السعر من…إلى».
INVOICE_ACTIVITY_FIELD_LABELS = {
    "customer": "العميل",
    "invoice_date": "تاريخ الفاتورة",
    "due_date": "تاريخ الاستحقاق",
    "invoice_type": "نوع الفاتورة",
    "invoice_discount": "خصم الفاتورة",
    "discount_percent": "نسبة الخصم",
    "exchange_rate": "سعر الصرف",
    "notes": "الملاحظات",
}
INVOICE_ACTIVITY_LINE_LABELS = {
    "quantity": "الكمية",
    "unit_price": "السعر",
    "line_discount": "خصم البند",
}


def _invoice_line_snapshot(invoice):
    """لقطة بنود الفاتورة من القاعدة — لا من ذاكرة prefetch (تكون قديمة بعد الحفظ)."""
    lines = SalesInvoiceLine.objects.filter(invoice=invoice).select_related("product")
    return snapshot_document_lines(
        lines,
        label=lambda line: (
            line.product.name_ar or line.product.name_en or line.product.sku
        ),
        fields=INVOICE_ACTIVITY_LINE_LABELS,
    )


class SalesInvoiceViewSet(PagePartnerBalanceMixin, viewsets.ModelViewSet):
    # P0-5: ترقيم إلزامي — SalesInvoicesPage مُرقَّمة أصلاً، والمحرّرات على
    # نقطة lookup المحدودة (مصفوفة خام بسقف 500، لا يمسّها ترقيم القائمة).
    pagination_class = EnforcedPageNumberPagination
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    partner_balance_spec = ("customer_id", False, "customer_balance")

    queryset = SalesInvoice.objects.all().select_related(
        "customer", "currency", "journal", "tenant"
    )

    def get_serializer_class(self):
        if self.action in {"list", "lookup"}:
            return SalesInvoiceListSerializer
        return SalesInvoiceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_tenant(self.request)
        if not tenant:
            return qs.none()
        qs = qs.filter(tenant_id=tenant.TenantID)
        # القائمة تأخذ الرصيد من `PagePartnerBalanceMixin` باستعلام واحد بعد
        # الترقيم؛ الاستعلام الفرعي هنا للصف الواحد (المستند المفتوح) فقط.
        if self.action not in {"list", "lookup"}:
            from accounting.services import annotate_partner_posted_balance
            qs = annotate_partner_posted_balance(
                qs, "customer_id", supplier=False, alias="customer_balance",
            )
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
        invoice_type = self.request.query_params.get("invoice_type")
        if invoice_type:
            qs = qs.filter(invoice_type=invoice_type)
        payment_status = self.request.query_params.get("payment_status")
        if payment_status == "paid":
            qs = qs.filter(grand_total__gt=0, amount_paid__gte=models.F("grand_total"))
        elif payment_status == "partially_paid":
            qs = qs.filter(
                grand_total__gt=0, amount_paid__gt=0,
                amount_paid__lt=models.F("grand_total"),
            )
        elif payment_status == "unpaid":
            qs = qs.filter(models.Q(grand_total__lte=0) | models.Q(amount_paid__lte=0))
        date_from = self.request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        date_to = self.request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                models.Q(invoice_number__icontains=search)
                | models.Q(customer__name__icontains=search)
                | models.Q(customer__legal_name__icontains=search)
            )
        if self.action not in {"list", "lookup"}:
            qs = qs.prefetch_related(
                "lines__product",
                "payment_allocations__payment__currency",
                "payment_allocations__payment__journal",
            )
        return qs.order_by("-invoice_date", "-id")

    @action(detail=False, methods=["get"], url_path="lookup")
    def lookup(self, request):
        """Bounded raw-array invoice choices for editors without page controls."""
        try:
            limit = int(request.query_params.get("limit", 200))
        except (TypeError, ValueError):
            limit = 200
        limit = min(max(limit, 1), 500)
        rows = list(self.get_queryset()[:limit])
        spec = self.partner_balance_spec
        attach_partner_posted_balance(rows, spec[0], supplier=spec[1], attr=spec[2])
        return Response(self.get_serializer(rows, many=True).data)

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
        require_perm(self.request, "sales.invoice.create")
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
        # T-PLANLIMITS: حدّ الخطة يُفحص قبل الحفظ — الفاتورة المحفوظة ثم المرفوضة
        # تبقى محسوبة ضمن الحدّ.
        enforce_limits(tenant, "sales.invoices", "documents.invoices")
        # ترحيل تلقائي إذا فُعِّل الإعداد وطلب المستخدم ذلك (أو auto_post من الـ body)
        auto_flag = self.request.data.get("auto_post")
        ss = get_or_create_sales_settings(tenant) if tenant else None
        should_auto = False
        if auto_flag is True or str(auto_flag).lower() == "true":
            require_perm(self.request, "sales.invoice.post")
            should_auto = True
        elif (
            auto_flag in (None, "")
            and ss
            and ss.auto_post_invoices
            and user_has_perm(self.request.user, tenant, "sales.invoice.post")
        ):
            should_auto = True
        invoice = serializer.save(
            tenant=tenant,
            branch=get_branch(self.request, tenant),
            created_by=self.request.user if self.request.user.is_authenticated else None,
        )
        if should_auto and invoice and invoice.status == SalesInvoice.STATUS_DRAFT:
            try:
                post_sales_invoice(invoice, user=self.request.user)
            except Exception as e:  # noqa: BLE001
                # Store error on invoice for later inspection
                invoice._auto_post_error = str(e)
        log_activity(
            action="create", entity_type="sales_invoice", entity_id=invoice.id,
            entity_label=invoice.invoice_number, description="إنشاء فاتورة مبيعات",
            partner_ids=[invoice.customer_id],
            request=self.request,
        )

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        obj = self.get_object()
        log_view(
            entity_type="sales_invoice", entity_id=obj.id,
            entity_label=obj.invoice_number, request=request,
        )
        return response

    def perform_update(self, serializer):
        require_perm(self.request, "sales.invoice.edit")
        instance = serializer.instance
        if instance is not None and instance.status != SalesInvoice.STATUS_DRAFT:
            raise DRFValidationError(
                {"detail": POSTED_DOC_WARNING, "can_unpost": True},
            )
        before_header = snapshot_fields(instance, INVOICE_ACTIVITY_FIELD_LABELS)
        before_lines = _invoice_line_snapshot(instance)
        invoice = serializer.save()
        changes = build_activity_changes(
            before=before_header,
            after=snapshot_fields(invoice, INVOICE_ACTIVITY_FIELD_LABELS),
            labels=INVOICE_ACTIVITY_FIELD_LABELS,
        ) + build_line_changes(
            before=before_lines,
            after=_invoice_line_snapshot(invoice),
            labels=INVOICE_ACTIVITY_LINE_LABELS,
        )
        details = describe_activity_changes(changes)
        logger.info(
            "Sales invoice %s edited by %s with %s change(s).",
            invoice.invoice_number, getattr(self.request.user, "username", "—"), len(changes),
        )
        log_activity(
            action="update", entity_type="sales_invoice", entity_id=invoice.id,
            entity_label=invoice.invoice_number,
            description=f"تعديل فاتورة مبيعات — {details}" if details else "تعديل فاتورة مبيعات",
            metadata={"changes": changes} if changes else None,
            partner_ids=[invoice.customer_id],
            request=self.request,
        )

    def destroy(self, request, *args, **kwargs):
        require_perm(request, "sales.invoice.delete")
        instance = self.get_object()
        if instance.status != SalesInvoice.STATUS_DRAFT:
            return Response(
                {"detail": POSTED_DOC_WARNING, "can_unpost": True},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # T-ARINT: نفس حارس إلغاء الترحيل — حذف فاتورة عليها سند قبض مرحّل
        # (شكل قديم فاسد) يُيتّم قيد السند فيبقى دائن الذمم بلا مقابل.
        try:
            guard_invoice_payments_before_unpost(instance, action_label="حذف")
        except ValidationError as e:
            return Response(
                {"error": "؛ ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST
            )
        inv_id, inv_no, customer_id = instance.id, instance.invoice_number, instance.customer_id
        response = super().destroy(request, *args, **kwargs)
        log_activity(
            action="delete", entity_type="sales_invoice", entity_id=inv_id,
            entity_label=inv_no, description="حذف فاتورة مبيعات", request=request,
            partner_ids=[customer_id],
        )
        return response

    @action(detail=True, methods=["post"], url_path="unpost")
    @requires_perm("sales.invoice.unpost")
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
                # T-ARINT: سند التسوية النقدية التلقائي من إنتاج الترحيل نفسه —
                # يُحرَّر (قيوده + صفوفه) ذرّياً معه، فلا يبقى معلّقاً ولا يتكرّر
                # عند إعادة الترحيل. سندات المستخدم يحرسها الفحص التالي فتُمنع.
                released = release_auto_cash_settlement(invoice, user=request.user)
                guard_invoice_payments_before_unpost(invoice)
                # الوحدات المُرقَّمة تعود للمخزن مع مخزونها؛ ما اختاره المستخدم يبقى
                # على البند فتستهلك إعادة الترحيل الوحدات ذاتها.
                release_sales_serials(invoice)
                # THA-24: بطاقات الكفالة التلقائية من إنتاج هذا الترحيل — تُحذف
                # معه وتعود بإعادته (نمط الحذف نفسه). اليدوية لا تُمَسّ.
                from after_sales.services import delete_auto_warranty_cards

                delete_auto_warranty_cards(invoice)
                result = unpost_document(
                    tenant_id=invoice.tenant_id,
                    reference_id=invoice.id,
                    journal_reference_types=["SALES_INVOICE", "SALES_DELIVERY_COGS"],
                    stock_reference_types=["SALE", "STOCK_ISSUE"],
                    user=request.user,
                    document_label=f"فاتورة مبيعات {invoice.invoice_number}",
                    recycle=True,
                )
                invoice.status = SalesInvoice.STATUS_DRAFT
                invoice.journal = None
                # آمن الآن: الحارس أعلاه أثبت ألّا سند قبض مرحّلاً بقي على
                # الفاتورة، فلا يبقى تحصيل حيّ بينما تعود «غير مدفوعة».
                invoice.amount_paid = Decimal("0")
                invoice.delivery_status = SalesInvoice.DELIVERY_NOT
                invoice.save(update_fields=[
                    "status", "journal", "amount_paid", "delivery_status",
                ])
                # حركات المخزون عُكِست أعلاه ⇒ تُصفَّر الكميات المسلَّمة وتُحذف
                # الإرساليات المبنية عليها (تُعاد بالتسليم بعد إعادة الترحيل).
                invoice.lines.update(delivered_quantity=0)
                invoice.delivery_orders.all().delete()
                # إعادة الشيكات المرفقة إلى مسودة (عكس ترقيتها عند الترحيل).
                # CHQ-2: عبر خدمة الشيكات — تسجّل الرجوع في سجل الشيك وتغطّي
                # «مستلَم» أيضاً. الشيك المتحرك منعه الحارس أعلاه أصلاً.
                from accounting.models import Cheque
                from accounting.services import record_document_cheque_unposting

                record_document_cheque_unposting(
                    list(Cheque.objects.filter(
                        tenant_id=invoice.tenant_id, sales_invoice=invoice)),
                    user=request.user,
                )
        except ValidationError as e:
            # رسائل الحُرّاس عربية موجّهة للمستخدم — تُعاد نصّاً لا ['...'].
            return Response(
                {"error": "؛ ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        invoice.refresh_from_db()
        log_activity(
            action="unpost", entity_type="sales_invoice", entity_id=invoice.id,
            entity_label=invoice.invoice_number, description="إلغاء ترحيل فاتورة مبيعات",
            partner_ids=[invoice.customer_id],
            request=request,
        )
        ser = SalesInvoiceSerializer(invoice, context={"request": request})
        return Response({
            **ser.data,
            "unpost_result": {**result, "auto_settlements_released": released},
        })

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
                    invoice_date=timezone.localdate(),
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
        log_activity(
            action="duplicate", entity_type="sales_invoice", entity_id=inv.id,
            entity_label=inv.invoice_number, description=f"نسخ من فاتورة {src.invoice_number}",
            partner_ids=[inv.customer_id],
            request=request,
        )
        ser = SalesInvoiceSerializer(inv, context={"request": request})
        return Response(ser.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="post")
    @requires_perm("sales.invoice.post")
    def post_invoice(self, request, pk=None):
        invoice = self.get_object()
        try:
            post_sales_invoice(invoice, user=request.user)
        except ValidationError as e:
            # `str(ValidationError)` يطبع تمثيل بايثون (`['…']`) — أول رسالة يراها
            # المستخدم من الحارس يجب أن تكون جملةً، كما في جانب الشراء.
            return Response(
                {"error": e.message if hasattr(e, "message") else "؛ ".join(e.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        invoice.refresh_from_db()
        log_activity(
            action="post", entity_type="sales_invoice", entity_id=invoice.id,
            entity_label=invoice.invoice_number, description="ترحيل فاتورة مبيعات",
            partner_ids=[invoice.customer_id],
            request=request,
        )
        ser = SalesInvoiceSerializer(invoice, context={"request": request})
        return Response(ser.data)

    @action(detail=True, methods=["post"], url_path="collect")
    @requires_perm("sales.payment.create")
    def collect(self, request, pk=None):
        """T2 — تحصيل الفاتورة من داخلها: نقد + شيكات + رصيد العميل، بعملية ذرّية.

        Body:
            {
                "cash": "60.00",
                "cash_account_id": 12,
                "cheques": [
                    {"cheque_number": "12345", "amount": "40",
                     "due_date": "2026-09-01", "bank_name": "..."}
                ],
                "from_on_account": [{"payment_id": 7, "amount": "20"}],
                "post_invoice": true,
                "payment_date": "2026-07-01"
            }

        يُنتج **سند قبض واحداً مرحّلاً** بكل ما دُفع نقداً وشيكاتٍ، ويخصم ما
        اختير من رصيد العميل ربطاً بلا قيد جديد. الفشل في أي خطوة يُرجع كل شيء.
        """
        invoice = self.get_object()
        want_post = bool(request.data.get("post_invoice"))
        if want_post:
            require_perm(request, "sales.invoice.post")
        try:
            payment = collect_invoice_payment(
                invoice,
                cash=request.data.get("cash"),
                cash_account_id=request.data.get("cash_account_id"),
                cheques=request.data.get("cheques") or [],
                from_on_account=request.data.get("from_on_account") or [],
                post_invoice=want_post,
                payment_date=request.data.get("payment_date") or None,
                user=request.user,
            )
        except ValidationError as e:
            # رسائل الحُرّاس عربية موجّهة للمستخدم — تُعاد جملةً لا ['...'].
            return Response(
                {"error": e.message if hasattr(e, "message") else "؛ ".join(e.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        invoice.refresh_from_db()
        log_activity(
            action="payment", entity_type="sales_invoice", entity_id=invoice.id,
            entity_label=invoice.invoice_number,
            description="تحصيل من داخل الفاتورة" + (" + ترحيل" if want_post else ""),
            partner_ids=[invoice.customer_id],
            request=request,
        )
        ser = SalesInvoiceSerializer(invoice, context={"request": request})
        return Response({
            **ser.data,
            "payment_id": payment.pk if payment is not None else None,
        })

    @action(detail=True, methods=["post"], url_path="payment-voucher")
    @requires_perm("sales.payment.create")
    def payment_voucher(self, request, pk=None):
        """M2-T3 — Attach the financial voucher (cheques) to the invoice.

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

        T2: شكل النقطة محفوظ لأي مستهلك خارجي، لكنها صارت غلافاً فوق منسّق
        التحصيل — فالنقد يصير سند قبض حقيقياً بدل عمود لا يُرحَّل — واكتسبت فحص
        الصلاحية الذي كانت وحدها بين أخواتها بلا فحص. المفضَّل للجديد:
        `invoices/{id}/collect/`.
        """
        invoice = self.get_object()
        want_post = bool(request.data.get("post"))
        if want_post:
            require_perm(request, "sales.invoice.post")
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
        log_activity(
            action="payment", entity_type="sales_invoice", entity_id=invoice.id,
            entity_label=invoice.invoice_number,
            description="سند قبض" + (" + ترحيل" if want_post else ""),
            partner_ids=[invoice.customer_id],
            request=request,
        )
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

    @action(detail=False, methods=["get"], url_path="resolve-price")
    def resolve_price(self, request):
        """FEAT-2: السعر المقترح لبند بيع — آخر سعر دفعه هذا العميل لهذا الصنف.

        يفوّض إلى core.pricing (المصدر المشترك مع الشراء): آخر بيع للعميل ثم
        سعر البيع الافتراضي للصنف ثم فارغ — مع تطبيع العملة وأساس الضريبة.
        """
        from core.pricing import resolve_sales_price

        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST)
        pid = request.query_params.get("product")
        if not pid or not pid.isdigit():
            return Response({"error": "باراميتر product مطلوب."}, status=status.HTTP_400_BAD_REQUEST)
        cid = request.query_params.get("customer")
        rate = request.query_params.get("exchange_rate")
        cur = request.query_params.get("currency")
        inc = request.query_params.get("tax_inclusive")
        data = resolve_sales_price(
            tenant_id=tenant.TenantID,
            product_id=int(pid),
            customer_id=int(cid) if cid and cid.isdigit() else None,
            target_currency_id=int(cur) if cur and cur.isdigit() else None,
            target_exchange_rate=Decimal(str(rate)) if rate else Decimal("1"),
            target_tax_inclusive=str(inc).lower() in ("1", "true", "yes"),
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

    @action(detail=True, methods=["get"], url_path="delivery-lines")
    def delivery_lines(self, request, pk=None):
        """بنود الفاتورة القابلة للتسليم (المفوتر/المسلَّم/المتبقي) — تغذّي نافذة التسليم."""
        invoice = self.get_object()
        return Response({
            "invoice_number": invoice.invoice_number,
            "delivery_status": invoice.delivery_status,
            "delivery_status_display": invoice.get_delivery_status_display(),
            "stock_on_post": invoice.stock_on_post,
            "lines": [
                {k: (str(v) if isinstance(v, Decimal) else v) for k, v in row.items()}
                for row in remaining_delivery_lines(invoice)
            ],
        })

    @action(detail=True, methods=["post"], url_path="deliver")
    @requires_perm("sales.invoice.post")
    def deliver(self, request, pk=None):
        """تسليم بنود مختارة من الفاتورة (إرسالية) — خصم مخزون + قيد تكلفة للمُسلَّم.

        Body: { "lines": [ { "line_id": int, "quantity": number }, ... ], "notes": str }
        """
        invoice = self.get_object()
        lines = request.data.get("lines")
        if not isinstance(lines, list):
            return Response(
                {"error": "أرسل قائمة البنود المراد تسليمها."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            delivery = deliver_invoice_lines(
                invoice,
                lines=lines,
                user=request.user,
                notes=str(request.data.get("notes", "") or "")[:500],
            )
        except ValidationError as e:
            msg = "؛ ".join(e.messages) if hasattr(e, "messages") else str(e)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("sales invoice deliver failed pk=%s", invoice.pk)
            return Response(
                {"error": "حدث خطأ غير متوقع أثناء التسليم."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        invoice.refresh_from_db()
        log_activity(
            action="deliver", entity_type="sales_invoice", entity_id=invoice.id,
            entity_label=invoice.invoice_number, description="تسليم بضاعة فاتورة مبيعات",
            partner_ids=[invoice.customer_id],
            request=request,
        )
        return Response({
            "delivery_id": delivery.id,
            "delivery_status": invoice.delivery_status,
            "delivery_status_display": invoice.get_delivery_status_display(),
            "lines_delivered": delivery.lines.count(),
        })


class DeliveryOrderViewSet(viewsets.ModelViewSet):
    # P0-5: ترقيم إلزامي — DeliveryNotesPage صارت على أحدث 200 مع بحث خادمي،
    # وoutstanding نقطة action مستقلة.
    pagination_class = EnforcedPageNumberPagination
    """إرساليات البيع — مستند تسليم البضاعة المرتبط بفاتورة.

    الإنشاء **هو** فعل التسليم: يمرّ عبر `deliver_invoice_lines` نفسه الذي
    يستدعيه زر «تسليم» داخل قائمة الفواتير، فلا مساران لإخراج البضاعة.
    مرآة `GoodsReceiptViewSet` في الشراء.
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    # P1-1 (SCALABILITY_AUDIT §2-2): `partner` و`invoice__lines` كانا خارج الجلب
    # المسبق، والمُسلسِل يقرأ `obj.partner.name` (سند مستقل) و`obj.invoice.lines`
    # (حساب المتبقّي) ⇒ استعلامان لكل صف على قائمة كاملة.
    queryset = DeliveryOrder.objects.all().select_related(
        "invoice", "invoice__customer", "partner", "tenant",
    ).prefetch_related(
        "lines__product", "lines__invoice_line", "lines__warehouse",
        "invoice__lines",
    )
    serializer_class = DeliveryOrderSerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action == "list":
            return DeliveryOrderListSerializer
        return DeliveryOrderSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # P1-7 (المرحلة 5): .none() عند غياب الشركة بدل إرساليات كل الشركات.
        tenant = get_tenant(self.request)
        if not tenant:
            return qs.none()
        qs = qs.filter(tenant_id=tenant.TenantID)
        invoice_id = self.request.query_params.get("invoice")
        if invoice_id:
            qs = qs.filter(invoice_id=invoice_id)
        kind = self.request.query_params.get("kind")
        if kind == "linked":
            qs = qs.filter(invoice__isnull=False)
        elif kind == "standalone":
            qs = qs.filter(invoice__isnull=True)
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                models.Q(delivery_number__icontains=search)
                | models.Q(customer_ref__icontains=search)
                | models.Q(invoice__invoice_number__icontains=search)
                | models.Q(invoice__customer__name__icontains=search)
                | models.Q(partner__name__icontains=search)
            )
        return qs.order_by("-id")

    def _apply(self, request, *, existing=None):
        """المسار الموحّد للإنشاء والتعديل — التسليم فعل واحد مهما كان مدخله.

        Body: { "invoice": int|null, "partner": int, "customer_ref": str,
                "delivery_date": "YYYY-MM-DD", "notes": str,
                "lines": [ { "line_id"?, "product_id"?, "quantity" } ] }
        بلا `invoice` ⇒ «سند تسليم» مستقل (يتطلب `partner`).
        """
        from partners.models import Partner
        from .services import (
            create_standalone_delivery_note, get_or_create_sales_settings,
            void_delivery_note,
        )

        require_perm(request, "sales.invoice.post")
        tenant = get_tenant(request)
        if not tenant:
            return Response(
                {"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST,
            )
        ss = get_or_create_sales_settings(tenant)
        lines = request.data.get("lines")
        if not isinstance(lines, list):
            return Response(
                {"error": "أرسل قائمة البنود المراد تسليمها."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice_id = request.data.get("invoice") or None
        invoice = None
        if invoice_id:
            invoice = SalesInvoice.objects.filter(pk=invoice_id, tenant=tenant).first()
            if not invoice:
                return Response(
                    {"error": "الفاتورة المرتبطة غير موجودة."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif not ss.allow_standalone_delivery:
            return Response(
                {"error": "اختر الفاتورة المرتبطة — سند التسليم المستقل معطّل من إعدادات المبيعات."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        partner = None
        if request.data.get("partner"):
            partner = Partner.objects.filter(
                pk=request.data.get("partner"), tenant=tenant,
            ).first()
            if partner is None:
                return Response(
                    {"error": "العميل غير موجود."}, status=status.HTTP_400_BAD_REQUEST,
                )

        notes = str(request.data.get("notes", "") or "")[:500]
        customer_ref = str(request.data.get("customer_ref", "") or "")[:100]
        delivery_date = request.data.get("delivery_date") or None

        try:
            with transaction.atomic():
                # التعديل = عكس أثر الإرسالية القديمة ثم تطبيق الجديد ذرّياً.
                if existing is not None:
                    void_delivery_note(existing, user=request.user)
                if invoice is not None:
                    delivery = deliver_invoice_lines(
                        invoice, lines=lines, user=request.user, notes=notes,
                        delivery_date=delivery_date,
                    )
                    if customer_ref:
                        delivery.customer_ref = customer_ref
                        delivery.save(update_fields=["customer_ref"])
                else:
                    delivery = create_standalone_delivery_note(
                        tenant, partner=partner, lines=lines,
                        branch=get_branch(request, tenant), user=request.user,
                        delivery_date=delivery_date, notes=notes,
                        customer_ref=customer_ref,
                    )
        except ValidationError as e:
            msg = "؛ ".join(e.messages) if hasattr(e, "messages") else str(e)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("delivery note save failed")
            return Response(
                {"error": "حدث خطأ غير متوقع أثناء حفظ الإرسالية."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        log_activity(
            action="update" if existing is not None else "create",
            entity_type="sales_delivery_note", entity_id=delivery.id,
            entity_label=delivery.delivery_number,
            description="تعديل إرسالية بيع" if existing is not None else "إنشاء إرسالية بيع",
            partner_ids=[invoice.customer_id] if invoice else (
                [partner.id] if partner else []),
            request=request,
        )
        return Response(
            DeliveryOrderSerializer(delivery).data,
            status=status.HTTP_200_OK if existing is not None else status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="outstanding")
    def outstanding(self, request):
        """البواقي غير المسلَّمة عبر كل فواتير البيع المرحّلة — تقرير قابل للطباعة.

        مصدر واحد للشاشة وللطباعة/PDF، فلا يُحتسب الباقي مرتين بطريقتين.
        """
        tenant = get_tenant(request)
        if not tenant:
            return Response({"rows": []})
        invoices = (
            SalesInvoice.objects.filter(
                tenant=tenant, status=SalesInvoice.STATUS_POSTED, stock_on_post=False,
            )
            .exclude(delivery_status=SalesInvoice.DELIVERY_FULL)
            .select_related("customer")
            .prefetch_related("lines__product")
        )
        rows = []
        for inv in invoices:
            for line in inv.lines.all():
                if getattr(line.product, "is_service", False):
                    continue
                ordered = Decimal(str(line.quantity or 0))
                delivered = Decimal(str(line.delivered_quantity or 0))
                remaining = ordered - delivered
                if remaining <= 0:
                    continue
                rows.append({
                    "invoice": inv.id,
                    "invoice_number": inv.invoice_number,
                    "invoice_date": inv.invoice_date,
                    "partner_name": inv.customer.name if inv.customer_id else "",
                    "product": line.product_id,
                    "product_name": str(line.product),
                    "quantity": str(ordered),
                    "delivered_quantity": str(delivered),
                    "remaining_quantity": str(remaining),
                })
        return Response({"count": len(rows), "rows": rows})

    def create(self, request, *args, **kwargs):
        return self._apply(request)

    def update(self, request, *args, **kwargs):
        """تعديل الإرسالية: عكس أثرها القديم وإعادة تطبيق البنود الجديدة."""
        from .services import get_or_create_sales_settings

        delivery = self.get_object()
        if not get_or_create_sales_settings(get_tenant(request)).allow_edit_delivery:
            return Response(
                {"error": "تعديل الإرسالية معطّل من إعدادات المبيعات."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._apply(request, existing=delivery)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """إلغاء الإرسالية = عكس حركاتها وقيدها وكمياتها المسلَّمة."""
        from .services import get_or_create_sales_settings, void_delivery_note

        require_perm(request, "sales.invoice.post")
        delivery = self.get_object()
        if not get_or_create_sales_settings(get_tenant(request)).allow_edit_delivery:
            return Response(
                {"error": "حذف الإرسالية معطّل من إعدادات المبيعات."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        number = delivery.delivery_number or f"#{delivery.id}"
        try:
            result = void_delivery_note(delivery, user=request.user)
        except ValidationError as e:
            msg = "؛ ".join(e.messages) if hasattr(e, "messages") else str(e)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        log_activity(
            action="delete", entity_type="sales_delivery_note", entity_id=0,
            entity_label=number, description="إلغاء إرسالية بيع", request=request,
        )
        return Response({"message": "تم إلغاء الإرسالية وعكس أثرها.", **result})

    @action(detail=True, methods=["post"], url_path="deliver")
    def deliver(self, request, pk=None):
        d = self.get_object()
        try:
            deliver_delivery_order(d, user=request.user)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DeliveryOrderSerializer(d).data)


class CustomerPaymentViewSet(viewsets.ModelViewSet):
    # P0-5: ترقيم إلزامي — الشاشة الرئيسية على أحدث 200، والاستدعاءات
    # المفلترة بشريك بسقف صريح.
    pagination_class = EnforcedPageNumberPagination
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    queryset = CustomerPayment.objects.all().select_related(
        "partner", "currency", "cash_or_bank_account", "journal"
    ).prefetch_related("allocations")
    serializer_class = CustomerPaymentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_tenant(self.request)
        if not tenant:
            return qs.none()
        qs = qs.filter(tenant_id=tenant.TenantID)
        # بطاقة الشريك تجلب سنداته وحدها (لا كل سندات الشركة).
        partner_id = self.request.query_params.get("partner")
        if partner_id:
            try:
                qs = qs.filter(partner_id=int(partner_id))
            except (TypeError, ValueError):
                pass
        return qs.order_by("-payment_date", "-id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        instance = serializer.instance
        headers = self.get_success_headers(serializer.data)
        # T-AUTOPOST: نُعيد الحالة بعد الترحيل التلقائي (is_posted/journal) لا لقطة الإنشاء.
        data = CustomerPaymentSerializer(instance).data
        if getattr(instance, "_auto_post_error", None):
            data["auto_post_error"] = instance._auto_post_error
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

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
        from core.payments import PaymentContext, should_auto_post_payment, validate_payment
        from rest_framework.exceptions import ValidationError as DRFValidationError
        with transaction.atomic():
            payment = serializer.save(tenant=tenant)
            ctx = PaymentContext.from_customer_payment(payment)
            errors = validate_payment(ctx)
            if errors:
                raise DRFValidationError({"payment": errors})
        log_activity(
            action="payment", entity_type="customer_payment", entity_id=payment.id,
            entity_label=getattr(payment, "payment_number", "") or f"#{payment.id}",
            description="سند قبض عميل", request=self.request,
            partner_ids=[payment.partner_id],
        )
        # T-AUTOPOST: السند يُرحَّل فور الحفظ (لا مسودة) ما لم يُطلب خلاف ذلك —
        # نفس عقد فواتير المبيعات: راية auto_post تسمو على إعداد الشركة.
        if should_auto_post_payment(tenant, self.request.data):
            try:
                post_customer_payment(payment, user=self.request.user)
                # post_customer_payment يُعيد ربط اسمه الداخلي بصفّ مقفول، فلا
                # تنعكس is_posted/journal على الكائن الذي سيُسلسَل — نُحدّثه.
                payment.refresh_from_db()
                log_activity(
                    action="post", entity_type="customer_payment", entity_id=payment.id,
                    entity_label=getattr(payment, "payment_number", "") or f"#{payment.id}",
                    description="ترحيل سند قبض عميل", request=self.request,
                    partner_ids=[payment.partner_id],
                )
            except Exception as e:  # noqa: BLE001
                # الفشل لا يُضيع السند — يبقى مسودة وتُعاد الرسالة مع الاستجابة.
                logger.warning("Auto-post customer payment %s failed: %s", payment.id, e)
                payment._auto_post_error = str(e)

    def perform_update(self, serializer):
        payment = serializer.save()
        log_activity(
            action="update", entity_type="customer_payment", entity_id=payment.id,
            entity_label=getattr(payment, "payment_number", "") or f"#{payment.id}",
            description="تعديل سند قبض عميل", request=self.request,
            partner_ids=[payment.partner_id],
        )

    def destroy(self, request, *args, **kwargs):
        payment = self.get_object()
        payment_id, partner_id = payment.id, payment.partner_id
        # T-ARINT: حذف سند مرحّل كان يترك قيوده (دائن ذمم العميل) يتيمة وفواتيره
        # «مدفوعة» بلا تحصيل ⇒ رصيد دائن وهمي. الحذف الآن يتراجع عن الترحيل أولاً.
        if payment.is_posted:
            require_perm(request, "sales.payment.unpost")
            try:
                unpost_customer_payment(payment, user=request.user)
            except ValidationError as e:
                return Response(
                    {"error": "؛ ".join(e.messages)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        response = super().destroy(request, *args, **kwargs)
        log_activity(
            action="delete", entity_type="customer_payment", entity_id=payment_id,
            entity_label=f"#{payment_id}", description="حذف سند قبض عميل",
            request=request, partner_ids=[partner_id],
        )
        return response

    @action(detail=True, methods=["post"], url_path="unpost")
    @requires_perm("sales.payment.unpost")
    def unpost_payment(self, request, pk=None):
        """التراجع عن ترحيل سند قبض: حذف قيوده وإرجاع ما سدّده من الفواتير.

        المخرج الذي تُحيل إليه رسالة منع إلغاء ترحيل فاتورة عليها سند مرحّل.
        """
        payment = self.get_object()
        try:
            result = unpost_customer_payment(payment, user=request.user)
        except ValidationError as e:
            return Response(
                {"error": "؛ ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:  # noqa: BLE001
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        payment.refresh_from_db()
        log_activity(
            action="unpost", entity_type="customer_payment", entity_id=payment.id,
            entity_label=getattr(payment, "payment_number", "") or f"#{payment.id}",
            description="التراجع عن ترحيل سند قبض عميل", request=request,
            partner_ids=[payment.partner_id],
        )
        return Response({**CustomerPaymentSerializer(payment).data, "unpost_result": result})

    @action(detail=True, methods=["post"], url_path="post")
    @requires_perm("sales.payment.post")
    def post_payment(self, request, pk=None):
        payment = self.get_object()
        try:
            post_customer_payment(payment, user=request.user)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        # الخدمة تُعيد ربط اسمها الداخلي بصفّ مقفول — نُحدّث الكائن قبل التسلسل.
        payment.refresh_from_db()
        log_activity(
            action="post", entity_type="customer_payment", entity_id=payment.id,
            entity_label=getattr(payment, "payment_number", "") or f"#{payment.id}",
            description="ترحيل سند قبض عميل", request=request,
            partner_ids=[payment.partner_id],
        )
        return Response(CustomerPaymentSerializer(payment).data)

    @action(detail=True, methods=["post"], url_path="allocate")
    def allocate(self, request, pk=None):
        """T-ONACC: توزيع سند قبض على فواتير — يعمل قبل الترحيل وبعده.

        بعد الترحيل التوزيع ربط فقط (لا قيد جديد): الذمم خُفِّضت وقت الترحيل.
        """
        payment = self.get_object()
        try:
            allocate_customer_payment(
                payment, request.data.get("allocations") or [], user=request.user
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        payment.refresh_from_db()
        log_activity(
            action="update", entity_type="customer_payment", entity_id=payment.id,
            entity_label=getattr(payment, "payment_number", "") or f"#{payment.id}",
            description="توزيع سند قبض على الفواتير", request=request,
            partner_ids=[payment.partner_id],
        )
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
        require_perm(request, "sales.settings.manage", tenant=tenant)
        ser = SalesSettingsSerializer(ss, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    @action(detail=False, methods=["post"], url_path="restore-defaults")
    def restore_defaults(self, request):
        """T-S3: استعادة خريطة القيد الافتراضية — يُعيد الحسابات الافتراضية لكل نوع
        فاتورة إلى أفضل تطابق من شجرة الحسابات (حسب الكود ثم النوع ثم الاسم)."""
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST)
        ss = get_or_create_sales_settings(tenant)
        from sales.services import resolve_default_account

        def resolve(code_prefixes=None, acc_type=None, name_kw=None):
            return resolve_default_account(
                tenant.TenantID, code_prefixes, acc_type, name_kw
            )

        # T-DEFACC: 1103 = المدينون التجاريون و1201 = الأراضي و1106 = دفعات
        # الموردين — لم تكن أيٌّ منها صندوقاً ولا ذمم عملاء. الأكواد الصحيحة:
        # النقدية/البنوك/صناديق النقدية للصندوق، والمدينون التجاريون للذمم.
        ss.default_cash_account = resolve(["1101", "1102", "1110"], "Asset", "صندوق")
        ss.default_ar_account = resolve(["1103"], "Asset", "مدينون")
        ss.default_revenue_account_product = resolve(["4101", "41"], "Revenue", "مبيعات")
        ss.default_revenue_account_service = (
            resolve(["4102"], "Revenue", "خدمات") or ss.default_revenue_account_product
        )
        ss.default_inventory_account = resolve(["1104", "1105"], "Asset", "مخزون")
        ss.default_cogs_account = resolve(["5101", "51"], "Expense", "تكلفة")
        ss.save(update_fields=[
            "default_cash_account", "default_ar_account",
            "default_revenue_account_product", "default_revenue_account_service",
            "default_inventory_account", "default_cogs_account", "updated_at",
        ])
        return Response(SalesSettingsSerializer(ss).data)


class CustomerPriceListViewSet(viewsets.ViewSet):
    """DEF-004: عرض السعر لكل العميل عبر كامل الكتالوج (مبيعات فقط).

    GET  sales/customer-price-list/?customer={id} → كل المنتجات + مصدر السعر.
    PUT  sales/customer-price-list/  {customer, entries:[{product,unit_price}]} → حفظ
    العروض اليدوية. لا أثر محاسبي.
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def list(self, request):
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST)
        cid = request.query_params.get("customer")
        if not cid or not str(cid).isdigit():
            return Response({"error": "باراميتر customer مطلوب."}, status=status.HTTP_400_BAD_REQUEST)
        rows = customer_price_list(tenant_id=tenant.TenantID, customer_id=int(cid))
        return Response(rows)

    @action(detail=False, methods=["put", "post"], url_path="save")
    def save(self, request):
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة (tenant)."}, status=status.HTTP_400_BAD_REQUEST)
        cid = request.data.get("customer")
        if cid in (None, "") or not str(cid).isdigit():
            return Response({"error": "حقل customer مطلوب."}, status=status.HTTP_400_BAD_REQUEST)
        entries = request.data.get("entries") or []
        saved = save_customer_quotes(
            tenant_id=tenant.TenantID, customer_id=int(cid), entries=entries
        )
        return Response({"saved": saved})


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
        # P2-13 (SCALABILITY_AUDIT): كانت الحلقة تجلب **كل** فواتير الآجل
        # المرحّلة منذ نشأة الشركة ثم تُسقط المسدَّدة في بايثون — فالمُهمَل
        # يُنقَل عبر الشبكة كاملاً، وهو الأغلبية في شركة عاملة. الشرط صار في
        # القاعدة، ومدى التاريخ اختياري (from/to) لمن يريد تضييقه.
        from django.utils.dateparse import parse_date

        qs = SalesInvoice.objects.filter(
            tenant_id=tenant.TenantID,
            status=SalesInvoice.STATUS_POSTED,
            invoice_type=SalesInvoice.INVOICE_CREDIT,
        ).annotate(
            _remaining=models.F("grand_total") - models.F("amount_paid"),
        ).filter(_remaining__gt=0)

        date_from = parse_date(request.query_params.get("from") or "")
        date_to = parse_date(request.query_params.get("to") or "")
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)

        rows = []
        for inv in qs.select_related("customer").order_by("invoice_date", "id"):
            remaining = inv.grand_total - inv.amount_paid
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

    @action(detail=False, methods=["get"], url_path="reserved-stock")
    def reserved_stock_report(self, request):
        """T-RESERVEGUARD: «تقرير المحجوزات» — كل بند طلبية مؤكَّدة حجزه ساري.

        نفس مصدر الحارس الذي يمنع بيع الكمية المحجوزة، فلا يختلف ما يُرى عمّا
        يُمنَع. الفلترة الاختيارية: ?product= و?customer= و?from=/?to= (نافذة
        «الحجز حتى»).
        """
        from django.utils.dateparse import parse_date

        from sales.services import reserved_stock_rows

        tenant = get_tenant(request)
        if not tenant:
            return Response([])
        product = request.query_params.get("product")
        customer = request.query_params.get("customer")
        return Response(
            reserved_stock_rows(
                tenant.TenantID,
                product_id=int(product) if product and str(product).isdigit() else None,
                customer_id=int(customer) if customer and str(customer).isdigit() else None,
                date_from=parse_date(request.query_params.get("from") or ""),
                date_to=parse_date(request.query_params.get("to") or ""),
            )
        )

    @action(detail=False, methods=["get"], url_path="dormant-customers")
    def dormant_customers_report(self, request):
        """T-DORMANT: عملاء توقّفوا عن الشراء منذ عتبة الإعدادات — يستهلكها مولّد
        إشعارات الموقع. العتبة من `dormant_customer_days` ويمكن تجاوزها بـ ?days=."""
        from sales.services import dormant_customers

        tenant = get_tenant(request)
        if not tenant:
            return Response([])
        days = request.query_params.get("days")
        return Response(
            dormant_customers(
                tenant_id=tenant.TenantID,
                days=int(days) if days and str(days).isdigit() else None,
            )
        )


class SalesQuotationViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    queryset = SalesQuotation.objects.all().select_related(
        "customer", "currency", "tenant",
    )
    serializer_class = SalesQuotationSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return SalesQuotationListSerializer
        return SalesQuotationSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_tenant(self.request)
        if not tenant:
            return qs.none()
        qs = qs.filter(tenant_id=tenant.TenantID)
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        customer = self.request.query_params.get("customer")
        if customer:
            qs = qs.filter(customer_id=customer)
        date_from = self.request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(quotation_date__gte=date_from)
        date_to = self.request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(quotation_date__lte=date_to)
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                models.Q(quotation_number__icontains=search)
                | models.Q(customer__name__icontains=search)
                | models.Q(customer__legal_name__icontains=search)
            )
        # قائمة العروض تستخدم serializer خفيفاً ولا تحتاج البنود. التفاصيل فقط
        # تجلب المنتج مع السطر كي يبقى product_name بلا N+1.
        if self.action != "list":
            qs = qs.prefetch_related("lines__product")
        return qs.order_by("-quotation_date", "-id")

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة لهذا الطلب."})
        serializer.save(tenant=tenant, created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        """T-ORDERS: الحذف خلف إعداد الشركة — «إلغاء» هو المسار الافتراضي."""
        quotation = self.get_object()
        if not document_delete_allowed(quotation.tenant_id):
            return Response(
                {"detail": "حذف العروض معطَّل لهذه الشركة — استخدم «إلغاء» (لا يحذف المستند)."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="convert")
    def convert(self, request, pk=None):
        """تحويل العرض — `target=invoice` (افتراضي) أو `target=order` (طلبية)."""
        quotation = self.get_object()
        target = (request.data.get("target") or "invoice").strip()
        try:
            if target == "order":
                order = convert_quotation_to_order(quotation, user=request.user)
                log_activity(
                    action="convert", entity_type="sales_quotation", entity_id=quotation.id,
                    entity_label=quotation.quotation_number,
                    description=f"تحويل عرض إلى طلبية {order.order_number}",
                    request=request, partner_ids=[quotation.customer_id],
                )
                return Response({
                    "status": "تم تحويل العرض إلى طلبية.",
                    "target": "order",
                    "order": SalesOrderSerializer(order).data,
                })
            invoice = convert_quotation_to_invoice(quotation, user=request.user)
            log_activity(
                action="convert", entity_type="sales_quotation", entity_id=quotation.id,
                entity_label=quotation.quotation_number,
                description=f"تحويل عرض إلى فاتورة {invoice.invoice_number}",
                request=request, partner_ids=[quotation.customer_id],
            )
            return Response({
                "status": "تم تحويل العرض إلى فاتورة.",
                "target": "invoice",
                "invoice": SalesInvoiceSerializer(invoice).data,
            })
        except (ValueError, ValidationError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """إلغاء العرض — بديل الحذف، يُبقي المستند وسجلّه."""
        quotation = self.get_object()
        try:
            cancel_quotation(
                quotation, user=request.user, reason=request.data.get("reason") or "")
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        quotation.refresh_from_db()
        return Response(SalesQuotationSerializer(quotation).data)


class SalesOrderViewSet(viewsets.ModelViewSet):
    """طلبيات الزبائن (T-ORDERS) — إنشاء مباشر أو من عرض سعر.

    الطلبية تحجز الكمية حتى `reserved_until` (إعداد الشركة)، وتقبل عربوناً
    (سند قبض مرحَّل مربوط بها)، وتُلغى بلا حذف. لا قيد يومية لها.
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    # `invoice` ضمن الـselect_related: رقم الفاتورة الناتجة يُعرض في كل صف من
    # قائمة الطلبيات (رابط فتحها)، فبدونه استعلام لكل صف.
    queryset = SalesOrder.objects.all().select_related(
        "customer", "currency", "tenant", "invoice")
    serializer_class = SalesOrderSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_tenant(self.request)
        if not tenant:
            return qs.none()
        qs = qs.filter(tenant_id=tenant.TenantID)
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("customer"):
            qs = qs.filter(customer_id=params["customer"])
        if params.get("date_from"):
            qs = qs.filter(order_date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(order_date__lte=params["date_to"])
        search = params.get("search", "").strip()
        if search:
            qs = qs.filter(
                models.Q(order_number__icontains=search)
                | models.Q(customer__name__icontains=search)
            )
        return qs.prefetch_related("lines__product").order_by("-order_date", "-id")

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة لهذا الطلب."})
        order = serializer.save(tenant=tenant, created_by=self.request.user)
        log_order_activity(order, action="create", description="إنشاء طلبية", user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        order = self.get_object()
        if not document_delete_allowed(order.tenant_id):
            return Response(
                {"detail": "حذف الطلبيات معطَّل لهذه الشركة — استخدم «إلغاء» (لا يحذف المستند)."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if order.status != SalesOrder.STATUS_DRAFT or order.deposits.exists():
            return Response(
                {"detail": "لا يمكن حذف طلبية مؤكدة أو مرتبطة بحركة؛ استخدم «إلغاء»."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_order_activity(order, action="delete", description="حذف طلبية", user=request.user)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        """تأكيد الطلبية — يبدأ الحجز حتى `reserved_until`."""
        order = self.get_object()
        try:
            order = confirm_sales_order(order, user=request.user)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SalesOrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        order = self.get_object()
        try:
            cancel_sales_order(
                order, user=request.user, reason=request.data.get("reason") or "")
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        order.refresh_from_db()
        return Response(SalesOrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="convert")
    def convert(self, request, pk=None):
        """تحويل الطلبية إلى فاتورة بيع (مسودة) — ينهي الحجز."""
        order = self.get_object()
        try:
            invoice = convert_order_to_invoice(order, user=request.user)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "status": "تم تحويل الطلبية إلى فاتورة.",
            "invoice": SalesInvoiceSerializer(invoice).data,
        })

    @action(detail=True, methods=["post"], url_path="deposit")
    def deposit(self, request, pk=None):
        """تسجيل عربون — سند قبض مرحَّل «على الحساب» مربوط بالطلبية."""
        order = self.get_object()
        try:
            record_order_deposit(
                order,
                amount=request.data.get("amount"),
                cash_account_id=request.data.get("cash_or_bank_account"),
                user=request.user,
                payment_date=request.data.get("payment_date") or None,
            )
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        order.refresh_from_db()
        return Response(SalesOrderSerializer(order).data)


class CreditDebitNoteViewSet(viewsets.ModelViewSet):
    """M4-T4 — Credit / Debit notes (إشعارات مدينة/دائنة)."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = CreditDebitNoteSerializer

    def get_queryset(self):
        # P1-7 (المرحلة 5): .none() عند غياب الشركة بدل إشعارات كل الشركات.
        tenant = get_tenant(self.request)
        if not tenant:
            return CreditDebitNote.objects.none()
        return CreditDebitNote.objects.select_related(
            "customer", "related_invoice", "journal"
        ).filter(tenant=tenant).order_by("-note_date", "-id")

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
