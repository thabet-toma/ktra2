"""مالكُ المنصّة يدخل CRM من مركز القيادة **بلا صفِّ `PlatformEmployee`**.

وهذا ليس حالةً طرفيّة: `IsPlatformOperationsManager` هو `IsPlatformAdmin`، وهو
لا يشترط صفَّ موظّفٍ أصلاً (`crm/tests/_helpers.py::make_manager` يقول ذلك
صريحاً). فالمالكُ يمرّ البابَ ولا دفترَ شخصيَّ له.

وعلّةُ وجود هذا الملفّ أنّ ذلك الفرقَ **يُبدّل ما تراه الشاشة** لا ما تسمح به
الصلاحيّة: لوحةُ CRM كانت تهبط على `scope=mine` دائماً، و`mine` تُرشَّح
خادميّاً بـ`assigned_to=employee` — فبلا صفٍّ يعيد الخادمُ `none()`. أي أنّ
تبويبَ «العملاء» الذي أُضيف للمالك في 212-H كان يُفتح على **صفرٍ بحكم البناء**
والقاعدةُ مملوءةٌ بالأرقام؛ وهو بعينه الشكوى التي وُلد منها التبويب.

فالمقاسُ هنا الحقيقةُ الخادميّةُ التي يُبنى عليها قرارُ الواجهة، ويقابله حارسٌ
ساكنٌ على الواجهة في
`platform_ops/tests/test_crm_ui_contract.py::CrmPanelLandsOnADeskThatHasRowsTest`
— فأحدهما بلا الآخرِ لا يحرس شيئاً: الخادميُّ وحدَه يبقى أخضرَ ولو هبطت
الشاشةُ على الفراغ، والساكنُ وحدَه يثبت نصّاً لا سلوكاً.
"""
from rest_framework.test import APIClient, APITestCase

from crm.services import create_lead

from ._helpers import make_manager, make_staff_employee


class ManagerWithoutEmployeeRowTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.staff_user, cls.employee = make_staff_employee("crm-staff")
        # عميلٌ في المخزن، وعميلٌ مُسنَدٌ لموظّفٍ آخر: لا واحدَ منهما للمالك.
        cls.pooled = create_lead(
            actor=cls.manager, store_name="محل المخزن",
            phones=[{"raw": "0500000001", "kind": "primary"}],
        )
        cls.owned = create_lead(
            actor=cls.manager, store_name="محل الزميل",
            phones=[{"raw": "0500000002", "kind": "primary"}],
        )
        cls.owned.assigned_to = cls.employee
        cls.owned.save(update_fields=["assigned_to"])

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def _names(self, scope):
        response = self.client.get("/api/platform/crm/leads/", {"scope": scope})
        self.assertEqual(response.status_code, 200, response.data)
        # `OptionalPageNumberPagination` يعيد قائمةً عاريةً ما لم يُطلَب `page`،
        # وعميلُ الواجهة يحتمل الشكلَين بـ`pageRows`. فيُقرأ الشكلان هنا كذلك،
        # وإلّا صار الحارسُ رهينةَ مُعامِلٍ لا تُرسله الشاشةُ في أوّل نداء.
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        return sorted(row["store_name"] for row in rows)

    def test_the_managers_own_desk_is_empty_by_construction_not_by_search(self):
        """«عملائي» للمالكِ صفرٌ دائماً — لا لأنّ القاعدةَ فارغة.

        لو قُرئ هذا الصفرُ على الشاشة لَفُهم «لا أرقامَ في النظام»، والصفّان
        موجودان ويعودان في النطاق نفسِه لحظةَ سؤالِه بـ`all`.
        """
        self.assertEqual(self._names("mine"), [])
        self.assertEqual(self._names("all"), ["محل الزميل", "محل المخزن"])

    def test_the_pool_is_not_a_substitute_for_the_whole_book(self):
        """والمخزنُ ليس بديلاً: العميلُ المُسنَدُ لزميلٍ ليس فيه.

        فهبوطٌ على «المخزن المتاح» كان يخفي عن المالكِ كلَّ عميلٍ مُسنَد — وهو
        نصفُ دفترِه. النطاقُ الصحيحُ لمن لا دفترَ شخصيَّ له هو `all`.
        """
        self.assertEqual(self._names("pool"), ["محل المخزن"])

    def test_my_stats_has_nothing_to_show_a_manager_with_no_employee_row(self):
        """وشريطُ «عدّاداتي» يُرفَض له — فإخفاؤه صوابٌ لا تجميل.

        `MyLeadStatsView` يرفع `PermissionDenied` بلا صفّ موظّف، ولوحةُ
        العدّادات تعرض نصَّ الخطأ مكانَها بالتصميم («ملخَّصٌ لا شرطُ عمل»).
        فتركيبُها لمن لا دفترَ له يضع **اعتذاراً في صدر الشاشة** عن شيءٍ لا
        وجودَ له أصلاً، لا عن فشلٍ عابر.
        """
        response = self.client.get("/api/platform/crm/stats/me/")
        self.assertEqual(response.status_code, 403, response.data)

    def test_a_manager_who_does_have_an_employee_row_keeps_his_own_desk(self):
        """ومن له صفٌّ **وهو مدير** يبقى `mine` دفترَه هو لا دفترَ الجميع.

        وهذا ما يجعل الهبوطَ المشتقَّ ذا معنى: لو سوّى الخادمُ بين المديرين
        فأعاد لكلٍّ منهم كلَّ الصفوف في `mine`، لَما كان في اشتقاق النطاق من
        وجود الدفترِ فائدةٌ أصلاً — يستوي `'mine'` و`'all'`.

        ولا يحرس هذا الاختبارُ **اختيارَ** الشاشة: هو لا يقرأ TSX، فتثبيتُ
        النطاق على `'all'` دائماً يمرّ من هنا أخضرَ. الذي يمسك ذلك حارسُ
        `…::test_the_initial_scope_is_derived_from_whether_there_is_a_personal_desk`
        — أُثبِت سقوطُه على تلك الحالة بعينها.
        """
        manager_employee_user, manager_employee = make_staff_employee("crm-boss")
        manager_employee_user.is_superuser = True
        manager_employee_user.save(update_fields=["is_superuser"])
        self.owned.assigned_to = manager_employee
        self.owned.save(update_fields=["assigned_to"])

        self.client.force_authenticate(manager_employee_user)
        self.assertEqual(self._names("mine"), ["محل الزميل"])
