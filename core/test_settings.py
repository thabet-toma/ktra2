"""Test settings: same as core.settings but with SQLite in-memory database.

سلسلة الهجرات القديمة غير متّسقة لبناء قاعدة نظيفة: جداول أساسية (chartofaccounts,
partners, tenants…) أُنشئت في `0001_initial` بـ `managed=False` — أي تُطبَّق خارجياً على
قاعدة MySQL القديمة، ولا يُصدِر Django لها CREATE TABLE. وهجرات لاحقة تُعيد تسمية أعمدة
PascalCase إلى snake_case عبر «أضِف بنفس db_column ثم احذف القديم» — تعمل فقط لأنها كانت
تُتخطّى صمتاً حين كان النموذج managed=False. على قاعدة اختبار جديدة (SQLite) تنهار الهجرات.

الحل المعزول (بيئة الاختبار فقط، بلا لمس أي ملف هجرة مُلتزم): تعطيل الهجرات فيبني منشئ قاعدة
الاختبار المخطط من تعريفات النماذج الحالية مباشرةً عبر run_syncdb — نمط قياسي للمشاريع ذات
الهجرات القديمة، وأسرع أيضاً. النماذج هي مصدر الحقيقة (متّسقة، managed=True في الإنتاج).
"""
from core.settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}


class _DisableMigrations:
    """تُرجِع None لكل تطبيق ⇒ Django يعدّه بلا هجرات فيبني جداوله من النماذج (syncdb)."""

    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _DisableMigrations()
