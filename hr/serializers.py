from rest_framework import serializers
from .models import Task, TaskSubmission, AttendanceRecord, PointsHistory, PersonalExpense
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

class PersonalExpenseSerializer(serializers.ModelSerializer):
    """المالك يُشتق من الطلب دائماً — لا يُقبل من الجسم كي لا يُنسب مصروف لغيره."""
    category_label = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = PersonalExpense
        fields = [
            'id', 'date', 'title', 'category', 'category_label',
            'amount', 'is_paid', 'notes', 'created_at', 'updated_at',
        ]
