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
