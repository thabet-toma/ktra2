"""سطح الإدارة المصادَق عليه — يُدرَج تحت `api/document-shares/`.

السطح العام في `docshare/urls_public.py` مفصولاً عمداً: الملفّان يُقرآن
منفصلين، فلا يختلط ما يحتاج توكن مستخدم بما لا يحتاجه.
"""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from docshare.views import DocumentShareViewSet

#: `SimpleRouter` لا `DefaultRouter` — نفس سبب `after_sales`: جذر API قابل
#: للتصفّح يعلن عن وجود السطح لمن لا يعنيه.
router = SimpleRouter()
router.register(r"", DocumentShareViewSet, basename="document-shares")

urlpatterns = [path("", include(router.urls))]
