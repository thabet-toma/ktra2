import logging
import re

from rest_framework import serializers

from core.tenant_utils import get_tenant
from .models import CustomerNote, Partner, PartnerBankAccount

logger = logging.getLogger(__name__)

# ── T-DUPID: أرقام الهوية الشبيهة (ضريبي/بنكي) ─────────────────────────
# «شبيه» = مطابق بعد إسقاط كل ما ليس رقماً أو حرفاً وتوحيد الحالة، فـ
# «123-456 789» و«123456789» رقمٌ واحد كُتب بشكلين. المقارنة في بايثون لا في
# SQL لأن التطبيع غير متاح بمحرّكين (MySQL/SQLite) بصيغة واحدة.
_IDENTIFIER_NOISE = re.compile(r"[^0-9A-Za-z]+")


def normalize_identifier(value) -> str:
    """صورة الرقم القابلة للمقارنة — أرقام وحروف لاتينية فقط بحالة موحّدة."""
    return _IDENTIFIER_NOISE.sub("", str(value or "")).upper()


def find_partner_with_similar_tax_number(tenant_id, tax_number, *, exclude_id=None):
    """(معرّف، اسم) أول طرف في الشركة برقم ضريبي شبيه، أو None.

    الفحص يشمل كل الأنواع (عميل/مورد/وكيل/مخلّص/ناقل) — الرقم الضريبي هوية
    كيان قانوني واحد، لا صفة تعامل تتكرّر بأنواع.
    """
    target = normalize_identifier(tax_number)
    if not target or tenant_id is None:
        return None
    qs = (
        Partner.objects.filter(tenant_id=tenant_id)
        .exclude(tax_number__isnull=True).exclude(tax_number="")
    )
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    for pk, name, existing in qs.values_list("id", "name", "tax_number"):
        if normalize_identifier(existing) == target:
            return pk, name
    return None


def find_partner_with_similar_bank_account(
    tenant_id, account_number, *, exclude_partner_id=None,
):
    """(معرّف، اسم) صاحب حساب بنكي شبيه في الشركة، أو None.

    النطاق من الشريك (`partner__tenant_id`) لا من عمود tenant في الحساب، ليبقى
    الفحص صحيحاً على صفوف قديمة قد يكون tenant فيها غير مضبوط.
    """
    target = normalize_identifier(account_number)
    if not target or tenant_id is None:
        return None
    qs = PartnerBankAccount.objects.filter(partner__tenant_id=tenant_id)
    if exclude_partner_id:
        qs = qs.exclude(partner_id=exclude_partner_id)
    for existing, pk, name in qs.values_list(
        "account_number", "partner_id", "partner__name",
    ):
        if normalize_identifier(existing) == target:
            return pk, name
    return None


class CustomerNoteSerializer(serializers.ModelSerializer):
    """ملاحظة/تذكير على طرف أو هدف عام داخل المنصة."""
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)

    class Meta:
        model = CustomerNote
        fields = [
            'id', 'partner', 'title', 'body', 'remind_on', 'is_done',
            'target_type', 'target_id', 'target_label', 'target_path',
            'priority', 'priority_display',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'created_by', 'created_by_name', 'priority_display',
            'created_at', 'updated_at',
        ]
        extra_kwargs = {
            'partner': {'required': False, 'allow_null': True},
        }

    def validate_target_path(self, value):
        value = str(value or '').strip()
        if value and (
            not value.startswith('/') or value.startswith('//') or '\\' in value
            or any(ord(char) < 32 for char in value)
        ):
            raise serializers.ValidationError('مسار الهدف يجب أن يكون رابطاً داخلياً يبدأ بـ /.')
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        tenant = get_tenant(request) if request is not None else None
        instance = self.instance
        partner = attrs.get('partner', getattr(instance, 'partner', None))
        if partner is not None and tenant is not None and partner.tenant_id != tenant.TenantID:
            raise serializers.ValidationError({'partner': 'الطرف لا يتبع الشركة المحددة.'})

        target_fields = ('target_type', 'target_id', 'target_label', 'target_path')
        target = {
            field: str(attrs.get(field, getattr(instance, field, '')) or '').strip()
            for field in target_fields
        }
        for field, value in target.items():
            if field in attrs:
                attrs[field] = value
        if partner is None:
            missing = [field for field, value in target.items() if not value]
            if missing:
                raise serializers.ValidationError({
                    field: 'هذا الحقل مطلوب للملاحظة العامة.' for field in missing
                })
        return attrs

class PartnerBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerBankAccount
        fields = [
            'id', 'bank_name', 'account_number', 'branch_name', 'iban',
            'swift_code', 'bank_address', 'beneficiary_name', 'currency',
            'is_active', 'is_default',
        ]
        read_only_fields = ['id']

class PartnerSerializer(serializers.ModelSerializer):
    attachments = serializers.SerializerMethodField()
    bank_accounts = PartnerBankAccountSerializer(many=True, read_only=True)
    class Meta:
        model = Partner
        fields = [
            'id', 'name', 'legal_name', 'partner_type', 'supplier_scope',
            'tax_number', 'phone', 'email', 'country',
            'street_address', 'city', 'state_or_province', 'postal_code',
            'credit_limit', 'image_path', 'created_at',
            'opening_balance', 'opening_balance_date', 'currency',
            'linked_account', 'group', 'default_cost_center',
            'end_of_dealing_date', 'assigned_price_tier', 'row_color',
            'attachments', 'bank_accounts'
        ]
        read_only_fields = ['id', 'created_at']

    def _tenant_id(self):
        """شركة البطاقة: من السطر عند التعديل، ومن سياق الطلب عند الإنشاء."""
        if self.instance is not None:
            return self.instance.tenant_id
        request = self.context.get('request')
        tenant = get_tenant(request) if request is not None else None
        return getattr(tenant, 'TenantID', None)

    def validate_tax_number(self, value):
        """T-DUPID: لا طرفان لرقم ضريبي واحد — ولو كُتب بشكل مختلف."""
        hit = find_partner_with_similar_tax_number(
            self._tenant_id(), value,
            exclude_id=self.instance.pk if self.instance is not None else None,
        )
        if hit:
            logger.info(
                "partner.duplicate_tax_number tenant=%s value=%r existing=%s",
                self._tenant_id(), value, hit[0],
            )
            raise serializers.ValidationError(
                f"الرقم الضريبي «{value}» مستخدم للطرف «{hit[1]}» (#{hit[0]}) — "
                "لا يُقبل رقم مطابق أو شبيه."
            )
        return value

    def get_attachments(self, obj):
        try:
            from core.models import SystemAttachment
            attachments = SystemAttachment.objects.filter(related_table='partners', related_id=obj.id)
            return [{'id': a.id, 'file_path': a.file_path, 'file_type': a.file_type} for a in attachments]
        except Exception:
            return []


class PartnerListSerializer(serializers.ModelSerializer):
    """List/lookup contract without the per-row attachment query."""

    class Meta:
        model = Partner
        fields = [
            'id', 'name', 'legal_name', 'partner_type', 'supplier_scope',
            'tax_number', 'phone',
            'email', 'country', 'street_address', 'city', 'state_or_province',
            'postal_code', 'credit_limit', 'image_path', 'created_at',
            'opening_balance', 'opening_balance_date', 'currency',
            'linked_account', 'group', 'default_cost_center',
            'end_of_dealing_date', 'assigned_price_tier', 'row_color',
        ]
        read_only_fields = fields

