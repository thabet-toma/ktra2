import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0014_product_sale_price'),
        ('logistics', '0068_split_gr_ir_account'),
        ('partners', '0013_general_note_targets'),
        ('tenants', '0018_alter_rolepermission_role_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='supplierquotation',
            name='supplier_draft_name',
            field=models.CharField(blank=True, db_column='SupplierDraftName', default='', help_text='اسم مورد مبدئي غير مسجَّل — يُنشأ كشريك عند التحويل فقط', max_length=200),
        ),
        migrations.AlterField(
            model_name='supplierquotation',
            name='supplier',
            field=models.ForeignKey(blank=True, db_column='SupplierID', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='supplier_quotations', to='partners.partner'),
        ),
        migrations.AlterField(
            model_name='supplierquotationline',
            name='product',
            field=models.ForeignKey(blank=True, db_column='ProductID', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='supplier_quotation_lines', to='inventory.product'),
        ),
        migrations.AddConstraint(
            model_name='supplierquotation',
            constraint=models.CheckConstraint(condition=models.Q(('supplier__isnull', False), models.Q(('supplier_draft_name', ''), _negated=True), _connector='OR'), name='supplier_quote_has_party'),
        ),
        migrations.AddConstraint(
            model_name='supplierquotationline',
            constraint=models.CheckConstraint(condition=models.Q(('product__isnull', False), models.Q(('name_snapshot', ''), _negated=True), _connector='OR'), name='supplier_quote_line_named'),
        ),
    ]
