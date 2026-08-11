"""ترقيم صفحات opt-in موحّد (صيانة الأداء 2026-07).

كان الترقيم معطّلاً كلياً (DEFAULT_PAGINATION_CLASS=None) فكل endpoint قائمة
يبثّ الجدول كاملاً بكل طلب. هذا الكلاس — المنقول من inventory/views.py (task14
DEF-A5) حيث أثبت نفسه — يُفعِّل الترقيم فقط عند تمرير ?page= صراحةً، فلا تنكسر
أي شاشة/قائمة منسدلة قائمة تتوقع مصفوفة خام بلا غلاف {results,...}.
"""
from rest_framework.pagination import PageNumberPagination


class OptionalPageNumberPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        if 'page' not in request.query_params:
            return None
        return super().paginate_queryset(queryset, request, view)


class EnforcedPageNumberPagination(PageNumberPagination):
    """المرحلة 5 / P0-5: ترقيم إلزامي — بلا ?page= تُرجَع الصفحة الأولى.

    يُركَّب endpoint-بـendpoint على قوائم الفئة أ (الجداول التي تنمو بلا حد:
    حركات مخزون، قيود، فواتير، صفقات، مدفوعات) **بعد** تعديل كل مستهلكيها في
    الواجهة في نفس الـcommit — لأن `toList`/`asList` في الواجهة يفكّان غلاف
    {results} صامتَين، فتركيبه قبل تعديل المستهلك = اقتطاع صامت إلى 50 صفاً.

    القوائم المنسدلة/المحرّرات التي تحتاج مصفوفة خام تأخذ نقطة `lookup`
    محدودة السقف (النمط في `sales/views.py::SalesInvoiceViewSet.lookup`)
    بدل إعفاء القائمة كلها من الترقيم.

    ملاحظة تصميم: لا نجعل هذا الافتراضي العام (DEFAULT_PAGINATION_CLASS)
    لأن مئات القوائم الصغيرة (عملات، وحدات قياس، إعدادات) تُستهلك كمصفوفات
    خام في عشرات الشاشات — فرضه عليها دفعة واحدة يعيد خطر الاقتطاع الصامت
    الذي نتجنّبه. القاعدة: جدول ينمو بلا حد ⇒ EnforcedPageNumberPagination.
    """

    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200
