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
import logging
import mimetypes

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import (
    MethodNotAllowed,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from accounting_office import (
    appointments,
    book_reports,
    client_books,
    deadlines,
    fee_invoices,
    fees,
    payments,
    services,
)
from accounting_office.models import (
    TAX_SYSTEM_CHOICES,
    ClientBook,
    ClientContact,
    ClientService,
    ClientServicePrice,
    Contact,
    DocumentChecklistItem,
    DocumentFile,
    FeeExtraService,
    FeeInvoice,
    FeeSubscription,
    FeeWriteOff,
    Obligation,
    OfficeAlert,
    OfficeClient,
    OfficeCustomRule,
    OfficeDocumentItem,
    OfficeHoliday,
    OfficeService,
    PeriodTask,
    ServicePackage,
)
from accounting_office.serializers import (
    ApplyPackageSerializer,
    BookAccountWriteSerializer,
    BookEntryReverseSerializer,
    BookEntryWriteSerializer,
    ClientBookKindWriteSerializer,
    ClientBookWriteSerializer,
    ClientAppointmentConfirmSerializer,
    ClientAppointmentRescheduleSerializer,
    ClientAppointmentWriteSerializer,
    ClientContactLinkSerializer,
    ClientContactRowSerializer,
    ClientEventSerializer,
    ClientServiceFrequencyWriteSerializer,
    ClientServiceStopSerializer,
    ClientServiceWriteSerializer,
    ClosePriorSerializer,
    ContactConsentSerializer,
    ContactSerializer,
    CustomRuleUpdateSerializer,
    CustomRuleWriteSerializer,
    DocumentFileUploadSerializer,
    DocumentItemChoiceSerializer,
    DocumentStatusSerializer,
    FeeDraftApproveSerializer,
    FeeDraftRowSerializer,
    FeeExtraServiceWriteSerializer,
    FeeInvoiceCancelSerializer,
    FeeInvoiceCreditNoteSerializer,
    FeeInvoiceRowSerializer,
    FeeInvoiceSupplementarySerializer,
    FeeLedgerQuerySerializer,
    FeePaymentWriteSerializer,
    FeeServicePriceWriteSerializer,
    FeeSubscriptionWriteSerializer,
    FeeWriteOffWriteSerializer,
    ObligationAmountSerializer,
    ObligationClientPaidSerializer,
    ObligationExtensionSerializer,
    ObligationSubmitSerializer,
    OfficeClientListSerializer,
    OfficeClientSerializer,
    OfficeDocumentItemUpdateSerializer,
    OfficeDocumentItemWriteSerializer,
    OfficeHolidayWriteSerializer,
    OfficeServiceSerializer,
    ReadyToSendDismissSerializer,
    ReadyToSendManualSerializer,
    ReadyToSendPayloadSerializer,
    ReadyToSendSentSerializer,
    ReminderLogSerializer,
    ReminderPostponeWriteSerializer,
    ReminderRecipientSerializer,
    ReminderTemplateWriteSerializer,
    RuleCodeSerializer,
    RuleOverrideSerializer,
    ServicePackageWriteSerializer,
    SettingValueSerializer,
    TaskAssignSerializer,
    TaxCardWriteSerializer,
)
from core.access import (
    OFFICE_CLIENTS_ASSIGN_KEY,
    OFFICE_CLIENTS_WRITE_KEY,
    OFFICE_SETTINGS_MANAGE_KEY,
    require_perm,
)
from core.api_defaults import ApiAuthAndUser
from core.media_views import (
    MediaUploadError,
    destroy_cloudinary_asset,
    stream_stored_asset,
    upload_media_file,
)
from core.modules import require_module

logger = logging.getLogger(__name__)

MODULE_KEY = "accounting_office"
#: أقصى سنةٍ تُطلب في شبكة الأوراق — حمايةٌ من مسحٍ بلا حدّ لا قاعدةَ بيانات.
DOCUMENT_YEAR_MIN = 2000
DOCUMENT_YEAR_MAX = 2100


def parse_iso_date(raw, field):
    """تاريخٌ مطلوبٌ بصيغة ISO — غيابُه أو فسادُه **400 بالحقل**.

    المساعدُ الوحيد لتاريخ الطلب في الموديول. و`parse_date("2026-02-30")` صحيحُ
    الشكل فاسدُ اليوم: يرمي `ValueError` بدل أن يُعيد `None`، وكان ذلك يصل 500
    على التقويم وعلى اقتراح الخدمة معاً — فيُلتقط هنا ويُحوَّل 400.
    """
    value = (raw or "").strip()
    if not value:
        raise ValidationError({field: "تاريخٌ مطلوبٌ بالصيغة YYYY-MM-DD."})
    try:
        day = parse_date(value)
    except ValueError:
        day = None
    if day is None:
        raise ValidationError({field: "تاريخٌ غير صالح — الصيغة YYYY-MM-DD."})
    return day


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
        """`ValidationError` من طبقة الخدمات خطأُ مدخلاتٍ (400) لا عطلُ خادم.

        **إلا زبونَ غيرك**: زبونٌ لا يراه العضو **404** لا 400 — 400 كان يقول
        «حمولتُك فاسدة» عن كائنٍ موجود، و404 لا يقول شيئاً (#272).
        """
        if isinstance(exc, services.ReminderClientNotVisible):
            return Response(
                {"detail": "الزبون غير موجود."},
                status=status.HTTP_404_NOT_FOUND,
            )
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
        # نظامُ كل صفٍّ و«اللي عليه» يُبنيان بضعةَ استعلاماتٍ ثابتةٍ للصفحة
        # (لا استعلامين لكل زبون)، ويُمرَّران في `context` صراحةً — لا سمةً على
        # الصنف تبقى بين الطلبات.
        context = {
            **self.get_serializer_context(),
            "tax_systems": services.resolve_setting_for_clients(
                self.tenant, services.TAX_SYSTEM_KEY, clients,
            ),
            # #283: مصدرُ «اللي عليه» الواحد (`payments.client_due`) مجمَّعاً.
            "client_dues": payments.client_dues_payload(
                self.tenant, clients, user=request.user,
            ),
        }
        serializer = self.get_serializer(clients, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def get_serializer_context(self):
        # `tenant` للحمولات التي تُحسب في المُسلسِل (حقلُ `due` وحده) — الشركةُ
        # من الطلب لا من صفٍّ يُقرأ استعلاماً لكل زبون.
        context = super().get_serializer_context()
        context["tenant"] = self.tenant
        return context

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
            client.contact_links
            .select_related("contact__consent_withdrawn_by")
            .order_by("-is_primary", "id"),
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
            ClientContact.objects
            .select_related("contact__consent_withdrawn_by")
            .get(pk=link.pk),
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

    @action(detail=True, methods=["get"], url_path="reminder-log")
    def reminder_log(self, request, pk=None):
        """سجلُّ التذكيرات لتبويب ملفّ الزبون (#280/D9).

        **`reminders/` مسارٌ آخر ومحجوز**: هو مستلِمو الأنواع الأربعة منذ #271،
        وسجلُّ التذكيرات جرحٌ مختلف — فلا يُكسَر مسارٌ قائمٌ ليحمل معنًى ثانياً.
        """
        return Response(services.client_reminder_log_payload(self.get_object()))

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
        on_date = parse_iso_date(raw_date, "on") if raw_date else None
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
            row,
            ends_on=serializer.validated_data["ends_on"],
            last_period_ours=serializer.validated_data["last_period_ours"],
        )
        return Response(services.client_services_payload(client, user=request.user))

    # ── الالتزامات والشغلات (#275) ───────────────────────────────────────
    @action(detail=True, methods=["get"], url_path="obligations")
    def client_obligations(self, request, pk=None):
        """شغلاتُ الزبون والتزاماتُها — **كلُّ الحالات**، والمبلغُ بالقناع."""
        client = self.get_object()
        return Response(services.client_obligations_payload(
            client, user=request.user, day=timezone.localdate(),
        ))

    # ── الأوراق: الشبكة والقائمة السنوية وخيار الزبون (#278) ──────────────
    @action(detail=True, methods=["get"], url_path="documents")
    def client_documents(self, request, pk=None):
        """`?year=YYYY` — شبكةُ الأشهر × البنود والقائمةُ السنوية. **قراءةٌ خالصة**.

        الصفوفُ تُولَّد في «حدّث المكتب» لا هنا: طلبُ الشبكة لا يكتب صفّاً، فسنةٌ
        لم يحن وقتُها تعود فارغةً بلا أن تخترع ورقةً لم تُطلب بعد.
        """
        client = self.get_object()
        return Response(services.client_documents_payload(
            client, year=self._document_year(request),
        ))

    @action(detail=True, methods=["post"], url_path="document-choice")
    def document_choice(self, request, pk=None):
        """خيارُ الزبون على بند — **يغلب قالبَ المكتب وشروطَ القانون**.

        الرؤيةُ أوّلاً (`get_object` عبر `visible_clients`) فيأخذ من لا يرى الزبون
        **404**، ثم مفتاحُ الكتابة فيأخذ القارئُ 403. ويُرجع خيارَه وحده مع
        بنود نظامه المحدَّثة، فلا تُعاد الشبكةُ كلُّها بعد كبسةٍ واحدة.
        """
        client = self.get_object()
        self.require_write()
        serializer = DocumentItemChoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.set_client_document_choice(
            client,
            item_code=data["item_code"],
            included=data["included"],
            actor=request.user,
        )
        payload = {
            "item_code": data["item_code"],
            "included": data["included"],
            "items": [],
        }
        system = services.resolve_setting(
            self.tenant, services.TAX_SYSTEM_KEY, client=client,
        )
        if system:
            payload["items"] = services.document_items_payload(
                self.tenant, tax_system=system, client=client,
            )["items"]
        return Response(payload)

    def _document_year(self, request):
        """السنةُ المطلوبة — الغيابُ سنةُ اليوم، وغيرُ الرقم 400 لا 500."""
        raw = (request.query_params.get("year") or "").strip()
        if not raw:
            return timezone.localdate().year
        try:
            year = int(raw)
        except (TypeError, ValueError):
            raise ValidationError({"year": "السنة بصيغة YYYY."}) from None
        if not DOCUMENT_YEAR_MIN <= year <= DOCUMENT_YEAR_MAX:
            raise ValidationError({
                "year": (
                    f"سنةٌ خارج المدى — بين {DOCUMENT_YEAR_MIN} و"
                    f"{DOCUMENT_YEAR_MAX}."
                ),
            })
        return year

    # ── الأحداث (#277) ──────────────────────────────────────────────────
    @action(detail=True, methods=["get", "post"], url_path="events")
    def events(self, request, pk=None):
        """«صار حدث»: `GET` أحداثُ الزبون، و`POST` يسجّل حدثاً ويولّد التزامَه.

        الرؤيةُ أوّلاً (`get_object` عبر `visible_clients`) فيأخذ من لا يرى الزبون
        **404**، ثم مفتاحُ الكتابة فيأخذ القارئُ 403. والكتابةُ تعيد الحدثَ
        والتزاماتِه الجديدة (`{event, obligations}`) لا القائمةَ كلَّها.
        """
        client = self.get_object()
        if request.method == "GET":
            return Response(services.client_events_payload(client, user=request.user))
        self.require_write()
        serializer = ClientEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        event, obligations = services.record_client_event(
            client,
            kind=data["kind"],
            occurred_on=data["occurred_on"],
            note=data.get("note", ""),
            actor=request.user,
        )
        return Response(
            {
                "event": services.client_event_row(
                    event, client=client, user=request.user,
                ),
                "obligations": [
                    services.obligation_row(
                        obligation,
                        day=timezone.localdate(),
                        masked=not services.can_see_amounts(self.tenant, request.user),
                    )
                    for obligation in obligations
                ],
            },
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True, methods=["post"], url_path="obligations/close-prior",
    )
    def close_prior(self, request, pk=None):
        """«هدول انقدّموا قبل ما يجي علينا» — تُرجع عددَ ما أُغلق."""
        client = self.get_object()
        self.require_write()
        serializer = ClosePriorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        closed = services.close_prior_obligations(
            client,
            before=serializer.validated_data.get("before") or timezone.localdate(),
            actor=request.user,
        )
        return Response({"closed": closed})

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
        queryset = services.visible_contacts(
            self.tenant, self.request.user,
        ).select_related("consent_withdrawn_by")
        if self.action == "list":
            term = (self.request.query_params.get("q") or "").strip()
            if term:
                queryset = queryset.filter(
                    Q(name__icontains=term) | Q(phone__icontains=term),
                )
        return queryset.order_by("name", "id")

    def perform_create(self, serializer):
        self.require_write()
        # #280/D2: الجهةُ الجديدة تأخذ أنواعَ الإذن الافتراضية للمكتب — من الخدمة
        # لا من مُسلسِلٍ يقرأ إعداداً (حراسةُ `test_settings_guard.py`).
        contact = services.create_contact(
            self.tenant,
            name=serializer.validated_data.get("name", ""),
            phone=serializer.validated_data.get("phone", ""),
            language=serializer.validated_data.get("language") or Contact.LANGUAGE_ARABIC,
        )
        serializer.instance = contact

    def perform_update(self, serializer):
        self.require_write()
        serializer.save()

    @action(detail=True, methods=["get", "post"], url_path="consent")
    def consent(self, request, pk=None):
        """`GET` جوابُ الإذن، و`POST` يُسجّله بتاريخه — بمفتاح الكتابة نفسه."""
        contact = self.get_object()
        if request.method == "POST":
            self.require_write()
            serializer = ContactConsentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            services.set_contact_consent(
                contact,
                consent=serializer.validated_data["consent"],
                types=serializer.validated_data.get("types"),
                channel=serializer.validated_data.get("channel", ""),
                actor=request.user,
            )
        return Response(services.contact_consent_payload(contact))

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


# ── التقويم ولائحة المواعيد (#274) ───────────────────────────────────────────
class OfficeCalendarViewSet(OfficeModuleViewSet):
    """تقويمُ المواعيد — **قراءةٌ خالصة، ولا سطرَ يُحفظ**.

    المواعيدُ محسوبةٌ من لائحة المنصّة عند كل طلب (`services.client_deadlines`)،
    فلا شيءَ يُولَّد ولا وظيفةٌ خلفية: تعديلُ سطرٍ في اللائحة يغيّر التقويمَ في
    الطلب التالي فوراً. ولا استدعاءَ لـ`ensure_default_services` هنا — تلك تكتب.

    والزبائنُ من `visible_clients` وحدها، فلا يظهر زبونُ غيرك. والمدى محدودٌ:
    ≤ 62 يوماً، ولا يتجاوز `today + calendar_months_ahead` شهراً — طلبٌ يخرج عنهما
    **400** لا تقويمَ مقتطعاً بلا أن يقول.
    """

    http_method_names = ["get", "head", "options"]

    def list(self, request, *args, **kwargs):
        params = request.query_params
        start = parse_iso_date(params.get("from"), "from")
        end = parse_iso_date(params.get("to"), "to")
        if end < start:
            raise ValidationError({"to": "نهاية المدى قبل بدايته."})
        if (end - start).days > services.CALENDAR_MAX_SPAN_DAYS:
            raise ValidationError({
                "to": (
                    f"أقصى مدىً للتقويم {services.CALENDAR_MAX_SPAN_DAYS} يوماً — "
                    "اقصر المدى أو قسّمه."
                ),
            })

        today = timezone.localdate()
        months_ahead = services.resolve_setting(self.tenant, "calendar_months_ahead") or 0
        if end > deadlines.add_months(today, months_ahead):
            raise ValidationError({
                "to": "المدى يتجاوز أفق التقويم المضبوط في إعدادات المكتب.",
            })

        return Response(services.calendar_payload(
            self.tenant,
            user=request.user,
            start=start,
            end=end,
            client=self._id(params.get("client"), "client"),
            member=self._id(params.get("member"), "member"),
            rule_code=(params.get("rule") or "").strip(),
            today=today,
        ))

    def _id(self, raw, field):
        value = (raw or "").strip()
        if not value:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValidationError({field: "معرّفٌ غير صالح."}) from None


class OfficeDeadlineRuleViewSet(OfficeModuleViewSet):
    """أسطرُ اللائحة السارية لكل سنة — للفلتر، ولعرض اللائحة وتعديلها (#277).

    القراءةُ مفتوحةٌ لكل عضو (يكفيها الترخيص)، و**الكتابةُ بمفتاح
    `office.settings.manage`**: تعديلُ سطرٍ يسري على كل زبائن المكتب، فليس فعلاً
    لكل من يكتب زبوناً.
    """

    http_method_names = ["get", "post", "head", "options"]
    serializer_class = RuleOverrideSerializer

    def list(self, request, *args, **kwargs):
        system = (request.query_params.get("system") or "").strip()
        if system not in {value for value, _label in TAX_SYSTEM_CHOICES}:
            raise ValidationError({"system": "النظام الضريبي مطلوب: PS أو IL."})
        return Response(services.deadline_rules_payload(system, tenant=self.tenant))

    def _body(self, serializer_class):
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @action(detail=False, methods=["post"], url_path="override")
    def override(self, request):
        """`{system, code, rule_day?, rule_month?, electronic_extension_days?, note}`."""
        require_perm(request, OFFICE_SETTINGS_MANAGE_KEY, tenant=self.tenant)
        data = self._body(RuleOverrideSerializer)
        return Response(services.set_rule_override(
            self.tenant,
            tax_system=data["system"],
            rule_code=data["code"],
            rule_day=data.get("rule_day"),
            rule_month=data.get("rule_month"),
            electronic_extension_days=data.get("electronic_extension_days"),
            note=data.get("note", ""),
            actor=request.user,
        ))

    @action(detail=False, methods=["post"], url_path="clear-override")
    def clear_override(self, request):
        """«تأخذ الجديد»: صفُّ `cleared` — **لا حذفَ لسجلّ التعديل**."""
        require_perm(request, OFFICE_SETTINGS_MANAGE_KEY, tenant=self.tenant)
        data = self._body(RuleCodeSerializer)
        return Response(services.clear_rule_override(
            self.tenant,
            tax_system=data["system"],
            rule_code=data["code"],
            actor=request.user,
        ))

    @action(detail=False, methods=["post"], url_path="keep-override")
    def keep_override(self, request):
        """«أُبقي تاريخي»: صفٌّ بالقيم نفسها ولقطةٍ من النسخة السارية."""
        require_perm(request, OFFICE_SETTINGS_MANAGE_KEY, tenant=self.tenant)
        data = self._body(RuleCodeSerializer)
        return Response(services.keep_rule_override(
            self.tenant,
            tax_system=data["system"],
            rule_code=data["code"],
            actor=request.user,
        ))


class OfficeCustomRuleViewSet(OfficeModuleViewSet):
    """التزاماتُ المكتب الخاصة (#277) — **قراءةً وكتابةً بمفتاح الإعدادات**.

    القرارُ قرارُ مكتبٍ لا سطرُ بيانات زبون، فحتى قراءتُه لصاحب الصلاحية وحده
    (`office.settings.manage`) كما في موجز #277 §7. **ولا حذف**: التعطيلُ
    (`PATCH is_active=false`) يوقف توليد الفترات الجديدة، وما وُلد يبقى بتاريخه —
    و`delete` خارج `http_method_names` فيردّ الـview 405.
    """

    http_method_names = ["get", "post", "patch", "head", "options"]
    serializer_class = CustomRuleWriteSerializer

    def list(self, request, *args, **kwargs):
        self.require_settings_manage()
        return Response(services.custom_rules_payload(self.tenant))

    def create(self, request, *args, **kwargs):
        self.require_settings_manage()
        serializer = CustomRuleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.create_custom_rule(
            self.tenant,
            name=data["name"],
            service=services.service_or_raise(self.tenant, data["service"]),
            cadence=data["cadence"],
            rule_kind=data["rule_kind"],
            rule_day=data.get("rule_day"),
            rule_month=data.get("rule_month"),
            is_active=data.get("is_active", True),
            actor=request.user,
            day=timezone.localdate(),
        )
        return Response(
            services.custom_rules_payload(self.tenant),
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        self.require_settings_manage()
        row = self._row(kwargs.get("pk"))
        serializer = CustomRuleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        service = self.request.data.get("service")
        services.update_custom_rule(
            row,
            name=data.get("name"),
            service=(
                None if service is None
                else services.service_or_raise(self.tenant, data["service"])
            ),
            cadence=data.get("cadence"),
            rule_kind=data.get("rule_kind"),
            is_active=data.get("is_active"),
            **{
                key: data[key]
                for key in ("rule_day", "rule_month")
                if key in self.request.data
            },
            actor=request.user,
            day=timezone.localdate(),
        )
        return Response(services.custom_rules_payload(self.tenant))

    def _row(self, pk):
        row = (
            OfficeCustomRule.objects
            .select_related("service")
            .filter(tenant=self.tenant, pk=pk)
            .first()
        )
        if row is None:
            raise NotFound("التزامُ المكتب هذا غير موجود.")
        return row


# ── «اليوم» والالتزامات والشغلات (#275) ──────────────────────────────────────
class OfficeTodayViewSet(OfficeModuleViewSet):
    """شاشةُ «اليوم» — **تشغيلٌ يوميٌّ ثم قراءة**.

    أوّلُ فتحٍ في اليوم يشغّل `ensure_office_refreshed(day=localdate)`: مكتبٌ لم
    يعمل عليه cron الخادم بعد يرى ما حان وقتُه عند أول فتح، والفتحُ الثاني في
    اليوم نفسه لا يعمل شيئاً (سجلُّ `OfficeRefreshRun`). والفلاترُ تُتحقَّق في
    `today_payload` — غيرُ المعروف **400** لا كلُّ الصفوف.
    """

    http_method_names = ["get", "head", "options"]

    def list(self, request, *args, **kwargs):
        today = timezone.localdate()
        services.ensure_office_refreshed(self.tenant, day=today)
        return Response(services.today_payload(
            self.tenant,
            user=request.user,
            day=today,
            filter=(request.query_params.get("filter") or "").strip(),
        ))


class OfficeObligationViewSet(OfficeModuleViewSet):
    """أفعالُ الالتزام — **كلُّ كائنٍ عبر `visible_clients`**، وكلُّ كتابةٍ بمفتاحها.

    الترتيبُ في كلّ فعل: `get_object` أوّلاً (فالتزامُ غيرك **404** لا 403)، ثم المفتاح:
    الحالةُ و«الزبون دفع» بـ`office.clients.write`، **والمبلغُ معه
    `office.amounts.view`** (403 بلا المفتاحين — كسعر الباقة المقترح).
    """

    http_method_names = ["post", "head", "options"]
    # `get_serializer_class` يحتاجه `OPTIONS` (SimpleMetadata) وإلا سقط 500.
    serializer_class = ObligationSubmitSerializer

    def get_queryset(self):
        return (
            Obligation.objects
            .filter(client__in=services.visible_clients(
                self.tenant, self.request.user,
            ).values("pk"))
            .select_related("client__responsible", "task", "task__assignee")
        )

    def get_object(self):
        obligation = self.get_queryset().filter(pk=self.kwargs.get("pk")).first()
        if obligation is None:
            raise NotFound("الالتزام غير موجود.")
        return obligation

    def _row(self, obligation):
        return Response(services.obligation_row(
            obligation,
            day=timezone.localdate(),
            masked=not services.can_see_amounts(self.tenant, self.request.user),
        ))

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        obligation = self.get_object()
        self.require_write()
        serializer = ObligationSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.submit_obligation(
            obligation,
            actor=request.user,
            submitted_on=serializer.validated_data.get("submitted_on"),
            number=serializer.validated_data.get("number", ""),
        )
        return self._row(obligation)

    @action(detail=True, methods=["post"], url_path="not-required")
    def not_required(self, request, pk=None):
        obligation = self.get_object()
        self.require_write()
        services.mark_obligation_not_required(obligation, actor=request.user)
        return self._row(obligation)

    @action(detail=True, methods=["post"], url_path="reopen")
    def reopen(self, request, pk=None):
        obligation = self.get_object()
        self.require_write()
        services.reopen_obligation(obligation, actor=request.user)
        return self._row(obligation)

    @action(detail=True, methods=["post"], url_path="amount")
    def amount(self, request, pk=None):
        """المبلغُ يحتاج مفتاحي الكتابة **ورؤية المبالغ** — وإلا 403.

        والترتيب: الرؤيةُ (404 لغيرك)، ثم مفتاحُ الكتابة، ثم قرارُ القناع على
        الجسم نفسه — فلا يُقاس مبلغٌ لعضوٍ لا يملك كتابةً أصلاً.
        """
        obligation = self.get_object()
        self.require_write()
        # `reject_amount_writes` يقارن `AMOUNT_KEYS`: من لا يرى المبلغ لا يكتبه.
        self.reject_amount_writes(request.data)
        serializer = ObligationAmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_obligation_amount(
            obligation,
            amount=serializer.validated_data.get("amount"),
            direction=serializer.validated_data.get("direction", ""),
        )
        return self._row(obligation)

    @action(detail=True, methods=["post"], url_path="client-paid")
    def client_paid(self, request, pk=None):
        obligation = self.get_object()
        self.require_write()
        serializer = ObligationClientPaidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_obligation_client_paid(
            obligation, paid=serializer.validated_data["paid"],
        )
        return self._row(obligation)

    # ── التمديد (#277) ──────────────────────────────────────────────────
    @action(detail=True, methods=["post"], url_path="extend")
    def extend(self, request, pk=None):
        """«مدّد»: تاريخٌ + ملاحظة ⇒ `due_date` يتحرّك والأحمرُ معه."""
        obligation = self.get_object()
        self.require_write()
        serializer = ObligationExtensionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.extend_obligation(
            obligation,
            until=serializer.validated_data["until"],
            note=serializer.validated_data["note"],
            actor=request.user,
        )
        return self._row(obligation)

    @action(detail=True, methods=["post"], url_path="clear-extension")
    def clear_extension(self, request, pk=None):
        """«ألغِ التمديد»: يرجع إلى الموعد الفعليّ بصفٍّ في سجلّ التغيّر."""
        obligation = self.get_object()
        self.require_write()
        services.clear_obligation_extension(obligation, actor=request.user)
        return self._row(obligation)


class OfficeTaskViewSet(OfficeModuleViewSet):
    """تحويلُ شغلةِ فترةٍ لعضو — بمفتاح `office.clients.assign` وحده.

    الشغلةُ تُحلّ عبر `visible_clients` (شغلةُ زبونٍ لا تراه **404**)، ثم
    المفتاح: من يكتب بيانات زبونٍ لا يسلب شغلتَه بضغطة.
    """

    http_method_names = ["post", "head", "options"]
    serializer_class = TaskAssignSerializer

    def get_queryset(self):
        return (
            PeriodTask.objects
            .filter(client__in=services.visible_clients(
                self.tenant, self.request.user,
            ).values("pk"))
            .select_related(
                "assignee", "client__responsible", "client_service__service",
            )
        )

    def get_object(self):
        task = self.get_queryset().filter(pk=self.kwargs.get("pk")).first()
        if task is None:
            raise NotFound("شغلة الفترة غير موجودة.")
        return task

    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request, pk=None):
        # الرؤيةُ أوّلاً (`get_object` عبر `visible_clients`) فيأخذ من لا يرى
        # الشغلة **404**، ثم المفتاحُ فيأخذ من يراها ولا يملكه 403.
        task = self.get_object()
        require_perm(request, OFFICE_CLIENTS_ASSIGN_KEY, tenant=self.tenant)
        serializer = TaskAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data.get("assignee")
        target = None
        if user_id is not None:
            target = get_user_model().objects.filter(
                pk=user_id, is_active=True,
            ).first()
            if target is None:
                raise ValidationError({"assignee": "لا يوجد مستخدم مفعَّل بهذا المعرّف."})
        services.assign_task(task, assignee=target)
        return Response(services.task_row(task))


# ── الجرس (#276) ─────────────────────────────────────────────────────────────
class OfficeAlertsViewSet(OfficeModuleViewSet):
    """جرسُ التنبيهات — **كلُّ عضوٍ يرى تنبيهاته هو فقط**: لا مفتاحَ إضافياً.

    الكائنُ يُحلّ بمستلِمِه هو (`recipient=request.user`) داخل شركة الطلب، فتنبيهُ
    غيرك — أو تنبيهُ مكتبٍ آخر — **404** لا 403. والقراءةُ تُسقط المحسوم
    (`alerts_payload`) ولا تحذف صفّاً؛ و«شفته» يُنقص العدّاد.
    """

    http_method_names = ["get", "post", "head", "options"]
    # الأفعالُ هنا بلا جسمٍ يُسلسَل؛ الصنفُ الفارغُ يلزم `SimpleMetadata` في OPTIONS
    # (وإلا سقط `get_serializer` على `serializer_class` الغائب).
    serializer_class = serializers.Serializer

    def list(self, request, *args, **kwargs):
        # الجرسُ لا ينتظر أن يفتح أحدٌ «اليوم»: cron فاتَه يومٌ ⇒ يلحقه أولُ فتحٍ هنا.
        # وفي اليوم المسجَّل استعلامُ وجودٍ واحد (`OfficeRefreshRun`).
        today = timezone.localdate()
        services.ensure_office_refreshed(self.tenant, day=today)
        return Response(services.alerts_payload(
            self.tenant, user=request.user, day=today,
        ))

    def get_object(self):
        alert = (
            OfficeAlert.objects
            .filter(
                tenant=self.tenant,
                recipient=self.request.user,
                pk=self.kwargs.get("pk"),
            )
            .select_related("client")
            .first()
        )
        if alert is None:
            raise NotFound("التنبيه غير موجود.")
        return alert

    @action(detail=True, methods=["post"], url_path="seen")
    def seen(self, request, pk=None):
        """«شفته» — يُرجع السطرَ المحدَّث (`seen: true`) لا عدّاداً فقط."""
        alert = self.get_object()
        services.mark_alert_seen(alert, user=request.user)
        return Response(services.alert_row(alert))

    @action(detail=False, methods=["post"], url_path="seen-all")
    def seen_all(self, request):
        """«شفتهم كلهم» — `{"seen": n}` عددُ ما كُتب له وقتُ الشوفة."""
        return Response({
            "seen": services.mark_all_alerts_seen(
                self.tenant, user=request.user, day=timezone.localdate(),
            ),
        })


# ── قائمة الأوراق وشبكة الأشهر (#278) ───────────────────────────────────────
#
# **كلُّ صفٍّ يُحلّ عبر `visible_clients`**: صفُّ ورقةِ زميلٍ أو مكتبٍ آخر **404**
# لا 403 — ثم مفتاحُ `office.clients.write` للكتابة. **ورفعُ الملف أو حذفُه لا
# يمسّ الحالة**: الحالةُ تصريحُ موظّف، والملفُّ كيانٌ آخر (بحث #260 §5.4).
class OfficeDocumentViewSet(OfficeModuleViewSet):
    """صفوفُ الأوراق: تسجيلُ الحالة، وملفاتُ الورقة (قراءةً ورفعاً)."""

    http_method_names = ["get", "post", "head", "options"]
    # `get_serializer_class` يحتاجه `OPTIONS` (SimpleMetadata) وإلا سقط 500.
    serializer_class = DocumentStatusSerializer
    # الحالةُ JSON والملفُّ multipart — القائمةُ تضمّ الاثنين لأن الفعلين في
    # الـViewSet نفسه، ولكلٍّ جسمُه.
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return (
            DocumentChecklistItem.objects
            .filter(
                tenant=self.tenant,
                client__in=services.visible_clients(
                    self.tenant, self.request.user,
                ).values("pk"),
            )
            .select_related("client", "received_by", "updated_by")
        )

    def get_object(self):
        row = self.get_queryset().filter(pk=self.kwargs.get("pk")).first()
        if row is None:
            raise NotFound("الورقة غير موجودة.")
        return row

    @action(detail=True, methods=["post"], url_path="status")
    def document_status(self, request, pk=None):
        """`{status, channel?}` — «وصلت» و«وصلت ناقصة» بلا قناةٍ **400**.

        الرؤيةُ أوّلاً (`get_object`) ثم المفتاح: ورقةُ غيرك 404، وقراءةُ عضوٍ
        بلا `office.clients.write` على ورقةٍ يراها 403.
        """
        row = self.get_object()
        self.require_write()
        serializer = DocumentStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_document_status(
            row,
            status=serializer.validated_data["status"],
            channel=serializer.validated_data.get("channel", ""),
            actor=request.user,
            day=timezone.localdate(),
        )
        row.refresh_from_db()
        return Response(services.document_row_payload(row))

    @action(detail=True, methods=["get", "post"], url_path="files")
    def files(self, request, pk=None):
        """`GET` ملفاتُ الورقة، و`POST` رفعٌ multipart بحقول נספח ז.

        **الرابطُ لا يخرج**: الحمولةُ تُبنى بـ`document_file_payload` وحدها.
        """
        row = self.get_object()
        if request.method == "GET":
            return Response([
                services.document_file_payload(file)
                for file in row.files.select_related("created_by").order_by(
                    "-captured_at", "-id",
                )
            ])
        self.require_write()
        serializer = DocumentFileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        upload = data.pop("file")
        # الحجمُ يُفحص **قبل** أي قراءة: ملفٌّ فوق السقف لا يدخل الذاكرة أصلاً.
        size = getattr(upload, "size", 0)
        services.validate_document_size(size=size)
        # ثم رأسٌ بطول البايتات المميّزة للتحقّق من المحتوى، ويُعاد المؤشّر للرفع.
        head = upload.read(services.DOCUMENT_MAGIC_BYTES)
        upload.seek(0)
        services.validate_document_upload(
            size=size,
            filename=getattr(upload, "name", "") or "",
            content_type=getattr(upload, "content_type", "") or "",
            head=head,
        )
        try:
            file_url = upload_media_file(
                upload,
                folder=services.DOCUMENT_UPLOAD_FOLDER,
                tenant=self.tenant,
                uploaded_by=request.user,
            )
        except MediaUploadError as exc:
            # 400 (حجمٌ أو سقفُ تخزين الخطّة) نصُّه مكتوبٌ لمستخدم الشركة فيُردّ كما هو؛
            # وغيرُه (502 مزوّد، 503 غير مهيّأ) قد يحمل نصَّ المورّد — للسجلّ لا للردّ.
            logger.warning(
                "accounting_office document upload failed row=%s err=%s",
                row.pk, exc.detail,
            )
            return Response(
                {
                    "file": exc.detail
                    if exc.status_code == status.HTTP_400_BAD_REQUEST
                    else "تعذّر رفع الملف. حاول مرة أخرى.",
                },
                status=exc.status_code,
            )
        try:
            file_row = services.create_document_file(
                row,
                file_url=file_url,
                file_name=getattr(upload, "name", "") or "",
                data=data,
                actor=request.user,
            )
        except Exception:
            # الصفُّ لم يُحفظ: الأصلُ المرفوع صار يتيماً في التخزين — يُمحى ثم يُرفع الخطأ.
            destroy_cloudinary_asset(file_url)
            raise
        return Response(
            services.document_file_payload(file_row),
            status=status.HTTP_201_CREATED,
        )


class OfficeDocumentFileViewSet(OfficeModuleViewSet):
    """ملفاتُ الأوراق: التقديمُ بايتاتٍ والحذف — **ولا رابطَ تخزينٍ في أيّ ردّ**.

    `download` قراءةٌ لكل من يرى الزبون، و`destroy` بمفتاح الكتابة. والحذفُ يمحو
    الصفَّ **أوّلاً** ثم الأصلَ من التخزين بجهدٍ بذل (`destroy_cloudinary_asset`)
    — والحالةُ لا تتغيّر.
    """

    http_method_names = ["get", "delete", "head", "options"]
    serializer_class = DocumentFileUploadSerializer

    def get_queryset(self):
        return DocumentFile.objects.filter(
            tenant=self.tenant,
            client__in=services.visible_clients(
                self.tenant, self.request.user,
            ).values("pk"),
        )

    def get_object(self):
        row = self.get_queryset().select_related("client").filter(
            pk=self.kwargs.get("pk"),
        ).first()
        if row is None:
            raise NotFound("الملف غير موجود.")
        return row

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        """بايتاتٌ لا تحويل: رابطُ التخزين يبقى على الخادم."""
        file_row = self.get_object()
        safe_name = (file_row.file_name or "file").replace('"', "").replace("\\", "")
        return stream_stored_asset(
            file_row.file_url,
            filename=safe_name,
            content_type_fallback=(
                mimetypes.guess_type(file_row.file_name)[0]
                or "application/octet-stream"
            ),
            owner="office_document_file",
            owner_pk=file_row.pk,
        )

    def destroy(self, request, *args, **kwargs):
        file_row = self.get_object()
        self.require_write()
        url = services.delete_document_file(file_row)
        destroy_cloudinary_asset(url)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OfficeDocumentItemViewSet(OfficeModuleViewSet):
    """قالبُ الأوراق: بنداتُ المنصّة وقائمةُ المكتب وخيارُ «ضمن القائمة».

    **القراءةُ لكل عضو** (ملفُّ الزبون يعرض اللوحة لمن يكتب)، و**الكتابةُ
    بمفتاح `office.settings.manage`** كـ`OfficeCustomRuleViewSet`: من يكتب
    بياناتِ زبونٍ لا يغيّر قائمةَ أوراق المكتب كلّه. ولا حذف: التعطيلُ
    (`PATCH is_active=false`) يوقف التوليدَ ويُبقي ما وُلد.
    """

    http_method_names = ["get", "post", "patch", "head", "options"]
    serializer_class = OfficeDocumentItemWriteSerializer

    def list(self, request, *args, **kwargs):
        system = (request.query_params.get("system") or "").strip()
        if system not in {value for value, _label in TAX_SYSTEM_CHOICES}:
            raise ValidationError({"system": "النظام الضريبي مطلوب: PS أو IL."})
        return Response(services.document_items_payload(
            self.tenant,
            tax_system=system,
            client=self._client(request.query_params.get("client")),
        ))

    def get_object(self):
        row = OfficeDocumentItem.objects.filter(
            tenant=self.tenant, pk=self.kwargs.get("pk"),
        ).first()
        if row is None:
            raise NotFound("بند الأوراق غير موجود.")
        return row

    def create(self, request, *args, **kwargs):
        self.require_settings_manage()
        serializer = OfficeDocumentItemWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.create_office_document_item(
            self.tenant,
            tax_system=data["system"],
            name=data["name"],
            cadence=data["cadence"],
            service_codes=data.get("service_codes"),
            is_active=data.get("is_active", True),
            actor=request.user,
        )
        return Response(
            services.document_items_payload(
                self.tenant, tax_system=data["system"],
            ),
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        self.require_settings_manage()
        row = self.get_object()
        serializer = OfficeDocumentItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.update_office_document_item(
            row,
            name=data.get("name"),
            cadence=data.get("cadence"),
            service_codes=data.get("service_codes"),
            is_active=data.get("is_active"),
        )
        return Response(
            services.document_items_payload(
                self.tenant, tax_system=row.tax_system,
            ),
        )

    @action(detail=False, methods=["post"], url_path="choice")
    def choice(self, request):
        """`{item_code, included}` — «ضمن القائمة» على بندٍ في قالب المكتب."""
        self.require_settings_manage()
        serializer = DocumentItemChoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.set_office_document_choice(
            self.tenant,
            item_code=data["item_code"],
            included=data["included"],
            actor=request.user,
        )
        # الردُّ قائمةَ النظام المحدَّثة: الشاشةُ تستبدل حالتها بردّ الخادم، فلا
        # تُعيد قراءةً ثانية بعد كل قلبة.
        payload = {"item_code": data["item_code"], "included": data["included"]}
        system = services.document_item_system(self.tenant, data["item_code"])
        if system:
            payload.update(
                services.document_items_payload(self.tenant, tax_system=system),
            )
        return Response(payload)

    def _client(self, raw):
        """زبونُ لوح «تخصيص القائمة» — من `visible_clients` وحدها، وغيابُه `None`."""
        value = (raw or "").strip()
        if not value:
            return None
        try:
            pk = int(value)
        except (TypeError, ValueError):
            raise ValidationError({"client": "معرّفُ زبونٍ غير صالح."}) from None
        client = services.visible_clients(
            self.tenant, self.request.user,
        ).filter(pk=pk).first()
        if client is None:
            raise NotFound("الزبون غير موجود.")
        return client


# ── التذكيرات والرسائل (#280) ────────────────────────────────────────────────
class OfficeReminderTemplateViewSet(OfficeModuleViewSet):
    """نصوصُ التذكير: **قراءةٌ لكل عضو، وكتابةٌ بمفتاح الإعدادات**.

    والقراءةُ ليست ترفاً: من يرسل يقرأ ما سيرسل. والكتابةُ قرارُ مكتبٍ لا قرارُ
    موظّف — ومن يكتب بيانات الزبائن لا يغيّر نصّاً يخرج باسم المكتب.
    """

    # لا `POST` ولا `PATCH`: البديلُ يُكتب بـ`PUT` على (النوع، اللغة) ويُحذف.
    http_method_names = ["get", "put", "delete", "head", "options"]
    serializer_class = ReminderTemplateWriteSerializer

    def list(self, request, *args, **kwargs):
        return Response(services.reminder_templates_payload(self.tenant))

    @action(
        detail=False, methods=["put", "delete"],
        url_path=r"(?P<reminder_type>[a-z_]+)/(?P<language>[a-z]{2})",
    )
    def template(self, request, reminder_type=None, language=None):
        self.require_settings_manage()
        if request.method == "DELETE":
            services.reset_reminder_template(
                self.tenant, reminder_type=reminder_type, language=language,
            )
        else:
            serializer = ReminderTemplateWriteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            services.set_reminder_template(
                self.tenant,
                reminder_type=reminder_type,
                language=language,
                body=serializer.validated_data["body"],
                actor=request.user,
            )
        return Response(services.reminder_templates_payload(self.tenant))


class OfficeReadyToSendViewSet(OfficeModuleViewSet):
    """«جاهز للإرسال»: القائمةُ المحسوبة وأفعالُها الأربعة.

    **الترتيبُ في كل فعل:** مفتاحُ الكتابة أوّلاً (403)، ثم البنودُ عبر
    `visible_clients` في الخدمة (زبونُ غيرك 404)، ثم الحمولة. فالبنودُ تُحلّ
    داخل الخدمة لا هنا، ومفتاحُ الكتابة لا ينتظر حلَّها — وهذا خلافُ `undo` في
    السجلّ الذي يُحلّ كائنَه أوّلاً (404) ثم يسأل عن المفتاح، لأن السطرَ كائنٌ
    واحدٌ يُقرأ قبل الفعل.
    و`day` يُقرأ من الاستعلام للقائمة وحدها (فالاختبار لا ينتظر ساعة)، ولا
    يُمرَّر في الأفعال — ساعتُها اليوم، ويومُ الصفّ المحفوظ `created_at`.
    """

    http_method_names = ["get", "post", "head", "options"]
    # `get_serializer_class` يحتاجه `OPTIONS` (SimpleMetadata) وإلا سقط 500.
    serializer_class = ReadyToSendPayloadSerializer

    def list(self, request, *args, **kwargs):
        raw_day = (request.query_params.get("day") or "").strip()
        day = parse_iso_date(raw_day, "day") if raw_day else timezone.localdate()
        reminder_type = (request.query_params.get("reminder_type") or "").strip() or None
        raw_assignee = (request.query_params.get("assignee") or "").strip()
        assignee = None
        if raw_assignee:
            try:
                assignee = int(raw_assignee)
            except ValueError:
                raise ValidationError({"assignee": "معرّفُ موظّفٍ غير صالح."}) from None
        return Response(services.ready_to_send_payload(
            self.tenant,
            user=request.user,
            day=day,
            reminder_type=reminder_type,
            assignee=assignee,
        ))

    def _rows_response(self, rows):
        return Response(
            {"rows": [services.reminder_log_row(row) for row in rows]},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="sent")
    def sent(self, request):
        """«انبعثت»: صفُّ `sent` لكل بندٍ بالنصّ نفسه."""
        self.require_write()
        serializer = ReadyToSendSentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return self._rows_response(services.mark_reminders_sent(
            self.tenant,
            user=request.user,
            contact_id=data["contact_id"],
            body=data.get("body", ""),
            channel=data.get("channel", ""),
            items=[dict(item) for item in data["items"]],
        ))

    @action(detail=False, methods=["post"], url_path="manual")
    def manual(self, request):
        """«كلّمناه»: تلفون أو زيارة — والعدُّ في الحدّ الأقصى واحد."""
        self.require_write()
        serializer = ReadyToSendManualSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return self._rows_response(services.mark_reminders_manual(
            self.tenant,
            user=request.user,
            contact_id=data["contact_id"],
            body=data.get("body", ""),
            channel=data["channel"],
            items=[dict(item) for item in data["items"]],
        ))

    @action(detail=False, methods=["post"], url_path="dismiss")
    def dismiss(self, request):
        """«شيل لهذه المرة»: يُعيد المؤقّت ولا يُعدّ — والسببُ اختياري."""
        self.require_write()
        serializer = ReadyToSendDismissSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return self._rows_response(services.dismiss_reminders(
            self.tenant,
            user=request.user,
            items=[dict(item) for item in data["items"]],
            reason=data.get("reason", ""),
        ))

    @action(detail=False, methods=["post"], url_path="postpone")
    def postpone(self, request):
        """«أجّل التذكير لتاريخ…» — صفٌّ جديد، و`until=null` يمسح التأجيل."""
        self.require_write()
        serializer = ReminderPostponeWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = services.postpone_reminder(
            self.tenant,
            user=request.user,
            day=timezone.localdate(),
            client_id=data["client_id"],
            reminder_type=data["reminder_type"],
            until=data.get("until"),
            reason=data.get("reason", ""),
        )
        return Response(services.reminder_postpone_row(row))


class OfficeReminderLogViewSet(OfficeModuleViewSet):
    """سجلُّ التذكيرات: **قراءةٌ وتصحيحٌ، ولا تعديلَ ولا حذف**.

    `POST` على الجمعِ مرفوضٌ (405) لأن الصفَّ لا يُنشأ من الـAPI: يُكتب بفعلِ
    إرسالٍ (`ready-to-send/*`) أو بتصحيحٍ (`undo`). فالـ`http_method_names` هنا
    تسمح بالقراءة وبالفعل وحدهما، و`PUT`/`PATCH`/`DELETE` 405 بحكم القائمة.
    """

    http_method_names = ["get", "post", "head", "options"]
    # شكلُ المورد المُعلَن هو السطرُ الذي يخرج (قراءةً) لا حمولةُ تأجيلٍ للكتابة.
    serializer_class = ReminderLogSerializer

    def get_object(self):
        row = (
            services.visible_reminder_logs(self.tenant, self.request.user)
            .filter(pk=self.kwargs.get("pk"))
            .first()
        )
        if row is None:
            raise NotFound("سطر السجل غير موجود.")
        return row

    def list(self, request, *args, **kwargs):
        return Response(
            services.reminder_log_payload(self.tenant, user=request.user),
        )

    def retrieve(self, request, *args, **kwargs):
        """قراءةُ سطرٍ واحد — **بها وحدها يوجد مسارُ التفصيل**.

        وغيابُها كان يجعل `PUT`/`PATCH`/`DELETE` على المسار **404** لا 405: بلا
        أفعالِ تفصيلٍ لا يولّد الراوترُ المسارَ أصلاً، فيسبق 404ُ التوجيه حكمَ
        الطريقة. و405 هو الجوابُ الصادق: المسارُ موجودٌ والطريقةُ ممنوعة.
        """
        return Response(services.reminder_log_row(self.get_object()))

    @action(detail=True, methods=["post"], url_path="undo")
    def undo(self, request, pk=None):
        """«ما انبعتت» — صفٌّ جديدٌ يشير إلى ما يُبطله، والأصلُ يبقى."""
        row = self.get_object()
        self.require_write()
        undo = services.undo_reminder_log(row, actor=request.user)
        return Response(
            {"row": services.reminder_log_row(undo)},
            status=status.HTTP_201_CREATED,
        )


class OfficeHolidayViewSet(OfficeModuleViewSet):
    """عطلُ المكتب: **تُقرأ لكل عضو وتُكتب بمفتاح الإعدادات** — ولا تقويمَ مخترَع."""

    serializer_class = OfficeHolidayWriteSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return OfficeHoliday.objects.filter(tenant=self.tenant)

    def list(self, request, *args, **kwargs):
        return Response([
            services.office_holiday_row(row)
            for row in self.get_queryset().order_by("date", "id")
        ])

    def create(self, request, *args, **kwargs):
        self.require_settings_manage()
        serializer = OfficeHolidayWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # `get_or_create`: القيدُ في القاعدة هو الحكم، والتكرارُ 400 لا 500.
        row, was_created = OfficeHoliday.objects.get_or_create(
            tenant=self.tenant,
            date=data["date"],
            defaults={"name": data.get("name", "").strip()},
        )
        if not was_created:
            raise ValidationError({"date": "هذا اليوم عطلةٌ مسجَّلةٌ أصلاً."})
        return Response(
            services.office_holiday_row(row), status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        self.require_settings_manage()
        self.get_object().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OfficeAppointmentViewSet(OfficeModuleViewSet):
    """مواعيدُ الزبائن (#281): حجزٌ وقراءة، وتأكيدٌ وتأجيلٌ وإلغاء — **بلا حذف**.

    **الرؤيةُ من `visible_clients` وحدها**: موعدُ زبونٍ لا يراه العضو **404 لا
    403** كسائر الموديول، والكتابةُ بمفتاح `office.clients.write`. والقائمةُ
    ثلاثةُ أشكال: بزبونٍ (تبويبُ ملفّه، مع `kind_choices`)، أو بيومٍ (شاشةُ اليوم
    والتقويم)، أو بالجميع حين لا يُسأل عن مدى.
    """

    # `post` وحدها للكتابة: لا تعديلَ جزئيٌّ لصفِّ موعد (لكلّ تغييرٍ فعلُه)، ولا
    # حذف — الإلغاءُ يكتب حالة، فـ`DELETE` 405.
    http_method_names = ["get", "post", "head", "options"]
    serializer_class = ClientAppointmentWriteSerializer

    def get_queryset(self):
        """المحجوزُ وما صار وما أُلغي — فالبطاقةُ تُقرأ بحالتها لا تُخفى."""
        return appointments.appointment_queryset(
            self.tenant, self.request.user, open_only=False,
        )

    def _client(self, raw):
        """زبونُ القائمة — من رؤية العضو وحدها، وغيابُه **404**."""
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            raise ValidationError({"client": "معرّفُ زبونٍ غير صالح."}) from None
        client = (
            services.visible_clients(self.tenant, self.request.user)
            .filter(pk=pk)
            .first()
        )
        if client is None:
            raise NotFound("الزبون غير موجود.")
        return client

    def list(self, request, *args, **kwargs):
        params = request.query_params
        raw_day = (params.get("day") or "").strip()
        raw_client = (params.get("client") or "").strip()
        day = parse_iso_date(raw_day, "day") if raw_day else timezone.localdate()
        if raw_client:
            return Response(appointments.client_appointments_payload(
                self._client(raw_client), day=day,
            ))
        rows = (
            appointments.appointments_for_day(self.tenant, request.user, day)
            if raw_day
            else appointments.appointments_list(self.tenant, request.user)
        )
        return Response({
            "day": day.isoformat(),
            "client": None,
            "rows": rows,
            "kind_choices": appointments.kind_choices(),
        })

    def create(self, request, *args, **kwargs):
        self.require_write()
        serializer = ClientAppointmentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            appointments.create_appointment(
                self.tenant,
                user=request.user,
                client_id=data["client_id"],
                kind=data["kind"],
                scheduled_at=data["scheduled_at"],
                note=data.get("note", ""),
            ),
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        """«ابعت تأكيد»: صفُّ تذكيرٍ بنوع `appointment` وختمُ وقت التأكيد (د4)."""
        self.require_write()
        serializer = ClientAppointmentConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(appointments.send_appointment_confirmation(
            self.tenant,
            self.get_object(),
            actor=request.user,
            body=serializer.validated_data.get("body") or None,
        ))

    @action(detail=True, methods=["post"], url_path="reschedule")
    def reschedule(self, request, pk=None):
        """«أجّل»: وقتٌ جديد على الصفّ نفسه — لا إلغاءَ وحجزٌ ثانٍ."""
        self.require_write()
        serializer = ClientAppointmentRescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"appointment": appointments.reschedule_appointment(
            self.get_object(),
            scheduled_at=serializer.validated_data["scheduled_at"],
            actor=request.user,
            note=serializer.validated_data.get("note"),
        )})

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """«ألغِ»: حالةٌ تُكتب — والصفُّ يبقى بتاريخه."""
        self.require_write()
        return Response({"appointment": appointments.cancel_appointment(
            self.get_object(), actor=request.user,
        )})

    @action(detail=True, methods=["post"], url_path="done")
    def done(self, request, pk=None):
        """«صار»: الزيارةُ وقعت — الحالةُ تتحرّك ووقتُ الموعد يبقى."""
        self.require_write()
        return Response({"appointment": appointments.complete_appointment(
            self.get_object(), actor=request.user,
        )})


class OfficeClientBookViewSet(OfficeModuleViewSet):
    """دفاترُ الزبائن — قراءةٌ لكل عضوٍ يرى الزبون، وكتابةٌ بمفتاح الزبائن (#286).

    **ولا حذفَ البتة**: `http_method_names` بلا `delete` ولا `put`/`patch`، فحكمُ
    الـ405 يأتي من القائمة لا من نسيان فعل. القاعدةُ نفسها في الـmodels (د4):
    التصحيحُ حركةٌ عكسية والأصلُ يبقى.

    والمسارُ مفتاحُه الزبون لا الدفتر: `client-books/<client_id>/…`، لأن الدفتر
    واحدٌ لكل زبون (`OneToOne`) فمعرّفُه الثاني يخترع مسارين للشيء نفسه.
    """

    serializer_class = ClientBookWriteSerializer
    http_method_names = ["get", "post", "head", "options"]
    #: مسارُ التفصيل مفتاحُه **معرّفُ الزبون** لا معرّفُ الدفتر: `[^/.]+` كان
    #: يمرّر نصّاً إلى `filter(client_id="abc")` فيردّ 500، والصحيحُ 404.
    lookup_value_regex = r"[0-9]+"

    def _masked(self):
        """قرارُ القناع مرّةً للطلب — لا سؤالٌ لكل حركة في القائمة."""
        return client_books.amounts_masked(self.tenant, self.request.user)

    def get_queryset(self):
        # العزلُ من مصدره الواحد (`visible_clients`): دفترُ زبونٍ لا يراه العضو
        # **404** لا 403 — الثاني يُثبت وجوده.
        return ClientBook.objects.filter(
            tenant=self.tenant,
            client__in=services.visible_clients(self.tenant, self.request.user),
        )

    def _book(self, client_id):
        book = (
            self.get_queryset()
            .filter(client_id=client_id)
            .select_related("client")
            .first()
        )
        if book is None:
            raise NotFound("لا دفترَ لهذا الزبون.")
        return book

    def _client(self, client_id):
        client = (
            services.visible_clients(self.tenant, self.request.user)
            .filter(pk=client_id)
            .first()
        )
        if client is None:
            raise NotFound("الزبون غير موجود.")
        return client

    def _book_row(self, book):
        row = client_books.book_row(
            book,
            writable=client_books.book_is_writable(book),
            entry_method=services.resolve_setting(
                self.tenant, client_books.ENTRY_METHOD_KEY, client=book.client,
            ),
        )
        # #286/ب: قائمتا التسميات تُبنيان في `client_books` كما تُبنى
        # `frequency_choices`/`direction_choices` في الخدمات — لا جدولَ محليّاً
        # هنا يفترق عن `BOOK_*_CHOICES` عند أول تعديل. والاسمُ `entry_kind_choices`
        # لأن `kind` في هذا السطر نوعُ الدفتر لا نوعُ الحركة.
        row["entry_kind_choices"] = client_books.entry_kind_choices()
        row["account_type_choices"] = client_books.account_type_choices()
        return row

    def list(self, request, *args, **kwargs):
        return Response(client_books.books_payload(self.tenant, request.user))

    @action(detail=False, methods=["get"], url_path="choices")
    def choices(self, request):
        """تسمياتُ الأنواع الثلاثة — **قراءةٌ لكل عضوٍ يراه الموديول**.

        بلا مفتاح كتابة: من يفتح تبويب «الدفتر» يقرأ القوائمَ ليُدخل حركةً أو
        يعرض زرَّ الانتقال، وإن لم يملك إنشاءَ دفترٍ جديد.
        """
        return Response(client_books.choices_payload())

    def retrieve(self, request, *args, **kwargs):
        """دفترُ زبونٍ واحد — **بمعرّف الزبون** كسائر المسارات تحته.

        ووجودُ هذا المسار شرطٌ لحكمِ د4: `DELETE`/`PATCH` على دفترٍ موجود يجب أن
        يردّا **405** لا 404 — والـ404 يقول «لا مسارَ هنا»، وهو غيرُ ما تقوله
        القاعدة («الحذفُ ممنوع»).
        """
        return Response(self._book_row(self._book(kwargs.get("pk"))))

    def create(self, request, *args, **kwargs):
        self.require_write()
        serializer = ClientBookWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        client = self._client(data["client_id"])
        book = client_books.create_book(
            self.tenant,
            client,
            kind=data["kind"],
            opened_on=data.get("opened_on"),
        )
        return Response(self._book_row(book), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="accounts")
    def accounts(self, request, pk=None):
        """شجرةُ حساب الزبون: تُقرأ لكلّ من يرى الزبون، ويُضاف إليها بمفتاح الكتابة."""
        book = self._book(pk)
        if request.method == "POST":
            self.require_write()
            # الكتابةُ على دفتر زبونٍ خدمتُه موقوفة 400 (د5) — والقراءةُ تبقى.
            client_books.assert_book_writable(book)
            serializer = BookAccountWriteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            row = client_books.add_account(book.client, **serializer.validated_data)
            return Response(
                client_books.account_row(row), status=status.HTTP_201_CREATED,
            )
        return Response(client_books.accounts_payload(book.client))

    @action(detail=True, methods=["get", "post"], url_path="entries")
    def entries(self, request, pk=None):
        """حركاتُ الدفتر: قراءةٌ (بسنةٍ اختيارية)، وإدخالٌ جديد بمفتاح الكتابة."""
        book = self._book(pk)
        if request.method == "POST":
            self.require_write()
            serializer = BookEntryWriteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            entry = client_books.create_entry(
                book, actor=request.user, **serializer.validated_data,
            )
            return Response(
                client_books.entry_row(entry, masked=self._masked()),
                status=status.HTTP_201_CREATED,
            )
        return Response(
            client_books.entries_payload(
                book, year=self._entry_year(request), user=request.user,
            ),
        )

    def _entry_year(self, request):
        """السنةُ المطلوبة — الغيابُ «كلُّ السنوات»، وغيرُ الرقم 400 لا 500."""
        raw = (request.query_params.get("year") or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise ValidationError({"year": "السنة بصيغة YYYY."}) from None

    @action(
        detail=True, methods=["get"],
        url_path=r"entries/(?P<entry_id>[0-9]+)",
    )
    def entry(self, request, pk=None, entry_id=None):
        """حركةٌ واحدة — **قراءةٌ فقط**: `PUT`/`PATCH`/`DELETE` عليها 405 (د4)."""
        book = self._book(pk)
        entry = book.entries.prefetch_related(
            "lines__account", "reversed_by", "documents",
        ).filter(pk=entry_id).first()
        if entry is None:
            raise NotFound("الحركة غير موجودة.")
        return Response(client_books.entry_row(entry, masked=self._masked()))

    @action(
        detail=True, methods=["post"],
        url_path=r"entries/(?P<entry_id>[0-9]+)/reverse",
    )
    def reverse(self, request, pk=None, entry_id=None):
        """حركةٌ عكسية على حركةٍ في **هذا** الدفتر — وحركةُ غيره 404."""
        book = self._book(pk)
        self.require_write()
        entry = book.entries.filter(pk=entry_id).select_related(
            "client_book", "client",
        ).first()
        if entry is None:
            raise NotFound("الحركة غير موجودة.")
        serializer = BookEntryReverseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reversal = client_books.reverse_entry(
            entry, actor=request.user, **serializer.validated_data,
        )
        return Response(
            client_books.entry_row(reversal, masked=self._masked()),
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="pending-entry")
    def pending_entry(self, request):
        """«للإدخال»: ورقٌ واصلةٌ بلا حركةٍ حيّة — مشتقٌّ لا مخزّن (د8/د9)."""
        return Response(
            client_books.pending_entry_payload(self.tenant, request.user),
        )

    @action(detail=True, methods=["post"], url_path="kind")
    def kind(self, request, pk=None):
        """تغييرُ نوع الدفتر — الشروطُ الثلاثة في الخدمة (د7) لا في الـview."""
        book = self._book(pk)
        self.require_write()
        serializer = ClientBookKindWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        book = client_books.change_kind(book, serializer.validated_data["kind"])
        return Response(self._book_row(book))

    # ── التقارير (#288/أ): قراءةٌ محسوبةٌ على الخادم ─────────────────────────
    #
    # **ولا حسابَ هنا**: `book_reports` هي الوحدةُ التي تُرشِّح وتجمع وتقنّع،
    # والـview يمرّر الطلبَ ويردّ ما بُني. والعزلُ من `_book` نفسِه
    # (`visible_clients`): تقريرُ زبونٍ لا يراه العضو **404**، وزبونٌ بلا دفتر
    # كذلك — لا تقريرَ على لا شيء.
    @action(detail=True, methods=["get"], url_path="reports")
    def reports(self, request, pk=None):
        """الأنواعُ المتاحةُ لنوع دفتر هذا الزبون — والعلامةُ المائية معها."""
        return Response(book_reports.reports_index_payload(self._book(pk)))

    @action(detail=True, methods=["get"], url_path=r"reports/(?P<kind>[a-z_]+)")
    def report(self, request, pk=None, kind=None):
        """تقريرٌ واحد بفترة `from`/`to` — وميزانٌ لا يتوازن **409 صريح**.

        و409 لا 400: الطلبُ سليمٌ والبياناتُ هي المكسورة، فيقول الرقمُ للمحاسب
        أين ينظر بدل «حمولتُك فاسدة» عن فترةٍ صحيحة.
        """
        book = self._book(pk)
        if not book_reports.is_report_available(book, kind):
            raise NotFound("لا تقريرَ بهذا النوع لهذا الدفتر.")
        try:
            payload = book_reports.report_payload(
                book,
                kind,
                raw_from=request.query_params.get("from"),
                raw_to=request.query_params.get("to"),
                user=request.user,
                account=request.query_params.get("account") or "",
                party=request.query_params.get("party") or "",
            )
        except book_reports.ReportImbalance as exc:
            return Response(
                {"detail": str(exc), "totals": exc.totals},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(payload)


# ── الأتعاب: الاشتراك والمسودّات والاعتماد (#282) ───────────────────────────
#
# **ولا حذفَ في أيّ نقطةٍ منها**: كلُّ `http_method_names` هنا بلا `delete`، فحكمُ
# الـ405 من القائمة لا من نسيان فعل. والاشتراكُ لا يُعدَّل: تغييرُ السعر صفٌّ
# جديدٌ بتاريخ سريانه (`fees.create_subscription`)، فتاريخُ الشهر الماضي يبقى.
def _visible_client(tenant, user, client_id):
    """زبونٌ يراه العضو — وإلا **404 لا 403**: الثاني يُثبت وجودَ الزبون."""
    client = services.visible_clients(tenant, user).filter(pk=client_id).first()
    if client is None:
        raise NotFound("الزبون غير موجود.")
    return client


def _visible_client_service(tenant, user, data):
    """خدمةُ زبونٍ يراه العضو — وإلا **404**: زبونُ غيرك لا وجودَ له.

    تُقبل بمعرّف الخدمة (`client_service`) أو بالخدمة والزبون معاً (أحدثُ صفٍّ
    للخدمة عند الزبون إن تعدّد بتوقّفٍ وإعادة). والبحثُ من `visible_clients`
    وحدها، فلا تُسعَّر خدمةُ زبونِ زميلٍ ولا زبونِ مكتبٍ آخر.
    """
    visible = services.visible_clients(tenant, user)
    if data.get("client_service") is not None:
        client_service = (
            ClientService.objects
            .filter(pk=data["client_service"], client__in=visible.values("pk"))
            .first()
        )
    else:
        client = visible.filter(pk=data["client"]).first()
        if client is None:
            raise NotFound("الزبون غير موجود.")
        client_service = (
            ClientService.objects
            .filter(client=client, service_id=data["service"])
            .order_by("-starts_on", "-id")
            .first()
        )
    if client_service is None:
        raise NotFound("خدمة الزبون غير موجودة.")
    return client_service


class OfficeFeeSubscriptionViewSet(OfficeModuleViewSet):
    """اشتراكاتُ الأتعاب — **قراءةٌ وإضافة، ولا تعديلَ ولا حذف**.

    القراءةُ بمصدر الرؤية الواحد (`visible_clients`)، والقناعُ في الخدمة، وكتابةُ
    مبلغٍ بلا «يرى المبالغ» **403** كما في مبلغ الالتزام وسعر الباقة.
    """

    serializer_class = FeeSubscriptionWriteSerializer
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        return Response(fees.subscriptions_payload(self.tenant, user=request.user))

    def create(self, request, *args, **kwargs):
        self.require_write()
        serializer = FeeSubscriptionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        client = _visible_client(self.tenant, request.user, data["client"])
        self.reject_amount_writes(data)
        row = fees.create_subscription(
            self.tenant,
            client,
            amount=data["amount"],
            starts_on=data["starts_on"],
            cadence=data.get("cadence"),
            currency=data.get("currency"),
            paused_from=data.get("paused_from"),
            paused_to=data.get("paused_to"),
            ended_on=data.get("ended_on"),
        )
        row = FeeSubscription.objects.select_related("client", "currency").get(pk=row.pk)
        return Response(
            fees.subscription_row(
                row, masked=fees.amounts_masked(self.tenant, request.user),
            ),
            status=status.HTTP_201_CREATED,
        )


class OfficeFeeDraftViewSet(OfficeModuleViewSet):
    """مسودّاتُ الأتعاب — قراءةٌ، واعتمادٌ وإلغاءٌ بدور صاحب المكتب ومدير المكتب.

    **ولا إنشاءَ من الـAPI**: المولّدُ في «حدّث المكتب» بفرادة `(زبون، سنة، شهر)`
    في القاعدة، فـ`POST` على الجمع **405**. والمسودّةُ لا تُعدَّل ولا تُحذف:
    الاعتمادُ والإلغاءُ فعلان وحدهما، والمعتمدةُ سندُ فاتورةٍ في أ٢.
    """

    serializer_class = FeeDraftRowSerializer
    http_method_names = ["get", "post", "head", "options"]
    # مسارُ التفصيل رقميّ: `approve-all` مسارُ جمعٍ لا معرّفَ مسودّة، والرقمُ يمنع
    # التباسَ الاثنين ولو غيّر الراوترُ ترتيبَه.
    lookup_value_regex = r"[0-9]+"

    def get_queryset(self):
        return fees.visible_drafts(self.tenant, self.request.user)

    def get_object(self):
        draft = self.get_queryset().filter(pk=self.kwargs.get("pk")).first()
        if draft is None:
            raise NotFound("المسودّة غير موجودة.")
        return draft

    def list(self, request, *args, **kwargs):
        return Response(fees.drafts_payload(self.tenant, user=request.user))

    def _row(self, draft):
        return Response(fees.draft_row(
            draft, masked=fees.amounts_masked(self.tenant, self.request.user),
        ))

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """`draft → approved` — والانتقالُ من الحالة الآنية يقرؤه `fees` بقفلٍ."""
        draft = self.get_object()
        serializer = FeeDraftApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        approved = fees.approve_fee_draft(
            draft,
            actor=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return self._row(approved)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """«أَلغِها» — من المسودّة وحدها، وقبل الاعتماد."""
        draft = self.get_object()
        cancelled = fees.cancel_fee_draft(draft, actor=request.user)
        return self._row(cancelled)

    @action(detail=False, methods=["post"], url_path="approve-all")
    def approve_all(self, request):
        """«اعتمد الكل» — كلُّ منتظرةٍ في المكتب، والردُّ يقول كم بقي منها."""
        serializer = FeeDraftApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        approved = fees.approve_all_fee_drafts(
            self.tenant,
            actor=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        masked = fees.amounts_masked(self.tenant, request.user)
        summaries = payments.invoice_summaries(approved)
        return Response({
            "approved": len(approved),
            "remaining": fees.pending_drafts(self.tenant).count(),
            "drafts": [
                fees.draft_row(draft, masked=masked, summaries=summaries)
                for draft in approved
            ],
        })

    # #283: الشطبُ فعلٌ على المسودّة لا نموذجٌ جديد يُحذف: سطرٌ إلحاقيٌّ يخفّض
    # `remaining` في القراءة، والدفعةُ والمسودّةُ لا تتغيّران.
    @action(detail=True, methods=["post"], url_path="write-off")
    def write_off(self, request, pk=None):
        """«اشطُب المتبقّي» — **دورُ صاحب المكتب وحده**، بسببٍ مكتوبٍ إلزاميّ.

        ولا مفتاحَ كتابةٍ فوقه: البوابةُ الوحيدةُ هي `payments.write_off_fee_draft`
        (`user_tenant_role == MANAGER_ROLE`) كما في المواصفة — مديرُ المكتب يملك
        مفتاحَ الكتابة ولا يشطب.
        """
        draft = self.get_object()
        serializer = FeeWriteOffWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.reject_amount_writes({"amount": data["amount"]})
        row = payments.write_off_fee_draft(
            draft,
            amount=data["amount"],
            reason=data["reason"],
            actor=request.user,
        )
        row = FeeWriteOff.objects.select_related("draft", "created_by").get(pk=row.pk)
        return Response(
            payments.write_off_row(
                row, masked=fees.amounts_masked(self.tenant, request.user),
            ),
            status=status.HTTP_201_CREATED,
        )


class OfficeFeeExtraServiceViewSet(OfficeModuleViewSet):
    """الخدماتُ الإضافية — **قراءةٌ وإضافة، ولا حذف**: قيدُ عملٍ نُفِّذ فعلاً."""

    serializer_class = FeeExtraServiceWriteSerializer
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        return Response(fees.extras_payload(self.tenant, user=request.user))

    def create(self, request, *args, **kwargs):
        self.require_write()
        serializer = FeeExtraServiceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        client = _visible_client(self.tenant, request.user, data["client"])
        self.reject_amount_writes(data)
        row = fees.create_extra_service(
            self.tenant,
            client,
            service_name=data["service_name"],
            amount=data["amount"],
            performed_on=data["performed_on"],
            draft=data.get("draft"),
        )
        row = FeeExtraService.objects.select_related("client").get(pk=row.pk)
        return Response(
            fees.extra_row(row, masked=fees.amounts_masked(self.tenant, request.user)),
            status=status.HTTP_201_CREATED,
        )


class OfficeFeeServicePriceViewSet(OfficeModuleViewSet):
    """أسعارُ خدمات الزبائن — **قراءةٌ وتسعير، ولا تعديلَ ولا حذف**.

    **بها تُكتمل طريقةُ «سعرٌ لكل خدمة»**: كانت الطريقةُ تُختار ولا مدخلَ لسعر
    الخدمة، فتُولَّد المسودّاتُ بلا سطورٍ ويتوقّف المكتب بصمت. والرؤيةُ عبر
    `client_service.client` و`visible_clients`، والمبلغُ يمرّ بالقناع وبحارس
    الكتابة، وإعادةُ التسعير `POST` ثانٍ يحدّث الصفَّ الواحد (`OneToOne`) — فلا
    `PUT`/`PATCH` ولا `DELETE`.
    """

    serializer_class = FeeServicePriceWriteSerializer
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        return Response(fees.service_prices_payload(self.tenant, user=request.user))

    def create(self, request, *args, **kwargs):
        self.require_write()
        serializer = FeeServicePriceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        client_service = _visible_client_service(self.tenant, request.user, data)
        self.reject_amount_writes(data)
        row, created = fees.set_client_service_price(
            client_service, amount=data["amount"],
        )
        row = ClientServicePrice.objects.select_related(
            "client", "client_service__service",
        ).get(pk=row.pk)
        return Response(
            fees.service_price_row(
                row, masked=fees.amounts_masked(self.tenant, request.user),
            ),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class OfficeFeeInvoiceViewSet(OfficeModuleViewSet):
    """فواتيرُ الأتعاب — قراءةٌ وأفعالُ إلغاءٍ وتصحيح، **ولا حذفَ ولا تعديل**.

    **`http_method_names` تُغلق `delete`/`put`/`patch`**: الفاتورةُ مستندٌ
    مرقَّمٌ خرج أو سيخرج، والتصحيحُ إشعارٌ دائن أو تكميلية لا محوُ صفّ. و`POST`
    على الجمع 405 كذلك — الإصدارُ بالاعتماد وحده (`fees.approve_fee_draft`).

    **والقراءةُ بمصدر الرؤية الواحد** (`fee_invoices.visible_invoices`)،
    ففاتورةُ زبونٍ لا يراه العضو **404** لا 403؛ والقناعُ قرارٌ يُحسب مرّةً في
    الخدمة كما في المسودّات، وكتابةُ مبلغِ تصحيحٍ بلا `office.amounts.view` 403.
    """

    serializer_class = FeeInvoiceRowSerializer
    http_method_names = ["get", "post", "head", "options"]
    # مسارُ التفصيل رقميّ: أفعالُه مساراتُ جمعٍ نسبيّة، والرقمُ يمنع الالتباس.
    lookup_value_regex = r"[0-9]+"

    def get_queryset(self):
        return fee_invoices.visible_invoices(self.tenant, self.request.user)

    def get_object(self):
        invoice = self.get_queryset().filter(pk=self.kwargs.get("pk")).first()
        if invoice is None:
            raise NotFound("الفاتورة غير موجودة.")
        return invoice

    def list(self, request, *args, **kwargs):
        client = (request.query_params.get("client") or "").strip()
        kind = (request.query_params.get("kind") or "").strip() or None
        state = (request.query_params.get("state") or "").strip() or None
        if client and not client.isdigit():
            raise ValidationError({"client": "معرّفُ زبونٍ غير صالح."})
        return Response(fee_invoices.invoices_payload(
            self.tenant,
            user=request.user,
            client=int(client) if client else None,
            kind=kind,
            state=state,
        ))

    def _detail(self, invoice):
        return Response(fee_invoices.invoice_detail(
            invoice, masked=fees.amounts_masked(self.tenant, self.request.user),
        ))

    def retrieve(self, request, *args, **kwargs):
        return self._detail(self.get_object())

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """«أَلغِها» — قبل إنشاء الرابط وحده، والصفُّ يبقى في التاريخ.

        وإشعارٌ دائنٌ حيٌّ على الفاتورة **409** لا 400: الطلبُ صحيحٌ والحالةُ
        القائمةُ تمنعه — وإلا بقي تصحيحٌ دائنٌ على أصلٍ ملغى.
        """
        invoice = self.get_object()
        self.require_write()
        serializer = FeeInvoiceCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cancelled = fee_invoices.cancel_invoice(
                invoice,
                actor=request.user,
                reason=serializer.validated_data.get("reason", ""),
            )
        except fee_invoices.LiveCreditNoteConflict as conflict:
            return Response(
                {"invoice": [str(conflict)]},
                status=status.HTTP_409_CONFLICT,
            )
        return self._detail(cancelled)

    @action(detail=True, methods=["post"], url_path="credit-note")
    def credit_note(self, request, pk=None):
        """إشعارٌ دائنٌ على سلسلةٍ منفصلة — بمبلغٍ وسببٍ إلزاميّ."""
        invoice = self.get_object()
        self.require_write()
        serializer = FeeInvoiceCreditNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.reject_amount_writes(data)
        note = fee_invoices.issue_credit_note(
            invoice,
            actor=request.user,
            amount=data["amount"],
            reason=data["reason"],
        )
        return Response(
            fee_invoices.invoice_detail(
                FeeInvoice.objects.select_related(
                    "client", "issued_by", "related_invoice",
                ).get(pk=note.pk),
                masked=fees.amounts_masked(self.tenant, request.user),
            ),
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="supplementary")
    def supplementary(self, request, pk=None):
        """فاتورةٌ تكميليةٌ للنقص — على السلسلة الرئيسية."""
        invoice = self.get_object()
        self.require_write()
        serializer = FeeInvoiceSupplementarySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.reject_amount_writes(data)
        extra = fee_invoices.issue_supplementary(
            invoice,
            actor=request.user,
            amount=data["amount"],
            reason=data.get("reason", ""),
        )
        return Response(
            fee_invoices.invoice_detail(
                FeeInvoice.objects.select_related(
                    "client", "issued_by", "related_invoice",
                ).get(pk=extra.pk),
                masked=fees.amounts_masked(self.tenant, request.user),
            ),
            status=status.HTTP_201_CREATED,
        )


# ── الدفعات و«اللي عليه» وكشف الحساب (#283) ─────────────────────────────────
#
# **الدفعةُ تُنشأ ولا تُعدَّل ولا تُحذف**: `http_method_names` بلا `put`/`patch`/
# `delete`، فحكمُ 405 من القائمة لا من نسيان فعل. والتصحيحُ دفعةٌ جديدة أو
# شطبٌ على المسودّة — لا كتابةٌ فوق سندِ قبضٍ صدر.
class OfficeFeePaymentViewSet(OfficeModuleViewSet):
    """دفعاتُ الأتعاب — قراءةٌ بفلترة، وإنشاءٌ بتخصيصٍ تلقائيّ أو صريح.

    القراءةُ بمصدر الرؤية الواحد (`visible_clients`)، والقناعُ في الخدمة
    (`payments.payments_payload`)، وكتابةُ مبلغٍ بلا «يرى المبالغ» **403**
    كسائر مبالغ الموديول.
    """

    serializer_class = FeePaymentWriteSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return payments.visible_payments(self.tenant, self.request.user)

    def list(self, request, *args, **kwargs):
        """قائمةٌ بفلاتر `client`/`method`/`date_from`/`date_to` — في الاستعلام."""
        queryset = payments.filter_payments(
            self.get_queryset(), request.query_params,
        )
        return Response(
            payments.payments_payload(
                self.tenant, user=request.user, queryset=queryset,
            ),
        )

    def create(self, request, *args, **kwargs):
        self.require_write()
        serializer = FeePaymentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        client = _visible_client(self.tenant, request.user, data["client"])
        self.reject_amount_writes(data)
        payment = payments.create_payment(
            self.tenant,
            client,
            amount=data["amount"],
            method=data["method"],
            paid_at=data["paid_at"],
            note=data.get("note", ""),
            actor=request.user,
            # `None` = «الأقدم أولاً»، و`[]` = لا تخصيصَ (دفعةٌ مقدَّمة) — لا
            # يجمعهما `or None` فتُلغى القائمةُ الفارغة.
            allocations=data.get("allocations"),
        )
        row = payments.created_payment_row(
            self.tenant, payment, user=request.user,
        )
        return Response(row, status=status.HTTP_201_CREATED)


class OfficeFeeLedgerViewSet(OfficeModuleViewSet):
    """كشفُ الحساب — الفواتيرُ المعتمدةُ والدفعات في حمولةٍ واحدة.

    الفلاترُ (`client` · `state` · `q`) والترقيمُ (`page` · `page_size`) على
    الاستعلام لا في بايثون؛ والبناءُ كلُّه في `payments.ledger_payload`.
    """

    serializer_class = FeeLedgerQuerySerializer
    http_method_names = ["get", "head", "options"]

    def list(self, request, *args, **kwargs):
        return Response(
            payments.ledger_payload(
                self.tenant, user=request.user, params=request.query_params,
            ),
        )
