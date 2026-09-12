"""كاشُ «الشركة الواحدة» يحمل هويّةً لا كائناً قديماً (`core/tenant_utils.py`).

`get_tenant()` يحلّ الشركةَ تلقائياً حين لا يوجد في القاعدة إلا شركةٌ واحدة، ويحتفظ
بها في **متغيّرٍ عامٍّ على مستوى العملية** تفادياً لاستعلامٍ في كلّ طلب. والتحقّقُ
الذي يحرس هذا الكاش كان عدّاً وحدَه: `Tenant.objects.count() == 1`.

**والعدُّ لا يقول أيَّ شركةٍ هي.** فحين تُستبدَل الشركةُ الوحيدةُ بأخرى — تُحذف
ثمّ تُنشأ غيرُها، والعددُ واحدٌ في الحالتين — يظلّ الكاشُ يسلّم الكائنَ القديم،
فيُنسَب كلُّ ما يُكتب بعدها إلى شركةٍ **لم تعد موجودة**. وأوّلُ ما يقع ضحيّةً
`core.activity.log_activity`: يكتب `ActivityLog` بمفتاحٍ أجنبيٍّ معلَّق.

كُشف هذا من سقوطٍ متقطّعٍ في البوّابة: `PRAGMA foreign_key_check` عند تفكيك
اختبارٍ يشتكي من `activity_logs.TenantID` بقيمةٍ بلا شركة — والاختبارُ المتّهَمُ
يتغيّر في كلّ تشغيل، لأنّ المتّهَمَ هو من يُفكَّك أخيراً لا من كتب الصفّ.
"""
from django.test import TestCase

from core import tenant_utils
from core.tenant_utils import get_tenant, invalidate_tenant_cache
from tenants.models import Tenant


class SingleTenantCacheIdentityTest(TestCase):
    def setUp(self):
        invalidate_tenant_cache()
        self.addCleanup(invalidate_tenant_cache)

    def test_replacing_the_only_tenant_does_not_keep_serving_the_old_one(self):
        """شركةٌ وحيدةٌ تُستبدَل بأخرى — العددُ يبقى واحداً والهويّةُ تتغيّر."""
        first = Tenant.objects.create(CompanyName="الأولى")
        self.assertEqual(get_tenant().pk, first.pk, "الحلُّ التلقائيُّ لم يعمل أصلاً.")

        first.delete()
        second = Tenant.objects.create(CompanyName="الثانية")
        self.assertEqual(Tenant.objects.count(), 1, "شرطُ الاختبار: العددُ لم يتغيّر.")

        resolved = get_tenant()
        self.assertIsNotNone(resolved, "الحلُّ التلقائيُّ توقّف بلا سبب.")
        self.assertEqual(
            resolved.pk, second.pk,
            "الكاشُ سلّم الشركةَ المحذوفة — وكلُّ ما يُكتب بعدها يحمل مفتاحاً معلَّقاً.",
        )

    def test_a_cached_tenant_that_vanished_is_not_handed_out(self):
        """حُذفت الوحيدةُ ولم تُخلَف: الجوابُ «لا شركة»، لا كائنٌ ميّت."""
        only = Tenant.objects.create(CompanyName="الوحيدة")
        self.assertEqual(get_tenant().pk, only.pk)

        only.delete()
        self.assertIsNone(
            get_tenant(),
            "سُلّمت شركةٌ محذوفة؛ والكتابةُ بها تُنتج صفّاً بمفتاحٍ أجنبيٍّ معلَّق.",
        )

    def test_adding_a_second_tenant_still_disables_auto_resolve(self):
        """السلوكُ الأصليُّ محفوظ: شركتان ⇒ لا حلَّ تلقائيّاً (لا «أوّل شركة»)."""
        first = Tenant.objects.create(CompanyName="الأولى")
        self.assertEqual(get_tenant().pk, first.pk)

        Tenant.objects.create(CompanyName="الثانية")
        self.assertIsNone(get_tenant(), "الحلُّ التلقائيُّ يجب أن يتوقّف عند وجود شركتين.")

    def test_the_resolution_stays_one_query_per_request(self):
        """الغرضُ من الكاش محفوظ: لا استعلامَ إضافيٌّ على المسار الشائع.

        كان تحسينُ P2-2 يُسقط العدَّ المتكرّر داخل الطلب الواحد؛ والإصلاحُ يستبدل
        `count()` بشريحةِ صفَّين تحمل الصفَّ نفسَه — **رحلةٌ واحدةٌ كما كان** لا
        رحلتان — ويبقى الاستدعاءُ الثاني في الطلب نفسِه مجّانيّاً بلا استعلام.
        """
        Tenant.objects.create(CompanyName="الوحيدة")
        get_tenant()  # تسخينُ الكاش

        from django.contrib.auth.models import AnonymousUser

        class _FakeRequest:
            headers: dict = {}
            META: dict = {}
            user = AnonymousUser()
            path = "/"

        request = _FakeRequest()
        # الأوّلُ يُعيد التحقّقَ لهذا الطلب باستعلامٍ واحد، والثاني يقرأ العَلَمَ
        # المحفوظَ على الطلب فلا يستعلم إطلاقاً.
        with self.assertNumQueries(1):
            get_tenant(request)
        with self.assertNumQueries(0):
            get_tenant(request)

    def test_invalidate_clears_both_the_object_and_the_checked_flag(self):
        Tenant.objects.create(CompanyName="الوحيدة")
        get_tenant()
        invalidate_tenant_cache()
        self.assertIsNone(tenant_utils._single_tenant_cache)
        self.assertFalse(tenant_utils._single_tenant_checked)
