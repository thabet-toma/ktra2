"""API مكتب المحاسبة — كلُّ نقطةٍ خلف بوابة الترخيص `require_module`.

**404 لا 403 لشركةٍ غير مرخّصة** (كما في `device_registry` و`employee_ops`): 403
يُثبت وجود الوحدة، و404 لا يُثبت شيئاً. والترخيصُ في `initial` **بعد** المصادقة
والصلاحيات (نمط `device_registry`): طلبٌ مجهول يأخذ 401 لا 403، وعضوٌ في شركةٍ
غير مرخّصة يأخذ 404.

**والعزل في كل استعلام**: `get_queryset` مقيَّدٌ بشركة الطلب، وكلُّ كائنٍ مرجعيّ
في الجسم (زبون، جهة) يُتحقَّق أنه من الشركة نفسها — وإلا كان الـpk باباً خلفياً.

**ولا حذف للزبون:** `destroy` مرفوضةٌ صراحةً (405) ولو كان `delete` مُدرَجاً في
`http_method_names` — لأن فكَّ ربط الجهة فعلُ حذفٍ يسكن هذا الـViewSet نفسه.
«منتهٍ» حالةٌ تُكتب بقيمتها الحقيقية، لا صفٌّ يُطوى.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound, ValidationError
from rest_framework.response import Response

from accounting_office import services
from accounting_office.models import ClientContact, Contact, OfficeClient
from accounting_office.serializers import (
    ClientContactLinkSerializer,
    ClientContactRowSerializer,
    ContactSerializer,
    OfficeClientListSerializer,
    OfficeClientSerializer,
    ReminderRecipientSerializer,
    SettingValueSerializer,
    TaxCardWriteSerializer,
)
from core.api_defaults import ApiAuthAndUser
from core.modules import require_module

MODULE_KEY = "accounting_office"


class OfficeModuleViewSet(viewsets.GenericViewSet):
    """الأساس: مصادقة، ترخيص، وعزل شركة — ثم تحويلُ خطأ الخدمة إلى 400."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def initial(self, request, *args, **kwargs):
        # الترتيب: المصادقةُ والصلاحيات ثم الترخيص (نمط `device_registry`) — كي
        # يأخذ الطلبُ المجهول 401 لا 404، ويأخذ عضوُ الشركة غير المرخّصة 404.
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)

    def handle_exception(self, exc):
        """`ValidationError` من طبقة الخدمات خطأُ مدخلاتٍ (400) لا عطلُ خادم."""
        if isinstance(exc, DjangoValidationError):
            detail = exc.message_dict if hasattr(exc, "error_dict") else list(exc.messages)
            exc = ValidationError(detail)
        return super().handle_exception(exc)

    def _contact(self, contact_id):
        contact = (
            self._contacts()
            .filter(pk=contact_id)
            .first()
        )
        if contact is None:
            raise NotFound("الجهة غير موجودة.")
        return contact

    def _contacts(self):
        return Contact.objects.filter(tenant=self.tenant)


class OfficeClientViewSet(OfficeModuleViewSet, viewsets.ModelViewSet):
    """زبائن المكتب: قائمةٌ بحثاً وفلترة، وإنشاء، وقراءة، وتعديل — بلا حذف."""

    # `delete` مُدرَجٌ لأن أفعالَ الحذف داخل هذا الـViewSet (فكُّ ربط جهة) تمرّ به،
    # و`destroy` وحدها مرفوضةٌ صراحةً أدناه — لا يُحذف الزبون نفسه أبداً.
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def destroy(self, request, *args, **kwargs):
        """**لا حذف للزبون**: «منتهٍ» يبقى ببطاقته وجهاته وملاحظاته، ويعود نشطاً."""
        raise MethodNotAllowed("DELETE")

    def get_serializer_class(self):
        # القائمة صفٌّ خفيف بلا بطاقة — بطاقةُ كل زبون في تفصيله وحده.
        if self.action == "list":
            return OfficeClientListSerializer
        return OfficeClientSerializer

    def get_queryset(self):
        queryset = OfficeClient.objects.filter(tenant=self.tenant)
        if self.action == "list":
            queryset = self._filtered(queryset)
        else:
            queryset = queryset.select_related("tax_card", "tenant")
        return queryset.order_by("name", "id")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        clients = list(page) if page is not None else list(queryset)
        # نظامُ كل صفٍّ يُبنى استعلامين لكل الصفحة، ويُمرَّر في `context` صراحةً —
        # لا سمةً على الصنف تبقى بين الطلبات.
        context = {
            **self.get_serializer_context(),
            "tax_systems": services.resolve_setting_for_clients(
                self.tenant, services.TAX_SYSTEM_KEY, clients,
            ),
        }
        serializer = self.get_serializer(clients, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def _filtered(self, queryset):
        params = self.request.query_params
        term = (params.get("q") or "").strip()
        if term:
            queryset = queryset.filter(
                Q(name__icontains=term) | Q(tax_file_number__icontains=term),
            )
        status_filter = (params.get("status") or "").strip()
        if status_filter in (OfficeClient.STATUS_ACTIVE, OfficeClient.STATUS_ENDED):
            queryset = queryset.filter(status=status_filter)
        return queryset

    # ── الكتابة عبر الخدمات، لا عبر `serializer.save` ────────────────────
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        tax_card = data.pop("tax_card", None)
        client = services.create_office_client(
            tenant=self.tenant, tax_card=tax_card, **data,
        )
        return Response(
            self.get_serializer(client).data, status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        client = self.get_object()
        serializer = self.get_serializer(client, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        # البطاقةُ تُمرَّر للخدمة مع الاسم: كتابةٌ واحدة في معاملةٍ واحدة.
        services.update_office_client(
            client,
            name=data.get("name"),
            tax_file_number=data.get("tax_file_number"),
            notes=data.get("notes"),
            tax_card=data.pop("tax_card", None),
        )
        client.refresh_from_db()
        return Response(self.get_serializer(client).data)

    # ── دورة الحياة ─────────────────────────────────────────────────────
    # الفاعلُ يمرّ إلى الخدمة كي يُسجَّل الحدث باسم من فعله — `log_activity` يقرأ
    # `request.user` أيضاً، لكن تمريرَه صراحةً يجعل الخدمة صالحةً للنداء البرمجي.
    @action(detail=True, methods=["post"], url_path="end")
    def end(self, request, pk=None):
        client = services.end_office_client(
            self.get_object(), actor=request.user, request=request,
        )
        return Response(self.get_serializer(client).data)

    @action(detail=True, methods=["post"], url_path="reactivate")
    def reactivate(self, request, pk=None):
        client = services.reactivate_office_client(
            self.get_object(), actor=request.user, request=request,
        )
        return Response(self.get_serializer(client).data)

    # ── البطاقة الضريبية ────────────────────────────────────────────────
    @action(detail=True, methods=["get", "patch"], url_path="tax-card")
    def tax_card(self, request, pk=None):
        client = self.get_object()
        if request.method == "PATCH":
            serializer = TaxCardWriteSerializer(data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            services.update_tax_card(client, **serializer.validated_data)
            client.refresh_from_db()
        return Response(services.tax_card_payload(client))

    # ── الجهات المربوطة ─────────────────────────────────────────────────
    @action(detail=True, methods=["get", "post"], url_path="contacts")
    def contacts(self, request, pk=None):
        client = self.get_object()
        if request.method == "POST":
            serializer = ClientContactLinkSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            link = services.link_client_contact(
                client=client,
                contact=self._contact(serializer.validated_data["contact"]),
                is_primary=serializer.validated_data.get("is_primary", False),
            )
            return Response(
                ClientContactRowSerializer(link).data, status=status.HTTP_201_CREATED,
            )
        return Response(ClientContactRowSerializer(
            client.contact_links.select_related("contact").order_by("-is_primary", "id"),
            many=True,
        ).data)

    @action(
        detail=True, methods=["delete"],
        url_path=r"contacts/(?P<contact_id>[0-9]+)",
    )
    def unlink_contact(self, request, pk=None, contact_id=None):
        client = self.get_object()
        link = self._link(client, contact_id)
        services.unlink_client_contact(client=client, contact=link.contact)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True, methods=["post"],
        url_path=r"contacts/(?P<contact_id>[0-9]+)/primary",
    )
    def promote_contact(self, request, pk=None, contact_id=None):
        client = self.get_object()
        link = self._link(client, contact_id)
        services.set_primary_client_contact(client=client, contact=link.contact)
        return Response(ClientContactRowSerializer(
            ClientContact.objects.select_related("contact").get(pk=link.pk),
        ).data)

    def _link(self, client, contact_id):
        link = (
            ClientContact.objects
            .select_related("contact")
            .filter(client=client, contact_id=contact_id)
            .first()
        )
        if link is None:
            raise NotFound("هذه الجهة غير مربوطةٍ بالزبون.")
        return link

    # ── مستلِم كل نوع تذكير ─────────────────────────────────────────────
    @action(detail=True, methods=["get", "post"], url_path="reminders")
    def reminders(self, request, pk=None):
        client = self.get_object()
        if request.method == "POST":
            serializer = ReminderRecipientSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            contact_id = serializer.validated_data.get("contact")
            services.set_reminder_recipient(
                client=client,
                reminder_type=serializer.validated_data["reminder_type"],
                contact=None if contact_id is None else self._contact(contact_id),
            )
        return Response(services.reminder_recipients_payload(client))

    # ── إعدادات الزبون ──────────────────────────────────────────────────
    #
    # اسمُ الدالة `client_settings` لا `settings`: الحقلُ `APIView.settings`
    # موجودٌ في DRF، ودالّةٌ بنفس الاسم تحجبه فيصير `self.settings` دالّةً
    # مقيدةً لا كائنَ إعدادات — ويسقط كلُّ طلبٍ على `FORMAT_SUFFIX_KWARG`.
    @action(detail=True, methods=["get"], url_path="settings")
    def client_settings(self, request, pk=None):
        return Response(services.client_settings_payload(self.get_object()))

    @action(detail=True, methods=["put", "delete"], url_path=r"settings/(?P<key>[a-z_]+)")
    def setting(self, request, pk=None, key=None):
        client = self.get_object()
        if request.method == "DELETE":
            services.reset_client_setting(client, key)
        else:
            serializer = SettingValueSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            services.set_client_setting(client, key, serializer.validated_data["value"])
        return Response(services.client_setting_row(client, key))


class OfficeContactViewSet(OfficeModuleViewSet, viewsets.ModelViewSet):
    """جهات اتصال المكتب — شخصٌ يملكه المكتب ويُربط بأكثر من زبون."""

    serializer_class = ContactSerializer

    def get_queryset(self):
        queryset = self._contacts()
        if self.action == "list":
            term = (self.request.query_params.get("q") or "").strip()
            if term:
                queryset = queryset.filter(
                    Q(name__icontains=term) | Q(phone__icontains=term),
                )
        return queryset.order_by("name", "id")

    def perform_create(self, serializer):
        serializer.save(tenant=self.tenant)

    def destroy(self, request, *args, **kwargs):
        """الحذفُ من دفتر المكتب مشروطٌ بلا ربط — والقاعدة في الخدمة لا هنا."""
        contact = self.get_object()
        services.delete_contact(contact)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OfficeSettingsViewSet(OfficeModuleViewSet):
    """سجلّ الإعدادات: مجموعة «المكتب» الآن — وتخصيصُ الزبون في ملفّه."""

    serializer_class = SettingValueSerializer

    def get_object(self):
        # الإعدادات تُقرأ بمفتاحها عبر `services` لا ككائنٍ مفرد.
        # و`SimpleMetadata.determine_actions` ينادي `get_object` لأفعال الكتابة في
        # `OPTIONS` ويبتلع `Http404` — فبلا هذا التعريف يسقط
        # `GenericAPIView.get_queryset` بـ`AssertionError` (500).
        raise NotFound("لا كائن مفرد لسجلّ الإعدادات.")

    def list(self, request, *args, **kwargs):
        return Response(services.office_settings_payload(self.tenant))

    @action(detail=False, methods=["put", "delete"], url_path=r"(?P<key>[a-z_]+)")
    def setting(self, request, key=None):
        if request.method == "DELETE":
            services.reset_office_setting(self.tenant, key)
        else:
            serializer = SettingValueSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            services.set_office_setting(self.tenant, key, serializer.validated_data["value"])
        return Response(services.office_setting_row(self.tenant, key))

    @action(detail=False, methods=["get"], url_path=r"(?P<key>[a-z_]+)/clients")
    def customized_clients(self, request, key=None):
        return Response(services.clients_customized_payload(self.tenant, key))
