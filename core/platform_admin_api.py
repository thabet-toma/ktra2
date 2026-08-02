"""واجهات إدارة المنصة — عالمية ومحروسة بالسوبر أدمن فقط."""
import logging

from django.contrib.auth import get_user_model
from django.db.models import Count
from rest_framework import serializers, viewsets
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from core.import_access import is_super_admin
from core.models import DevelopmentNote
from tenants.models import Tenant, UserCompanyMembership


logger = logging.getLogger(__name__)
User = get_user_model()


class IsPlatformAdmin(BasePermission):
    message = 'هذه المساحة متاحة لسوبر أدمن المنصة فقط.'

    def has_permission(self, request, view):
        return is_super_admin(request.user)


class DevelopmentNoteSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DevelopmentNote
        fields = [
            'id', 'title', 'description', 'status', 'priority', 'assignee',
            'due_date', 'position', 'created_by', 'created_by_name',
            'updated_by', 'updated_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'created_by', 'created_by_name', 'updated_by',
            'updated_by_name', 'created_at', 'updated_at',
        ]

    def validate_title(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('عنوان الملاحظة مطلوب.')
        return value

    @staticmethod
    def _user_name(user):
        if user is None:
            return ''
        return (f'{user.first_name} {user.last_name}').strip() or user.username

    def get_created_by_name(self, obj):
        return self._user_name(obj.created_by)

    def get_updated_by_name(self, obj):
        return self._user_name(obj.updated_by)


class DevelopmentNoteViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsPlatformAdmin]
    serializer_class = DevelopmentNoteSerializer
    queryset = DevelopmentNote.objects.select_related('created_by', 'updated_by')

    def perform_create(self, serializer):
        note = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        logger.info('platform development note created id=%s by_user=%s', note.id, self.request.user.pk)

    def perform_update(self, serializer):
        note = serializer.save(updated_by=self.request.user)
        logger.info('platform development note updated id=%s by_user=%s', note.id, self.request.user.pk)

    def perform_destroy(self, instance):
        note_id = instance.id
        instance.delete()
        logger.info('platform development note deleted id=%s by_user=%s', note_id, self.request.user.pk)


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_dashboard(request):
    """مؤشرات تشغيل المنصة بلا بيانات مالية داخلية للشركات."""
    companies = Tenant.objects.annotate(member_count=Count('memberships')).order_by('-CreatedAt')
    company_rows = [
        {
            'id': tenant.TenantID,
            'name': tenant.CompanyName,
            'plan': tenant.SubscriptionPlan,
            'status': tenant.Status,
            'import_enabled': tenant.import_enabled,
            'member_count': tenant.member_count,
            'created_at': tenant.CreatedAt,
        }
        for tenant in companies
    ]
    status_counts = {
        row['Status']: row['count']
        for row in Tenant.objects.values('Status').annotate(count=Count('TenantID'))
    }
    plan_counts = {
        row['SubscriptionPlan']: row['count']
        for row in Tenant.objects.values('SubscriptionPlan').annotate(count=Count('TenantID'))
    }
    return Response({
        'companies': {
            'total': len(company_rows),
            'active': status_counts.get('Active', 0),
            'trial': status_counts.get('Trial', 0),
            'suspended': status_counts.get('Suspended', 0),
        },
        'users': {
            'total': User.objects.count(),
            'active': User.objects.filter(is_active=True).count(),
        },
        'memberships': UserCompanyMembership.objects.count(),
        'status_distribution': status_counts,
        'plan_distribution': plan_counts,
        'company_rows': company_rows,
    })
