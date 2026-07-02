import datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F
from rest_framework import filters, serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from .models import (
    ProductCategory, Product, UnitOfMeasure, StockMovement, Warehouse,
    WarehouseTransfer, Stocktake,
)
from .serializers import (
    CategorySerializer, ProductSerializer, UnitOfMeasureSerializer,
    StockMovementSerializer, WarehouseSerializer,
    WarehouseTransferSerializer, StocktakeSerializer,
)
from .services import (
    generate_next_sku, record_stock_movement,
    post_warehouse_transfer, unpost_warehouse_transfer, post_stocktake,
)
from tenants.models import Tenant
from core.tenant_utils import get_tenant


class OptionalPageNumberPagination(PageNumberPagination):
    """
    task14 M2 (DEF-A5): ترقيم صفحات opt-in — يُفعَّل فقط بوجود ?page=
    حتى لا تنكسر الشاشات القائمة التي تتوقع مصفوفة خام بلا غلاف.
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        if 'page' not in request.query_params:
            return None
        return super().paginate_queryset(queryset, request, view)

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

class UnitOfMeasureViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = UnitOfMeasure.objects.filter(is_active=True)
    serializer_class = UnitOfMeasureSerializer

class ProductViewSet(viewsets.ModelViewSet):
    # task14 M2 (DEF-A5): ترتيب افتراضي حتمي «الأحدث أولاً» + بحث/فرز/ترقيم خادمي
    queryset = Product.objects.all().select_related('category')
    serializer_class = ProductSerializer
    pagination_class = OptionalPageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['sku', 'barcode', 'name_ar', 'name_en', 'brand', 'category__name']
    ordering_fields = ['id', 'sku', 'name_ar', 'quantity_on_hand', 'avg_cost', 'min_stock_level', 'created_at']
    ordering = ['-id']

    def _get_tenant(self):
        return get_tenant(self.request)

    def get_queryset(self):
        # task11 M7: الأصناف كانت بلا فلترة tenant في القراءة —
        # أصناف كل الشركات تظهر للشركة الجديدة. .none() عند غياب الشركة.
        tenant = self._get_tenant()
        if not tenant:
            return Product.objects.none()
        qs = super().get_queryset().filter(tenant=tenant)
        params = self.request.query_params
        category_id = params.get('category')
        if category_id:
            qs = qs.filter(category_id=category_id)
        created_from = params.get('created_from')
        if created_from:
            qs = qs.filter(created_at__date__gte=created_from)
        created_to = params.get('created_to')
        if created_to:
            qs = qs.filter(created_at__date__lte=created_to)
        # جدول الأصناف: فلتر حالة المخزون — مطابق لمنطق ProductSerializer.get_stock_status
        # (نفذ: ≤0 · منخفض: >0 و حد أدنى>0 و ≤الحد الأدنى · متوفر: الباقي).
        stock_status = params.get('stock_status')
        if stock_status == 'out_of_stock':
            qs = qs.filter(quantity_on_hand__lte=0)
        elif stock_status == 'low_stock':
            qs = qs.filter(
                quantity_on_hand__gt=0,
                min_stock_level__gt=0,
                quantity_on_hand__lte=F('min_stock_level'),
            )
        elif stock_status == 'in_stock':
            qs = qs.filter(quantity_on_hand__gt=0).exclude(
                min_stock_level__gt=0,
                quantity_on_hand__lte=F('min_stock_level'),
            )
        return qs

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

    def _auto_create_group_category(self, serializer, tenant):
        variant_group = (serializer.validated_data.get('variant_group') or '').strip()
        base_category = serializer.validated_data.get('category')
        
        if variant_group and base_category:
            # If editing and the incoming category is the old group category itself, use its parent as the base.
            if getattr(self, 'action', '') in ['update', 'partial_update'] and self.instance:
                old_category_id = getattr(self.instance, 'category_id', None)
                old_variant_group = (getattr(self.instance, 'variant_group', '') or '').strip()
                if old_category_id == base_category.id and base_category.name == old_variant_group and base_category.parent:
                    base_category = base_category.parent

            if base_category.name == variant_group:
                return
            cat, _ = ProductCategory.objects.get_or_create(
                tenant=tenant,
                name=variant_group,
                parent=base_category,
                defaults={
                    'revenue_account': base_category.revenue_account,
                    'cogs_account': base_category.cogs_account,
                    'inventory_account': base_category.inventory_account,
                }
            )
            serializer.validated_data['category'] = cat

    def create(self, request, *args, **kwargs):
        tenant = self._get_tenant()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._validate_category_tenant(serializer, tenant)
        self._auto_create_group_category(serializer, tenant)

        # task14 M2 (DEF-A2): SKU يولَّد خادمياً عند الغياب — مع إعادة محاولة عند السباق
        explicit_sku = (serializer.validated_data.get('sku') or '').strip()
        if explicit_sku:
            if Product.objects.filter(tenant=tenant, sku=explicit_sku).exists():
                raise serializers.ValidationError({'sku': 'رقم الصنف مستخدم مسبقاً لهذه الشركة.'})
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
                raise serializers.ValidationError({'sku': 'تعذّر توليد رقم صنف — أعد المحاولة.'})

        self._handle_attachments(product, request.data, tenant)
        return Response(self.get_serializer(product).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        tenant = self._get_tenant()
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        self._validate_category_tenant(serializer, tenant)
        self._auto_create_group_category(serializer, tenant)
        # task14 M2: SKU فارغ في التعديل = «أبقِ الرقم الحالي» — لا تمسحه
        new_sku = (serializer.validated_data.get('sku') or '').strip()
        if 'sku' in serializer.validated_data:
            if not new_sku:
                serializer.validated_data.pop('sku')
            elif new_sku != instance.sku and Product.objects.filter(
                tenant=tenant, sku=new_sku
            ).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError({'sku': 'رقم الصنف مستخدم مسبقاً لهذه الشركة.'})
        product = serializer.save()
        self._handle_attachments(product, request.data, tenant)
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
    # تمرّر الواجهة معرّفات أعضاء المجموعة عبر ?ids=1,2,3 (تحسبها من group_key)؛
    # العزل بالشركة في الخدمة. النقر على عقدة الأب في الشجرة/الجرد يفتح هذه الكروت.
    def _group_ids(self, request):
        raw = request.query_params.get('ids', '')
        ids = []
        for part in raw.split(','):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        return ids

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
        """قائمة المجموعات (الأصناف الفرعية) المستخدمة — لمنتقي المجموعة (اختر/أضف)."""
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

    @action(detail=False, methods=['get'], url_path='group-profile')
    def group_profile(self, request):
        from inventory.services import product_group_profile
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'الشركة غير محددة'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(product_group_profile(
            tenant_id=tenant.pk, product_ids=self._group_ids(request)))

    @action(detail=False, methods=['get'], url_path='group-ledger')
    def group_ledger(self, request):
        from inventory.services import product_stock_ledger
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'الشركة غير محددة'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            limit = min(int(request.query_params.get('limit', 50)), 200)
        except (TypeError, ValueError):
            limit = 50
        try:
            offset = max(int(request.query_params.get('offset', 0)), 0)
        except (TypeError, ValueError):
            offset = 0
        return Response(product_stock_ledger(
            tenant_id=tenant.pk, product_ids=self._group_ids(request),
            limit=limit, offset=offset))

    @action(detail=False, methods=['get'], url_path='group-invoices')
    def group_invoices(self, request):
        from inventory.services import product_linked_invoices
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'الشركة غير محددة'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(product_linked_invoices(
            tenant_id=tenant.pk, product_ids=self._group_ids(request)))


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
        # أول مستودع للشركة يصبح الافتراضي تلقائياً
        is_first = not Warehouse.objects.filter(tenant=tenant).exists()
        is_default = bool(serializer.validated_data.get('is_default') or is_first)
        if is_default:
            Warehouse.objects.filter(tenant=tenant, is_default=True).update(is_default=False)
        serializer.save(tenant=tenant, is_default=is_default)

    def perform_update(self, serializer):
        tenant = get_tenant(self.request)
        if serializer.validated_data.get('is_default'):
            Warehouse.objects.filter(tenant=tenant, is_default=True).exclude(
                pk=serializer.instance.pk
            ).update(is_default=False)
        serializer.save()

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

    def create(self, request, *args, **kwargs):
        data = request.data
        product_id = data.get('product')
        if not product_id:
            return Response({'error': 'المنتج مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            product = Product.objects.get(pk=product_id)
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

        movement_date = data.get('movement_date') or datetime.date.today()
        partner_id = data.get('partner')
        partner = None
        if partner_id:
            from partners.models import Partner
            partner = Partner.objects.filter(pk=partner_id).first()

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
            )
            return Response(
                StockMovementSerializer(mv).data,
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        from django.db.models import Sum, Count, Q
        products = Product.objects.filter(
            quantity_on_hand__gt=0
        ).order_by('-quantity_on_hand')[:50]
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
                'stock_status': (
                    'low_stock' if p.min_stock_level and p.quantity_on_hand <= p.min_stock_level
                    else 'in_stock'
                ),
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

