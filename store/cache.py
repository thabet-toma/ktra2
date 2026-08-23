"""إبطال كاش المتجر العام — مفتاح نسخة لكل شركة.

**لماذا نسخة لا مسحٌ بنمط:** مفاتيح قائمة المنتجات بصمةُ md5 لكل توليفة
معاملات (بحث · براند · تصنيف · فرز · صفحة)، فلا يمكن تعدادها ولا مسحها بنمطٍ
على كاش Django القياسي. إدخال رقم نسخةٍ في المفتاح يجعل الإبطال زيادةً واحدة:
المفاتيح القديمة تصير غير مقروءة وتموت بانتهاء مدّتها وحدها.

**النسخة لكل شركة** لأن عزل الشركات قانون المشروع ويسري على الكاش كما يسري
على الاستعلام: نشرُ شركةٍ صنفاً يجب ألّا يُسقط كاش متجر شركةٍ أخرى.

هذا الملف **لا يستورد من `store.models` ولا من `inventory`** عمداً: تستدعيه
`inventory/views.py` عند كل كتابة على الصنف، وأي استيراد معاكس يصنع دورة.
"""
from django.core.cache import cache

#: مدة مفتاح النسخة — أطول بكثير من مدة الكاش نفسه كي لا تُفقد النسخة
#: فتُقرأ حمولةٌ قديمة بمفتاحٍ عاد صالحاً.
VERSION_TTL_SECONDS = 30 * 24 * 60 * 60


def _version_key(tenant_id) -> str:
    return f"store:products:ver:{tenant_id}"


def products_version(tenant_id) -> int:
    """رقم النسخة الحالي لكتالوج شركة — يدخل في كل مفتاح كاشٍ للقائمة."""
    if not tenant_id:
        return 0
    key = _version_key(tenant_id)
    value = cache.get(key)
    if value is None:
        cache.add(key, 1, VERSION_TTL_SECONDS)
        value = cache.get(key) or 1
    return value


def invalidate_products(tenant_id) -> None:
    """يُبطل كاش كتالوج شركة — يُستدعى بعد كل كتابةٍ تغيّر الحمولة العامة.

    الفشل هنا لا يُسقط الطلب: الكاش مساعد لا مصدر حقيقة، وكتابةٌ نجحت يجب
    ألّا تُردّ للمستخدم خطأً لأن Redis تعثّر.
    """
    if not tenant_id:
        return
    key = _version_key(tenant_id)
    try:
        cache.incr(key)
    except ValueError:
        # لا مفتاح بعد: أنشئه على 2 كي تُهجر أي حمولةٍ كُتبت تحت النسخة 1.
        cache.set(key, 2, VERSION_TTL_SECONDS)
    except Exception:
        cache.set(key, 2, VERSION_TTL_SECONDS)


class InvalidatesStoreCacheMixin:
    """يُبطل كاش كتالوج المتجر بعد كل طلبٍ ناجحٍ يكتب.

    الربط في `finalize_response` لا في `perform_*` عمداً: بعض الـViewSets هنا
    تتجاوز `create`/`update` كاملةً بلا `perform_*`، وربطُ الإبطال بالاستجابة
    يغطّي كل مسار كتابةٍ حاليٍّ ومستقبلي — بما فيه الإجراءات المخصّصة — بموضع
    واحد لا بخمسة تُنسى إحداها.
    """

    WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    def _invalidation_tenant(self, request):
        from core.tenant_utils import get_tenant

        return get_tenant(request)

    def finalize_response(self, request, response, *args, **kwargs):
        from core.permissions import is_read_only_post

        response = super().finalize_response(request, response, *args, **kwargs)
        # قراءةٌ تُرسَل بـPOST (محدِّدها لا يسع سطر الطلب) ليست كتابة: لا تُبطل
        # كاش الكتالوج — فتحُ كرتٍ مجمّع واحد كان سيبطله ثلاث مرات.
        if (
            request.method in self.WRITE_METHODS
            and not is_read_only_post(request, self)
            and getattr(response, "status_code", 500) < 400
        ):
            tenant = self._invalidation_tenant(request)
            if tenant is not None:
                invalidate_products(getattr(tenant, "pk", tenant))
        return response
