"""تطبيعُ رقم الهاتف إلى صيغة E.164 — مفتاحُ منع تكرار العملاء المحتمَلين.

**هذه الدالّةُ مفتاحُ فرادةٍ مخزَّنٌ في القاعدة (`crm.models.LeadPhone.e164`)،
فتغييرُ سلوكها بعد اليوم يستلزم هجرةَ بياناتٍ تعيد تطبيعَ كلّ الصفوف — لا
تُعدَّل بلا ذلك.** ولهذا لا تُستعمل مكتبةٌ خارجيّةٌ (`libphonenumber` أو
نظيراتها): ترقيتها تُغيّر منطقَ التطبيع بلا علمنا فتنفصل الصفوفُ القديمةُ عن
الجديدة على نفس العمود.
"""
import re

#: إسرائيل — سوقُ كترا اليوم (رهط · بئر السبع …)
DEFAULT_COUNTRY_CODE = "972"
#: 970 فلسطين، تُقبل حين يكتبها المستخدم صراحةً بلا `+`.
KNOWN_COUNTRY_CODES = ("972", "970")

_ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ASCII_DIGITS = "01234567890123456789"
_DIGIT_TRANSLATION = str.maketrans(_ARABIC_INDIC_DIGITS + _PERSIAN_DIGITS, _ASCII_DIGITS)

#: كل ما ليس رقماً ولا `+` يُحذف بضربةٍ واحدة — فراغات · `-` · أقواس · نقاط ·
#: ومحارف RTL غير المرئية التي يلصقها واتساب أحياناً مع الرقم (LRM/RLM/LRE/RLE/
#: PDF/LRO/RLO): لا واحد منها رقمٌ أو `+`، فلا داعي لقائمةٍ صريحةٍ بها.
_NON_DIGIT_PLUS_RE = re.compile(r"[^\d+]")
_FINAL_SHAPE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class PhoneNormalizationError(ValueError):
    """رقمٌ لا يمكن تطبيعه بثقة — يُرفض ولا يُخمَّن."""


def normalize_phone(raw: str, *, default_country_code: str = DEFAULT_COUNTRY_CODE) -> str:
    """طبّع رقم هاتف محليّاً أو دوليّاً مكتوباً إلى `+<country><number>`.

    القواعد بالترتيب (كلُّها تُختبر في `crm/tests/test_phone_normalization.py`):
    1. فارغ/`None` ⇒ خطأ.
    2. الأرقامُ العربيّة-الهنديّة والفارسيّة تتحوّل إلى لاتينيّة أوّلاً.
    3. حذفُ كلّ ما ليس رقماً ولا `+` (فراغات · `-` · أقواس · نقاط · محارف RTL).
    4. `00XX…` ⇒ `+XX…`، و`+XX…` تبقى كما هي.
    5. بادئة صفر محليّة: `0XXXXXXXXX` ⇒ `+{افتراضي}{الباقي بلا الصفر}`.
    6. بلا بادئةٍ وبلا صفر، تسعةُ أرقامٍ تبدأ بـ2-9 (رقمٌ محليٌّ بلا الصفر) ⇒
       `+{افتراضي}{هي}`.
    7. بلا `+` لكنّها تبدأ برمز دولةٍ معروف (`KNOWN_COUNTRY_CODES`) ⇒ يُضاف `+`
       فقط — لا تخمين لأرقامٍ لا تبدأ برمزٍ معروف.
    8. الناتج يجب أن يطابق `^\\+[1-9]\\d{7,14}$` وإلا خطأ.
    """
    if not raw or not isinstance(raw, str):
        raise PhoneNormalizationError("رقم الهاتف فارغ.")

    text = raw.translate(_DIGIT_TRANSLATION)
    text = _NON_DIGIT_PLUS_RE.sub("", text)

    if not text:
        raise PhoneNormalizationError(f"رقم الهاتف غير صالح: {raw!r}")

    if text.startswith("00"):
        text = "+" + text[2:]
    elif text.startswith("+"):
        pass
    elif text.startswith("0"):
        text = f"+{default_country_code}{text[1:]}"
    elif len(text) == 9 and text[0] in "23456789":
        text = f"+{default_country_code}{text}"
    elif any(text.startswith(code) for code in KNOWN_COUNTRY_CODES):
        text = "+" + text
    else:
        raise PhoneNormalizationError(f"رقم الهاتف غير صالح: {raw!r}")

    if not _FINAL_SHAPE_RE.match(text):
        raise PhoneNormalizationError(f"رقم الهاتف غير صالح: {raw!r}")

    return text
