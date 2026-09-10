"""اختبار رسم الهجرات لوحدة عمليات المنصة (`platform_ops`).

التحقق من أن الهجرة الأولى موجودة وتعلن اعتمادها على `tenants`،
وأن خطة البناء تضع كل الاعتمادات قبل الوحدة.
"""
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, override_settings

APP = "platform_ops"


@override_settings(MIGRATION_MODULES={})
class PlatformOpsMigrationGraphTest(SimpleTestCase):
    def setUp(self):
        self.loader = MigrationLoader(None, ignore_no_migrations=True)

    def test_initial_migration_exists_in_the_graph(self):
        self.assertIn((APP, "0001_initial"), self.loader.graph.nodes)

    def test_initial_migration_declares_its_dependency_on_tenants(self):
        """الاعتماد مُعلَن لا مستنتَج — وإلا بُنيت جداولنا قبل جدول الشركات."""
        migration = self.loader.disk_migrations[(APP, "0001_initial")]
        depended_apps = {app for app, _ in migration.dependencies}
        self.assertIn(
            "tenants", depended_apps,
            f"هجرة {APP} الأولى لا تعلن اعتمادها على `tenants`: {migration.dependencies}",
        )

    def test_forwards_plan_places_every_dependency_before_the_module(self):
        """خطّةُ البناء من الصفر تضع كلّ ما نعتمد عليه قبلنا."""
        plan = self.loader.graph.forwards_plan((APP, "0001_initial"))
        self.assertEqual(plan[-1], (APP, "0001_initial"))
        preceding_apps = {app for app, _ in plan[:-1]}
        self.assertIn("tenants", preceding_apps)

    def test_migration_0002_exists_and_depends_on_0001(self):
        """هجرة المرحلة الثانية موجودة وتعتمد على 0001_initial."""
        migration_0002_name = "0002_engagement_agentgrantedmembership_and_more"
        self.assertIn((APP, migration_0002_name), self.loader.graph.nodes)
        migration = self.loader.disk_migrations[(APP, migration_0002_name)]
        self.assertIn((APP, "0001_initial"), migration.dependencies)

    def test_forwards_plan_for_0002_places_all_dependencies_before_it(self):
        """خطة البناء للأمام حتى 0002 تضع الاعتمادات قبلها وتختم بـ 0002."""
        migration_0002_name = "0002_engagement_agentgrantedmembership_and_more"
        plan = self.loader.graph.forwards_plan((APP, migration_0002_name))
        self.assertEqual(plan[-1], (APP, migration_0002_name))
        self.assertIn((APP, "0001_initial"), plan[:-1])

    def test_migration_0003_exists_and_depends_on_0002(self):
        """هجرة المرحلة الثالثة موجودة وتعتمد على 0002."""
        migration_0003_name = "0003_workorder_workordercomment_workorderdeliverable_and_more"
        self.assertIn((APP, migration_0003_name), self.loader.graph.nodes)
        migration = self.loader.disk_migrations[(APP, migration_0003_name)]
        self.assertIn(
            (APP, "0002_engagement_agentgrantedmembership_and_more"),
            migration.dependencies,
        )

    def test_forwards_plan_for_0003_places_all_dependencies_before_it(self):
        """خطة البناء للأمام حتى 0003 تضع الاعتمادات قبلها وتختم بـ 0003."""
        migration_0003_name = "0003_workorder_workordercomment_workorderdeliverable_and_more"
        plan = self.loader.graph.forwards_plan((APP, migration_0003_name))
        self.assertEqual(plan[-1], (APP, migration_0003_name))
        self.assertIn((APP, "0002_engagement_agentgrantedmembership_and_more"), plan[:-1])

    def test_migration_0004_exists_and_depends_on_0003(self):
        """هجرة المرحلة الرابعة موجودة وتعتمد على 0003."""
        migration_0004_name = "0004_workorder_attachment_ids_workorder_channel_and_more"
        self.assertIn((APP, migration_0004_name), self.loader.graph.nodes)
        migration = self.loader.disk_migrations[(APP, migration_0004_name)]
        self.assertIn(
            (APP, "0003_workorder_workordercomment_workorderdeliverable_and_more"),
            migration.dependencies,
        )

    def test_forwards_plan_for_0004_places_all_dependencies_before_it(self):
        """خطة البناء للأمام حتى 0004 تضع الاعتمادات قبلها وتختم بـ 0004."""
        migration_0004_name = "0004_workorder_attachment_ids_workorder_channel_and_more"
        plan = self.loader.graph.forwards_plan((APP, migration_0004_name))
        self.assertEqual(plan[-1], (APP, migration_0004_name))
        self.assertIn((APP, "0003_workorder_workordercomment_workorderdeliverable_and_more"), plan[:-1])

    def test_migration_0005_exists_and_depends_on_0004(self):
        """هجرة المرحلة الخامسة موجودة وتعتمد على 0004."""
        migration_0005_name = "0005_policyprofile_workorder_cancelled_at_and_more"
        self.assertIn((APP, migration_0005_name), self.loader.graph.nodes)
        migration = self.loader.disk_migrations[(APP, migration_0005_name)]
        self.assertIn(
            (APP, "0004_workorder_attachment_ids_workorder_channel_and_more"),
            migration.dependencies,
        )

    def test_forwards_plan_for_0005_places_all_dependencies_before_it(self):
        """خطة البناء للأمام حتى 0005 تضع الاعتمادات قبلها وتختم بـ 0005."""
        migration_0005_name = "0005_policyprofile_workorder_cancelled_at_and_more"
        plan = self.loader.graph.forwards_plan((APP, migration_0005_name))
        self.assertEqual(plan[-1], (APP, migration_0005_name))
        self.assertIn((APP, "0004_workorder_attachment_ids_workorder_channel_and_more"), plan[:-1])


