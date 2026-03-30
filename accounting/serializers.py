from rest_framework import serializers
from .models import Account, JournalHeader, JournalLine, Cheque, CostCenter
from partners.models import Partner

class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ['id', 'code', 'name', 'parent', 'account_type', 'is_active']

class CostCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostCenter
        fields = '__all__'

class JournalLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    # Use PrimaryKeyRelatedField for strict ID validation
    partner = serializers.PrimaryKeyRelatedField(
        queryset=Partner.objects.all(),
        many=False, 
        read_only=False,
        required=False, 
        allow_null=True
    )
    cost_center = serializers.PrimaryKeyRelatedField(
        queryset=CostCenter.objects.all(),
        many=False,
        read_only=False,
        required=False,
        allow_null=True
    )

    class Meta:
        model = JournalLine
        fields = ['id', 'account', 'debit', 'credit', 'partner', 'cost_center', 'project_id']


class JournalHeaderSerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True)
    
    class Meta:
        model = JournalHeader
        fields = ['id', 'transaction_date', 'reference_type', 'reference_id', 'description', 'is_posted', 'lines']

    def create(self, validated_data):
        lines_data = validated_data.pop('lines')
        # Tenant might not be in validated_data if it's read_only in ViewSet
        # Reliance on journal.tenant is safer if ViewSet handles tenant assignment
        
        journal = JournalHeader.objects.create(**validated_data)
        
        for line_data in lines_data:
            line_data.pop('id', None)
            JournalLine.objects.create(
                journal=journal,
                tenant=journal.tenant, # ALWAYS use the journal's tenant
                **line_data
            )
        return journal

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if lines_data is not None:
            existing_lines = {line.id: line for line in instance.lines.all()}
            seen_ids = set()

            for line_data in lines_data:
                line_id = line_data.get('id')
                if line_id and line_id in existing_lines:
                    line_instance = existing_lines[line_id]
                    for attr, value in line_data.items():
                        if attr != 'id':
                            setattr(line_instance, attr, value)
                    line_instance.save()
                    seen_ids.add(line_id)
                else:
                    line_data.pop('id', None)
                    JournalLine.objects.create(
                        journal=instance,
                        tenant=instance.tenant,
                        **line_data
                    )
            
            for line_id, line_instance in existing_lines.items():
                if line_id not in seen_ids:
                    line_instance.delete()

        return instance

class ChequeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cheque
        fields = '__all__'

