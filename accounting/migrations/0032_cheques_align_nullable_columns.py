"""T-CHQ3/ح — مواءمة أعمدة `cheques` القابلة للفراغ مع النموذج.

بلاغ المالك: حفظ سند قبض بشيك بلا تاريخ استحقاق يرتدّ بـ500:
`IntegrityError (1048, "Column 'DueDate' cannot be null")`.

الجدول `cheques` مُرحَّل من مخطط قديم (كان `managed=False` في 0001)، فبقيت
أعمدة **NOT NULL** في MySQL بينما يعلنها النموذج `null=True` — وكل الكود
يعتمد إعلان النموذج. اختبارات SQLite تُبنى من النموذج لا من المخطط الحقيقي،
فلا تكشف هذا الانحراف أبداً (نفس درس «سجل التدقيق يُلغي القيد بصمت»).

`DueDate` أول عمود اصطدم به المستخدم فقط؛ الإصلاح يشمل كل أعمدة الجدول
القابلة للفراغ في النموذج كي لا يتكرر العطل مع `IssueDate` أو `PartnerID` أو
مفاتيح المستندات عند أول شيك لا يحمل أحدها.

الهجرة MySQL فقط، تقرأ `information_schema` فلا تلمس إلا الأعمدة المنحرفة
فعلاً (idempotent)، وتحافظ على نوع العمود وقيمته الافتراضية كما هي.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)

# أعمدة `cheques` التي يعلنها النموذج null=True.
NULLABLE_COLUMNS = [
    "BankID", "BankBranchID", "DepositBankAccountID", "BankName",
    "AccountNumber", "BankBranch", "DueDate", "IssueDate", "PayeeName",
    "PartnerID", "CreatedBy_UserID", "Notes", "SalesInvoiceID",
    "CustomerPaymentID", "SupplierPaymentID", "PurchaseInvoiceID",
    # CHQ-1: عمود جديد تنشئه الهجرة 0037 قابلاً للفراغ أصلاً، فلا انحراف له
    # ليُصحَّح — يدخل القائمة لأن الحارس يشترط تغطية كل حقل nullable على الشيك
    # (`accounting/tests/test_cheques_column_alignment.py`)، والمواءمة لا تلمس
    # إلا عموداً وجدته NOT NULL فعلاً.
    "EndorsedToPartnerID",
]


def align_nullable_columns(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_DEFAULT
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'cheques'
              AND IS_NULLABLE = 'NO'
              AND COLUMN_NAME IN %s
            """,
            [tuple(NULLABLE_COLUMNS)],
        )
        drifted = cursor.fetchall()
        for column_name, column_type, column_default in drifted:
            default_sql = ""
            if column_default is not None:
                default_sql = f" DEFAULT {column_default}"
            cursor.execute(
                f"ALTER TABLE `cheques` "
                f"MODIFY COLUMN `{column_name}` {column_type} NULL{default_sql}"
            )
            logger.info(
                "cheques.%s: NOT NULL → NULL (aligned with the model)", column_name,
            )
        if not drifted:
            logger.info("cheques: no drifted columns — nothing to align")


def noop_reverse(apps, schema_editor):
    """لا نُعيد فرض NOT NULL — الصفوف القائمة قد تحمل فراغات مشروعة."""


class Migration(migrations.Migration):
    # DDL على MySQL لا يرتد داخل معاملة — كما في 0031.
    atomic = False

    dependencies = [
        ("accounting", "0031_cost_centers_ensure_code_column"),
    ]

    operations = [
        migrations.RunPython(align_nullable_columns, noop_reverse),
    ]
