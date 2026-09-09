from django.apps import AppConfig


class EmployeeOpsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "employee_ops"
    verbose_name = "متابعة الموظفين"

    def ready(self):
        # تسجيلُ فحوص النظام — الشرطُ الرابع لإطلاق بوابة التوظيف يعيش هنا
        # لا في فقرةٍ بوثيقة (انظر `employee_ops/checks.py`).
        from . import checks  # noqa: F401
