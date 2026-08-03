from rest_framework import serializers
from .models import (
    Task, TaskSubmission, AttendanceRecord, PointsHistory, PersonalExpense,
    PersonalExpenseCategory, PersonalExpenseSheet,
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
