from decimal import Decimal

from rest_framework import serializers
from .models import (
    Task, TaskSubmission, AttendanceRecord, PointsHistory, PersonalExpense,
    PersonalExpenseCategory, PersonalExpenseSheet,
    AttendanceAdjustment, Employee, Payslip, PayrollPayment, WorkLog,
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

    class Meta:
        model = Employee
        fields = [
            'id', 'code', 'name', 'pay_type', 'pay_type_label',
            'monthly_salary', 'hourly_rate',
            'standard_hours_per_day', 'working_days_per_month',
            'job_title', 'phone', 'national_id', 'hire_date', 'is_active', 'notes',
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
            'gross', 'allowances', 'absence_deduction', 'late_deduction',
            'other_deductions', 'net', 'status', 'status_label', 'notes',
            'posted_at', 'paid_total', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'pay_type', 'rate', 'worked_hours', 'absence_days', 'late_minutes',
            'gross', 'absence_deduction', 'late_deduction', 'net',
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
