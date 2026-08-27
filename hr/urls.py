from django.urls import path, include
from rest_framework.routers import DefaultRouter, SimpleRouter
from .attendance_api import (
    AttendanceDayViewSet, CheckEventViewSet, ShiftAssignmentViewSet, ShiftViewSet,
    WorkLocationViewSet,
)
from .contracts_api import ContractViewSet, PayrollRunViewSet
from .ess_api import (
    ess_me, ess_my_day, ess_my_month, ess_my_payslips, ess_my_schedule, ess_punch,
)
from .org_api import DepartmentViewSet, JobTitleViewSet
from .requests_api import (
    AdvanceViewSet, ApprovalRuleViewSet, EmployeeRequestViewSet, HolidayViewSet,
    LeaveBalanceAdjustmentViewSet, LeaveTypeViewSet,
)
from .views import (
    TaskViewSet, AttendanceRecordViewSet, PointsHistoryViewSet, PersonalExpenseViewSet,
    PersonalExpenseCategoryViewSet, PersonalExpenseSheetViewSet,
)
from .payroll_api import (
    AttendanceAdjustmentViewSet, EmployeeViewSet, PayrollPaymentViewSet,
    PayslipViewSet, WorkLogViewSet,
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
# الرواتب — الموظفون وساعاتهم وغياباتهم وكشوفهم وصرفها.
router.register(r'employees', EmployeeViewSet, basename='payroll-employee')
router.register(r'work-logs', WorkLogViewSet, basename='payroll-work-log')
router.register(r'attendance-adjustments', AttendanceAdjustmentViewSet, basename='payroll-adjustment')
router.register(r'payslips', PayslipViewSet, basename='payroll-payslip')
router.register(r'payroll-payments', PayrollPaymentViewSet, basename='payroll-payment')

# ──────────────────────────────────────────────────────────────────────────
# وحدة الموارد البشرية الموسّعة (`hr_suite`) — راوتر منفصل عمداً.
#
# `SimpleRouter` لا `DefaultRouter`: جذر الـAPI القابل للتصفّح لا يمرّ ببوابة
# `require_module`، فلو سُجّلت هذه المسارات على الراوتر العام لكشف الجذرُ
# وجودَ الوحدة لشركةٍ غير مرخّصة — وهو بالضبط ما تمنعه البوابة (404 لا 403).
# ──────────────────────────────────────────────────────────────────────────
suite_router = SimpleRouter()
suite_router.register(r'departments', DepartmentViewSet, basename='hr-department')
suite_router.register(r'job-titles', JobTitleViewSet, basename='hr-job-title')
suite_router.register(r'work-locations', WorkLocationViewSet, basename='hr-work-location')
suite_router.register(r'shifts', ShiftViewSet, basename='hr-shift')
suite_router.register(r'shift-assignments', ShiftAssignmentViewSet, basename='hr-shift-assignment')
suite_router.register(r'check-events', CheckEventViewSet, basename='hr-check-event')
suite_router.register(r'attendance-days', AttendanceDayViewSet, basename='hr-attendance-day')
suite_router.register(r'leave-types', LeaveTypeViewSet, basename='hr-leave-type')
suite_router.register(r'holidays', HolidayViewSet, basename='hr-holiday')
suite_router.register(r'leave-adjustments', LeaveBalanceAdjustmentViewSet, basename='hr-leave-adjustment')
suite_router.register(r'approval-rules', ApprovalRuleViewSet, basename='hr-approval-rule')
suite_router.register(r'requests', EmployeeRequestViewSet, basename='hr-request')
suite_router.register(r'advances', AdvanceViewSet, basename='hr-advance')
suite_router.register(r'contracts', ContractViewSet, basename='hr-contract')
suite_router.register(r'payroll-runs', PayrollRunViewSet, basename='hr-payroll-run')

urlpatterns = [
    path('auth/login/', login_view),
    path('auth/logout/', logout_view),
    path('auth/signup/', signup_view),
    path('auth/resend-verification/', resend_view),
    path('auth/change-password/', change_password_view),
    path('users/', list_users),
    path('users/<str:pk>/', user_detail),
    # الخدمة الذاتية — الموظف يُحلّ من الجلسة، فلا معرّف في أي مسار هنا.
    path('ess/me/', ess_me),
    path('ess/my-day/', ess_my_day),
    path('ess/my-month/', ess_my_month),
    path('ess/my-schedule/', ess_my_schedule),
    path('ess/my-payslips/', ess_my_payslips),
    path('ess/check-in/', ess_punch, {'kind': 'in'}),
    path('ess/check-out/', ess_punch, {'kind': 'out'}),
    path('', include(suite_router.urls)),
    path('', include(router.urls)),
]
