"""الحارسُ الذي يمنع موظّفاً من الكتابة على عميلٍ ليس له — **وتعدادُ الملكيّة**.

`test_crm_route_guard.py` يسأل سؤالاً واحداً: «هل البابُ مغلقٌ بوجه الغريب؟».
وهذا الملفُّ يسأل الثاني الذي لا يُغنيه الأوّل: «وماذا يرى **الزميل** بعد أن
يدخل؟» — فكلُّ موظّفي كترا يمرّون من البابِ نفسِه، والتسريبُ المحتمَل بينهم لا
منهم. ولأنّ سؤالاً بلا تعدادٍ يتقادم مع أوّل مسارٍ جديد، يُفرَض أدناه أن يكون
**كلُّ** مسارٍ تحت `/api/platform/crm/` إمّا مُختبَراً هنا أو مُستثنًى بسبب.

هذا هو نظيرُ `platform_ops/tests/test_staff_scope_guard.py` لهذه الوحدة: ذاك
التعدادُ يمشي على `api/platform/ops/` وحدَها فلا يرى هذه البادئةَ إطلاقاً، وviewٌ
يعلن `IsPlatformOperationsStaff` صراحةً يخرج كذلك من تعداده الثاني — فبلا هذا
الملفّ تكون كلُّ مسارات الـCRM خارجَ كلِّ تعداد.
"""
from rest_framework.test import APIClient, APITestCase

from crm.models import Lead, LeadPhone
from crm.services import create_lead

from ._helpers import make_manager, make_staff_employee
from .test_crm_route_guard import _crm_routes

#: مساراتٌ يُثبَت هنا فعلياً أنّ زميلاً لا يملك الصفَّ لا يكتبه ولا يقرأ تفصيلَه.
OWNERSHIP_EXERCISED = frozenset({
    "/api/platform/crm/leads/",
    "/api/platform/crm/leads/1/",
    "/api/platform/crm/leads/1/activities/",
    "/api/platform/crm/leads/1/claim/",
    "/api/platform/crm/leads/1/status/",
    "/api/platform/crm/leads/1/transfer/",
    "/api/platform/crm/leads/lookup/",
    "/api/platform/crm/stats/me/",
})

#: مساراتٌ لا ينطبق عليها فحصُ «صفُّ زميل»، ولكلٍّ سببُه المكتوب.
OWNERSHIP_EXCUSED = {
    "/api/platform/crm/leads/import/":
        "للمدير وحدَه (`IsPlatformOperationsManager`) — لا صفَّ زميلٍ يُقرأ، ورفضُ "
        "الموظّف منه مُثبَتٌ في `test_lead_import.py`.",
    "/api/platform/crm/leads/1/approve/":
        "بتُّ اقتراحٍ — للمدير وحدَه، ومُثبَتٌ في `test_lead_suggestions.py`.",
    "/api/platform/crm/leads/1/reject/":
        "بتُّ اقتراحٍ — للمدير وحدَه، ومُثبَتٌ في `test_lead_suggestions.py`.",
    "/api/platform/crm/leads/1/release/":
        "إعادةُ عميلٍ إلى المخزن — للمدير وحدَه بالتصميم.",
    "/api/platform/crm/stats/overview/":
        "لوحةُ المدير: أرقامُ كلِّ الموظّفين مجموعةً بالتصميم، فلا ملكيّةَ صفٍّ تُفحَص.",
    "/api/platform/crm/leads/1/transfer-requests/":
        "**طلبُ** التحويل مفتوحٌ عمداً لموظّفٍ ليس صاحبَ العميل — هذا غرضُه كلُّه "
        "(زرُّ «طلب تحويل العميل» في نموذج المالك)؛ ودورتُه في `test_lead_transfer.py`.",
    "/api/platform/crm/transfer-requests/":
        "قائمةٌ مضيَّقةٌ على ما يخصّ الطالبَ أو صاحبَ العميل — يغطّيها `test_lead_transfer.py`.",
    "/api/platform/crm/transfer-requests/1/":
        "تفصيلُ طلبٍ — نفسُ تضييق القائمة أعلاه عبر `get_queryset`.",
    "/api/platform/crm/transfer-requests/1/decide/":
        "البتُّ لصاحب العميل أو المدير، ومُثبَتٌ في `test_lead_transfer.py`.",
}


class CrmOwnershipCensusTest(APITestCase):
    """لا مسارَ CRM يُنسى: اتّحادُ (المُختبَر ∪ المُستثنى) يساوي التعدادَ تماماً."""

    def test_every_crm_route_is_exercised_for_ownership_or_excused(self):
        census = set(_crm_routes())
        accounted_for = OWNERSHIP_EXERCISED | set(OWNERSHIP_EXCUSED)

        forgotten = census - accounted_for
        self.assertEqual(
            forgotten, set(),
            "مسارُ CRM جديدٌ ولم يُقرَّر مصيرُه في فحص الملكيّة "
            f"(اختبِرْه هنا أو استثنِه بسبب): {sorted(forgotten)}",
        )

        stale = accounted_for - census
        self.assertEqual(
            stale, set(),
            f"مسارٌ في قوائم هذا الملفّ لم يعد موجوداً في الـURLconf: {sorted(stale)}",
        )

    def test_every_excuse_is_a_real_written_reason(self):
        for route, reason in OWNERSHIP_EXCUSED.items():
            with self.subTest(route=route):
                self.assertGreater(
                    len(reason.strip()), 25,
                    f"استثناءُ {route} بلا سببٍ مكتوب — الاستثناءُ قرارٌ يُبرَّر لا سطرٌ يمرّ.",
                )


class LeadLockTest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner_user, self.owner = make_staff_employee("lock-owner")
        self.colleague_user, self.colleague = make_staff_employee("lock-colleague")
        self.lead = create_lead(
            store_name="محل مقفل", phones=[{"raw": "0501111111", "kind": LeadPhone.Kind.PRIMARY}],
        )
        self.lead.assigned_to = self.owner
        self.lead.save(update_fields=["assigned_to"])

    def test_a_colleague_cannot_write_on_a_lead_that_is_not_his(self):
        self.client.force_authenticate(user=self.colleague_user)
        res = self.client.post(
            f"/api/platform/crm/leads/{self.lead.pk}/status/", {"status": Lead.Status.CONTACTED}, format="json",
        )
        self.assertEqual(res.status_code, 403, res.content)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.NEW)

    def test_a_colleague_cannot_claim_an_assigned_lead(self):
        self.client.force_authenticate(user=self.colleague_user)
        res = self.client.post(f"/api/platform/crm/leads/{self.lead.pk}/claim/")
        self.assertEqual(res.status_code, 409, res.content)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to_id, self.owner.pk)

    def test_a_colleague_can_still_see_that_the_number_is_taken(self):
        self.client.force_authenticate(user=self.colleague_user)
        res = self.client.get("/api/platform/crm/leads/lookup/", {"phone": "0501111111"})
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["found"])
        self.assertEqual(data["locked_by"]["id"], self.owner.pk)
        self.assertFalse(data["is_mine"])
        self.assertFalse(data["can_claim"])
        self.assertNotIn("activities", data)

    def test_a_colleague_does_not_see_the_lead_in_his_own_list(self):
        self.client.force_authenticate(user=self.colleague_user)
        res = self.client.get("/api/platform/crm/leads/")
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        rows = body.get("results", body) if isinstance(body, dict) else body
        self.assertNotIn(self.lead.pk, [row["id"] for row in rows])

    def test_a_colleague_cannot_open_the_lead_detail(self):
        """صفُّ زميلٍ يُردّ **٤٠٤ لا ٤٠٣**: الثانيةُ تُثبت أنّ الصفَّ موجود."""
        self.client.force_authenticate(user=self.colleague_user)
        res = self.client.get(f"/api/platform/crm/leads/{self.lead.pk}/")
        self.assertEqual(res.status_code, 404, res.content)

    def test_a_colleague_cannot_read_or_write_the_activity_log(self):
        self.client.force_authenticate(user=self.colleague_user)
        read = self.client.get(f"/api/platform/crm/leads/{self.lead.pk}/activities/")
        self.assertIn(read.status_code, (403, 404), read.content)
        write = self.client.post(
            f"/api/platform/crm/leads/{self.lead.pk}/activities/",
            {"kind": "call", "body": "محاولةُ زميل"}, format="json",
        )
        self.assertIn(write.status_code, (403, 404), write.content)
        self.assertEqual(self.lead.activities.count(), 0)

    def test_a_colleague_cannot_transfer_a_lead_away_from_its_owner(self):
        """التحويلُ المباشرُ لصاحبه أو المدير — وغيرُهما **يطلب** لا يحوّل."""
        self.client.force_authenticate(user=self.colleague_user)
        res = self.client.post(
            f"/api/platform/crm/leads/{self.lead.pk}/transfer/",
            {"to_employee": self.colleague.pk, "reason": "بدّي ياه"}, format="json",
        )
        self.assertIn(res.status_code, (403, 404), res.content)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to_id, self.owner.pk)

    def test_a_colleague_stats_do_not_count_a_lead_that_is_not_his(self):
        self.client.force_authenticate(user=self.colleague_user)
        res = self.client.get("/api/platform/crm/stats/me/")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["assigned"], 0)

    def test_two_claims_of_one_pool_lead_leave_one_owner(self):
        pool_lead = create_lead(
            store_name="محل في المخزن", phones=[{"raw": "0502222222", "kind": LeadPhone.Kind.PRIMARY}],
        )
        self.client.force_authenticate(user=self.owner_user)
        first = self.client.post(f"/api/platform/crm/leads/{pool_lead.pk}/claim/")
        self.assertEqual(first.status_code, 200, first.content)

        self.client.force_authenticate(user=self.colleague_user)
        second = self.client.post(f"/api/platform/crm/leads/{pool_lead.pk}/claim/")
        self.assertEqual(second.status_code, 409, second.content)

        pool_lead.refresh_from_db()
        self.assertEqual(pool_lead.assigned_to_id, self.owner.pk)


class LeadLockManagerOverrideTest(APITestCase):
    def test_manager_can_write_on_any_lead(self):
        manager = make_manager()
        owner_user, owner = make_staff_employee("lock-owner-2")
        lead = create_lead(store_name="محل المدير", phones=[{"raw": "0503333333", "kind": LeadPhone.Kind.PRIMARY}])
        lead.assigned_to = owner
        lead.save(update_fields=["assigned_to"])

        client = APIClient()
        client.force_authenticate(user=manager)
        res = client.post(f"/api/platform/crm/leads/{lead.pk}/status/", {"status": Lead.Status.CONTACTED}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
