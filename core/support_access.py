"""إذن دخول فريق كترا إلى شركة — SA-2 (`docs/plans/27-9-2026-super-admin-console.md` §3، §5).

سوبر أدمن المنصة كان يتجاوز شرط العضوية ويدخل أي شركة بصمت. الآن: من ليس عضواً
في الشركة لا يدخلها إلا بإذنٍ ساري **له هو** (`SupportAccessGrant`)، تمنحه الشركة
لمدةٍ محددة، أو بدخولٍ طارئ بسببٍ مكتوب تُبلَّغ به الشركة فوراً.

- «قراءة فقط» تُرفض فيها كل كتابة.
- وحتى الإذن الكامل لا يمنح: إدارة الأعضاء والأدوار والصلاحيات، ومفاتيح الربط
  الضريبي، والتصدير، ولا قرارات أذونات الدعم نفسها (`SUPPORT_FORBIDDEN_PERMS`،
  `SUPPORT_BLOCKED_PATH_PARTS`) — على نمط `LEGAL_ACCOUNTANT_FORBIDDEN`.
- كل طلب كتابةٍ تحت الإذن يُكتب في سجلّ نشاط الشركة موسوماً «دعم كترا»، وكل
  فعلٍ آخر يسجّله الكود (`log_activity`) يحمل رقم الإذن.

العضو يبقى عضواً: سوبر أدمن عضوٌ في شركته يدخلها كما كان، بلا إذن.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from core.models import SupportAccessGrant
from core.platform_audit import record_platform_event

logger = logging.getLogger(__name__)

DURATION_HOURS = (4, 24, 168)
DEFAULT_HOURS = 24
EMERGENCY_HOURS = 4
PENDING_TTL = timedelta(hours=72)

# ما لا يُمنح لفريق الدعم ولو بإذنٍ كامل (قرار المالك 3).
SUPPORT_FORBIDDEN_PERMS = frozenset({
    'admin.members.manage',
    'admin.permissions.manage',
    'tax.integration.manage',
    'finance.export.package',
})
# مسارات تُرفض بالكامل تحت الإذن — التصدير (قراءةً أيضاً) وقرارات الإذن نفسه:
# صاحب الإذن لا يوافق على إذنه ولا يمدّده من داخل الشركة.
SUPPORT_BLOCKED_PATH_PARTS = ('/export', '/api/support-access/')

SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})
SUPPORT_LABEL = 'دعم كترا'


class SupportAccessRequired(PermissionDenied):
    """لا إذن دخول ساري — الواجهة تلتقط الرمز فتعرض «اطلب إذناً»."""

    code = 'support_access_required'


class SupportAccessReadOnly(PermissionDenied):
    code = 'support_access_read_only'


class SupportAccessForbidden(PermissionDenied):
    code = 'support_access_forbidden'


class SupportAccessError(ValueError):
    """خطأ مدخلات/حالة في دورة الإذن — تُترجمه النقاط إلى 400."""


# ── القراءة ────────────────────────────────────────────────────────────────

def has_direct_access(user, tenant) -> bool:
    """عضويةٌ في الشركة، أو إدارةُ المكتب الذي يديرها — الطريقان العاديان."""
    from tenants.models import UserCompanyMembership

    if UserCompanyMembership.objects.filter(user=user, tenant=tenant).exists():
        return True
    office_id = getattr(tenant, 'managed_by_id', None)
    return office_id is not None and UserCompanyMembership.objects.filter(
        user=user, tenant_id=office_id, role='manager',
    ).exists()


def is_support_session(user, tenant) -> bool:
    """سوبر أدمن داخل شركة ليس له فيها طريقٌ عادي — أي داخلٌ بإذن دعم."""
    from core.import_access import is_super_admin

    if tenant is None or not is_super_admin(user):
        return False
    return not has_direct_access(user, tenant)


def is_support_forbidden(permission_key: str) -> bool:
    return permission_key in SUPPORT_FORBIDDEN_PERMS


def effective_status(grant, now=None) -> str:
    """الحالة كما يراها الناس: الساري بعد انقضائه «منتهٍ»، والمعلّق بعد مهلته «منتهٍ»."""
    now = now or timezone.now()
    if grant.status == SupportAccessGrant.STATUS_ACTIVE and grant.expires_at and grant.expires_at <= now:
        return 'expired'
    if grant.status == SupportAccessGrant.STATUS_PENDING and grant.created_at + PENDING_TTL <= now:
        return 'expired'
    return grant.status


def active_grant(user, tenant):
    now = timezone.now()
    return (
        SupportAccessGrant.objects
        .filter(
            tenant=tenant, requested_by=user,
            status=SupportAccessGrant.STATUS_ACTIVE, expires_at__gt=now,
        )
        .order_by('-expires_at')
        .first()
    )


# ── الإنفاذ ─────────────────────────────────────────────────────────────────

def enforce_support_access(request, tenant) -> None:
    """يُنادى من `_validate_user_tenant_access` لسوبر أدمن بلا طريقٍ عادي إلى الشركة."""
    user = request.user
    cached = getattr(request, '_support_grant', None)
    grant = cached if cached is not None and cached.tenant_id == tenant.pk else active_grant(user, tenant)
    if grant is None:
        logger.warning(
            'support_access_denied user=%s tenant=%s path=%s',
            user.pk, tenant.pk, getattr(request, 'path', '?'),
        )
        raise SupportAccessRequired(
            'لا يوجد إذن دخول ساري لك في هذه الشركة. اطلب إذناً من صفحة الشركة في لوحة المنصة.'
        )

    path = getattr(request, 'path', '') or ''
    if any(part in path for part in SUPPORT_BLOCKED_PATH_PARTS):
        raise SupportAccessForbidden('هذا المسار غير متاح لفريق الدعم.')
    method = (getattr(request, 'method', 'GET') or 'GET').upper()
    if method not in SAFE_METHODS and grant.scope != SupportAccessGrant.SCOPE_FULL:
        raise SupportAccessReadOnly('إذن الدعم في هذه الشركة قراءة فقط.')

    request._support_grant = grant
    _touch(request, grant, method, path)


def _touch(request, grant, method, path) -> None:
    """أول استعمال ← سجلّ المنصة؛ كل طلب كتابة ← سجلّ نشاط الشركة. مرة لكل طلب."""
    if getattr(request, '_support_touched', False):
        return
    request._support_touched = True
    now = timezone.now()
    updates = {'last_used_at': now}
    if grant.first_used_at is None:
        updates['first_used_at'] = now
        grant.first_used_at = now
        record_platform_event(
            'SUPPORT_ACCESS_USED', request=request, tenant=grant.tenant,
            metadata={'grant_id': grant.pk, 'scope': grant.scope, 'emergency': grant.is_emergency},
        )
    SupportAccessGrant.objects.filter(pk=grant.pk).update(**updates)
    if method not in SAFE_METHODS:
        from core.activity import log_activity

        log_activity(
            action={'POST': 'create', 'DELETE': 'delete'}.get(method, 'update'),
            entity_type='support_access',
            entity_id=grant.pk,
            entity_label=SUPPORT_LABEL,
            description=f'طلب من {SUPPORT_LABEL}: {method} {path}',
            metadata={'support_grant_id': grant.pk, 'method': method, 'path': path[:300]},
            request=request,
            tenant=grant.tenant,
            user=request.user,
        )


# ── الدورة ──────────────────────────────────────────────────────────────────

def _clean_reason(reason) -> str:
    reason = str(reason or '').strip()
    if len(reason) < 5:
        raise SupportAccessError('اكتب سبب الدخول (خمسة أحرف على الأقل).')
    return reason[:2000]


def _clean_scope(scope) -> str:
    scope = str(scope or SupportAccessGrant.SCOPE_READ_ONLY)
    if scope not in {SupportAccessGrant.SCOPE_READ_ONLY, SupportAccessGrant.SCOPE_FULL}:
        raise SupportAccessError('نطاق الإذن غير معروف.')
    return scope


def _clean_hours(hours) -> int:
    try:
        hours = int(hours or DEFAULT_HOURS)
    except (TypeError, ValueError):
        raise SupportAccessError('مدة الإذن غير صالحة.') from None
    if hours not in DURATION_HOURS:
        raise SupportAccessError('مدة الإذن: 4 ساعات أو 24 ساعة أو 7 أيام.')
    return hours


def _assert_outsider(tenant, actor):
    if has_direct_access(actor, tenant):
        raise SupportAccessError('أنت عضو في هذه الشركة — تدخلها مباشرةً بلا إذن.')


def request_access(*, tenant, actor, reason, scope=None, hours=None, request=None):
    _assert_outsider(tenant, actor)
    reason = _clean_reason(reason)
    scope = _clean_scope(scope)
    hours = _clean_hours(hours)
    with transaction.atomic():
        pending = SupportAccessGrant.objects.select_for_update().filter(
            tenant=tenant, requested_by=actor, status=SupportAccessGrant.STATUS_PENDING,
            created_at__gt=timezone.now() - PENDING_TTL,
        )
        if pending.exists():
            raise SupportAccessError('لديك طلب معلّق لهذه الشركة — انتظر ردّها أو ألغِه.')
        grant = SupportAccessGrant.objects.create(
            tenant=tenant, requested_by=actor, reason=reason,
            requested_scope=scope, requested_hours=hours,
        )
        record_platform_event(
            'SUPPORT_ACCESS_REQUESTED', request=request, actor=actor, tenant=tenant, reason=reason,
            metadata={'grant_id': grant.pk, 'scope': scope, 'hours': hours},
        )
        _log_for_tenant(
            grant, request, action='create',
            description=f'طلب {SUPPORT_LABEL} إذن دخول ({_scope_label(scope)}، {_hours_label(hours)}): {reason}',
        )
        transaction.on_commit(lambda: _notify_tenant(grant, 'request'))
    return grant


def emergency_access(*, tenant, actor, reason, request=None):
    _assert_outsider(tenant, actor)
    reason = _clean_reason(reason)
    now = timezone.now()
    with transaction.atomic():
        grant = SupportAccessGrant.objects.create(
            tenant=tenant, requested_by=actor, reason=reason,
            requested_scope=SupportAccessGrant.SCOPE_FULL, requested_hours=EMERGENCY_HOURS,
            is_emergency=True, status=SupportAccessGrant.STATUS_ACTIVE,
            scope=SupportAccessGrant.SCOPE_FULL,
            expires_at=now + timedelta(hours=EMERGENCY_HOURS),
            decided_at=now,
        )
        record_platform_event(
            'SUPPORT_ACCESS_EMERGENCY', request=request, actor=actor, tenant=tenant, reason=reason,
            metadata={'grant_id': grant.pk, 'hours': EMERGENCY_HOURS},
        )
        _log_for_tenant(
            grant, request, action='create',
            description=f'دخول طارئ من {SUPPORT_LABEL} لمدة {_hours_label(EMERGENCY_HOURS)} بلا موافقة مسبقة: {reason}',
        )
        transaction.on_commit(lambda: _notify_tenant(grant, 'emergency'))
    return grant


def _lock(grant_id, tenant=None):
    qs = SupportAccessGrant.objects.select_for_update().select_related('tenant', 'requested_by')
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    grant = qs.filter(pk=grant_id).first()
    if grant is None:
        raise SupportAccessGrant.DoesNotExist
    return grant


def approve(*, grant_id, tenant, decider, hours=None, scope=None, note='', request=None):
    """الشركة توافق — ولها أن تقصّر المدة أو تخفّض النطاق، لا أن ترفعهما."""
    with transaction.atomic():
        grant = _lock(grant_id, tenant)
        if effective_status(grant) != SupportAccessGrant.STATUS_PENDING:
            raise SupportAccessError('هذا الطلب لم يعد بانتظار الموافقة.')
        if decider.pk == grant.requested_by_id:
            raise SupportAccessError('لا يوافق صاحب الطلب على طلبه.')
        hours = _clean_hours(hours or grant.requested_hours)
        if hours > grant.requested_hours:
            raise SupportAccessError('لا تتجاوز المدة التي طلبها فريق الدعم.')
        scope = _clean_scope(scope or grant.requested_scope)
        if grant.requested_scope == SupportAccessGrant.SCOPE_READ_ONLY:
            scope = SupportAccessGrant.SCOPE_READ_ONLY
        now = timezone.now()
        grant.status = SupportAccessGrant.STATUS_ACTIVE
        grant.scope = scope
        grant.expires_at = now + timedelta(hours=hours)
        grant.decided_by = decider
        grant.decided_at = now
        grant.decision_note = str(note or '')[:2000]
        grant.save(update_fields=[
            'status', 'scope', 'expires_at', 'decided_by', 'decided_at', 'decision_note',
        ])
        record_platform_event(
            'SUPPORT_ACCESS_APPROVED', request=request, actor=decider, tenant=grant.tenant,
            target_user=grant.requested_by, reason=grant.decision_note,
            metadata={'grant_id': grant.pk, 'scope': scope, 'hours': hours},
        )
        _log_for_tenant(
            grant, request, action='update', user=decider,
            description=f'وُوفق على دخول {SUPPORT_LABEL} ({_scope_label(scope)}، {_hours_label(hours)}).',
        )
    return grant


def reject(*, grant_id, tenant, decider, note='', request=None):
    with transaction.atomic():
        grant = _lock(grant_id, tenant)
        if effective_status(grant) != SupportAccessGrant.STATUS_PENDING:
            raise SupportAccessError('هذا الطلب لم يعد بانتظار الموافقة.')
        grant.status = SupportAccessGrant.STATUS_REJECTED
        grant.decided_by = decider
        grant.decided_at = timezone.now()
        grant.decision_note = str(note or '')[:2000]
        grant.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_note'])
        record_platform_event(
            'SUPPORT_ACCESS_REJECTED', request=request, actor=decider, tenant=grant.tenant,
            target_user=grant.requested_by, reason=grant.decision_note,
            metadata={'grant_id': grant.pk},
        )
        _log_for_tenant(grant, request, action='update', user=decider,
                        description=f'رُفض طلب دخول {SUPPORT_LABEL}.')
    return grant


def revoke(*, grant_id, actor, tenant=None, note='', request=None):
    """سحب إذن ساري — من الشركة، أو «خروج» صاحبه قبل انتهائه، أو إلغاء طلبه المعلّق."""
    with transaction.atomic():
        grant = _lock(grant_id, tenant)
        current = effective_status(grant)
        if current == SupportAccessGrant.STATUS_PENDING and actor.pk == grant.requested_by_id:
            grant.status = SupportAccessGrant.STATUS_CANCELLED
            event = 'SUPPORT_ACCESS_CANCELLED'
            text = f'ألغى {SUPPORT_LABEL} طلب الدخول.'
        elif current == SupportAccessGrant.STATUS_ACTIVE:
            grant.status = SupportAccessGrant.STATUS_REVOKED
            event = 'SUPPORT_ACCESS_REVOKED'
            by_owner = actor.pk == grant.requested_by_id
            text = f'انتهى دخول {SUPPORT_LABEL} بخروجه.' if by_owner else f'سُحب إذن دخول {SUPPORT_LABEL}.'
        else:
            raise SupportAccessError('لا يوجد إذن ساري أو طلب معلّق يمكن إنهاؤه.')
        grant.revoked_by = actor
        grant.revoked_at = timezone.now()
        grant.save(update_fields=['status', 'revoked_by', 'revoked_at'])
        record_platform_event(
            event, request=request, actor=actor, tenant=grant.tenant,
            target_user=grant.requested_by, reason=str(note or ''),
            metadata={'grant_id': grant.pk},
        )
        _log_for_tenant(grant, request, action='update', user=actor, description=text)
    return grant


# ── العرض والإشعار ───────────────────────────────────────────────────────────

def _scope_label(scope):
    return dict(SupportAccessGrant.SCOPES).get(scope, scope)


def _hours_label(hours):
    # نفس نصوص الواجهة (`utils/supportAccessLabels.ts` — `SUPPORT_DURATIONS`): البريد
    # والشاشة يصفان الإذن الواحد بكلماتٍ واحدة.
    return {4: '4 ساعات', 24: 'يوم واحد', 168: 'أسبوع'}.get(hours, f'{hours} ساعة')


def _user_label(user):
    if user is None:
        return ''
    return f'{user.first_name} {user.last_name}'.strip() or user.username


def grant_payload(grant, now=None):
    now = now or timezone.now()
    return {
        'id': grant.pk,
        'tenant_id': grant.tenant_id,
        'tenant_name': grant.tenant.CompanyName,
        'requested_by_id': grant.requested_by_id,
        'requested_by': _user_label(grant.requested_by),
        'reason': grant.reason,
        'requested_scope': grant.requested_scope,
        'requested_hours': grant.requested_hours,
        'is_emergency': grant.is_emergency,
        'status': effective_status(grant, now),
        'scope': grant.scope,
        'expires_at': grant.expires_at,
        'decided_by': _user_label(grant.decided_by),
        'decided_at': grant.decided_at,
        'decision_note': grant.decision_note,
        'revoked_by': _user_label(grant.revoked_by),
        'revoked_at': grant.revoked_at,
        'first_used_at': grant.first_used_at,
        'last_used_at': grant.last_used_at,
        'created_at': grant.created_at,
    }


def _log_for_tenant(grant, request, *, action, description, user=None):
    from core.activity import log_activity

    log_activity(
        action=action,
        entity_type='support_access',
        entity_id=grant.pk,
        entity_label=SUPPORT_LABEL,
        description=description,
        metadata={'support_grant_id': grant.pk},
        request=request,
        tenant=grant.tenant,
        user=user or grant.requested_by,
    )


def _notify_tenant(grant, kind) -> None:
    """بريدٌ لمالك الشركة ومديريها — best-effort: البطاقة في لوحة الشركة هي القناة المضمونة."""
    try:
        from django.core.mail import send_mail
        from tenants.models import UserCompanyMembership

        emails = sorted({
            m.user.email for m in UserCompanyMembership.objects
            .filter(tenant=grant.tenant, role='manager').select_related('user')
            if m.user.email
        })
        if not emails:
            return
        base = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
        link = f'{base}/settings/support-access' if base else '/settings/support-access'
        if kind == 'emergency':
            subject = f'تنبيه: دخول طارئ من فريق كترا إلى {grant.tenant.CompanyName}'
            body = (
                f'دخل فريق دعم كترا ({_user_label(grant.requested_by)}) إلى شركتكم دخولاً طارئاً '
                f'لمدة {_hours_label(EMERGENCY_HOURS)}.\nالسبب: {grant.reason}\n'
                f'يمكنكم سحب الإذن فوراً ومراجعة كل ما جرى من:\n{link}'
            )
        else:
            subject = f'طلب إذن دخول من فريق كترا — {grant.tenant.CompanyName}'
            body = (
                f'يطلب فريق دعم كترا ({_user_label(grant.requested_by)}) الدخول إلى شركتكم '
                f'({_scope_label(grant.requested_scope)}، {_hours_label(grant.requested_hours)}).\n'
                f'السبب: {grant.reason}\nللموافقة أو الرفض:\n{link}'
            )
        send_mail(
            subject, body, getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@localhost'),
            emails, fail_silently=True,
        )
    except Exception:  # noqa: BLE001 — الإشعار لا يُسقط الدورة
        logger.exception('support access notification failed grant=%s kind=%s', grant.pk, kind)
