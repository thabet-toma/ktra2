"""خدماتُ الأطراف — منطقُ بحثٍ ومطابقةٍ لا تسلسُلَ بيانات.

**ولماذا هنا لا في `serializers.py`؟** `suggest_partner_matches` ليست مُسلسِلاً
ولا تخدم واحداً: هي بحثُ مطابقةٍ يستدعيه مسارُ الطلبيّة في `logistics`. وسكناها
في ملفّ المُسلسِلات كانت تُجبر `logistics.views` على استيراد `partners.serializers`
— وذلك يخالف عقدَ `.importlinter` «داخليّاتُ الـapps ليست واجهاتٍ عامّة».
فالواجهةُ العامّة للـapp خدماتُها، والمُسلسِلاتُ تُعيد التصدير للتوافق.
"""
import re

from core.text import normalize_party_name

from .models import Partner


_IDENTIFIER_NOISE = re.compile(r"[^0-9A-Za-z]+")


def normalize_identifier(value) -> str:
    """صورة الرقم القابلة للمقارنة — أرقام وحروف لاتينية فقط بحالة موحّدة."""
    return _IDENTIFIER_NOISE.sub("", str(value or "")).upper()


def suggest_partner_matches(
    *, tenant_id, name='', email='', tax_number=None, rfq_id=None,
) -> list[dict]:
    """اقتراحاتٌ **لا تُلزم ولا تحجب** — مواصفة #147 (المرحلة 3أ): مورّدٌ
    مجهولٌ كتب اسمه وبريده على رابطٍ عام، وقد يكون طرفاً مسجَّلاً أصلاً بصيغة
    مختلفة. القرار للإنسان دائماً — هذه الدالّة **تقترح مرتَّبةً** ولا تُنشئ
    ولا تُدمج ولا تمنع، خلافاً لـ`find_partner_with_similar_tax_number`/
    `find_partner_with_similar_bank_account` أعلاه اللتين تحجبان الإنشاء:
    تينك حراسة، وهذه اقتراح.

    الترتيب بقوة الإشارة: (١) بريدٌ مطابقٌ تماماً بعد التطبيع — الأقوى.
    (٢) اسمٌ مطابقٌ بعد تطبيعٍ عربي وإسقاط ضجيج الاسم التجاري
    (`core.text.normalize_party_name`). (٣) رقمٌ ضريبيّ شبيهٌ إن وُرد.
    وكلّ اقتراحٍ يحمل `already_recipient` — هل هذا الطرف مستقبِلٌ مسمّىً
    أصلاً على هذه الطلبية (`rfq_id`)؟ الأولى بتحذيرٍ خاص من المالك: اعتمادٌ
    عليه هنا لا يُنشئ `PurchaseRFQRecipient` ثانياً (المسار لا يفعل ذلك
    أصلاً)، لكنّه قد يستحق تحذيراً بصرياً في الواجهة إن اختير سهواً بدل
    التحقّق من ردّه الحقيقي على رابطه الخاص.
    """
    if tenant_id is None:
        return []

    normalized_email = str(email or '').strip().casefold()
    normalized_name = normalize_party_name(name)
    normalized_tax = normalize_identifier(tax_number) if tax_number else ''

    recipient_partner_ids = set()
    if rfq_id:
        from logistics.models import PurchaseRFQRecipient

        recipient_partner_ids = set(
            PurchaseRFQRecipient.objects.filter(
                rfq_id=rfq_id, tenant_id=tenant_id,
            ).values_list('supplier_id', flat=True)
        )

    signal_rank = {'email': 0, 'name': 1, 'tax_number': 2}
    candidates: dict[int, dict] = {}

    def _add(partner, signal):
        entry = candidates.setdefault(
            partner.id, {'partner': partner, 'signals': set()},
        )
        entry['signals'].add(signal)

    qs = Partner.objects.filter(tenant_id=tenant_id, partner_type='Supplier')

    if normalized_email:
        for partner in qs.exclude(email__isnull=True).exclude(email=''):
            if str(partner.email or '').strip().casefold() == normalized_email:
                _add(partner, 'email')

    if normalized_name:
        for partner in qs.only('id', 'name'):
            if normalize_party_name(partner.name) == normalized_name:
                _add(partner, 'name')

    if normalized_tax:
        for partner in qs.exclude(tax_number__isnull=True).exclude(tax_number=''):
            if normalize_identifier(partner.tax_number) == normalized_tax:
                _add(partner, 'tax_number')

    results = [
        {
            'partner_id': entry['partner'].id,
            'name': entry['partner'].name,
            'signals': sorted(entry['signals'], key=lambda s: signal_rank[s]),
            'already_recipient': entry['partner'].id in recipient_partner_ids,
        }
        for entry in candidates.values()
    ]
    results.sort(key=lambda r: (min(signal_rank[s] for s in r['signals']), r['name']))
    return results
