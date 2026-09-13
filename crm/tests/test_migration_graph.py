"""قاعدةٌ فارغةٌ تُبنى من الهجرات وحدها — هل تنجح؟ على نمط
`employee_ops/tests/test_migration_graph.py`.

**لماذا لا يكفي أن تكون قاعدةُ التطوير خضراء:** جداولها موجودةٌ أصلاً، فهجرةٌ لا
تُعلن اعتمادها على `tenants` تمرّ عليها بلا شكوى وتنكسر على قاعدةٍ فارغة تُبنى
من الصفر. و`pytest.ini` يشغّل `--nomigrations`، فهذا الاختبار يقرأ رسمَ الهجرات
من القرص (`MigrationLoader`) بلا اتّصالٍ بقاعدة.
"""
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, override_settings

APP = "crm"


@override_settings(MIGRATION_MODULES={})
class CrmMigrationGraphTest(SimpleTestCase):
    def setUp(self):
        self.loader = MigrationLoader(None, ignore_no_migrations=True)

    def test_initial_migration_exists_in_the_graph(self):
        self.assertIn((APP, "0001_initial"), self.loader.graph.nodes)

    def test_initial_migration_declares_its_dependency_on_tenants(self):
        """الاعتماد **مُعلَن** لا مستنتَج — `converted_tenant` يشير إلى `tenants.Tenant`."""
        migration = self.loader.disk_migrations[(APP, "0001_initial")]
        depended_apps = {app for app, _ in migration.dependencies}
        self.assertIn(
            "tenants", depended_apps,
            f"هجرة {APP} الأولى لا تعلن اعتمادها على `tenants`: {migration.dependencies}",
        )

    def test_initial_migration_declares_its_dependency_on_platform_ops(self):
        """`assigned_to`/`suggested_by`/`from_employee`/`to_employee` تشير إلى `platform_ops.PlatformEmployee`."""
        migration = self.loader.disk_migrations[(APP, "0001_initial")]
        depended_apps = {app for app, _ in migration.dependencies}
        self.assertIn(
            "platform_ops", depended_apps,
            f"هجرة {APP} الأولى لا تعلن اعتمادها على `platform_ops`: {migration.dependencies}",
        )

    def test_forwards_plan_places_every_dependency_before_the_module(self):
        """خطّةُ البناء من الصفر تضع كلّ ما نعتمد عليه **قبلنا**."""
        plan = self.loader.graph.forwards_plan((APP, "0001_initial"))
        self.assertEqual(plan[-1], (APP, "0001_initial"))
        preceding_apps = {app for app, _ in plan[:-1]}
        self.assertIn("tenants", preceding_apps)
        self.assertIn("platform_ops", preceding_apps)
