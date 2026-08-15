"""الاسترجاع الأثري لسجلّ البايتات — `backfill_tenant_assets` (THA-254).

كل ما رُفع قبل THA-252 موجودٌ عند Cloudinary بلا صفٍّ يعرف صاحبه: الأمر يقرأ
الروابط من القاعدة (وهي وحدها تحمل الشركة)، يسأل Admin API عن الأحجام، ويكتب
الصفوف الناقصة. Admin API مُموّه هنا — لا اتصال شبكي واحد.

ما تحرسه هذه الاختبارات هو ما يجعل الرقم قابلاً للتصديق: أن يُنسب كل ملف لشركته
الحقيقية من كل سطح، وأن يبقى «غير المنسوب» غير منسوبٍ بقصد، وأن **لا يُكتب رقمٌ
لم يُقَس** — لا عند غياب الاعتماد ولا عند رابطٍ مكسور.
"""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from core.models import DevelopmentNote, SystemAttachment, TenantAsset
from device_registry.models import SensitiveDevice
from partners.models import Partner
from tenants.models import Tenant, TenantSettings

FAKE_CLOUDINARY = {
    "CLOUD_NAME": "test-cloud",
    "API_KEY": "key",
    "API_SECRET": "secret",
}
NO_CLOUDINARY = {"CLOUD_NAME": "", "API_KEY": "", "API_SECRET": ""}

BASE = "https://res.cloudinary.com/test-cloud"


def img(public_id: str) -> str:
    return f"{BASE}/image/upload/v1700000000/{public_id}.png"


def raw(public_id_with_ext: str) -> str:
    return f"{BASE}/raw/upload/v1700000000/{public_id_with_ext}"


class BackfillTenantAssetsTest(TestCase):
    """مسحٌ واحد يغطّي خمسة أسطح وشركتين وأصلاً منصّياً بلا شركة."""

    @classmethod
    def setUpTestData(cls):
        cls.alpha = Tenant.objects.create(
            CompanyName="شركة ألفا", SubscriptionPlan="Pro", Status="Active",
        )
        cls.beta = Tenant.objects.create(
            CompanyName="شركة بيتا", SubscriptionPlan="Basic", Status="Active",
        )
        # الشعار في ورقة الإعدادات لا في بطاقة الشركة
        TenantSettings.objects.create(
            tenant=cls.alpha, logo_url=img("ktra_uploads/t1/alpha-logo"),
        )

        # سطح ١: مرفقات النظام (ألفا) — ملف raw امتداده جزء من المعرّف
        SystemAttachment.objects.create(
            tenant=cls.alpha, related_table="SalesInvoice", related_id=7,
            file_type="Invoice", file_path=raw("ktra_uploads/inv-7.pdf"),
        )
        # سطح ٢: صورة طرف (بيتا)
        cls.supplier = Partner.objects.create(
            tenant=cls.beta, name="مورد بيتا",
            image_path=img("ktra_uploads/partner-beta"),
        )
        # سطح ٣: جهاز حسّاس (بيتا)
        SensitiveDevice.objects.create(
            tenant=cls.beta, customer_name="سامي", customer_phone="0599000111",
            model_name="آيفون", serial_number="DEV-7",
            photo_url=img("ktra_uploads/device-7"),
        )
        # سطح ٤: JSON بقواميس منسوبة لشركة (ألفا)
        from logistics.models import SupplierQuotation
        from accounting.models import Currency

        currency = Currency.objects.create(Code="USD", Name="دولار")
        SupplierQuotation.objects.create(
            tenant=cls.alpha, quotation_number="Q-1", supplier=cls.supplier,
            quotation_date="2026-07-01", currency=currency,
            attachments=[
                {"name": "عرض", "url": img("ktra_uploads/quote-1")},
                {"name": "ملحق", "url": img("ktra_uploads/quote-1-annex")},
            ],
        )
        # سطح ٥: أصل منصّي — ملاحظة تطوير لا تتبع شركة
        DevelopmentNote.objects.create(
            title="ملاحظة", images=[{"url": img("platform/note-1"), "caption": "ش"}],
        )

    # حجم كل معرّف كما «يعرفه» المزوّد في هذه الاختبارات.
    SIZES = {
        "ktra_uploads/inv-7.pdf": 4_000,
        "ktra_uploads/partner-beta": 1_500,
        "ktra_uploads/device-7": 2_500,
        "ktra_uploads/quote-1": 1_000,
        "ktra_uploads/quote-1-annex": 3_000,
        "ktra_uploads/t1/alpha-logo": 800,
        "platform/note-1": 600,
    }

    def _resources_by_ids(self, public_ids, resource_type="image", **kwargs):
        """يردّ ما يعرفه فقط — والمجهول يغيب عن الرد كما يفعل Cloudinary."""
        self.api_calls.append((resource_type, list(public_ids)))
        return {
            "resources": [
                {
                    "public_id": pid,
                    "bytes": self.SIZES[pid],
                    "resource_type": resource_type,
                }
                for pid in public_ids
                if pid in self.SIZES
            ]
        }

    def setUp(self):
        self.api_calls: list[tuple[str, list[str]]] = []

    def _run(self, *args):
        out = StringIO()
        with patch(
            "cloudinary.api.resources_by_ids", side_effect=self._resources_by_ids
        ), patch(
            "cloudinary.api.usage",
            return_value={"storage": {"usage": 100_000}},
        ):
            call_command("backfill_tenant_assets", *args, stdout=out, stderr=out)
        return out.getvalue()

    @override_settings(CLOUDINARY_STORAGE=FAKE_CLOUDINARY)
    def test_every_surface_is_attributed_to_its_own_tenant(self):
        self._run("--yes")

        by_tenant = {
            (row.tenant_id, row.public_id): row.bytes
            for row in TenantAsset.objects.all()
        }
        self.assertEqual(len(by_tenant), 7, by_tenant)

        # ألفا: مرفق نظام + شعار + مرفقا عرض المورد
        self.assertEqual(by_tenant[(self.alpha.pk, "ktra_uploads/inv-7.pdf")], 4_000)
        self.assertEqual(by_tenant[(self.alpha.pk, "ktra_uploads/t1/alpha-logo")], 800)
        self.assertEqual(by_tenant[(self.alpha.pk, "ktra_uploads/quote-1")], 1_000)
        self.assertEqual(
            by_tenant[(self.alpha.pk, "ktra_uploads/quote-1-annex")], 3_000
        )
        # بيتا: صورة الطرف + صورة الجهاز
        self.assertEqual(by_tenant[(self.beta.pk, "ktra_uploads/partner-beta")], 1_500)
        self.assertEqual(by_tenant[(self.beta.pk, "ktra_uploads/device-7")], 2_500)
        # المنصة: ملاحظة التطوير بلا شركة — «غير منسوب» بقصد لا بخطأ
        self.assertEqual(by_tenant[(None, "platform/note-1")], 600)

        row = TenantAsset.objects.get(public_id="ktra_uploads/inv-7.pdf")
        self.assertEqual(row.source, "backfill")
        # raw: الامتداد جزء من المعرّف فيبقى — حذفه يجعله معرّفاً لا وجود له
        self.assertEqual(row.resource_type, "raw")
        self.assertEqual(row.folder, "ktra_uploads")
        # مجلّد الشركة المتداخل يُقرأ كاملاً لا أوّل مقطعٍ منه
        nested = TenantAsset.objects.get(public_id="ktra_uploads/t1/alpha-logo")
        self.assertEqual(nested.folder, "ktra_uploads/t1")

    @override_settings(CLOUDINARY_STORAGE=FAKE_CLOUDINARY)
    def test_second_run_creates_nothing_and_asks_the_api_for_nothing(self):
        self._run("--yes")
        first = set(TenantAsset.objects.values_list("public_id", flat=True))

        self.api_calls.clear()
        output = self._run("--yes")

        self.assertEqual(
            set(TenantAsset.objects.values_list("public_id", flat=True)), first
        )
        self.assertEqual(TenantAsset.objects.count(), 7)
        # المسجَّل يُتخطّى **قبل** النداء الشبكي: إعادة التشغيل لا تكلّف حصّة.
        self.assertEqual(self.api_calls, [])
        self.assertIn("كُتب 0 صفّاً", output)
        # وجدول الشركات يبقى جواب «كم تستهلك ألفا؟» لا «كم أضاف هذا التشغيل؟»
        # — وإلا قرأ المالك صفراً في تشغيلٍ ثانٍ وظنّ السجلّ فارغاً.
        self.assertIn("8,800 بايت", output)

    @override_settings(CLOUDINARY_STORAGE=FAKE_CLOUDINARY)
    def test_dry_run_reports_but_writes_nothing(self):
        output = self._run()

        self.assertEqual(TenantAsset.objects.count(), 0)
        self.assertIn("شركة ألفا", output)
        self.assertIn("عرضٌ فقط", output)

    @override_settings(CLOUDINARY_STORAGE=FAKE_CLOUDINARY)
    def test_asset_missing_at_the_provider_is_reported_and_never_written(self):
        # رابطٌ في القاعدة بلا أصلٍ خلفه: `bytes=0` له رقمٌ يبدو مقيساً وهو ليس
        SystemAttachment.objects.create(
            tenant=self.beta, related_table="SalesInvoice", related_id=9,
            file_path=img("ktra_uploads/vanished"),
        )
        output = self._run("--yes")

        self.assertFalse(
            TenantAsset.objects.filter(public_id="ktra_uploads/vanished").exists()
        )
        self.assertIn("روابط مكسورة", output)
        self.assertIn("ktra_uploads/vanished", output)

    @override_settings(CLOUDINARY_STORAGE=FAKE_CLOUDINARY)
    def test_legacy_non_cloudinary_url_is_counted_never_guessed(self):
        SystemAttachment.objects.create(
            tenant=self.beta, related_table="Partner", related_id=3,
            file_path="https://firebasestorage.googleapis.com/v0/b/x/o/old.png",
        )
        self._run("--yes")

        self.assertEqual(TenantAsset.objects.filter(tenant=self.beta).count(), 2)
        for _rtype, ids in self.api_calls:
            self.assertNotIn("old.png", " ".join(ids))

    @override_settings(CLOUDINARY_STORAGE=NO_CLOUDINARY)
    def test_writing_without_credentials_refuses_before_touching_anything(self):
        with self.assertRaises(CommandError) as caught:
            call_command("backfill_tenant_assets", "--yes", stdout=StringIO())

        message = str(caught.exception)
        for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
            self.assertIn(key, message)
        self.assertEqual(TenantAsset.objects.count(), 0)

    @override_settings(CLOUDINARY_STORAGE=NO_CLOUDINARY)
    def test_dry_run_without_credentials_still_enumerates_and_says_what_is_missing(self):
        out = StringIO()
        call_command("backfill_tenant_assets", stdout=out, stderr=out)
        output = out.getvalue()

        # الجرد من القاعدة حقيقي بلا اعتماد؛ الناقص هو الأحجام وحدها — ويُقال.
        self.assertIn("شركة ألفا", output)
        self.assertIn("CLOUDINARY_CLOUD_NAME", output)
        self.assertEqual(TenantAsset.objects.count(), 0)


class BackfillBatchingTest(TestCase):
    """سقف المعدّل ليس تفصيلاً: ١٠٠ معرّف في النداء، وإلا رُفض النداء كلّه."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            CompanyName="شركة كبيرة", SubscriptionPlan="Pro", Status="Active",
        )
        SystemAttachment.objects.bulk_create(
            [
                SystemAttachment(
                    tenant=cls.tenant, related_table="SalesInvoice", related_id=i,
                    file_path=img(f"ktra_uploads/doc-{i}"),
                )
                for i in range(150)
            ]
        )

    @override_settings(CLOUDINARY_STORAGE=FAKE_CLOUDINARY)
    def test_ids_are_asked_in_batches_of_a_hundred(self):
        calls: list[list[str]] = []

        def fake(public_ids, resource_type="image", **kwargs):
            calls.append(list(public_ids))
            return {
                "resources": [
                    {"public_id": pid, "bytes": 10, "resource_type": resource_type}
                    for pid in public_ids
                ]
            }

        with patch("cloudinary.api.resources_by_ids", side_effect=fake), patch(
            "cloudinary.api.usage", return_value={"storage": {"usage": 5_000}}
        ):
            call_command("backfill_tenant_assets", "--yes", stdout=StringIO())

        self.assertEqual([len(c) for c in calls], [100, 50])
        self.assertEqual(TenantAsset.objects.count(), 150)
