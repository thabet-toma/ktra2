"""N0-T4 — Views for TenantSettings + TenantBook + Currency (Group Constants F11)."""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from core.api_defaults import ApiAuthAndUser
from core.tenant_utils import get_tenant
from .models import Currency, TenantBook, TenantSettings
from .serializers import TenantBookSerializer, TenantSettingsSerializer


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
    """ThenantSettings — one row per tenant. Provides /current/ action."""

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
