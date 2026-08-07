# قواعد MySQL قديمة: جدول cost_centers أُنشئ قبل Django بأعمدة
# (CostCenterID, TenantID, Name, Description) فقط — بلا Code. النموذج يطلبه،
# فيفشل SELECT بـ OperationalError ويرجع 500 على /api/accounting/cost-centers/،
# وهو ما كان يُفشل تحميل «تعديل بطاقة الطرف» (Promise.all) وشاشة القيود معاً.

from django.db import migrations
import logging

logger = logging.getLogger(__name__)


def ensure_code_column(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != "mysql":
        return
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'cost_centers'
              AND COLUMN_NAME = 'Code'
            """
        )
        if cursor.fetchone()[0]:
            return
    schema_editor.execute(
        "ALTER TABLE cost_centers ADD COLUMN Code VARCHAR(50) NULL AFTER Name"
    )
    logger.info("accounting.cost_centers.code_column_added")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    # DDL على MySQL لا يرتد داخل معاملة — كما في 0010.
    atomic = False

    dependencies = [
        ("accounting", "0030_alter_chequemovement_movement_type"),
    ]

    operations = [
        migrations.RunPython(ensure_code_column, noop_reverse),
    ]
