from rest_framework import serializers
from .models import ProductCategory, Product, UnitOfMeasure, StockMovement

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

    stock_status = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'tenant', 'sku', 'barcode', 'name_ar', 'name_en', 
            'category', 'category_name', 'uom_id', 'uom_name', 
            'weight_kg', 'volume_cbm', 'hs_code', 'min_stock_level', 
            'is_serialized', 'is_for_sale_online', 'online_price', 'online_description',
            'quantity_on_hand', 'avg_cost',
            'stock_status',
            'attachments',
        ]
        read_only_fields = ['id', 'tenant', 'quantity_on_hand', 'avg_cost']

    def get_attachments(self, obj):
        try:
            from core.models import SystemAttachment
            attachments = SystemAttachment.objects.filter(related_table='products', related_id=obj.id)
            return [{'id': a.id, 'file_path': a.file_path, 'file_type': a.file_type} for a in attachments]
        except Exception:
            return []

    def get_stock_status(self, obj):
        qty = float(obj.quantity_on_hand or 0)
        min_lvl = obj.min_stock_level or 0
        if qty <= 0:
            return 'out_of_stock'
        if min_lvl > 0 and qty <= min_lvl:
            return 'low_stock'
        return 'in_stock'


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    partner_name = serializers.CharField(source='partner.name', read_only=True, default=None)
    movement_type_display = serializers.CharField(source='get_movement_type_display', read_only=True)
    reference_type_display = serializers.CharField(source='get_reference_type_display', read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'product', 'product_name', 'product_sku',
            'movement_type', 'movement_type_display',
            'quantity', 'unit_cost', 'total_cost',
            'reference_type', 'reference_type_display', 'reference_id',
            'partner', 'partner_name',
            'movement_date', 'notes', 'created_at',
            'quantity_before', 'quantity_after',
            'avg_cost_before', 'avg_cost_after',
        ]
        read_only_fields = [
            'id', 'total_cost', 'created_at',
            'quantity_before', 'quantity_after',
            'avg_cost_before', 'avg_cost_after',
        ]

    def get_product_name(self, obj):
        p = obj.product
        return p.name_ar or p.name_en or p.sku

