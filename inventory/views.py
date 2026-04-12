import datetime
from decimal import Decimal

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ProductCategory, Product, UnitOfMeasure, StockMovement
from .serializers import (
    CategorySerializer, ProductSerializer, UnitOfMeasureSerializer,
    StockMovementSerializer,
)
from .services import record_stock_movement
from tenants.models import Tenant
from core.tenant_utils import get_tenant

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all().order_by('name')
    serializer_class = CategorySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
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
    queryset = Product.objects.all().order_by('name_ar')
    serializer_class = ProductSerializer

    def _get_tenant(self):
        return get_tenant(self.request)

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

    def create(self, request, *args, **kwargs):
        tenant = self._get_tenant()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save(tenant=tenant)
        self._handle_attachments(product, request.data, tenant)
        return Response(self.get_serializer(product).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        tenant = self._get_tenant()
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        self._handle_attachments(product, request.data, tenant)
        return Response(self.get_serializer(product).data)

    @action(detail=True, methods=['get'], url_path='stock-movements')
    def stock_movements(self, request, pk=None):
        product = self.get_object()
        qs = StockMovement.objects.filter(product=product).select_related('partner')
        return Response(StockMovementSerializer(qs[:50], many=True).data)


class StockMovementViewSet(viewsets.ModelViewSet):
    queryset = StockMovement.objects.all().select_related('product', 'partner')
    serializer_class = StockMovementSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
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

