"""API ما بعد البيع — بطاقات الكفالة (م1) وأوامر الصيانة (م3).

ترتيب البوابتين مقصود: `require_module` **قبل** `require_perm`، فترد الشركة غير
المرخّصة **404 لا 403** — 403 يُثبت وجود الوحدة، و404 لا يُثبت شيئاً. وكل
استعلام مقيّد بالشركة النشطة القادمة من الحارس نفسه، لا من جسم الطلب.
"""
import logging
from datetime import date, timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.access import require_perm, user_has_perm
from core.api_defaults import ApiAuthAndUser
from core.modules import require_module

from .models import (
    ManufacturerWarrantor,
    ServiceOrder,
    ServiceOrderPart,
    WarrantyCard,
    WarrantyCardEvent,
    WarrantyPolicy,
)
from .serializers import (
    AfterSalesSettingsSerializer,
    GenerateServiceInvoiceSerializer,
    ManufacturerWarrantorSerializer,
    ServiceOrderEventSerializer,
    ServiceOrderListSerializer,
    ServiceOrderNoteSerializer,
    ServiceOrderPartSerializer,
    ServiceOrderSerializer,
    ServiceOrderTransitionSerializer,
    WarrantyCardEventSerializer,
    WarrantyCardSerializer,
    WarrantyExtendSerializer,
    WarrantyPolicyBulkSerializer,
    WarrantyPolicySerializer,
)
from .services import (
    MODULE_KEY,
    get_or_create_after_sales_settings,
    log_warranty_event,
    warranty_coverage,
)

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
    "events": PERM_VIEW,
}

# ما يُسمح بتعديله يدوياً على بطاقة **تلقائية**: البطاقة من إنتاج الترحيل،
# فتعديل نسبها باليد يجعلها تكذب على فاتورتها. التمديد والملاحظات وحدهما قرار
# بشري مشروع فوقها. و#232: بداية كفالة المصنع كذلك — بعض المصنّعين يحسبون من
# التفعيل لا البيع؛ ونهايتها معها لأنها مشتقّةٌ منها دائماً في `validate()`
# ولا يملك العميل قيمةً مستقلة لها أصلاً.
_AUTO_CARD_EDITABLE = {
    "end_date", "notes", "supplier_warranty_end_date",
    "manufacturer_start_date", "manufacturer_end_date",
}


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
            .select_related(
                "product", "partner", "supplier", "sales_invoice",
                "sales_invoice_line__invoice",
            )
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

        # #222/#229: «المنتهية بواقعة» ليست سارية ولا «انتهت مدّتها» — فئةٌ
        # ثالثة، و`WarrantyCardQuerySet` هو من يحسم الثلاثة — لا مقارنة
        # `end_date` حرّة هنا.
        status_filter = (params.get("status") or "").strip()
        if status_filter in ("active", "expired", "ended"):
            today = timezone.localdate()
            if status_filter == "ended":
                queryset = queryset.ended()
            elif status_filter == "active":
                queryset = queryset.active_on(today)
            else:
                queryset = queryset.expired_on(today)

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
            queryset = queryset.active_on(today).filter(
                end_date__lte=today + timedelta(days=int(expiring)),
            )
        return queryset

    # ── الكتابة ───────────────────────────────────────────────────────────
    def _validate_tenant_links(self, serializer):
        """كل مرجع في الجسم يجب أن يتبع الشركة النشطة — لا عبور بين الشركات."""
        for field in ("product", "partner", "supplier", "manufacturer_warrantor"):
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
            # #232: `manufacturer_warrantor`/`manufacturer_duration_months` يمرّان
            # معاً من `validate()` أيضاً — مجمَّدان على البطاقة التلقائية، فبلا
            # تغيّرٍ فعلي ليسا تعديلاً (تعديل `manufacturer_start_date` وحده
            # يُعيد اشتقاق `manufacturer_end_date` المعفى أصلاً في `_AUTO_CARD_EDITABLE`).
            if "manufacturer_duration_months" in touched and (
                serializer.validated_data["manufacturer_duration_months"]
                == card.manufacturer_duration_months
            ):
                touched.discard("manufacturer_duration_months")
            if "manufacturer_warrantor" in touched:
                new_warrantor = serializer.validated_data["manufacturer_warrantor"]
                new_warrantor_id = new_warrantor.pk if new_warrantor is not None else None
                if new_warrantor_id == card.manufacturer_warrantor_id:
                    touched.discard("manufacturer_warrantor")
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
        # `card` على `WarrantyCardEvent` بـPROTECT — الحذف كان سيرتدّ 500 دون
        # هذا الفحص؛ هنا الرسالة تُقرأ (#229).
        if instance.events.exists():
            raise ValidationError({
                "detail": "على هذه البطاقة أحداث مسجّلة (مثل تمديد) — لا تُحذف.",
            })
        instance.delete()

    # ── الإجراءات ─────────────────────────────────────────────────────────
    @action(detail=True, methods=["post"], url_path="extend")
    def extend(self, request, pk=None):
        """تمديد الكفالة مجاملةً — يُسجَّل حدث `extend` لا سطراً في الملاحظات (#229).

        شرطان (#222 البند ٨): البطاقة ليست منتهيةً بواقعة، والتاريخ الجديد
        **بعد** الحالي — يفرض الثاني `WarrantyExtendSerializer.resolved_end_date`.
        """
        card = self.get_object()
        if card.ended_on is not None:
            raise ValidationError({
                "detail": (
                    f"البطاقة منتهية ({card.get_end_reason_display()}) بتاريخ "
                    f"{card.ended_on} — لا تُمدَّد. تراجع عمّا أنهاها أولاً."
                )
            })
        form = WarrantyExtendSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        new_end = form.resolved_end_date(card)

        previous = card.end_date
        reason = (form.validated_data.get("reason") or "").strip()
        card.end_date = new_end
        card.save(update_fields=["end_date", "updated_at"])
        log_warranty_event(
            card,
            event_type=WarrantyCardEvent.TYPE_EXTEND,
            reason_code=WarrantyCardEvent.EXTEND_REASON_COURTESY,
            text=reason,
            user=request.user,
            old_end_date=previous,
            new_end_date=new_end,
        )
        logger.info(
            "after_sales.warranty_extended tenant=%s card=%s %s→%s",
            self.tenant.pk, card.pk, previous, new_end,
        )
        return Response(self.get_serializer(card).data)

    @action(detail=True, methods=["get"], url_path="events")
    def events(self, request, pk=None):
        """سجل أحداث البطاقة — إلحاقي، للقراءة فقط. لا PATCH ولا DELETE عليه."""
        card = self.get_object()
        queryset = (
            WarrantyCardEvent.objects
            .filter(tenant=self.tenant, card=card)
            .select_related("actor", "service_order")
        )
        return Response(WarrantyCardEventSerializer(queryset, many=True).data)

    @action(detail=False, methods=["get"], url_path="check")
    def check(self, request):
        """«هل هذه الوحدة تحت الكفالة؟» — جوابٌ واحد من البطاقة ومن نسب الوحدة."""
        return Response(
            warranty_coverage(self.tenant.pk, request.query_params.get("serial") or "")
        )


# ══════════════════════════════════════════════════════════════════════════
# جهات كفالة المصنع وإعدادات الوحدة (#230)
# ══════════════════════════════════════════════════════════════════════════

PERM_SETTINGS_MANAGE = "aftersales.settings.manage"
PURCHASE_INVOICE_EDIT_PERM = "purchase.invoice.edit"


class ManufacturerWarrantorViewSet(viewsets.ModelViewSet):
    """جهات كفالة المصنع — إدارتها الكاملة خلف `aftersales.settings.manage`.

    `lookup/` وحدها أوسع: يقرأها من يحرّر فواتير الشراء (`purchase.invoice.edit`)
    أيضاً — تغذّي منتقي كفالة المصنع على بند الشراء لاحقاً (#235).
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = ManufacturerWarrantorSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        if self.action == "lookup":
            if not user_has_perm(request.user, self.tenant, PURCHASE_INVOICE_EDIT_PERM):
                require_perm(request, PERM_VIEW, tenant=self.tenant)
        else:
            require_perm(request, PERM_SETTINGS_MANAGE, tenant=self.tenant)

    def get_queryset(self):
        return ManufacturerWarrantor.objects.filter(tenant=self.tenant)

    def _reject_duplicate_name(self, name: str, *, exclude_pk=None):
        name = name.strip()
        queryset = ManufacturerWarrantor.objects.filter(tenant=self.tenant, name=name)
        if exclude_pk is not None:
            queryset = queryset.exclude(pk=exclude_pk)
        if queryset.exists():
            raise ValidationError({"name": f"توجد جهة بهذا الاسم «{name}» مسبقاً."})

    def perform_create(self, serializer):
        self._reject_duplicate_name(serializer.validated_data["name"])
        serializer.save(tenant=self.tenant)

    def perform_update(self, serializer):
        name = serializer.validated_data.get("name")
        if name is not None:
            self._reject_duplicate_name(name, exclude_pk=serializer.instance.pk)
        serializer.save()

    def perform_destroy(self, instance):
        # لا حذف لجهة مرتبطة (#230): كل من يشير إليها لاحقاً يفعل ذلك بـPROTECT
        # (السياسة #231، بند الشراء #235، البطاقة #232) — لا شيء يشير إليها
        # اليوم، لكن الفحص عامٌّ فلا تحتاج تذكرةٌ لاحقة لمسّه.
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError({
                "detail": "هذه الجهة مرتبطة بسجلات أخرى — أرشفها (أوقف تفعيلها) بدل حذفها.",
            })

    @action(detail=False, methods=["get"], url_path="lookup")
    def lookup(self, request):
        """قائمة القراءة للمنتقي — الجهات المفعَّلة وحدها."""
        queryset = (
            ManufacturerWarrantor.objects
            .filter(tenant=self.tenant, is_active=True)
            .order_by("name")
        )
        return Response(ManufacturerWarrantorSerializer(queryset, many=True).data)


class WarrantyPolicyViewSet(viewsets.ModelViewSet):
    """سياسات الكفالة — صفٌّ لكل براند (#231).

    القراءة خلف `aftersales.warranty.view` (نفس بوابة بطاقات الكفالة — كرت
    المنتج يعرض منها سطراً للقراءة)، والكتابة (بما فيها `bulk/`) خلف
    `aftersales.settings.manage` وحدها: السياسة تغيّر وعد الزبون وتفرض إدخالاً
    على الكاشير، فلا تُترك لموظف مبيعات عابر.
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = WarrantyPolicySerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        if self.action in ("list", "retrieve"):
            require_perm(request, PERM_VIEW, tenant=self.tenant)
        else:
            require_perm(request, PERM_SETTINGS_MANAGE, tenant=self.tenant)

    def get_queryset(self):
        queryset = (
            WarrantyPolicy.objects
            .filter(tenant=self.tenant)
            .select_related("product", "manufacturer_warrantor")
        )
        if self.action != "list":
            return queryset

        params = self.request.query_params
        product_id = (params.get("product") or "").strip()
        if product_id.isdigit():
            queryset = queryset.filter(product_id=int(product_id))
        family_id = (params.get("family") or "").strip()
        if family_id.isdigit():
            queryset = queryset.filter(product__family_id=int(family_id))
        category_id = (params.get("category") or "").strip()
        if category_id.isdigit():
            from inventory.services import category_descendant_product_ids
            queryset = queryset.filter(product_id__in=category_descendant_product_ids(
                tenant_id=self.tenant.pk, category_id=int(category_id),
            ))
        return queryset

    def _validate_tenant_links(self, serializer):
        for field in ("product", "manufacturer_warrantor"):
            obj = serializer.validated_data.get(field)
            if obj is not None and obj.tenant_id != self.tenant.pk:
                raise ValidationError({field: "هذا السجل لا يتبع الشركة النشطة."})

    def perform_create(self, serializer):
        self._validate_tenant_links(serializer)
        serializer.save(tenant=self.tenant)

    def perform_update(self, serializer):
        self._validate_tenant_links(serializer)
        serializer.save()

    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk(self, request):
        """تطبيق سياسةٍ واحدة على كل براندات منتجٍ أب أو تصنيف — صفٌّ لكل براند.

        كلّ أم لا شيء: أيّ براندٍ يرفضه التحقّق (منتج خدمة تحت `method=serial`،
        أو طبقاتٌ كلّها صفر) يُسقط الجماعة كلّها بـ400 يسمّيه — لا كتابة جزئية
        صامتة يكتشفها المدير لاحقاً براندًا براندًا.
        """
        from inventory.models import Product

        form = WarrantyPolicyBulkSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

        family_id = data.get("family")
        if family_id:
            product_ids = list(
                Product.objects.filter(tenant=self.tenant, family_id=family_id)
                .values_list("id", flat=True)
            )
        else:
            from inventory.services import category_descendant_product_ids
            product_ids = category_descendant_product_ids(
                tenant_id=self.tenant.pk, category_id=data["category"],
            )
        if not product_ids:
            raise ValidationError({"detail": "لا براندات لهذا المحدِّد."})

        warrantor_id = data.get("manufacturer_warrantor")
        if warrantor_id and not ManufacturerWarrantor.objects.filter(
            tenant=self.tenant, pk=warrantor_id,
        ).exists():
            raise ValidationError({
                "manufacturer_warrantor": "هذا السجل لا يتبع الشركة النشطة.",
            })

        base_fields = {
            "method": data["method"],
            "dealer_months": data.get("dealer_months", 0),
            "manufacturer_warrantor": warrantor_id,
            "manufacturer_months": data.get("manufacturer_months", 0),
            "supplier_months": data.get("supplier_months", 0),
            "terms_override": data.get("terms_override", ""),
        }
        existing = {
            policy.product_id: policy
            for policy in WarrantyPolicy.objects.filter(
                tenant=self.tenant, product_id__in=product_ids,
            )
        }

        saved = []
        with transaction.atomic():
            for product_id in product_ids:
                row_data = dict(base_fields, product=product_id)
                serializer = WarrantyPolicySerializer(
                    instance=existing.get(product_id), data=row_data,
                )
                serializer.is_valid(raise_exception=True)
                saved.append(serializer.save(tenant=self.tenant))

        return Response({
            "applied": len(saved),
            "policies": WarrantyPolicySerializer(saved, many=True).data,
        })


class AfterSalesSettingsView(APIView):
    """صفٌّ واحد لكل شركة — `GET` يقرأه كل من يملك الوحدة، و`PATCH` خلف
    `aftersales.settings.manage` وحدها (على نمط `SalesSettingsViewSet.current`)."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def get(self, request):
        tenant = require_module(request, MODULE_KEY)
        settings_row = get_or_create_after_sales_settings(tenant.pk)
        return Response(AfterSalesSettingsSerializer(settings_row).data)

    def patch(self, request):
        tenant = require_module(request, MODULE_KEY)
        require_perm(request, PERM_SETTINGS_MANAGE, tenant=tenant)
        settings_row = get_or_create_after_sales_settings(tenant.pk)
        serializer = AfterSalesSettingsSerializer(settings_row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ══════════════════════════════════════════════════════════════════════════
# أمر الصيانة (م3)
# ══════════════════════════════════════════════════════════════════════════

ORDER_PERM_VIEW = "aftersales.order.view"
ORDER_PERM_CREATE = "aftersales.order.create"
ORDER_PERM_EDIT = "aftersales.order.edit"
ORDER_PERM_POST = "aftersales.order.post"
ORDER_PERM_UNPOST = "aftersales.order.unpost"

_ORDER_ACTION_PERMS = {
    "list": ORDER_PERM_VIEW,
    "retrieve": ORDER_PERM_VIEW,
    "lookup": ORDER_PERM_VIEW,
    "create": ORDER_PERM_CREATE,
    "update": ORDER_PERM_EDIT,
    "partial_update": ORDER_PERM_EDIT,
    "transition": ORDER_PERM_EDIT,
    "add_note": ORDER_PERM_EDIT,
    "approve": ORDER_PERM_EDIT,
    "add_part": ORDER_PERM_EDIT,
    "part_detail": ORDER_PERM_EDIT,
    # المال: الترحيل والفوترة للمحاسب، والتراجع بصلاحيته المستقلة.
    "post_covered": ORDER_PERM_POST,
    "generate_invoice": ORDER_PERM_POST,
    "detach_invoice": ORDER_PERM_POST,
    "unpost_covered": ORDER_PERM_UNPOST,
}


def _reraise_as_drf(error: DjangoValidationError):
    """رسائل الخدمات تُكتب لتُقرأ — ننقلها كما هي بدل «حدث خطأ»."""
    detail = getattr(error, "message_dict", None) or getattr(error, "messages", None)
    raise ValidationError(detail or str(error))


class ServiceOrderViewSet(viewsets.ModelViewSet):
    """أمر الصيانة — الملف الذي يوثّق كل شيء من الشكوى حتى الحل.

    الحالة لا تنتقل بـPATCH: `transition` وحدها تمرّ من البوابات (لا تسليم وقطعٌ
    مغطاة غير مرحّلة، ولا إلغاء وفي الأمر ترحيلٌ قائم). و**لا حذف** — الإلغاء
    بديل الحذف كما في طلبيات الزبائن، فسجلّ الجهاز لا يختفي من التاريخ.
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = ServiceOrderSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        required = _ORDER_ACTION_PERMS.get(self.action)
        if required:
            require_perm(request, required, tenant=self.tenant)

    def get_serializer_class(self):
        if self.action == "list":
            return ServiceOrderListSerializer
        return ServiceOrderSerializer

    # ── الاستعلام ─────────────────────────────────────────────────────────
    def get_queryset(self):
        queryset = ServiceOrder.objects.filter(tenant=self.tenant).select_related(
            "partner", "product", "technician", "warranty_card", "sales_invoice",
        )
        if self.action != "list":
            return queryset.prefetch_related("parts__product", "events__actor")

        params = self.request.query_params
        term = (params.get("q") or "").strip()
        if term:
            queryset = queryset.filter(
                Q(order_number__icontains=term)
                | Q(serial__icontains=term)
                | Q(customer_name__icontains=term)
                | Q(customer_phone__icontains=term)
                | Q(partner__name__icontains=term)
                | Q(device_description__icontains=term)
                | Q(complaint__icontains=term)
            )

        status_filter = (params.get("status") or "").strip()
        if status_filter:
            queryset = queryset.filter(status__in=status_filter.split(","))

        if (params.get("open") or "").strip() in ("1", "true"):
            queryset = queryset.exclude(
                status__in=[ServiceOrder.STATUS_DELIVERED, ServiceOrder.STATUS_CANCELLED],
            )

        covered = (params.get("warranty_covered") or "").strip()
        if covered in ("1", "true"):
            queryset = queryset.filter(warranty_covered=True)
        elif covered in ("0", "false"):
            queryset = queryset.filter(warranty_covered=False)

        partner_id = (params.get("partner") or "").strip()
        if partner_id.isdigit():
            queryset = queryset.filter(partner_id=int(partner_id))

        date_from = (params.get("date_from") or "").strip()
        if date_from:
            queryset = queryset.filter(order_date__gte=date_from)
        date_to = (params.get("date_to") or "").strip()
        if date_to:
            queryset = queryset.filter(order_date__lte=date_to)
        return queryset

    # ── الكتابة ───────────────────────────────────────────────────────────
    def _validate_tenant_links(self, serializer):
        for field in ("partner", "product", "warranty_card"):
            obj = serializer.validated_data.get(field)
            if obj is not None and obj.tenant_id != self.tenant.pk:
                raise ValidationError({field: "هذا السجل لا يتبع الشركة النشطة."})

    def perform_create(self, serializer):
        from .service_orders import log_event, next_service_order_number

        self._validate_tenant_links(serializer)
        order = serializer.save(
            tenant=self.tenant,
            order_number=next_service_order_number(self.tenant.pk),
            created_by=self.request.user,
        )
        log_event(
            order,
            text=(
                f"استُلم الجهاز — {order.serial or order.device_description or 'بلا معرّف'}"
                + (f" — الشكوى: {order.complaint[:200]}" if order.complaint else "")
            ),
            to_status=order.status,
            user=self.request.user,
        )

    def perform_update(self, serializer):
        order = serializer.instance
        if order.status in (ServiceOrder.STATUS_DELIVERED, ServiceOrder.STATUS_CANCELLED):
            raise ValidationError({
                "detail": (
                    f"الأمر في حالة «{order.get_status_display()}» النهائية — لا يُعدَّل بعدها."
                )
            })
        self._validate_tenant_links(serializer)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        raise ValidationError({
            "detail": (
                "أوامر الصيانة لا تُحذف — ألغِ الأمر بدل ذلك ليبقى سجلّ الجهاز في التاريخ."
            )
        })

    # ── الحالة والأحداث ───────────────────────────────────────────────────
    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        from .service_orders import transition_status

        order = self.get_object()
        form = ServiceOrderTransitionSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        try:
            transition_status(
                order,
                form.validated_data["to_status"],
                user=request.user,
                outcome=form.validated_data.get("outcome") or "",
                note=form.validated_data.get("note") or "",
            )
        except DjangoValidationError as error:
            _reraise_as_drf(error)
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="note")
    def add_note(self, request, pk=None):
        from .service_orders import log_event

        order = self.get_object()
        form = ServiceOrderNoteSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        event = log_event(order, text=form.validated_data["text"], user=request.user)
        return Response(
            ServiceOrderEventSerializer(event).data, status=http_status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        from .service_orders import record_approval

        order = self.get_object()
        try:
            record_approval(
                order, user=request.user, note=(request.data.get("note") or "").strip(),
            )
        except DjangoValidationError as error:
            _reraise_as_drf(error)
        return Response(self.get_serializer(self.get_object()).data)

    # ── قطع الغيار ────────────────────────────────────────────────────────
    def _editable_order(self):
        order = self.get_object()
        if order.status in (ServiceOrder.STATUS_DELIVERED, ServiceOrder.STATUS_CANCELLED):
            raise ValidationError({
                "detail": f"الأمر في حالة «{order.get_status_display()}» — لا تُعدَّل قطعه."
            })
        return order

    @action(detail=True, methods=["post"], url_path="parts")
    def add_part(self, request, pk=None):
        order = self._editable_order()
        form = ServiceOrderPartSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        product = form.validated_data["product"]
        if product.tenant_id != self.tenant.pk:
            raise ValidationError({"product": "هذا المنتج لا يتبع الشركة النشطة."})
        # الخام آمنٌ الآن: `form.is_valid()` أعلاه مرّ بـ`validate_billing`
        # (THA-223) فرفض قيمةً خارج `BILLING_CHOICES` قبل هذا السطر — قيمة
        # عشوائية كانت تُسقط القطعة من كل المسارات ولا تمنع التسليم. الافتراض
        # يتبع قرار التغطية على الأمر حين لا تُرسَل أصلاً.
        billing = request.data.get("billing") or (
            ServiceOrderPart.BILLING_COVERED if order.warranty_covered
            else ServiceOrderPart.BILLING_BILLABLE
        )
        part = form.save(order=order, billing=billing)
        self._log_part(order, part, "أُضيفت")
        return Response(
            ServiceOrderPartSerializer(part).data, status=http_status.HTTP_201_CREATED,
        )

    @action(
        detail=True, methods=["patch", "delete"],
        url_path=r"parts/(?P<part_id>[^/.]+)",
    )
    def part_detail(self, request, pk=None, part_id=None):
        order = self._editable_order()
        part = order.parts.filter(pk=part_id).select_related("product").first()
        if part is None:
            raise ValidationError({"detail": "بند القطعة غير موجود على هذا الأمر."})
        if part.materialized_at is not None:
            raise ValidationError({
                "detail": (
                    "هذا البند تجسّد في مستند (صرف كفالة أو فاتورة) — تراجع عن ذلك "
                    "المستند أولاً ثم عدّله."
                )
            })

        if request.method == "DELETE":
            self._log_part(order, part, "حُذفت")
            part.delete()
            return Response(status=http_status.HTTP_204_NO_CONTENT)

        form = ServiceOrderPartSerializer(part, data=request.data, partial=True)
        form.is_valid(raise_exception=True)
        product = form.validated_data.get("product")
        if product is not None and product.tenant_id != self.tenant.pk:
            raise ValidationError({"product": "هذا المنتج لا يتبع الشركة النشطة."})
        part = form.save()
        self._log_part(order, part, "عُدّلت")
        return Response(ServiceOrderPartSerializer(part).data)

    def _log_part(self, order, part, verb: str):
        from .service_orders import log_event
        from .models import ServiceOrderEvent
        from inventory.services import product_display_name

        name = product_display_name(part.product)
        log_event(
            order, event_type=ServiceOrderEvent.TYPE_PART,
            text=f"{verb} قطعة: {name} × {part.quantity} ({part.get_billing_display()})",
            user=self.request.user,
        )

    # ── المال ─────────────────────────────────────────────────────────────
    @action(detail=True, methods=["post"], url_path="post-covered")
    def post_covered(self, request, pk=None):
        from .service_orders import post_covered_parts

        order = self.get_object()
        try:
            result = post_covered_parts(order, user=request.user)
        except DjangoValidationError as error:
            _reraise_as_drf(error)
        return Response({
            "posted": result,
            "order": self.get_serializer(self.get_object()).data,
        })

    @action(detail=True, methods=["post"], url_path="unpost-covered")
    def unpost_covered(self, request, pk=None):
        from .service_orders import unpost_covered_parts

        order = self.get_object()
        try:
            result = unpost_covered_parts(order, user=request.user)
        except DjangoValidationError as error:
            _reraise_as_drf(error)
        return Response({
            "unposted": result,
            "order": self.get_serializer(self.get_object()).data,
        })

    @action(detail=True, methods=["post"], url_path="generate-invoice")
    def generate_invoice(self, request, pk=None):
        from .service_orders import generate_service_invoice

        order = self.get_object()
        form = GenerateServiceInvoiceSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        try:
            invoice = generate_service_invoice(
                order, user=request.user,
                labour_amount=form.validated_data.get("labour_amount"),
            )
        except DjangoValidationError as error:
            _reraise_as_drf(error)
        return Response(
            {
                "invoice": {
                    "id": invoice.pk,
                    "invoice_number": invoice.invoice_number,
                    "status": invoice.status,
                    "grand_total": invoice.grand_total,
                },
                "order": self.get_serializer(self.get_object()).data,
            },
            status=http_status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="detach-invoice")
    def detach_invoice(self, request, pk=None):
        from .service_orders import detach_service_invoice

        order = self.get_object()
        try:
            result = detach_service_invoice(order, user=request.user)
        except DjangoValidationError as error:
            _reraise_as_drf(error)
        return Response({
            "detached": result,
            "order": self.get_serializer(self.get_object()).data,
        })

    # ── الاستقبال ─────────────────────────────────────────────────────────
    @action(detail=False, methods=["get"], url_path="lookup")
    def lookup(self, request):
        """بحث الاستقبال بمعرّف واحد في ثلاثة مصادر — بلا مفتاح أجنبي بينها."""
        from .service_orders import intake_lookup

        return Response(
            intake_lookup(self.tenant, request.query_params.get("serial") or "")
        )
