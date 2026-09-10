"""مسارُ منتقي المستندات — خارج بادئة `/api/inventory/` عمداً (ISSUE #88).

عقدُ `view=lookup` وحدَه، ولا يسكن تحت بادئة الوحدة كي لا يبتلعه قناعُ قالب
المكتب (`TemplateSurfacePermission` يفحص بادئةَ المسار لا معاملاتِ الاستعلام).

**ولماذا ملفٌّ مستقلّ؟** كان `core/urls.py` يستورد `inventory.views` مباشرةً،
وذلك يخالف عقدَ `.importlinter` «داخليّاتُ الـapps ليست واجهاتٍ عامّة». فالمسارُ
يبقى `/api/lookup/products/` حرفيّاً، ويصله `core` بـ`include` نصّيٍّ لا باستيراد.
"""
from django.urls import path

from .views import ProductLookupViewSet

urlpatterns = [
    path('', ProductLookupViewSet.as_view({'get': 'list'})),
]
