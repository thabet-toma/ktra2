from rest_framework import serializers
from .models import (
    LogisticsDeal, LogisticsDealItem, LogisticsShipment, 
    LogisticsClearance, LogisticsExpense, LogisticsShipmentDeal,
    LogisticsPayment
)
from partners.serializers import PartnerSerializer
from inventory.models import Product

class LogisticsPaymentSerializer(serializers.ModelSerializer):
    journal_id_display = serializers.IntegerField(source='journal.id', read_only=True)
    
    class Meta:
        model = LogisticsPayment
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'is_posted', 'journal']

class LogisticsDealItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name_ar', read_only=True)
    total_price = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = LogisticsDealItem
        fields = ['id', 'product', 'product_name', 'quantity', 'unit_price', 'total_price', 'notes']

class LogisticsDealSerializer(serializers.ModelSerializer):
    items = LogisticsDealItemSerializer(many=True)
    payments = LogisticsPaymentSerializer(many=True, required=False)
    partner_name = serializers.CharField(source='partner.name', read_only=True)

    class Meta:
        model = LogisticsDeal
        fields = '__all__'
        read_only_fields = ['id', 'tenant', 'created_by', 'is_posted', 'journal', 'total_amount']

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        payments_data = validated_data.pop('payments', [])
        deal = LogisticsDeal.objects.create(**validated_data)
        
        total = 0
        for item_data in items_data:
            LogisticsDealItem.objects.create(deal=deal, **item_data)
            total += item_data['quantity'] * item_data['unit_price']
        
        for payment_data in payments_data:
            LogisticsPayment.objects.create(deal=deal, **payment_data)
        
        deal.total_amount = total
        deal.save()
        return deal

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        payments_data = validated_data.pop('payments', None)
        
        # Update Deal fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            # Smart update for items
            keep_items = []
            total = 0
            for item_data in items_data:
                item_id = item_data.get('id')
                if item_id:
                    # Update existing item
                    LogisticsDealItem.objects.filter(id=item_id, deal=instance).update(**item_data)
                    keep_items.append(item_id)
                    # Fetch for total calculation to ensure we have latest decimals
                    updated_item = LogisticsDealItem.objects.get(id=item_id)
                    total += updated_item.quantity * updated_item.unit_price
                else:
                    # Create new item
                    new_item = LogisticsDealItem.objects.create(deal=instance, **item_data)
                    keep_items.append(new_item.id)
                    total += new_item.quantity * new_item.unit_price
            
            # Delete items not in the list
            instance.items.exclude(id__in=keep_items).delete()
            
            instance.total_amount = total
            instance.save()
            
        if payments_data is not None:
            # Smart update for payments to preserve IDs and Journal links
            keep_payments = []
            for payment_data in payments_data:
                # Retrieve ID from initial_data since it might be read_only in validated_data
                # But here we assume payment_data comes from the list of dicts passed to the serializer
                pay_id = payment_data.get('id')
                
                if pay_id:
                    # Update existing (only if not posted, or allow notes update)
                    pay_instance = LogisticsPayment.objects.filter(id=pay_id, deal=instance).first()
                    if pay_instance:
                        for attr, value in payment_data.items():
                            if attr == 'id': continue
                            # If posted, maybe restrict what can be updated (e.g. only notes)
                            if not pay_instance.is_posted or attr == 'notes':
                                setattr(pay_instance, attr, value)
                        pay_instance.save()
                        keep_payments.append(pay_id)
                else:
                    # Create new
                    new_pay = LogisticsPayment.objects.create(deal=instance, **payment_data)
                    keep_payments.append(new_pay.id)
            
            # Delete payments not in the list (only if not posted!)
            instance.payments.exclude(id__in=keep_payments, is_posted=False).delete()

        return instance

class LogisticsShipmentSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source='shipping_agent.name', read_only=True)
    deals = LogisticsDealSerializer(many=True, read_only=True)

    class Meta:
        model = LogisticsShipment
        fields = '__all__'
        read_only_fields = ['id', 'tenant']

class LogisticsClearanceSerializer(serializers.ModelSerializer):
    broker_name = serializers.CharField(source='customs_broker.name', read_only=True)

    class Meta:
        model = LogisticsClearance
        fields = '__all__'
        read_only_fields = ['id', 'tenant']

class LogisticsExpenseSerializer(serializers.ModelSerializer):
    expense_account_name = serializers.CharField(source='expense_account.name', read_only=True)
    payable_account_name = serializers.CharField(source='payable_account.name', read_only=True)

    class Meta:
        model = LogisticsExpense
        fields = '__all__'
        read_only_fields = ['id', 'tenant', 'is_posted', 'journal']
