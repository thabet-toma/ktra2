"""T-TRIAL: عمود `Status` في MySQL كان `enum('Active','Suspended','Trial')`.

نفس فخّ `0022` بالضبط، وقد كُشف معه: النموذج يقول `CharField(max_length=50)`
والجدول ENUM. القيم الثلاث الحالية داخل الـENUM فلا شيء مكسور **اليوم** — وأول
حالة رابعة (`Expired`، `Cancelled`، `PendingPayment`) سترتدّ في الإنتاج بـ
`DataError (1265)` بينما المجموعة كلها خضراء، لأن SQLite لا تعرف ENUM
و`AlterField` على `choices` لا تُصدر SQL.

يُغلَق الفخّ قبل أن يُوقِع أحداً، لا بعد. لا شيء يُنفَّذ على غير MySQL.
"""
from django.db import migrations


TABLE = 'tenants'
COLUMN = 'Status'


def _widen_to_varchar(apps, schema_editor):
    if schema_editor.connection.vendor != 'mysql':
        return
    schema_editor.execute(
        f'ALTER TABLE `{TABLE}` MODIFY `{COLUMN}` varchar(50) NULL'
    )


def _back_to_enum(apps, schema_editor):
    """الرجوع يعيد الـENUM — وأي حالة خارج الثلاث تصير `Active` أولاً."""
    if schema_editor.connection.vendor != 'mysql':
        return
    schema_editor.execute(
        f"UPDATE `{TABLE}` SET `{COLUMN}` = 'Active' "
        f"WHERE `{COLUMN}` NOT IN ('Active','Suspended','Trial') OR `{COLUMN}` IS NULL"
    )
    schema_editor.execute(
        f"ALTER TABLE `{TABLE}` MODIFY `{COLUMN}` "
        f"enum('Active','Suspended','Trial') NULL"
    )


class Migration(migrations.Migration):
    # DDL في MySQL لا يُلَفّ بمعاملة — كما في `0022`.
    atomic = False

    dependencies = [
        ('tenants', '0022_subscription_plan_varchar'),
    ]

    operations = [
        migrations.RunPython(_widen_to_varchar, _back_to_enum),
    ]
