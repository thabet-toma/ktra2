"""واجهات إدارة المنصة — عالمية ومحروسة بالسوبر أدمن فقط."""
import logging

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from rest_framework import serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from core.import_access import is_super_admin, super_admin_emails
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


def _super_admin_row(user):
    by_email = (user.email or '').strip().lower() in super_admin_emails()
    return {
        'id': user.pk,
        'username': user.username,
        'email': user.email,
        'full_name': f'{user.first_name} {user.last_name}'.strip() or user.username,
        'is_active': user.is_active,
        # مصدر الصلاحية: العلم قابل للسحب، أما بريدٌ مُهيّأ في الإعدادات فلا
        # يُسحب من الواجهة (يُغيَّر في settings.SUPER_ADMIN_EMAILS).
        'source': 'settings' if by_email and not user.is_superuser else 'flag',
        'removable': user.is_superuser and not by_email,
    }


def _super_admin_queryset():
    """أصحاب الصلاحية: حاملو العلم + أصحاب البريد المُهيّأ (المطابقة بلا حالة أحرف)."""
    emails = super_admin_emails()
    ids = set(User.objects.filter(is_superuser=True).values_list('pk', flat=True))
    if emails:
        ids.update(
            pk
            for pk, email in User.objects.exclude(email='').values_list('pk', 'email')
            if (email or '').strip().lower() in emails
        )
    return User.objects.filter(pk__in=ids).order_by('username')


@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_super_admins(request):
    """قائمة سوبر أدمن المنصة، وترقية مستخدم قائم إلى سوبر أدمن.

    الترقية **لا تُنشئ حساباً** ولا تلمس كلمة سر — تبحث عن مستخدم مسجَّل باسمه
    أو بريده وترفع علم `is_superuser`. إنشاء الحسابات يبقى في مسار التسجيل.
    """
    if request.method == 'GET':
        return Response([_super_admin_row(user) for user in _super_admin_queryset()])

    identifier = str(request.data.get('identifier') or '').strip()
    if not identifier:
        return Response(
            {'detail': 'اكتب اسم المستخدم أو بريده.'}, status=status.HTTP_400_BAD_REQUEST)

    target = User.objects.filter(
        Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
    if target is None:
        return Response(
            {'detail': 'لا يوجد مستخدم بهذا الاسم أو البريد.'}, status=status.HTTP_404_NOT_FOUND)
    if target.is_superuser:
        return Response(
            {'detail': 'هذا المستخدم سوبر أدمن أصلاً.'}, status=status.HTTP_400_BAD_REQUEST)

    target.is_superuser = True
    target.is_staff = True
    target.save(update_fields=['is_superuser', 'is_staff'])
    logger.info('platform super admin granted user=%s by_user=%s', target.pk, request.user.pk)
    return Response(_super_admin_row(target), status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_super_admin_detail(request, pk):
    """سحب صلاحية السوبر أدمن — بلا حذف الحساب ولا مسّ عضويات الشركات."""
    target = User.objects.filter(pk=pk).first()
    if target is None or not target.is_superuser:
        return Response({'detail': 'غير موجود.'}, status=status.HTTP_404_NOT_FOUND)
    if target.pk == request.user.pk:
        return Response(
            {'detail': 'لا تسحب الصلاحية من نفسك — اطلب ذلك من سوبر أدمن آخر.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if (target.email or '').strip().lower() in super_admin_emails():
        return Response(
            {'detail': 'بريد هذا المستخدم مُهيّأ كسوبر أدمن في إعدادات المنصة — يُسحب من الإعدادات.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    target.is_superuser = False
    target.is_staff = False
    target.save(update_fields=['is_superuser', 'is_staff'])
    logger.info('platform super admin revoked user=%s by_user=%s', target.pk, request.user.pk)
    return Response(status=status.HTTP_204_NO_CONTENT)


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
