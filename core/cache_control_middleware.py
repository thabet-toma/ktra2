"""
منع تخزين ردود الـ API في المتصفح/الوسطاء (بيانات مالية/ERP حسّاسة).

السبب الجذري لبلاغ «كروم يفتح الواجهات بلا بيانات محدّثة / كاش عالق»: كان يُسمح
للمتصفح بتخزين ردود GET للـ API، فتُعرض بيانات قديمة بعد التعديل أو «التراجع عن
الترحيل». نطبّق الحماية هنا (طبقة Django) لا على الخادم الأمامي لأنها portable —
الاستضافة LiteSpeed مشتركة بلا صلاحية على مستوى الخادم لضبط ترويسات الكاش.

نستخدم أداة Django القياسية `add_never_cache_headers` التي تضع
`Cache-Control: max-age=0, no-cache, no-store, must-revalidate, private`
(+ `Expires`) — القيمة نفسها التي أوصى بها مدير السيرفر.
"""
from django.utils.cache import add_never_cache_headers


class NoStoreAPIMiddleware:
    # يُطبَّق على مسارات الـ API فقط (يُترك ما عداها — لا يخص كاش الأصول الثابتة).
    NO_STORE_PREFIXES = ('/api/',)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(self.NO_STORE_PREFIXES):
            add_never_cache_headers(response)
        return response
