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
        child_map = self.context.get('category_children')
        if child_map is not None:
            children = child_map.get(obj.id, [])
            return CategorySerializer(children, many=True, context=self.context).data
        children = list(obj.children.all())
        return CategorySerializer(children, many=True, context=self.context).data

class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = ['id', 'code', 'name_ar', 'name_en']
        read_only_fields = ['id']

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    uom_name = serializers.CharField(source='uom_id', read_only=True)
    attachments = serializers.SerializerMethodField()
    reserved_quantity = serializers.SerializerMethodField()
    available_quantity = serializers.SerializerMethodField()

    stock_status = serializers.SerializerMethodField()
    # تجميع البراندات: مفتاح الصنف الفرعي (للشجرة/الجرد/الجدول) + اسم العرض (الاسم+
    # البراند بين قوسين) + هل المجموعة صريحة (فيظهر المجلّد حتى لمنتج واحد).
    group_key = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    has_group = serializers.SerializerMethodField()
    # W8: تجميعات من StockMovement (منقّطة في ProductViewSet.get_queryset — لا N+1).
    # المشتريات = الوارد التراكمي (IN). المتوسط الشهري = صافي (OUT−RETURN_IN) 90ي ÷ 3.
    purchased_qty = serializers.SerializerMethodField()
    avg_monthly_sales = serializers.SerializerMethodField()

    # task14 M2 (DEF-A2): رقم الصنف اختياري — يولَّد خادمياً عند الغياب
    sku = serializers.CharField(max_length=50, required=False, allow_blank=True)

    class Meta:
        model = Product
        fields = [
            'id', 'tenant', 'sku', 'barcode', 'name_ar', 'name_en',
            'variant_group', 'brand',
            'category', 'category_name', 'uom_id', 'uom_name',
            'weight_kg', 'volume_cbm', 'hs_code', 'min_stock_level',
            'is_serialized', 'is_service',
            'is_for_sale_online', 'online_price', 'online_description',
            'quantity_on_hand', 'reserved_quantity', 'available_quantity', 'avg_cost',
            'purchased_qty', 'avg_monthly_sales',
            'stock_status', 'group_key', 'display_name', 'has_group',
            'created_at',
            'attachments',
        ]
        read_only_fields = ['id', 'tenant', 'quantity_on_hand', 'avg_cost', 'created_at']

    def get_group_key(self, obj):
        from .services import product_group_key
        return product_group_key(obj)

    def get_reserved_quantity(self, obj):
        reserved = self.context.get('reserved_quantity_map', {}).get(obj.id, 0)
        return str(reserved)

    def get_available_quantity(self, obj):
        from decimal import Decimal as _D
        reserved = _D(str(self.context.get('reserved_quantity_map', {}).get(obj.id, 0)))
        return str((_D(str(obj.quantity_on_hand or 0)) - reserved).quantize(_D('0.0001')))

    def get_display_name(self, obj):
        from .services import product_display_name
        return product_display_name(obj)

    def get_has_group(self, obj):
        from .services import product_has_explicit_group
        return product_has_explicit_group(obj)

    def get_purchased_qty(self, obj):
        v = getattr(obj, 'purchased_qty', None)
        return str(v) if v is not None else None

    def get_avg_monthly_sales(self, obj):
        # المتوسط الشهري = صافي المبيعات (OUT − RETURN_IN) خلال آخر 90 يوماً ÷ 3.
        sold = getattr(obj, 'sold_qty_90d', None)
        if sold is None:
            return None
        from decimal import Decimal as _D
        returned = getattr(obj, 'returned_qty_90d', None) or 0
        net = _D(str(sold)) - _D(str(returned))
        return str((net / _D('3')).quantize(_D('0.01')))

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
        attachment_map = self.context.get('product_attachments')
        if attachment_map is not None:
            return attachment_map.get(obj.id, [])
        try:
            from core.models import SystemAttachment
            attachments = SystemAttachment.objects.filter(
                tenant_id=obj.tenant_id,
                related_table='products',
                related_id=obj.id,
            )
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


class ProductLookupSerializer(ProductSerializer):
    """Small, explicit contract for invoice/deal product pickers."""

    class Meta(ProductSerializer.Meta):
        fields = [
            'id', 'sku', 'name_ar', 'name_en', 'display_name',
            'category', 'category_name', 'hs_code', 'min_stock_level',
            'quantity_on_hand', 'reserved_quantity', 'available_quantity',
            'avg_cost', 'is_for_sale_online',
            'online_price', 'online_description', 'attachments',
        ]


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
        if not obj.product: return ""
        from .services import product_display_name
        return product_display_name(obj.product)


# ── Phase 7 (T-I1/T-I2): مستندات المخزون ──────────────────────────────

class WarehouseTransferLineSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()

    class Meta:
        model = WarehouseTransferLine
        fields = ['id', 'product', 'product_name', 'quantity']
        read_only_fields = ['id']

    def get_product_name(self, obj):
        if not obj.product: return ""
        from .services import product_display_name
        return product_display_name(obj.product)


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
        if not obj.product: return ""
        from .services import product_display_name
        return product_display_name(obj.product)


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
