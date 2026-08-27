from decimal import Decimal

from rest_framework import serializers
from core.api_defaults import TenantScopedPrimaryKeyRelatedField
from tenants.models import Branch
from .models import (
    Task, TaskSubmission, AttendanceRecord, PointsHistory, PersonalExpense,
    PersonalExpenseCategory, PersonalExpenseSheet,
    AttendanceAdjustment, Employee, Payslip, PayrollPayment, WorkLog,
    Department, JobTitle,
    AttendanceDay, CheckEvent, Shift, ShiftAssignment, WorkLocation,
    Advance, ApprovalRule, ApprovalStep, EmployeeRequest, Holiday,
    LeaveBalanceAdjustment, LeaveType,
    Contract, ContractComponent, PayrollRun,
)
from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']

class TaskSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskSubmission
        fields = '__all__'

class TaskSerializer(serializers.ModelSerializer):
    submissions = TaskSubmissionSerializer(many=True, read_only=True)
    assigned_to_details = UserSerializer(source='assigned_to', read_only=True)

    class Meta:
        model = Task
        fields = '__all__'

class AttendanceRecordSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = '__all__'

class PointsHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PointsHistory
        fields = '__all__'

class PersonalExpenseSheetSerializer(serializers.ModelSerializer):
    """المالك من الطلب — كسائر بيانات الدفتر الشخصي."""
    class Meta:
        model = PersonalExpenseSheet
        fields = ['id', 'name', 'position', 'created_at']

    def validate_name(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('اسم الورقة مطلوب.')
        request = self.context.get('request')
        owner = getattr(request, 'user', None)
        if owner is not None:
            taken = PersonalExpenseSheet.objects.filter(user=owner, name=value)
            if self.instance is not None:
                taken = taken.exclude(pk=self.instance.pk)
            if taken.exists():
                raise serializers.ValidationError('عندك ورقة بهذا الاسم.')
        return value


class PersonalExpenseCategorySerializer(serializers.ModelSerializer):
    """`key` يُولَّد خادمياً ولا يُعدَّل — المصاريف مرتبطة به، والاسم وحده يتغيّر."""
    class Meta:
        model = PersonalExpenseCategory
        fields = ['id', 'key', 'label', 'position']
        read_only_fields = ['key']

    def validate_label(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('اسم الفئة مطلوب.')
        return value


class PersonalExpenseSerializer(serializers.ModelSerializer):
    """المالك يُشتق من الطلب دائماً — لا يُقبل من الجسم كي لا يُنسب مصروف لغيره."""
    category_label = serializers.SerializerMethodField()

    class Meta:
        model = PersonalExpense
        fields = [
            'id', 'sheet', 'date', 'title', 'category', 'category_label',
            'amount', 'is_paid', 'notes', 'created_at', 'updated_at',
        ]

    def _owner(self):
        request = self.context.get('request')
        return getattr(request, 'user', None)

    def get_category_label(self, obj):
        # خريطة واحدة لكل استجابة — القائمة كلها لمستخدم واحد.
        if not hasattr(self, '_category_labels'):
            self._category_labels = PersonalExpenseCategory.label_map(obj.user_id)
        return self._category_labels.get(obj.category, obj.category)

    def validate_sheet(self, value):
        """ورقة غيري لا تستقبل مصروفي — العزل نفسه المفروض على القائمة."""
        owner = self._owner()
        if value is not None and owner is not None and value.user_id != owner.pk:
            raise serializers.ValidationError('الورقة غير موجودة.')
        return value

    def validate_category(self, value):
        owner = self._owner()
        if owner is not None and value not in PersonalExpenseCategory.label_map(owner.pk):
            raise serializers.ValidationError('فئة غير معروفة.')
        return value


# ──────────────────────────────────────────────────────────────
#  الرواتب
# ──────────────────────────────────────────────────────────────

class EmployeeSerializer(serializers.ModelSerializer):
    """الموظف — حسابه في الشجرة خادميّ بالكامل ولا يُقبل من الجسم.

    الرصيد لا يُحسب هنا صفّاً صفّاً: العرض يمرّر خريطة أرصدة الصفحة كلها في
    السياق (`balances`)، مبنيّةً باستعلام واحد.
    """
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    pay_type_label = serializers.CharField(source='get_pay_type_display', read_only=True)
    balance = serializers.SerializerMethodField()
    # الهيكل التنظيمي — اختياريّ كلّه، ومقيَّد بالشركة عند الكتابة.
    branch = TenantScopedPrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True)
    department = TenantScopedPrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True)
    job_title_ref = TenantScopedPrimaryKeyRelatedField(
        queryset=JobTitle.objects.all(), required=False, allow_null=True)
    work_location = TenantScopedPrimaryKeyRelatedField(
        queryset=WorkLocation.objects.all(), required=False, allow_null=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    job_title_name = serializers.CharField(source='job_title_ref.name', read_only=True)
    work_location_name = serializers.CharField(source='work_location.name', read_only=True)

    class Meta:
        model = Employee
        fields = [
            'id', 'code', 'name', 'pay_type', 'pay_type_label',
            'monthly_salary', 'hourly_rate',
            'standard_hours_per_day', 'working_days_per_month',
            'job_title', 'phone', 'national_id', 'hire_date', 'is_active', 'notes',
            'branch', 'branch_name', 'department', 'department_name',
            'job_title_ref', 'job_title_name', 'work_location', 'work_location_name',
            'user', 'account', 'account_code', 'account_name', 'balance',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['account', 'created_at', 'updated_at']

    #: أرقامٌ يجوز أن تصل فارغة — حقلُ نوعٍ لا يخصّ الموظف، أو حقلٌ تُرك بلا لمس.
    BLANKABLE_NUMBERS = (
        'monthly_salary', 'hourly_rate',
        'standard_hours_per_day', 'working_days_per_month',
    )

    def to_internal_value(self, data):
        """الفارغ يعني «لم يُذكر» لا «رقم غير صالح».

        `DecimalField` يردّ على النصّ الفارغ رسالته العامّة «الرجاء إدخال رقم
        صالح» بلا اسم حقل، فيرى المستخدم خطأً لا يدلّه على مكانه — وهو أصلاً
        حقل النوع الآخر الذي لم يعرضه النموذج له. نُسقِط الفارغ هنا فيسري
        افتراض النموذج عند الإنشاء وتبقى القيمة المحفوظة عند التعديل، ثم
        يتكفّل `validate` برسالة تسمّي الحقل وسببه.
        """
        if hasattr(data, 'copy'):
            data = data.copy()
            for field in self.BLANKABLE_NUMBERS:
                if field in data and str(data[field]).strip() == '':
                    data.pop(field)
        return super().to_internal_value(data)

    def get_balance(self, obj):
        balances = self.context.get('balances')
        if balances is not None:
            return str(balances.get(obj.pk, Decimal('0.00')))
        # مسار الصفّ الواحد (عرض/تعديل) — استعلام واحد لصفّ واحد، لا N+1.
        from .payroll import employee_balance

        return str(employee_balance(obj))

    def validate_name(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('اسم الموظف مطلوب.')
        return value

    def validate_code(self, value):
        """رقم مكرّر يجب أن يعود 400 مفهومة لا 500 من قيد قاعدة البيانات."""
        from core.tenant_utils import get_tenant

        value = str(value or '').strip()
        request = self.context.get('request')
        tenant = get_tenant(request) if request is not None else None
        if value and tenant is not None:
            taken = Employee.objects.filter(tenant=tenant, code=value)
            if self.instance is not None:
                taken = taken.exclude(pk=self.instance.pk)
            if taken.exists():
                raise serializers.ValidationError('رقم الموظف مستعمل لموظف آخر.')
        return value

    def validate(self, attrs):
        """أجرٌ لا رقم له = موظفٌ بلا راتب — والفرق بين النوعين هو محل الرقم."""
        pay_type = attrs.get('pay_type') or getattr(self.instance, 'pay_type', Employee.PAY_MONTHLY)
        monthly = attrs.get('monthly_salary', getattr(self.instance, 'monthly_salary', 0)) or 0
        hourly = attrs.get('hourly_rate', getattr(self.instance, 'hourly_rate', 0)) or 0
        if pay_type == Employee.PAY_HOURLY and Decimal(hourly) <= 0:
            raise serializers.ValidationError(
                {'hourly_rate': 'الموظف الجزئي يلزمه أجر الساعة المتفق عليه.'})
        if pay_type == Employee.PAY_MONTHLY and Decimal(monthly) <= 0:
            raise serializers.ValidationError(
                {'monthly_salary': 'الموظف الدائم يلزمه راتب شهري.'})
        days = attrs.get('working_days_per_month',
                         getattr(self.instance, 'working_days_per_month', None))
        if days is not None and Decimal(days) <= 0:
            raise serializers.ValidationError(
                {'working_days_per_month': 'أيام الدوام الشهرية يجب أن تكون أكبر من صفر.'})
        hours = attrs.get('standard_hours_per_day',
                          getattr(self.instance, 'standard_hours_per_day', None))
        if hours is not None and Decimal(hours) <= 0:
            raise serializers.ValidationError(
                {'standard_hours_per_day': 'ساعات الدوام اليومية يجب أن تكون أكبر من صفر.'})
        return attrs


class EmployeeRefMixin:
    """يمنع نسبة سجلٍّ لموظف شركة أخرى — العزل لا يكفي أن يكون على القائمة.

    الفلترة تحمي القراءة، لكن الكتابة تصل بمعرّف من الجسم: بلا هذا الفحص يُسجَّل
    غيابٌ أو كشفٌ على موظف شركة أخرى فيلوّث دفاترها.
    """

    def validate_employee(self, value):
        from core.tenant_utils import get_tenant

        request = self.context.get('request')
        tenant = get_tenant(request) if request is not None else None
        if tenant is not None and value.tenant_id != tenant.TenantID:
            raise serializers.ValidationError('الموظف غير موجود في هذه الشركة.')
        return value


# ──────────────────────────────────────────────────────────────
#  الموارد البشرية الموسّعة (`hr_suite`) — الهيكل التنظيمي
# ──────────────────────────────────────────────────────────────

class DepartmentSerializer(serializers.ModelSerializer):
    parent = TenantScopedPrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True)
    branch = TenantScopedPrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True)
    manager = TenantScopedPrimaryKeyRelatedField(
        queryset=Employee.objects.all(), required=False, allow_null=True)
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    manager_name = serializers.CharField(source='manager.name', read_only=True)
    employees_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Department
        fields = [
            'id', 'name', 'parent', 'parent_name', 'branch', 'branch_name',
            'manager', 'manager_name', 'is_active', 'notes', 'employees_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_name(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('اسم القسم مطلوب.')
        return value

    def validate_parent(self, value):
        """قسمٌ أبٌ لنفسه أو لأحد أجداده يصنع حلقةً تُعلّق كل من يمشي الشجرة."""
        if value is None or self.instance is None:
            return value
        node = value
        seen = set()
        while node is not None and node.pk not in seen:
            if node.pk == self.instance.pk:
                raise serializers.ValidationError('لا يجوز أن يكون القسم تابعاً لنفسه أو لفرعٍ منه.')
            seen.add(node.pk)
            node = node.parent
        return value

    def validate(self, attrs):
        """اسمٌ مكرّر يجب أن يعود 400 مفهومة لا 500 من قيد قاعدة البيانات."""
        from core.tenant_utils import get_tenant

        name = attrs.get('name') or getattr(self.instance, 'name', '')
        request = self.context.get('request')
        tenant = get_tenant(request) if request is not None else None
        if name and tenant is not None:
            taken = Department.objects.filter(tenant=tenant, name=name)
            if self.instance is not None:
                taken = taken.exclude(pk=self.instance.pk)
            if taken.exists():
                raise serializers.ValidationError({'name': 'اسم القسم مستعمل لقسم آخر.'})
        return attrs


class JobTitleSerializer(serializers.ModelSerializer):
    department = TenantScopedPrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    employees_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = JobTitle
        fields = [
            'id', 'name', 'department', 'department_name', 'is_active',
            'employees_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_name(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('اسم المسمّى الوظيفي مطلوب.')
        return value

    def validate(self, attrs):
        from core.tenant_utils import get_tenant

        name = attrs.get('name') or getattr(self.instance, 'name', '')
        request = self.context.get('request')
        tenant = get_tenant(request) if request is not None else None
        if name and tenant is not None:
            taken = JobTitle.objects.filter(tenant=tenant, name=name)
            if self.instance is not None:
                taken = taken.exclude(pk=self.instance.pk)
            if taken.exists():
                raise serializers.ValidationError({'name': 'المسمّى الوظيفي مستعمل.'})
        return attrs


class WorkLogSerializer(EmployeeRefMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.name', read_only=True)

    class Meta:
        model = WorkLog
        fields = ['id', 'employee', 'employee_name', 'date', 'hours', 'notes', 'created_at']

    def validate_hours(self, value):
        if value is None or Decimal(value) <= 0:
            raise serializers.ValidationError('عدد الساعات يجب أن يكون أكبر من صفر.')
        if Decimal(value) > 24:
            raise serializers.ValidationError('لا يتجاوز اليوم 24 ساعة.')
        return value


class AttendanceAdjustmentSerializer(EmployeeRefMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)

    class Meta:
        model = AttendanceAdjustment
        fields = [
            'id', 'employee', 'employee_name', 'date', 'kind', 'kind_label',
            'days', 'minutes', 'is_deductible', 'notes', 'created_at',
        ]

    def validate(self, attrs):
        kind = attrs.get('kind') or getattr(self.instance, 'kind', AttendanceAdjustment.KIND_ABSENCE)
        if kind == AttendanceAdjustment.KIND_ABSENCE:
            days = attrs.get('days', getattr(self.instance, 'days', None))
            if days is None or Decimal(days) <= 0:
                raise serializers.ValidationError({'days': 'أيام الغياب يجب أن تكون أكبر من صفر.'})
            attrs['minutes'] = 0
        else:
            minutes = attrs.get('minutes', getattr(self.instance, 'minutes', None))
            if not minutes or int(minutes) <= 0:
                raise serializers.ValidationError({'minutes': 'دقائق التأخير يجب أن تكون أكبر من صفر.'})
            attrs['days'] = Decimal('0')
        return attrs


class PayslipSerializer(EmployeeRefMixin, serializers.ModelSerializer):
    """كل الأرقام المشتقّة للقراءة فقط — الخادم وحده يحتسبها من السجلات.

    القابل للتحرير: الموظف، الفترة، البدلات، الخصومات الأخرى، الملاحظات.
    """
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    paid_total = serializers.SerializerMethodField()

    class Meta:
        model = Payslip
        fields = [
            'id', 'employee', 'employee_name', 'period_start', 'period_end',
            'pay_type', 'rate', 'worked_hours', 'absence_days', 'late_minutes',
            'overtime_minutes', 'overtime_pay',
            'gross', 'allowances', 'absence_deduction', 'late_deduction',
            'other_deductions', 'net', 'advance_deduction', 'net_payable',
            'run', 'status', 'status_label', 'notes',
            'posted_at', 'paid_total', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'pay_type', 'rate', 'worked_hours', 'absence_days', 'late_minutes',
            'overtime_minutes', 'overtime_pay',
            'gross', 'absence_deduction', 'late_deduction', 'net',
            # قسط السلفة و«صافي المدفوع» مشتقّان بالكامل — حقلٌ قابلٌ للكتابة
            # هنا كان يفتح تعديل دَينٍ بلا أثرٍ في السلفة نفسها.
            'advance_deduction', 'net_payable', 'run',
            'status', 'posted_at', 'created_at', 'updated_at',
        ]

    def get_paid_total(self, obj):
        paid = sum((p.amount for p in obj.payments.all()), Decimal('0'))
        return str(paid.quantize(Decimal('0.01')))


class PayrollPaymentSerializer(EmployeeRefMixin, serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    cash_account_name = serializers.CharField(source='cash_account.name', read_only=True)

    class Meta:
        model = PayrollPayment
        fields = [
            'id', 'employee', 'employee_name', 'payslip', 'date', 'amount',
            'cash_account', 'cash_account_name', 'notes', 'created_at',
        ]

    def validate_amount(self, value):
        if value is None or Decimal(value) <= 0:
            raise serializers.ValidationError('مبلغ الصرف يجب أن يكون أكبر من صفر.')
        return value


# ──────────────────────────────────────────────────────────────
#  الموارد البشرية الموسّعة (`hr_suite`) — الحضور والورديات
# ──────────────────────────────────────────────────────────────

class WorkLocationSerializer(serializers.ModelSerializer):
    branch = TenantScopedPrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = WorkLocation
        fields = [
            'id', 'name', 'branch', 'branch_name', 'latitude', 'longitude', 'radius_m',
            'require_geo', 'require_photo', 'allow_ip_fallback', 'ip_allowlist',
            'is_active', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_name(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('اسم موقع العمل مطلوب.')
        return value

    def validate_radius_m(self, value):
        """نصف قطرٍ صفر يرفض كل بصمة، وواسعٌ جداً يجعل السياج زينة."""
        if value is not None and (value < 20 or value > 20000):
            raise serializers.ValidationError('نصف القطر المقبول بين 20 و20000 متر.')
        return value

    def validate_ip_allowlist(self, value):
        """عنوانٌ لا يُفهم يجب أن يقوله الخادم الآن، لا أن يبتلعه صامتاً."""
        from .attendance import parse_ip_allowlist

        raw = str(value or '')
        tokens = [t.strip() for t in raw.replace(',', '\n').split('\n') if t.strip()]
        if tokens and len(parse_ip_allowlist(raw)) != len(tokens):
            raise serializers.ValidationError(
                'أحد العناوين غير صالح — اكتب عنواناً مثل 192.168.1.5 أو نطاقاً مثل 192.168.1.0/24.')
        return raw

    def validate(self, attrs):
        latitude = attrs.get('latitude', getattr(self.instance, 'latitude', None))
        longitude = attrs.get('longitude', getattr(self.instance, 'longitude', None))
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError(
                {'latitude': 'خط الطول وخط العرض يُدخلان معاً أو يُتركان معاً.'})
        require_geo = attrs.get('require_geo', getattr(self.instance, 'require_geo', True))
        if require_geo and latitude is None:
            raise serializers.ValidationError(
                {'latitude': 'موقعٌ يشترط التحقق الجغرافي يلزمه إحداثياته.'})
        return attrs


class ShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = [
            'id', 'name', 'start1', 'end1', 'start2', 'end2',
            'grace_minutes', 'overtime_after_minutes', 'overtime_multiplier',
            'weekly_off_days', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_name(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('اسم الوردية مطلوب.')
        return value

    def validate_weekly_off_days(self, value):
        """أيامٌ بترقيم `weekday()` — الاثنين 0 … الأحد 6، بلا تكرار."""
        if value in (None, ''):
            return []
        if not isinstance(value, (list, tuple)):
            raise serializers.ValidationError('أيام العطلة قائمةُ أرقام.')
        days = []
        for item in value:
            try:
                day = int(item)
            except (TypeError, ValueError):
                raise serializers.ValidationError('يوم العطلة رقمٌ بين 0 و6.')
            if not 0 <= day <= 6:
                raise serializers.ValidationError('يوم العطلة رقمٌ بين 0 و6.')
            if day not in days:
                days.append(day)
        return days

    def validate_overtime_multiplier(self, value):
        if value is not None and (Decimal(value) < 1 or Decimal(value) > 5):
            raise serializers.ValidationError('مضاعف الساعة الإضافية بين 1 و5.')
        return value

    def validate(self, attrs):
        """الفترة الثانية طرفان أو لا شيء — نصفُها يُسقط حساب اليوم بصمت."""
        def current(name):
            return attrs.get(name, getattr(self.instance, name, None))

        start2, end2 = current('start2'), current('end2')
        if (start2 is None) != (end2 is None):
            raise serializers.ValidationError(
                {'start2': 'الفترة الثانية تحتاج بدايةً ونهايةً معاً.'})
        if current('start1') == current('end1'):
            raise serializers.ValidationError(
                {'end1': 'بداية الفترة ونهايتها لا يتطابقان.'})
        if start2 is not None and start2 == end2:
            raise serializers.ValidationError(
                {'end2': 'بداية الفترة الثانية ونهايتها لا يتطابقان.'})
        return attrs


class ShiftAssignmentSerializer(EmployeeRefMixin, serializers.ModelSerializer):
    employee = TenantScopedPrimaryKeyRelatedField(queryset=Employee.objects.all())
    shift = TenantScopedPrimaryKeyRelatedField(queryset=Shift.objects.all())
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    employee_code = serializers.CharField(source='employee.code', read_only=True)
    shift_name = serializers.CharField(source='shift.name', read_only=True)

    class Meta:
        model = ShiftAssignment
        fields = [
            'id', 'employee', 'employee_name', 'employee_code', 'shift', 'shift_name',
            'start_date', 'end_date', 'notes', 'created_at',
        ]
        read_only_fields = ['created_at']

    def validate(self, attrs):
        def current(name):
            return attrs.get(name, getattr(self.instance, name, None))

        start, end = current('start_date'), current('end_date')
        if start and end and end < start:
            raise serializers.ValidationError(
                {'end_date': 'تاريخ النهاية قبل تاريخ البداية.'})
        return attrs


class CheckEventSerializer(serializers.ModelSerializer):
    """البصمة تُقرأ ولا تُعدَّل — كل حقولها `read_only` عمداً.

    الإنشاء يمرّ بمحرّك الحضور لا بـ`save()` المباشر، فالقرار الجغرافي ونسبةُ
    البصمة ليومها مكانهما واحد.
    """
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    employee_code = serializers.CharField(source='employee.code', read_only=True)
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)
    source_label = serializers.CharField(source='get_source_display', read_only=True)
    reject_label = serializers.CharField(source='get_reject_reason_display', read_only=True)
    work_location_name = serializers.CharField(source='work_location.name', read_only=True)

    class Meta:
        model = CheckEvent
        fields = [
            'id', 'employee', 'employee_name', 'employee_code', 'kind', 'kind_label',
            'ts', 'attendance_date', 'source', 'source_label',
            'latitude', 'longitude', 'accuracy_m', 'distance_m', 'ip', 'photo_url',
            'work_location', 'work_location_name',
            'accepted', 'reject_reason', 'reject_label', 'is_voided', 'voided_at',
            'notes', 'created_at',
        ]
        read_only_fields = fields


class ManualPunchSerializer(serializers.Serializer):
    """بصمةٌ يُدخلها مشرف — بلا موقعٍ ولا صورة، ومصدرها معلَنٌ في السجل."""
    employee = TenantScopedPrimaryKeyRelatedField(queryset=Employee.objects.all())
    kind = serializers.ChoiceField(choices=CheckEvent.KIND_CHOICES)
    ts = serializers.DateTimeField()
    notes = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default='')


class AttendanceDaySerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    employee_code = serializers.CharField(source='employee.code', read_only=True)
    department_name = serializers.CharField(source='employee.department.name', read_only=True)
    shift_name = serializers.CharField(source='shift.name', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = AttendanceDay
        fields = [
            'id', 'employee', 'employee_name', 'employee_code', 'department_name',
            'date', 'shift', 'shift_name', 'status', 'status_label',
            'worked_minutes', 'late_minutes', 'early_leave_minutes', 'overtime_minutes',
            'scheduled_minutes', 'absence_days', 'first_in', 'last_out',
            'is_manual_override', 'notes', 'computed_at',
        ]
        read_only_fields = fields


class AttendanceDayOverrideSerializer(serializers.Serializer):
    """تصحيح يومٍ بيد مشرف — يُعلن نفسه فلا تكتسحه إعادة الحساب.

    `is_manual_override=false` ترفع التصحيح وتعيد اليوم إلى حكم بصماته.
    """
    status = serializers.ChoiceField(choices=AttendanceDay.STATUS_CHOICES, required=False)
    worked_minutes = serializers.IntegerField(min_value=0, max_value=24 * 60, required=False)
    late_minutes = serializers.IntegerField(min_value=0, max_value=24 * 60, required=False)
    overtime_minutes = serializers.IntegerField(min_value=0, max_value=24 * 60, required=False)
    absence_days = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal('0'), max_value=Decimal('1'),
        required=False)
    notes = serializers.CharField(max_length=200, required=False, allow_blank=True)
    is_manual_override = serializers.BooleanField(required=False, default=True)


# ──────────────────────────────────────────────────────────────
#  الإجازات والطلبات والسلف (`hr_suite`)
# ──────────────────────────────────────────────────────────────

class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = [
            'id', 'name', 'is_paid', 'annual_grant', 'monthly_accrual',
            'max_days_per_request', 'requires_balance', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_name(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('اسم نوع الإجازة مطلوب.')
        return value


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ['id', 'date', 'name', 'created_at']
        read_only_fields = ['created_at']

    def validate_name(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('اسم العطلة مطلوب.')
        return value

    def validate_date(self, value):
        from core.tenant_utils import get_tenant

        request = self.context.get('request')
        tenant = get_tenant(request) if request is not None else None
        if tenant is not None:
            taken = Holiday.objects.filter(tenant=tenant, date=value)
            if self.instance is not None:
                taken = taken.exclude(pk=self.instance.pk)
            if taken.exists():
                raise serializers.ValidationError('هذا اليوم مسجَّل عطلةً بالفعل.')
        return value


class LeaveBalanceAdjustmentSerializer(EmployeeRefMixin, serializers.ModelSerializer):
    employee = TenantScopedPrimaryKeyRelatedField(queryset=Employee.objects.all())
    leave_type = TenantScopedPrimaryKeyRelatedField(queryset=LeaveType.objects.all())
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    leave_type_name = serializers.CharField(source='leave_type.name', read_only=True)

    class Meta:
        model = LeaveBalanceAdjustment
        fields = [
            'id', 'employee', 'employee_name', 'leave_type', 'leave_type_name',
            'date', 'days', 'notes', 'created_at',
        ]
        read_only_fields = ['created_at']

    def validate_days(self, value):
        if value is None or Decimal(value) == 0:
            raise serializers.ValidationError('التسوية بصفر يومٍ بلا معنى.')
        return value


class ApprovalRuleSerializer(serializers.ModelSerializer):
    department = TenantScopedPrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True)
    branch = TenantScopedPrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    approver_name = serializers.CharField(source='approver_user.username', read_only=True)

    class Meta:
        model = ApprovalRule
        fields = [
            'id', 'kind', 'department', 'department_name', 'branch', 'branch_name',
            'level', 'approver_user', 'approver_name', 'is_active', 'created_at',
        ]
        read_only_fields = ['created_at']

    def validate_kind(self, value):
        value = str(value or '').strip()
        valid = {key for key, _ in EmployeeRequest.KIND_CHOICES}
        if value and value not in valid:
            raise serializers.ValidationError('نوع طلب غير معروف.')
        return value

    def validate_level(self, value):
        if value is not None and not 1 <= int(value) <= 10:
            raise serializers.ValidationError('مستوى الاعتماد بين 1 و10.')
        return value

    def validate_approver_user(self, value):
        """معتمِدٌ من خارج الشركة لا يستطيع فتح الطلب أصلاً — يُمنع عند الباب."""
        from core.tenant_utils import get_tenant
        from tenants.models import UserCompanyMembership

        if value is None:
            return value
        request = self.context.get('request')
        tenant = get_tenant(request) if request is not None else None
        if tenant is not None and not UserCompanyMembership.objects.filter(
                user=value, tenant=tenant).exists():
            raise serializers.ValidationError('هذا المستخدم ليس عضواً في الشركة.')
        return value


class ApprovalStepSerializer(serializers.ModelSerializer):
    approver_name = serializers.CharField(source='approver_user.username', read_only=True)
    acted_by_name = serializers.CharField(source='acted_by.username', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ApprovalStep
        fields = [
            'id', 'level', 'approver_user', 'approver_name', 'status', 'status_label',
            'acted_by', 'acted_by_name', 'acted_at', 'note',
        ]
        read_only_fields = fields


class EmployeeRequestSerializer(EmployeeRefMixin, serializers.ModelSerializer):
    employee = TenantScopedPrimaryKeyRelatedField(queryset=Employee.objects.all())
    leave_type = TenantScopedPrimaryKeyRelatedField(
        queryset=LeaveType.objects.all(), required=False, allow_null=True)
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    employee_code = serializers.CharField(source='employee.code', read_only=True)
    leave_type_name = serializers.CharField(source='leave_type.name', read_only=True)
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    steps = ApprovalStepSerializer(many=True, read_only=True)
    days = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeRequest
        fields = [
            'id', 'employee', 'employee_name', 'employee_code',
            'kind', 'kind_label', 'status', 'status_label',
            'leave_type', 'leave_type_name', 'date_from', 'date_to', 'days',
            'amount', 'installments', 'description', 'attachment_url',
            'execution_date', 'decided_at', 'decision_note', 'steps',
            'created_at', 'updated_at',
        ]
        # الحالة والقرار يتحرّكان بالأفعال (`submit`/`approve`/`reject`) لا
        # بـ`PATCH`: حالةٌ تُكتب مباشرةً تتخطّى سلسلة الاعتماد كلها.
        read_only_fields = [
            'status', 'decided_at', 'decision_note', 'created_at', 'updated_at',
        ]

    def get_days(self, obj):
        return str(obj.leave_days)

    def validate(self, attrs):
        def current(name):
            return attrs.get(name, getattr(self.instance, name, None))

        kind = current('kind')
        if kind == EmployeeRequest.KIND_LEAVE:
            date_from, date_to = current('date_from'), current('date_to')
            if not date_from or not date_to:
                raise serializers.ValidationError(
                    {'date_from': 'طلب الإجازة يلزمه تاريخا البداية والنهاية.'})
            if date_to < date_from:
                raise serializers.ValidationError(
                    {'date_to': 'تاريخ النهاية قبل تاريخ البداية.'})
            leave_type = current('leave_type')
            if leave_type is None:
                raise serializers.ValidationError({'leave_type': 'اختر نوع الإجازة.'})
            days = Decimal((date_to - date_from).days + 1)
            if leave_type.max_days_per_request and days > leave_type.max_days_per_request:
                raise serializers.ValidationError(
                    {'date_to': f'أقصى مدة لهذا النوع {leave_type.max_days_per_request} يوماً.'})
            # الرصيد يُفحص هنا لا عند الاعتماد: منعُ طلبٍ لا رصيد له أرحم من
            # تركه يمشي في سلسلة اعتماد ثم يُرفض في آخرها.
            if leave_type.requires_balance:
                from .leave import available_days

                employee = current('employee')
                if employee is not None:
                    available = available_days(
                        employee, leave_type,
                        exclude_request=getattr(self.instance, 'pk', None))
                    if days > available:
                        raise serializers.ValidationError({
                            'date_to': f'الرصيد المتاح {available} يوماً فقط '
                                       f'(بعد خصم الطلبات قيد المراجعة).',
                        })
        elif kind in (EmployeeRequest.KIND_ADVANCE, EmployeeRequest.KIND_EXPENSE):
            amount = current('amount')
            if amount is None or Decimal(amount) <= 0:
                raise serializers.ValidationError(
                    {'amount': 'المبلغ يجب أن يكون أكبر من صفر.'})
            if kind == EmployeeRequest.KIND_ADVANCE:
                installments = current('installments')
                if installments is not None and int(installments) < 1:
                    raise serializers.ValidationError(
                        {'installments': 'عدد الأقساط واحدٌ على الأقل.'})
        return attrs


class AdvanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    employee_code = serializers.CharField(source='employee.code', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    is_disbursed = serializers.BooleanField(read_only=True)

    class Meta:
        model = Advance
        fields = [
            'id', 'employee', 'employee_name', 'employee_code', 'request',
            'date', 'total', 'monthly_installment', 'remaining',
            'status', 'status_label', 'is_disbursed', 'notes',
            'created_at', 'updated_at',
        ]
        # كلّها خادمية: السلفة تُنشأ باعتماد طلبها، ومتبقّيها ينقص بترحيل
        # القسائم. حقلٌ قابلٌ للكتابة هنا كان يفتح تعديل دَينٍ بلا أثر.
        read_only_fields = fields


# ──────────────────────────────────────────────────────────────
#  العقود ومسير الرواتب (`hr_suite`)
# ──────────────────────────────────────────────────────────────

class ContractComponentSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)

    class Meta:
        model = ContractComponent
        fields = ['id', 'kind', 'kind_label', 'name', 'amount', 'position']

    def validate_name(self, value):
        value = str(value or '').strip()
        if not value:
            raise serializers.ValidationError('اسم البند مطلوب.')
        return value


class ContractSerializer(EmployeeRefMixin, serializers.ModelSerializer):
    """العقد وبنوده معاً — البنود تُكتب متداخلةً لأنها لا معنى لها بدونه."""
    employee = TenantScopedPrimaryKeyRelatedField(queryset=Employee.objects.all())
    employee_name = serializers.CharField(source='employee.name', read_only=True)
    employee_code = serializers.CharField(source='employee.code', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    pay_type_label = serializers.CharField(source='get_pay_type_display', read_only=True)
    components = ContractComponentSerializer(many=True, required=False)
    days_to_expiry = serializers.IntegerField(read_only=True)

    class Meta:
        model = Contract
        fields = [
            'id', 'employee', 'employee_name', 'employee_code',
            'start_date', 'end_date', 'pay_type', 'pay_type_label',
            'monthly_salary', 'hourly_rate', 'overtime_multiplier',
            'status', 'status_label', 'job_title', 'notes', 'document_url',
            'components', 'days_to_expiry', 'created_at', 'updated_at',
        ]
        # الحالة تتحرّك بالأفعال (`activate`/`terminate`) لا بـ`PATCH`: تفعيلٌ
        # مكتوبٌ مباشرةً يتخطّى حارس «عقد نشط واحد».
        read_only_fields = ['status', 'created_at', 'updated_at']

    def validate(self, attrs):
        def current(name):
            return attrs.get(name, getattr(self.instance, name, None))

        start, end = current('start_date'), current('end_date')
        if start and end and end < start:
            raise serializers.ValidationError(
                {'end_date': 'تاريخ نهاية العقد قبل بدايته.'})

        pay_type = current('pay_type')
        monthly = current('monthly_salary') or 0
        hourly = current('hourly_rate') or 0
        if pay_type == Employee.PAY_HOURLY and Decimal(hourly) <= 0:
            raise serializers.ValidationError(
                {'hourly_rate': 'العقد بالساعة يلزمه أجر الساعة.'})
        if pay_type == Employee.PAY_MONTHLY and Decimal(monthly) <= 0:
            raise serializers.ValidationError(
                {'monthly_salary': 'العقد الشهري يلزمه راتب شهري.'})

        multiplier = current('overtime_multiplier')
        if multiplier is not None and not (Decimal('1') <= Decimal(multiplier) <= Decimal('5')):
            raise serializers.ValidationError(
                {'overtime_multiplier': 'مضاعف الساعة الإضافية بين 1 و5.'})
        return attrs

    def create(self, validated_data):
        components = validated_data.pop('components', [])
        contract = Contract.objects.create(**validated_data)
        self._write_components(contract, components)
        return contract

    def update(self, instance, validated_data):
        components = validated_data.pop('components', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if components is not None:
            instance.components.all().delete()
            self._write_components(instance, components)
        return instance

    @staticmethod
    def _write_components(contract, rows):
        for index, row in enumerate(rows):
            row.pop('id', None)
            ContractComponent.objects.create(
                contract=contract, position=row.pop('position', index), **row)


class PayrollRunSerializer(serializers.ModelSerializer):
    branch = TenantScopedPrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True)
    department = TenantScopedPrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    payslip_count = serializers.IntegerField(read_only=True)
    total_net = serializers.CharField(read_only=True)

    class Meta:
        model = PayrollRun
        fields = [
            'id', 'name', 'period_start', 'period_end',
            'branch', 'branch_name', 'department', 'department_name',
            'status', 'status_label', 'notes', 'payslip_count', 'total_net',
            'posted_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['status', 'posted_at', 'created_at', 'updated_at']

    def validate(self, attrs):
        def current(name):
            return attrs.get(name, getattr(self.instance, name, None))

        start, end = current('period_start'), current('period_end')
        if start and end and end < start:
            raise serializers.ValidationError(
                {'period_end': 'نهاية الفترة قبل بدايتها.'})
        return attrs
