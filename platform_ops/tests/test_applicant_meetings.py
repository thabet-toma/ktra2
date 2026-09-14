"""212-S1 — اجتماعاتُ المتقدّمين: دفترُ مقابلاتٍ قبل التوظيف.

طلبُ المالك: تبويبٌ رابعٌ على شاشة التوظيف المنصّيّ، يسجّل فيه وقتَ الاجتماع
ومَن حضر — متقدّماً جاء من رابط الوظيفة أو اسماً حرّاً لمن لم يأتِ منه —
**وملاحظةً على كلّ واحدٍ في كلّ اجتماع**. ومن خارجِه تُرى الاجتماعاتُ كلُّها،
والنقرُ على واحدٍ يفتح حاضريه بملاحظاتهم.

وما تحرسه هذه الاختباراتُ هو ما لا يمسكه المُسلسِلُ ولا الـ`tsc`: أنّ القواعدَ
في الخدمة لا في الشاشة، وأنّ معرّفَ حاضرٍ من اجتماعٍ آخر لا يُكتَب عليه من هنا.
"""
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from platform_ops.models import (
    ApplicantMeeting,
    ApplicantMeetingAttendee,
    JobApplicant,
    JobPosting,
    PlatformRecruiter,
)

MEETINGS = "/api/platform/ops/applicant-meetings/"


class ApplicantMeetingTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.recruiter_user = User.objects.create_user(username="meet-recruiter", password="x")
        PlatformRecruiter.objects.create(user=self.recruiter_user, is_active=True)
        self.client.force_authenticate(user=self.recruiter_user)

        self.job = JobPosting.objects.create(
            title="مدخل بيانات", description="إدخال مستندات", token="tok-meetings-1"
        )
        self.applicant = JobApplicant.objects.create(
            job=self.job, name="نور الهدى", phone="0790000001", reference_code="REF-M1"
        )
        self.other = JobApplicant.objects.create(
            job=self.job, name="سامر", phone="0790000002", reference_code="REF-M2"
        )

        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(hours=1)

    def _create_meeting(self, **over):
        payload = {
            "title": "مقابلة الدفعة الأولى",
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            **over,
        }
        return self.client.post(f"{MEETINGS}create/", payload, format="json")

    def _meeting_with(self, *applicants, guests=()):
        res = self._create_meeting()
        meeting_id = res.data["id"]
        for applicant in applicants:
            self.client.post(
                f"{MEETINGS}{meeting_id}/attendees/", {"applicant": applicant.pk}, format="json"
            )
        for guest in guests:
            self.client.post(
                f"{MEETINGS}{meeting_id}/attendees/", {"guest_name": guest}, format="json"
            )
        return meeting_id


class TheMeetingItselfTest(ApplicantMeetingTestBase):
    """جدولةُ الاجتماع: ما يقبله الخادمُ وما يردّه بنصٍّ يُقرأ."""

    def test_a_scheduled_meeting_comes_back_as_a_bare_list_the_client_can_map(self):
        """**الشكلُ جزءٌ من العقد لا تفصيلٌ**: `OptionalPageNumberPagination` لا
        تُغلِّف بلا `?page=`، وعميلُ الواجهة يمرّ بـ`apiGetList`.

        وتأكيدٌ يتسامح مع الشكلين (`data["results"] if isinstance(dict) else data`)
        لا يستطيع السقوطَ على تغيّرِ أحدهما — وهو ما كان مكتوباً هنا وأخفى أنّ
        العميلَ كان يقرأ الغلافَ مصفوفةً.
        """
        res = self._create_meeting(location="مكتب المنصّة — الطابق الثاني")
        self.assertEqual(res.status_code, 201, res.data)
        listing = self.client.get(MEETINGS)
        self.assertEqual(listing.status_code, 200)
        self.assertIsInstance(
            listing.data, list,
            "نقطةُ القائمة صارت مُغلَّفةً — عدِّل `listApplicantMeetings` معها في الـcommit نفسِه.",
        )
        self.assertEqual([row["title"] for row in listing.data], ["مقابلة الدفعة الأولى"])
        self.assertEqual(listing.data[0]["attendee_count"], 0)

    def test_a_place_is_not_forced_to_be_a_url(self):
        """مقابلةُ التوظيف تكون في مكتبٍ كما تكون على رابط.

        `URLField` كان ليردّ «مكتب المنصّة — الطابق الثاني» بأربعمئة، وهو
        المكانُ الأغلبُ لمقابلةٍ أولى.
        """
        res = self._create_meeting(location="مكتب المنصّة — الطابق الثاني")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["location"], "مكتب المنصّة — الطابق الثاني")

    def test_an_end_before_its_start_is_refused_in_arabic_not_by_five_hundred(self):
        """القيدُ على القاعدة يحمي الكتابةَ المباشرة، والفحصُ في الخدمة يحمي القارئ."""
        res = self._create_meeting(end=(self.start - timedelta(hours=1)).isoformat())
        self.assertEqual(res.status_code, 400, res.data)
        self.assertIn("end", res.data)

    def test_the_database_refuses_a_backwards_window_written_directly(self):
        """لأنّ `clean()` لا يحمي `bulk_create` ولا كتابةً من الـshell."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ApplicantMeeting.objects.create(
                    title="مقلوب", start=self.end, end=self.start
                )

    def test_editing_the_time_does_not_wipe_the_agenda(self):
        """‏`None` تعني «لم يُرسَل» لا «امسحه» — وإلاّ ضاع نصٌّ بتعديل وقت."""
        res = self._create_meeting(agenda="أسئلةُ الجولة الأولى")
        meeting_id = res.data["id"]
        moved = self.client.post(
            f"{MEETINGS}{meeting_id}/update/",
            {"start": (self.start + timedelta(days=1)).isoformat(),
             "end": (self.end + timedelta(days=1)).isoformat()},
            format="json",
        )
        self.assertEqual(moved.status_code, 200, moved.data)
        self.assertEqual(moved.data["agenda"], "أسئلةُ الجولة الأولى")

    def test_a_malformed_edit_payload_answers_four_hundred_not_five_hundred(self):
        """مفتاحٌ اسمُه `meeting` في الحمولة كان يصطدم بوسيط الدالّة نفسِه.

        ‏`update_applicant_meeting(meeting=…, **request.data)` تسقط بـ
        `TypeError` — خمسمئةٌ على طلبٍ مشوّه. والقائمةُ الصريحةُ تتجاهله.
        """
        meeting_id = self._create_meeting().data["id"]
        res = self.client.post(
            f"{MEETINGS}{meeting_id}/update/",
            {"meeting": 99, "self": 1, "title": "عنوانٌ جديد"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["title"], "عنوانٌ جديد")

    def test_a_title_cannot_be_blanked_by_an_edit(self):
        meeting_id = self._create_meeting().data["id"]
        res = self.client.post(f"{MEETINGS}{meeting_id}/update/", {"title": "   "}, format="json")
        self.assertEqual(res.status_code, 400, res.data)

    def test_moving_only_the_start_is_compared_against_the_stored_end(self):
        """طرفٌ واحدٌ من النافذة يصل نصّاً، والآخرُ يُقرأ من الصفّ `datetime`.

        ومقارنتُهما كما وصلا ترفع `TypeError` — خمسمئةٌ على طلبٍ مشروع. فمن
        أراد تأجيلَ البدايةِ وحدَها إلى ما بعد النهاية يجب أن يقرأ «النهايةُ
        يجب أن تكون بعد بدايته»، ومن أجّلها دقيقةً واحدةً يجب أن ينجح.
        """
        meeting_id = self._create_meeting().data["id"]

        late = self.client.post(
            f"{MEETINGS}{meeting_id}/update/",
            {"start": (self.end + timedelta(hours=2)).isoformat()},
            format="json",
        )
        self.assertEqual(late.status_code, 400, late.data)
        self.assertIn("end", late.data)

        nudged = self.client.post(
            f"{MEETINGS}{meeting_id}/update/",
            {"start": (self.start + timedelta(minutes=1)).isoformat()},
            format="json",
        )
        self.assertEqual(nudged.status_code, 200, nudged.data)

    def test_an_unreadable_datetime_answers_four_hundred_not_five_hundred(self):
        """نصٌّ ليس وقتاً — من حقلٍ فارغٍ أو عميلٍ غيرِ شاشتنا."""
        res = self._create_meeting(start="غداً بعد الظهر")
        self.assertEqual(res.status_code, 400, res.data)
        self.assertIn("start", res.data)


class WhoWasInTheRoomTest(ApplicantMeetingTestBase):
    """هويّةُ الحاضر: متقدّمٌ من الرابط **أو** اسمٌ حرّ، لا الاثنان ولا لا شيء."""

    def test_an_applicant_from_the_link_is_named_by_his_own_row(self):
        meeting_id = self._meeting_with(self.applicant)
        detail = self.client.get(f"{MEETINGS}{meeting_id}/")
        attendee = detail.data["attendees"][0]
        self.assertEqual(attendee["name"], "نور الهدى")
        self.assertEqual(attendee["job_title"], "مدخل بيانات")
        self.assertEqual(attendee["status"], ApplicantMeetingAttendee.Status.INVITED)

    def test_a_guest_who_never_came_through_the_link_is_free_text(self):
        """طلبُ المالك حرفيّاً: «يا من المتقدّمين أو عادي إذا تكست فري»."""
        meeting_id = self._meeting_with(guests=["ضيفٌ بتوصية"])
        detail = self.client.get(f"{MEETINGS}{meeting_id}/")
        attendee = detail.data["attendees"][0]
        self.assertEqual(attendee["name"], "ضيفٌ بتوصية")
        self.assertIsNone(attendee["applicant"])

    def test_neither_both_identities_nor_none_of_them(self):
        meeting_id = self._create_meeting().data["id"]
        both = self.client.post(
            f"{MEETINGS}{meeting_id}/attendees/",
            {"applicant": self.applicant.pk, "guest_name": "اسمٌ آخر"},
            format="json",
        )
        neither = self.client.post(f"{MEETINGS}{meeting_id}/attendees/", {}, format="json")
        self.assertEqual(both.status_code, 400, both.data)
        self.assertEqual(neither.status_code, 400, neither.data)

    def test_the_database_refuses_a_row_carrying_both_identities(self):
        meeting = ApplicantMeeting.objects.create(
            title="مباشر", start=self.start, end=self.end
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ApplicantMeetingAttendee.objects.create(
                    meeting=meeting, applicant=self.applicant, guest_name="اسمٌ آخر"
                )

    def test_the_same_applicant_is_not_listed_twice_in_one_meeting(self):
        """صفّان للشخص نفسِه يعنيان ملاحظتين متنافستين على الجلسة نفسِها."""
        meeting_id = self._meeting_with(self.applicant)
        again = self.client.post(
            f"{MEETINGS}{meeting_id}/attendees/", {"applicant": self.applicant.pk}, format="json"
        )
        self.assertEqual(again.status_code, 400, again.data)

    def test_a_hired_applicant_cannot_be_added_because_these_meetings_are_before_hiring(self):
        """«هاي الاجتماعات للمتقدّمين الي لسا مش موظّفين»."""
        self.applicant.status = JobApplicant.Status.HIRED
        self.applicant.save(update_fields=["status"])
        meeting_id = self._create_meeting().data["id"]
        res = self.client.post(
            f"{MEETINGS}{meeting_id}/attendees/", {"applicant": self.applicant.pk}, format="json"
        )
        self.assertEqual(res.status_code, 400, res.data)

    def test_hiring_someone_later_does_not_erase_the_meeting_he_attended(self):
        """الفحصُ لحظةَ الإضافة وحدَها: الفحصُ الرجعيُّ يمحو تاريخاً وقع فعلاً."""
        meeting_id = self._meeting_with(self.applicant)
        self.applicant.status = JobApplicant.Status.HIRED
        self.applicant.save(update_fields=["status"])
        detail = self.client.get(f"{MEETINGS}{meeting_id}/")
        self.assertEqual(detail.data["attendees"][0]["name"], "نور الهدى")
        self.assertEqual(detail.data["attendees"][0]["applicant_status"], "hired")


class TheNoteOnEachPersonTest(ApplicantMeetingTestBase):
    """الغرضُ من الجدول كلِّه: رأيٌ في **هذا** الشخص في **هذا** الاجتماع."""

    def test_attendance_and_a_note_are_recorded_on_one_person(self):
        meeting_id = self._meeting_with(self.applicant, self.other)
        detail = self.client.get(f"{MEETINGS}{meeting_id}/")
        target = detail.data["attendees"][0]["id"]

        res = self.client.post(
            f"{MEETINGS}{meeting_id}/record/",
            {"attendee": target, "status": "attended", "note": "هادئٌ ويجيب بدقّة."},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        rows = {row["id"]: row for row in res.data["attendees"]}
        self.assertEqual(rows[target]["status"], "attended")
        self.assertEqual(rows[target]["note"], "هادئٌ ويجيب بدقّة.")
        # والآخرُ لم يُمَسّ: الكتابةُ على شخصٍ لا تكتب على جاره.
        neighbour = next(row for row in res.data["attendees"] if row["id"] != target)
        self.assertEqual(neighbour["status"], "invited")
        self.assertEqual(neighbour["note"], "")

    def test_the_note_survives_a_later_attendance_change(self):
        """الحقلان مستقلّان: تصحيحُ الحضور لا يمسح رأياً كُتب."""
        meeting_id = self._meeting_with(self.applicant)
        target = self.client.get(f"{MEETINGS}{meeting_id}/").data["attendees"][0]["id"]
        self.client.post(
            f"{MEETINGS}{meeting_id}/record/",
            {"attendee": target, "note": "مرشَّحٌ قويّ"}, format="json",
        )
        res = self.client.post(
            f"{MEETINGS}{meeting_id}/record/",
            {"attendee": target, "status": "absent"}, format="json",
        )
        self.assertEqual(res.data["attendees"][0]["note"], "مرشَّحٌ قويّ")
        self.assertEqual(res.data["attendees"][0]["status"], "absent")

    def test_the_default_is_invited_not_absent(self):
        """بوليانٌ افتراضُه `false` يقول «لم يحضر» عن اجتماعٍ لم يبدأ بعد.

        من يفتح جدولَ اجتماعِ الغد يقرأ غياباً لم يقع — و«مدعوّ» حالةٌ ثالثةٌ
        صادقةٌ تمنع الكذبة.
        """
        meeting_id = self._meeting_with(self.applicant)
        detail = self.client.get(f"{MEETINGS}{meeting_id}/")
        self.assertEqual(detail.data["attendees"][0]["status"], "invited")
        self.assertEqual(detail.data["attendees"][0]["status_display"], "مدعوّ")

    def test_an_unknown_attendance_state_is_refused(self):
        meeting_id = self._meeting_with(self.applicant)
        target = self.client.get(f"{MEETINGS}{meeting_id}/").data["attendees"][0]["id"]
        res = self.client.post(
            f"{MEETINGS}{meeting_id}/record/",
            {"attendee": target, "status": "maybe"}, format="json",
        )
        self.assertEqual(res.status_code, 400, res.data)

    def test_a_note_cannot_be_written_on_an_attendee_of_another_meeting(self):
        """**العطبُ الذي يُبحَث عنه هنا:** معرّفُ صفٍّ يُقرأ من الجدول كلِّه.

        `attendees.filter(pk=…)` تبحث داخلَ الاجتماع، و`Attendee.objects.get`
        كانت لتكتب على حاضرٍ في اجتماعٍ آخر بمعرّفٍ مخمَّنٍ بالعدّ.
        """
        mine = self._meeting_with(self.applicant)
        theirs = self._meeting_with(self.other)
        foreign = self.client.get(f"{MEETINGS}{theirs}/").data["attendees"][0]["id"]

        res = self.client.post(
            f"{MEETINGS}{mine}/record/",
            {"attendee": foreign, "note": "كتابةٌ عابرة"}, format="json",
        )
        self.assertEqual(res.status_code, 404, res.data)
        untouched = self.client.get(f"{MEETINGS}{theirs}/").data["attendees"][0]
        self.assertEqual(untouched["note"], "")

    def test_removing_an_attendee_takes_his_note_with_him(self):
        meeting_id = self._meeting_with(self.applicant, self.other)
        target = self.client.get(f"{MEETINGS}{meeting_id}/").data["attendees"][0]["id"]
        res = self.client.post(
            f"{MEETINGS}{meeting_id}/remove-attendee/", {"attendee": target}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["attendee_count"], 1)
        self.assertNotIn(target, [row["id"] for row in res.data["attendees"]])


class TheDoorToTheMeetingsTest(ApplicantMeetingTestBase):
    """البابُ بابُ الشاشة نفسِها — لا بابٌ رابعٌ ولا بابٌ مفتوح."""

    def test_a_signed_in_stranger_is_refused(self):
        stranger = User.objects.create_user(username="stranger-meet", password="x")
        client = APIClient()
        client.force_authenticate(user=stranger)
        self.assertEqual(client.get(MEETINGS).status_code, 403)
        self.assertEqual(
            client.post(f"{MEETINGS}create/", {"title": "x"}, format="json").status_code, 403
        )

    def test_the_super_admin_reaches_them_as_he_reaches_everything(self):
        """«السوبر أدمن بسجّل» — وهو يمرّ من `IsPlatformRecruiter` لا حولَه."""
        admin = User.objects.create_superuser(username="meet-admin", password="x")
        client = APIClient()
        client.force_authenticate(user=admin)
        self.assertEqual(client.get(MEETINGS).status_code, 200)

    def test_no_cv_link_leaks_through_the_attendee_row(self):
        """رابطُ السيرة هو الصلاحية — فمن يقرؤه يقرأ سيرةَ إنسانٍ كائناً من كان.

        الجدولُ الجديدُ بابٌ جديدٌ إلى صفِّ المتقدّم، ونسخُ حقولِه بلا تمييزٍ
        كان ليُسرّب ما حُجب في كلّ مُسلسِلٍ آخر.
        """
        self.applicant.cv_url = "https://files.example.test/secret-cv.pdf"
        self.applicant.save(update_fields=["cv_url"])
        meeting_id = self._meeting_with(self.applicant)
        body = self.client.get(f"{MEETINGS}{meeting_id}/").content.decode("utf-8")
        self.assertNotIn("secret-cv", body)
        self.assertNotIn("cv_url", body)


class ThePickerDoesNotOfferWhatTheServerRefusesTest(TestCase):
    """حارسٌ ساكنٌ — `tsc` لا يقرأ ما يُملأ به `<select>`.

    الخدمةُ تردّ ٤٠٠ على إضافة من صار موظّفاً، وقائمةُ `job-applicants`
    تشمل الجميع. فمنتقٍ يُغذّى منها بلا تضييقٍ يعرض خياراً **يفشل كلَّما اختير**
    — وهو بعينه عطبُ «زرٍّ يَعِد بما لا يملكه ناقرُه» الذي أُصلح في 212-Q2-ب.
    """

    DETAIL = (
        Path(__file__).resolve().parents[2]
        / "frontend_v2" / "components" / "platform-hiring" / "PlatformMeetingDetail.tsx"
    )

    def test_the_applicant_picker_is_narrowed_before_it_is_rendered(self):
        source = self.DETAIL.read_text(encoding="utf-8")
        start = source.index("<select")
        end = source.index("</select>", start)
        picker = source[start:end]
        violations = []
        if "selectableApplicants.map(" not in picker:
            violations.append("قائمةُ الخيارات لا تُغذّى من `selectableApplicants`")
        if "{applicants.map(" in picker:
            violations.append("قائمةُ الخيارات تُغذّى من `applicants` الخام")
        self.assertEqual(violations, [], " · ".join(violations))

    def test_the_status_the_picker_hides_is_the_status_the_service_refuses(self):
        """النصُّ في الواجهة مربوطٌ بالثابت في الخادم فلا يفترقان بصمت."""
        source = self.DETAIL.read_text(encoding="utf-8")
        hidden = f'applicant.status !== "{JobApplicant.Status.HIRED.value}"'
        self.assertIn(
            hidden,
            source,
            "التضييقُ في المنتقي يخفي حالةً غيرَ التي ترفضها `add_meeting_attendee`.",
        )


class TheRaceTheCheckCannotWinTest(ApplicantMeetingTestBase):
    """‏**«افحص ثمّ اكتب» تسابق نفسَها — والقيدُ في القاعدة هو الحَكَم.**

    `add_meeting_attendee` تفحص بـ`exists()` ثمّ تكتب. طلبان متزامنان يعبران
    الفحصَ كلاهما قبل أن يكتب أيٌّ منهما ⇒ صفّان لشخصٍ واحدٍ في اجتماعٍ واحد،
    أي ملاحظتان متنافستان عليه. وصارت القاعدةُ تمنع ذلك — لكنّ `IntegrityError`
    عارياً يخرج للمستخدم **خمسمئة** على طلبٍ مشروعٍ خسر السباق.

    **والسباقُ يُحاكى بتعمية الفحص لا بتزييف الخطأ**: `side_effect=IntegrityError`
    على `create` يرفع خطأً بايثونيّاً لا يمسّ الاتصال، فيمرّ الاختبارُ وإن نُزعت
    نقطةُ الحفظ — أي تأكيدٌ لا يستطيع السقوطَ لسببه. فيُكتب الصفُّ الأوّلُ فعلاً،
    ويُعمَّى `exists()` وحدَه، فيقع خطأُ القاعدة **حقيقيّاً** كما يقع في السباق.
    """

    BLIND = "django.db.models.query.QuerySet.exists"

    def _existing_meeting(self):
        meeting_id = self._meeting_with(self.applicant)
        return ApplicantMeeting.objects.get(pk=meeting_id)

    def test_a_write_that_loses_the_race_answers_four_hundred_with_the_same_message(self):
        from unittest import mock

        from rest_framework.exceptions import ValidationError as DRFValidationError

        from platform_ops.services import add_meeting_attendee

        meeting = self._existing_meeting()
        with mock.patch(self.BLIND, return_value=False):
            with self.assertRaises(DRFValidationError) as caught:
                add_meeting_attendee(meeting=meeting, applicant_id=self.applicant.pk)

        self.assertIn("سلفاً", str(caught.exception.detail))
        self.assertEqual(meeting.attendees.count(), 1)

    def test_the_losing_write_does_not_poison_the_surrounding_transaction(self):
        """ترجمةُ الخطأ إلى رسالةٍ لا تنفع إن بقيت المعاملةُ فاسدةً بعدها.

        جانغو يمنع أيّ استعلامٍ في معاملةٍ أفسدها خطأُ قاعدة، فيرى المستدعي
        `TransactionManagementError` بدل الرسالة التي صيغت له. وما يحمي ذلك هنا
        `@transaction.atomic` أعلى `add_meeting_attendee`: نقطةُ حفظٍ يرتدّ إليها
        الخطأُ فتبقى معاملةُ المستدعي صالحة. ويسقط هذا الاختبارُ لحظةَ نزعها.
        """
        from unittest import mock

        from rest_framework.exceptions import ValidationError as DRFValidationError

        from platform_ops.services import add_meeting_attendee

        meeting = self._existing_meeting()
        with transaction.atomic():
            with mock.patch(self.BLIND, return_value=False):
                with self.assertRaises(DRFValidationError):
                    add_meeting_attendee(meeting=meeting, applicant_id=self.applicant.pk)
            # المعاملةُ ما زالت صالحةً للكتابة — وهذا كلُّ الفرق.
            ApplicantMeetingAttendee.objects.create(
                meeting=meeting, guest_name="حاضرٌ بعد الخطأ"
            )
        self.assertEqual(meeting.attendees.count(), 2)


class TheAttendeeConstraintIsRealOnBothEnginesTest(TestCase):
    """يتجاوز طبقةَ الخدمة عمداً: الحراسةُ البايثونيّةُ تُفحص في مكانها،

    وهذا الملفُّ يسأل سؤالاً آخر — **هل يمنع الجدولُ نفسُه؟** فالخدمةُ تفحص ثمّ
    تكتب، وطلبان متزامنان يعبران الفحصَ كلاهما قبل أن يكتب أيٌّ منهما.
    """

    @classmethod
    def setUpTestData(cls):
        cls.job = JobPosting.objects.create(
            title="وظيفة", description="وصف", token="tok-uniq-1"
        )
        cls.applicant = JobApplicant.objects.create(
            job=cls.job, name="متقدّم", phone="0500", reference_code="REF-UNIQ-1"
        )
        now = timezone.now()
        cls.meeting = ApplicantMeeting.objects.create(
            title="مقابلة", start=now, end=now + timezone.timedelta(hours=1)
        )
        cls.other_meeting = ApplicantMeeting.objects.create(
            title="مقابلة ثانية", start=now, end=now + timezone.timedelta(hours=1)
        )

    def test_the_same_applicant_cannot_be_written_twice_into_one_meeting(self):
        ApplicantMeetingAttendee.objects.create(
            meeting=self.meeting, applicant=self.applicant
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ApplicantMeetingAttendee.objects.create(
                    meeting=self.meeting, applicant=self.applicant
                )

    def test_the_same_guest_name_cannot_be_written_twice_into_one_meeting(self):
        ApplicantMeetingAttendee.objects.create(
            meeting=self.meeting, guest_name="ضيف من خارج الرابط"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ApplicantMeetingAttendee.objects.create(
                    meeting=self.meeting, guest_name="ضيف من خارج الرابط"
                )

    def test_the_same_person_in_two_meetings_is_the_whole_point_and_stays_allowed(self):
        """القيدُ لو ضاق صار يمنع ما وُجد الجدولُ لأجله: مقابلتان لمتقدّمٍ واحد."""
        ApplicantMeetingAttendee.objects.create(
            meeting=self.meeting, applicant=self.applicant
        )
        ApplicantMeetingAttendee.objects.create(
            meeting=self.other_meeting, applicant=self.applicant
        )
        ApplicantMeetingAttendee.objects.create(
            meeting=self.meeting, guest_name="ضيف"
        )
        ApplicantMeetingAttendee.objects.create(
            meeting=self.other_meeting, guest_name="ضيف"
        )
        self.assertEqual(ApplicantMeetingAttendee.objects.count(), 4)

    def test_an_applicant_and_a_guest_never_collide_in_the_one_column(self):
        """الهويّتان تسكنان عموداً واحداً، فلا بدّ من بادئةٍ تفصلهما.

        بلا بادئةٍ يصير متقدّمٌ رقمُه ٧ وضيفٌ اسمُه «٧» هويّةً واحدةً، فيمنع
        القيدُ إضافةَ أحدهما بلا سبب.
        """
        attendee = ApplicantMeetingAttendee.objects.create(
            meeting=self.meeting, applicant=self.applicant
        )
        guest = ApplicantMeetingAttendee.objects.create(
            meeting=self.meeting, guest_name=str(self.applicant.pk)
        )
        attendee.refresh_from_db()
        guest.refresh_from_db()
        self.assertNotEqual(attendee.identity_key, guest.identity_key)
        self.assertEqual(attendee.identity_key, f"a:{self.applicant.pk}")
        self.assertEqual(guest.identity_key, f"g:{self.applicant.pk}")
