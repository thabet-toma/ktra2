"""#222 — واقعة انتهاء البطاقة، ومرساةُ إحيائها على الفاتورة.

`sales_invoice` يُملأ للبطاقات القائمة من `sales_invoice_line.invoice`: كانت
الفاتورة تُعرف من البند وحده، وهو ما ينقطع بصمت حين تُعدَّل المسودّة.
"""
from django.db import migrations, models
from django.db.models import OuterRef, Subquery
import django.db.models.deletion


def backfill_sales_invoice(apps, schema_editor):
    """كل بطاقةٍ لها بندٌ حيّ ترث فاتورته — دفعةً واحدة لا صفّاً صفّاً."""
    WarrantyCard = apps.get_model("after_sales", "WarrantyCard")
    SalesInvoiceLine = apps.get_model("sales", "SalesInvoiceLine")
    WarrantyCard.objects.filter(
        sales_invoice__isnull=True, sales_invoice_line__isnull=False,
    ).update(
        sales_invoice_id=Subquery(
            SalesInvoiceLine.objects
            .filter(pk=OuterRef("sales_invoice_line_id"))
            .values("invoice_id")[:1]
        )
    )


def unbackfill_sales_invoice(apps, schema_editor):
    """عكسٌ مُعلَن بلا عمل: العمود نفسه يسقط في `RemoveField` بعده."""


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0034_salesinvoiceline_serials_and_more"),
        ("after_sales", "0002_alter_aftersalessettings_default_labour_product"),
    ]

    operations = [
        migrations.AddField(
            model_name="warrantycard",
            name="sales_invoice",
            field=models.ForeignKey(
                blank=True,
                help_text="فاتورة البيع التي وَلَّدت البطاقة — مرساة إحيائها عند إعادة الترحيل",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="warranty_cards",
                to="sales.salesinvoice",
            ),
        ),
        migrations.AddField(
            model_name="warrantycard",
            name="ended_on",
            field=models.DateField(
                blank=True,
                help_text="يوم انتهاء البطاقة كواقعة — لا بانقضاء مدّتها",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="warrantycard",
            name="end_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("returned", "أُرجع الجهاز"),
                    ("invoice_unposted", "أُلغي ترحيل الفاتورة"),
                    ("sale_cancelled", "أُلغي البيع"),
                    ("superseded", "حلّت محلّها بطاقة أحدث"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="warrantycard",
            name="end_return_line",
            field=models.ForeignKey(
                blank=True,
                help_text="بند مرجع البيع الذي أنهى البطاقة — ومنه يُحييها إلغاءُ ترحيله",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ended_warranty_cards",
                to="sales.salesinvoiceline",
            ),
        ),
        migrations.AlterField(
            model_name="warrantycard",
            name="sales_invoice_line",
            field=models.ForeignKey(
                blank=True,
                help_text="بند فاتورة البيع الذي وَلَّد البطاقة — يُفرَّغ إن حُذف البند من المسودّة",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="warranty_cards",
                to="sales.salesinvoiceline",
            ),
        ),
        migrations.RunPython(backfill_sales_invoice, unbackfill_sales_invoice),
    ]
