"""إشعار الدفع — #285، معياراً بمعيار.

**ما يثبته هذا الملف:**

1. **التجميع:** زبونٌ عليه ق.م 1,200 واقتطاعُ رواتب 300 بتاريخٍ واحد ⇒ إشعارٌ واحد
   بسطرين ومجموع 1,500 «عليك».
2. **«إلك»:** رصيدُ ق.م لصالحه يظهر «إلك» أخضر — والإشارةُ من `direction` القائم
   في `Obligation` لا من نصّ الشاشة.
3. **الرمادي:** 7 شيكل رماديٌّ بالحدّ الافتراضي 10، والحدُّ نفسه (`<=`) رماديّ.
4. **الورقةُ المصيَّرة:** تحمل العنوانَ الثابت، واللونُ يُفحص على الورقة **وعلى
   الدالّة الخالصة** `payment_notice_tone`.
5. **الإرفاق:** إطفاءُ `payment_notice_attach` لزبونٍ يُخرج الإشعارَ من رسالته
   وحدها، ويبقى بندُ «موعد رسمي قريب» كما هو.

**ولا ساعةَ حقيقية:** كلُّ يومٍ يُمرَّر صريحاً إلى الدالّة، والتواريخُ ثابتة (شباط
2026). والشجرةُ (مكتبٌ جاهزٌ وزبونٌ بجهته الرئيسية) تُعاد استعمالاً من `OfficeFixture`
في `test_appointments.py` بدل نسخةٍ ثانية منها.
"""
import datetime
from decimal import Decimal

from django.db import connection
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext

from accounting_office import appointments, services, settings_registry
from accounting_office.models import (
    OBLIGATION_DIRECTION_DUE,
    OBLIGATION_DIRECTION_REFUND,
    OBLIGATION_STATUS_SUBMITTED,
    REMINDER_DEADLINE,
    Obligation,
)
from accounting_office.tests.test_appointments import (
    DUE,
    JAN_END,
    JAN_START,
    SEVEN_DAYS_BEFORE,
    OfficeFixture,
)
from docshare import services as docshare_services
from docshare.models import DOC_PAYMENT_NOTICE, DocumentShare

#: الفترةُ الثانية — الالتزامُ مفتاحُه (زبون، فترة) والإشعارُ (زبون، تاريخ)، فتاريخٌ
#: واحدٌ يفتح بندين حين تختلف الفترتان (م١).
FEB_START = datetime.date(2026, 2, 1)
FEB_END = datetime.date(2026, 2, 28)


class PaymentNoticeToneTest(SimpleTestCase):
    """د4: دالّةُ اللون **نقيّة** — الحالاتُ المحسومة وحدها، بلا قاعدة بيانات."""

    def test_a_large_owed_amount_is_red(self):
        self.assertEqual(
            appointments.payment_notice_tone(Decimal("1500"), Decimal("10")), "owed",
        )

    def test_a_negative_amount_is_green(self):
        self.assertEqual(
            appointments.payment_notice_tone(Decimal("-300"), Decimal("10")), "refund",
        )

    def test_an_amount_under_the_threshold_is_gray(self):
        self.assertEqual(
            appointments.payment_notice_tone(Decimal("7"), Decimal("10")), "neutral",
        )

    def test_the_threshold_itself_is_gray_because_it_is_inclusive(self):
        self.assertEqual(
            appointments.payment_notice_tone(Decimal("10"), Decimal("10")), "neutral",
        )

    def test_the_gray_band_wins_over_the_sign_on_the_negative_side_too(self):
        self.assertEqual(
            appointments.payment_notice_tone(Decimal("-10"), Decimal("10")), "neutral",
        )


class PaymentNoticeSettingsTest(SimpleTestCase):
    """د2: ثلاثةُ مفاتيحَ في السجلّ، بمستوى المكتب والزبون كسائر إعدادات التذكير."""

    def test_the_attachment_toggle_is_a_boolean_on_by_default(self):
        definition = settings_registry.SETTINGS_REGISTRY["payment_notice_attach"]
        self.assertEqual(definition.kind, settings_registry.KIND_BOOL)
        self.assertIs(definition.default, True)
        self.assertEqual(definition.levels, ("office", "client"))
        self.assertEqual(definition.group, settings_registry.GROUP_REMINDERS)

    def test_the_format_is_one_of_text_pdf_or_both_and_defaults_to_both(self):
        definition = settings_registry.SETTINGS_REGISTRY["payment_notice_format"]
        self.assertEqual(definition.kind, settings_registry.KIND_CHOICE)
        self.assertEqual(definition.choices, ("text", "pdf", "both"))
        self.assertEqual(definition.default, "both")
        self.assertEqual(definition.levels, ("office", "client"))

    def test_the_gray_threshold_defaults_to_ten_and_never_goes_below_zero(self):
        definition = settings_registry.SETTINGS_REGISTRY["payment_notice_gray_threshold"]
        self.assertEqual(definition.default, 10)
        self.assertEqual(definition.min_value, 0)
        self.assertEqual(definition.levels, ("office", "client"))


class PaymentNoticeFixture(OfficeFixture):
    """مكتبٌ جاهز + إشعارٌ بسطرٍ واحد — والاسمُ يُكتب بعد الإنشاء.

    `add_obligation` في `test_appointments` يثبّت الاسم على سطر اللائحة
    (`דוח תקופתי`)، وهذا الملفّ يريد أسماءً تميّز السطرين («ض.ق.م» و«اقتطاع
    الرواتب») فيقرأها القارئ على الورقة. وتحديثُ الاسم مباشرةً **لا** يغيّر ما
    يقيسه `add_obligation` (التاريخُ والمبلغُ والاتجاه).
    """

    def add_line(
        self, client, *, name, amount, service_code="vat",
        direction=OBLIGATION_DIRECTION_DUE, actual=DUE,
        status=None, client_paid=False,
        period_start=JAN_START, period_end=JAN_END,
    ):
        kwargs = {}
        if status is not None:
            kwargs["status"] = status
        obligation = self.add_obligation(
            client, actual=actual, amount=amount, direction=direction,
            service_code=service_code, client_paid=client_paid,
            period_start=period_start, period_end=period_end, **kwargs,
        )
        Obligation.objects.filter(pk=obligation.pk).update(name=name)
        obligation.name = name
        return obligation

    def contacted_client(self, name, contact_name):
        """زبونٌ وجهةٌ رئيسيةٌ باسمٍ مميّز — رسالتان في اليوم تُقرأان بالاسم."""
        client = self.make_client(name)
        self.link(client, self.make_contact(contact_name))
        return client

    def deadline_items(self, day=SEVEN_DAYS_BEFORE):
        return [
            item for item in self.items(day)
            if item["reminder_type"] == REMINDER_DEADLINE
        ]

    def notice(self, day=SEVEN_DAYS_BEFORE):
        items = self.deadline_items(day)
        self.assertEqual(len(items), 1, items)
        return items[0]["notice"]


# ── المعيار ١: التجميع ──────────────────────────────────────────────────────
class PaymentNoticeGroupingTest(PaymentNoticeFixture):
    def test_a_vat_amount_and_a_payroll_withholding_on_one_date_are_one_notice(self):
        client = self.ready_client()
        self.add_line(client, name="ض.ق.م", amount=Decimal("1200.00"))
        self.add_line(
            client, name="اقتطاع الرواتب", amount=Decimal("300.00"),
            service_code="payroll",
        )

        notice = self.notice()

        self.assertEqual(notice["date"], DUE.isoformat())
        self.assertEqual(
            [line["label"] for line in notice["lines"]],
            ["ض.ق.م", "اقتطاع الرواتب"],
        )
        self.assertEqual(notice["total"], "1500.00")
        self.assertEqual(notice["tone"], "owed")
        self.assertEqual(notice["direction_label"], "عليك")

    def test_an_obligation_that_moved_on_is_not_a_line_of_the_notice(self):
        """«انقدّم» ليس مستحقّاً: سطرٌ لا يظهر على إشعار دفع."""
        client = self.ready_client()
        self.add_line(client, name="ض.ق.م", amount=Decimal("1200.00"))
        self.add_line(
            client, name="اقتطاع الرواتب", amount=Decimal("300.00"),
            service_code="payroll", status=OBLIGATION_STATUS_SUBMITTED,
        )

        notice = self.notice()

        self.assertEqual([line["label"] for line in notice["lines"]], ["ض.ق.م"])
        self.assertEqual(notice["total"], "1200.00")

    def test_a_zero_amount_is_not_a_line(self):
        client = self.ready_client()
        self.add_line(client, name="ض.ق.م", amount=Decimal("1200.00"))
        self.add_line(
            client, name="اقتطاع الرواتب", amount=Decimal("0.00"),
            service_code="payroll",
        )

        self.assertEqual([line["label"] for line in self.notice()["lines"]], ["ض.ق.م"])

    def test_a_paid_amount_is_not_a_line_of_the_notice(self):
        """«الزبون دفع» ليس مستحقّاً — الإشعارُ لا يطالب بمالٍ سُدِّد."""
        client = self.ready_client()
        self.add_line(client, name="ض.ق.م", amount=Decimal("1200.00"))
        self.add_line(
            client, name="اقتطاع الرواتب", amount=Decimal("300.00"),
            service_code="payroll", client_paid=True,
        )

        notice = self.notice()

        self.assertEqual([line["label"] for line in notice["lines"]], ["ض.ق.م"])
        self.assertEqual(notice["total"], "1200.00")

    def test_a_second_date_opens_a_second_notice(self):
        """«واحدٌ لكل زبونٍ لكل تاريخ استحقاق» — تاريخان ⇒ إشعاران لا إشعار."""
        client = self.ready_client()
        later = DUE + datetime.timedelta(days=20)
        self.add_line(client, name="ض.ق.م", amount=Decimal("1200.00"))
        self.add_line(
            client, name="اقتطاع الرواتب", amount=Decimal("300.00"),
            service_code="payroll", actual=later,
        )

        first = self.notice(SEVEN_DAYS_BEFORE)
        second = self.notice(later - datetime.timedelta(days=7))

        self.assertEqual(first["date"], DUE.isoformat())
        self.assertEqual([line["label"] for line in first["lines"]], ["ض.ق.م"])
        self.assertEqual(second["date"], later.isoformat())
        self.assertEqual(
            [line["label"] for line in second["lines"]], ["اقتطاع الرواتب"],
        )

    def test_two_periods_owing_on_one_date_carry_one_notice_not_two(self):
        """م١: بندان لفترتين بتاريخٍ واحد ⇒ **إشعارٌ واحد** لا إشعاران متطابقان.

        البندُ يُفتح لكل (زبون، **فترة**) والإشعارُ يُجمع لكل (زبون، **تاريخ**)،
        فربعيّةٌ وشهريّةٌ تستحقّان في اليوم نفسه تعطيان بندين بمفتاحٍ واحد: كان
        الإشعارُ يُركَّب على كلٍّ منهما، فيخرج العنوانُ والمجموعُ مرّتين في الرسالة
        المدمجة وإشعاران في `items[]`. الحارسُ مفتاحُ (زبون، تاريخ): أوّلُ بندٍ
        يحمله والباقي `None`.
        """
        client = self.ready_client()
        self.add_line(client, name="ض.ق.م", amount=Decimal("1200.00"))
        self.add_line(
            client, name="اقتطاع الرواتب", amount=Decimal("300.00"),
            service_code="payroll", period_start=FEB_START, period_end=FEB_END,
        )

        items = self.deadline_items()
        body = self.ready(SEVEN_DAYS_BEFORE)["messages"][0]["body"]

        self.assertEqual(len(items), 2, items)
        self.assertEqual(body.count(appointments.PAYMENT_NOTICE_TITLE), 1)
        self.assertEqual(
            len([item for item in items if item["notice"] is not None]), 1, items,
        )
        # والأوّلُ هو من يحمله — لا آخرُ بندٍ في الترتيب.
        self.assertIsNotNone(items[0]["notice"], items)
        self.assertEqual(items[0]["notice"]["total"], "1500.00")


# ── المعيار ٢: «إلك» ────────────────────────────────────────────────────────
class PaymentNoticeCreditTest(PaymentNoticeFixture):
    def credit_and_withholding(self):
        client = self.ready_client()
        # رصيدُ ق.م لصالحه (مرتجع) مع اقتطاعٍ مستحقّ: البندَ يفتحه المستحقّ وحده،
        # والسطرُ المرتجعُ يظهر بإشارته — والمجموعُ صار «إلك».
        self.add_line(
            client, name="ض.ق.م", amount=Decimal("800.00"),
            direction=OBLIGATION_DIRECTION_REFUND,
        )
        self.add_line(
            client, name="اقتطاع الرواتب", amount=Decimal("300.00"),
            service_code="payroll",
        )
        return client

    def test_a_vat_balance_in_the_clients_favour_reads_as_owed_to_the_client(self):
        self.credit_and_withholding()

        notice = self.notice()

        self.assertEqual([line["tone"] for line in notice["lines"]], ["refund", "owed"])
        self.assertEqual(notice["total"], "-500.00")
        self.assertEqual(notice["tone"], "refund")
        self.assertEqual(notice["direction_label"], "إلك")

    def test_the_credit_is_written_with_its_own_word_in_the_message_text(self):
        self.credit_and_withholding()

        body = self.ready(SEVEN_DAYS_BEFORE)["messages"][0]["body"]

        self.assertIn("800.00 إلك", body)
        self.assertIn("500.00 إلك", body)

    def test_a_date_that_is_all_credit_opens_no_item_but_the_notice_is_green(self):
        """حدُّ القاعدة: مرتجعٌ وحده ليس «عليه شيء»، فلا يفتح بندَ موعد — والإشعارُ
        نفسُه (لو طُلب بذاته) أخضرُ سالب. الفرقُ قرارُ `client_owes` لا قرارُ لون."""
        client = self.ready_client()
        self.add_line(
            client, name="ض.ق.م", amount=Decimal("300.00"),
            direction=OBLIGATION_DIRECTION_REFUND,
        )

        self.assertEqual(self.deadline_items(), [])
        notice = appointments.payment_notice(self.tenant, client_id=client.pk, due=DUE)
        self.assertEqual(notice["total"], Decimal("-300.00"))
        self.assertEqual(notice["tone"], "refund")
        self.assertEqual(notice["direction_label"], "إلك")
        # ولم يُنشَأ رابطٌ لبندٍ لم يظهر.
        self.assertFalse(
            DocumentShare.objects.filter(doc_type=DOC_PAYMENT_NOTICE).exists(),
        )


# ── المعيار ٣: الرمادي ──────────────────────────────────────────────────────
class PaymentNoticeGrayTest(PaymentNoticeFixture):
    def test_seven_shekels_under_the_default_threshold_of_ten_is_gray(self):
        client = self.ready_client()
        self.add_line(client, name="ض.ق.م", amount=Decimal("7.00"))

        notice = self.notice()

        self.assertEqual(notice["total"], "7.00")
        self.assertEqual(notice["tone"], "neutral")

    def test_the_threshold_is_per_client_so_a_client_override_colours_it_red(self):
        client = self.ready_client()
        services.set_client_setting(client, "payment_notice_gray_threshold", 5)
        self.add_line(client, name="ض.ق.م", amount=Decimal("7.00"))

        self.assertEqual(self.notice()["tone"], "owed")


# ── المعيار ٤: الورقةُ المصيَّرة ────────────────────────────────────────────
class PaymentNoticePageTest(PaymentNoticeFixture):
    def page_of(self, anchor):
        share = docshare_services.create_share(
            self.tenant, DOC_PAYMENT_NOTICE, anchor.pk,
        )
        response = self.client.get(f"/s/{share.token}")
        self.assertEqual(response.status_code, 200, response.content[:400])
        return response.content.decode("utf-8")

    def test_the_page_carries_the_fixed_title_and_the_red_line(self):
        client = self.ready_client()
        anchor = self.add_line(client, name="ض.ق.م", amount=Decimal("1200.00"))
        self.add_line(
            client, name="اقتطاع الرواتب", amount=Decimal("300.00"),
            service_code="payroll",
        )

        html = self.page_of(anchor)

        self.assertIn(appointments.PAYMENT_NOTICE_TITLE, html)
        # م٤: الصنفُ على **العنصر** لا في الورقة. `<style>` في القالب يحمل
        # `.pn-owed` في كل صفحة، ف`assertIn("pn-owed", html)` كان ينجح ولو قلبنا
        # اللون — هذه الأسطر تسقط يوم يخالف المجموعُ القاعدة، وهو معيار القبول ٤.
        self.assertIn('<span class="pn-owed">1,500 عليك</span>', html)
        self.assertIn('<td class="num pn-owed">1,200</td>', html)
        self.assertIn("عليك", html)

    def test_the_page_paints_a_credit_green(self):
        client = self.ready_client()
        self.add_line(
            client, name="ض.ق.م", amount=Decimal("800.00"),
            direction=OBLIGATION_DIRECTION_REFUND,
        )
        anchor = self.add_line(
            client, name="اقتطاع الرواتب", amount=Decimal("300.00"),
            service_code="payroll",
        )

        html = self.page_of(anchor)

        self.assertIn('class="num pn-refund"', html)
        self.assertIn('<span class="pn-refund">500 إلك</span>', html)
        self.assertIn("إلك", html)

    def test_the_page_paints_a_near_zero_total_gray(self):
        client = self.ready_client()
        anchor = self.add_line(client, name="ض.ق.م", amount=Decimal("7.00"))

        html = self.page_of(anchor)

        # `<span class="pn-neutral">` لا يوجد إلا على المجموع: خليّةُ السطر `<td>`.
        # والاتجاهُ «عليك» لأن اللون قرارُ حدٍّ والإشارةُ قرارُ مبلغ.
        self.assertIn('<span class="pn-neutral">7 عليك</span>', html)


# ── المعيار ٥: الإرفاق ──────────────────────────────────────────────────────
class PaymentNoticeAttachmentTest(PaymentNoticeFixture):
    def test_turning_the_attachment_off_drops_the_notice_from_one_message_only(self):
        muted = self.contacted_client("زبونٌ بلا إرفاق", "أمّ سامي")
        self.add_line(muted, name="ض.ق.م", amount=Decimal("1200.00"))
        services.set_client_setting(muted, "payment_notice_attach", False)

        kept = self.contacted_client("زبونٌ بإرفاق", "أبو سامي")
        self.add_line(kept, name="ض.ق.م", amount=Decimal("640.00"))

        payload = self.ready(SEVEN_DAYS_BEFORE)
        messages = {
            message["recipient"]["name"]: message for message in payload["messages"]
        }

        self.assertEqual(len(messages), 2, payload["messages"])
        quiet = messages["أمّ سامي"]
        self.assertIsNone(quiet["items"][0]["notice"])
        self.assertNotIn(appointments.PAYMENT_NOTICE_TITLE, quiet["body"])
        # والبندُ نفسه باقٍ كما هو: الإطفاءُ أخرج الإشعارَ وحده.
        self.assertEqual(quiet["items"][0]["reminder_type"], REMINDER_DEADLINE)
        self.assertIsNotNone(
            messages["أبو سامي"]["items"][0]["notice"],
        )
        self.assertIn(
            appointments.PAYMENT_NOTICE_TITLE, messages["أبو سامي"]["body"],
        )

    def test_the_deadline_item_survives_the_toggle_and_only_the_notice_leaves(self):
        client = self.ready_client()
        self.add_line(client, name="ض.ق.م", amount=Decimal("1200.00"))
        services.set_client_setting(client, "payment_notice_attach", False)

        items = self.deadline_items()

        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["reminder_type_label"], "موعد رسمي قريب")
        self.assertIsNone(items[0]["notice"])

    def test_a_text_only_format_keeps_the_lines_and_drops_the_link(self):
        client = self.ready_client()
        self.add_line(client, name="ض.ق.م", amount=Decimal("1200.00"))
        services.set_client_setting(client, "payment_notice_format", "text")

        notice = self.notice()

        self.assertEqual(notice["url"], "")
        self.assertEqual(notice["total"], "1200.00")

    def test_a_pdf_only_format_carries_the_link_and_no_lines_in_the_text(self):
        client = self.ready_client()
        self.add_line(client, name="ض.ق.م", amount=Decimal("1200.00"))
        services.set_client_setting(client, "payment_notice_format", "pdf")

        notice = self.notice()
        body = self.ready(SEVEN_DAYS_BEFORE)["messages"][0]["body"]

        self.assertIn("/s/", notice["url"])
        self.assertIn(notice["url"], body)
        self.assertNotIn("1200.00 عليك", body)

    def test_the_format_is_read_per_client_and_not_once_for_the_batch(self):
        """الصيغةُ تُقرأ لصاحب كلّ بندٍ: زبونٌ «نصّاً» لا رابطَ له وزبونٌ بالافتراض يأخذه.

        قراءةٌ واحدة للدفعة (صيغةُ أوّل زبون) كانت تُعطي الاثنين قرارَ واحد:
        رابطاً لِمن طلب نصّاً، أو نصّاً لِمن طلب رابطاً.
        """
        textual = self.contacted_client("زبونٌ نصّاً", "أمّ سامي")
        self.add_line(textual, name="ض.ق.م", amount=Decimal("1200.00"))
        services.set_client_setting(textual, "payment_notice_format", "text")

        linked = self.contacted_client("زبونٌ برابط", "أبو سامي")
        self.add_line(linked, name="ض.ق.م", amount=Decimal("640.00"))

        messages = {
            message["recipient"]["name"]: message
            for message in self.ready(SEVEN_DAYS_BEFORE)["messages"]
        }

        self.assertEqual(messages["أمّ سامي"]["items"][0]["notice"]["url"], "")
        self.assertEqual(
            messages["أمّ سامي"]["items"][0]["notice"]["lines"][0]["amount"], "1200.00",
        )
        link = messages["أبو سامي"]["items"][0]["notice"]["url"]
        self.assertIn("/s/", link)
        # ورابطٌ واحدٌ لا اثنان: صاحبُ «نصّاً» لم يُنشَأ له صفُّ مشاركة.
        self.assertEqual(
            DocumentShare.objects.filter(doc_type=DOC_PAYMENT_NOTICE).count(), 1,
        )

    def test_a_member_without_the_share_permission_reads_text_and_mints_no_link(self):
        """الرابطُ يُنشَأ في مسار قراءة — فلا يُمنَح لِمن لا يملك المشاركة.

        عضوٌ بدور `viewer` يفتح «جاهز للإرسال» فيرى إشعارَ زبونه **نصّاً** كاملاً،
        ولا يُنشَأ صفُّ `DocumentShare` حيّ باسمه بمبالغ زبون.
        """
        viewer = self.make_member("ap_viewer", role="viewer")
        client = self.make_client("زبون القارئ", responsible=viewer)
        self.link(client, self.make_contact(name="جهة القارئ"))
        self.add_line(client, name="ض.ق.م", amount=Decimal("1200.00"))

        payload = services.ready_to_send_payload(
            self.tenant, user=viewer, day=SEVEN_DAYS_BEFORE,
        )
        notice = payload["messages"][0]["items"][0]["notice"]

        self.assertEqual(notice["url"], "")
        self.assertIn("1200.00 عليك", payload["messages"][0]["body"])
        self.assertFalse(
            DocumentShare.objects.filter(doc_type=DOC_PAYMENT_NOTICE).exists(),
        )

    def test_a_member_without_the_amounts_permission_still_reads_the_notice_amounts(self):
        """م٦: `items[].notice` **استثناءٌ مقصود** من قناع المبالغ — ومكتوبٌ باختبار.

        الإشعارُ نصُّه للزبون، فقناؤه يُخفي عن الموظف ما يقرؤه من يُرسِل إليه.
        والقناعُ يبقى حيث كان: صفوفُ الجداول والحمولات المشتقّة. ودورُ `accountant`
        لا يملك `office.amounts.view` افتراضاً، فهو الحالةُ الواقعيّة هنا لا دورٌ
        مُلفَّق — ولولا هذا الاختبار كان الاستثناءُ موثَّقاً بلا حارس، والوثيقةُ
        تحيل إلى شقيقةٍ تفحص `body`/`url` وحدهما.
        """
        member = self.make_member("ap_without_amounts", role="accountant")
        client = self.make_client("زبون بلا مبالغ", responsible=member)
        self.link(client, self.make_contact(name="جهة بلا مبالغ"))
        self.add_line(client, name="ض.ق.م", amount=Decimal("620.00"))

        payload = services.ready_to_send_payload(
            self.tenant, user=member, day=SEVEN_DAYS_BEFORE,
        )
        notice = payload["messages"][0]["items"][0]["notice"]

        self.assertFalse(
            services.can_see_amounts(self.tenant, member),
            "الاختبار يفترض عضواً بلا `office.amounts.view` — والدورُ منحه.",
        )
        self.assertEqual(notice["total"], "620.00")
        self.assertEqual(notice["lines"][0]["amount"], "620.00")
        self.assertIn("620.00 عليك", payload["messages"][0]["body"])


# ── م٥: الكلفة ──────────────────────────────────────────────────────────────
class PaymentNoticeCostTest(PaymentNoticeFixture):
    """بندُ «موعد رسمي قريب» بمبلغٍ لا يكلّف استعلاماً لكل زبون.

    ثابتُ `test_reminders.CostTest` يحرس القائمةَ بزبائنَ بلا التزامٍ بمبلغ، فلا
    يمرّ على الإشعار أصلاً. والإشعارُ يضيف فوقه ثلاثةَ مصادرِ كلفة: استعلامَ
    التزاماتٍ لكل بند، واستعلامَي الرابط الحيّ (`create_share`)، و`INSERT`ين عند
    أوّل فتح. المواعيدُ الضريبيةُ تتجمّع في يومٍ واحد (15)، فمكتبٌ بـ300 زبون كان
    يدفع ≈900 استعلامٍ في كل فتح.

    **والقياسُ بعد وجود الروابط**: أوّلُ فتحٍ يُنشئها بحكم التصميم، والنقصُ
    المتبقّي `INSERT` لكل رابطٍ جديد. الحالةُ الدائمة — الشاشةُ تُفتح كلَّ يوم —
    يجب أن تكون ثابتةً.
    """

    def test_one_deadline_item_costs_what_five_cost_once_the_links_exist(self):
        first = self.ready_client("زبون أول")
        self.add_line(first, name="ض.ق.م", amount=Decimal("1200.00"))
        self.ready(SEVEN_DAYS_BEFORE)  # الرابطُ يُنشَأ في مسار القراءة أوّلَ مرّة.

        with CaptureQueriesContext(connection) as one:
            self.ready(SEVEN_DAYS_BEFORE)

        for index in range(4):
            client = self.ready_client(f"زبون {index}")
            self.add_line(client, name="ض.ق.م", amount=Decimal("700.00"))
        self.ready(SEVEN_DAYS_BEFORE)

        with CaptureQueriesContext(connection) as five:
            payload = self.ready(SEVEN_DAYS_BEFORE)

        notices = [
            item["notice"]
            for message in payload["messages"] for item in message["items"]
            if item["notice"] is not None
        ]
        self.assertEqual(len(notices), 5, notices)
        self.assertEqual(
            len(one.captured_queries), len(five.captured_queries),
            [query["sql"] for query in five.captured_queries],
        )
