from rest_framework import serializers
from .models import CustomerNote, Partner, PartnerBankAccount


class CustomerNoteSerializer(serializers.ModelSerializer):
    """ملاحظة/تذكير على بطاقة الزبون (CRM)."""
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)

    class Meta:
        model = CustomerNote
        fields = [
            'id', 'partner', 'title', 'body', 'remind_on', 'is_done',
            'priority', 'priority_display',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'created_by', 'created_by_name', 'priority_display',
            'created_at', 'updated_at',
        ]

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
            'id', 'name', 'legal_name', 'partner_type', 
            'tax_number', 'phone', 'email', 'country', 
            'street_address', 'city', 'state_or_province', 'postal_code',
            'credit_limit', 'image_path', 'created_at',
            'opening_balance', 'opening_balance_date', 'currency',
            'linked_account', 'group', 'default_cost_center',
            'end_of_dealing_date', 'assigned_price_tier', 'row_color',
            'attachments', 'bank_accounts'
        ]
        read_only_fields = ['id', 'created_at']

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
            'id', 'name', 'legal_name', 'partner_type', 'tax_number', 'phone',
            'email', 'country', 'street_address', 'city', 'state_or_province',
            'postal_code', 'credit_limit', 'image_path', 'created_at',
            'opening_balance', 'opening_balance_date', 'currency',
            'linked_account', 'group', 'default_cost_center',
            'end_of_dealing_date', 'assigned_price_tier', 'row_color',
        ]
        read_only_fields = fields

