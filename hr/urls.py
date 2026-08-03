from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TaskViewSet, AttendanceRecordViewSet, PointsHistoryViewSet, PersonalExpenseViewSet,
    PersonalExpenseCategoryViewSet, PersonalExpenseSheetViewSet,
)
from .auth_api import (
    login_view,
    logout_view,
    signup_view,
    resend_view,
    change_password_view,
)
from .user_api import user_detail, list_users

router = DefaultRouter()
router.register(r'tasks', TaskViewSet)
router.register(r'attendance', AttendanceRecordViewSet)
router.register(r'points', PointsHistoryViewSet)
router.register(r'personal-expenses', PersonalExpenseViewSet, basename='personal-expense')
router.register(r'personal-expense-sheets', PersonalExpenseSheetViewSet, basename='personal-expense-sheet')
router.register(r'personal-expense-categories', PersonalExpenseCategoryViewSet, basename='personal-expense-category')

urlpatterns = [
    path('auth/login/', login_view),
    path('auth/logout/', logout_view),
    path('auth/signup/', signup_view),
    path('auth/resend-verification/', resend_view),
    path('auth/change-password/', change_password_view),
    path('users/', list_users),
    path('users/<str:pk>/', user_detail),
    path('', include(router.urls)),
]
