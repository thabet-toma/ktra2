"""تنسيق الأرقام والتواريخ في الصفحة العامة — مرآةٌ خادمية لقواعد الواجهة.

الرقم الذي يراه الزبون على الرابط يجب أن يطابق حرفياً ما يراه الموظف على شاشته.
لذلك هذه الدوال **تنسخ قاعدة `frontend_v2/utils/formatNumber.ts` (`formatNumber`)
بالضبط**: قصٌّ إلى أقصى منازل ثم حذف الأصفار غير الدالّة — `30490.00` تصير
«30490» و`187.50` تصير «187.5». أي انحراف هنا يجعل الفاتورة المُشارَكة تبدو
مستنداً آخر.

والتاريخ ميلادي صريح بـ`YYYY-MM-DD`: `toLocaleDateString` بالعربية يُخرج
تاريخاً هجرياً بحسب ICU على بعض الأنظمة — فخٌّ وقع في هذا المستودع من قبل،
ولا محلّ له في مستند مالي.
"""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def _format(value, max_decimals: int, group: bool, fallback: str) -> str:
    if value is None or value == "":
        return fallback
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return fallback
    if not number.is_finite():
        return fallback

    quantum = Decimal(1).scaleb(-max(0, int(max_decimals)))
    fixed = number.quantize(quantum)
    text = f"{fixed:f}"
    negative = text.startswith("-")
    if negative:
        text = text[1:]

    int_part, _, frac_part = text.partition(".")
    frac_part = frac_part.rstrip("0")
    if group:
        int_part = f"{int(int_part):,}"
    body = f"{int_part}.{frac_part}" if frac_part else int_part
    return f"-{body}" if negative and body != "0" else body


@register.filter
def money(value):
    """مبلغ مالي بفاصل آلاف — مطابق لـ`formatMoney` في الواجهة."""
    return _format(value, 2, True, "0")


@register.filter
def qty(value):
    """كمية أو سعر وحدة: حتى أربع منازل بلا تجميع — مطابق لـ`formatQuantity`."""
    return _format(value, 4, False, "")


@register.filter
def percent(value):
    """نسبة مئوية — منزلتان بلا تجميع، والأصفار غير الدالّة محذوفة."""
    return _format(value, 2, False, "0")


@register.filter
def gdate(value):
    """تاريخ ميلادي صريح `YYYY-MM-DD`. فارغٌ يبقى فارغاً لا «None»."""
    if not value:
        return ""
    try:
        return value.strftime("%Y-%m-%d")
    except AttributeError:
        return str(value)
