from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Task, TaskSubmission, AttendanceRecord, PointsHistory
from .serializers import TaskSerializer, TaskSubmissionSerializer, AttendanceRecordSerializer, PointsHistorySerializer
from core.mixins import BaseTenantViewSet
from core.tenant_utils import get_tenant


class TaskViewSet(BaseTenantViewSet):
    queryset = Task.objects.all().order_by('-created_at')
    serializer_class = TaskSerializer

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        kwargs = {'tenant': tenant} if tenant else {}
        if self.request.user.is_authenticated:
            kwargs['created_by'] = self.request.user
        serializer.save(**kwargs)

    @action(detail=True, methods=['post'])
    def add_submission(self, request, pk=None):
        task = self.get_object()
        data = request.data.copy()
        data['task'] = task.id
        if request.user.is_authenticated:
            data['user'] = request.user.id
            
        serializer = TaskSubmissionSerializer(data=data)
        if serializer.is_valid():
            serializer.save(task=task)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AttendanceRecordViewSet(BaseTenantViewSet):
    queryset = AttendanceRecord.objects.all().order_by('-date')
    serializer_class = AttendanceRecordSerializer

class PointsHistoryViewSet(BaseTenantViewSet):
    queryset = PointsHistory.objects.all().order_by('-date')
    serializer_class = PointsHistorySerializer
