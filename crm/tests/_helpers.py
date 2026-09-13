"""أدواتُ اختبارٍ مشتركة لنواة الـCRM.

الاستيرادُ من `platform_ops` صريحٌ هنا: `crm` جزءٌ من **عنقود المنصّة** المعلَن
في `platform_ops/tests/test_isolation_guard.py` (`PLATFORM_CLUSTER_APPS`).
"""
from django.contrib.auth.models import User

from platform_ops.models import PlatformEmployee


def make_manager(username="crm-manager"):
    """مستخدمٌ سوبر أدمن — يمرّ من `IsPlatformOperationsManager` بلا صفّ PlatformEmployee."""
    return User.objects.create_user(username=username, password="x", is_superuser=True)


def make_staff_employee(username, **extra):
    """موظّفُ عمليات منصّة نشط — مستخدمٌ عاديّ + صفّ `PlatformEmployee`."""
    user = User.objects.create_user(username=username, password="x")
    employee = PlatformEmployee.objects.create(user=user, **extra)
    return user, employee


def make_plain_user(username="plain-user"):
    """مستخدمٌ مصادَقٌ بلا أيّ صفةٍ منصّية — يُستعمل لاختبار الرفض."""
    return User.objects.create_user(username=username, password="x")
