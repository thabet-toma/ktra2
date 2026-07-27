"""N0-T4 — Serializers for TenantSettings + TenantBook (Group Constants F11)."""
from rest_framework import serializers

from .models import Branch, Tenant, TenantBook, TenantSettings, UserCompanyMembership


class BranchSerializer(serializers.ModelSerializer):
    """task11 M4 — فرع تحت شركة أم."""

    class Meta:
        model = Branch
        fields = ["id", "name", "code", "is_main", "is_active", "created_at"]
        read_only_fields = ["id", "is_main", "created_at"]


class TenantSettingsSerializer(serializers.ModelSerializer):
    """ثوابت المجموعة — F11 page."""

    class Meta:
        model = TenantSettings
        fields = [
            "id",
            # بيانات الشركة
            "company_name_primary",
            "company_name_sub",
            "address",
            "po_box",
            "phone",
            "fax",
            "email",
            "logo_url",
            # أرقام رسمية
            "licensed_dealer_no",
            "income_tax_file_no",
            # ضرائب وافتراضيات
            "default_vat_rate",
            "default_source_discount_rate",
            "currency",
            # فترة مالية
            "fiscal_period_label",
            "fiscal_period_start",
            "fiscal_period_end",
            # دورة ملخص لوحة الأعمال
            "dashboard_month_start_day",
            # حسابات افتراضية
            "default_freight_credit_account",
            # خيارات
            "mixture_auto_fill_enabled",
            "barcode_action",
            # تفضيل المظهر (per-company)
            "font_scale",
            "font_family",
            # الجلسة (per-company)
            "idle_timeout_minutes",
        ]


class TenantBookSerializer(serializers.ModelSerializer):
    """دفتر أرقام لكل نوع مستند."""

    document_type_label = serializers.CharField(
        source="get_document_type_display", read_only=True
    )

    class Meta:
        model = TenantBook
        fields = [
            "id",
            "document_type",
            "document_type_label",
            "book_number",
            "name",
            "last_used_number",
            "is_active",
        ]
        read_only_fields = ["id", "document_type_label"]


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["TenantID", "CompanyName", "SubscriptionPlan", "Status", "CreatedAt", "import_enabled"]
        read_only_fields = ["import_enabled"]


class UserCompanyMembershipSerializer(serializers.ModelSerializer):
    tenant = TenantSerializer(read_only=True)

    class Meta:
        model = UserCompanyMembership
        fields = ["id", "tenant", "role", "is_default", "created_at", "can_access_import"]

