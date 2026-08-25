"""CHQ-4 — **السبب الجذري** لشكوى «تعذّر الترحيل، وتم عمل مسودة».

عمودا `cheques.Status` و`cheques.Direction` في MySQL نوعهما `ENUM`:

    Status    enum('Draft','Under_Collection','Collected','Bounced','Returned')
    Direction enum('Incoming','Outgoing')

بينما النموذج يعلنهما `CharField` منذ البداية. الجدول موروثٌ من مخطط أقدم (كان
`managed=False` في `0001`) — نفس انحراف `T-CHQ3/ح` في `0032` ونفس عطل عمود الخطة
في `tenants/0022`.

الفارق كان نائماً ما دامت الحالات الخمس هي كل ما يُكتب. ثم أدخلت `CHQ-1`
(`0037_cheque_cycle_v2`) ثلاث حالات جديدة — `Received` و`Endorsed` و`Cancelled` —
فصار **ترحيل أي سند قبض فيه شيك وارد** يحاول كتابة `Received` فترتدّ MySQL بـ
`(1265, "Data truncated for column 'Status' at row 1")`. يبتلعه الترحيل التلقائي
في `sales/views.py` فيصل المستخدمَ «حُفظ السند كمسودة — تعذّر الترحيل»، ولا
تُرحَّل المسودة بعدها من شاشة الشيكات لأن العطل يتكرر في كل محاولة. وهذا بعينه
معنى «كان شغال قبل التزبيط»: الكود القديم كان يكتب `Under_Collection` وهي داخل
الـENUM.

ولا يكشفه شيء قبل الإنتاج: `AlterField` على `choices` وحدها **لا تُصدر SQL**
(الخيارات تُتحقَّق في بايثون لا في المحرّك) — بل إن `0037` تنصّ صراحةً على أن
العمودين «varchar أصلاً فتوسيع الـchoices بلا DDL فعلي»، وهي مقولةٌ صحيحة عن
حالة الهجرات وكاذبة عن الجدول الحقيقي. واختبارات SQLite لا تعرف ENUM أصلاً
فتمرّ خضراء على جدولٍ يخالف نموذجه.

يُصلَح العمودان إلى ما يعلنه النموذج (`varchar` لا ENUM أوسع): قائمة الحالات
تنمو مع الدورة، وعمودٌ يلزمه `ALTER TABLE` لكل حالة جديدة هو الفخّ نفسه
مؤجَّلاً — نفس قرار `tenants/0022_subscription_plan_varchar`. `Direction` يُصلَح
معه رغم أن قيمتيه تطابقان النموذج اليوم: هو الفخّ ذاته ينتظر أول اتجاه ثالث.

لا شيء يُنفَّذ على غير MySQL.
"""
from django.db import migrations

TABLE = 'cheques'

#: (العمود، نوع النموذج، القيمة الافتراضية في الجدول، الـENUM للرجوع)
COLUMNS = [
    ('Status', 'varchar(50)', 'Draft',
     "enum('Draft','Under_Collection','Collected','Bounced','Returned')"),
    ('Direction', 'varchar(20)', 'Incoming',
     "enum('Incoming','Outgoing')"),
]

#: الحالات التي أدخلتها CHQ-1 ولا وجود لها في الـENUM القديم. عند الرجوع
#: تُطبَّع إلى أقرب حالة داخله وإلا فشل الرجوع بنفس الخطأ الذي جاء يصلحه.
BACKWARD_STATUS_MAP = {
    'Received': 'Under_Collection',   # الورقة في اليد ⇒ أقرب ما في القديم
    'Endorsed': 'Collected',          # خرجت من حوزتنا نهائياً
    'Cancelled': 'Returned',          # أُوقفت قبل صرفها
}


def _widen_to_varchar(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'mysql':
        return
    with connection.cursor() as cursor:
        for column, target_type, default, _enum in COLUMNS:
            # idempotent: لا نلمس عموداً صُحِّح سابقاً (أو وُلد varchar في
            # قاعدةٍ أُنشئت من الهجرات لا من المخطط الموروث).
            cursor.execute(
                """
                SELECT DATA_TYPE FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s AND COLUMN_NAME = %s
                """,
                [TABLE, column],
            )
            row = cursor.fetchone()
            if not row or row[0] != 'enum':
                continue
            cursor.execute(
                f"ALTER TABLE `{TABLE}` MODIFY `{column}` "
                f"{target_type} NOT NULL DEFAULT %s",
                [default],
            )


def _back_to_enum(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'mysql':
        return
    with connection.cursor() as cursor:
        for new_value, old_value in BACKWARD_STATUS_MAP.items():
            cursor.execute(
                f"UPDATE `{TABLE}` SET `Status` = %s WHERE `Status` = %s",
                [old_value, new_value],
            )
        for column, _target_type, default, enum_type in COLUMNS:
            cursor.execute(
                f"ALTER TABLE `{TABLE}` MODIFY `{column}` "
                f"{enum_type} NOT NULL DEFAULT %s",
                [default],
            )


class Migration(migrations.Migration):
    # DDL في MySQL لا يُلَفّ بمعاملة (لا رجوع له)، و`RunPython` ذرّيةٌ افتراضاً
    # ⇒ `TransactionManagementError`. نفس علاج `tenants/0022`.
    atomic = False

    dependencies = [
        ('accounting', '0038_cheque_document_movements'),
    ]

    operations = [
        migrations.RunPython(_widen_to_varchar, _back_to_enum),
    ]
