from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import ProductCategory, Product, UnitOfMeasure
from .serializers import CategorySerializer, ProductSerializer, UnitOfMeasureSerializer
from tenants.models import Tenant

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
        tenant = Tenant.objects.first() 
        serializer.save(tenant=tenant)

class UnitOfMeasureViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = UnitOfMeasure.objects.filter(is_active=True)
    serializer_class = UnitOfMeasureSerializer

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('name_ar')
    serializer_class = ProductSerializer

    def _get_tenant(self):
        return Tenant.objects.first()

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

