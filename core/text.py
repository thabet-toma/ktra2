"""نصوصٌ عربية أوّليّة يشترك فيها أكثر من app — مواصفة #147 (المرحلة 3أ).

`normalize_product_name` كانت وحيدةً داخل `inventory/services.py`، ومطابقةُ
موردٍ مجهولٍ بمورّدٍ مسجَّل (`partners.suggest_partner_matches`) تحتاج نفس
التطبيع بالضبط. استيراد `partners` من `inventory` مباشرةً حافّة اعتماديةٍ
سيّئة (شريكٌ ليس مخزوناً) — فالبدائيّة انتقلت إلى `core`، الطبقة المشتركة
بين apps هذا المشروع، و`inventory.services.normalize_product_name` تستوردها
هنا بسلوكٍ مطابقٍ حرفياً بلا أيّ تغيير في نقاط الاستدعاء.
"""
import re

_TATWEEL = 'ـ'
# التشكيل: الفتحة/الضمة/الكسرة/السكون/الشدة/التنوين (U+064B–U+0652) والألف
# الفوقية (U+0670).
_ARABIC_DIACRITICS_RE = re.compile(r'[ً-ْٰ]')
# صور الألف/الهمزة توحَّد إلى ألفٍ عارية، والألف المقصورة إلى ياء، والتاء
# المربوطة إلى هاء — تطبيعٌ إملائي معياري (نمط مرشِّح Elasticsearch العربي).
_ARABIC_NORMALIZE_MAP = str.maketrans({
    'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا',
    'ى': 'ي',
    'ة': 'ه',
})


def normalize_arabic_text(text: str | None) -> str:
    """طيّ المسافات، إسقاط التطويل والتشكيل، وتوحيد صور الألف/الهمزة/التاء
    المربوطة/الألف المقصورة — بدايةً لكلّ مطابقة اسمٍ عربيّة في المشروع.

    **عمداً بلا مطابقة صوتية.** الحروف الساكنة لا تُمسّ: «سامسونج» تبقى
    مختلفة عن «سامسونغ» بعد هذا التطبيع لأن الفرق حرفٌ حقيقي (ج مقابل غ) لا
    تنويع كتابة — توحيدهما بقاعدة أفضفض كان يُنتج اقتراحاً خاطئاً بلا أساس.
    """
    if not text:
        return ''
    result = str(text).replace(_TATWEEL, '')
    result = _ARABIC_DIACRITICS_RE.sub('', result)
    result = result.translate(_ARABIC_NORMALIZE_MAP)
    result = ' '.join(result.split())
    return result.casefold()


# أسماء تجارية عربية شائعة تُسقَط عند مطابقة **طرف** (مورّد/عميل) لا منتج —
# «شركة الأمل للتجارة» و«الأمل» نفس الطرف. قائمةٌ صريحة قصيرة كما طُلب، لا
# قاعدة عامّة (regex ذكي) قد تبتلع جزءاً من اسمٍ حقيقي. المُقارنة بعد
# `normalize_arabic_text` (فالتاء المربوطة صارت هاءً، مثلاً «مؤسسة» تطابق
# «مؤسسه»).
_ARABIC_PARTY_NOISE_WORDS = {
    normalize_arabic_text(word) for word in (
        'شركة', 'مؤسسة', 'للتجارة', 'التجارة', 'وأولاده', 'واولاده',
        'وشركاه', 'ذ.م.م', 'ذمم',
    )
}
_ENGLISH_PARTY_NOISE_WORDS = {'co', 'co.', 'ltd', 'ltd.', 'llc', 'trading'}


def normalize_party_name(name: str | None) -> str:
    """اسمُ طرفٍ (مورّد/عميل) مُطبَّعٌ **وخالٍ من ضجيج الاسم التجاري** —
    للمطابقة وحدها، لا للتخزين ولا للعرض. يمتدّ `normalize_arabic_text`
    بإسقاط كلمات مثل «شركة»/«مؤسسة»/«للتجارة»/Co./Ltd./LLC كي يُقترَح «الأمل»
    مطابقاً لـ«شركة الأمل للتجارة» بلا أن يُطلَب من أحدٍ كتابة الاسمين
    بنفس الصيغة.
    """
    normalized = normalize_arabic_text(name)
    if not normalized:
        return ''
    kept = [
        word for word in normalized.split(' ')
        if word not in _ARABIC_PARTY_NOISE_WORDS
        and word not in _ENGLISH_PARTY_NOISE_WORDS
    ]
    return ' '.join(kept).strip()
