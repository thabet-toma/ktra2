from rest_framework import serializers
from .models import (
    ProductCategory, Product, UnitOfMeasure, StockMovement, Warehouse,
    WarehouseTransfer, WarehouseTransferLine, Stocktake, StocktakeLine,
)


class WarehouseSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True, default=None)

    class Meta:
        model = Warehouse
        fields = [
            'id', 'tenant', 'branch', 'branch_name', 'name', 'code',
            'location', 'is_default', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'tenant', 'created_at']

    def validate_name(self, value):
        if not (value or '').strip():
            raise serializers.ValidationError('اسم المستودع مطلوب.')
        return value.strip()

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

    # task14 M2 (DEF-A2): رقم الصنف اختياري — يولَّد خادمياً عند الغياب
    sku = serializers.CharField(max_length=50, required=False, allow_blank=True)

    class Meta:
        model = Product
        fields = [
            'id', 'tenant', 'sku', 'barcode', 'name_ar', 'name_en',
            'category', 'category_name', 'uom_id', 'uom_name',
            'weight_kg', 'volume_cbm', 'hs_code', 'min_stock_level',
            'is_serialized', 'is_service',
            'is_for_sale_online', 'online_price', 'online_description',
            'quantity_on_hand', 'avg_cost',
            'stock_status',
            'created_at',
            'attachments',
        ]
        read_only_fields = ['id', 'tenant', 'quantity_on_hand', 'avg_cost', 'created_at']

    def validate(self, attrs):
        # task14 M2 (DEF-A2/A3): الاسم هو الحقل الإلزامي الوحيد — والخطأ يسمّي حقله الحقيقي
        name_ar = attrs.get('name_ar', getattr(self.instance, 'name_ar', None))
        name_en = attrs.get('name_en', getattr(self.instance, 'name_en', None))
        if not ((name_ar or '').strip() or (name_en or '').strip()):
            raise serializers.ValidationError(
                {'name_ar': 'اسم الصنف مطلوب — أدخل الاسم بالعربية أو بالإنجليزية.'}
            )
        return attrs

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
    origin = serializers.CharField(read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'product', 'product_name', 'product_sku',
            'movement_type', 'movement_type_display',
            'quantity', 'unit_cost', 'total_cost',
            'reference_type', 'reference_type_display', 'reference_id', 'origin',
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


# ── Phase 7 (T-I1/T-I2): مستندات المخزون ──────────────────────────────

class WarehouseTransferLineSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()

    class Meta:
        model = WarehouseTransferLine
        fields = ['id', 'product', 'product_name', 'quantity']
        read_only_fields = ['id']

    def get_product_name(self, obj):
        p = obj.product
        return p.name_ar or p.name_en or p.sku


class WarehouseTransferSerializer(serializers.ModelSerializer):
    lines = WarehouseTransferLineSerializer(many=True)
    source_warehouse_name = serializers.CharField(source='source_warehouse.name', read_only=True)
    dest_warehouse_name = serializers.CharField(source='dest_warehouse.name', read_only=True)

    class Meta:
        model = WarehouseTransfer
        fields = [
            'id', 'transfer_number', 'transfer_date',
            'source_warehouse', 'source_warehouse_name',
            'dest_warehouse', 'dest_warehouse_name',
            'notes', 'is_posted', 'created_at', 'lines',
        ]
        read_only_fields = ['id', 'transfer_number', 'is_posted', 'created_at']

    def validate(self, attrs):
        src = attrs.get('source_warehouse') or getattr(self.instance, 'source_warehouse', None)
        dst = attrs.get('dest_warehouse') or getattr(self.instance, 'dest_warehouse', None)
        if src and dst and src == dst:
            raise serializers.ValidationError('مستودع المصدر والوجهة متطابقان.')
        return attrs

    def create(self, validated_data):
        lines = validated_data.pop('lines', [])
        transfer = WarehouseTransfer.objects.create(**validated_data)
        for ln in lines:
            WarehouseTransferLine.objects.create(transfer=transfer, **ln)
        return transfer

    def update(self, instance, validated_data):
        if instance.is_posted:
            raise serializers.ValidationError('لا يمكن تعديل تحويل مُرحَّل.')
        lines = validated_data.pop('lines', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            for ln in lines:
                WarehouseTransferLine.objects.create(transfer=instance, **ln)
        return instance


class StocktakeLineSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()

    class Meta:
        model = StocktakeLine
        fields = ['id', 'product', 'product_name', 'counted_quantity', 'system_quantity', 'variance']
        read_only_fields = ['id', 'system_quantity', 'variance']

    def get_product_name(self, obj):
        p = obj.product
        return p.name_ar or p.name_en or p.sku


class StocktakeSerializer(serializers.ModelSerializer):
    lines = StocktakeLineSerializer(many=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True, default=None)

    class Meta:
        model = Stocktake
        fields = [
            'id', 'stocktake_number', 'stocktake_date',
            'warehouse', 'warehouse_name', 'notes',
            'is_posted', 'journal', 'created_at', 'lines',
        ]
        read_only_fields = ['id', 'stocktake_number', 'is_posted', 'journal', 'created_at']

    def create(self, validated_data):
        lines = validated_data.pop('lines', [])
        stocktake = Stocktake.objects.create(**validated_data)
        for ln in lines:
            StocktakeLine.objects.create(stocktake=stocktake, **ln)
        return stocktake

    def update(self, instance, validated_data):
        if instance.is_posted:
            raise serializers.ValidationError('لا يمكن تعديل جرد مُرحَّل.')
        lines = validated_data.pop('lines', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            for ln in lines:
                StocktakeLine.objects.create(stocktake=instance, **ln)
        return instance

