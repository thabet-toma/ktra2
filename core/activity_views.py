"""API سجل النشاط الموحّد.

- سجل مستند واحد: ?entity_type=sales_invoice&entity_id=12 → متاح لأي مستخدم مصرّح.
- الصفحة العامة (بلا entity_id): نشاط كل المستخدمين → للمدير/السوبر أدمن فقط.
- فلاتر: user, action, entity_type, search, include_views (افتراضي false —
  يستبعد أحداث العرض من الجدول العام).
- المدى الزمني: `range` جاهز (today/yesterday/week/month/quarter/year/all)، أو
  `date` ليومٍ واحد، أو `date_from`/`date_to`. الافتراضي للصفحة العامة «اليوم».
"""
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from core.api_defaults import ApiAuthAndUser
from core.date_ranges import RANGE_PRESETS, filter_local_date_range, resolve_preset
from core.models import ActivityLog
from core.tenant_utils import get_tenant
from core.user_roles import user_is_admin


def _partner_activity_filter(tenant, partner_id):
    """روابط جديدة + حل علاقات المستندات للسجلات التاريخية غير المربوطة."""
    from logistics.models import (
        LocalShipment, LogisticsClearance, LogisticsDeal, LogisticsShipment,
        LogisticsShipmentDeal, PurchaseInvoice,
    )
    from sales.models import CustomerPayment, SalesInvoice, SupplierPayment

    deal_ids = LogisticsDeal.all_objects.filter(
        tenant=tenant, partner_id=partner_id,
    ).values("id")
    supplier_shipment_ids = LogisticsShipmentDeal.objects.filter(
        shipment__tenant=tenant, deal__partner_id=partner_id,
    ).values("shipment_id")
    shipment_ids = LogisticsShipment.all_objects.filter(
        Q(tenant=tenant, shipping_agent_id=partner_id)
        | Q(id__in=supplier_shipment_ids),
    ).values("id")
    clearance_ids = LogisticsClearance.objects.filter(
        Q(tenant=tenant, customs_broker_id=partner_id)
        | Q(tenant=tenant, shipment_id__in=supplier_shipment_ids),
    ).values("id")
    local_shipment_ids = LocalShipment.objects.filter(
        Q(tenant=tenant, carrier_id=partner_id)
        | Q(tenant=tenant, shipment_id__in=supplier_shipment_ids),
    ).values("id")

    return (
        Q(partner_links__partner_id=partner_id)
        | Q(entity_type="partner", entity_id=partner_id)
        | Q(entity_type="deal", entity_id__in=deal_ids)
        | Q(
            entity_type="purchase_invoice",
            entity_id__in=PurchaseInvoice.objects.filter(
                tenant=tenant, partner_id=partner_id,
            ).values("id"),
        )
        | Q(
            entity_type="sales_invoice",
            entity_id__in=SalesInvoice.objects.filter(
                tenant=tenant, customer_id=partner_id,
            ).values("id"),
        )
        | Q(
            entity_type="customer_payment",
            entity_id__in=CustomerPayment.objects.filter(
                tenant=tenant, partner_id=partner_id,
            ).values("id"),
        )
        | Q(
            entity_type="supplier_payment",
            entity_id__in=SupplierPayment.objects.filter(
                tenant=tenant, partner_id=partner_id,
            ).values("id"),
        )
        | Q(entity_type="shipment", entity_id__in=shipment_ids)
        | Q(entity_type="clearance", entity_id__in=clearance_ids)
        | Q(entity_type="local_shipment", entity_id__in=local_shipment_ids)
    )


def _fold_view_events(rows):
    """يطوي أحداث العرض المتتالية لنفس المستخدم في صفّ واحد بعدّاد.

    الطيّ **عند القراءة**: مسار الكتابة (core.activity) عقدُه أنه لا يعطّل الطلب
    أبداً، فلا يُقحَم فيه قفلُ صفٍّ ولا سباقٌ على عدّاد. الصفوف الخام تبقى كاملة في
    قاعدة البيانات، والمعروض مشتقّ منها: `group_rows` يحمل المطويّات كي تُفتح.

    التتالي شرط: تعديلٌ بين عرضين يفصلهما، فلا يبتلع الطيّ ترتيب الأحداث — وهو
    أهمّ ما في سجل تدقيق. الطيّ يجري على الصفحة المعروضة، فالعدّاد عدّاد صفحتها.
    """
    folded = []
    for row in rows:
        prev = folded[-1] if folded else None
        same_actor_view = (
            row.get("is_view")
            and prev is not None
            and prev.get("is_view")
            and prev.get("user") == row.get("user")
            and prev.get("action") == row.get("action")
            and prev.get("entity_type") == row.get("entity_type")
            and prev.get("entity_id") == row.get("entity_id")
        )
        if same_actor_view:
            prev["group_count"] += 1
            prev["group_ids"].append(row["id"])
            prev["group_rows"].append(row)
            # الترتيب تنازليّ زمنياً، فآخر ما يُضاف هو الأقدم في المجموعة.
            prev["first_timestamp"] = row["timestamp"]
            continue
        new_row = dict(row)
        new_row["group_count"] = 1
        new_row["group_ids"] = [row["id"]]
        new_row["group_rows"] = [row]
        new_row["first_timestamp"] = row["timestamp"]
        folded.append(new_row)
    # الصفّ المفرد لا يحمل نسخةً من نفسه — الحمولة تبقى بحجم الصفحة لا ضعفها.
    for row in folded:
        if row["group_count"] == 1:
            row.pop("group_rows", None)
    return folded


class ActivityLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = ActivityLog
        fields = [
            "id", "action", "action_label", "is_view", "entity_type", "entity_id",
            "entity_label", "description", "metadata", "user", "user_name",
            "ip_address", "timestamp",
        ]

    def get_user_name(self, obj):
        u = obj.user
        if not u:
            return "—"
        full = f"{u.first_name} {u.last_name}".strip()
        return full or u.username


class ActivityLogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = ActivityLogSerializer
    pagination_class = ActivityLogPagination

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return ActivityLog.objects.none()
        qs = ActivityLog.objects.filter(tenant=tenant).select_related("user")

        p = self.request.query_params
        entity_type = p.get("entity_type")
        entity_id = p.get("entity_id")
        partner_id = p.get("partner_id")

        # صلاحية: سجل مستند/جهة متاح للعضو؛ السجل العام للمدير فقط.
        is_document_scoped = self._is_document_scoped()
        is_partner_scoped = bool(partner_id)
        is_scoped = is_document_scoped or is_partner_scoped
        if not is_scoped and not user_is_admin(self.request.user):
            raise PermissionDenied("سجل النشاط العام متاح للمدير فقط.")

        if entity_type:
            qs = qs.filter(entity_type=entity_type)
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        if partner_id:
            try:
                partner_id = int(partner_id)
            except (TypeError, ValueError):
                raise ValidationError({"partner_id": "معرّف الجهة غير صالح."})
            from partners.models import Partner

            if not Partner.objects.filter(tenant=tenant, id=partner_id).exists():
                raise ValidationError({"partner_id": "الجهة غير موجودة في هذه الشركة."})
            qs = qs.filter(_partner_activity_filter(tenant, partner_id)).distinct()

        user_id = p.get("user")
        if user_id:
            qs = qs.filter(user_id=user_id)

        act = p.get("action")
        if act:
            qs = qs.filter(action=act)

        # أحداث العرض مستبعَدة افتراضياً من الجدول العام؛ تُطلب صراحةً بـ include_views=true
        # أو ضمن سجل مستند واحد.
        include_views = str(p.get("include_views", "")).lower() in ("1", "true", "yes")
        if not include_views and not is_document_scoped:
            qs = qs.filter(is_view=False)

        # المدى الزمني: `range` جاهز، أو `date` ليومٍ واحد، أو `date_from/to`.
        # لا `timestamp__date` هنا: CONVERT_TZ تُعيد NULL على خادمٍ بلا جداول
        # مناطق زمنية فتُفرَّغ الصفحة بصمت — راجع core/date_ranges.py.
        date_from, date_to = self._resolve_dates(p, is_scoped)
        qs = filter_local_date_range(
            qs, "timestamp", date_from=date_from, date_to=date_to,
        )

        search = (p.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(entity_label__icontains=search)
                | Q(description__icontains=search)
                | Q(user__username__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )

        return qs.order_by("-timestamp", "-id")

    @staticmethod
    def _resolve_dates(params, is_scoped: bool):
        """المدى الزمني المطلوب كيومين شاملين — أو (None, None) لبلا حدّ.

        الأولوية: `range` الجاهز ← `date` ليومٍ واحد ← `date_from/date_to`. وحين
        لا يُطلب شيء تبقى الصفحة العامة على «اليوم» (سجل مستندٍ أو جهةٍ بلا حدّ
        زمني افتراضاً، فتاريخه كلّه هو المقصود).
        """
        preset = (params.get("range") or "").strip().lower()
        if preset:
            if preset not in RANGE_PRESETS:
                raise ValidationError(
                    {"range": f"مدى غير معروف: {preset}. المتاح: {', '.join(RANGE_PRESETS)}."},
                )
            return resolve_preset(preset)

        single_date = parse_date(params.get("date") or "")
        if single_date:
            return single_date, single_date

        date_from = parse_date(params.get("date_from") or "")
        date_to = parse_date(params.get("date_to") or "")
        if date_from or date_to:
            return date_from, date_to
        if is_scoped:
            return None, None
        return resolve_preset("today")

    def _is_document_scoped(self) -> bool:
        """سجل مستند واحد = نوع الكيان ومعرّفه معاً؛ وهو وحده ما يُطوى."""
        p = self.request.query_params
        return bool(p.get("entity_type") and p.get("entity_id"))

    def list(self, request, *args, **kwargs):
        """سجل المستند يُطوى قبل بثّه؛ الصفحة العامة تبقى صفوفاً خاماً.

        الطيّ بعد الترقيم لا قبله: الصفحة هي ما يراه المستخدم، وعليها يُحسب
        العدّاد — بلا استعلام إضافي على الجدول كاملاً.
        """
        response = super().list(request, *args, **kwargs)
        if not self._is_document_scoped():
            return response
        data = response.data
        if isinstance(data, dict) and "results" in data:
            data["results"] = _fold_view_events(data["results"])
        else:
            response.data = _fold_view_events(data)
        return response

    @action(detail=False, methods=["get"], url_path="users")
    def users(self, request):
        """قائمة المستخدمين الذين لهم نشاط (لفلتر الصفحة العامة). للمدير فقط."""
        tenant = get_tenant(request)
        if not tenant:
            return Response([])
        if not user_is_admin(request.user):
            raise PermissionDenied("متاح للمدير فقط.")
        user_ids = (
            ActivityLog.objects.filter(tenant=tenant, user__isnull=False)
            .values_list("user_id", flat=True)
            .distinct()
        )
        out = []
        for u in User.objects.filter(id__in=list(user_ids)):
            name = f"{u.first_name} {u.last_name}".strip() or u.username
            out.append({"id": u.id, "name": name})
        out.sort(key=lambda x: x["name"])
        return Response(out)
