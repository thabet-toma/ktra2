"""API بطاقات الكفالة (THA-24 م1).

ترتيب البوابتين مقصود: `require_module` **قبل** `require_perm`، فترد الشركة غير
المرخّصة **404 لا 403** — 403 يُثبت وجود الوحدة، و404 لا يُثبت شيئاً. وكل
استعلام مقيّد بالشركة النشطة القادمة من الحارس نفسه، لا من جسم الطلب.
"""
import logging
from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.access import require_perm
from core.api_defaults import ApiAuthAndUser
from core.modules import require_module

from .models import WarrantyCard
from .serializers import WarrantyCardSerializer, WarrantyExtendSerializer
from .services import MODULE_KEY, warranty_coverage

logger = logging.getLogger(__name__)

PERM_VIEW = "aftersales.warranty.view"
PERM_MANAGE = "aftersales.warranty.manage"

_ACTION_PERMS = {
    "list": PERM_VIEW,
    "retrieve": PERM_VIEW,
    "check": PERM_VIEW,
    "create": PERM_MANAGE,
    "update": PERM_MANAGE,
    "partial_update": PERM_MANAGE,
    "destroy": PERM_MANAGE,
    "extend": PERM_MANAGE,
}

# ما يُسمح بتعديله يدوياً على بطاقة **تلقائية**: البطاقة من إنتاج الترحيل،
# فتعديل نسبها باليد يجعلها تكذب على فاتورتها. التمديد والملاحظات وحدهما قرار
# بشري مشروع فوقها.
_AUTO_CARD_EDITABLE = {"end_date", "notes", "supplier_warranty_end_date"}


class WarrantyCardViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = WarrantyCardSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        required = _ACTION_PERMS.get(self.action)
        if required:
            require_perm(request, required, tenant=self.tenant)

    # ── الاستعلام ─────────────────────────────────────────────────────────
    def get_queryset(self):
        queryset = (
            WarrantyCard.objects
            .filter(tenant=self.tenant)
            .select_related("product", "partner", "supplier", "sales_invoice_line__invoice")
        )
        if self.action != "list":
            return queryset

        params = self.request.query_params
        term = (params.get("q") or "").strip()
        if term:
            queryset = queryset.filter(
                Q(serial__icontains=term)
                | Q(device_name__icontains=term)
                | Q(customer_name__icontains=term)
                | Q(customer_phone__icontains=term)
                | Q(partner__name__icontains=term)
                | Q(product__name_ar__icontains=term)
                | Q(product__name_en__icontains=term)
                | Q(product__sku__icontains=term)
            )

        status_filter = (params.get("status") or "").strip()
        if status_filter in ("active", "expired"):
            today = timezone.localdate()
            queryset = (
                queryset.filter(end_date__gte=today)
                if status_filter == "active"
                else queryset.filter(end_date__lt=today)
            )

        source = (params.get("source") or "").strip()
        if source:
            queryset = queryset.filter(source=source)

        product_id = (params.get("product") or "").strip()
        if product_id.isdigit():
            queryset = queryset.filter(product_id=int(product_id))

        partner_id = (params.get("partner") or "").strip()
        if partner_id.isdigit():
            queryset = queryset.filter(partner_id=int(partner_id))

        expiring = (params.get("expiring_within_days") or "").strip()
        if expiring.isdigit():
            today = timezone.localdate()
            queryset = queryset.filter(
                end_date__gte=today,
                end_date__lte=today + timedelta(days=int(expiring)),
            )
        return queryset

    # ── الكتابة ───────────────────────────────────────────────────────────
    def _validate_tenant_links(self, serializer):
        """كل مرجع في الجسم يجب أن يتبع الشركة النشطة — لا عبور بين الشركات."""
        for field in ("product", "partner", "supplier"):
            obj = serializer.validated_data.get(field)
            if obj is not None and obj.tenant_id != self.tenant.pk:
                raise ValidationError({field: "هذا السجل لا يتبع الشركة النشطة."})

    def perform_create(self, serializer):
        self._validate_tenant_links(serializer)
        # كل ما يُنشأ من الـAPI يدويٌّ بحكم التعريف — التلقائي من الترحيل وحده.
        serializer.save(
            tenant=self.tenant,
            source=WarrantyCard.SOURCE_MANUAL,
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        card = serializer.instance
        if card.source == WarrantyCard.SOURCE_AUTO_SALE:
            touched = set(serializer.validated_data) - _AUTO_CARD_EDITABLE
            # `duration_months` و`end_date` يمرّان معاً من التحقق دائماً؛ المدة
            # وحدها بلا تغيّر فعلي ليست تعديلاً.
            if "duration_months" in touched and (
                serializer.validated_data["duration_months"] == card.duration_months
            ):
                touched.discard("duration_months")
            if touched:
                raise ValidationError({
                    "detail": (
                        "هذه بطاقة تلقائية من ترحيل فاتورة — يُعدَّل عليها تاريخ "
                        "الانتهاء والملاحظات فقط. للباقي: تراجع عن ترحيل الفاتورة."
                    )
                })
        self._validate_tenant_links(serializer)
        serializer.save()

    def perform_destroy(self, instance):
        if instance.source == WarrantyCard.SOURCE_AUTO_SALE:
            raise ValidationError({
                "detail": (
                    "بطاقة تلقائية لا تُحذف مباشرة — تُحذف مع التراجع عن ترحيل "
                    "فاتورتها وتعود بإعادة الترحيل."
                )
            })
        instance.delete()

    # ── الإجراءات ─────────────────────────────────────────────────────────
    @action(detail=True, methods=["post"], url_path="extend")
    def extend(self, request, pk=None):
        """تمديد الكفالة مجاملةً — يُوثَّق في الملاحظات بتاريخ الخادم."""
        card = self.get_object()
        form = WarrantyExtendSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        new_end = form.resolved_end_date(card)
        if new_end < card.start_date:
            raise ValidationError({"end_date": "التاريخ الجديد قبل بدء الكفالة."})

        previous = card.end_date
        reason = (form.validated_data.get("reason") or "").strip()
        stamp = timezone.localtime().strftime("%Y-%m-%d %H:%M")
        line = f"[{stamp}] تمديد الكفالة من {previous} إلى {new_end}"
        if reason:
            line = f"{line} — {reason}"
        card.end_date = new_end
        card.notes = f"{card.notes}\n{line}".strip() if card.notes else line
        card.save(update_fields=["end_date", "notes", "updated_at"])
        logger.info(
            "after_sales.warranty_extended tenant=%s card=%s %s→%s",
            self.tenant.pk, card.pk, previous, new_end,
        )
        return Response(self.get_serializer(card).data)

    @action(detail=False, methods=["get"], url_path="check")
    def check(self, request):
        """«هل هذه الوحدة تحت الكفالة؟» — جوابٌ واحد من البطاقة ومن نسب الوحدة."""
        return Response(
            warranty_coverage(self.tenant.pk, request.query_params.get("serial") or "")
        )
