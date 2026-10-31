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
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import (
    MethodNotAllowed,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.response import Response

from accounting_office import services
from accounting_office.models import (
    ClientContact,
    ClientService,
    Contact,
    OfficeClient,
    OfficeService,
    ServicePackage,
)
from accounting_office.serializers import (
    ApplyPackageSerializer,
    ClientContactLinkSerializer,
    ClientContactRowSerializer,
    ClientServiceFrequencyWriteSerializer,
    ClientServiceStopSerializer,
    ClientServiceWriteSerializer,
    ContactSerializer,
    OfficeClientListSerializer,
    OfficeClientSerializer,
    OfficeServiceSerializer,
    ReminderRecipientSerializer,
    ServicePackageWriteSerializer,
    SettingValueSerializer,
    TaxCardWriteSerializer,
)
from core.access import (
    OFFICE_CLIENTS_ASSIGN_KEY,
    OFFICE_CLIENTS_WRITE_KEY,
    OFFICE_SETTINGS_MANAGE_KEY,
    require_perm,
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

    def require_write(self):
        """كلُّ كتابةٍ في الموديول — زبائن، بطاقة، جهات، ربط، مستلِمون، تخصيص."""
        require_perm(self.request, OFFICE_CLIENTS_WRITE_KEY, tenant=self.tenant)

    def require_settings_manage(self):
        """كتابةُ كتالوج الخدمات والباقات — مفتاحُ الإعدادات لا مفتاحُ الزبائن."""
        require_perm(self.request, OFFICE_SETTINGS_MANAGE_KEY, tenant=self.tenant)

    def reject_amount_writes(self, payload):
        """كتابةُ مبلغٍ بلا `office.amounts.view` ⇒ **403** — لا يكتب ما لا يراه.

        والحقلُ المخفيّ لا يُمسّ حين يحفظ العضو حقولاً أخرى: القناع يمنع الطلبَ
        من الأصل، فلا يُعاد كتابةُ المبلغ المخزَّن بـ`None`.
        """
        if not payload:
            return
        hidden = [key for key in services.AMOUNT_KEYS if key in payload]
        if hidden and not services.can_see_amounts(self.tenant, self.request.user):
            raise PermissionDenied(
                "صلاحية «يرى المبالغ» غير ممنوحة لدورك — لا تكتب مبلغاً لا تراه.",
            )

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
        # **مصدر الرؤية الوحيد** (`services.visible_clients`): بلا
        # `office.clients.all` لا يُرى إلا زبون العضو — والقائمةُ والتفصيلُ
        # وأفعالُه المتداخلة كلُّها تمرّ من هنا، فزبونُ غيرك **404** لا 403.
        queryset = services.visible_clients(self.tenant, self.request.user)
        if self.action == "list":
            queryset = self._filtered(queryset)
        else:
            queryset = queryset.select_related("tax_card", "tenant")
        return queryset.select_related("responsible").order_by("name", "id")

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
        self.require_write()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        tax_card = data.pop("tax_card", None)
        self.reject_amount_writes(tax_card)
        client = services.create_office_client(
            tenant=self.tenant, actor=request.user, tax_card=tax_card, **data,
        )
        return Response(
            self.get_serializer(client).data, status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        self.require_write()
        partial = kwargs.pop("partial", False)
        client = self.get_object()
        serializer = self.get_serializer(client, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        tax_card = data.pop("tax_card", None)
        self.reject_amount_writes(tax_card)
        # البطاقةُ تُمرَّر للخدمة مع الاسم: كتابةٌ واحدة في معاملةٍ واحدة.
        services.update_office_client(
            client,
            name=data.get("name"),
            tax_file_number=data.get("tax_file_number"),
            notes=data.get("notes"),
            tax_card=tax_card,
        )
        client.refresh_from_db()
        return Response(self.get_serializer(client).data)

    # ── دورة الحياة ─────────────────────────────────────────────────────
    # الفاعلُ يمرّ إلى الخدمة كي يُسجَّل الحدث باسم من فعله — `log_activity` يقرأ
    # `request.user` أيضاً، لكن تمريرَه صراحةً يجعل الخدمة صالحةً للنداء البرمجي.
    @action(detail=True, methods=["post"], url_path="end")
    def end(self, request, pk=None):
        self.require_write()
        client = services.end_office_client(
            self.get_object(), actor=request.user, request=request,
        )
        return Response(self.get_serializer(client).data)

    @action(detail=True, methods=["post"], url_path="reactivate")
    def reactivate(self, request, pk=None):
        self.require_write()
        client = services.reactivate_office_client(
            self.get_object(), actor=request.user, request=request,
        )
        return Response(self.get_serializer(client).data)

    # ── الموظف المسؤول والتحويل ─────────────────────────────────────────
    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request, pk=None):
        """`{"user": <id>}` — تحويلُ الزبون، بمفتاحه وحده (`office.clients.assign`).

        مفتاحٌ ثانٍ لا `office.clients.write`: من يكتب بيانات زبونٍ لا يسلبه من
        صاحبه بضغطةٍ في نموذج التعديل.
        """
        require_perm(request, OFFICE_CLIENTS_ASSIGN_KEY, tenant=self.tenant)
        client = self.get_object()
        user_id = request.data.get("user")
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            raise ValidationError({"user": "معرّف الموظف مطلوب."}) from None
        target = get_user_model().objects.filter(pk=user_id, is_active=True).first()
        if target is None:
            raise ValidationError({"user": "لا يوجد مستخدم مفعَّل بهذا المعرّف."})
        client = services.assign_office_client(
            client, user=target, actor=request.user, request=request,
        )
        return Response(self.get_serializer(client).data)

    # ── البطاقة الضريبية ────────────────────────────────────────────────
    @action(detail=True, methods=["get", "patch"], url_path="tax-card")
    def tax_card(self, request, pk=None):
        client = self.get_object()
        if request.method == "PATCH":
            self.require_write()
            serializer = TaxCardWriteSerializer(data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.reject_amount_writes(serializer.validated_data)
            services.update_tax_card(client, **serializer.validated_data)
            client.refresh_from_db()
        return Response(services.tax_card_payload(client, user=request.user))

    # ── الجهات المربوطة ─────────────────────────────────────────────────
    @action(detail=True, methods=["get", "post"], url_path="contacts")
    def contacts(self, request, pk=None):
        client = self.get_object()
        if request.method == "POST":
            self.require_write()
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
        self.require_write()
        client = self.get_object()
        link = self._link(client, contact_id)
        services.unlink_client_contact(client=client, contact=link.contact)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True, methods=["post"],
        url_path=r"contacts/(?P<contact_id>[0-9]+)/primary",
    )
    def promote_contact(self, request, pk=None, contact_id=None):
        self.require_write()
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
            self.require_write()
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
        self.require_write()
        client = self.get_object()
        if request.method == "DELETE":
            services.reset_client_setting(client, key)
        else:
            serializer = SettingValueSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            services.set_client_setting(client, key, serializer.validated_data["value"])
        return Response(services.client_setting_row(client, key))

    # ── خدمات الزبون (#273) ─────────────────────────────────────────────
    #
    # كلُّ فعلٍ هنا يبدأ بـ`get_object()`: الرؤيةُ أوّلاً (`visible_clients`) فيأخذ
    # مَن لا يرى الزبون **404** لا 403، ثم مفتاحُ الكتابة فيأخذ القارئُ 403.
    @action(detail=True, methods=["get", "post"], url_path="services")
    def client_services(self, request, pk=None):
        client = self.get_object()
        if request.method == "POST":
            self.require_write()
            serializer = ClientServiceWriteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            # الخدمةُ تُحلّ من كتالوج الشركة وحدها — معرّفٌ من مكتبٍ آخر 400 لا 404.
            service = services.service_or_raise(self.tenant, data["service"])
            services.add_client_service(
                client=client,
                service=service,
                starts_on=data.get("starts_on"),
                responsible_from=data.get("responsible_from"),
                # `null` الواصل يعني «لم يُختَر» فيُقترح — لا دوريةَ بقيمة None.
                frequency=data.get("frequency") or None,
                actor=request.user,
            )
            return Response(
                services.client_services_payload(client, user=request.user),
                status=status.HTTP_201_CREATED,
            )
        return Response(services.client_services_payload(client, user=request.user))

    @action(detail=True, methods=["get"], url_path="services/suggest")
    def client_service_suggest(self, request, pk=None):
        """`?service=<code>&on=<date>` — الاقتراحُ وسببُه، ولا كتابةَ هنا."""
        client = self.get_object()
        code = (request.query_params.get("service") or "").strip()
        if not code:
            raise ValidationError({"service": "كود الخدمة مطلوب."})
        raw_date = (request.query_params.get("on") or "").strip()
        on_date = None
        if raw_date:
            on_date = parse_date(raw_date)
            if on_date is None:
                raise ValidationError({"on": "تاريخٌ غير صالح."})
        service = services.service_by_code(self.tenant, code)
        return Response(
            services.suggestion_payload(client, service, on_date=on_date),
        )

    @action(
        detail=True, methods=["post"],
        url_path=r"services/(?P<client_service_id>[0-9]+)/frequency",
    )
    def client_service_frequency(self, request, pk=None, client_service_id=None):
        client = self.get_object()
        self.require_write()
        row = self._client_service(client, client_service_id)
        serializer = ClientServiceFrequencyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_client_service_frequency(
            row,
            frequency=serializer.validated_data["frequency"],
            effective_from=serializer.validated_data["effective_from"],
            actor=request.user,
        )
        return Response(services.client_services_payload(client, user=request.user))

    @action(
        detail=True, methods=["post"],
        url_path=r"services/(?P<client_service_id>[0-9]+)/stop",
    )
    def client_service_stop(self, request, pk=None, client_service_id=None):
        client = self.get_object()
        self.require_write()
        row = self._client_service(client, client_service_id)
        serializer = ClientServiceStopSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.stop_client_service(
            row, ends_on=serializer.validated_data["ends_on"],
        )
        return Response(services.client_services_payload(client, user=request.user))

    @action(detail=True, methods=["post"], url_path="apply-package")
    def apply_package(self, request, pk=None):
        """تعبئةُ خدمات الزبون من باقة — **نسخٌ لا ربط**، ويُبلَّغ بما تُخطّي."""
        client = self.get_object()
        self.require_write()
        serializer = ApplyPackageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        package = services.package_or_raise(
            self.tenant, serializer.validated_data["package"],
        )
        return Response(
            services.apply_package(client, package, actor=request.user),
        )

    def _client_service(self, client, client_service_id):
        """صفُّ `ClientService` — **معرّفُ خدمة الزبون** لا معرّفُ الكتالوج."""
        row = (
            ClientService.objects
            .select_related("service", "client")
            .filter(client=client, pk=client_service_id)
            .first()
        )
        if row is None:
            raise NotFound("خدمةُ الزبون هذه غير موجودة.")
        return row


class OfficeContactViewSet(OfficeModuleViewSet, viewsets.ModelViewSet):
    """جهات اتصال المكتب — شخصٌ يملكه المكتب ويُربط بأكثر من زبون."""

    serializer_class = ContactSerializer

    def get_queryset(self):
        # **مصدر رؤية الجهات** (`services.visible_contacts`): بلا
        # `office.clients.all` لا تُقرأ جهةُ زبونٍ لا يراه العضو (ولا تُعدَّل ولا
        # تُحذف) — وغيرُ المربوطة تبقى ليجدها المنتقي.
        queryset = services.visible_contacts(self.tenant, self.request.user)
        if self.action == "list":
            term = (self.request.query_params.get("q") or "").strip()
            if term:
                queryset = queryset.filter(
                    Q(name__icontains=term) | Q(phone__icontains=term),
                )
        return queryset.order_by("name", "id")

    def perform_create(self, serializer):
        self.require_write()
        serializer.save(tenant=self.tenant)

    def perform_update(self, serializer):
        self.require_write()
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """الحذفُ من دفتر المكتب مشروطٌ بلا ربط — والقاعدة في الخدمة لا هنا."""
        self.require_write()
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
        # عدّادُ «مخصَّص عند N زبون» رقمٌ عن الزبائن — يُحسب على ما يراه العضو.
        return Response(
            services.office_settings_payload(self.tenant, user=request.user),
        )

    @action(detail=False, methods=["put", "delete"], url_path=r"(?P<key>[a-z_]+)")
    def setting(self, request, key=None):
        # كتابةُ إعداد المكتب بمفتاحها: `office.settings.manage` لا مفتاح الكتابة
        # العامّ — من يكتب بيانات الزبائن لا يغيّر النظام الضريبي للمكتب كلّه.
        require_perm(request, OFFICE_SETTINGS_MANAGE_KEY, tenant=self.tenant)
        if request.method == "DELETE":
            services.reset_office_setting(self.tenant, key)
        else:
            serializer = SettingValueSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            services.set_office_setting(self.tenant, key, serializer.validated_data["value"])
        return Response(
            services.office_setting_row(self.tenant, key, user=request.user),
        )

    @action(detail=False, methods=["get"], url_path=r"(?P<key>[a-z_]+)/clients")
    def customized_clients(self, request, key=None):
        # تُرجع زبائن — فتمرّ بـ`visible_clients` كسائر النقاط (#272).
        return Response(
            services.clients_customized_payload(
                self.tenant, key, user=request.user,
            ),
        )


class OfficeServiceViewSet(OfficeModuleViewSet, viewsets.ModelViewSet):
    """كتالوج خدمات المكتب — **قراءةٌ لكل عضو، وكتابةٌ بـ`office.settings.manage`**.

    ولا `DELETE`: خدمةٌ استُعملت لا تُحذف أبداً (`ClientService.service` على
    `PROTECT`) — تُعطَّل فتُخفى من الإضافة ويبقى تاريخُ من اشتراها.
    """

    serializer_class = OfficeServiceSerializer
    # `delete` خارج القائمة: الـAPI لا يعرف حذف خدمة، والتعطيلُ هو الفعل.
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        return OfficeService.objects.filter(tenant=self.tenant).order_by(
            "position", "name", "id",
        )

    def list(self, request, *args, **kwargs):
        # القائمةُ تُزرع عند أوّل قراءة — فلا مكتبَ بكتالوجٍ فارغ.
        return Response(services.services_catalog_payload(self.tenant))

    def create(self, request, *args, **kwargs):
        self.require_settings_manage()
        serializer = OfficeServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = services.create_office_service(
            self.tenant, name=data.get("name", ""), position=data.get("position"),
        )
        return Response(
            OfficeServiceSerializer(row).data, status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        self.require_settings_manage()
        partial = kwargs.pop("partial", False)
        row = self.get_object()
        serializer = OfficeServiceSerializer(
            row, data=request.data, partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.update_office_service(
            row,
            name=data.get("name"),
            is_active=data.get("is_active"),
            position=data.get("position"),
        )
        return Response(OfficeServiceSerializer(row).data)


class OfficePackageViewSet(OfficeModuleViewSet, viewsets.ModelViewSet):
    """الباقات الجاهزة — **الحذفُ مباحٌ هنا وحده**: قالبٌ لا تاريخَ زبونٍ فيه.

    قراءةُ الباقة تمرّ بـ`package_payload`: `suggested_price` مبلغ، فيُقنَّع عن
    عضوٍ بلا `office.amounts.view`، وكتابتُه من دونه 403 (`reject_amount_writes`).
    """

    serializer_class = ServicePackageWriteSerializer

    def get_queryset(self):
        return ServicePackage.objects.filter(tenant=self.tenant).prefetch_related(
            "services",
        )

    def list(self, request, *args, **kwargs):
        return Response(services.packages_payload(self.tenant, user=request.user))

    def retrieve(self, request, *args, **kwargs):
        return Response(
            services.package_payload(self.get_object(), user=request.user),
        )

    def create(self, request, *args, **kwargs):
        self.require_settings_manage()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.reject_amount_writes(data)
        package = services.create_service_package(
            self.tenant,
            name=data.get("name", ""),
            suggested_price=data.get("suggested_price"),
            service_ids=data.get("services"),
        )
        return Response(
            services.package_payload(package, user=request.user),
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        self.require_settings_manage()
        partial = kwargs.pop("partial", False)
        package = self.get_object()
        serializer = self.get_serializer(
            data=request.data, partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.reject_amount_writes(data)
        # `suggested_price` تُمرَّر وحدها إن وصلت — `None` الواصلةُ تمسح السعر،
        # وغيابُها لا يمسّه (`_UNSET`).
        kwargs = {}
        if "suggested_price" in data:
            kwargs["suggested_price"] = data["suggested_price"]
        services.update_service_package(
            package,
            name=data.get("name"),
            service_ids=data.get("services"),
            **kwargs,
        )
        return Response(
            services.package_payload(package, user=request.user),
        )

    def destroy(self, request, *args, **kwargs):
        self.require_settings_manage()
        services.delete_service_package(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)
