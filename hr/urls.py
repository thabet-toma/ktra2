from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaskViewSet, AttendanceRecordViewSet, PointsHistoryViewSet
from .auth_api import (
    login_view,
    logout_view,
    signup_view,
    resend_view,
    change_password_view,
)
from .user_api import user_detail

router = DefaultRouter()
router.register(r'tasks', TaskViewSet)
router.register(r'attendance', AttendanceRecordViewSet)
router.register(r'points', PointsHistoryViewSet)

urlpatterns = [
    path('auth/login/', login_view),
    path('auth/logout/', logout_view),
    path('auth/signup/', signup_view),
    path('auth/resend-verification/', resend_view),
    path('auth/change-password/', change_password_view),
    path('users/<int:pk>/', user_detail),
    path('', include(router.urls)),
]
