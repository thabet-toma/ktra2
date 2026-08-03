"""Test settings: same as core.settings but with SQLite in-memory database.

سلسلة الهجرات صارت قابلة للبناء من صفر (أُصلحت 2026-07-22: كانت الجداول الأساسية
تُنشأ في `0001_initial` بـ `managed=False` فلا يُصدِر Django لها CREATE TABLE، و
`AlterModelOptions` في `0002` تُبدّل الحالة فقط بلا إنشاء الجدول).

تعطيل الهجرات هنا يبقى لسبب واحد: السرعة. منشئ قاعدة الاختبار يبني المخطط من تعريفات
النماذج مباشرةً عبر run_syncdb بدل تشغيل 161 هجرة لكل جولة اختبار. النماذج هي مصدر
الحقيقة، و`makemigrations --check` يحرس تطابقها مع سلسلة الهجرات.
"""
from core.settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# كاش معطَّل في الاختبارات: FileBasedCache يكتب على القرص ويبقى بين تشغيلات
# الاختبار، وTTL الداشبورد (60ث) قد يُرجِع بيانات قديمة بين اختبارات نفس المستأجر.
# DummyCache = لا تخزين إطلاقاً ⇒ سلوك مطابق لما قبل إضافة الكاش.
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}
}

# Test-only placeholders let media tests reach the mocked Cloudinary uploader.
# They are never used for network access and keep production credentials env-only.
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": "test-cloud",
    "API_KEY": "test-key",
    "API_SECRET": "test-secret",
}


class _DisableMigrations:
    """تُرجِع None لكل تطبيق ⇒ Django يعدّه بلا هجرات فيبني جداوله من النماذج (syncdb)."""

    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _DisableMigrations()
