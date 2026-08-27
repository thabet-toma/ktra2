"""الخدمة الذاتية للموظف (ESS) — واجهةُ الموظف بنفسه، وأساسُ التطبيق الخارجي.

**القاعدة الحاكمة: الموظف يُحلّ من `request.user` لا من معرّفٍ في الطلب.**
كل نقطة هنا تخدم صاحب الجلسة وحده، فلا يوجد `?employee=` ولا معرّفٌ في المسار
— ومعرّفٌ يُقبل من العميل هنا يعني أن أي موظف يقرأ راتب زميله بتغيير رقم.

**والتطبيق الخارجي لا يحتاج شيئاً جديداً**: نفس `TokenAuthentication` غير
منتهية الصلاحية التي تستعملها الواجهة، ونفس ترويسة `X-Tenant-Id`. عقد الربط
موثَّقٌ كاملاً في `docs/modules/hr.md`.

**والصورة تُرفع أولاً** عبر `POST /api/media/upload/` القائم، ثم يُرسَل رابطها
في حمولة البصمة — لا مسار رفعٍ ثانٍ لهذه الوحدة.
"""
import logging
from datetime import timedelta

from django.utils import timezone
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, throttle_classes,
)
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.access import require_perm
from core.modules import require_module
from core.tenant_utils import _get_client_ip, get_tenant

from . import attendance as engine
from .models import AttendanceDay, CheckEvent, Employee, ShiftAssignment
from .serializers import AttendanceDaySerializer, CheckEventSerializer, PayslipSerializer
from .suite import MODULE_KEY, PERM_ESS

logger = logging.getLogger(__name__)

#: أقصى ما تُرجعه نقطةُ «قسائم راتبي» — الموظف يبحث عن قسيمته الأخيرة لا عن أرشيف.
PAYSLIP_LIMIT = 24


class EssThrottle(ScopedRateThrottle):
    scope = 'ess'


class EssPunchThrottle(ScopedRateThrottle):
    scope = 'ess_punch'


def _ess_context(request):
    """يفتح الباب: الترخيص، ثم الصلاحية، ثم الموظف المرتبط بصاحب الجلسة.

    غيابُ الربط **404 لا 403**: مستخدمٌ بلا ملفّ موظف ليس ممنوعاً من شيء —
    لا وجود لبياناته أصلاً.
    """
    tenant = require_module(request, MODULE_KEY)
    require_perm(request, PERM_ESS, tenant=tenant)
    employee = (
        Employee.objects
        .filter(tenant=tenant, user=request.user, is_active=True)
        .select_related('work_location', 'department')
        .first()
    )
    if employee is None:
        raise NotFound('لا يوجد ملفّ موظف مرتبط بحسابك في هذه الشركة.')
    return tenant, employee


def _decimal_or_none(raw, field):
    if raw in (None, ''):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise ValidationError({field: 'قيمة غير صالحة.'})


def _open_session_payload(employee):
    """لحظةُ الدخول المفتوح — الواجهة تَعُدّ منها ولا تخترعها.

    العدّاد الحيّ يقيس ما يصير مالاً، فبدايته خادميّة. الواجهة تضيف الثواني
    فحسب، ولو خُتم التبويب وأُعيد فتحه عاد العدّاد من حيث كان.
    """
    open_event = engine.open_check_in(employee)
    if open_event is None:
        return None
    return {
        'event_id': open_event.pk,
        'since': open_event.ts,
        'attendance_date': open_event.attendance_date,
        'server_now': timezone.now(),
    }


def _location_payload(location):
    return {
        'id': location.pk,
        'name': location.name,
        'latitude': location.latitude,
        'longitude': location.longitude,
        'radius_m': location.radius_m,
        'require_geo': location.require_geo,
        'require_photo': location.require_photo,
    }


def _employee_payload(employee):
    """هويّة الموظف ومواقع بصمته **المرشَّحة** لا موقعه المربوط وحده.

    الموظف غير المربوط تُقبل بصمته عند أي موقع نشط، فإرسالُ موقعه وحده كان
    يترك شاشته بلا ما تقول به «اقترب من المقر» — والقرار يبقى خادمياً على كلّ
    حال: هذه أرقامُ إرشادٍ لا فحصٌ يُعتمد عليه.
    """
    sites = engine.candidate_locations(employee)
    return {
        'id': employee.pk,
        'code': employee.code,
        'name': employee.name,
        'job_title': (employee.job_title_ref.name if employee.job_title_ref_id
                      else employee.job_title),
        'department_name': employee.department.name if employee.department_id else '',
        'pay_type': employee.pay_type,
        'work_location': (
            _location_payload(employee.work_location)
            if employee.work_location_id else None
        ),
        'check_in_sites': [_location_payload(site) for site in sites],
        'requires_photo': any(site.require_photo for site in sites),
        'requires_geo': any(site.require_geo for site in sites),
    }


def _today_payload(employee):
    today = timezone.localdate()
    row = AttendanceDay.objects.filter(employee=employee, date=today).first()
    shift = engine.shift_for(employee, today)
    return {
        'date': today,
        'day': AttendanceDaySerializer(row).data if row is not None else None,
        'shift': (
            {
                'id': shift.pk,
                'name': shift.name,
                'start1': shift.start1,
                'end1': shift.end1,
                'start2': shift.start2,
                'end2': shift.end2,
                'grace_minutes': shift.grace_minutes,
            }
            if shift is not None else None
        ),
        'open_session': _open_session_payload(employee),
    }


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([EssThrottle])
def ess_me(request):
    """هويّة الموظف وموقع بصمته ويومُه الجاري — أول نداءٍ يفتح به التطبيق."""
    _tenant, employee = _ess_context(request)
    payload = _employee_payload(employee)
    payload['today'] = _today_payload(employee)
    return Response(payload)


@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([EssPunchThrottle])
def ess_punch(request, kind):
    """تسجيل حضور أو انصراف — القرار الجغرافي خادميّ بالكامل.

    الرفض يعود **200 مع `accepted=false` وسببه**، لا 4xx: البصمة سُجّلت فعلاً
    (السجل يحفظ المحاولة) وما جرى قرارُ سياسةٍ يُشرح للموظف، لا خطأ في طلبه.
    """
    _tenant, employee = _ess_context(request)
    if kind not in (CheckEvent.KIND_IN, CheckEvent.KIND_OUT):
        raise ValidationError({'kind': 'نوع البصمة إما دخول أو خروج.'})

    data = request.data or {}
    latitude = _decimal_or_none(data.get('lat', data.get('latitude')), 'lat')
    longitude = _decimal_or_none(data.get('lng', data.get('longitude')), 'lng')
    accuracy = data.get('accuracy')
    try:
        accuracy = int(float(accuracy)) if accuracy not in (None, '') else None
    except (TypeError, ValueError):
        accuracy = None

    # ترتيبُ الدخول والخروج يُحرَس هنا لا في الواجهة: زرٌّ مضغوطٌ مرّتين، أو
    # تبويبان مفتوحان، كانا سيفتحان جلستين أو يُغلقان جلسةً غير موجودة.
    open_session = engine.open_check_in(employee)
    if kind == CheckEvent.KIND_IN and open_session is not None:
        raise ValidationError({'detail': 'لديك تسجيل دخول مفتوح — سجّل انصرافك أولاً.'})
    if kind == CheckEvent.KIND_OUT and open_session is None:
        raise ValidationError({'detail': 'لا يوجد تسجيل دخول مفتوح لتسجيل الانصراف منه.'})

    event = engine.record_punch(
        employee,
        kind=kind,
        source=CheckEvent.SOURCE_ESS,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy,
        ip=_get_client_ip(request) or '',
        photo_url=str(data.get('photo_url') or ''),
        user=request.user,
    )
    return Response({
        'event': CheckEventSerializer(event).data,
        'accepted': event.accepted,
        'reject_reason': event.reject_reason,
        'reject_label': event.get_reject_reason_display() if event.reject_reason else '',
        'today': _today_payload(employee),
    })


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([EssThrottle])
def ess_my_day(request):
    """يومي الجاري — العدّاد الحيّ وحالة اليوم ووردية اليوم."""
    _tenant, employee = _ess_context(request)
    return Response(_today_payload(employee))


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([EssThrottle])
def ess_my_month(request):
    """ملخّص شهري وأيامه — «ملخص الحضور خلال الشهر» في تطبيق الجوال."""
    _tenant, employee = _ess_context(request)
    from .views import _month_bounds

    month = str(request.query_params.get('month') or '').strip()
    if month:
        bounds = _month_bounds(month)
        if not bounds:
            raise ValidationError({'month': 'صيغة الشهر يجب أن تكون YYYY-MM.'})
        start, end_exclusive = bounds
    else:
        today = timezone.localdate()
        start = today.replace(day=1)
        end_exclusive = (start + timedelta(days=32)).replace(day=1)

    rows = list(
        AttendanceDay.objects
        .filter(employee=employee, date__gte=start, date__lt=end_exclusive)
        .select_related('shift')
        .order_by('date')
    )
    counted = [r for r in rows if r.status != AttendanceDay.STATUS_UNSCHEDULED]
    present = [r for r in counted if r.status in
               (AttendanceDay.STATUS_PRESENT, AttendanceDay.STATUS_LATE)]
    expected = [r for r in counted if r.status in
                (AttendanceDay.STATUS_PRESENT, AttendanceDay.STATUS_LATE,
                 AttendanceDay.STATUS_ABSENT)]

    return Response({
        'month': start.strftime('%Y-%m'),
        'from': start,
        'to': end_exclusive - timedelta(days=1),
        'summary': {
            'worked_minutes': sum(r.worked_minutes for r in rows),
            'overtime_minutes': sum(r.overtime_minutes for r in rows),
            'late_minutes': sum(r.late_minutes for r in rows),
            'present_days': len(present),
            'absent_days': sum(1 for r in rows if r.status == AttendanceDay.STATUS_ABSENT),
            'leave_days': sum(1 for r in rows if r.status == AttendanceDay.STATUS_LEAVE),
            # النسبة تُحتسب على أيام الدوام المتوقَّعة وحدها: العطلة الأسبوعية
            # والرسمية ليستا حضوراً ولا غياباً، وإقحامُها يخفض نسبة كلِّ منتظم.
            'expected_days': len(expected),
            'attendance_rate': (
                round(100 * len(present) / len(expected), 1) if expected else None
            ),
        },
        'days': AttendanceDaySerializer(rows, many=True).data,
    })


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([EssThrottle])
def ess_my_schedule(request):
    """جدول مناوباتي — الإسنادات السارية والقادمة."""
    _tenant, employee = _ess_context(request)
    today = timezone.localdate()
    rows = (
        ShiftAssignment.objects
        .filter(employee=employee)
        .select_related('shift')
        .order_by('-start_date')[:24]
    )
    return Response([
        {
            'id': row.pk,
            'shift_name': row.shift.name,
            'start1': row.shift.start1,
            'end1': row.shift.end1,
            'start2': row.shift.start2,
            'end2': row.shift.end2,
            'weekly_off_days': row.shift.weekly_off_days,
            'start_date': row.start_date,
            'end_date': row.end_date,
            'is_current': row.covers(today),
        }
        for row in rows
    ])


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([EssThrottle])
def ess_my_payslips(request):
    """قسائم راتبي — **المرحّلة وحدها**.

    القسيمة المسودّة رقمٌ لم يُعتمد بعد وقد يتغيّر قبل الاعتماد؛ عرضُها على
    الموظف يُنشئ توقّعاً بمبلغٍ لم تقرّه الشركة.
    """
    from .models import Payslip

    _tenant, employee = _ess_context(request)
    rows = (
        Payslip.objects
        .filter(employee=employee, status=Payslip.STATUS_POSTED)
        .order_by('-period_start')[:PAYSLIP_LIMIT]
    )
    return Response(PayslipSerializer(rows, many=True).data)
