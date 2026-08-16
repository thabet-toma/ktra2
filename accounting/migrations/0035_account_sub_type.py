"""THA-111-T1 — `Account.sub_type`: العمود + اشتقاق التصنيف لكل الشركات.

العمود nullable بلا default: إضافة عمود فارغ في MySQL لا تعيد كتابة جدول
`chartofaccounts` (ALGORITHM=INSTANT)، فالإضافة آمنة على قاعدة إنتاج فيها
بيانات شركات حقيقية.

الاشتقاق نفسه يعيش في `accounting/account_classification.py` لا هنا: نفس
الدالة تخدم الـmigration والاختبارات وأي إعادة تشغيل لاحقة، وتبقى قابلة
للاختبار بعد تطبيق الـmigration. تُمرَّر لها الموديلات التاريخية فلا تتعلّق
بشكل الموديل الحيّ مستقبلاً. لا تكسر شركةً تنقصها جذور الشجرة المعيارية —
غياب الجذر يعني أن تلك الخطوة لا تجيب، لا أن العملية تفشل.
"""
from django.db import migrations, models


def classify_existing_accounts(apps, schema_editor):
    from accounting.account_classification import backfill_account_sub_types

    backfill_account_sub_types(
        Account=apps.get_model("accounting", "Account"),
        BankAccount=apps.get_model("accounting", "BankAccount"),
        CashBoxLedgerAccount=apps.get_model("accounting", "CashBoxLedgerAccount"),
        Partner=apps.get_model("partners", "Partner"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0034_journalheader_created_by"),
        ("partners", "0006_n9_t8_partner_row_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="sub_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("cash_box", "صندوق نقدية"),
                    ("bank", "حساب بنكي"),
                    ("receivable", "ذمم مدينة"),
                    ("payable", "ذمم دائنة"),
                    ("inventory", "مخزون"),
                ],
                db_column="SubType",
                help_text="التصنيف الوظيفي: صندوق/بنك/ذمم مدينة/ذمم دائنة/مخزون. فارغ = حساب عادي.",
                max_length=20,
                null=True,
            ),
        ),
        migrations.RunPython(classify_existing_accounts, migrations.RunPython.noop),
    ]
