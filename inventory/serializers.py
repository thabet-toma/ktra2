from rest_framework import serializers
from .models import (
    ProductCategory, ProductFamily, Product, ProductPriceTier, UnitOfMeasure,
    StockMovement, SupplierProduct, Warehouse, WarehouseTransfer,
    WarehouseTransferLine, Stocktake, StocktakeLine,
)


class ProductFamilySerializer(serializers.ModelSerializer):
    """«المنتج» (#20) — الأب فوق البراند. لا رصيد ولا تكلفة هنا؛ كل مجموعٍ
    على مستواه يُشتقّ عند القراءة من برانداته (`Product.family`)."""

    class Meta:
        model = ProductFamily
        fields = [
            'id', 'tenant', 'name_ar', 'name_en', 'category', 'uom',
            'min_stock_level', 'max_stock_level',
            'is_serialized', 'is_service', 'allow_negative_stock',
            'sale_account_override', 'sale_return_account_override',
            'purchase_account_override', 'purchase_return_account_override',
            'supplier_account_override', 'ending_inventory_account_override',
            'created_at',
        ]
        read_only_fields = ['id', 'tenant', 'created_at']
        # لا `validate` هنا: الطرف قراءةٌ فقط (`ProductFamilyViewSet`) والكتابة
        # كلُّها على صفّ البراند، فتحقُّقُ تصنيفِ الشركة يجري هناك
        # (`ProductViewSet._validate_category_tenant`). تحقُّقٌ لا يعمل أسوأ من
        # غيابه: يُقرأ فيُظنّ أن الطرف محروس.


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

    def validate_name(self, value):
        # تصنيفٌ بلا اسم يظهر في الشجرة سطراً فارغاً لا يُنقر ولا يُميَّز.
        if not (value or '').strip():
            raise serializers.ValidationError('اسم التصنيف مطلوب.')
        return value.strip()

    def validate(self, attrs):
        if 'name' not in attrs and self.instance is None:
            raise serializers.ValidationError({'name': 'اسم التصنيف مطلوب.'})
        if 'parent' in attrs:
            self._validate_parent(attrs.get('parent'))
        return attrs

    def _validate_parent(self, parent):
        """الأب من الشركة نفسها، وليس العقدة نفسها، ولا أحد أحفادها.

        بلا هذا الحرس كان `PATCH {"parent": <حفيد>}` مقبولاً، فتنشأ حلقة في
        الشجرة: كلّ من يمشيها (المنتقي، الجدول، الكرت المجمّع) يدور بلا نهاية.
        نجا قارئٌ واحد لأنه يحمل مجموعة `seen` — وتلك تُخفي الحلقة ولا تمنعها.
        الصعود يقرأ الأزواج مسطّحةً مرّةً واحدة: استعلامٌ واحد مهما عمقت الشجرة.
        """
        if parent is None:
            return
        request = self.context.get('request')
        if request is not None:
            from core.tenant_utils import get_tenant
            tenant = get_tenant(request)
            if tenant is not None and parent.tenant_id != tenant.pk:
                raise serializers.ValidationError(
                    {'parent': 'التصنيف الأب غير موجود لهذه الشركة.'}
                )
        if self.instance is None:
            return
        if parent.pk == self.instance.pk:
            raise serializers.ValidationError(
                {'parent': 'لا يصلح التصنيف أباً لنفسه.'}
            )
        pairs = dict(
            ProductCategory.objects.filter(tenant_id=parent.tenant_id)
            .values_list('id', 'parent_id')
        )
        node_id = pairs.get(parent.pk)
        seen = set()
        while node_id and node_id not in seen:
            if node_id == self.instance.pk:
                raise serializers.ValidationError({
                    'parent': 'لا يصلح تصنيفٌ فرعي أباً لأصله — تنشأ حلقة في الشجرة.'
                })
            seen.add(node_id)
            node_id = pairs.get(node_id)

class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = ['id', 'code', 'name_ar', 'name_en']
        read_only_fields = ['id']

class ProductPriceTierSerializer(serializers.ModelSerializer):
    """T-ITEMS M5: شريحة سعرٍ واحدة (بيع/شراء × رقم).

    خمسُ شرائح بيع وخمسُ شراء لكل منتج — الجدول موجود منذ N8-T9 وشاشةُ الكرت
    تعرضه، لكن لا نقطةَ تكتبه: يملأ المستخدم الشرائح ويقرأ «تم الحفظ» وتضيع.
    والشرائح ليست زينة: `core/pricing.py` (`resolve_sales_price`) يقرأ شريحة
    البيع الأولى كمصدرٍ خامس للسعر، فبمجرّد أن تُحفَظ تدخل تسعير الفواتير.
    """

    class Meta:
        model = ProductPriceTier
        fields = ['id', 'tier_type', 'tier_number', 'price', 'currency', 'tax_inclusive']
        read_only_fields = ['id']


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    price_tiers = ProductPriceTierSerializer(many=True, required=False)
    uom_name = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    reserved_quantity = serializers.SerializerMethodField()
    available_quantity = serializers.SerializerMethodField()

    stock_status = serializers.SerializerMethodField()
    # تجميع البراندات: مفتاح المنتج الفرعي (للشجرة/الجرد/الجدول) + اسم العرض (الاسم+
    # البراند بين قوسين) + هل المجموعة صريحة (فيظهر المجلّد حتى لمنتج واحد).
    group_key = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    has_group = serializers.SerializerMethodField()
    # #23: شاشة الأصناف تجمع صفوف البراندات تحت صفّ منتجٍ واحد — تحتاج معرّف
    # الأب واسمه لتقرّر أيّ صفوفٍ تتجمّع (مرآة `ProductLookupSerializer`).
    family_id = serializers.IntegerField(read_only=True)
    family_name = serializers.SerializerMethodField()
    # #35: الحدّ **الحاكم** — نفس المصدر الذي حكمت به `stock_status` (حدّ
    # الأب إن كان له أبٌ ظاهرٌ في `family_thresholds`، وإلا حدّ الصفّ نفسه).
    # قراءةٌ فقط عمداً وباسمٍ جديد: `min_stock_level`/`max_stock_level`
    # يبقيان كما هما لأن نموذج التحرير يبعثهما في الحفظ، وتبديل معناهما
    # يكسر جولة الكتابة بصمت.
    effective_min_stock_level = serializers.SerializerMethodField()
    effective_max_stock_level = serializers.SerializerMethodField()
    # W8: تجميعات من StockMovement (منقّطة في ProductViewSet.get_queryset — لا N+1).
    # المشتريات = الوارد التراكمي (IN). المتوسط الشهري = صافي (OUT−RETURN_IN) 90ي ÷ 3.
    purchased_qty = serializers.SerializerMethodField()
    avg_monthly_sales = serializers.SerializerMethodField()

    # task14 M2 (DEF-A2): رقم المنتج اختياري — يولَّد خادمياً عند الغياب
    sku = serializers.CharField(max_length=50, required=False, allow_blank=True)
    # M0: وحدة القياس لم تكن تُحفظ من أيّ شاشة. إدراج `uom_id` في `fields` لا
    # يكفي: DRF لا يرى فيه علاقةً (العلاقة اسمها `uom`) بل صفةَ نموذج، فيبنيه
    # `ReadOnlyField` ويبتلع القيمة بصمت. التصريح هنا يُبقي اسم الحقل على السلك
    # كما تعرفه الواجهة ويجعله قابلاً للكتابة.
    uom_id = serializers.PrimaryKeyRelatedField(
        source='uom', queryset=UnitOfMeasure.objects.all(),
        required=False, allow_null=True,
    )
    class Meta:
        model = Product
        fields = [
            'id', 'tenant', 'sku', 'barcode', 'name_ar', 'name_en',
            'variant_group', 'brand',
            'category', 'category_name', 'uom_id', 'uom_name',
            # T-ITEMS M5: حقولٌ كانت تُعرض في الكرت ولا تُحفظ — صارت حقيقيةً
            # (وحدتان إضافيتان بمعاملَيهما، الوصف الداخلي، موقع التخزين).
            'uom2', 'uom2_factor', 'uom3', 'uom3_factor',
            'description', 'storage_location',
            # تجاوزات الحسابات على مستوى المنتج (نمط Odoo: حساب إيراد/مصروف
            # على المنتج يسبق حساب تصنيفه).
            'sale_account_override', 'sale_return_account_override',
            'purchase_account_override', 'purchase_return_account_override',
            'supplier_account_override', 'ending_inventory_account_override',
            'price_tiers',
            'weight_kg', 'volume_cbm', 'hs_code', 'min_stock_level', 'max_stock_level',
            # #33: مفتاحٌ لكل صنف — أيّ مسارٍ يحكم اقتراح التجديد (يدوي/تلقائي).
            'reorder_mode',
            'is_serialized', 'is_service',
            # THA-24: سياسة الكفالة على المنتج — تقرأها الكفالة عند ترحيل البيع،
            # ويحرّرها المستخدم من كرت المنتج. بلا إدراجها هنا يبتلع DRF قيمتها
            # في الكتابة بصمت فيبدو الحقل محفوظاً وهو ليس كذلك.
            'warranty_months', 'supplier_warranty_months',
            'is_for_sale_online', 'online_price', 'online_description',
            'quantity_on_hand', 'reserved_quantity', 'available_quantity', 'avg_cost',
            # كرت المنتج: سعر البيع الافتراضي — قابل للتحرير بجانب التكلفة المحسوبة.
            'sale_price',
            'purchased_qty', 'avg_monthly_sales',
            'stock_status', 'group_key', 'display_name', 'has_group',
            'family_id', 'family_name',
            'effective_min_stock_level', 'effective_max_stock_level',
            'created_at',
            'attachments',
        ]
        read_only_fields = ['id', 'tenant', 'quantity_on_hand', 'avg_cost', 'created_at']

    def get_group_key(self, obj):
        from .services import product_group_key
        return product_group_key(obj)

    def get_uom_name(self, obj):
        """اسم الوحدة لا معرّفها — كان `source='uom_id'` فيعرض الكرت رقماً.

        مصدران: الوحدة المرتبطة (FK)، وإلا نصّ الوحدة القديم (`uom_legacy`)
        الذي تحمله بيانات ما قبل جدول الوحدات.
        """
        if obj.uom_id and getattr(obj, 'uom', None):
            return obj.uom.name_ar or obj.uom.name_en or obj.uom.code
        return obj.uom_legacy or None

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
        return product_has_explicit_group(
            obj, family_sibling_counts=self.context.get('family_brand_counts'),
        )

    def get_family_name(self, obj):
        if not obj.family_id:
            return None
        return obj.family.name_ar or obj.family.name_en or None

    def _governing_thresholds(self, obj):
        """#35: نفس شرط `stock_status_of` حرفاً — أبٌ ظاهرٌ في
        `family_thresholds` يحكم، وإلا الصفّ نفسه (بلا أبٍ، أو أبٌ لم يظهر
        بعد في الخريطة). خامٌ من `family_thresholds` (خريطة السياق، بلا
        استعلامٍ إضافي) لا استدعاءٌ جديد لـ`effective_min`/`effective_max`."""
        thresholds = self.context.get('family_thresholds')
        if obj.family_id and thresholds and obj.family_id in thresholds:
            return thresholds[obj.family_id]
        return obj.min_stock_level, obj.max_stock_level

    def get_effective_min_stock_level(self, obj):
        return self._governing_thresholds(obj)[0]

    def get_effective_max_stock_level(self, obj):
        return self._governing_thresholds(obj)[1]

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

    ACCOUNT_OVERRIDE_FIELDS = (
        'sale_account_override', 'sale_return_account_override',
        'purchase_account_override', 'purchase_return_account_override',
        'supplier_account_override', 'ending_inventory_account_override',
    )

    def validate(self, attrs):
        # task14 M2 (DEF-A2/A3): الاسم هو الحقل الإلزامي الوحيد — والخطأ يسمّي حقله الحقيقي
        name_ar = attrs.get('name_ar', getattr(self.instance, 'name_ar', None))
        name_en = attrs.get('name_en', getattr(self.instance, 'name_en', None))
        if not ((name_ar or '').strip() or (name_en or '').strip()):
            raise serializers.ValidationError(
                {'name_ar': 'اسم المنتج مطلوب — أدخل الاسم بالعربية أو بالإنجليزية.'}
            )
        self._validate_barcode_unique(attrs)
        self._validate_account_overrides(attrs)
        return attrs

    def _validate_account_overrides(self, attrs):
        """كل حساب تجاوزٍ من شركة المنتج نفسها — الحسابات معزولةٌ بالشركة.

        بلا هذا الفحص يُقبل معرّف حسابٍ من شركةٍ أخرى (الـFK لا يعرف الشركة)،
        فيُرحَّل بيعُ المنتج على دفتر شركةٍ ليست صاحبته — تسريبٌ محاسبي صامت.
        نفس منطق `ProductViewSet._validate_category_tenant`.
        """
        present = {f: attrs[f] for f in self.ACCOUNT_OVERRIDE_FIELDS
                   if f in attrs and attrs[f] is not None}
        if not present:
            return
        tenant_id = getattr(self.instance, 'tenant_id', None)
        if tenant_id is None:
            request = self.context.get('request')
            if request is None:
                return
            from core.tenant_utils import get_tenant
            tenant = get_tenant(request)
            if tenant is None:
                return
            tenant_id = tenant.TenantID
        for field, account in present.items():
            if getattr(account, 'tenant_id', None) != tenant_id:
                raise serializers.ValidationError(
                    {field: 'الحساب غير موجود لهذه الشركة.'}
                )

    # ── الشرائح: كتابة متداخلة (upsert بالمفتاح، وحذف الغائب) ───────────────
    def _save_price_tiers(self, product, tiers):
        """الحمولة **تصف الحالة النهائية**: ما ورد يُنشأ أو يُحدَّث، وما غاب يُحذف.

        المفتاح `(tier_type, tier_number)` هو نفسه قيد التفرّد في الجدول، فلا
        تتكاثر الشريحة الواحدة عند إعادة الحفظ.
        """
        wanted = {}
        for tier in tiers:
            key = (tier['tier_type'], tier['tier_number'])
            wanted[key] = tier
        existing = {
            (t.tier_type, t.tier_number): t
            for t in product.price_tiers.all()
        }
        for key, tier in wanted.items():
            row = existing.get(key)
            if row is None:
                ProductPriceTier.objects.create(product=product, **tier)
                continue
            row.price = tier['price']
            row.currency = tier['currency']
            row.tax_inclusive = tier.get('tax_inclusive', False)
            row.save(update_fields=['price', 'currency', 'tax_inclusive'])
        stale = [row.pk for key, row in existing.items() if key not in wanted]
        if stale:
            ProductPriceTier.objects.filter(pk__in=stale).delete()

    def create(self, validated_data):
        # #20: نقطة الإنشاء الموحّدة — تُنشئ «المنتج» وبراندَه الضمنيّ معاً.
        from .services import create_product_with_family
        tiers = validated_data.pop('price_tiers', None)
        _family, product = create_product_with_family(**validated_data)
        if tiers is not None:
            self._save_price_tiers(product, tiers)
        return product

    def update(self, instance, validated_data):
        # غيابُ المفتاح = «لا تمسّ الشرائح» (تعديلٌ جزئي للاسم مثلاً)؛ قائمةٌ
        # فارغة = «امسح الشرائح» — تمييزٌ لازم وإلا مسح كلُّ PATCH الشرائحَ.
        tiers = validated_data.pop('price_tiers', None)
        product = super().update(instance, validated_data)
        if tiers is not None:
            self._save_price_tiers(product, tiers)
        return product

    def _validate_barcode_unique(self, attrs):
        """الباركود يجب أن يميّز منتجاً واحداً في الشركة — وإلا فقد معناه.

        العمود ليس فريداً في المخطّط ولن يُجعَل كذلك: بياناتٌ قديمة تحمل تكراراً،
        وقيدٌ فريد يمنع حفظ أي منتج منها. الحرس هنا على **ما يُكتَب**: تكرارٌ قائم
        يبقى كما هو حتى يُحرَّر صاحبه.
        """
        if 'barcode' not in attrs:
            return
        barcode = (attrs.get('barcode') or '').strip()
        if not barcode:
            return
        tenant_id = getattr(self.instance, 'tenant_id', None)
        if tenant_id is None:
            request = self.context.get('request')
            if request is None:
                return
            from core.tenant_utils import get_tenant
            tenant = get_tenant(request)
            if tenant is None:
                return
            tenant_id = tenant.TenantID
        clash = Product.objects.filter(tenant_id=tenant_id, barcode=barcode)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        other = clash.only('sku', 'name_ar', 'name_en').first()
        if other is not None:
            raise serializers.ValidationError({
                'barcode': (
                    f'الباركود «{barcode}» مستخدم للمنتج '
                    f'«{other.name_ar or other.name_en or other.sku}».'
                )
            })

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
        # T-REORDER: القاعدة تعيش في `inventory/stock_status.py` وحدها.
        from .stock_status import stock_status_of
        return stock_status_of(
            obj,
            reserved_map=self.context.get('reserved_quantity_map'),
            family_totals=self.context.get('family_available_map'),
        )


class ProductLookupSerializer(ProductSerializer):
    """Small, explicit contract for invoice/deal product pickers.

    يجب أن يغطّي **كل** ما تقرؤه شاشات الفواتير من المنتج، وإلا رجعت تلك الشاشات
    إلى العقد الكامل فتجلب لكل منتج تحليلاتٍ وحقولَ كرتٍ لا تعرضها (قياس على
    1490 منتجاً: 1,145 كيلوبايت / 1,249 مِلّي ثانية مقابل 609 / 331).
    """

    # T-SUPSKU: أرقام كتالوج الموردين لهذا المنتج، مفصولةً بمسافات — هنا وحدها
    # لا على العقد الكامل: منتقي المستندات يجلب الكتالوج دفعةً واحدة ويبحث
    # موضعياً، فبحث الخادم لا يبلغه. تُقرأ من `supplier_codes` المجلوبة مسبقاً
    # في `ProductViewSet.get_queryset`، وإلا صارت استعلاماً لكل صفّ من 1490.
    # نصٌّ لا مصفوفةُ كائنات — المنتقي يطابق ولا يعرض.
    supplier_codes_text = serializers.SerializerMethodField()

    def get_supplier_codes_text(self, obj):
        codes = [c.supplier_sku for c in obj.supplier_codes.all() if c.supplier_sku]
        return ' '.join(codes)

    # #22: معرّف واسم «المنتج» (الأب) — البند يبقى دائماً براندًا، لكن هذان
    # الحقلان وحدهما (لا أكثر، العقد ضيّقٌ عمداً) يسمحان لمنتقي المستند بمعرفة
    # أيّ براندات تتبع نفس المنتج بلا استرجاع الأب نفسه كخيارٍ قابل للإدراج.
    family_id = serializers.IntegerField(read_only=True)
    family_name = serializers.SerializerMethodField()

    def get_family_name(self, obj):
        if not obj.family_id:
            return None
        return obj.family.name_ar or obj.family.name_en or None

    class Meta(ProductSerializer.Meta):
        fields = [
            'id', 'sku', 'barcode', 'name_ar', 'name_en', 'display_name',
            # وكيل الفواتير يطبع الماركة في كل سطر تشخيص وفي أسباب استبعاد
            # المنتجات؛ بدونها كان يطبع أقواساً فارغة: «❌ 205/65/16 () — رصيد 0».
            'brand',
            # #22: منتقي المستندات — «هذا موجود» يحمل الأب لا يعرضه خياراً.
            'family_id', 'family_name',
            'category', 'category_name', 'hs_code', 'min_stock_level',
            # T-REORDER: حقلان يجعلان بند الفاتورة يعرف حالة المنتج وبدائله:
            # `stock_status` يصبغ الخيار (نفذ/منخفض)، و`group_key` يجمع موديلات
            # النوع الواحد فيقترح المنتقي بديلاً بدل أن يقف عند «الرصيد 0».
            # نصّان قصيران — والحمولة تُقاس على 1490 منتجاً، فأي حقل ثالث يُبرَّر.
            'stock_status', 'group_key',
            'quantity_on_hand', 'reserved_quantity', 'available_quantity',
            'avg_cost', 'sale_price', 'is_service', 'is_serialized',
            # THA-24: نافذة البطاقة اليدوية تملأ المدة من سياسة المنتج المختار،
            # فلا يعيد المستخدم كتابة ما تعرفه المنظومة.
            'warranty_months', 'supplier_warranty_months',
            'is_for_sale_online',
            'online_price', 'online_description', 'attachments',
            # T-SUPSKU: أرقام المورّدين نصّاً واحداً — منتقي بند الفاتورة يبحث
            # موضعياً في الكتالوج المجلوب دفعةً واحدة، فبحث الخادم لا يبلغه.
            # نصٌّ لا مصفوفةُ كائنات: الحمولة تُقاس على 1490 منتجاً، والمنتقي
            # لا يحتاج إلا أن يطابق.
            'supplier_codes_text',
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


class SupplierProductSerializer(serializers.ModelSerializer):
    """رقم المنتج عند المورّد — بياناتٌ رئيسية محايدة مالياً.

    الفرادة تُحرَس في قاعدة البيانات (شركة، مورّد، رقم)، ويُترجَم خرقُها هنا
    إلى رسالةٍ تسمّي المنتج الذي يحمل الرقم بالفعل — «قيد فريد مخروق» لا يعلّم
    المستخدم شيئاً.
    """

    supplier_display_name = serializers.CharField(
        source='supplier.name', read_only=True, default='',
    )
    product_sku = serializers.CharField(
        source='product.sku', read_only=True, default='',
    )
    product_display_name = serializers.SerializerMethodField()

    class Meta:
        model = SupplierProduct
        fields = [
            'id', 'supplier', 'supplier_display_name',
            'product', 'product_sku', 'product_display_name',
            'supplier_sku', 'supplier_name', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_product_display_name(self, obj):
        from inventory.services import product_display_name
        return product_display_name(obj.product) if obj.product_id else ''

    def validate_supplier_sku(self, value):
        cleaned = str(value or '').strip()
        if not cleaned:
            raise serializers.ValidationError('رقم المنتج عند المورّد مطلوب.')
        return cleaned

    def validate(self, attrs):
        tenant = self.context.get('tenant')
        supplier = attrs.get('supplier', getattr(self.instance, 'supplier', None))
        product = attrs.get('product', getattr(self.instance, 'product', None))
        sku = attrs.get('supplier_sku', getattr(self.instance, 'supplier_sku', None))

        if supplier is not None and supplier.partner_type != 'Supplier':
            raise serializers.ValidationError(
                {'supplier': 'الطرف المحدد ليس مورّداً.'})
        if tenant is not None:
            for field, obj in (('supplier', supplier), ('product', product)):
                if obj is not None and obj.tenant_id != tenant.pk:
                    raise serializers.ValidationError(
                        {field: 'لا يتبع الشركة الحالية.'})

        if supplier is not None and sku:
            clash = SupplierProduct.objects.filter(
                tenant=tenant, supplier=supplier, supplier_sku=sku,
            ).exclude(pk=getattr(self.instance, 'pk', None)).first()
            if clash is not None:
                from inventory.services import product_display_name
                raise serializers.ValidationError({'supplier_sku': (
                    f'الرقم «{sku}» مرتبطٌ عند هذا المورّد بالمنتج '
                    f'«{product_display_name(clash.product)}» — رقمٌ واحد '
                    f'لمنتجين يجعل مطابقة فاتورة المورّد تخميناً.'
                )})
        return attrs
