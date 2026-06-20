import datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
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
    search_fields = ['sku', 'barcode', 'name_ar', 'name_en', 'category__name']
    ordering_fields = ['id', 'sku', 'name_ar', 'quantity_on_hand', 'avg_cost', 'created_at']
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
        return qs

    def _handle_attachments(self, product, data, tenant):
        from core.models import SystemAttachment
        image_url = data.get('image_url') or data.get('image_path')
        if image_url and isinstance(image_url, str) and image_url.startswith('http'):
            if not SystemAttachment.objects.filter(
                tenant=tenant,
                related_table='products',
                related_id=product.id,
                file_path=image_url
            ).exists():
                SystemAttachment.objects.create(
                    tenant=tenant,
                    related_table='products',
                    related_id=product.id,
                    file_type='Product Image',
                    file_path=image_url
                )

    def _validate_category_tenant(self, serializer, tenant):
        # DEF-A1: التصنيف FK يجب أن يكون من نفس الشركة
        category = serializer.validated_data.get('category')
        if category and category.tenant_id != tenant.pk:
            raise serializers.ValidationError({'category': 'التصنيف غير موجود لهذه الشركة.'})

    def create(self, request, *args, **kwargs):
        tenant = self._get_tenant()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._validate_category_tenant(serializer, tenant)

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

