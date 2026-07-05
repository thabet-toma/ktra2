from rest_framework import serializers
from .models import CustomerNote, Partner, PartnerBankAccount


class CustomerNoteSerializer(serializers.ModelSerializer):
    """ملاحظة/تذكير على بطاقة الزبون (CRM)."""
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = CustomerNote
        fields = [
            'id', 'partner', 'title', 'body', 'remind_on', 'is_done',
            'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_by_name', 'created_at', 'updated_at']

class PartnerBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerBankAccount
        fields = [
            'id', 'bank_name', 'account_number', 'iban', 
            'swift_code', 'bank_address', 'beneficiary_name', 'currency', 'is_active'
        ]
        read_only_fields = ['id']

class PartnerSerializer(serializers.ModelSerializer):
    attachments = serializers.SerializerMethodField()
    class Meta:
        model = Partner
        fields = [
            'id', 'name', 'legal_name', 'partner_type', 
            'tax_number', 'phone', 'email', 'country', 
            'street_address', 'city', 'state_or_province', 'postal_code',
            'credit_limit', 'image_path', 'created_at',
            'opening_balance', 'opening_balance_date', 'currency',
            'linked_account', 'group', 'attachments'
        ]
        read_only_fields = ['id', 'created_at']

    def get_attachments(self, obj):
        try:
            from core.models import SystemAttachment
            attachments = SystemAttachment.objects.filter(related_table='partners', related_id=obj.id)
            return [{'id': a.id, 'file_path': a.file_path, 'file_type': a.file_type} for a in attachments]
        except Exception:
            return []

