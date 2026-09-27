"""واجهات إدارة المنصة — عالمية ومحروسة بالسوبر أدمن فقط."""
import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Max, Q, Sum, Value, When
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication
from hr.authentication import DeviceTokenAuthentication as TokenAuthentication
from rest_framework.decorators import (
    action, api_view, authentication_classes, permission_classes,
)
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.routers import APIRootView, DefaultRouter

from accounting.models import AccountingAuditLog
from core.activity import log_activity
from core.import_access import is_super_admin, super_admin_emails
from core.models import (
    ActivityLog, DevelopmentNote, DevelopmentNoteComment, PlanPricing,
    TenantAsset, TenantLimit, TenantModule,
)
from core.modules import MODULES, invalidate_module_cache
from core.platform_audit import record_platform_event
from core.plans import (
    LIMITS, PLAN_LABELS, PLAN_PRICING_DEFAULTS, bulk_overrides, bulk_usage,
    invalidate_limit_cache, invalidate_plan_pricing_cache, limit_rows,
    limit_value, near_limit_rows, plan_default, plan_pricing_overrides,
    subscription_expiry, trial_end_date,
)
from tenants.models import Branch, Tenant, UserCompanyMembership


logger = logging.getLogger(__name__)
User = get_user_model()


class IsPlatformAdmin(BasePermission):
    message = 'هذه المساحة متاحة لسوبر أدمن المنصة فقط.'

    def has_permission(self, request, view):
        return is_super_admin(request.user)


class PlatformAPIRootView(APIRootView):
    """جذر راوتر المنصة — محروسٌ كبقية مساراته.

    الجذر الافتراضي يرث صلاحيات الإعدادات (`IsAuthenticated`)، فيسرد لأي مستخدم
    مسجَّل خريطةَ نقاط لوحة المنصة. لا بيانات شركات فيه، لكن **كل** ما تحت
    `/api/platform/` يجب أن يردّ 403 لغير السوبر أدمن بلا استثناء يُتذكَّر.
    """

    permission_classes = [IsPlatformAdmin]


class PlatformRouter(DefaultRouter):
    APIRootView = PlatformAPIRootView


MAX_NOTE_IMAGES = 10


def _user_display_name(user):
    if user is None:
        return ''
    return (f'{user.first_name} {user.last_name}').strip() or user.username


class DevelopmentNoteCommentSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DevelopmentNoteComment
        fields = ['id', 'body', 'created_by', 'created_by_name', 'created_at']
        read_only_fields = ['id', 'created_by', 'created_by_name', 'created_at']

    def validate_body(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('نص الردّ مطلوب.')
        return value

    def get_created_by_name(self, obj):
        return _user_display_name(obj.created_by)


class DevelopmentNoteSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    comments = DevelopmentNoteCommentSerializer(many=True, read_only=True)

    class Meta:
        model = DevelopmentNote
        fields = [
            'id', 'title', 'description', 'status', 'priority', 'images',
            'due_date', 'completed_at', 'created_by', 'created_by_name',
            'updated_by', 'updated_by_name', 'created_at', 'updated_at',
            'comments',
        ]
        read_only_fields = [
            'id', 'completed_at', 'created_by', 'created_by_name', 'updated_by',
            'updated_by_name', 'created_at', 'updated_at', 'comments',
        ]

    def create(self, validated_data):
        if validated_data.get('status') == 'done':
            validated_data['completed_at'] = timezone.now()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # الختم يتبع **الانتقال** لا الحالة: حفظةٌ ثانية على ملاحظة مكتملة لا
        # تعيد ختمها، والخروج من `done` يمحو الختم فلا يبقى تاريخ إنجازٍ لشيء
        # لم يُنجَز.
        new_status = validated_data.get('status', instance.status)
        if new_status != instance.status:
            validated_data['completed_at'] = (
                timezone.now() if new_status == 'done' else None
            )
        return super().update(instance, validated_data)

    def validate_title(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('عنوان الملاحظة مطلوب.')
        return value

    def validate_images(self, value):
        """يقبل روابط http(s) فقط ويعيد {url,caption} نظيفة — لا مفاتيح إضافية.

        الرابط يُعرَض في `<img src>` فمنعُ أي مخطط آخر (javascript:/data:) شرطُ
        سلامة لا تجميل: الحقل JSON حرّ الشكل بلا هذا التحقق.
        """
        if not isinstance(value, list):
            raise serializers.ValidationError('الصور تُرسَل كقائمة [{url,caption}].')
        if len(value) > MAX_NOTE_IMAGES:
            raise serializers.ValidationError(f'أقصى عدد صور للملاحظة {MAX_NOTE_IMAGES}.')
        cleaned = []
        for entry in value:
            if not isinstance(entry, dict):
                raise serializers.ValidationError('كل صورة كائن فيه url.')
            url = str(entry.get('url') or '').strip()
            if not url.startswith(('http://', 'https://')):
                raise serializers.ValidationError('رابط الصورة يجب أن يبدأ بـ http:// أو https://.')
            cleaned.append({'url': url[:500], 'caption': str(entry.get('caption') or '').strip()[:200]})
        return cleaned

    def get_created_by_name(self, obj):
        return _user_display_name(obj.created_by)

    def get_updated_by_name(self, obj):
        return _user_display_name(obj.updated_by)


class DevelopmentNoteViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsPlatformAdmin]
    serializer_class = DevelopmentNoteSerializer
    # الأهمّ أولاً، والأقدم أولاً داخل الأولوية الواحدة، والمكتملة أخيراً —
    # والواجهة تعيد نفس الفرز محلياً بعد كل تغيير حالة. `created_at` مرساة
    # ثابتة لا يحرّكها تعديل، بخلاف المفتاحين السابقين: `position` (حُذف —
    # الواجهة كانت ترسل 0 لأول ملاحظة كل جلسة فتقفز للأعلى) و`-updated_at`
    # (كل حفظة كانت تُقفز الملاحظة فوق أخواتها).
    queryset = (
        DevelopmentNote.objects
        .select_related('created_by', 'updated_by')
        .prefetch_related('comments__created_by')
        .annotate(
            is_done=Case(
                When(status='done', then=Value(1)), default=Value(0),
                output_field=IntegerField(),
            ),
            priority_rank=Case(
                When(priority='high', then=Value(0)),
                When(priority='medium', then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ),
        )
        .order_by('is_done', 'priority_rank', 'created_at', 'id')
    )

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

    @action(detail=True, methods=['post'], url_path='comments')
    def comments(self, request, pk=None):
        """يضيف ردّاً على الملاحظة ويعيده وحده — لا إعادة تحميل للملاحظة كلها."""
        note = self.get_object()
        serializer = DevelopmentNoteCommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(note=note, created_by=request.user)
        logger.info(
            'platform development note comment added note=%s id=%s by_user=%s',
            note.id, comment.id, request.user.pk,
        )
        return Response(
            DevelopmentNoteCommentSerializer(comment).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True, methods=['delete'],
        url_path=r'comments/(?P<comment_id>[0-9]+)',
    )
    def comment_detail(self, request, pk=None, comment_id=None):
        """حذف ردّ — أي سوبر أدمن يحذف أي ردّ (لوحة داخلية لفريق واحد)."""
        note = self.get_object()
        comment = DevelopmentNoteComment.objects.filter(
            pk=comment_id, note=note).first()
        if comment is None:
            return Response(
                {'detail': 'الردّ غير موجود على هذه الملاحظة.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        comment.delete()
        logger.info(
            'platform development note comment deleted note=%s id=%s by_user=%s',
            note.id, comment_id, request.user.pk,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


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

    with transaction.atomic():
        target.is_superuser = True
        target.is_staff = True
        target.save(update_fields=['is_superuser', 'is_staff'])
        record_platform_event('SUPER_ADMIN_GRANTED', request=request, target_user=target)
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

    with transaction.atomic():
        target.is_superuser = False
        target.is_staff = False
        target.save(update_fields=['is_superuser', 'is_staff'])
        record_platform_event('SUPER_ADMIN_REVOKED', request=request, target_user=target)
    logger.info('platform super admin revoked user=%s by_user=%s', target.pk, request.user.pk)
    return Response(status=status.HTTP_204_NO_CONTENT)


def _plan_choices():
    """خطط الاشتراك بأسمائها من `PLAN_LABELS` — الواجهة لا تحمل نسخةً منها."""
    return [
        {'key': key, 'label': PLAN_LABELS.get(key, key)}
        for key, _ in Tenant.SUBSCRIPTION_PLANS
    ]


def _company_payload(tenant, member_count=None):
    # T-TRIAL: حالة الانتهاء محسوبة في الخادم لا في اللوحة — «كم بقي» قسمةُ
    # تواريخ، وإجراؤها في المتصفّح يجعلها تتبع ساعة جهاز السوبر أدمن ومنطقته.
    expiry = subscription_expiry(tenant)
    return {
        'id': tenant.TenantID,
        'name': tenant.CompanyName,
        'plan': tenant.SubscriptionPlan,
        'plan_label': PLAN_LABELS.get(tenant.SubscriptionPlan, tenant.SubscriptionPlan),
        'status': tenant.Status,
        'subscription_ends_at': expiry['ends_at'],
        'subscription_days_left': expiry['days_left'],
        'subscription_expired': expiry['expired'],
        'import_enabled': tenant.import_enabled,
        'is_example': tenant.is_example,
        'member_count': (
            member_count if member_count is not None
            else UserCompanyMembership.objects.filter(tenant=tenant).count()
        ),
        'created_at': tenant.CreatedAt,
    }


# «بلا نشاط» = لم يُسجَّل لها أي فعل (غير العرض) منذ هذه المدة — شركةٌ دفعت
# ولا تستعمل النظام هي أوّل من يُلغي اشتراكه، فظهورها بالاسم لا بالعدد وحده.
IDLE_COMPANY_DAYS = 30
TOP_STORAGE_COMPANIES = 5


def _last_timestamp_by_tenant(queryset):
    """{tenant_id: آخر طابع زمني} — استعلامٌ واحد مهما بلغ عدد الشركات."""
    return {
        row['tenant_id']: row['last']
        for row in (
            queryset.values('tenant_id').order_by().annotate(last=Max('timestamp'))
        )
    }


def _storage_by_tenant():
    """استهلاك التخزين المجمَّع من سجلّ البايتات: لكل شركة، وللمنصة، وغير المنسوب.

    استعلام واحد يخدم الثلاثة: مجموعة `tenant_id = NULL` هي «غير منسوب» (أصول
    المنصة ومكتب المحاسبة)، ومجموع المجموعات كلها هو إجمالي السجلّ. إجمالي
    Cloudinary نفسه **لا يُطلب هنا** — لا نداء خارجي على تحميل صفحة؛ الفارق
    الدقيق مع المزوّد يسكن في تقرير التخزين.
    """
    per_tenant, counts = {}, {}
    ledger_total = unattributed = 0
    rows = (
        TenantAsset.objects
        .values('tenant_id')
        .order_by()
        .annotate(total_bytes=Sum('bytes'), asset_count=Count('id'))
    )
    for row in rows:
        total = row['total_bytes'] or 0
        ledger_total += total
        if row['tenant_id'] is None:
            unattributed += total
            continue
        per_tenant[row['tenant_id']] = total
        counts[row['tenant_id']] = row['asset_count']
    return per_tenant, counts, ledger_total, unattributed


def _dashboard_kpis(company_rows, status_counts):
    """مؤشرات اللوحة — مشتقّة من الصفوف المحسوبة أعلاه، بصفر استعلام إضافي."""
    idle_before = timezone.now() - timedelta(days=IDLE_COMPANY_DAYS)
    idle = [
        row for row in company_rows
        if row['last_activity_at'] is None or row['last_activity_at'] < idle_before
    ]
    near = [row for row in company_rows if row['near_limit']]
    top_storage = sorted(
        (row for row in company_rows if row['storage_bytes']),
        key=lambda row: row['storage_bytes'],
        reverse=True,
    )[:TOP_STORAGE_COMPANIES]
    return {
        'active_companies': status_counts.get('Active', 0),
        'idle_companies': {
            'days': IDLE_COMPANY_DAYS,
            'count': len(idle),
            'companies': [
                {
                    'id': row['id'],
                    'name': row['name'],
                    'last_activity_at': row['last_activity_at'],
                }
                for row in idle
            ],
        },
        'top_storage': [
            {
                'id': row['id'],
                'name': row['name'],
                'storage_bytes': row['storage_bytes'],
                'storage_asset_count': row['storage_asset_count'],
            }
            for row in top_storage
        ],
        'near_limit_companies': {
            'count': len(near),
            # `near_limit` مرتَّب بالأقرب إلى حدّه أولاً، فأوّل عنصر هو أسوأ حدّ.
            'companies': [
                {'id': row['id'], 'name': row['name'], **row['near_limit'][0]}
                for row in near
            ],
        },
    }


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_dashboard(request):
    """مؤشرات تشغيل المنصة بلا بيانات مالية داخلية للشركات.

    كل عمود في جدول الشركات يأتي من قاموسٍ مبنيّ باستعلامٍ مجمَّع واحد، فعدد
    الاستعلامات ثابت سواءٌ كانت الشركات خمساً أو خمسمئة. النداء الفردي
    (`limit_rows` / `current_usage` لكل شركة) هو ما يحوّل هذه الصفحة إلى مئات
    الاستعلامات، ويحرسه اختبارٌ يقارن جولة ٥ شركات بجولة ٥٠.
    """
    companies = list(
        Tenant.objects.annotate(member_count=Count('memberships')).order_by('-CreatedAt')
    )
    tenant_ids = [tenant.pk for tenant in companies]

    usage = bulk_usage(tenant_ids=tenant_ids)
    overrides = bulk_overrides(tenant_ids)
    storage_bytes, storage_counts, ledger_total_bytes, unattributed_bytes = (
        _storage_by_tenant()
    )
    last_login = _last_timestamp_by_tenant(ActivityLog.objects.filter(action='login'))
    last_activity = _last_timestamp_by_tenant(ActivityLog.objects.filter(is_view=False))

    company_rows = []
    for tenant in companies:
        tenant_usage = {key: counts.get(tenant.pk, 0) for key, counts in usage.items()}
        company_rows.append({
            **_company_payload(tenant, tenant.member_count),
            'branch_count': tenant_usage['company.branches'],
            'storage_bytes': storage_bytes.get(tenant.pk, 0),
            'storage_asset_count': storage_counts.get(tenant.pk, 0),
            # نافذة المستندات هي نافذة الحدّ نفسها (الشهر الجاري بـ`created_at`):
            # عمودٌ يقيس شيئاً وحدٌّ يقيس آخر يجعل «قريب من الحدّ» غير مفهوم.
            'document_count': tenant_usage['documents.invoices'],
            'last_login_at': last_login.get(tenant.pk),
            'last_activity_at': last_activity.get(tenant.pk),
            'near_limit': near_limit_rows(
                tenant.SubscriptionPlan, overrides.get(tenant.pk, {}), tenant_usage,
            ),
        })

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
        'plan_choices': _plan_choices(),
        'kpis': _dashboard_kpis(company_rows, status_counts),
        'storage': {
            'ledger_total_bytes': ledger_total_bytes,
            'unattributed_bytes': unattributed_bytes,
        },
    })


# ── تحكم السوبر أدمن بالشركات وأعضائها ──
# السوبر أدمن يدير أي شركة دون أن يكون عضواً فيها؛ مسارات tenants تبقى للمدير
# داخل شركته (require_perm)، وهذه المسارات محروسة بـ IsPlatformAdmin وحده.

_BOOL_FIELD = serializers.BooleanField()


class TenantModuleToggleSerializer(serializers.Serializer):
    module_key = serializers.ChoiceField(choices=tuple(MODULES))
    enabled = serializers.BooleanField()
    plan_note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=120,
        trim_whitespace=True,
    )


def _module_rows(tenant):
    """حالة كل وحدة لهذه الشركة — استعلام واحد لسجل الوحدات، والقديمة من عَلَمها."""
    stored = {
        row.module_key: row
        for row in TenantModule.objects.filter(tenant=tenant)
    }
    rows = []
    for key, definition in MODULES.items():
        legacy_flag = definition['legacy_flag']
        row = stored.get(key)
        rows.append({
            'module_key': key,
            'label': definition['label'],
            'plans': list(definition['plans']),
            # هل تشمل خطةُ الشركة هذه الوحدةَ؟ الترخيص يبقى قراراً صريحاً للسوبر
            # أدمن (تغيير الخطة لا يُطفئ وحدة عاملة بصمت)، لكن اللوحة تُظهر
            # التعارض بدل أن يبقى مخفياً في جدول الأسعار.
            'plan_allows': tenant.SubscriptionPlan in definition['plans'],
            'legacy': bool(legacy_flag),
            'enabled': (
                bool(getattr(tenant, legacy_flag, False)) if legacy_flag
                else bool(row and row.enabled)
            ),
            'plan_note': row.plan_note if row else '',
            'enabled_at': row.enabled_at if row else None,
        })
    return rows


@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_company_modules(request, pk):
    """اقرأ حالة وحدات الشركة (GET) أو فعّل/عطّل وحدة (POST) بتدقيق مالي وتشغيلي."""
    if request.method == 'GET':
        tenant = Tenant.objects.filter(pk=pk).first()
        if tenant is None:
            return Response(
                {'detail': 'الشركة غير موجودة.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({'results': _module_rows(tenant)})

    serializer = TenantModuleToggleSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    module_key = serializer.validated_data['module_key']
    enabled = serializer.validated_data['enabled']
    plan_note = serializer.validated_data['plan_note']

    with transaction.atomic():
        tenant = Tenant.objects.select_for_update().filter(pk=pk).first()
        if tenant is None:
            return Response(
                {'detail': 'الشركة غير موجودة.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        definition = MODULES[module_key]
        legacy_flag = definition['legacy_flag']
        if legacy_flag:
            previous = bool(getattr(tenant, legacy_flag, False))
            setattr(tenant, legacy_flag, enabled)
            tenant.save(update_fields=[legacy_flag])
            audit_model_name = 'Tenant'
            audit_object_id = tenant.pk
            entity_id = tenant.pk
        else:
            row, _ = TenantModule.objects.select_for_update().get_or_create(
                tenant=tenant,
                module_key=module_key,
            )
            previous = row.enabled
            row.enabled = enabled
            row.enabled_by = request.user
            row.enabled_at = timezone.now() if enabled else None
            row.plan_note = plan_note
            row.save(update_fields=[
                'enabled', 'enabled_by', 'enabled_at', 'plan_note',
            ])
            audit_model_name = 'TenantModule'
            audit_object_id = row.pk
            entity_id = row.pk

        AccountingAuditLog.objects.create(
            tenant=tenant,
            user=request.user,
            action='MODULE_TOGGLED',
            model_name=audit_model_name,
            object_id=audit_object_id,
            change_details=(
                f'module={module_key}; enabled={str(enabled).lower()}'
            ),
        )
        log_activity(
            action='update',
            entity_type='tenant_module',
            entity_id=entity_id,
            entity_label=definition['label'],
            description='تم تحديث ترخيص وحدة للشركة.',
            metadata={
                'event_code': 'MODULE_TOGGLED',
                'module': module_key,
                'previous_enabled': previous,
                'enabled': enabled,
            },
            request=request,
            tenant=tenant,
            user=request.user,
        )
        record_platform_event(
            'MODULE_TOGGLED', request=request, tenant=tenant, reason=plan_note,
            metadata={'module': module_key, 'previous_enabled': previous, 'enabled': enabled},
        )
        transaction.on_commit(
            lambda tenant_id=tenant.pk: invalidate_module_cache(
                tenant_id,
                request=request,
            )
        )

    return Response({
        'module_key': module_key,
        'enabled': enabled,
        'plan_note': plan_note,
    })


class TenantLimitWriteSerializer(serializers.Serializer):
    """ضبط حدّ لشركة: قيمة، أو «بلا حدّ» (null)، أو استعادة افتراضي الخطة."""

    limit_key = serializers.ChoiceField(choices=tuple(LIMITS))
    # ثلاث حالات مقصودة: رقم = حدّ صريح، null = بلا حدّ لهذه الشركة،
    # و`reset=true` = احذف التجاوز فتعود الشركة لافتراضي خطتها.
    max_value = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=1_000_000,
    )
    reset = serializers.BooleanField(required=False, default=False)
    note = serializers.CharField(
        required=False, allow_blank=True, default='', max_length=120,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        if not attrs.get('reset') and 'max_value' not in attrs:
            raise serializers.ValidationError({
                'max_value': 'أرسل قيمة الحدّ، أو null لبلا حدّ، أو reset=true للعودة لافتراضي الخطة.',
            })
        return attrs


@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_company_limits(request, pk):
    """حدود خطة الشركة: قراءتها مع الاستهلاك (GET)، وضبط/استعادة حدّ (POST)."""
    tenant = Tenant.objects.filter(pk=pk).first()
    if tenant is None:
        return Response({'detail': 'الشركة غير موجودة.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response({'plan': tenant.SubscriptionPlan, 'results': limit_rows(tenant)})

    serializer = TenantLimitWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    limit_key = serializer.validated_data['limit_key']
    reset = serializer.validated_data['reset']
    note = serializer.validated_data['note']
    # الحدّ الفعّال **قبل** الكتابة — بعدها يضيع الفرق: صفّ التجاوز يُحذف أو
    # يُستبدل، ولا يبقى في السجل ما يقول من أي قيمة تحرّك.
    previous_limit = limit_value(tenant, limit_key)

    with transaction.atomic():
        if reset:
            TenantLimit.objects.filter(tenant=tenant, limit_key=limit_key).delete()
            new_value = plan_default(tenant.SubscriptionPlan, limit_key)
        else:
            new_value = serializer.validated_data['max_value']
            TenantLimit.objects.update_or_create(
                tenant=tenant,
                limit_key=limit_key,
                defaults={
                    'max_value': new_value,
                    'note': note,
                    'updated_by': request.user,
                },
            )
        AccountingAuditLog.objects.create(
            tenant=tenant,
            user=request.user,
            action='LIMIT_CHANGED',
            model_name='TenantLimit',
            object_id=tenant.pk,
            change_details=(
                f'limit={limit_key}; value={"plan_default" if reset else new_value}'
            ),
        )
        log_activity(
            action='update',
            entity_type='tenant_limit',
            entity_id=tenant.pk,
            entity_label=LIMITS[limit_key].label,
            description='تم تعديل حدّ من حدود خطة الشركة.',
            metadata={
                'event_code': 'LIMIT_CHANGED',
                'limit': limit_key,
                'previous_limit': previous_limit,
                'new_limit': new_value,
                'reset': reset,
            },
            request=request,
            tenant=tenant,
            user=request.user,
        )
        record_platform_event(
            'LIMIT_CHANGED', request=request, tenant=tenant, reason=note,
            metadata={
                'limit': limit_key, 'previous_limit': previous_limit,
                'new_limit': new_value, 'reset': reset,
            },
        )
        transaction.on_commit(
            lambda tenant_id=tenant.pk: invalidate_limit_cache(tenant_id)
        )

    logger.info(
        'platform limit set tenant=%s key=%s reset=%s value=%s by_user=%s',
        tenant.pk, limit_key, reset, new_value, request.user.pk,
    )
    return Response({'plan': tenant.SubscriptionPlan, 'results': limit_rows(tenant)})


class PlanPricingWriteSerializer(serializers.Serializer):
    """ضبط سعر خطة: قيمةٌ صريحة، أو مساواتها بالافتراض فتُحذف كتجاوز."""

    plan_key = serializers.ChoiceField(choices=tuple(PLAN_PRICING_DEFAULTS))
    monthly_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0,
    )
    note = serializers.CharField(
        required=False, allow_blank=True, default='', max_length=120,
        trim_whitespace=True,
    )


def _plan_pricing_rows():
    """صفٌّ لكل خطةٍ معروضة: الافتراضي والتجاوز والسعر الفعّال — للوحة المنصة."""
    overrides = plan_pricing_overrides()
    rows = []
    for plan_key, default_price in PLAN_PRICING_DEFAULTS.items():
        has_override = plan_key in overrides
        rows.append({
            'plan_key': plan_key,
            'label': PLAN_LABELS.get(plan_key, plan_key),
            'default_price': default_price,
            'override': overrides.get(plan_key) if has_override else None,
            'has_override': has_override,
            'effective_price': overrides[plan_key] if has_override else default_price,
        })
    return rows


def _plan_pricing_effective(plan_key):
    overrides = plan_pricing_overrides()
    return overrides.get(plan_key, PLAN_PRICING_DEFAULTS[plan_key])


@api_view(['GET', 'PUT'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_plan_pricing(request):
    """أسعار الخطط: قراءتها مع الافتراض والتجاوز (GET)، وضبط/استعادة سعر (PUT).

    لا شركة هنا — السعر يخصّ الخطة كلها، فلا `ActivityLog`/`AccountingAuditLog`
    (كلاهما يلزمه `tenant`)؛ الأثر في `PlatformAuditLog` بلا شركة، كمنح السوبر أدمن.
    """
    if request.method == 'GET':
        return Response({'results': _plan_pricing_rows()})

    serializer = PlanPricingWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    plan_key = serializer.validated_data['plan_key']
    monthly_price = serializer.validated_data['monthly_price']
    note = serializer.validated_data['note']
    default_price = PLAN_PRICING_DEFAULTS[plan_key]
    previous_price = _plan_pricing_effective(plan_key)

    with transaction.atomic():
        if monthly_price == default_price:
            # مساواة السعر بالافتراض = استعادة — حذف الصف لا كتابة نسخة منه،
            # وإلا تجمّد السعر عند قيمة قديمة حين يتغيّر افتراض الكود لاحقاً.
            PlanPricing.objects.filter(plan_key=plan_key).delete()
            new_price = default_price
        else:
            PlanPricing.objects.update_or_create(
                plan_key=plan_key,
                defaults={
                    'monthly_price': monthly_price,
                    'note': note,
                    'updated_by': request.user,
                },
            )
            new_price = monthly_price
        record_platform_event(
            'PLAN_PRICE_CHANGED', request=request, reason=note,
            metadata={
                'plan': plan_key, 'previous_price': str(previous_price),
                'new_price': str(new_price),
            },
        )
        transaction.on_commit(invalidate_plan_pricing_cache)

    logger.info(
        'platform plan price set plan=%s value=%s by_user=%s',
        plan_key, new_price, request.user.pk,
    )
    return Response({'results': _plan_pricing_rows()})


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
    # الدور الخارجي لا يُنشأ أو يُحوّل من إدارة الأعضاء العامة؛ مصدره الوحيد
    # دورة AccountantEngagement التي تضمن وجود علاقة نشطة ونطاقاً صالحاً.
    return {
        role for role, _ in UserCompanyMembership.ROLE_CHOICES
        if role != 'legal_accountant'
    }


def _accountant_profile_payload(profile):
    return {
        'id': profile.pk,
        'user_id': profile.user_id,
        'full_name': profile.user.get_full_name() or profile.user.username,
        'email': profile.user.email,
        'professional_type': profile.professional_type,
        'license_number': profile.license_number,
        'license_authority': profile.license_authority,
        'tax_registration_number': profile.tax_registration_number,
        'business_address': profile.business_address,
        'phone': profile.phone,
        'email_verified': profile.email_verified_at is not None,
        'verification_status': profile.verification_status,
        'rejection_reason': profile.rejection_reason,
        'barred_until': profile.barred_until,
        'created_at': profile.created_at,
    }


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_accountants_pending(request):
    from accountant_portal.models import AccountantProfile

    profiles = (
        AccountantProfile.objects
        .filter(verification_status='pending_review')
        .select_related('user')
        .order_by('created_at')
    )
    return Response({
        'results': [_accountant_profile_payload(profile) for profile in profiles],
        'count': profiles.count(),
    })


@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_accountant_verify(request, profile_id):
    from accountant_portal.models import AccountantProfile

    profile = AccountantProfile.objects.select_related('user').filter(pk=profile_id).first()
    if profile is None:
        return Response({'detail': 'ملف المحاسب غير موجود.'}, status=status.HTTP_404_NOT_FOUND)
    raw_decision = str(request.data.get('decision') or '').strip().lower()
    decisions = {
        'approve': 'verified',
        'approved': 'verified',
        'verified': 'verified',
        'reject': 'rejected',
        'rejected': 'rejected',
        'bar': 'barred',
        'barred': 'barred',
    }
    decision = decisions.get(raw_decision)
    if decision is None:
        return Response(
            {'decision': 'القرار يجب أن يكون verified أو rejected أو barred.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    reason = str(request.data.get('reason') or '').strip()
    if decision in {'rejected', 'barred'} and not reason:
        return Response({'reason': 'سبب القرار مطلوب.'}, status=status.HTTP_400_BAD_REQUEST)

    profile.verification_status = decision
    profile.verified_by = request.user
    profile.verified_at = timezone.now()
    profile.rejection_reason = '' if decision == 'verified' else reason[:2000]
    with transaction.atomic():
        profile.save(update_fields=[
            'verification_status', 'verified_by', 'verified_at',
            'rejection_reason', 'updated_at',
        ])
        record_platform_event(
            'ACCOUNTANT_VERIFIED', request=request, target_user=profile.user,
            reason=reason, metadata={'profile_id': profile.pk, 'decision': decision},
            severity='warning' if decision == 'barred' else None,
        )
    logger.info(
        'platform accountant verification profile=%s decision=%s by_user=%s',
        profile.pk,
        decision,
        request.user.pk,
    )
    return Response(_accountant_profile_payload(profile))


ACCOUNTANT_OFFICE_NAME = 'مكتب المحاسبة القانونية (تجريبي)'


@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_accountant_workspace(request):
    """يفتح لسوبر أدمن المنصة واجهةَ المحاسب القانوني كاملةً بضغطة واحدة.

    ينشئ (أو يعيد) ثلاثة أشياء متلازمة: ملفاً مهنياً موثَّقاً لحسابه، ومكتبَ
    محاسبة (Tenant هو مديره كما في §16 — بلا وحدة فوترة جديدة)، وترخيصَ الوحدة
    على المكتب. بعدها يظهر له قائمة المحاسب ويستطيع إرسال طلب ارتباط لأي شركة.
    """
    from accountant_portal.models import AccountantProfile
    from core.modules import invalidate_module_cache
    from tenants.services import create_company

    with transaction.atomic():
        profile, profile_created = AccountantProfile.objects.get_or_create(
            user=request.user,
            defaults={
                'professional_type': 'licensed_auditor',
                'tax_registration_number': f'DEMO-{request.user.pk}',
                'business_address': 'عنوان تجريبي — عدّله من الملف المهني',
                'email_verified_at': timezone.now(),
                'verification_status': 'verified',
                'verified_by': request.user,
                'verified_at': timezone.now(),
            },
        )
        if not profile_created and (
            profile.email_verified_at is None or profile.verification_status != 'verified'
        ):
            profile.email_verified_at = profile.email_verified_at or timezone.now()
            profile.verification_status = 'verified'
            profile.verified_by = request.user
            profile.verified_at = timezone.now()
            profile.save(update_fields=[
                'email_verified_at', 'verification_status', 'verified_by',
                'verified_at', 'updated_at',
            ])

        office = (
            Tenant.objects
            .filter(
                CompanyName=ACCOUNTANT_OFFICE_NAME,
                memberships__user=request.user,
                memberships__role='manager',
            )
            .first()
        )
        office_created = office is None
        if office_created:
            office = create_company(ACCOUNTANT_OFFICE_NAME, request.user)

        module_row, _ = TenantModule.objects.get_or_create(
            tenant=office,
            module_key='accountant_portal',
        )
        if not module_row.enabled:
            module_row.enabled = True
            module_row.enabled_by = request.user
            module_row.enabled_at = timezone.now()
            module_row.plan_note = 'واجهة تجريبية لسوبر أدمن'
            module_row.save(update_fields=[
                'enabled', 'enabled_by', 'enabled_at', 'plan_note',
            ])
            AccountingAuditLog.objects.create(
                tenant=office,
                user=request.user,
                action='MODULE_TOGGLED',
                model_name='TenantModule',
                object_id=module_row.pk,
                change_details='module=accountant_portal; enabled=true',
            )
        record_platform_event(
            'ACCOUNTANT_WORKSPACE_OPENED', request=request, tenant=office,
            metadata={'profile_created': profile_created, 'office_created': office_created},
        )
        transaction.on_commit(
            lambda tenant_id=office.pk: invalidate_module_cache(tenant_id, request=request)
        )

    logger.info(
        'platform accountant workspace opened user=%s office=%s profile_created=%s',
        request.user.pk, office.pk, profile_created,
    )
    return Response({
        'profile': _accountant_profile_payload(profile),
        'office': {'tenant_id': office.pk, 'name': office.CompanyName},
        'profile_created': profile_created,
        'office_created': office_created,
    })


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
        # T-TRIAL: تحويلٌ إلى الخطة التجريبية بلا تاريخ = تجربةٌ بلا نهاية، وهي
        # الحالة التي وُجد هذا الحقل ليمنعها. يُملأ الافتراضي هنا لا في النموذج:
        # الافتراضي على مستوى العمود كان سيمنح **كل** شركة قائمة تاريخ انتهاء.
        # ولا يُلمس تاريخٌ موجود — تمديدُ تجربةٍ يمرّ بحقل التاريخ صراحةً.
        if plan == 'Trial' and tenant.subscription_ends_at is None:
            tenant.subscription_ends_at = trial_end_date()
            changed.append('subscription_ends_at')
    if 'subscription_ends_at' in data:
        raw = data.get('subscription_ends_at')
        if raw in (None, '', 'null'):
            tenant.subscription_ends_at = None  # اشتراك بلا انتهاء
        else:
            parsed = parse_date(str(raw).strip())
            if parsed is None:
                raise serializers.ValidationError(
                    {'subscription_ends_at': 'تاريخ غير صالح — الصيغة YYYY-MM-DD.'})
            tenant.subscription_ends_at = parsed
        if 'subscription_ends_at' not in changed:
            changed.append('subscription_ends_at')
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


# حدثٌ في سجل الشركة لكل قرار إداري يغيّر ما تدفعه أو ما تراه: تغيير الخطة
# وإيقاف الشركة يظهران في اللوحة نفسها كأي حدث آخر، فلا يبقى فعل السوبر أدمن
# وحده خارج الحكاية. الاسم و`import_enabled` لا حدث لهما — تصحيحٌ إداري لا يغيّر
# ما للشركة من حقوق.
_COMPANY_EVENT_FIELDS = {
    'SubscriptionPlan': ('PLAN_CHANGED', 'خطة الاشتراك', 'تم تغيير خطة اشتراك الشركة.'),
    'Status': ('STATUS_CHANGED', 'حالة الشركة', 'تم تغيير حالة الشركة.'),
    'subscription_ends_at': (
        'SUBSCRIPTION_END_CHANGED', 'تاريخ انتهاء الاشتراك',
        'تم تغيير تاريخ انتهاء اشتراك الشركة.',
    ),
}


# رمز حدث الشركة ← رمزه في سجلّ تدقيق المنصة (الحالة والخطة لهما فلترٌ خاص).
_PLATFORM_COMPANY_EVENTS = {
    'PLAN_CHANGED': 'COMPANY_PLAN_CHANGED',
    'STATUS_CHANGED': 'COMPANY_STATUS_CHANGED',
    'SUBSCRIPTION_END_CHANGED': 'COMPANY_UPDATED',
}


def _json_safe(value):
    """التاريخ نصّاً قبل أن يدخل `metadata` — JSONField لا يسلسل `date`."""
    return value.isoformat() if isinstance(value, date) else value


def _log_company_changes(request, tenant, changed, previous):
    """يسجّل حدثاً لكل حقلٍ ذي أثر **تغيّرت** قيمته فعلاً — لا حدث لحفظةٍ بلا فرق."""
    for field, (event_code, label, description) in _COMPANY_EVENT_FIELDS.items():
        if field not in changed:
            continue
        new_value = getattr(tenant, field)
        if new_value == previous[field]:
            continue
        log_activity(
            action='update',
            entity_type='tenant',
            entity_id=tenant.pk,
            entity_label=label,
            description=description,
            metadata={
                'event_code': event_code,
                'field': field,
                'previous': _json_safe(previous[field]),
                'new': _json_safe(new_value),
            },
            request=request,
            tenant=tenant,
            user=request.user,
        )
        record_platform_event(
            _PLATFORM_COMPANY_EVENTS[event_code], request=request, tenant=tenant,
            metadata={
                'field': field,
                'previous': _json_safe(previous[field]),
                'new': _json_safe(new_value),
            },
        )


def _company_activity_extras(tenant):
    """فروع الشركة وتخزينها وآخر نشاطها — ثلاثة استعلامات مقيّدة لشركة واحدة."""
    branches = list(
        Branch.objects
        .filter(tenant=tenant)
        .order_by('-is_main', 'name')
        .values('id', 'name', 'code')
    )
    storage_bytes = (
        TenantAsset.objects.filter(tenant=tenant).aggregate(total=Sum('bytes'))['total']
        or 0
    )
    last_activity_at = (
        ActivityLog.objects
        .filter(tenant=tenant, is_view=False)
        .aggregate(last=Max('timestamp'))['last']
    )
    return {
        'branches': branches,
        'storage_bytes': storage_bytes,
        'last_activity_at': last_activity_at,
    }


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
            previous = {
                field: getattr(tenant, field) for field in _COMPANY_EVENT_FIELDS
            }
            changed = _apply_company_changes(tenant, request.data)
            if changed:
                tenant.save(update_fields=changed)
                _log_company_changes(request, tenant, changed, previous)
            if 'is_example' in request.data:
                from tenants.services import set_example_company

                requested = _BOOL_FIELD.to_internal_value(request.data.get('is_example'))
                if requested:
                    set_example_company(tenant)
                elif tenant.is_example:
                    set_example_company(None)
                    tenant.is_example = False
                changed.append('is_example')
                record_platform_event(
                    'COMPANY_UPDATED', request=request, tenant=tenant,
                    metadata={'field': 'is_example', 'new': bool(requested)},
                )
            if changed:
                logger.info('platform company updated tenant=%s fields=%s by_user=%s',
                            tenant.pk, ','.join(changed), request.user.pk)
        return Response(_company_payload(tenant))

    return Response({
        **_company_payload(tenant),
        **_company_activity_extras(tenant),
        'members': _member_rows(tenant),
        'plan_choices': _plan_choices(),
    })


# آخر مئة حدث تكفي لقراءة «ماذا يجري في هذه الشركة» بلا ترقيم صفحات ولا حِمل:
# السجل الكامل للشركة مكانه صفحة النشاط داخلها، لا كرتُ اللوحة.
COMPANY_ACTIVITY_LIMIT = 100


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_company_activity(request, pk):
    """آخر أحداث الشركة كما تراها لوحة المنصة — أحداث العرض مستبعدة.

    `is_view=True` هو فتحُ مستندٍ لا فعلٌ عليه؛ تركُه هنا يُغرق آخر مئة حدث بفتحٍ
    وتصفّح فيختفي القرار الإداري الذي جاء القارئ يبحث عنه.
    """
    tenant = Tenant.objects.filter(pk=pk).first()
    if tenant is None:
        return Response({'detail': 'الشركة غير موجودة.'}, status=status.HTTP_404_NOT_FOUND)

    rows = (
        ActivityLog.objects
        .filter(tenant=tenant, is_view=False)
        .select_related('user')
        .order_by('-timestamp', '-id')[:COMPANY_ACTIVITY_LIMIT]
    )
    return Response({'results': [
        {
            'timestamp': row.timestamp,
            'user_name': _user_display_name(row.user) or '—',
            'action': row.action,
            'action_label': row.get_action_display(),
            'entity_type': row.entity_type,
            'entity_label': row.entity_label,
            'description': row.description,
        }
        for row in rows
    ]})


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
    with transaction.atomic():
        membership, created = UserCompanyMembership.objects.get_or_create(
            user=target, tenant=tenant, defaults={'role': role})
        if created:
            record_platform_event(
                'MEMBER_ADDED', request=request, tenant=tenant, target_user=target,
                metadata={'membership_id': membership.pk, 'role': role},
            )
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
        with transaction.atomic():
            record_platform_event(
                'MEMBER_REMOVED', request=request, tenant=tenant, target_user=membership.user,
                metadata={'membership_id': membership.pk, 'role': membership.role},
            )
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
        with transaction.atomic():
            membership.save(update_fields=changed)
            record_platform_event(
                'MEMBER_UPDATED', request=request, tenant=tenant, target_user=membership.user,
                metadata={
                    'membership_id': membership.pk,
                    **{field: getattr(membership, field) for field in changed},
                },
            )
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
    previous_active = target.is_active
    with transaction.atomic():
        target.is_active = is_active
        target.save(update_fields=['is_active'])
        record_platform_event(
            'USER_ACTIVE_CHANGED', request=request, target_user=target,
            metadata={'previous': previous_active, 'is_active': is_active},
        )
    logger.info('platform user active=%s user=%s by_user=%s',
                is_active, target.pk, request.user.pk)
    return Response({'id': target.pk, 'username': target.username, 'is_active': target.is_active})


PLATFORM_AUDIT_PAGE_SIZE = 50


def _platform_audit_row(entry):
    from core.platform_audit import event_label

    return {
        'id': entry.id,
        'action': entry.action,
        'action_label': event_label(entry.action),
        'severity': entry.severity,
        'actor_id': entry.actor_id,
        'actor': entry.actor_label,
        'tenant_id': entry.tenant_id,
        'tenant': entry.tenant_label,
        'target_user_id': entry.target_user_id,
        'target_user': entry.target_label,
        'reason': entry.reason,
        'metadata': entry.metadata,
        'ip_address': entry.ip_address,
        'trace_id': entry.trace_id,
        'created_at': entry.created_at,
    }


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_audit_log(request):
    """سجلّ تدقيق المنصة — قراءة فقط، مرقَّم، بفلاتر: شركة، حدث، خطورة، فاعل، تاريخ، بحث.

    `events` في الردّ هو كتالوج الأحداث وتسمياتها من `core.platform_audit`
    (مصدرٌ واحد للفلتر وللتسمية في الواجهة).
    """
    from core.models import PlatformAuditLog
    from core.platform_audit import PLATFORM_EVENTS

    params = request.query_params
    queryset = PlatformAuditLog.objects.all()
    for param, field in (('tenant', 'tenant_id'), ('actor', 'actor_id')):
        value = params.get(param)
        if value:
            if not str(value).isdigit():
                return Response({param: 'قيمة غير صالحة.'}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(**{field: int(value)})
    if params.get('action'):
        queryset = queryset.filter(action=params['action'])
    if params.get('severity'):
        queryset = queryset.filter(severity=params['severity'])
    for param, lookup in (('date_from', 'created_at__date__gte'), ('date_to', 'created_at__date__lte')):
        if params.get(param):
            try:
                parsed = parse_date(params[param])
            except ValueError:  # شكلٌ صحيح بقيمٍ مستحيلة (شهر 13)
                parsed = None
            if parsed is None:
                return Response({param: 'تاريخ غير صالح.'}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(**{lookup: parsed})
    search = (params.get('q') or '').strip()
    if search:
        queryset = queryset.filter(
            Q(actor_label__icontains=search) | Q(tenant_label__icontains=search)
            | Q(target_label__icontains=search) | Q(reason__icontains=search)
        )

    try:
        page = max(1, int(params.get('page') or 1))
    except ValueError:
        page = 1
    total = queryset.count()
    start = (page - 1) * PLATFORM_AUDIT_PAGE_SIZE
    rows = queryset[start:start + PLATFORM_AUDIT_PAGE_SIZE]
    return Response({
        'count': total,
        'page': page,
        'page_size': PLATFORM_AUDIT_PAGE_SIZE,
        'results': [_platform_audit_row(entry) for entry in rows],
        'events': [
            {'action': key, 'label': label, 'severity': severity}
            for key, (severity, label) in PLATFORM_EVENTS.items()
        ],
    })


def _support_access_response(fn, **kwargs):
    from core.models import SupportAccessGrant
    from core.support_access import SupportAccessError, grant_payload

    try:
        grant = fn(**kwargs)
    except SupportAccessGrant.DoesNotExist:
        return Response({'detail': 'الإذن غير موجود.'}, status=status.HTTP_404_NOT_FOUND)
    except SupportAccessError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(grant_payload(grant), status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_company_support_access(request, pk):
    """أذونات الدخول لشركة (GET)، وطلب إذن أو دخولٌ طارئ (POST) — SA-2.

    POST: {reason, scope: read_only|full, hours: 4|24|168} طلبٌ ينتظر موافقة الشركة،
    أو {reason, emergency: true} دخولٌ فوريّ لأربع ساعات تُبلَّغ به الشركة.
    """
    from core.models import SupportAccessGrant
    from core.support_access import emergency_access, grant_payload, request_access

    tenant = Tenant.objects.filter(pk=pk).first()
    if tenant is None:
        return Response({'detail': 'الشركة غير موجودة.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        grants = (
            SupportAccessGrant.objects.filter(tenant=tenant)
            .select_related('tenant', 'requested_by', 'decided_by', 'revoked_by')[:50]
        )
        return Response({'results': [grant_payload(grant) for grant in grants]})

    if _BOOL_FIELD.to_internal_value(request.data.get('emergency', False)):
        return _support_access_response(
            emergency_access, tenant=tenant, actor=request.user,
            reason=request.data.get('reason'), request=request,
        )
    return _support_access_response(
        request_access, tenant=tenant, actor=request.user,
        reason=request.data.get('reason'), scope=request.data.get('scope'),
        hours=request.data.get('hours'), request=request,
    )


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_support_access(request):
    """كل أذونات الدخول على المنصة — `?status=pending|active` لصفحة «طلبات الدخول»."""
    from core.models import SupportAccessGrant
    from core.support_access import PENDING_TTL, grant_payload

    now = timezone.now()
    queryset = SupportAccessGrant.objects.select_related(
        'tenant', 'requested_by', 'decided_by', 'revoked_by')
    wanted = request.query_params.get('status')
    if wanted == 'pending':
        queryset = queryset.filter(status='pending', created_at__gt=now - PENDING_TTL)
    elif wanted == 'active':
        queryset = queryset.filter(status='active', expires_at__gt=now)
    elif wanted:
        return Response({'status': 'القيمة: pending أو active.'}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'results': [grant_payload(grant, now) for grant in queryset[:100]]})


@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_support_access_end(request, grant_id):
    """إنهاء إذن ساري (خروج) أو إلغاء طلبٍ معلّق — قبل موعده."""
    from core.support_access import revoke

    response = _support_access_response(
        revoke, grant_id=grant_id, actor=request.user,
        note=request.data.get('note', ''), request=request,
    )
    if response.status_code == status.HTTP_201_CREATED:
        response.status_code = status.HTTP_200_OK
    return response


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_usage(request):
    """حجم استعمال كل الشركات (SA-3): حركات ومستندات (الكل وهذا الشهر) ومستخدمون نشطون.

    من الكاش عشر دقائق مع `computed_at`؛ `?refresh=1` يعيد الحساب الآن.
    """
    from core.usage import counter_catalog, platform_usage as compute_platform_usage

    refresh = str(request.query_params.get('refresh') or '').lower() in {'1', 'true'}
    payload = compute_platform_usage(refresh=refresh)
    names = dict(Tenant.objects.values_list('TenantID', 'CompanyName'))
    return Response({
        'computed_at': payload['computed_at'],
        'counter_catalog': counter_catalog(),
        'results': [
            {'tenant_id': tenant_id, 'name': names.get(tenant_id, ''), **row}
            for tenant_id, row in payload['rows'].items()
        ],
    })


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_company_usage(request, pk):
    """استعمال شركة واحدة محسوباً الآن — لصفحة الشركة (رخيصٌ لشركة واحدة)."""
    from core.usage import compute_usage, counter_catalog

    tenant = Tenant.objects.filter(pk=pk).first()
    if tenant is None:
        return Response({'detail': 'الشركة غير موجودة.'}, status=status.HTTP_404_NOT_FOUND)
    row = compute_usage([tenant.pk])[tenant.pk]
    return Response({
        'computed_at': timezone.now(),
        'counter_catalog': counter_catalog(),
        'tenant_id': tenant.pk,
        'name': tenant.CompanyName,
        **row,
    })


# ── SA-9: إنشاء شركة لعميل من اللوحة ─────────────────────────────────────────

# `client_book` خارج القائمة: دفتر العميل يولد من مكتب محاسبة (`managed_by`)
# عبر مساره، لا من لوحة المنصة بلا مكتب.
_CREATABLE_TEMPLATES = ('general', 'accounting_firm', 'tyres')
MAX_TRIAL_DAYS = 90


def _creation_options():
    from core.plans import TRIAL_PERIOD_DAYS
    from tenants.company_templates import COMPANY_TEMPLATES

    return {
        'templates': [
            {'key': key, 'label': COMPANY_TEMPLATES[key]['name']}
            for key in _CREATABLE_TEMPLATES if key in COMPANY_TEMPLATES
        ],
        'plans': _plan_choices(),
        'default_trial_days': TRIAL_PERIOD_DAYS,
        'max_trial_days': MAX_TRIAL_DAYS,
    }


def _creation_errors(data):
    """يتحقّق من طلب الإنشاء كاملاً قبل أي كتابة — يعيد (القيم، الأخطاء)."""
    errors = {}
    name = str(data.get('name') or '').strip()
    owner_email = str(data.get('owner_email') or '').strip().lower()
    template = str(data.get('template') or 'general').strip()
    plan = str(data.get('plan') or 'Trial').strip()
    if not name:
        errors['name'] = 'اسم الشركة مطلوب.'
    elif len(name) > Tenant._meta.get_field('CompanyName').max_length:
        errors['name'] = 'اسم الشركة أطول من المسموح.'
    if not owner_email:
        errors['owner_email'] = 'بريد مالك الشركة مطلوب.'
    if template not in _CREATABLE_TEMPLATES:
        errors['template'] = 'قالب غير متاح للإنشاء من اللوحة.'
    if plan not in {key for key, _ in Tenant.SUBSCRIPTION_PLANS}:
        errors['plan'] = 'خطة اشتراك غير معروفة.'

    ends_at = None
    if plan == 'Trial':
        raw_days = data.get('trial_days')
        if raw_days not in (None, ''):
            try:
                days = int(raw_days)
            except (TypeError, ValueError):
                days = 0
            if not 1 <= days <= MAX_TRIAL_DAYS:
                errors['trial_days'] = f'مدة التجربة بين يوم و{MAX_TRIAL_DAYS} يوماً.'
            else:
                ends_at = timezone.localdate() + timedelta(days=days)
    else:
        raw_end = data.get('subscription_ends_at')
        if raw_end not in (None, ''):
            ends_at = parse_date(str(raw_end).strip())
            if ends_at is None:
                errors['subscription_ends_at'] = 'تاريخ غير صالح — الصيغة YYYY-MM-DD.'
            elif ends_at <= timezone.localdate():
                errors['subscription_ends_at'] = 'تاريخ انتهاء الاشتراك يجب أن يكون بعد اليوم.'
    values = {
        'name': name, 'owner_email': owner_email, 'template': template,
        'plan': plan, 'ends_at': ends_at,
    }
    return values, errors


def _notify_new_company_owner(tenant, owner) -> None:
    """بريدٌ للمالك أن شركته جاهزة — best-effort: الشركة تظهر له عند دخوله أياً كان."""
    try:
        from django.conf import settings
        from django.core.mail import send_mail

        if not owner.email:
            return
        base = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
        link = base or 'موقع كترا'
        send_mail(
            f'شركتكم «{tenant.CompanyName}» جاهزة على كترا',
            (
                f'أنشأ فريق كترا شركة «{tenant.CompanyName}» على حسابكم ({owner.email}) '
                f'وأنتم مديرها.\nادخلوا بحسابكم المعتاد من:\n{link}'
            ),
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@localhost'),
            [owner.email],
        )
    except Exception:  # noqa: BLE001 — الإشعار لا يُسقط الإنشاء
        logger.exception('new company owner notification failed tenant=%s', tenant.pk)


@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_company_create(request):
    """SA-9 — شركة لعميل: GET خيارات النموذج، POST ينشئها.

    الإنشاء عبر `tenants.services.create_company` نفسها (زرع الدليل والدفاتر
    والفرع والمستودع والسنة المالية) والمالك مديرها — لا مسار زرعٍ ثانٍ.
    المالك **حسابٌ مسجَّل**: لا نظام دعوات عامّاً للحسابات في المنتج (دعوات
    `employee_ops` مقيّدة بموظف ميداني)، فبريدٌ بلا حساب يُرفض برمز
    `owner_not_registered` ليسجّل العميل أولاً — كقاعدة إضافة العضو نفسها.
    """
    from django.core.exceptions import ValidationError as DjangoValidationError
    from tenants.services import create_company

    if request.method == 'GET':
        return Response(_creation_options())

    values, errors = _creation_errors(request.data)
    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)
    owner = User.objects.filter(
        Q(email__iexact=values['owner_email']) | Q(username__iexact=values['owner_email'])
    ).first()
    if owner is None:
        return Response(
            {
                'code': 'owner_not_registered',
                'owner_email': 'لا حساب بهذا البريد بعد — اطلب من العميل إنشاء حساب من '
                               'صفحة كترا الرئيسية بهذا البريد، ثم أنشئ الشركة باسمه.',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not owner.is_active:
        return Response(
            {'owner_email': 'حساب هذا البريد موقوف — فعّله أولاً.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        with transaction.atomic():
            tenant = create_company(values['name'], owner, template=values['template'])
            changed = []
            if values['plan'] != 'Trial':
                tenant.SubscriptionPlan = values['plan']
                tenant.Status = 'Active'
                tenant.subscription_ends_at = values['ends_at']
                changed = ['SubscriptionPlan', 'Status', 'subscription_ends_at']
            elif values['ends_at'] is not None:
                tenant.subscription_ends_at = values['ends_at']
                changed = ['subscription_ends_at']
            if changed:
                tenant.save(update_fields=changed)
            metadata = {
                'template': values['template'],
                'plan': tenant.SubscriptionPlan,
                'subscription_ends_at': _json_safe(tenant.subscription_ends_at),
            }
            record_platform_event(
                'COMPANY_CREATED', request=request, tenant=tenant, target_user=owner,
                metadata=metadata,
            )
            log_activity(
                action='create', entity_type='tenant', entity_id=tenant.pk,
                entity_label=tenant.CompanyName,
                description='أنشأ فريق كترا الشركة وعيّن مالكها مديراً.',
                metadata={'event_code': 'COMPANY_CREATED', **metadata},
                request=request, tenant=tenant, user=request.user,
            )
            transaction.on_commit(lambda: _notify_new_company_owner(tenant, owner))
    except DjangoValidationError as exc:
        return Response({'detail': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

    logger.info('platform company created tenant=%s template=%s plan=%s owner=%s by_user=%s',
                tenant.pk, values['template'], tenant.SubscriptionPlan, owner.pk, request.user.pk)
    return Response(_company_payload(tenant, member_count=1), status=status.HTTP_201_CREATED)


# ── SA-9: صحة النظام ─────────────────────────────────────────────────────────

# نسخةٌ أقدم من هذا (بالساعات) تُعلَّم «متأخرة» — نسخٌ يومية + ساعتا هامش.
BACKUP_STALE_HOURS = 26


def _database_health():
    import time

    from django.db import connection

    started = time.monotonic()
    result = {'vendor': connection.vendor, 'ok': True, 'ping_ms': None,
              'size_bytes': None, 'largest_tables': []}
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
            result['ping_ms'] = round((time.monotonic() - started) * 1000, 1)
            if connection.vendor == 'mysql':
                cursor.execute(
                    'SELECT table_name, table_rows, data_length + index_length '
                    'FROM information_schema.tables WHERE table_schema = DATABASE() '
                    'ORDER BY data_length + index_length DESC'
                )
                rows = cursor.fetchall()
                result['size_bytes'] = sum(int(row[2] or 0) for row in rows)
                result['largest_tables'] = [
                    {'name': row[0], 'rows': int(row[1] or 0), 'bytes': int(row[2] or 0)}
                    for row in rows[:10]
                ]
            elif connection.vendor == 'sqlite':
                cursor.execute('PRAGMA page_count')
                pages = cursor.fetchone()[0]
                cursor.execute('PRAGMA page_size')
                result['size_bytes'] = int(pages) * int(cursor.fetchone()[0])
    except Exception:  # noqa: BLE001 — الصفحة تقول «تعذّر» ولا تسقط
        logger.exception('platform health database probe failed')
        result['ok'] = False
    return result


def _pending_migrations():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    try:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        return [f'{migration.app_label}.{migration.name}' for migration, _ in plan]
    except Exception:  # noqa: BLE001
        logger.exception('platform health migration probe failed')
        return None


def _cache_health():
    from django.conf import settings
    from django.core.cache import cache

    backend = settings.CACHES.get('default', {}).get('BACKEND', '').rsplit('.', 1)[-1]
    try:
        cache.set('platform_health_probe', 1, 10)
        return {'ok': cache.get('platform_health_probe') == 1, 'backend': backend}
    except Exception:  # noqa: BLE001
        logger.exception('platform health cache probe failed')
        return {'ok': False, 'backend': backend}


def _backup_health():
    """آخر نسخة احتياطية من مجلّد `KTRA_BACKUP_DIR` إن ضُبط — اسم الملف لا مساره."""
    import os
    from datetime import datetime

    from django.conf import settings

    directory = getattr(settings, 'KTRA_BACKUP_DIR', '') or os.environ.get('KTRA_BACKUP_DIR', '')
    if not directory:
        return {'configured': False}
    if not os.path.isdir(directory):
        return {'configured': True, 'readable': False}
    try:
        entries = [entry for entry in os.scandir(directory) if entry.is_file()]
    except OSError:
        logger.exception('platform health backup dir unreadable')
        return {'configured': True, 'readable': False}
    if not entries:
        return {'configured': True, 'readable': True, 'latest_file': None}
    latest = max(entries, key=lambda entry: entry.stat().st_mtime)
    stat = latest.stat()
    latest_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone())
    age_hours = round((timezone.now() - latest_at).total_seconds() / 3600, 1)
    return {
        'configured': True, 'readable': True,
        'latest_file': latest.name, 'latest_at': latest_at, 'latest_bytes': stat.st_size,
        'age_hours': age_hours, 'stale': age_hours > BACKUP_STALE_HOURS,
        'file_count': len(entries),
    }


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsPlatformAdmin])
def platform_health(request):
    """SA-9 — صحة النظام الأساسية: القاعدة، الهجرات، الكاش، النسخ الاحتياطي، التخزين،
    أثقل الشركات استعمالاً، ومحاولات الدخول الفاشلة. لا CPU/RAM لحظي (خارج النطاق).
    """
    import platform as py_platform

    import django
    from django.conf import settings

    from core.models import PlatformAuditLog
    from core.usage import platform_usage as compute_platform_usage

    per_tenant_storage, _, ledger_total, unattributed = _storage_by_tenant()
    usage = compute_platform_usage()
    names = dict(Tenant.objects.values_list('TenantID', 'CompanyName'))
    heaviest = sorted(
        usage['rows'].items(),
        key=lambda item: item[1]['movements_total'] + item[1]['documents_total'],
        reverse=True,
    )[:5]
    pending = _pending_migrations()
    return Response({
        'checked_at': timezone.now(),
        'database': _database_health(),
        'migrations': {'ok': pending == [], 'pending': pending or []},
        'cache': _cache_health(),
        'backup': _backup_health(),
        'storage': {'ledger_bytes': ledger_total, 'unattributed_bytes': unattributed},
        'heaviest_companies': [
            {
                'tenant_id': tenant_id, 'name': names.get(tenant_id, ''),
                'movements_total': row['movements_total'],
                'documents_total': row['documents_total'],
                'storage_bytes': per_tenant_storage.get(tenant_id, 0),
            }
            for tenant_id, row in heaviest
        ],
        'usage_computed_at': usage['computed_at'],
        'failed_logins_24h': PlatformAuditLog.objects.filter(
            action='LOGIN_FAILED', created_at__gte=timezone.now() - timedelta(hours=24),
        ).count(),
        'app': {
            'django': django.get_version(),
            'python': py_platform.python_version(),
            'debug': bool(settings.DEBUG),
            'timezone': settings.TIME_ZONE,
        },
    })
