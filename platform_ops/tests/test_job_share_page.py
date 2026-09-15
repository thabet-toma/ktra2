"""صفحةُ الإعلان الوظيفيّ المُصيَّرةُ من الخادم — بلاغُ المالك #214-أ.

**البلاغ:** «لما اخذ الرابط تبع الاعلان واحطو عفيس بوك بيجي الشرح والعنوان
للرابط منصة ktra» — أي أنّ كلَّ إعلانٍ يُشارَك يظهر بعنوان المنصّة العامّ
ووصفِها العامّ، لا بعنوان الوظيفة.

**السبب الجذريّ** (مُتحقَّقٌ منه في الكود لا مُستنتَج): الرابطُ المنسوخ كان
مسارَ SPA، والخادمُ الأمامي يخدم `frontend_v2/index.html` لكلّ ما ليس `/api/`،
وزاحفُ فيسبوك **لا ينفّذ JavaScript** — فما يقرؤه هو وسومُ `index.html` وحدَها.

فكلُّ اختبارٍ هنا يقيس ما يراه **الزاحف** لا ما يراه المتصفّح: نصُّ الردّ الخامّ
قبل أيّ سكربت.
"""
import datetime
import json
import re

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from platform_ops.services import (
    close_job_posting,
    create_job_posting,
    job_apply_url,
    job_public_url,
)


def _meta(html: str, prop: str) -> str:
    """قيمةُ وسمٍ اجتماعيٍّ بعينه من نصّ الصفحة الخامّ.

    قراءةُ النصّ لا قراءةُ السياق: هذا بالضبط ما يفعله الزاحف.
    """
    match = re.search(
        r'<meta\s+(?:property|name)="%s"\s+content="([^"]*)"' % re.escape(prop), html
    )
    return match.group(1) if match else ""


class JobSharePageTests(TestCase):
    """الصفحةُ العامّةُ للإعلان: ما يقرؤه فيسبوك، وما تقرؤه جوجل."""

    def setUp(self):
        self.client = APIClient()
        self.job = create_job_posting(
            title="محاسب أول",
            description="مسكُ دفاتر شركاتِ المنصّة ومراجعةُ القيود الشهريّة.",
            requirements="خبرةٌ ثلاثُ سنواتٍ في المحاسبة.",
            location="عمّان",
            employment_type="full_time",
            salary_range="٥٠٠ – ٨٠٠ دينار",
            expires_at=timezone.now() + datetime.timedelta(days=30),
        )

    def _page(self):
        return self.client.get(f"/api/careers/j/{self.job.token}/")

    # ── الرابطُ نفسُه ────────────────────────────────────────────────────────

    def test_the_copied_link_is_the_server_page_not_the_spa_route(self):
        """زرُّ «نسخ الرابط» يجب أن يُخرج ما يستطيع الزاحفُ قراءتَه.

        هذا هو العطبُ نفسُه: رابطٌ إلى `/careers/job/` يُخدَم من `index.html`،
        فلا شيء فيه يخصّ هذه الوظيفة مهما حسّنّا الصفحة.
        """
        url = job_public_url(self.job.token)
        self.assertIn("/api/careers/j/", url)
        self.assertNotIn("/careers/job/", url)
        self.assertTrue(url.endswith(self.job.token))

    def test_the_apply_link_stays_on_the_live_screen(self):
        """شاشةُ التقديم تبقى في الـSPA — فيها رفعُ ملفٍّ وتأكيدٌ حيّ."""
        self.assertIn("/careers/job/", job_apply_url(self.job.token))

    # ── ما يقرؤه الزاحف ─────────────────────────────────────────────────────

    def test_the_preview_names_the_job_not_the_platform(self):
        """قلبُ البلاغ: العنوانُ والوصفُ يخصّان الوظيفة."""
        html = self._page().content.decode("utf-8")
        title = _meta(html, "og:title")
        self.assertIn("محاسب أول", title)
        self.assertIn("التقديم", title)
        # والعنوانُ العامُّ الذي كان يظهر لكلّ إعلان — غائبٌ تماماً.
        self.assertNotIn("نظام متكامل لإدارة الاستيراد", html)

    def test_the_preview_description_leads_with_the_deciding_facts(self):
        """المكانُ والدوامُ والراتبُ قبل نصّ الوصف — بهم يُقرَّر الضغط."""
        description = _meta(self._page().content.decode("utf-8"), "og:description")
        self.assertIn("عمّان", description)
        self.assertIn("دوام كامل", description)
        self.assertIn("٥٠٠ – ٨٠٠ دينار", description)

    def test_the_preview_description_is_one_line_and_bounded(self):
        """وصفٌ متعدّدُ الأسطر يكسر وسمَ `content`، وطويلٌ يُقطَع في منتصف كلمة."""
        job = create_job_posting(
            title="مهندس دعم",
            description="سطرٌ أوّل.\nسطرٌ ثانٍ.\n\n" + ("كلمةٌ طويلةٌ جداً " * 60),
        )
        html = self.client.get(f"/api/careers/j/{job.token}/").content.decode("utf-8")
        description = _meta(html, "og:description")
        self.assertNotIn("\n", description)
        self.assertLessEqual(len(description), 201)
        self.assertTrue(description.endswith("…"))

    def test_the_page_carries_its_own_canonical_and_url(self):
        """`og:url` يشير إلى هذه الصفحة لا إلى جذر المنصّة."""
        html = self._page().content.decode("utf-8")
        share_url = job_public_url(self.job.token)
        self.assertEqual(_meta(html, "og:url"), share_url)
        self.assertIn(f'<link rel="canonical" href="{share_url}">', html)

    def test_the_ad_is_indexable_unlike_a_shared_document(self):
        """فرقٌ مقصودٌ عن `docshare`: ذاك خاصٌّ فيُمنَع، وهذا إعلانٌ يُراد نشرُه."""
        html = self._page().content.decode("utf-8")
        self.assertNotIn("noindex", html)

    def test_the_page_needs_no_login_and_no_javascript(self):
        """الزاحفُ مجهولٌ ولا ينفّذ سكربتاً — والصفحةُ تُقرأ كاملةً بلا أيٍّ منهما."""
        response = self._page()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        html = response.content.decode("utf-8")
        self.assertIn("محاسب أول", html)
        self.assertIn("مسكُ دفاتر شركاتِ المنصّة", html)
        # لا سكربتَ تشغيليٌّ في الصفحة — وحدَه وسمُ البيانات المهيكلة.
        self.assertEqual(html.count("<script"), 1)
        self.assertIn('type="application/ld+json"', html)

    def test_the_bare_path_serves_the_same_page(self):
        """رابطٌ بلا شرطةٍ أخيرةً أقصرُ وأنظف، وبعضُ الزواحف لا تتبع التحويل."""
        bare = self.client.get(f"/api/careers/j/{self.job.token}")
        self.assertEqual(bare.status_code, status.HTTP_200_OK)
        self.assertIn("محاسب أول", bare.content.decode("utf-8"))

    def test_the_apply_button_leads_to_the_application_screen(self):
        html = self._page().content.decode("utf-8")
        self.assertIn(f'href="{job_apply_url(self.job.token)}"', html)

    # ── البياناتُ المهيكلة ───────────────────────────────────────────────────

    def test_the_structured_data_is_valid_json_and_describes_this_job(self):
        """ما تقرؤه «وظائف جوجل». JSON غيرُ صالحٍ يُتجاهَل صامتاً."""
        html = self._page().content.decode("utf-8")
        raw = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        ).group(1)
        data = json.loads(raw)
        self.assertEqual(data["@type"], "JobPosting")
        self.assertEqual(data["title"], "محاسب أول")
        self.assertEqual(data["employmentType"], "FULL_TIME")
        self.assertEqual(data["jobLocation"]["address"]["addressLocality"], "عمّان")
        self.assertEqual(data["datePosted"], self.job.created_at.date().isoformat())
        self.assertIn("validThrough", data)
        self.assertEqual(data["hiringOrganization"]["name"], "K.T.R.A")

    def test_a_contract_job_is_not_named_contract_in_the_schema(self):
        """اسمُها هناك `CONTRACTOR`. اشتقاقٌ آليٌّ بـ`.upper()` يُخرج قيمةً
        يرفضها مُدقّقُ جوجل بصمتٍ فلا يظهر الإعلان ولا يُقال لأحدٍ لماذا."""
        job = create_job_posting(
            title="مدقّق عقود", description="وصف.", employment_type="contract",
        )
        html = self.client.get(f"/api/careers/j/{job.token}/").content.decode("utf-8")
        raw = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        ).group(1)
        self.assertEqual(json.loads(raw)["employmentType"], "CONTRACTOR")

    def test_an_empty_field_is_omitted_not_written_blank(self):
        """حقلٌ فارغٌ يُحذف من المخطَّط: `jobLocation` بعنوانٍ فارغٍ خطأُ تدقيق."""
        job = create_job_posting(title="مساعد", description="وصف.")
        html = self.client.get(f"/api/careers/j/{job.token}/").content.decode("utf-8")
        raw = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        ).group(1)
        data = json.loads(raw)
        self.assertNotIn("jobLocation", data)
        self.assertNotIn("employmentType", data)
        self.assertNotIn("baseSalary", data)
        self.assertNotIn("validThrough", data)

    def test_a_description_cannot_close_the_structured_data_script(self):
        """وصفُ الوظيفة نصٌّ يكتبه إنسانٌ في لوحة التحكّم، والصفحةُ عامّة.

        `</script>` داخلَه يُنهي الوسمَ ويفتح بابَ حقنٍ لكلّ من يفتح الرابط.
        """
        job = create_job_posting(
            title="مدخل بيانات",
            description='وصف</script><script>alert("خرق")</script> وتكملة.',
        )
        html = self.client.get(f"/api/careers/j/{job.token}/").content.decode("utf-8")
        self.assertNotIn('<script>alert("خرق")</script>', html)
        # ويبقى سكربتٌ واحدٌ في الصفحة — وسمُ البيانات المهيكلة وحدَه.
        self.assertEqual(html.count("<script"), 1)
        raw = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        ).group(1)
        self.assertIn("خرق", json.loads(raw)["description"])

    # ── الأبوابُ المغلقة ─────────────────────────────────────────────────────

    def test_a_closed_ad_says_so_and_advertises_nothing(self):
        """رابطٌ ميّتٌ على فيسبوك يجب ألّا يحمل بطاقةَ وظيفةٍ لا وجودَ لها."""
        close_job_posting(job=self.job)
        response = self._page()
        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        html = response.content.decode("utf-8")
        self.assertIn("انتهى التقديم", html)
        self.assertEqual(_meta(html, "og:title"), "")
        self.assertNotIn("محاسب أول", html)

    def test_an_unknown_token_renders_a_page_not_a_broken_body(self):
        """بلا التقاطِ `NotFound` يردّ DRF جسمَ خطأٍ بلا قالبٍ فينكسر التصيير."""
        response = self.client.get("/api/careers/j/لا-يوجد/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        html = response.content.decode("utf-8")
        self.assertIn("الرابطُ غير صالح", html)
        self.assertIn("<!DOCTYPE html>", html)

    def test_the_short_mount_serves_the_very_same_page(self):
        """مركَّبةٌ مرّتين كـ`docshare`: القصيرُ ينتظر سطراً في الخادم الأمامي،
        و`/api/…` يعمل اليوم — فلا ميزةَ معطَّلةٌ بانتظار إعداد."""
        short = self.client.get(f"/j/{self.job.token}/")
        self.assertEqual(short.status_code, status.HTTP_200_OK)
        self.assertEqual(short.content, self._page().content)
