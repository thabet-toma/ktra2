from django.urls import re_path

from after_sales.public_views import WarrantyVerifyPublicView

# يبقى تحت `/api/` عمداً: مسار `/w/` القصير يحتاج سطراً في nginx ينكسر بصمت عند
# نقل الخادم. والشرطة المائلة الأخيرة اختيارية — الرابط المطبوع بلا شرطة.
urlpatterns = [
    re_path(r"^(?P<token>[^/]+)/?$", WarrantyVerifyPublicView.as_view(), name="warranty-verify-public"),
]
