"""N0-T4 — Views for TenantSettings + TenantBook + Currency (Group Constants F11)."""
import logging

from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from core.api_defaults import ApiAuthAndUser
from core.access import require_perm
from core.plans import enforce_limits
from core.tenant_utils import get_tenant
from .models import Branch, Currency, TenantBook, TenantSettings, Tenant, UserCompanyMembership
from .serializers import BranchSerializer, TenantBookSerializer, TenantSettingsSerializer, TenantSerializer, UserCompanyMembershipSerializer

logger = logging.getLogger(__name__)


class CurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    """قائمة العملات (read-only) — يَستخدمها GroupConstantsPage."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = Currency.objects.all().order_by("Code")

    def list(self, request, *args, **kwargs):
        """Plain list (no pagination)."""
        from rest_framework import serializers as drf_serializers

        class _CurrencyOut(drf_serializers.ModelSerializer):
            class Meta:
                model = Currency
                fields = ["CurrencyID", "Code", "Name", "Symbol", "IsBaseCurrency"]

        qs = self.get_queryset()
        return Response(_CurrencyOut(qs, many=True).data)


class TenantSettingsViewSet(viewsets.ModelViewSet):
    """TenantSettings — one row per tenant. Provides /current/ action."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = TenantSettingsSerializer

    def get_queryset(self):
        # P1-7 (المرحلة 5): غياب الشركة كان يُرجِع إعدادات كل الشركات — نفس
        # نمط ثغرة task11 M7. .none() عند الغياب، كبقية المشروع.
        tenant = get_tenant(self.request)
        if not tenant:
            return TenantSettings.objects.none()
        return TenantSettings.objects.select_related(
            "currency", "default_freight_credit_account"
        ).filter(tenant=tenant)

    @action(detail=False, methods=["get", "put", "patch"], url_path="current")
    def current(self, request):
        """Returns/updates the singleton TenantSettings for the current tenant.

        Auto-creates a default row on first GET — so `GroupConstantsPage` can
        always read something even on a fresh tenant.
        """
        tenant = get_tenant(request)
        if not tenant:
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة."})

        settings_obj, _ = TenantSettings.objects.get_or_create(tenant=tenant)

        if request.method == "GET":
            return Response(TenantSettingsSerializer(settings_obj).data)

        # PUT / PATCH — T-PERM: الكتابة تتطلب «إعدادات الشركة العامة».
        require_perm(request, "admin.settings.manage", tenant=tenant)
        partial = request.method == "PATCH"
        ser = TenantSettingsSerializer(settings_obj, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        old_start_day = settings_obj.dashboard_month_start_day
        ser.save()
        if ser.instance.dashboard_month_start_day != old_start_day:
            logger.info(
                "dashboard_month_start updated tenant=%s start_day=%s by_user=%s",
                tenant.TenantID,
                ser.instance.dashboard_month_start_day,
                getattr(request.user, "pk", None),
            )
        return Response(ser.data)


class TenantBookViewSet(viewsets.ModelViewSet):
    """TenantBook — 1 row per (tenant, document_type, book_number).

    Provides a `seed/` action that creates the default 10-books-per-doc-type
    grid on first call (idempotent).
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = TenantBookSerializer

    def get_queryset(self):
        # P1-7 (المرحلة 5): .none() عند غياب الشركة بدل إرجاع دفاتر الجميع.
        tenant = get_tenant(self.request)
        if not tenant:
            return TenantBook.objects.none()
        return TenantBook.objects.filter(tenant=tenant).order_by(
            "document_type", "book_number")

    def list(self, request, *args, **kwargs):
        """Plain list (no pagination)."""
        return Response(TenantBookSerializer(self.get_queryset(), many=True).data)

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة."})
        serializer.save(tenant=tenant)

    @action(detail=False, methods=["post"], url_path="seed")
    def seed(self, request):
        """Create the default 10 books per document type for the current tenant.

        Idempotent: if a book already exists, it's left untouched. Returns the
        full set after seeding.
        """
        tenant = get_tenant(request)
        if not tenant:
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة."})

        created = 0
        for doc_type, doc_label in TenantBook.DOCUMENT_TYPES:
            for book_number in range(1, 11):
                _, was_created = TenantBook.objects.get_or_create(
                    tenant=tenant,
                    document_type=doc_type,
                    book_number=book_number,
                    defaults={
                        "name": f"{doc_label} — دفتر {book_number}",
                        "last_used_number": 0,
                        "is_active": True,
                    },
                )
                if was_created:
                    created += 1

        return Response(
            {
                "created": created,
                "books": TenantBookSerializer(self.get_queryset(), many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class BranchViewSet(viewsets.ModelViewSet):
    """task11 M4 — فروع الشركة النشطة.

    الفرع يشارك الشركةَ شجرةَ الحسابات/المنتجات/الشركاء، وتُعزل فواتيره
    ومخزونه وقيوده عبر بُعد branch على المستندات.
    إنشاء فرع = صلاحية مدير في الشركة النشطة.
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = BranchSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return Branch.objects.none()
        return Branch.objects.filter(tenant=tenant).order_by("-is_main", "name")

    def list(self, request, *args, **kwargs):
        """Plain list (no pagination) — يستهلكها BranchSwitcher."""
        return Response(BranchSerializer(self.get_queryset(), many=True).data)

    def _require_manager(self, request, tenant):
        # T-PERM: الفروع جزء من إعدادات الشركة.
        require_perm(request, "admin.settings.manage", tenant=tenant)

    def create(self, request, *args, **kwargs):
        tenant = get_tenant(request)
        if not tenant:
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة."})
        self._require_manager(request, tenant)
        # T-PLANLIMITS: عدد الفروع المسموح به من خطة الشركة.
        enforce_limits(tenant, "company.branches")
        from .services import create_branch
        try:
            branch = create_branch(
                tenant,
                request.data.get("name", ""),
                request.data.get("code", ""),
            )
        except DjangoValidationError as e:
            raise DRFValidationError({"detail": e.messages if hasattr(e, "messages") else str(e)})
        return Response(BranchSerializer(branch).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        tenant = get_tenant(self.request)
        self._require_manager(self.request, tenant)
        serializer.save(tenant=tenant)

    def destroy(self, request, *args, **kwargs):
        """حماية البيانات: لا حذف فعلي للفروع — تعطيل فقط (is_active=False)."""
        tenant = get_tenant(request)
        if not tenant:
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة."})
        self._require_manager(request, tenant)
        branch = self.get_object()
        if branch.is_main:
            raise DRFValidationError({"detail": "لا يمكن تعطيل الفرع الرئيسي."})
        branch.is_active = False
        branch.save(update_fields=["is_active"])
        return Response({"ok": True, "deactivated": True})


class TenantViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Tenant / Companies management.
    """
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = TenantSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Tenant.objects.none()
        if user.is_superuser:
            return Tenant.objects.all().order_by("CompanyName")
        # ISSUE #52: العزل هو المنتج — عضوية صريحة، أو مدير مكتبٍ يملك الدفتر
        # المُدار (قرار 7: يرى كل دفاتر مكتبه بلا عضوية لكل واحد). موظفٌ غير
        # مُسند، أو مستخدمٌ من مكتبٍ آخر، لا يقع تحت أيٍّ من الشرطين ⇒ 404 لا
        # 403 (الصفّ غائبٌ عن get_queryset فيسقط `get_object` على DoesNotExist).
        from django.db.models import Q

        office_ids = UserCompanyMembership.objects.filter(
            user=user, role="manager",
        ).values_list("tenant_id", flat=True)
        return Tenant.objects.filter(
            Q(memberships__user=user) | Q(managed_by_id__in=office_ids)
        ).distinct().order_by("CompanyName")

    def _can_create_company(self, user) -> bool:
        """Manager-only (M4-T3), with a bootstrap exception: a user with no
        memberships yet may create their first company. Superusers always may."""
        if user.is_superuser:
            return True
        # عضوية شركة المثال وصول عام، ولا تُحسب كشركة يملكها المستخدم؛ وإلا
        # تمنعه من إنشاء شركته الحقيقية الأولى.
        memberships = UserCompanyMembership.objects.filter(
            user=user, is_example_access=False,
        )
        # الارتباطات الخارجية لا تعني أن المحاسب يملك شركة؛ لذلك لا تمنعه من
        # إنشاء مكتبه (Tenant مستقل يصبح مديره) للمرة الأولى.
        owned_memberships = memberships.exclude(role="legal_accountant")
        if not owned_memberships.exists():
            return True  # bootstrapping the first company
        return owned_memberships.filter(role="manager").exists()

    def create(self, request, *args, **kwargs):
        if not self._can_create_company(request.user):
            raise PermissionDenied("فقط المدير يمكنه إنشاء شركة جديدة.")
        name = request.data.get("CompanyName")
        if not name:
            raise DRFValidationError({"CompanyName": "اسم الشركة مطلوب."})
        from .company_templates import COMPANY_TEMPLATES, DEFAULT_TEMPLATE
        from .services import create_company
        template = request.data.get("template") or DEFAULT_TEMPLATE
        if template not in COMPANY_TEMPLATES:
            raise DRFValidationError({"template": f"قالب الشركة «{template}» غير معروف."})
        try:
            tenant = create_company(name, request.user, template=template)
        except DjangoValidationError as e:
            # Known validation errors → 400; unexpected errors propagate to the
            # shaped 500 handler (with trace_id) instead of being masked as 400.
            raise DRFValidationError({"detail": e.messages if hasattr(e, "messages") else str(e)})
        return Response(TenantSerializer(tenant).data, status=status.HTTP_201_CREATED)

    # ── إدارة الشركة (task12 M4) ──
    def _require_company_manager(self, request, tenant, key="admin.members.manage"):
        """T-PERM: الحَكَم صار الصلاحية لا اسم الدور — فمن يمنحه المدير
        «إدارة الأعضاء» يديرهم دون أن يصير مديراً. الشركة تُمرَّر صراحةً (من
        مسار الطلب) فلا يفتح ترويسة X-Tenant-Id باباً لشركة أخرى."""
        require_perm(request, key, tenant=tenant)

    def update(self, request, *args, **kwargs):
        """تعديل بيانات الشركة (الاسم…) — كان مفتوحاً لأي عضو (T12-B3)."""
        self._require_company_manager(request, self.get_object(), "admin.settings.manage")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._require_company_manager(request, self.get_object(), "admin.settings.manage")
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """حماية البيانات: لا حذف فعلي للشركات من الـ API (كان hard-delete مفتوحاً لأي عضو)."""
        raise DRFValidationError({"detail": "حذف الشركة غير متاح من النظام. تواصل مع إدارة المنصة."})

    @staticmethod
    def _member_payload(m):
        from .services import member_payload
        return member_payload(m)

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, pk=None):
        """GET: قائمة أعضاء الشركة (لأي عضو). POST: إضافة عضو بدور (مدير فقط).

        body (POST): {"username_or_email": "...", "role": "manager|accountant|staff|viewer"}
        """
        tenant = self.get_object()
        if request.method == "GET":
            qs = UserCompanyMembership.objects.filter(tenant=tenant).select_related("user").order_by("user__username")
            return Response([self._member_payload(m) for m in qs])

        self._require_company_manager(request, tenant)
        # T-PLANLIMITS: عدد أعضاء الشركة المسموح به من خطتها.
        enforce_limits(tenant, "company.members")
        from django.contrib.auth.models import User as AuthUser
        from django.db.models import Q

        ident = str(request.data.get("username_or_email") or "").strip()
        role = str(request.data.get("role") or "staff").strip()
        valid_roles = {r for r, _ in UserCompanyMembership.ROLE_CHOICES}
        if role not in valid_roles:
            raise DRFValidationError({"role": f"دور غير صالح. المسموح: {sorted(valid_roles)}"})
        if role == "legal_accountant":
            raise DRFValidationError({
                "role": "يُنشأ دور المحاسب القانوني من دورة الارتباط المحمية فقط."
            })
        if not ident:
            raise DRFValidationError({"username_or_email": "اسم المستخدم أو البريد مطلوب."})
        target = AuthUser.objects.filter(Q(username__iexact=ident) | Q(email__iexact=ident)).first()
        if not target:
            raise DRFValidationError({"username_or_email": "لا يوجد مستخدم بهذا الاسم/البريد. يجب أن يسجّل حسابه أولاً."})
        membership, created = UserCompanyMembership.objects.get_or_create(
            user=target, tenant=tenant, defaults={"role": role}
        )
        if not created:
            raise DRFValidationError({"username_or_email": "المستخدم عضو في الشركة بالفعل."})
        return Response(self._member_payload(membership), status=status.HTTP_201_CREATED)

    def _get_member_or_400(self, tenant, request):
        mid = request.data.get("membership_id")
        try:
            mid = int(mid)
        except (TypeError, ValueError):
            raise DRFValidationError({"membership_id": "membership_id مطلوب."})
        m = UserCompanyMembership.objects.filter(id=mid, tenant=tenant).select_related("user").first()
        if not m:
            raise DRFValidationError({"membership_id": "العضوية غير موجودة في هذه الشركة."})
        return m

    @staticmethod
    def _assert_not_last_manager(tenant, membership):
        from .services import is_last_manager
        if is_last_manager(tenant, membership):
            raise DRFValidationError({"detail": "لا يمكن إزالة/تخفيض آخر مدير في الشركة."})

    @action(detail=True, methods=["post"], url_path="members/change-role")
    def change_member_role(self, request, pk=None):
        """body: {"membership_id": n, "role": "..."} — مدير فقط، مع حماية آخر مدير."""
        tenant = self.get_object()
        self._require_company_manager(request, tenant)
        m = self._get_member_or_400(tenant, request)
        role = str(request.data.get("role") or "").strip()
        valid_roles = {r for r, _ in UserCompanyMembership.ROLE_CHOICES}
        if role not in valid_roles:
            raise DRFValidationError({"role": f"دور غير صالح. المسموح: {sorted(valid_roles)}"})
        if role == "legal_accountant":
            raise DRFValidationError({
                "role": "يُنشأ دور المحاسب القانوني من دورة الارتباط المحمية فقط."
            })
        if role != "manager":
            self._assert_not_last_manager(tenant, m)
        m.role = role
        m.save(update_fields=["role"])
        return Response(self._member_payload(m))

    @action(detail=True, methods=["post"], url_path="members/remove")
    def remove_member(self, request, pk=None):
        """body: {"membership_id": n} — مدير فقط، مع حماية آخر مدير."""
        tenant = self.get_object()
        self._require_company_manager(request, tenant)
        m = self._get_member_or_400(tenant, request)
        self._assert_not_last_manager(tenant, m)
        m.delete()
        return Response({"ok": True})

    # ── صلاحية وحدة الاستيراد (نموذج من مستويين) ──
    @staticmethod
    def _coerce_bool(val) -> bool:
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "on")
        return bool(val)

    @action(detail=True, methods=["post"], url_path="set-import-enabled")
    def set_import_enabled(self, request, pk=None):
        """تفعيل/تعطيل وحدة الاستيراد لشركة — سوبر أدمن المنصة فقط.

        body: {"import_enabled": true|false}
        """
        from core.import_access import is_super_admin
        if not is_super_admin(request.user):
            raise PermissionDenied("فقط مدير المنصة (سوبر أدمن) يتحكم بتفعيل الاستيراد للشركات.")
        # السوبر أدمن يصل لأي شركة بمعرّفها (لا يقيّده فلتر العضوية في get_queryset).
        tenant = Tenant.objects.filter(pk=pk).first()
        if not tenant:
            raise DRFValidationError({"detail": "الشركة غير موجودة."})
        tenant.import_enabled = self._coerce_bool(request.data.get("import_enabled"))
        tenant.save(update_fields=["import_enabled"])
        logger.info("import-access: tenant=%s import_enabled=%s by_user=%s",
                    tenant.pk, tenant.import_enabled, request.user.pk)
        return Response({"TenantID": tenant.pk, "import_enabled": tenant.import_enabled})

    @action(detail=True, methods=["post"], url_path="members/set-import-access")
    def set_member_import_access(self, request, pk=None):
        """منح/سحب صلاحية الاستيراد لعضو — مدير الشركة فقط، ويشترط تفعيل الاستيراد للشركة.

        body: {"membership_id": n, "can_access_import": true|false}
        """
        tenant = self.get_object()
        self._require_company_manager(request, tenant)
        if not tenant.import_enabled:
            raise DRFValidationError({"detail": "وحدة الاستيراد غير مفعّلة لهذه الشركة. تواصل مع إدارة المنصة."})
        m = self._get_member_or_400(tenant, request)
        m.can_access_import = self._coerce_bool(request.data.get("can_access_import"))
        m.save(update_fields=["can_access_import"])
        logger.info("import-access: membership=%s can_access_import=%s by_user=%s",
                    m.id, m.can_access_import, request.user.pk)
        return Response(self._member_payload(m))

    # ── ST-1: معرّف المتجر العام ──
    @action(detail=True, methods=["post"], url_path="set-store-slug")
    def set_store_slug(self, request, pk=None):
        """يفتح متجر الشركة أو يغيّر معرّفه أو يقفله — بصلاحية `store.manage`.

        body: {"store_slug": "alpha"} — أو نصّ فارغ/غياب القيمة لإقفال المتجر.

        القيمة نفسها هي مفتاح التفعيل: NULL = مقفل. فلا حقل «مفعّل» ثانٍ يمكن
        أن يتناقض مع المعرّف، ولا حالة «متجر مفعّل بلا رابط».
        """
        tenant = self.get_object()
        # ST-3: الحارس مفتاح مستقل — فتح متجر عام قرارٌ تجاري لا إعداد شركة،
        # ومَن يضبط الشعار والعنوان لا يفتح به واجهةً تعرض الأسعار للملأ.
        self._require_company_manager(request, tenant, "store.manage")

        raw = request.data.get("store_slug")
        slug = (str(raw).strip().lower() if raw is not None else "")
        if not slug:
            tenant.store_slug = None
            tenant.save(update_fields=["store_slug"])
            logger.info("store-slug: tenant=%s closed by_user=%s",
                        tenant.pk, request.user.pk)
            return Response({"TenantID": tenant.pk, "store_slug": None})

        from .models import validate_store_slug
        try:
            validate_store_slug(slug)
        except DjangoValidationError as e:
            raise DRFValidationError({"store_slug": e.messages})
        taken = Tenant.objects.filter(store_slug=slug).exclude(pk=tenant.pk).exists()
        if taken:
            raise DRFValidationError(
                {"store_slug": "هذا المعرّف محجوز لشركة أخرى. اختر معرّفاً غيره."})

        tenant.store_slug = slug
        tenant.save(update_fields=["store_slug"])
        logger.info("store-slug: tenant=%s slug=%s by_user=%s",
                    tenant.pk, slug, request.user.pk)
        return Response({"TenantID": tenant.pk, "store_slug": tenant.store_slug})

    @action(detail=False, methods=["get"], url_path="my-companies")
    def my_companies(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response([])
        from .services import ensure_example_company_access
        ensure_example_company_access(user)
        # ISSUE #52: الدفاتر المُدارة لا تظهر هنا — مبدّل الشركات العادي ليس
        # مكانها، بل قائمة زبائن المكتب.
        qs = UserCompanyMembership.objects.filter(
            user=user, tenant__managed_by__isnull=True,
        ).select_related("tenant").order_by("tenant__CompanyName")
        return Response(UserCompanyMembershipSerializer(qs, many=True).data)

    @action(detail=True, methods=["get", "post"], url_path="managed-books")
    def managed_books(self, request, pk=None):
        """ISSUE #52: مكتب المحاسبة يفتح دفتراً مُداراً لعميله.

        GET: قائمة الدفاتر المُدارة التي يملكها هذا المكتب. POST: ينشئ دفتراً
        جديداً بعد فحص حصّة الخطة `office.managed_books` — مدير المكتب فقط.
        body (POST): {"CompanyName": "...", "template": "..."} (القالب اختياري).
        """
        office = self.get_object()
        self._require_company_manager(request, office)

        if request.method == "GET":
            qs = Tenant.objects.filter(managed_by=office).order_by("CompanyName")
            return Response(TenantSerializer(qs, many=True).data)

        # T-PLANLIMITS: يُفحص **قبل** الإنشاء — الدفتر المُدار لا يُحذف بعدها.
        enforce_limits(office, "office.managed_books")
        name = request.data.get("CompanyName")
        if not name:
            raise DRFValidationError({"CompanyName": "اسم الدفتر مطلوب."})
        from .company_templates import COMPANY_TEMPLATES, DEFAULT_TEMPLATE
        from .services import create_company
        template = request.data.get("template") or DEFAULT_TEMPLATE
        if template not in COMPANY_TEMPLATES:
            raise DRFValidationError({"template": f"قالب الشركة «{template}» غير معروف."})
        try:
            tenant = create_company(name, request.user, template=template, managed_by=office)
        except DjangoValidationError as e:
            raise DRFValidationError({"detail": e.messages if hasattr(e, "messages") else str(e)})
        return Response(TenantSerializer(tenant).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="set-default")
    def set_default(self, request):
        user = request.user
        company_id = request.data.get("company_id")
        if not company_id:
            raise DRFValidationError({"company_id": "معرف الشركة مطلوب."})
        
        # Verify user belongs to this company
        membership = UserCompanyMembership.objects.filter(user=user, tenant_id=company_id).first()
        if not membership:
            raise DRFValidationError({"company_id": "ليس لديك صلاحية الوصول لهذه الشركة أو أنها غير موجودة."})
        
        with transaction.atomic():
            UserCompanyMembership.objects.filter(user=user).update(is_default=False)
            membership.is_default = True
            membership.save(update_fields=["is_default"])
            
        return Response({"status": "success", "message": "تم تعيين الشركة الافتراضية بنجاح."})

    @action(detail=False, methods=["post"], url_path="set-ui-mode")
    def set_ui_mode(self, request):
        """THA-110: وضع عرض الواجهة لهذا المستخدم في الشركة النشطة.

        كتابة ذاتية بلا صلاحية إدارية — تفضيلٌ شخصي لا إعداد شركة، ولو خُزّن في
        `TenantSettings` لَما استطاع غير المدير حفظه (بوابة admin.settings.manage).
        الشركة تُحلّ من سياق الطلب لا من جسمه، والعضوية المكتوب عليها هي عضوية
        المستدعي وحدها.
        """
        mode = str(request.data.get("ui_mode") or "").strip()
        if mode not in {m for m, _ in UserCompanyMembership.UI_MODE_CHOICES}:
            raise DRFValidationError(
                {"ui_mode": "وضع غير صالح. القيم المسموحة: simple أو advanced."})

        tenant = get_tenant(request)
        if not tenant:
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة."})

        membership = UserCompanyMembership.objects.filter(
            user=request.user, tenant=tenant).first()
        if not membership:
            raise DRFValidationError({"tenant": "ليس لديك عضوية في هذه الشركة."})

        membership.ui_mode = mode
        membership.save(update_fields=["ui_mode"])
        return Response({"ui_mode": membership.ui_mode})

