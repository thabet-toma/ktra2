"""N0-T4 — Views for TenantSettings + TenantBook + Currency (Group Constants F11)."""
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from core.api_defaults import ApiAuthAndUser
from core.tenant_utils import get_tenant
from .models import Branch, Currency, TenantBook, TenantSettings, Tenant, UserCompanyMembership
from .serializers import BranchSerializer, TenantBookSerializer, TenantSettingsSerializer, TenantSerializer, UserCompanyMembershipSerializer


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
        tenant = get_tenant(self.request)
        qs = TenantSettings.objects.select_related("currency", "default_freight_credit_account")
        if tenant:
            qs = qs.filter(tenant=tenant)
        return qs

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

        # PUT / PATCH
        partial = request.method == "PATCH"
        ser = TenantSettingsSerializer(settings_obj, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        ser.save()
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
        tenant = get_tenant(self.request)
        qs = TenantBook.objects.all().order_by("document_type", "book_number")
        if tenant:
            qs = qs.filter(tenant=tenant)
        return qs

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

    الفرع يشارك الشركةَ شجرةَ الحسابات/الأصناف/الشركاء، وتُعزل فواتيره
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
        user = request.user
        if user.is_superuser:
            return
        is_manager = UserCompanyMembership.objects.filter(
            user=user, tenant=tenant, role="manager"
        ).exists()
        if not is_manager:
            raise PermissionDenied("فقط مدير الشركة يمكنه إدارة الفروع.")

    def create(self, request, *args, **kwargs):
        tenant = get_tenant(request)
        if not tenant:
            raise DRFValidationError({"tenant": "لا يوجد شركة محددة."})
        self._require_manager(request, tenant)
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
        return Tenant.objects.filter(memberships__user=user).order_by("CompanyName")

    def _can_create_company(self, user) -> bool:
        """Manager-only (M4-T3), with a bootstrap exception: a user with no
        memberships yet may create their first company. Superusers always may."""
        if user.is_superuser:
            return True
        memberships = UserCompanyMembership.objects.filter(user=user)
        if not memberships.exists():
            return True  # bootstrapping the first company
        return memberships.filter(role="manager").exists()

    def create(self, request, *args, **kwargs):
        if not self._can_create_company(request.user):
            raise PermissionDenied("فقط المدير يمكنه إنشاء شركة جديدة.")
        name = request.data.get("CompanyName")
        if not name:
            raise DRFValidationError({"CompanyName": "اسم الشركة مطلوب."})
        from .services import create_company
        try:
            tenant = create_company(name, request.user)
        except DjangoValidationError as e:
            # Known validation errors → 400; unexpected errors propagate to the
            # shaped 500 handler (with trace_id) instead of being masked as 400.
            raise DRFValidationError({"detail": e.messages if hasattr(e, "messages") else str(e)})
        return Response(TenantSerializer(tenant).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="my-companies")
    def my_companies(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response([])
        qs = UserCompanyMembership.objects.filter(user=user).select_related("tenant").order_by("tenant__CompanyName")
        return Response(UserCompanyMembershipSerializer(qs, many=True).data)

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

