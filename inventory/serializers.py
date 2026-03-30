from rest_framework import serializers
from .models import ProductCategory, Product, UnitOfMeasure

class CategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = ProductCategory
        fields = ['id', 'tenant', 'name', 'parent', 'children']
        read_only_fields = ['id', 'tenant']

    def get_children(self, obj):
        if obj.children.exists():
            return CategorySerializer(obj.children.all(), many=True).data
        return []

class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = ['id', 'tenant', 'code', 'name_ar', 'name_en']
        read_only_fields = ['id', 'tenant']

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    uom_name = serializers.CharField(source='uom_id', read_only=True)
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'tenant', 'sku', 'barcode', 'name_ar', 'name_en', 
            'category', 'category_name', 'uom_id', 'uom_name', 
            'weight_kg', 'volume_cbm', 'hs_code', 'min_stock_level', 
            'is_serialized', 'is_for_sale_online', 'online_price', 'online_description',
            'attachments'
        ]
        read_only_fields = ['id', 'tenant']

    def get_attachments(self, obj):
        try:
            from core.models import SystemAttachment
            attachments = SystemAttachment.objects.filter(related_table='products', related_id=obj.id)
            return [{'id': a.id, 'file_path': a.file_path, 'file_type': a.file_type} for a in attachments]
        except Exception:
            return []

