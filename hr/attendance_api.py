"""واجهة الحضور الإدارية — المواقع والورديات والبصمات والأيام (`hr_suite`).

الفصل بين ما يُقرأ وما يُكتب مقصود:

- **البصمة لا تُعدَّل ولا تُحذف.** الإنشاء اليدوي يمرّ بـ`hr.attendance` كي
  يقرّر الموقعَ ويومَ النسبة في مكانٍ واحد، والتصحيح إبطالٌ بعَلَم يترك الأصل
  مقروءاً. سجلٌّ يُعاد كتابته ليس سجلاً.
- **اليوم مشتقّ لا مُدخَل.** لا `POST` عليه ولا `PATCH` عام؛ وطريقه الوحيد
  `override/` الذي يرفع عَلَم التصحيح اليدوي صراحةً — تصحيحٌ صامت تكتسحه أول
  إعادة حساب ويضيع بلا أثر.
"""
import csv
import io
import logging
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.activity import log_activity

from . import attendance as engine
from .models import AttendanceDay, CheckEvent, Employee, Shift, ShiftAssignment, WorkLocation
from .serializers import (
    AttendanceDayOverrideSerializer, AttendanceDaySerializer, CheckEventSerializer,
    ManualPunchSerializer, ShiftAssignmentSerializer, ShiftSerializer,
    WorkLocationSerializer,
)
from .suite import (
    PERM_ATTENDANCE_MANAGE, PERM_ATTENDANCE_VIEW, PERM_SETTINGS, PERM_SHIFTS,
    HrSuiteViewSetBase,
)

logger = logging.getLogger(__name__)

#: سقف نافذة الأيام في استعلام واحد — شهرٌ ونيّف. الشبكة عمودٌ لكل يوم،
#: وما فوق ذلك جدولٌ لا يُقرأ ولا يُطبع (نفس حارس كشف الساعات القائم).
MAX_DAY_WINDOW = 62

#: سقف ملف الاستيراد — سجلّ شهرٍ لمئة موظف أقلّ من هذا بكثير، وما فوقه
#: يقفل worker طوال قراءته.
MAX_IMPORT_BYTES = 2 * 1024 * 1024

#: أسماء الأعمدة المقبولة في ترويسة ملف الاستيراد — بالعربية والإنجليزية معاً،
#: لأن الملف يخرج من جهاز بصمةٍ أو من Excel كتبه محاسب.
_IMPORT_ALIASES = {
    'code': 'code', 'employee': 'code', 'employee_code': 'code',
    'الرقم': 'code', 'رقم الموظف': 'code', 'الموظف': 'code',
    'date': 'date', 'التاريخ': 'date',
    'time_in': 'time_in', 'in': 'time_in', 'الدخول': 'time_in', 'وقت الدخول': 'time_in',
    'time_out': 'time_out', 'out': 'time_out', 'الخروج': 'time_out', 'وقت الخروج': 'time_out',
}


def _parse_clock(day, raw):
    """يقرأ وقتاً بصيغة HH:MM أو HH:MM:SS ويركّبه على يومه. الفارغ يعني «لا بصمة»."""
    text = str(raw or '').strip()
    if not text:
        return None
    for fmt in ('%H:%M', '%H:%M:%S'):
        try:
            clock = datetime.strptime(text, fmt).time()
        except ValueError:
            continue
        return datetime.combine(day, clock)
    raise ValueError(f'وقت غير صالح: {text}')


def parse_attendance_csv(text: str):
    """يحوّل نصّ CSV إلى صفوفٍ مفهومة وقائمةِ أخطاء — بلا لمس قاعدة البيانات.

    منفصلةٌ عن الـview كي تُختبر وحدها: قارئُ ملفٍ مدفونٌ في نقطة HTTP لا
    يُختبر إلا برفع ملف، فتبقى حالاته الحدّية بلا حارس.

    الصفّ الخاطئ **لا يُسقط الملف**: يُجمَع خطؤه برقم سطره ويُكمَل — ملفٌ من
    مئة صفٍّ يُرفض كلّه لأجل صفٍّ واحد يترك صاحبه بلا طريق.
    """
    reader = csv.reader(io.StringIO(text))
    rows = []
    errors = []
    order = ['code', 'date', 'time_in', 'time_out']
    header_seen = False

    for line_no, raw_row in enumerate(reader, start=1):
        cells = [str(cell).strip() for cell in raw_row]
        if not any(cells):
            continue
        if not header_seen:
            mapped = [_IMPORT_ALIASES.get(cell.lower()) for cell in cells]
            if all(mapped) and 'code' in mapped and 'date' in mapped:
                order = mapped
                header_seen = True
                continue
            header_seen = True  # لا ترويسة — نعتمد الترتيب الافتراضي
        record = dict(zip(order, cells))
        code = str(record.get('code') or '').strip()
        if not code:
            errors.append({'row': line_no, 'message': 'رقم الموظف مفقود.'})
            continue
        day = parse_date(str(record.get('date') or '').strip())
        if day is None:
            errors.append({'row': line_no, 'message': 'تاريخ غير صالح (YYYY-MM-DD).'})
            continue
        try:
            time_in = _parse_clock(day, record.get('time_in'))
            time_out = _parse_clock(day, record.get('time_out'))
        except ValueError as exc:
            errors.append({'row': line_no, 'message': str(exc)})
            continue
        if time_in is None and time_out is None:
            errors.append({'row': line_no, 'message': 'لا وقت دخول ولا خروج في السطر.'})
            continue
        # خروجٌ أبكر من دخوله في اليوم نفسه = وردية ليلية عبرت منتصف الليل.
        if time_in is not None and time_out is not None and time_out < time_in:
            time_out += timedelta(days=1)
        rows.append({
            'row': line_no, 'code': code, 'date': day,
            'time_in': time_in, 'time_out': time_out,
        })
    return rows, errors


def _parse_window(params):
    """يحلّ نافذة التواريخ من `?month=` أو `?from=&to=`، وافتراضها اليوم وحده."""
    month = str(params.get('month') or '').strip()
    if month:
        from .views import _month_bounds

        bounds = _month_bounds(month)
        if not bounds:
            raise ValidationError({'month': 'صيغة الشهر يجب أن تكون YYYY-MM.'})
        start, end_exclusive = bounds
        return start, end_exclusive - timedelta(days=1)

    raw_from = str(params.get('from') or '').strip()
    raw_to = str(params.get('to') or '').strip()
    if not raw_from and not raw_to:
        today = timezone.localdate()
        return today, today

    start = parse_date(raw_from) if raw_from else None
    end = parse_date(raw_to) if raw_to else None
    if raw_from and start is None:
        raise ValidationError({'from': 'تاريخ غير صالح.'})
    if raw_to and end is None:
        raise ValidationError({'to': 'تاريخ غير صالح.'})
    start = start or end
    end = end or start
    if end < start:
        raise ValidationError({'to': 'تاريخ النهاية قبل تاريخ البداية.'})
    if (end - start).days + 1 > MAX_DAY_WINDOW:
        raise ValidationError(
            {'to': f'أقصى نافذة {MAX_DAY_WINDOW} يوماً في الطلب الواحد.'})
    return start, end


class WorkLocationViewSet(HrSuiteViewSetBase):
    """مواقع العمل وسياساتها — ضبطُ الشركة، فخلف صلاحية الإعدادات."""

    queryset = WorkLocation.objects.select_related('branch').all()
    serializer_class = WorkLocationSerializer
    perm_read = PERM_ATTENDANCE_VIEW
    perm_write = PERM_SETTINGS

    def perform_destroy(self, instance):
        """موقعٌ بُصم عنده يُعطَّل ولا يُمحى — حذفه يُيتّم بصماته."""
        if instance.check_events.exists():
            raise ValidationError(
                {'detail': 'لا يمكن حذف موقع سُجّلت عنده بصمات — عطّله بدل حذفه.'})
        if instance.employees.exists():
            raise ValidationError(
                {'detail': 'لا يمكن حذف موقع مربوطٍ بموظفين — افصلهم عنه أولاً.'})
        super().perform_destroy(instance)


class ShiftViewSet(HrSuiteViewSetBase):
    """الورديات — تعريفُ الدوام المتوقَّع الذي يُقاس عليه التأخير والإضافي."""

    queryset = Shift.objects.all()
    serializer_class = ShiftSerializer
    perm_read = PERM_ATTENDANCE_VIEW
    perm_write = PERM_SHIFTS

    def get_queryset(self):
        qs = super().get_queryset()
        active = self.request.query_params.get('active')
        if active in ('1', 'true', 'True'):
            qs = qs.filter(is_active=True)
        return qs

    def perform_destroy(self, instance):
        """`PROTECT` على الإسناد يمنع الحذف بـ500 — نسبقه برسالةٍ مفهومة."""
        if instance.assignments.exists():
            raise ValidationError(
                {'detail': 'لا يمكن حذف وردية مُسنَدة لموظفين — عطّلها بدل حذفها.'})
        if instance.attendance_days.exists():
            raise ValidationError(
                {'detail': 'لا يمكن حذف وردية دخلت أيام حضور محسوبة — عطّلها بدل حذفها.'})
        super().perform_destroy(instance)


class ShiftAssignmentViewSet(HrSuiteViewSetBase):
    """جدول المناوبات — إسناد وردية لموظف على مدى تواريخ."""

    queryset = ShiftAssignment.objects.select_related('employee', 'shift').all()
    serializer_class = ShiftAssignmentSerializer
    perm_read = PERM_ATTENDANCE_VIEW
    perm_write = PERM_SHIFTS

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if str(params.get('employee') or '').isdigit():
            qs = qs.filter(employee_id=params['employee'])
        if str(params.get('shift') or '').isdigit():
            qs = qs.filter(shift_id=params['shift'])
        return qs

    def _recompute_around(self, assignment):
        """تغيير الإسناد يغيّر حكم أيامٍ محسوبة — تُعاد بحدود النافذة المسموحة.

        بلا هذا يبقى يومٌ معلَّماً «بلا وردية» بعد إسناد ورديته، فيقرأ المشرف
        جدولاً يناقض ما ضبطه للتوّ.
        """
        start = assignment.start_date
        end = assignment.end_date or timezone.localdate()
        if end < start:
            return
        span = (end - start).days + 1
        if span > MAX_DAY_WINDOW:
            # نافذةٌ أطول من الحدّ تُترك لإعادة الحساب المجدولة من الشاشة —
            # حلقةٌ من مئات الأيام داخل طلب HTTP تُعلّقه.
            end = start + timedelta(days=MAX_DAY_WINDOW - 1)
        assignments = list(
            ShiftAssignment.objects
            .filter(employee_id=assignment.employee_id)
            .select_related('shift')
            .order_by('-start_date', '-id')
        )
        known = set(
            AttendanceDay.objects
            .filter(employee_id=assignment.employee_id, date__gte=start, date__lte=end)
            .values_list('date', flat=True)
        )
        for day in known:
            engine.recompute_attendance_day(
                assignment.employee, day, assignments=assignments)

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._recompute_around(serializer.instance)

    def perform_update(self, serializer):
        serializer.save()
        self._recompute_around(serializer.instance)

    def perform_destroy(self, instance):
        employee, start, end = instance.employee, instance.start_date, instance.end_date
        instance.delete()
        stub = ShiftAssignment(employee=employee, start_date=start, end_date=end)
        self._recompute_around(stub)


class CheckEventViewSet(HrSuiteViewSetBase):
    """سجل البصمات — يُقرأ ويُضاف إليه يدوياً، ولا يُعدَّل ولا يُحذف."""

    queryset = CheckEvent.objects.select_related('employee', 'work_location').all()
    serializer_class = CheckEventSerializer
    perm_read = PERM_ATTENDANCE_VIEW
    perm_write = PERM_ATTENDANCE_MANAGE
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        # النافذة الزمنية فلترُ **قائمة** لا قيدُ وجود: تطبيقها على مسار السجل
        # المفرد يجعل `void/` على بصمة الشهر الماضي تردّ 404 وهي موجودة.
        if getattr(self, 'action', None) != 'list':
            return qs
        params = self.request.query_params
        if str(params.get('employee') or '').isdigit():
            qs = qs.filter(employee_id=params['employee'])
        if params.get('accepted') in ('0', 'false', 'False'):
            qs = qs.filter(accepted=False)
        elif params.get('accepted') in ('1', 'true', 'True'):
            qs = qs.filter(accepted=True)
        if params.get('source'):
            qs = qs.filter(source=params['source'])
        start, end = _parse_window(params)
        return qs.filter(attendance_date__gte=start, attendance_date__lte=end)

    def create(self, request, *args, **kwargs):
        """بصمةٌ يدوية — تمرّ بالمحرّك كي تُنسب ليومها ويُعاد حساب ذلك اليوم.

        الإدخال اليدوي **مقبولٌ دائماً** جغرافياً: المشرف يُصحّح ما لم يُسجَّل،
        ولا معنى لأن يُطالَب بإحداثيات موظفٍ بصم أمس بالورقة والقلم.
        """
        serializer = ManualPunchSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        employee = data['employee']

        with transaction.atomic():
            moment = data['ts']
            attendance_date = engine.resolve_attendance_date(employee, moment)
            event = CheckEvent.objects.create(
                tenant=self.tenant,
                employee=employee,
                kind=data['kind'],
                ts=moment,
                attendance_date=attendance_date,
                source=CheckEvent.SOURCE_MANUAL,
                accepted=True,
                created_by=request.user,
                notes=data.get('notes') or '',
            )
            engine.recompute_attendance_day(employee, attendance_date)

        log_activity(
            action='create', entity_type='hr_check_event', entity_id=event.pk,
            entity_label=f'{employee.name} — {event.get_kind_display()}',
            description='بصمة يدوية', request=request,
        )
        return Response(CheckEventSerializer(event).data, status=201)

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """يُبطل بصمةً ويُعيد حساب يومها — والأصل يبقى مقروءاً في السجل."""
        event = self.get_object()
        if event.is_voided:
            raise ValidationError({'detail': 'البصمة مُبطَلة أصلاً.'})
        with transaction.atomic():
            event.is_voided = True
            event.voided_by = request.user
            event.voided_at = timezone.now()
            event.notes = (request.data.get('notes') or event.notes)[:200]
            event.save(update_fields=['is_voided', 'voided_by', 'voided_at', 'notes'])
            engine.recompute_attendance_day(event.employee, event.attendance_date)

        log_activity(
            action='update', entity_type='hr_check_event', entity_id=event.pk,
            entity_label=event.employee.name, description='إبطال بصمة', request=request,
        )
        return Response(CheckEventSerializer(event).data)


class AttendanceDayViewSet(HrSuiteViewSetBase):
    """أيام الحضور المشتقّة — تُقرأ، وتُصحَّح بإعلانٍ صريح، ولا تُنشأ ولا تُحذف."""

    queryset = AttendanceDay.objects.select_related(
        'employee', 'employee__department', 'shift').all()
    serializer_class = AttendanceDaySerializer
    perm_read = PERM_ATTENDANCE_VIEW
    perm_write = PERM_ATTENDANCE_MANAGE
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        # كما في سجل البصمات: النافذة فلترُ قائمة، وتطبيقها على السجل المفرد
        # يُخفي يوماً موجوداً خلف 404 عند `override/`.
        if getattr(self, 'action', None) != 'list':
            return qs
        params = self.request.query_params
        if str(params.get('employee') or '').isdigit():
            qs = qs.filter(employee_id=params['employee'])
        if str(params.get('department') or '').isdigit():
            qs = qs.filter(employee__department_id=params['department'])
        if str(params.get('branch') or '').isdigit():
            qs = qs.filter(employee__branch_id=params['branch'])
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        start, end = _parse_window(params)
        return qs.filter(date__gte=start, date__lte=end).order_by('date', 'employee__name')

    def create(self, request, *args, **kwargs):
        """اليوم مشتقّ لا مُدخَل — يُبنى من البصمات أو يُصحَّح بـ`override/`.

        `POST` مسموحٌ على المجموعة لأجل `recompute/` وحده؛ وبلا هذا الردّ كان
        الإنشاءُ يمرّ إلى مُسلسِلٍ كلُّ حقوله للقراءة فيُنشئ صفّاً فارغاً.
        """
        return Response(
            {'detail': 'يوم الحضور يُحسب من البصمات — استعمل «تصحيح» أو «إعادة حساب».'},
            status=405)

    @action(detail=True, methods=['post'])
    def override(self, request, pk=None):
        """يصحّح يوماً بيد مشرف ويرفع عَلَم التصحيح — أو يرفعه فيعود للبصمات."""
        day = self.get_object()
        serializer = AttendanceDayOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        keep = data.pop('is_manual_override', True)
        if not keep:
            day.is_manual_override = False
            day.save(update_fields=['is_manual_override'])
            day = engine.recompute_attendance_day(day.employee, day.date)
        else:
            for field, value in data.items():
                setattr(day, field, value)
            day.is_manual_override = True
            day.save()

        log_activity(
            action='update', entity_type='hr_attendance_day', entity_id=day.pk,
            entity_label=f'{day.employee.name} — {day.date}',
            description='تصحيح يوم حضور' if keep else 'رفع التصحيح اليدوي',
            request=request,
        )
        return Response(AttendanceDaySerializer(day).data)

    @action(detail=False, methods=['post'], url_path='import')
    def import_rows(self, request):
        """يستورد سجلّ حضورٍ من CSV — مخرَجُ أجهزة البصمة وجداول Excel.

        الأعمدة: `code, date, time_in, time_out` (الترويسة اختيارية، وتُقبل
        أسماؤها العربية كذلك). كل صفٍّ يُنتج بصمةً أو بصمتين بمصدر «استيراد»
        ثم يُعاد حساب يومها.

        **CSV لا XLSX**: لا `openpyxl` في `requirements.txt`، وإضافةُ تبعيةٍ
        ثقيلة لأجل صيغةٍ يُصدّرها Excel نفسه بنقرتين ثمنٌ لا مقابل له. والتصدير
        يمرّ بمحرّك التقارير القائم (`hr-check-events`) بلا كود جديد.

        `dry_run=true` يفحص الملف ويعدّ أخطاءه بلا كتابة — الاستيراد الأعمى في
        سجلٍّ لا يُحذف منه شيء خطأٌ لا يُتراجَع عنه بسهولة.
        """
        upload = request.FILES.get('file')
        if upload is None:
            raise ValidationError({'file': 'أرفق ملف CSV.'})
        if upload.size > MAX_IMPORT_BYTES:
            raise ValidationError(
                {'file': f'أقصى حجم للملف {MAX_IMPORT_BYTES // 1024} كيلوبايت.'})

        raw = upload.read()
        for encoding in ('utf-8-sig', 'utf-8', 'cp1256'):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValidationError({'file': 'تعذّرت قراءة ترميز الملف.'})

        dry_run = str(request.data.get('dry_run') or '').lower() in ('1', 'true', 'yes')
        parsed, errors = parse_attendance_csv(text)
        if not parsed and not errors:
            raise ValidationError({'file': 'الملف فارغ أو بلا صفوف صالحة.'})

        codes = {row['code'] for row in parsed}
        employees = {
            employee.code: employee
            for employee in Employee.objects.filter(tenant=self.tenant, code__in=codes)
        }

        created = 0
        touched = set()
        with transaction.atomic():
            for row in parsed:
                employee = employees.get(row['code'])
                if employee is None:
                    errors.append({'row': row['row'], 'message': f"رقم موظف غير معروف: {row['code']}"})
                    continue
                for kind, moment in (
                    (CheckEvent.KIND_IN, row['time_in']),
                    (CheckEvent.KIND_OUT, row['time_out']),
                ):
                    if moment is None:
                        continue
                    aware = timezone.make_aware(moment, timezone.get_current_timezone()) \
                        if timezone.is_naive(moment) else moment
                    attendance_date = engine.resolve_attendance_date(employee, aware)
                    if not dry_run:
                        CheckEvent.objects.create(
                            tenant=self.tenant, employee=employee, kind=kind, ts=aware,
                            attendance_date=attendance_date,
                            source=CheckEvent.SOURCE_IMPORT, accepted=True,
                            created_by=request.user,
                        )
                    created += 1
                    touched.add((employee.pk, attendance_date))

            if not dry_run:
                by_employee = {}
                for employee_id, day in touched:
                    by_employee.setdefault(employee_id, []).append(day)
                for employee_id, dates in by_employee.items():
                    employee = next(e for e in employees.values() if e.pk == employee_id)
                    assignments = list(
                        ShiftAssignment.objects
                        .filter(employee=employee)
                        .select_related('shift')
                        .order_by('-start_date', '-id')
                    )
                    for day in dates:
                        engine.recompute_attendance_day(
                            employee, day, assignments=assignments)
            else:
                transaction.set_rollback(True)

        if not dry_run and created:
            log_activity(
                action='create', entity_type='hr_check_event',
                entity_label=upload.name[:200],
                description=f'استيراد {created} بصمة من ملف', request=request,
            )
        return Response({
            'dry_run': dry_run,
            'created': created,
            'days': len(touched),
            'errors': errors[:100],
            'error_count': len(errors),
        })

    @action(detail=False, methods=['post'])
    def recompute(self, request):
        """يعيد حساب نافذةٍ من الأيام لموظف أو لكل الموظفين.

        تُستدعى بعد تعديل ورديةٍ أو سياسةٍ تمسّ ماضياً محسوباً — وإلا بقيت
        الشبكة تعرض حكم القواعد القديمة.
        """
        start, end = _parse_window(request.data)
        employee_id = request.data.get('employee')
        employees = Employee.objects.filter(tenant=self.tenant, is_active=True)
        if str(employee_id or '').isdigit():
            employees = employees.filter(pk=employee_id)

        touched = 0
        for employee in employees:
            assignments = list(
                ShiftAssignment.objects
                .filter(employee=employee)
                .select_related('shift')
                .order_by('-start_date', '-id')
            )
            day = start
            while day <= end:
                engine.recompute_attendance_day(employee, day, assignments=assignments)
                touched += 1
                day += timedelta(days=1)

        return Response({'recomputed': touched, 'from': start, 'to': end})
