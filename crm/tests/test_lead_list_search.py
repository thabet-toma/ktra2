"""بحثُ قائمة العملاء وحدودُ «الكل» (#73/#69 — M2).

خانةُ البحث مكتوبٌ عليها «اسم المحل أو رقم الهاتف» والخادمُ كان يطابق `q`
على الاسمين وحدَهما — فرقمٌ جزئيٌّ يُكتب فيها يُرجع قائمةً فارغةً بلا خطأ.
و«الكل» للمدير كانت تخلط الاقتراحات المعلَّقة والمرفوضة بالأرقام المعتمدة،
ولها لوحةٌ خاصّةٌ بها في لوح المدير.
"""
from rest_framework.test import APITestCase

from crm.models import Lead, LeadPhone
from crm.services import create_lead

from ._helpers import make_manager


class LeadListSearchTest(APITestCase):
    def setUp(self):
        self.manager = make_manager("search-manager")
        self.bakery = create_lead(
            store_name="مخبز الريف",
            city="نابلس",
            phones=[
                {"raw": "0599123456", "kind": LeadPhone.Kind.PRIMARY},
                {"raw": "0599123457", "kind": LeadPhone.Kind.WHATSAPP},
            ],
        )
        self.market = create_lead(
            store_name="سوبرماركت النور",
            city="رام الله",
            phones=[{"raw": "0568000111", "kind": LeadPhone.Kind.PRIMARY}],
        )
        self.pending = create_lead(
            store_name="اقتراح معلَّق",
            phones=[{"raw": "0568000222", "kind": LeadPhone.Kind.PRIMARY}],
            approval_status=Lead.Approval.PENDING,
        )
        self.rejected = create_lead(
            store_name="اقتراح مرفوض",
            phones=[{"raw": "0568000333", "kind": LeadPhone.Kind.PRIMARY}],
            approval_status=Lead.Approval.REJECTED,
        )
        self.client.force_authenticate(user=self.manager)

    def _ids(self, **params):
        response = self.client.get("/api/platform/crm/leads/", {"scope": "all", **params})
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        return [row["id"] for row in rows]

    def test_partial_local_phone_finds_the_lead_once(self):
        # الرقمُ كما يكتبه الموظّف (بصفرٍ محلّيّ) ومخزَّنٌ E.164 — وللمحلّ هاتفان
        # يطابقان كلاهما، فبلا `distinct` يظهر مرّتين.
        self.assertEqual(self._ids(q="0599123"), [self.bakery.pk])

    def test_arabic_indic_digits_search_the_phone_too(self):
        self.assertEqual(self._ids(q="٠٥٦٨٠٠٠١١١"), [self.market.pk])

    def test_name_and_city_still_match(self):
        self.assertEqual(self._ids(q="الريف"), [self.bakery.pk])
        self.assertEqual(self._ids(q="رام الله"), [self.market.pk])

    def test_short_digit_runs_do_not_match_every_phone(self):
        # «05» في كل رقمٍ محلّيّ — بحثٌ بها ليس بحثاً.
        self.assertEqual(self._ids(q="05"), [])

    def test_all_scope_shows_approved_leads_only(self):
        ids = self._ids()
        self.assertCountEqual(ids, [self.bakery.pk, self.market.pk])

    def test_explicit_approval_filter_still_reaches_suggestions(self):
        # لوحةُ المدير تطلب المعلَّقة صراحةً — لا يجوز أن يحجبها الافتراضي.
        self.assertEqual(self._ids(approval_status="pending"), [self.pending.pk])
        self.assertEqual(self._ids(approval_status="rejected"), [self.rejected.pk])
