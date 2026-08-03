"""واجهات إدارة المنصة — عالمية ومحروسة بالسوبر أدمن فقط."""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
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


def _company_payload(tenant, member_count=None):
    return {
        'id': tenant.TenantID,
        'name': tenant.CompanyName,
        'plan': tenant.SubscriptionPlan,
        'status': tenant.Status,
        'import_enabled': tenant.import_enabled,
        'is_example': tenant.is_example,
        'member_count': (
            member_count if member_count is not None
            else UserCompanyMembership.objects.filter(tenant=tenant).count()
        ),
        'created_at': tenant.CreatedAt,
    }


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_dashboard(request):
    """مؤشرات تشغيل المنصة بلا بيانات مالية داخلية للشركات."""
    companies = Tenant.objects.annotate(member_count=Count('memberships')).order_by('-CreatedAt')
    company_rows = [
        _company_payload(tenant, tenant.member_count) for tenant in companies
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


# ── تحكم السوبر أدمن بالشركات وأعضائها ──
# السوبر أدمن يدير أي شركة دون أن يكون عضواً فيها؛ مسارات tenants تبقى للمدير
# داخل شركته (require_perm)، وهذه المسارات محروسة بـ IsPlatformAdmin وحده.

_BOOL_FIELD = serializers.BooleanField()


def _member_rows(tenant):
    from tenants.services import member_payload

    qs = (
        UserCompanyMembership.objects
        .filter(tenant=tenant)
        .select_related('user')
        .order_by('user__username')
    )
    return [member_payload(m) for m in qs]


def _valid_roles():
    return {role for role, _ in UserCompanyMembership.ROLE_CHOICES}


def _apply_company_changes(tenant, data):
    """يطبّق الحقول المُرسلة فقط ويعيد أسماء أعمدة الحفظ، أو يرفع 400."""
    changed = []
    if 'name' in data:
        name = str(data.get('name') or '').strip()
        if not name:
            raise serializers.ValidationError({'name': 'اسم الشركة مطلوب.'})
        tenant.CompanyName = name
        changed.append('CompanyName')
    if 'plan' in data:
        plan = str(data.get('plan') or '').strip()
        if plan not in {p for p, _ in Tenant.SUBSCRIPTION_PLANS}:
            raise serializers.ValidationError({'plan': 'خطة اشتراك غير معروفة.'})
        tenant.SubscriptionPlan = plan
        changed.append('SubscriptionPlan')
    if 'status' in data:
        state = str(data.get('status') or '').strip()
        if state not in {s for s, _ in Tenant.STATUS_CHOICES}:
            raise serializers.ValidationError({'status': 'حالة شركة غير معروفة.'})
        tenant.Status = state
        changed.append('Status')
    if 'import_enabled' in data:
        tenant.import_enabled = _BOOL_FIELD.to_internal_value(data.get('import_enabled'))
        changed.append('import_enabled')
    return changed


@api_view(['GET', 'PATCH'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_company_detail(request, pk):
    """كرت الشركة في لوحة المنصة: بياناتها وأعضاؤها، وتعديل الاسم/الخطة/الحالة/الاستيراد."""
    tenant = Tenant.objects.filter(pk=pk).first()
    if tenant is None:
        return Response({'detail': 'الشركة غير موجودة.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PATCH':
        with transaction.atomic():
            changed = _apply_company_changes(tenant, request.data)
            if changed:
                tenant.save(update_fields=changed)
            if 'is_example' in request.data:
                from tenants.services import set_example_company

                requested = _BOOL_FIELD.to_internal_value(request.data.get('is_example'))
                if requested:
                    set_example_company(tenant)
                elif tenant.is_example:
                    set_example_company(None)
                    tenant.is_example = False
                changed.append('is_example')
            if changed:
                logger.info('platform company updated tenant=%s fields=%s by_user=%s',
                            tenant.pk, ','.join(changed), request.user.pk)
        return Response(_company_payload(tenant))

    return Response({**_company_payload(tenant), 'members': _member_rows(tenant)})


@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_company_members(request, pk):
    """أعضاء الشركة — عرض وإضافة. POST: {"identifier": "...", "role": "..."}"""
    from tenants.services import member_payload

    tenant = Tenant.objects.filter(pk=pk).first()
    if tenant is None:
        return Response({'detail': 'الشركة غير موجودة.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        return Response(_member_rows(tenant))

    identifier = str(request.data.get('identifier') or '').strip()
    role = str(request.data.get('role') or 'staff').strip()
    if not identifier:
        return Response({'detail': 'اكتب اسم المستخدم أو بريده.'}, status=status.HTTP_400_BAD_REQUEST)
    if role not in _valid_roles():
        return Response({'role': 'دور غير معروف.'}, status=status.HTTP_400_BAD_REQUEST)
    target = User.objects.filter(
        Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
    if target is None:
        return Response(
            {'detail': 'لا يوجد مستخدم بهذا الاسم أو البريد. يجب أن يسجّل حسابه أولاً.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    membership, created = UserCompanyMembership.objects.get_or_create(
        user=target, tenant=tenant, defaults={'role': role})
    if not created:
        return Response(
            {'detail': 'المستخدم عضو في هذه الشركة بالفعل.'}, status=status.HTTP_400_BAD_REQUEST)
    logger.info('platform member added tenant=%s user=%s role=%s by_user=%s',
                tenant.pk, target.pk, role, request.user.pk)
    return Response(member_payload(membership), status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_company_member_detail(request, pk, membership_id):
    """تعديل عضوية (الدور/صلاحية الاستيراد) أو إخراج العضو من الشركة."""
    from tenants.services import is_last_manager, member_payload

    membership = (
        UserCompanyMembership.objects
        .filter(pk=membership_id, tenant_id=pk)
        .select_related('user', 'tenant')
        .first()
    )
    if membership is None:
        return Response({'detail': 'العضوية غير موجودة في هذه الشركة.'}, status=status.HTTP_404_NOT_FOUND)
    tenant = membership.tenant

    if request.method == 'DELETE':
        if is_last_manager(tenant, membership):
            return Response(
                {'detail': 'لا يمكن إخراج آخر مدير في الشركة — عيّن مديراً آخر أولاً.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user_id = membership.user_id
        membership.delete()
        logger.info('platform member removed tenant=%s user=%s by_user=%s',
                    tenant.pk, user_id, request.user.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    changed = []
    if 'role' in request.data:
        role = str(request.data.get('role') or '').strip()
        if role not in _valid_roles():
            return Response({'role': 'دور غير معروف.'}, status=status.HTTP_400_BAD_REQUEST)
        if role != 'manager' and is_last_manager(tenant, membership):
            return Response(
                {'detail': 'لا يمكن تخفيض آخر مدير في الشركة — عيّن مديراً آخر أولاً.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership.role = role
        changed.append('role')
    if 'can_access_import' in request.data:
        if not tenant.import_enabled:
            return Response(
                {'detail': 'فعّل وحدة الاستيراد للشركة أولاً ثم امنحها للأعضاء.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership.can_access_import = _BOOL_FIELD.to_internal_value(
            request.data.get('can_access_import'))
        changed.append('can_access_import')
    if changed:
        membership.save(update_fields=changed)
        logger.info('platform membership updated id=%s fields=%s by_user=%s',
                    membership.pk, ','.join(changed), request.user.pk)
    return Response(member_payload(membership))


@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_user_set_active(request, pk):
    """إيقاف/تفعيل حساب مستخدم على مستوى المنصة — الحساب الموقوف يُمنع من الدخول.

    body: {"is_active": true|false}. لا يمسّ العضويات ولا البيانات.
    """
    target = User.objects.filter(pk=pk).first()
    if target is None:
        return Response({'detail': 'المستخدم غير موجود.'}, status=status.HTTP_404_NOT_FOUND)
    is_active = _BOOL_FIELD.to_internal_value(request.data.get('is_active'))
    if not is_active:
        if target.pk == request.user.pk:
            return Response(
                {'detail': 'لا توقف حسابك — اطلب ذلك من سوبر أدمن آخر.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (target.email or '').strip().lower() in super_admin_emails():
            return Response(
                {'detail': 'حساب سوبر أدمن مُهيّأ في إعدادات المنصة — لا يُوقف من هنا.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
    target.is_active = is_active
    target.save(update_fields=['is_active'])
    logger.info('platform user active=%s user=%s by_user=%s',
                is_active, target.pk, request.user.pk)
    return Response({'id': target.pk, 'username': target.username, 'is_active': target.is_active})
