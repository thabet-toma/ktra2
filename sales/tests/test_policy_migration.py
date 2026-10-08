"""ترحيل البيانات `0050_stock_loss_policies`: المنطقيَّان القديمان → السياستان الثلاثيتان.

`allow_negative_stock_default`: True→allow، False→block.
`block_loss_invoices`:         False→allow، True→block.
والرجوع يعيد المنطقيَّين: allow→السماح، وأي غيرها (block أو save_only)→المنع.

مجموعة الاختبارات تعطّل الهجرات (`--nomigrations`) فلا يصلح `MigrationExecutor` هنا؛
فندير دالتَي الهجرة الحقيقيتين على جدولٍ مؤقّتٍ بنموذج تاريخيّ (`StateApps`) يحمل
الحقول الأربعة، فيختبر الاستعلام نفسه الذي تشغّله الهجرة. وبوّابة CI
(`KTRA_MIGRATIONS_DB`) تشغّل السلسلة كاملةً من صفر على الجدول الحقيقي.
"""
import importlib

import pytest
from django.db import connection, models
from django.db.migrations.state import ModelState, ProjectState

pytestmark = pytest.mark.django_db(transaction=True)

migration = importlib.import_module("sales.migrations.0050_stock_loss_policies")


@pytest.fixture
def historical_apps():
    state = ProjectState()
    state.add_model(ModelState(
        "sales", "SalesSettings",
        [
            ("id", models.AutoField(primary_key=True)),
            ("allow_negative_stock_default", models.BooleanField(default=True)),
            ("block_loss_invoices", models.BooleanField(default=False)),
            ("negative_stock_policy", models.CharField(max_length=12, default="allow")),
            ("loss_invoice_policy", models.CharField(max_length=12, default="allow")),
        ],
        options={"db_table": "tmp_policy_migration_settings"},
    ))
    apps = state.apps
    model = apps.get_model("sales", "SalesSettings")
    with connection.schema_editor() as editor:
        editor.create_model(model)
    yield apps
    with connection.schema_editor() as editor:
        editor.delete_model(model)


def test_forward_maps_booleans_to_policies(historical_apps):
    S = historical_apps.get_model("sales", "SalesSettings")
    rows = {
        "default": S.objects.create(allow_negative_stock_default=True, block_loss_invoices=False),
        "both_blocked": S.objects.create(allow_negative_stock_default=False, block_loss_invoices=True),
        "loss_only": S.objects.create(allow_negative_stock_default=True, block_loss_invoices=True),
        "negative_only": S.objects.create(allow_negative_stock_default=False, block_loss_invoices=False),
    }
    migration.booleans_to_policies(historical_apps, None)
    got = {
        k: (S.objects.get(pk=r.pk).negative_stock_policy, S.objects.get(pk=r.pk).loss_invoice_policy)
        for k, r in rows.items()
    }
    assert got == {
        "default": ("allow", "allow"),
        "both_blocked": ("block", "block"),
        "loss_only": ("allow", "block"),
        "negative_only": ("block", "allow"),
    }


def test_reverse_maps_policies_back_and_save_only_counts_as_block(historical_apps):
    S = historical_apps.get_model("sales", "SalesSettings")
    rows = {
        "allow": S.objects.create(negative_stock_policy="allow", loss_invoice_policy="allow"),
        "block": S.objects.create(negative_stock_policy="block", loss_invoice_policy="block"),
        "save_only": S.objects.create(negative_stock_policy="save_only", loss_invoice_policy="save_only"),
    }
    migration.policies_to_booleans(historical_apps, None)
    got = {
        k: (S.objects.get(pk=r.pk).allow_negative_stock_default, S.objects.get(pk=r.pk).block_loss_invoices)
        for k, r in rows.items()
    }
    assert got == {
        "allow": (True, False),
        "block": (False, True),
        "save_only": (False, True),
    }
