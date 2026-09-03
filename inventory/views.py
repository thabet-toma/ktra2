import datetime
import logging
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Sum, Q, Value, DecimalField
from django.db.models.functions import Coalesce
from rest_framework import filters, serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import (
    ProductCategory, ProductFamily, Product, UnitOfMeasure, StockMovement,
    SupplierProduct, Warehouse, WarehouseTransfer, Stocktake,
)
from .serializers import (
    CategorySerializer, ProductFamilySerializer, ProductSerializer,
    ProductLookupSerializer, UnitOfMeasureSerializer,
    StockMovementSerializer, WarehouseSerializer,
    WarehouseTransferSerializer, StocktakeSerializer,
    SupplierProductSerializer,
)
from .stock_status import filter_by_stock_status, stock_status_of
from .services import (
    generate_next_sku, record_stock_movement, sync_family_from_product,
    post_warehouse_transfer, unpost_warehouse_transfer, post_stocktake,
    warehouse_stock_summary,
)
from tenants.models import Tenant
from core.access import requires_perm
from core.pagination import EnforcedPageNumberPagination
from core.activity import build_activity_changes, log_activity, log_view
from core.date_ranges import filter_local_date_range
from django.utils.dateparse import parse_date
from core.tenant_utils import get_tenant
from store.cache import InvalidatesStoreCacheMixin
# صيانة الأداء 2026-07: الكلاس انتقل إلى core/pagination.py ليصبح الافتراضي
# العام في REST_FRAMEWORK — يبقى الاستيراد هنا لأي مرجع قائم.
from core.pagination import OptionalPageNumberPagination
from core.plans import enforce_limits
from django.utils import timezone

logger = logging.getLogger(__name__)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all().order_by('name')
    serializer_class = CategorySerializer

    def get_queryset(self):
        # task11 M7: تصنيفات كل الشركات كانت تظهر لأي شركة
        tenant = get_tenant(self.request)
        if not tenant:
            return ProductCategory.objects.none()
        queryset = super().get_queryset().filter(tenant=tenant)
        root_only = self.request.query_params.get('root_only') == 'true'
        if root_only:
            from django.db.models import Q
            return queryset.filter(Q(parent__isnull=True) | Q(parent=0))
        return queryset

    def perform_create(self, serializer):
        tenant = get_tenant(self.request) 
        serializer.save(tenant=tenant)

    def list(self, request, *args, **kwargs):
        """Build the recursive tree from one flat tenant query (no recursive N+1)."""
        queryset = list(self.filter_queryset(self.get_queryset()))
        tenant = get_tenant(request)
        # root_only still needs descendants to render its nested children.
        all_categories = (
            list(ProductCategory.objects.filter(tenant=tenant).order_by('name'))
            if tenant and request.query_params.get('root_only') == 'true'
            else queryset
        )
        child_map = {}
        for category in all_categories:
            if category.parent_id:
                child_map.setdefault(category.parent_id, []).append(category)
        context = self.get_serializer_context()
        context['category_children'] = child_map
        serializer = self.get_serializer(queryset, many=True, context=context)
        return Response(serializer.data)

class UnitOfMeasureViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = UnitOfMeasure.objects.filter(is_active=True)
    serializer_class = UnitOfMeasureSerializer


class ProductFamilyViewSet(viewsets.ReadOnlyModelViewSet):
    """«المنتج» — الأب فوق البراند (#20). **قراءةٌ فقط في هذه المرحلة**، عمداً:

    الأب يُنشأ حصراً مع براندِه الضمنيّ في نقطة الإنشاء الموحّدة
    (`services.create_product_with_family`) — فطرفٌ يُنشئ أباً وحده يصنع «منتجاً
    بلا براندات» وهو حالةٌ لا مكان لها في النموذج. والكتابة عليه مباشرةً تفتح
    **اتجاه كتابةٍ ثانياً**: كل مستهلكٍ قائم لا يزال يقرأ هذه الحقول من صفّ
    البراند، فتعديل الأب وحده يتركهم على قيمةٍ قديمة بصمت. الكاتب واحد — صفّ
    البراند — والأب مرآةٌ تتبعه عبر `services.sync_family_from_product`.

    فتحُ الكتابة هنا قرارُ تذكرةٍ لاحقة تنقل القرّاء أولاً. لا رصيد ولا تكلفة
    هنا إطلاقاً — كل مجموعٍ مشتقٌّ عند القراءة من `Product.family`.
    """
    queryset = ProductFamily.objects.all().select_related('category', 'uom')
    serializer_class = ProductFamilySerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return ProductFamily.objects.none()
        # #24: الأب الذي فقد برانداته كلَّها بالضمّ يبقى صفّاً في الجدول عمداً —
        # سجلّ التراجع يحفظ معرّفه نصّاً ليُعاد الربط به، فحذفه يكسر التراجع.
        # لكنه ليس «منتجاً» لأحد: لا براند تحته ولا رصيد ولا اسمَ يُعرض. فيبقى
        # في القاعدة ويُحجب عن القراءة — الثابت المعلَن في #20 («منتجٌ بلا
        # براندات حالةٌ لا مكان لها») يبقى صحيحاً في كل ما يراه المستخدم.
        return (
            super().get_queryset()
            .filter(tenant=tenant)
            .filter(brands__isnull=False)
            .distinct()
        )

    @action(detail=False, methods=['get'], url_path='check-name')
    def check_name(self, request):
        """#21: «هذا موجود — أضف براند؟» — اقتراحٌ لا منع. يطابق اسماً
        مطبَّعاً (`services.find_by_normalized_name`) لا حرفياً، فيلتقط أشهر
        تنويعات الكتابة العربية (تشكيل/تطويل/مسافات/ألف-همزة) بلا أن يمنع
        تسجيل منتجٍ آخر بالفعل باسمٍ متشابه."""
        from .services import find_by_normalized_name
        tenant = get_tenant(self.request)
        name = (request.query_params.get('name') or '').strip()
        if not tenant or not name:
            return Response({'match': None})
        # مجموعةٌ صريحة لا `get_queryset()`: تلك تحمل `select_related`، و
        # `find_by_normalized_name` تستعمل `only` — وجانغو يرفض تأجيل حقلٍ
        # يعبره `select_related`. والحجب نفسه مُطبَّق: أبٌ بلا براندات لا يُقترَح.
        match = find_by_normalized_name(
            ProductFamily.objects.filter(tenant=tenant, brands__isnull=False).distinct(),
            name,
        )
        if not match:
            return Response({'match': None})
        return Response({
            'match': {'id': match.id, 'name_ar': match.name_ar, 'name_en': match.name_en},
        })


class ProductViewSet(InvalidatesStoreCacheMixin, viewsets.ModelViewSet):
    # task14 M2 (DEF-A5): ترتيب افتراضي حتمي «الأحدث أولاً» + بحث/فرز/ترقيم خادمي
    # #22: `family` هنا أيضاً — `ProductLookupSerializer.get_family_name` يقرأ
    # `obj.family.name_ar`، وبلا هذا الجلب المسبق صار استعلاماً لكل صفّ من 1490.
    queryset = Product.objects.all().select_related('category', 'uom', 'family')
    serializer_class = ProductSerializer
    pagination_class = OptionalPageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    # `supplier_codes__supplier_sku`: البحث يجد المنتج برقم كتالوج مورّده
    # (מק"ט) — وهو الرقم الذي تصل به فاتورة المورّد فعلاً. `SearchFilter`
    # يضيف `.distinct()` تلقائياً لعبوره علاقةً متعدّدة، فلا يتكرّر الصفّ.
    search_fields = [
        'sku', 'barcode', 'name_ar', 'name_en', 'brand', 'category__name',
        'supplier_codes__supplier_sku', 'supplier_codes__supplier_name',
    ]
    ordering_fields = ['id', 'sku', 'name_ar', 'quantity_on_hand', 'avg_cost', 'sale_price',
                       'min_stock_level', 'max_stock_level', 'created_at']
    ordering = ['-id']
    # كروت المجموعة قراءةٌ تُرسَل بـPOST (محدِّدها لا يسع سطر الطلب) — يفحصها
    # TenantRolePermission كأنها GET، فيبقى «مستعرض» قادراً على فتحها.
    read_only_post_actions = ('group_profile', 'group_ledger', 'group_invoices')

    activity_field_labels = {
        'name_ar': 'اسم المنتج',
        'name_en': 'اسم المنتج بالإنجليزية',
        'sku': 'رقم المنتج',
        'barcode': 'الباركود',
        'variant_group': 'المجموعة',
        'brand': 'البراند',
        'category': 'التصنيف',
        'uom': 'وحدة القياس',
        'weight_kg': 'الوزن',
        'volume_cbm': 'الحجم',
        'hs_code': 'رمز HS',
        'min_stock_level': 'حد المخزون الأدنى',
        'max_stock_level': 'حد المخزون الأقصى',
        'allow_negative_stock': 'السماح بالمخزون السالب',
        'is_serialized': 'التتبع التسلسلي',
        'is_service': 'نوع الخدمة',
        'is_for_sale_online': 'البيع عبر الإنترنت',
        'online_price': 'سعر الإنترنت',
        'online_description': 'وصف الإنترنت',
        'sale_price': 'سعر البيع',
        # T-ITEMS M5: حقولٌ صارت تُحفَظ فعلاً — فتُسجَّل تغييراتها كغيرها.
        'uom2': 'الوحدة الثانية',
        'uom2_factor': 'معامل الوحدة الثانية',
        'uom3': 'الوحدة الثالثة',
        'uom3_factor': 'معامل الوحدة الثالثة',
        'description': 'وصف المنتج',
        'storage_location': 'موقع التخزين',
        'sale_account_override': 'حساب المبيعات',
        'sale_return_account_override': 'حساب مرتجع المبيعات',
        'purchase_account_override': 'حساب المشتريات',
        'purchase_return_account_override': 'حساب مرتجع المشتريات',
        'supplier_account_override': 'حساب المورد',
        'ending_inventory_account_override': 'حساب بضاعة آخر المدة',
    }

    def _get_tenant(self):
        return get_tenant(self.request)

    def _is_lookup(self):
        """عقد المنتقي (`view=lookup`) — دالّةٌ واحدة يقرأها كل فرعٍ بدل تكرار
        شرط `request.query_params.get('view') == 'lookup'` ثلاث مرات. ISSUE #88:
        `ProductLookupViewSet` (أسفله) تُعيدها `True` دائماً بصرف النظر عن
        المُرسَل — نفس المنطق حرفياً بلا نسخة ثانية منه."""
        return self.request.query_params.get('view') == 'lookup'

    def get_serializer_class(self):
        if self.action == 'list' and self._is_lookup():
            return ProductLookupSerializer
        return ProductSerializer

    def _reserved_map(self):
        """خريطة المحجوز للشركة — تُحسب مرّةً لكل طلب.

        يقرؤها الفلتر (`get_queryset`) والسيريالايزر معاً؛ بلا هذا الحفظ صارت
        استعلامين لنفس السؤال في الطلب الواحد.
        """
        if not hasattr(self, '_reserved_map_cache'):
            tenant = self._get_tenant()
            if tenant:
                from sales.services import reserved_quantity_map
                self._reserved_map_cache = reserved_quantity_map(tenant.TenantID)
            else:
                self._reserved_map_cache = {}
        return self._reserved_map_cache

    def _family_available_map(self):
        """#25: مجموع أرصدة إخوة كل أبٍ في الشركة — استعلامٌ واحدٌ لكل طلب.

        يقرؤه السيريالايزر ليحسب حالة المخزون على مستوى الأب لا البراند وحده
        (`inventory/stock_status.py` — `family_available_map`). يُبنى مرّةً
        ويُشارَك بين كل صفوف الصفحة — لا استعلامَ لكل صفّ.
        """
        if not hasattr(self, '_family_available_map_cache'):
            tenant = self._get_tenant()
            if tenant:
                from .stock_status import family_available_map
                self._family_available_map_cache = family_available_map(
                    tenant.TenantID, reserved_map=self._reserved_map(),
                )
            else:
                self._family_available_map_cache = {}
        return self._family_available_map_cache

    def _family_status_and_thresholds(self):
        """#35: حالة كل أبٍ وحدَّاه الحاكمان معاً — استدعاءٌ واحدٌ يُغذّي
        كِلا الخريطتين (`_family_statuses`/`_family_thresholds`)، فاستعلام
        `ProductFamily` الإضافيّ (فوق `_family_available_map`) لا يتضاعف بين
        الشارة والحدّ المعروض على الصفّ.
        """
        if not hasattr(self, '_family_status_and_thresholds_cache'):
            tenant = self._get_tenant()
            if tenant:
                from .stock_status import family_status_and_thresholds
                self._family_status_and_thresholds_cache = family_status_and_thresholds(
                    tenant.TenantID, family_totals=self._family_available_map(),
                    suggested_min_map=self._suggested_min_family_map(),
                )
            else:
                self._family_status_and_thresholds_cache = ({}, {})
        return self._family_status_and_thresholds_cache

    def _family_statuses(self):
        """#28: حالة كل أبٍ ظهر في `_family_available_map` — استعلامٌ إضافيٌّ
        واحد فقط (`ProductFamily`)، إذ الأرصدة نفسها محسوبةٌ سلفاً.

        يقرأه `get_queryset` ليُفلتر `?stock_status=` بحالة **الأب** لا حالة
        البراند وحده — نفس القاعدة التي تعرضها الشارة (`stock_status_of`
        عبر السيريالايزر). `view=lookup` لا يستدعيها إطلاقاً؛ يبقى فلتره على
        حالة البراند وحده عمداً، كما `get_serializer_context`.
        """
        return self._family_status_and_thresholds()[0]

    def _family_thresholds(self):
        """#35: حدّا (أدنى، أقصى) كل أبٍ ظهر في `_family_available_map` — من
        نفس استدعاء `_family_statuses`، بلا استعلامٍ إضافي.

        يقرأه السيريالايزر ليعرض على صفّ المنتج **نفس** الحدّ الذي حُوكِمت
        عليه شارته، لا حدّ البراند المرجعي (أصغر معرّف) الذي قد يختلف بعد ضمٍّ
        لم يُسوِّ الحدّين.
        """
        return self._family_status_and_thresholds()[1]

    def _suggested_min_maps(self):
        """#44: الحدّ الأدنى المحسوب لكل منتج ولكل عائلة — استعلاماتٌ للشركة
        كلّها لكل طلب، بنفس نمط `_reserved_map`/`_family_available_map`. من
        `core.replenishment.suggested_min_maps` وحدها — لا حسابٌ ثانٍ للصيغة
        ولا نسخةٌ مخزَّنة. `view=lookup` لا يستدعيها (عقده بلا حدودٍ أصلاً).
        """
        if not hasattr(self, '_suggested_min_maps_cache'):
            tenant = self._get_tenant()
            if tenant:
                from core.replenishment import suggested_min_maps
                self._suggested_min_maps_cache = suggested_min_maps(tenant.TenantID)
            else:
                self._suggested_min_maps_cache = ({}, {})
        return self._suggested_min_maps_cache

    def _suggested_min_product_map(self):
        return self._suggested_min_maps()[0]

    def _suggested_min_family_map(self):
        return self._suggested_min_maps()[1]

    def _family_brand_counts(self):
        """#23: عدد براندات كل أبٍ في الشركة — استعلامٌ واحدٌ لكل طلب.

        يقرأه السيريالايزر ليقرّر `has_group` (عنصر «كشف البراندات» في الجدول)
        بلا استعلامٍ لكل صفّ — نفس نمط `_family_available_map`.
        """
        if not hasattr(self, '_family_brand_counts_cache'):
            tenant = self._get_tenant()
            if tenant:
                from .services import family_brand_counts
                self._family_brand_counts_cache = family_brand_counts(tenant.TenantID)
            else:
                self._family_brand_counts_cache = {}
        return self._family_brand_counts_cache

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self._get_tenant():
            context['reserved_quantity_map'] = self._reserved_map()
            # منتقي المستندات (`view=lookup`) يبقى على حالة **البراند** وحده
            # عمداً — لا سهواً: البند يبيع براندًا بعينه، فبراندٌ رصيده صفرٌ
            # داخل منتجٍ وفير «نفذ» **حقيقةً** لمن يريد بيعه. الحالة على مستوى
            # الأب معناها «هل عندي من هذا المنتج شيء»، وهو سؤال شاشة الأصناف
            # لا سؤال سطر الفاتورة. (والعقد يعرض `stock_status` فعلاً — فهذا
            # اختلاف دلالة لا حقلٌ محذوف.)
            if not self._is_lookup():
                context['family_available_map'] = self._family_available_map()
                context['family_brand_counts'] = self._family_brand_counts()
                context['family_thresholds'] = self._family_thresholds()
                # #44: الشارة تُحاكَم بالحدّ المحسوب حين لا حدّ يدوياً — نفس
                # الرقم الذي يعرضه تقرير التجديد، لا صفراً صامتاً. `view=lookup`
                # يبقى بلا حدودٍ إطلاقاً (عقده الضيّق لا يتغيّر).
                context['suggested_min_map'] = self._suggested_min_product_map()
                context['suggested_min_family_map'] = self._suggested_min_family_map()
        return context

    def get_queryset(self):
        # task11 M7: المنتجات كانت بلا فلترة tenant في القراءة —
        # منتجات كل الشركات تظهر للشركة الجديدة. .none() عند غياب الشركة.
        tenant = self._get_tenant()
        if not tenant:
            return Product.objects.none()
        qs = super().get_queryset().filter(tenant=tenant)
        params = self.request.query_params

        # استبعاد المنتجات الخاصة بالمتجر فقط من الكتالوج المخزني ومحددات الفواتير
        store_only_param = params.get('is_store_only')
        if store_only_param == 'true':
            qs = qs.filter(is_store_only=True)
        elif store_only_param != 'all':
            qs = qs.filter(is_store_only=False)

        category_id = params.get('category')
        if category_id:
            # M0: التصنيف محدِّدٌ يعني شجرته — نفس قاعدة الكرت المجمّع، من نسخةٍ
            # واحدة في `services`. كان exact-id هنا وشجرةً هناك، فتصنيفُ أبٍ
            # يعرض «لا منتجات» بينما كرته المجمّع يعدّ المئات.
            from .services import category_descendant_ids
            try:
                wanted = category_descendant_ids(
                    tenant_id=tenant.pk, category_id=int(category_id)
                )
            except (TypeError, ValueError):
                wanted = []
            qs = qs.filter(category_id__in=wanted)
        # مدى محلّي بلا `__date`: CONVERT_TZ يُعيد NULL على خادمٍ بلا جداول
        # مناطق زمنية، فيبتلع الفلتر كل الصفوف بصمت (core/date_ranges.py).
        qs = filter_local_date_range(
            qs, 'created_at',
            date_from=parse_date(params.get('created_from') or ''),
            date_to=parse_date(params.get('created_to') or ''),
        )
        # T-REORDER: فلتر حالة المخزون — من `inventory/stock_status.py` وحدها.
        # كان مكتوباً هنا نسخةً ثانية بجانب نسخة السيريالايزر، وتباعدتا.
        # #28: يفلتر بحالة **الأب** لا البراند وحده — نفس ما تعرضه الشارة —
        # إلا في `view=lookup` (البند يبيع براندًا بعينه، عمداً كما في
        # `get_serializer_context`).
        stock_status = params.get('stock_status')
        if stock_status:
            is_lookup = self._is_lookup()
            family_statuses = self._family_statuses() if not is_lookup else None
            # #44: المقترَح بلا أبٍ يُحقَن هو الآخر — `view=lookup` يبقى بلا
            # حدودٍ إطلاقاً (`None` يُبقي `filter_by_stock_status` على
            # `min_stock_level` الخام حرفياً، نفس ما كان قبل هذا التاريخ).
            suggested_min_map = self._suggested_min_product_map() if not is_lookup else None
            qs = filter_by_stock_status(
                qs, stock_status, reserved_map=self._reserved_map(),
                family_statuses=family_statuses, suggested_min_map=suggested_min_map,
            )
        # ST-3: شاشة «متجري» تعرض المنشور وحده، وتحتاج عدده قبل فتح المتجر أول
        # مرة. بلا هذا الفلتر كان عليها تحميل الكتالوج كاملاً وتصفيته في
        # المتصفح — على 1490 منتجاً ذلك ميغابايت لعرض صفّين.
        published = params.get('is_for_sale_online')
        if published in ('true', 'false'):
            qs = qs.filter(is_for_sale_online=(published == 'true'))
        # محددات المنتجات في الفواتير/الصفقات لا تعرض التحليلات؛ تجنّب ثلاث
        # aggregations على جدول الحركات الكبير عند طلب view=lookup. عقد القائمة
        # الكامل يبقى كما هو افتراضياً لجدول إدارة المنتجات.
        if self._is_lookup():
            # T-SUPSKU: أرقام الموردين تدخل حمولة المنتقي؛ الجلب المسبق يجعلها
            # استعلاماً واحداً للصفحة كلّها لا واحداً لكل منتج.
            return qs.prefetch_related('supplier_codes')

        # T-ITEMS M5: الشرائح جزءٌ من العقد الكامل — بلا جلبٍ مسبق صارت
        # استعلاماً لكل منتج في القائمة.
        qs = qs.prefetch_related('price_tiers')

        # W8: تجميعات محسوبة من StockMovement (المصدر الوحيد) — منقّطة، لا N+1.
        # الوارد التراكمي (المشتريات) = مجموع حركات IN. متوسط المبيعات الشهري = صافي
        # (OUT − RETURN_IN) خلال آخر 90 يوماً ÷ 3 (يُحسب في السيريالايزر من المجاميع).
        cutoff_90 = timezone.localdate() - datetime.timedelta(days=90)
        _zero = Value(Decimal('0'), output_field=DecimalField(max_digits=18, decimal_places=4))
        qs = qs.annotate(
            purchased_qty=Coalesce(
                Sum('stock_movements__quantity',
                    filter=Q(stock_movements__movement_type='IN')), _zero),
            sold_qty_90d=Coalesce(
                Sum('stock_movements__quantity',
                    filter=Q(stock_movements__movement_type='OUT',
                             stock_movements__movement_date__gte=cutoff_90)), _zero),
            returned_qty_90d=Coalesce(
                Sum('stock_movements__quantity',
                    filter=Q(stock_movements__movement_type='RETURN_IN',
                             stock_movements__movement_date__gte=cutoff_90)), _zero),
        )
        return qs

    # مرشِّحاتٌ تختار **أيّ البراندات** لا **أيّ الحقائق عنها** (تفريق #26):
    # مع أيٍّ منها لا يُكمَّل شيء — الصفّ حينها مجموعٌ جزئيٌّ يدّعي أنه المنتج.
    #
    # و`stock_status` **خرج** من هذه القائمة بعد #28: صار حكماً على **الأب**
    # (مجموع البراندات مقابل حدّ الأب) لا على البراند، فيُعيد الفلتر كل براندات
    # المنتج المطابق لا بعضها — فالإكمال هنا لم يعد يُدخل غريباً، بل يجمع ما
    # فرّقه التقسيم إلى صفحات. وقبل #28 كان استبعاده صحيحاً: الفلتر كان يختار
    # البراندات الصفرية وحدها، فإكمال عائلتها يُدخل إخوةً متوفّرين.
    BRAND_SELECTING_PARAMS = ('search',)

    def _complete_families(self, products, request):
        """يُكمل عائلات الصفحة بعد التقسيم — شرط استقامة صفّ المنتج.

        التجميع يقع عند الرسم (#23) على الصفوف الواصلة وحدها، والشاشة الجدولية
        تُرقَّم عند 50. فمنتجٌ تتوزّع براندَاته على صفحتين كان يُرسَم صفَّ
        منتجٍ **بمجموعٍ جزئي معروضٍ على أنه مجموع المنتج** — وقد يظهر المقاس
        نفسه في صفحتين بمجموعين مختلفين. وليست حالة حدٍّ: الترتيب الافتراضي
        `-id` ومعرّفات الإخوة متباعدةٌ لأنها فُتحت على مدى شهور.

        الإصلاح هنا لا ينقل التجميع بل يضمن اكتمال مدخلاته: بعد التقسيم يُجلب
        **كل** إخوة عائلات الصفحة في **استعلامٍ واحد ثابت** لا واحدٍ لكل صفّ.
        فيستحيل الصفّ الناقص بنيوياً لا احترازاً — وهي قاعدة #26 نفسها: أرقام
        صفّ المنتج مجموع كل برانداته أو لا يظهر صفّ منتجٍ أصلاً.

        **اختياري** (`complete_families=1`): شاشة الأصناف وحدها ترسله، فعقد
        `?view=lookup` ومنتقي المستندات لا يتغيّران. ولا رقم يُخزَّن — هذا
        جلبُ صفوفٍ لا حسابُ مجموع.
        """
        if request.query_params.get('complete_families') not in ('1', 'true'):
            return products
        if any(request.query_params.get(k) for k in self.BRAND_SELECTING_PARAMS):
            return products
        family_ids = {p.family_id for p in products if p.family_id}
        if not family_ids:
            return products
        present = {p.id for p in products}
        missing = [
            p for p in self.get_queryset().filter(family_id__in=family_ids)
            if p.id not in present
        ]
        return products + missing

    def list(self, request, *args, **kwargs):
        """Serialize attachments in one tenant-scoped query instead of one per row."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        products = list(page if page is not None else queryset)
        products = self._complete_families(products, request)

        attachment_map = {product.id: [] for product in products}
        if products:
            try:
                from core.models import SystemAttachment
                rows = SystemAttachment.objects.filter(
                    tenant=self._get_tenant(),
                    related_table='products',
                    related_id__in=attachment_map,
                )
                for attachment in rows:
                    attachment_map.setdefault(attachment.related_id, []).append({
                        'id': attachment.id,
                        'file_path': attachment.file_path,
                        'file_type': attachment.file_type,
                    })
            except Exception:
                # Legacy deployments may not have the unmanaged attachment table.
                pass

        context = self.get_serializer_context()
        context['product_attachments'] = attachment_map
        serializer = self.get_serializer(products, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def _handle_attachments(self, product, data, tenant):
        from core.models import SystemAttachment

        def _save(url, file_type):
            if not (url and isinstance(url, str) and url.startswith('http')):
                return
            if not SystemAttachment.objects.filter(
                tenant=tenant,
                related_table='products',
                related_id=product.id,
                file_path=url
            ).exists():
                SystemAttachment.objects.create(
                    tenant=tenant,
                    related_table='products',
                    related_id=product.id,
                    file_type=file_type,
                    file_path=url
                )

        _save(data.get('image_url') or data.get('image_path'), 'Product Image')

        # داتا شيت — يقبل رابطاً مفرداً (datasheet_url) أو قائمة روابط (datasheet_urls)
        datasheets = data.get('datasheet_urls') or data.get('datasheet_url')
        if isinstance(datasheets, str):
            datasheets = [datasheets]
        if isinstance(datasheets, (list, tuple)):
            for url in datasheets:
                _save(url, 'Datasheet')

    def _validate_category_tenant(self, serializer, tenant):
        # DEF-A1: التصنيف FK يجب أن يكون من نفس الشركة
        category = serializer.validated_data.get('category')
        if category and category.tenant_id != tenant.pk:
            raise serializers.ValidationError({'category': 'التصنيف غير موجود لهذه الشركة.'})

    def create(self, request, *args, **kwargs):
        tenant = self._get_tenant()
        # T-PLANLIMITS: عدد المنتجات المسموح به من خطة الشركة.
        enforce_limits(tenant, 'inventory.products')
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._validate_category_tenant(serializer, tenant)

        # task14 M2 (DEF-A2): SKU يولَّد خادمياً عند الغياب — مع إعادة محاولة عند السباق
        explicit_sku = (serializer.validated_data.get('sku') or '').strip()
        if explicit_sku:
            if Product.objects.filter(tenant=tenant, sku=explicit_sku).exists():
                raise serializers.ValidationError({'sku': 'رقم المنتج مستخدم مسبقاً لهذه الشركة.'})
            product = serializer.save(tenant=tenant, sku=explicit_sku)
        else:
            product = None
            for _ in range(5):
                try:
                    with transaction.atomic():
                        product = serializer.save(tenant=tenant, sku=generate_next_sku(tenant))
                    break
                except IntegrityError:
                    continue
            if product is None:
                raise serializers.ValidationError({'sku': 'تعذّر توليد رقم منتج — أعد المحاولة.'})

        self._handle_attachments(product, request.data, tenant)
        product_label = product.name_ar or product.name_en or product.sku
        log_activity(
            action='create',
            entity_type='product',
            entity_id=product.id,
            entity_label=product_label,
            description=f'أضاف المنتج «{product_label}»',
            request=request,
        )
        return Response(self.get_serializer(product).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        # #20: حذف آخر براندٍ تحت منتجٍ يترك أباً بلا أبناء — «منتج بلا
        # براندات» حالةٌ لا مكان لها في النموذج، ولا شيء يشير إليها فتبقى
        # صفّاً يتيماً يظهر في كل قائمة منتجات. يُحذف معه.
        family = instance.family
        super().perform_destroy(instance)
        if family is not None and not family.brands.exists():
            family.delete()

    def update(self, request, *args, **kwargs):
        tenant = self._get_tenant()
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        self._validate_category_tenant(serializer, tenant)
        tracked_labels = {
            field: label for field, label in self.activity_field_labels.items()
            if field in serializer.validated_data
        }
        before = {field: getattr(instance, field) for field in tracked_labels}
        # task14 M2: SKU فارغ في التعديل = «أبقِ الرقم الحالي» — لا تمسحه
        new_sku = (serializer.validated_data.get('sku') or '').strip()
        if 'sku' in serializer.validated_data:
            if not new_sku:
                serializer.validated_data.pop('sku')
            elif new_sku != instance.sku and Product.objects.filter(
                tenant=tenant, sku=new_sku
            ).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError({'sku': 'رقم المنتج مستخدم مسبقاً لهذه الشركة.'})
        product = serializer.save()
        # #20: اتجاه الكتابة أثناء الانتقال واحد — الكاتب هو صفّ البراند، والأب
        # مرآةٌ تتبعه. بدونه يقرأ `resolve_family_field` أباً متجمّداً على قيمة
        # الإنشاء فيعرض الكرت تصنيفاً قديماً بعد تعديله فعلاً.
        family_changed = sync_family_from_product(product)
        # #35: `self.get_serializer(...)` أعلاه بنى `_family_status_and_thresholds_cache`
        # على حالة الأب **قبل** المزامنة — فردّ الاستجابة (السيريالايزر الثاني
        # أسفل) كان يعرض حدّاً/حالةً بائتين لو غيّر هذا الحفظ حقلاً أبوياً
        # (`min_stock_level` مثلاً). يُبطَل الاستخراج المخبوء هنا فقط، وحين
        # تغيّر شيءٌ فعلاً — لا استعلامَ إضافي على القائمة (`GET`) التي لا تكتب.
        if family_changed and hasattr(self, '_family_status_and_thresholds_cache'):
            del self._family_status_and_thresholds_cache
        self._handle_attachments(product, request.data, tenant)
        changes = build_activity_changes(
            before=before,
            after={field: getattr(product, field) for field in tracked_labels},
            labels=tracked_labels,
        )
        if changes:
            product_label = product.name_ar or product.name_en or product.sku
            if len(changes) == 1 and changes[0]['field'] == 'name_ar':
                change = changes[0]
                description = f'غيّر اسم المنتج من «{change["old"]}» إلى «{change["new"]}»'
            elif len(changes) == 1 and changes[0]['field'] == 'sale_price':
                change = changes[0]
                description = (
                    f'عدّل سعر البيع للمنتج «{product_label}» '
                    f'من {change["old"]} إلى {change["new"]}'
                )
            else:
                details = '؛ '.join(
                    f'{change["label"]} من «{change["old"]}» إلى «{change["new"]}»'
                    for change in changes
                )
                description = f'عدّل المنتج «{product_label}»: {details}'
            log_activity(
                action='update',
                entity_type='product',
                entity_id=product.id,
                entity_label=product_label,
                description=description,
                metadata={'changes': changes},
                request=request,
            )
        return Response(self.get_serializer(product).data)

    @action(detail=True, methods=['delete'], url_path='datasheets/(?P<att_id>[0-9]+)')
    def remove_datasheet(self, request, pk=None, att_id=None):
        """حذف مرفق داتا شيت محفوظ من SQL + محاولة حذف الأصل من Cloudinary (أفضل-جهد).
        مقيّد بشركة المستخدم ومنتجه ونوع Datasheet حصراً (get_object يفلتر tenant)."""
        from core.models import SystemAttachment
        from core.media_views import destroy_cloudinary_asset
        product = self.get_object()  # tenant-scoped
        att = SystemAttachment.objects.filter(
            tenant_id=product.tenant_id,
            related_table='products',
            related_id=product.id,
            id=att_id,
            file_type='Datasheet',
        ).first()
        if not att:
            return Response({'detail': 'المرفق غير موجود.'}, status=status.HTTP_404_NOT_FOUND)
        destroy_cloudinary_asset(att.file_path)
        att.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'], url_path='stock-movements')
    def stock_movements(self, request, pk=None):
        product = self.get_object()
        qs = StockMovement.objects.filter(product=product).select_related('partner')
        return Response(StockMovementSerializer(qs[:50], many=True).data)

    # ── FEAT-3: Product profile ──────────────────────────────────
    @action(detail=True, methods=['get'], url_path='profile')
    def profile(self, request, pk=None):
        from inventory.services import product_profile
        product = self.get_object()
        return Response(product_profile(tenant_id=product.tenant_id, product_id=product.id))

    @action(detail=True, methods=['get'], url_path='stock-ledger')
    def stock_ledger(self, request, pk=None):
        from inventory.services import product_stock_ledger
        product = self.get_object()
        try:
            limit = min(int(request.query_params.get('limit', 50)), 200)
        except (TypeError, ValueError):
            limit = 50
        try:
            offset = max(int(request.query_params.get('offset', 0)), 0)
        except (TypeError, ValueError):
            offset = 0
        return Response(product_stock_ledger(
            tenant_id=product.tenant_id, product_id=product.id, limit=limit, offset=offset))

    @action(detail=True, methods=['get'], url_path='invoices')
    def invoices(self, request, pk=None):
        from inventory.services import product_linked_invoices
        product = self.get_object()
        return Response(product_linked_invoices(
            tenant_id=product.tenant_id, product_id=product.id))

    @action(detail=True, methods=['get'], url_path='cost-breakdown')
    def cost_breakdown(self, request, pk=None):
        from inventory.services import product_cost_breakdown
        product = self.get_object()
        return Response(product_cost_breakdown(
            tenant_id=product.tenant_id, product_id=product.id))

    # ── تجميع البراندات: الكرت المجمّع (مجموع كل البراندات لنفس المقاس/الأساس) ──
    # النقر على عقدة التصنيف في الشجرة/الجرد يفتح هذه الكروت. أعضاء المجموعة
    # يُحدَّدون بأحد ثلاثة أشكال:
    #   • `category` — التصنيف وأحفاده، والخادم يشتقّ المعرّفات (الشكل المفضَّل)
    #   • `family` — كل براندات منتجٍ (أب) بعينه (#23: كرت المنتج المفرد)
    #   • `ids` — تعدادٌ صريح (مجموعات group_key، وأسطر جردٍ بعينها)
    # وكلاهما يُقرأ من **جسم** الطلب (POST). كان التعداد يسافر في سطر الطلب
    # (`?ids=1,2,3…`): تصنيفُ جذرٍ فيه ~1500 منتج ⇒ عنوانٌ ~7.5KB ⇒ nginx يردّ
    # 414/400 قبل أن يصل الطلب إلى Django (والتطوير يمرّ لأن runserver أسخى).
    # GET مع `?ids=`/`?category=` يبقى مقروءاً لتوافق الروابط القديمة.
    def _group_source(self, request):
        return request.data if request.method == 'POST' else request.query_params

    def _group_ids(self, request, tenant=None):
        source = self._group_source(request)
        raw = source.get('ids') or ''
        parts = raw if isinstance(raw, (list, tuple)) else str(raw).split(',')
        ids = [int(str(p).strip()) for p in parts if str(p).strip().isdigit()]
        if ids:
            return ids
        # #23: كرت المنتج المفرد يفتح الكرت المجمّع لإخوته بمعرّف الأب مباشرةً
        # — لا حاجة لتعداد براندات المنتج في الطلب (الخادم يشتقّها).
        family = str(source.get('family') or '').strip()
        if family.isdigit() and tenant is not None:
            return list(
                Product.objects.filter(tenant=tenant, family_id=int(family))
                .values_list('id', flat=True)
            )
        category = str(source.get('category') or '').strip()
        if category.isdigit() and tenant is not None:
            from inventory.services import category_descendant_product_ids
            return category_descendant_product_ids(
                tenant_id=tenant.pk, category_id=int(category))
        return []

    def _group_int(self, request, key, default, *, minimum=None, maximum=None):
        try:
            value = int(self._group_source(request).get(key, default))
        except (TypeError, ValueError):
            return default
        if minimum is not None:
            value = max(value, minimum)
        if maximum is not None:
            value = min(value, maximum)
        return value

    def _distinct_values(self, tenant, field):
        vals = (
            Product.objects.filter(tenant=tenant)
            .exclude(**{field: ''}).exclude(**{f'{field}__isnull': True})
            .values_list(field, flat=True)
        )
        return sorted({(v or '').strip() for v in vals if (v or '').strip()})

    @action(detail=False, methods=['get'], url_path='brands')
    def brands(self, request):
        """قائمة البراندات المستخدمة (مميّزة) للشركة — لمنتقي البراند (اختر/أضف)."""
        tenant = self._get_tenant()
        if not tenant:
            return Response([])
        return Response(self._distinct_values(tenant, 'brand'))

    @action(detail=False, methods=['get'], url_path='groups')
    def groups(self, request):
        """قائمة المجموعات (المنتجات الفرعية) المستخدمة — لمنتقي المجموعة (اختر/أضف)."""
        tenant = self._get_tenant()
        if not tenant:
            return Response([])
        return Response(self._distinct_values(tenant, 'variant_group'))

    @action(detail=False, methods=['get'], url_path='names')
    def names(self, request):
        """أسماء المنتجات المميّزة — لمنتقي «اسم المنتج» (اختر موجوداً لإضافة براند
        آخر، أو اكتب اسماً جديداً فيُنشأ تصنيف فرعي باسمه)."""
        tenant = self._get_tenant()
        if not tenant:
            return Response([])
        return Response(self._distinct_values(tenant, 'name_ar'))

    @action(detail=False, methods=['post'], url_path='add-brand')
    def add_brand(self, request):
        """#21: يضيف براندًا إلى منتجٍ قائم من داخل شاشة المنتج. أوّل براندٍ
        صريح يُسمّي البراند الضمنيّ الوحيد بدل أن يُنشئ صفّاً جديداً — انظر
        `services.add_brand_to_family`. الكتابة تبقى على جانب البراند/المنتج
        عمداً — لا على `ProductFamilyViewSet` القرائي حصراً."""
        from .services import add_brand_to_family
        tenant = self._get_tenant()
        if not tenant:
            return Response({'detail': 'الشركة غير محددة'}, status=status.HTTP_400_BAD_REQUEST)
        family_id = request.data.get('family_id')
        brand_name = (request.data.get('brand') or '').strip()
        if not family_id:
            raise serializers.ValidationError({'family_id': 'مطلوب.'})
        if not brand_name:
            raise serializers.ValidationError({'brand': 'اسم البراند مطلوب.'})
        family = ProductFamily.objects.filter(tenant=tenant, id=family_id).first()
        if not family:
            return Response({'detail': 'المنتج غير موجود.'}, status=status.HTTP_404_NOT_FOUND)
        sku = (request.data.get('sku') or '').strip() or None
        if sku and Product.objects.filter(tenant=tenant, sku=sku).exists():
            raise serializers.ValidationError({'sku': 'رقم المنتج مستخدم مسبقاً لهذه الشركة.'})
        # T-PLANLIMITS: البراند الثاني فصاعداً **صفُّ منتجٍ جديد** يحتسبه الحدّ —
        # فبلا هذا الحارس صار هذا الباب طريقاً للالتفاف على حدّ الخطة. وتسميةُ
        # البراند الضمنيّ لا تُنشئ صفّاً فلا تُحاسَب: الشرط هو وجود براندٍ مُسمّىً
        # سلفاً تحت الأب، وهو نفس شرط الإنشاء في `add_brand_to_family`.
        existing = list(Product.objects.filter(family=family).values_list('brand', flat=True))
        will_create = not (len(existing) == 1 and not (existing[0] or '').strip())
        if will_create:
            enforce_limits(tenant, 'inventory.products')
        try:
            product, created = add_brand_to_family(
                family=family, brand_name=brand_name, tenant=tenant, sku=sku,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {'brand': exc.messages if hasattr(exc, 'messages') else [str(exc)]}
            )
        product_label = product.name_ar or product.name_en or product.sku
        log_activity(
            action='create' if created else 'update',
            entity_type='product',
            entity_id=product.id,
            entity_label=product_label,
            description=(
                f'أضاف براند «{brand_name}» جديداً تحت «{product_label}»' if created
                else f'سمّى البراند الضمنيّ «{brand_name}» تحت «{product_label}»'
            ),
            request=request,
        )
        return Response(
            {
                'id': product.id, 'sku': product.sku, 'brand': product.brand,
                'family_id': product.family_id,
                'name_ar': product.name_ar, 'name_en': product.name_en,
                'created': created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], url_path='merge')
    @requires_perm('inventory.item.manage')
    def merge(self, request):
        """#24: ضمٌّ جماعي — منتجاتٌ قائمة (براندات منتجٍ واحد فعلياً) تحت أبٍ
        واحد. **بلا حركة مخزون ولا قيد محاسبي** — انظر `services.merge_products`.

        المحدِّد في **جسم** الطلب لا في عنوانه (نفس درس كرت المجموعة): `product_ids`
        قد تفوق 1500 معرّفاً، وتعدادها في سطر الطلب يتجاوز حدّ nginx.
        """
        from .services import merge_products
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'الشركة غير محددة'}, status=status.HTTP_400_BAD_REQUEST)
        target_product_id = request.data.get('target_product_id')
        if not target_product_id:
            raise serializers.ValidationError({'target_product_id': 'مطلوب.'})
        raw_ids = request.data.get('product_ids') or []
        if not isinstance(raw_ids, list):
            return Response(
                {'error': 'product_ids يجب أن تكون قائمة معرّفات منتجات'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            target_product_id = int(target_product_id)
            product_ids = [int(pid) for pid in raw_ids]
        except (TypeError, ValueError):
            return Response({'error': 'معرّف منتج غير صالح'}, status=status.HTTP_400_BAD_REQUEST)
        brands = request.data.get('brands') or {}
        if not isinstance(brands, dict):
            return Response({'error': 'brands يجب أن يكون تعييناً'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            merge_obj, moved = merge_products(
                tenant=tenant, target_product_id=target_product_id,
                product_ids=product_ids, brands=brands, user=request.user,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {'detail': exc.messages if hasattr(exc, 'messages') else [str(exc)]}
            )

        target_label = merge_obj.target_family.name_ar or merge_obj.target_family.name_en
        log_activity(
            action='update',
            entity_type='product_family',
            entity_id=merge_obj.target_family_id,
            entity_label=target_label,
            description=f'ضمّ {len(moved)} منتجاً تحت «{target_label}»',
            metadata={'merge_id': merge_obj.id, 'product_ids': [p.id for p in moved][:500]},
            request=request,
        )
        return Response({
            'merge_id': merge_obj.id,
            'target_family_id': merge_obj.target_family_id,
            'target_product_id': target_product_id,
            'merged_product_ids': [p.id for p in moved],
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='merge-undo')
    @requires_perm('inventory.item.manage')
    def merge_undo(self, request):
        """#24: يتراجع عن ضمٍّ بالكامل — كل براند يعود لأبيه واسمه وبراندِه
        كما كانوا. انظر `services.undo_product_merge`."""
        from .services import undo_product_merge
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'الشركة غير محددة'}, status=status.HTTP_400_BAD_REQUEST)
        merge_id = request.data.get('merge_id')
        if not merge_id:
            raise serializers.ValidationError({'merge_id': 'مطلوب.'})
        try:
            merge_obj, restored = undo_product_merge(tenant=tenant, merge_id=int(merge_id))
        except (TypeError, ValueError):
            return Response({'error': 'merge_id غير صالح'}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {'detail': exc.messages if hasattr(exc, 'messages') else [str(exc)]}
            )
        log_activity(
            action='update',
            entity_type='product_family',
            entity_id=merge_obj.target_family_id,
            description=f'تراجع عن ضمّ {len(restored)} منتجاً',
            metadata={'merge_id': merge_obj.id},
            request=request,
        )
        return Response({
            'merge_id': merge_obj.id,
            'restored_product_ids': [p.id for p in restored],
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get', 'post'], url_path='group-profile')
    def group_profile(self, request):
        from inventory.services import product_group_profile
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'الشركة غير محددة'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(product_group_profile(
            tenant_id=tenant.pk, product_ids=self._group_ids(request, tenant)))

    @action(detail=False, methods=['get', 'post'], url_path='group-ledger')
    def group_ledger(self, request):
        from inventory.services import product_stock_ledger
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'الشركة غير محددة'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(product_stock_ledger(
            tenant_id=tenant.pk, product_ids=self._group_ids(request, tenant),
            limit=self._group_int(request, 'limit', 50, minimum=1, maximum=200),
            offset=self._group_int(request, 'offset', 0, minimum=0)))

    @action(detail=False, methods=['get', 'post'], url_path='group-invoices')
    def group_invoices(self, request):
        from inventory.services import product_linked_invoices
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'الشركة غير محددة'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(product_linked_invoices(
            tenant_id=tenant.pk, product_ids=self._group_ids(request, tenant)))

    # ── تجديد المخزون ──────────────────────────────────────────────────
    @action(detail=False, methods=['post'], url_path='apply-replenishment')
    @requires_perm('inventory.item.manage')
    def apply_replenishment(self, request):
        """يثبّت الحدّين المقترَحين على منتجاتٍ محدَّدة — `{"product_ids": [...]}`.

        كتابةٌ حقيقية لا قراءة: **ليست** في `read_only_post_actions`، وتشترط
        صلاحية إدارة المنتجات لا عرضها.

        والمحدِّد في **جسم** الطلب لا في عنوانه: تعداد ألف منتجٍ في سطر الطلب
        تجاوز في الإنتاج `large_client_header_buffers` فردّ nginx 414 بينما مرّ
        التطوير — نفس درس كرت المجموعة.
        """
        from core.replenishment import apply_suggested_levels

        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'الشركة غير محددة'}, status=status.HTTP_400_BAD_REQUEST)
        raw = request.data.get('product_ids') or []
        if not isinstance(raw, list):
            return Response(
                {'error': 'product_ids يجب أن تكون قائمة معرّفات منتجات'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ids = [int(pid) for pid in raw]
        except (TypeError, ValueError):
            return Response(
                {'error': 'معرّف منتج غير صالح في القائمة'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not ids:
            return Response(
                {'error': 'لم تُحدَّد منتجات'}, status=status.HTTP_400_BAD_REQUEST,
            )
        result = apply_suggested_levels(tenant.TenantID, ids, user=request.user)
        return Response(result)

    @action(detail=False, methods=['post'], url_path='bulk-set-group')
    @requires_perm('inventory.item.manage')
    def bulk_set_group(self, request):
        """يضبط «النوع» و/أو البراند على منتجاتٍ محدَّدة دفعةً واحدة.

        لماذا نقطةٌ للجملة: `variant_group` هو مفتاح تجميع الموديلات (البدائل في
        الفاتورة، وقرار «مؤجَّل» في تقرير التجديد)، وكان فارغاً على كل منتجٍ في كل
        شركة لأنه بلا مدخل. ضبطُه منتجاً منتجاً على كتالوجٍ من ألفٍ ونصف يعني ألّا
        يُضبط أبداً.

        الحقل الغائب من الجسم **لا يُمَسّ**، والحقل الفارغ يُمحى — فيمكن تصحيح
        نوعٍ خاطئ كما يمكن تعيينه. المحدِّد في الجسم لا في العنوان.
        """
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'الشركة غير محددة'}, status=status.HTTP_400_BAD_REQUEST)
        raw = request.data.get('product_ids') or []
        if not isinstance(raw, list) or not raw:
            return Response(
                {'error': 'لم تُحدَّد منتجات'}, status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            ids = [int(pid) for pid in raw]
        except (TypeError, ValueError):
            return Response(
                {'error': 'معرّف منتج غير صالح في القائمة'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fields = {}
        if 'variant_group' in request.data:
            fields['variant_group'] = (request.data.get('variant_group') or '').strip()[:120]
        if 'brand' in request.data:
            fields['brand'] = (request.data.get('brand') or '').strip()[:100]
        if not fields:
            return Response(
                {'error': 'لا حقل للتعيين — مرّر variant_group أو brand'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        products = list(Product.objects.filter(tenant=tenant, pk__in=ids))
        for product in products:
            for name, value in fields.items():
                setattr(product, name, value)
        if products:
            Product.objects.bulk_update(products, list(fields))
            labels = '، '.join(
                f'{self.activity_field_labels.get(k, k)} = «{v or "—"}»'
                for k, v in fields.items()
            )
            log_activity(
                action='update',
                entity_type='product',
                entity_label=f'{len(products)} منتجاً',
                description=f'عيّن {labels} على {len(products)} منتجاً دفعةً واحدة',
                metadata={'product_ids': [p.id for p in products][:200], **fields},
                request=request,
                tenant=tenant,
                user=request.user,
            )
        return Response({'updated': len(products), 'fields': fields})

    # ── الباركود والأرقام التسلسلية ────────────────────────────────────
    @action(detail=False, methods=['post'], url_path='generate_barcode')
    def generate_barcode(self, request):
        """باركود EAN-13 داخلي (بادئة 2) غير مستخدم لهذه الشركة، بخانة تحقق سليمة.

        التوليد خادمي كي يبقى فحص «غير مستخدم» على مصدر البيانات نفسه — واجهةٌ
        تولّد رقماً محلياً قد تصطدم بمنتج لم تكن قد حمّلته.
        """
        from inventory.serials import generate_product_barcode
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'الشركة غير محددة'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            barcode = generate_product_barcode(tenant.TenantID)
        except DjangoValidationError as e:
            return Response(
                {'error': '؛ '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'barcode': barcode})

    @action(detail=False, methods=['post'], url_path='generate_serials')
    def generate_serials(self, request):
        """سلسلة أرقام تسلسلية من رقم بداية وعدد وحدات — «SN-0098» + 3.

        نقطة النهاية موجودة كي تبقى قاعدة التزايد (البادئة وخانات الصفر) في مكان
        واحد مُختبَر؛ إعادة تنفيذها في الواجهة تعني قاعدتين تتباعدان.
        """
        from inventory.serials import generate_serial_range
        try:
            serials = generate_serial_range(
                request.data.get('start'), request.data.get('count'),
            )
        except DjangoValidationError as e:
            return Response(
                {'error': '؛ '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'serials': serials})

    @action(detail=True, methods=['get'], url_path='serials')
    def serials(self, request, pk=None):
        """وحدات هذا المنتج المُرقَّمة — `?status=in_stock|sold` للفلترة."""
        from inventory.serials import product_serials
        product = self.get_object()
        return Response(product_serials(
            tenant_id=product.tenant_id,
            product_id=product.id,
            status=request.query_params.get('status') or None,
        ))

    @action(detail=True, methods=['post'], url_path='serials/register')
    def register_serials(self, request, pk=None):
        """ترقيم مخزون قائم — `{"serials": ["…"]}` ⇒ وحدات «في المخزن» بلا فاتورة.

        مخرج الشركة التي تُشغّل «إجباري» في البيع وكل مخزونها سابقٌ للميزة: بلا
        هذه النقطة يبقى النمط طريقاً مسدوداً لا يُفتح إلا بإطفائه.
        """
        from inventory.serials import product_serials, register_existing_serials
        product = self.get_object()
        try:
            created = register_existing_serials(
                tenant_id=product.tenant_id,
                product=product,
                serials=request.data.get('serials'),
            )
        except DjangoValidationError as e:
            return Response(
                {'error': e.message if hasattr(e, 'message') else '؛ '.join(e.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            'created': created,
            'serials': product_serials(
                tenant_id=product.tenant_id, product_id=product.id,
            ),
        }, status=status.HTTP_201_CREATED)


class ProductLookupViewSet(ProductViewSet):
    """ISSUE #88 — عقد `view=lookup` وحده، خارج بادئة `/api/inventory/`.

    قناع قالب `accounting_firm`/`client_book` (`tenants/company_templates.py`
    — `TEMPLATE_HIDDEN_PATH_PREFIXES`) يخفي بادئة `/api/inventory/` كاملةً
    بفحص بادئة المسار (`core/permissions.py` — `TemplateSurfacePermission`)،
    فمنتقي المستندات (فواتير المكتب — خدمات #78 — من بينها) لا يصله أبداً ولو
    حمل معاملَ `?view=lookup`: الحارس يفحص بادئة المسار لا معاملات الاستعلام.
    نقطةٌ مستقلة تحت `/api/lookup/products/` (`core/urls.py`) تخرج من نطاق
    القناع، بنفس منطق `ProductViewSet` **حرفياً** — لا نسخة ثانية من
    `get_queryset`/الفلاتر/السيريالايزر — محصورة بـ`list` وحده (لا كتابة هنا
    أصلاً)، وتفرض وضع `lookup` بصرف النظر عمّا أُرسل عبر `_is_lookup`.
    العزل وحارس الصلاحية موروثان من `ProductViewSet` كأي نقطة أخرى — تصفية
    `tenant` في `get_queryset` و`DEFAULT_PERMISSION_CLASSES` (لا صلاحيةٌ إضافية
    هنا: نفس ما يراه أي عضوٍ عبر `/api/inventory/products/?view=lookup` اليوم).
    """
    http_method_names = ['get', 'head', 'options']

    def _is_lookup(self):
        return True


class ProductSerialViewSet(viewsets.ViewSet):
    """بحث الأرقام التسلسلية على مستوى الشركة: من أين جاءت الوحدة وإلى أين ذهبت."""

    def list(self, request):
        from inventory.serials import search_serials
        tenant = get_tenant(request)
        if not tenant:
            return Response([])
        return Response(search_serials(
            tenant_id=tenant.TenantID,
            q=request.query_params.get('q', ''),
            status=request.query_params.get('status') or None,
            product_id=request.query_params.get('product') or None,
            limit=request.query_params.get('limit') or 100,
        ))


class SupplierProductViewSet(viewsets.ModelViewSet):
    """أرقام المنتجات عند الموردين — بياناتٌ رئيسية معزولة بالشركة.

    محايدة مالياً تماماً: لا قيد ولا حركة مخزون. الغرض واحد — أن تُطابَق فاتورة
    المورّد برقم كتالوجه لا برقمنا، وأن يجد البحثُ المنتجَ بذلك الرقم
    (`ProductViewSet.search_fields`).

    الترشيح: `?product=` لكرت المنتج، و`?supplier=` لكرت المورّد، و`?sku=`
    للمطابقة العكسية «هذا الرقم — أيّ منتج؟».
    """

    queryset = SupplierProduct.objects.all()
    serializer_class = SupplierProductSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return SupplierProduct.objects.none()
        qs = (
            super().get_queryset().filter(tenant=tenant)
            .select_related('supplier', 'product')
        )
        params = self.request.query_params
        product = str(params.get('product') or '').strip()
        supplier = str(params.get('supplier') or '').strip()
        sku = str(params.get('sku') or '').strip()
        if product.isdigit():
            qs = qs.filter(product_id=int(product))
        if supplier.isdigit():
            qs = qs.filter(supplier_id=int(supplier))
        if sku:
            qs = qs.filter(supplier_sku__iexact=sku)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['tenant'] = get_tenant(self.request)
        return ctx

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))


class WarehouseViewSet(viewsets.ModelViewSet):
    """مستودعات الشركة — معزولة بالشركة. الحذف يكتفي بالتعطيل (is_active=False)."""
    queryset = Warehouse.objects.all().select_related('branch').order_by('-is_default', 'name')
    serializer_class = WarehouseSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return Warehouse.objects.none()
        qs = super().get_queryset().filter(tenant=tenant)
        if self.request.query_params.get('active_only') == 'true':
            qs = qs.filter(is_active=True)
        return qs

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        # T-PLANLIMITS: عدد المستودعات المسموح به من خطة الشركة.
        enforce_limits(tenant, 'inventory.warehouses')
        # أول مستودع للشركة يصبح الافتراضي تلقائياً
        is_first = not Warehouse.objects.filter(tenant=tenant).exists()
        is_default = bool(serializer.validated_data.get('is_default') or is_first)
        if is_default:
            Warehouse.objects.filter(tenant=tenant, is_default=True).update(is_default=False)
        serializer.save(tenant=tenant, is_default=is_default)

    def perform_update(self, serializer):
        tenant = get_tenant(self.request)
        old_name = serializer.instance.name
        if serializer.validated_data.get('is_default'):
            Warehouse.objects.filter(tenant=tenant, is_default=True).exclude(
                pk=serializer.instance.pk
            ).update(is_default=False)
        warehouse = serializer.save()
        logger.info(
            "Warehouse updated tenant=%s warehouse=%s name_changed=%s",
            tenant.pk, warehouse.pk, warehouse.name != old_name,
        )
        log_activity(
            action='update',
            entity_type='warehouse',
            entity_id=warehouse.pk,
            entity_label=warehouse.name,
            description='تعديل المستودع',
            metadata={'name_changed': warehouse.name != old_name},
            request=self.request,
        )

    @action(detail=True, methods=['get'], url_path='stock')
    @requires_perm('inventory.cost.view')
    def stock(self, request, pk=None):
        warehouse = self.get_object()
        payload = warehouse_stock_summary(
            tenant_id=warehouse.tenant_id,
            warehouse_id=warehouse.id,
        )
        payload['warehouse'] = WarehouseSerializer(
            warehouse, context=self.get_serializer_context(),
        ).data
        log_view(
            entity_type='warehouse',
            entity_id=warehouse.pk,
            entity_label=warehouse.name,
            request=request,
        )
        return Response(payload)

    def destroy(self, request, *args, **kwargs):
        # تعطيل لا حذف نهائي — المخزون قد يشير للمستودع (PROTECT)
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class StockMovementViewSet(viewsets.ModelViewSet):
    queryset = StockMovement.objects.all().select_related('product', 'partner')
    serializer_class = StockMovementSerializer
    http_method_names = ['get', 'post', 'head', 'options']
    # P0-5: ترقيم إلزامي — أضخم جدول في النظام. المستهلكان:
    # StockMovementsPage مُرقَّمة أصلاً، وشاشة التقييم صارت على action
    # `valuation` التجميعي (لا تلمس القائمة). Meta.ordering يضمن ترتيباً حتمياً.
    pagination_class = EnforcedPageNumberPagination

    def get_queryset(self):
        qs = super().get_queryset()
        # task11 M7: حركات المخزون كانت بلا فلترة tenant في القراءة
        tenant = get_tenant(self.request)
        if not tenant:
            return StockMovement.objects.none()
        qs = qs.filter(tenant=tenant)
        # task11 M4: مخزون مستقل لكل فرع — الفرع النشط يرى حركاته فقط
        # (الرئيسي يشمل الحركات القديمة بلا فرع)
        from core.tenant_utils import get_branch
        branch = get_branch(self.request, tenant)
        if branch is not None:
            from django.db.models import Q
            if branch.is_main:
                qs = qs.filter(Q(branch=branch) | Q(branch__isnull=True))
            else:
                qs = qs.filter(branch=branch)
        params = self.request.query_params
        pid = params.get('product')
        if pid:
            qs = qs.filter(product_id=pid)
        mt = params.get('movement_type')
        if mt:
            qs = qs.filter(movement_type=mt)
        rt = params.get('reference_type')
        if rt:
            qs = qs.filter(reference_type=rt)
        # تقسيم المخزن: مصدر البضاعة محلي (فاتورة شراء) أو دولي (مسار الاستيراد).
        origin = params.get('origin')
        if origin == 'international':
            qs = qs.filter(reference_type__in=StockMovement.IMPORT_REFERENCE_TYPES)
        elif origin == 'local':
            qs = qs.filter(reference_type__in=StockMovement.LOCAL_REFERENCE_TYPES)
        df = params.get('date_from')
        if df:
            qs = qs.filter(movement_date__gte=df)
        dt = params.get('date_to')
        if dt:
            qs = qs.filter(movement_date__lte=dt)
        return qs

    @action(detail=False, methods=['get'], url_path='valuation')
    def valuation(self, request):
        """P0-5: تقييم المخزون خادمياً — صف تجميعي واحد لكل منتج.

        كانت شاشة التقييم تجلب **كل حركات المخزون** إلى المتصفح وتحسب هناك
        (أضخم جدول في النظام). هنا تُحسب التجميعات نفسها بـsubqueries على
        الفهرس (tenant, product, movement_date) وتعود ~صف/منتج، وتبديل طريقة
        التقييم في الشاشة يبقى client-side فورياً على هذه التجميعات:
        - first/last IN unit_cost (بترتيب movement_date,id) — لطريقتَي FIFO/LIFO.
        - متوسط unit_cost>0 للداخل والخارج — avg_purchase/avg_sale.
        - صافي الكمية (IN موجب وكل ما عداه سالب) — bonus «من الحركات»؛
          نفس دلالة includes("IN") في الواجهة حرفياً: ADJUST_IN/RETURN_IN داخل.
        """
        from django.db.models import Avg, Case, OuterRef, Subquery, When

        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'الشركة غير محددة'}, status=400)
        as_of = request.query_params.get('as_of')

        moves = StockMovement.objects.filter(
            tenant=tenant, product=OuterRef('pk'))
        if as_of:
            moves = moves.filter(movement_date__lte=as_of)
        ins = moves.filter(movement_type__contains='IN')
        outs = moves.filter(movement_type__contains='OUT')
        money = DecimalField(max_digits=18, decimal_places=4)

        def _agg(qs, expr):
            return Subquery(
                qs.values('product').annotate(v=expr).values('v')[:1],
                output_field=money,
            )

        products = Product.objects.filter(tenant=tenant).select_related(
            'category',
        ).annotate(
            first_in_cost=Subquery(
                ins.order_by('movement_date', 'id').values('unit_cost')[:1],
                output_field=money),
            last_in_cost=Subquery(
                ins.order_by('-movement_date', '-id').values('unit_cost')[:1],
                output_field=money),
            avg_in_cost=_agg(ins.filter(unit_cost__gt=0), Avg('unit_cost')),
            avg_out_cost=_agg(outs.filter(unit_cost__gt=0), Avg('unit_cost')),
            moves_qty_delta=_agg(moves, Sum(Case(
                When(movement_type__contains='IN', then=F('quantity')),
                default=-F('quantity'),
            ))),
        ).order_by('sku')

        rows = [
            {
                'id': p.id,
                'sku': p.sku,
                'name_ar': p.name_ar,
                'name_en': p.name_en,
                'category_name': p.category.name if p.category_id else '',
                'quantity_on_hand': str(p.quantity_on_hand),
                'avg_cost': str(p.avg_cost),
                'first_in_cost': str(p.first_in_cost) if p.first_in_cost is not None else None,
                'last_in_cost': str(p.last_in_cost) if p.last_in_cost is not None else None,
                'avg_in_cost': str(p.avg_in_cost) if p.avg_in_cost is not None else None,
                'avg_out_cost': str(p.avg_out_cost) if p.avg_out_cost is not None else None,
                'moves_qty_delta': str(p.moves_qty_delta) if p.moves_qty_delta is not None else None,
            }
            for p in products
        ]
        return Response({'as_of': as_of, 'rows': rows})

    def create(self, request, *args, **kwargs):
        data = request.data
        tenant = get_tenant(request)
        if not tenant:
            return Response(
                {'error': 'الشركة غير محددة'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product_id = data.get('product')
        if not product_id:
            return Response({'error': 'المنتج مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # لا تحل المنتج بالـ PK وحده: تمرير معرّف شركة أخرى كان يسمح
            # بتعديل رصيدها من خلال هذا المسار اليدوي.
            product = Product.objects.get(pk=product_id, tenant=tenant)
        except Product.DoesNotExist:
            return Response({'error': 'المنتج غير موجود'}, status=status.HTTP_404_NOT_FOUND)

        movement_type = data.get('movement_type', '')
        if movement_type not in dict(StockMovement.MOVEMENT_TYPES):
            return Response({'error': 'نوع الحركة غير صالح'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            qty = Decimal(str(data.get('quantity', 0)))
            cost = Decimal(str(data.get('unit_cost', 0)))
        except Exception:
            return Response({'error': 'قيم غير صالحة'}, status=status.HTTP_400_BAD_REQUEST)

        movement_date = data.get('movement_date') or timezone.localdate()
        partner_id = data.get('partner')
        partner = None
        if partner_id:
            from partners.models import Partner
            partner = Partner.objects.filter(pk=partner_id, tenant=tenant).first()
            if partner is None:
                return Response({'error': 'الشريك غير موجود'}, status=status.HTTP_404_NOT_FOUND)

        try:
            mv = record_stock_movement(
                product=product,
                movement_type=movement_type,
                quantity=qty,
                unit_cost=cost,
                reference_type=data.get('reference_type', 'MANUAL'),
                reference_id=data.get('reference_id'),
                partner=partner,
                movement_date=movement_date,
                notes=data.get('notes', ''),
                tenant=tenant,
            )
            return Response(
                StockMovementSerializer(mv).data,
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        tenant = get_tenant(request)
        if not tenant:
            return Response({
                'products': [],
                'total_inventory_value': 0,
                'total_products_in_stock': 0,
            })
        products = Product.objects.filter(
            tenant=tenant,
            quantity_on_hand__gt=0
        ).order_by('-quantity_on_hand')[:50]
        from sales.services import reserved_quantity_map
        reserved = reserved_quantity_map(tenant.TenantID, [p.id for p in products] or None)
        result = []
        for p in products:
            result.append({
                'id': p.id,
                'sku': p.sku,
                'name': p.name_ar or p.name_en or p.sku,
                'quantity_on_hand': float(p.quantity_on_hand),
                'avg_cost': float(p.avg_cost),
                'total_value': float(p.quantity_on_hand * p.avg_cost),
                'min_stock_level': p.min_stock_level,
                # T-REORDER: نسخةٌ ثالثة من القاعدة كانت هنا — صارت نداءً واحداً.
                'stock_status': stock_status_of(p, reserved_map=reserved),
            })
        total_value = sum(r['total_value'] for r in result)
        return Response({
            'products': result,
            'total_inventory_value': total_value,
            'total_products_in_stock': len(result),
        })


# ── Phase 7 (T-I1/T-I2): مستندات المخزون ──────────────────────────────

class WarehouseTransferViewSet(viewsets.ModelViewSet):
    """T-I1: تحويل بضاعة بين مستودعين — معزول بالشركة. الترحيل عبر action /post/."""
    queryset = WarehouseTransfer.objects.all().prefetch_related('lines__product').order_by('-transfer_date', '-id')
    serializer_class = WarehouseTransferSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return WarehouseTransfer.objects.none()
        return super().get_queryset().filter(tenant=tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))

    @action(detail=True, methods=['post'], url_path='post')
    @requires_perm('inventory.doc.post')
    def post_doc(self, request, pk=None):
        transfer = self.get_object()
        try:
            post_warehouse_transfer(transfer, user=request.user)
        except serializers.ValidationError:
            raise
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(transfer).data)

    @action(detail=True, methods=['post'], url_path='unpost')
    @requires_perm('inventory.doc.unpost')
    def unpost_doc(self, request, pk=None):
        transfer = self.get_object()
        try:
            unpost_warehouse_transfer(transfer, user=request.user)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(transfer).data)


class StocktakeViewSet(viewsets.ModelViewSet):
    """T-I2: جرد فعلي — معزول بالشركة. الترحيل عبر action /post/ (يسوّي المخزون + قيد الفرق)."""
    queryset = Stocktake.objects.all().prefetch_related('lines__product').order_by('-stocktake_date', '-id')
    serializer_class = StocktakeSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return Stocktake.objects.none()
        return super().get_queryset().filter(tenant=tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=get_tenant(self.request))

    @action(detail=True, methods=['post'], url_path='post')
    def post_doc(self, request, pk=None):
        stocktake = self.get_object()
        try:
            post_stocktake(stocktake, user=request.user)
        except serializers.ValidationError:
            raise
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(stocktake).data)

