"""T-TRIAL: عمود الخطة في MySQL كان `enum('Basic','Pro','Enterprise')`.

النموذج يقول `CharField(max_length=50)` منذ `0001_initial`، لكن الجدول الحقيقي
وُرِث من قاعدة أقدم بعمود ENUM. الفارق كان نائماً ما دامت القيم الثلاث هي كلّ ما
يُكتب — وأول محاولة لحفظ `'Trial'` ترتدّ بـ
`DataError (1265) Data truncated for column 'SubscriptionPlan'`.

ولا يكشفه شيء قبل الإنتاج: `AlterField` على `choices` وحدها **لا تُصدر SQL**
(الخيارات تحقّق في بايثون لا في المحرّك)، واختبارات SQLite لا تعرف ENUM أصلاً
فتمرّ خضراء على جدولٍ يخالف نموذجه.

يُصلَح العمود إلى ما يعلنه النموذج (`varchar(50) NOT NULL`) لا بتوسيع الـENUM:
قائمة الخطط تتغيّر بقرار تجاري، وعمودٌ يلزمه `ALTER TABLE` لكل خطة جديدة هو
الفخّ نفسه مؤجَّلاً. لا شيء يُنفَّذ على غير MySQL.
"""
from django.db import migrations


TABLE = 'tenants'
COLUMN = 'SubscriptionPlan'


def _widen_to_varchar(apps, schema_editor):
    if schema_editor.connection.vendor != 'mysql':
        return
    schema_editor.execute(
        f'ALTER TABLE `{TABLE}` MODIFY `{COLUMN}` varchar(50) NOT NULL'
    )


def _back_to_enum(apps, schema_editor):
    """الرجوع يعيد الـENUM القديم — وأي شركة على «Trial» تصير «Basic» أولاً.

    بلا هذا التطبيع يفشل الرجوع نفسه بنفس الخطأ الذي جاءت هذه الهجرة تصلحه.
    """
    if schema_editor.connection.vendor != 'mysql':
        return
    schema_editor.execute(
        f"UPDATE `{TABLE}` SET `{COLUMN}` = 'Basic' WHERE `{COLUMN}` = 'Trial'"
    )
    schema_editor.execute(
        f"ALTER TABLE `{TABLE}` MODIFY `{COLUMN}` "
        f"enum('Basic','Pro','Enterprise') NOT NULL"
    )


class Migration(migrations.Migration):
    # DDL في MySQL لا يُلَفّ بمعاملة (لا رجوع له)، و`RunPython` ذرّيةٌ افتراضاً
    # ⇒ `TransactionManagementError`. الهجرة عمليةٌ واحدة، فلا شيء يبقى نصفَ
    # مطبَّقٍ بإخراجها من المعاملة.
    atomic = False

    dependencies = [
        ('tenants', '0021_tenant_subscription_ends_at'),
    ]

    operations = [
        migrations.RunPython(_widen_to_varchar, _back_to_enum),
    ]
