from django.db import migrations, models


def _default_cost_lines():
    return [
        {"label": "ضريبة القيمة المضافة", "amount": 0},
        {"label": "رسوم البيان الجمركي", "amount": 0},
        {"label": "محطة الشحن", "amount": 0},
        {"label": "معالجة التصاريح", "amount": 0},
        {"label": "عمولة المخلص", "amount": 0},
        {"label": 'نظام الجمارك «الجيل الجديد»', "amount": 0},
    ]


class Migration(migrations.Migration):

    dependencies = [
        ("logistics", "0012_logisticspayment_shipment_agent_pay"),
    ]

    operations = [
        migrations.AddField(
            model_name="logisticsclearance",
            name="cost_lines",
            field=models.JSONField(
                blank=True,
                db_column="cost_lines",
                default=_default_cost_lines,
            ),
        ),
    ]
