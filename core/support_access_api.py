"""جهة الشركة من إذن دخول فريق كترا (SA-2): ترى الطلبات وتوافق وترفض وتسحب.

ملفٌّ مستقلّ عن `platform_admin_api.py` لأن حدّ الصلاحية مختلف: هناك سوبر أدمن
المنصة على كل الشركات، وهنا **مالك الشركة الحالية أو مديرها** على شركته وحدها
(`admin.members.manage` — من يملك إدخال الناس إلى شركته يملك إدخال الدعم).
والشركة من `get_tenant(request)` حصراً. وفريق الدعم الداخل بإذنٍ لا يصل هنا
أبداً: المسار ضمن `SUPPORT_BLOCKED_PATH_PARTS` والصلاحية ضمن المحظورات.
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.access import require_perm
from core.models import SupportAccessGrant
from core.support_access import (
    SupportAccessError, approve, grant_payload, reject, revoke,
)
from core.tenant_utils import get_tenant

MANAGE_PERM = 'admin.members.manage'
HISTORY_LIMIT = 50


def _tenant_or_400(request):
    tenant = get_tenant(request)
    if tenant is None:
        return None, Response({'detail': 'لم تُحدَّد الشركة في الطلب.'}, status=400)
    require_perm(request, MANAGE_PERM, tenant=tenant)
    return tenant, None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def support_access_list(request):
    """أذونات فريق كترا على الشركة الحالية: المعلّقة والسارية أولاً ثم السجلّ."""
    tenant, error = _tenant_or_400(request)
    if error:
        return error
    # المفتوحة (معلّقة/سارية) كلها بلا سقف — قليلةٌ دائماً، وطلبٌ معلّق يجب ألا
    # يسقط من الشاشة لأن السجلّ طال. السقف على السجلّ المغلق وحده.
    open_statuses = (SupportAccessGrant.STATUS_PENDING, SupportAccessGrant.STATUS_ACTIVE)
    grants = SupportAccessGrant.objects.filter(tenant=tenant).select_related(
        'tenant', 'requested_by', 'decided_by', 'revoked_by')
    rows = [grant_payload(grant) for grant in grants.filter(status__in=open_statuses)]
    rows += [
        grant_payload(grant)
        for grant in grants.exclude(status__in=open_statuses)[:HISTORY_LIMIT]
    ]
    # الحالة الفعلية لا المخزّنة: المعلّق بعد مهلته والساري بعد انقضائه «منتهٍ» ⇒ سجلّ.
    history = sorted(
        (row for row in rows if row['status'] not in open_statuses),
        key=lambda row: row['created_at'], reverse=True,
    )[:HISTORY_LIMIT]
    return Response({
        'pending': [row for row in rows if row['status'] == SupportAccessGrant.STATUS_PENDING],
        'active': [row for row in rows if row['status'] == SupportAccessGrant.STATUS_ACTIVE],
        'history': history,
    })


def _decide(request, grant_id, fn, **extra):
    tenant, error = _tenant_or_400(request)
    if error:
        return error
    try:
        grant = fn(grant_id=grant_id, tenant=tenant, request=request, **extra)
    except SupportAccessGrant.DoesNotExist:
        return Response({'detail': 'الطلب غير موجود.'}, status=status.HTTP_404_NOT_FOUND)
    except SupportAccessError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(grant_payload(grant))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def support_access_approve(request, grant_id):
    """{hours?, scope?, note?} — للشركة أن تقصّر المدة وتخفّض النطاق لا أن ترفعهما."""
    return _decide(
        request, grant_id, approve, decider=request.user,
        hours=request.data.get('hours'), scope=request.data.get('scope'),
        note=request.data.get('note', ''),
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def support_access_reject(request, grant_id):
    return _decide(
        request, grant_id, reject, decider=request.user, note=request.data.get('note', ''))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def support_access_revoke(request, grant_id):
    return _decide(
        request, grant_id, revoke, actor=request.user, note=request.data.get('note', ''))
