"""قاعدةٌ فارغةٌ تُبنى من الهجرات وحدها — هل تنجح؟ (اختبار المواصفة رقم ٢٢)

**لماذا لا يكفي أن تكون قاعدةُ التطوير خضراء:** جداولها موجودةٌ أصلاً، فهجرةٌ لا
تُعلن اعتمادها على `tenants` تمرّ عليها بلا شكوى وتنكسر على قاعدةٍ فارغة تُبنى
من الصفر — وهو ما يحدث عند نشر بيئةٍ جديدة، لا عند التطوير.

**ولماذا هذا الاختبار يقرأ الرسم ولا يُنشئ قاعدة:** `pytest.ini` يشغّل
`--nomigrations`، فالمجموعة كلّها تبني المخطّط من النماذج مباشرةً ولا تنفّذ هجرةً
واحدة. اختبارٌ يعتمد على تنفيذ الهجرات لن يُشغَّل في البوّابة أصلاً — فيُقرأ رسمُ
الهجرات من القرص (`MigrationLoader`) ويُتحقَّق منه بلا اتّصالٍ بقاعدة.
"""
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, override_settings

APP = "employee_ops"


# `--nomigrations` في `pytest.ini` يحقن `MIGRATION_MODULES` تعطّل اكتشافَ الهجرات
# كلّها، فيرى `MigrationLoader` رسماً فارغاً. إعادتُها قاموساً فارغاً تُرجع
# الاكتشافَ الافتراضي (`<app>.migrations`) لهذا الاختبار وحده.
@override_settings(MIGRATION_MODULES={})
class EmployeeOpsMigrationGraphTest(SimpleTestCase):
    def setUp(self):
        # `connection=None` يبني الرسم من الملفّات وحدها بلا قاعدة بيانات، ويرفع
        # استثناءً إن كان في الرسم اعتمادٌ مفقود أو دورة.
        self.loader = MigrationLoader(None, ignore_no_migrations=True)

    def test_initial_migration_exists_in_the_graph(self):
        self.assertIn((APP, "0001_initial"), self.loader.graph.nodes)

    def test_initial_migration_declares_its_dependency_on_tenants(self):
        """الاعتماد **مُعلَن** لا مستنتَج — وإلا بُنيت جداولنا قبل جدول الشركات."""
        migration = self.loader.disk_migrations[(APP, "0001_initial")]
        depended_apps = {app for app, _ in migration.dependencies}
        self.assertIn(
            "tenants", depended_apps,
            f"هجرة {APP} الأولى لا تعلن اعتمادها على `tenants`: {migration.dependencies}",
        )

    def test_forwards_plan_places_every_dependency_before_the_module(self):
        """خطّةُ البناء من الصفر تضع كلّ ما نعتمد عليه **قبلنا**.

        هذا هو التأكيد الذي يسقط فعلاً لو حُذف سطر `dependencies`: الخطّة تُبنى
        من الرسم، وحذفُ الاعتماد يُخرج هجرات `tenants` من الخطّة كلّها.
        """
        plan = self.loader.graph.forwards_plan((APP, "0001_initial"))
        self.assertEqual(plan[-1], (APP, "0001_initial"))
        preceding_apps = {app for app, _ in plan[:-1]}
        self.assertIn("tenants", preceding_apps)
