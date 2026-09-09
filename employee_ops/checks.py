"""فحوصُ نظامٍ لوحدة متابعة الموظفين.

**الشرط الرابع من شروط إطلاق بوابة التوظيف مكتوبٌ هنا لا في وثيقة.** المواصفة
تسمّيه «شرطاً لازماً قبل الإطلاق»، وشرطٌ يعيش في فقرةٍ يُنسى؛ فهذا الفحصُ يُظهره
في كلّ `manage.py check` و`runserver` وفي البوّابة.

المسألة: `NUM_PROXIES` غيرُ مضبوطٍ يعني أنّ DRF يتّخذ **كاملَ** `X-Forwarded-For`
هويّةً للخانق. وترويسةٌ واحدةٌ يكتبها العميلُ تكفي لتغيير تلك الهويّة في كلّ طلب،
أي أنّ الخانقَ الضيّقَ على نقطة التقديم وحدَّ الحجم يصيران زينة: من أراد إغراقَ
النقطة يفعل، ومن أراد رفعَ ألفِ ملفٍّ يفعل.

والفحصُ **تحذيرٌ** بالافتراض، و**خطأٌ** حين يُعلن المشغّلُ أنّ البوّابةَ حيّةٌ
بـ`EMPLOYEE_OPS_HIRING_LIVE=1`. ولم يُربط بـ`DEBUG` لأنّ اختباراتِ هذا المستودع
تعمل بـ`DEBUG=False`، فخطأٌ مشروطٌ به كان سيسقط البوّابةَ على كلّ مطوّرٍ ثمّ
يُسكَت — ومحروسٌ مُسكَتٌ ليس حراسة.

**وحدُّه صراحةً: هذا الفحصُ لا يمنع إقلاعَ الخادم.** جانغو لا يشغّل فحوصَ النظام
تحت WSGI، فالخطأُ يوقف أوامرَ `manage.py` ولا يوقف gunicorn. لذلك **لا يُبنى
الأمانُ عليه**: الهويّةُ التي يخنق بها `employee_ops_apply` مأخوذةٌ من
`REMOTE_ADDR` في `employee_ops/throttles.py`، فتصحّ بلا اعتمادٍ على انضباطِ نشرٍ
قد لا يقع. وهذا الفحصُ تذكيرٌ ثانٍ لا حارسٌ أوّل.
"""
import os

from django.conf import settings
from django.core.checks import Error, Warning, register

W001_ID = "employee_ops.W001"
E001_ID = "employee_ops.E001"

_MESSAGE = (
    "DRF_NUM_PROXIES غير مضبوط، فيتّخذ DRF كامل X-Forwarded-For هويّةً للخانق."
)
_HINT = (
    "اضبط متغيّر البيئة DRF_NUM_PROXIES على عدد الوكلاء العكسيّين أمام التطبيق "
    "(واحدٌ خلف nginx مفرد). بدونه يُلفَّق الخانق بترويسةٍ واحدة، فيصير خانقُ "
    "التقديم employee_ops_apply وحدُّ حجم السيرة بلا أثر — وهو الشرط الرابع من "
    "شروط إطلاق بوابة التوظيف في المواصفة #186."
)


@register()
def check_num_proxies_configured(app_configs, **kwargs):
    """`NUM_PROXIES` مضبوطٌ — وإلا فالخنقُ بالـIP قابلٌ للتلفيق."""
    configured = (settings.REST_FRAMEWORK or {}).get("NUM_PROXIES")
    if configured is not None:
        return []

    live = os.environ.get("EMPLOYEE_OPS_HIRING_LIVE", "").strip() in {"1", "true", "True"}
    if live:
        return [Error(_MESSAGE, hint=_HINT, id=E001_ID)]
    return [Warning(_MESSAGE, hint=_HINT, id=W001_ID)]
