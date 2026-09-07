# Generated manually for THA-166 م٦ (store home blocks)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0011_m5_collection_view_and_order_intent'),
    ]

    operations = [
        migrations.CreateModel(
            name='StoreHomeBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('hero', 'لافتة كبرى'), ('campaign_row', 'صفّ حملة'), ('category_row', 'صفّ فئة'), ('featured', 'صفّ منتقىً باليد'), ('most_viewed', 'الأكثر مشاهدة'), ('active_campaigns', 'الحملات السارية')], db_column='Kind', max_length=20)),
                ('title', models.CharField(blank=True, db_column='Title', default='', max_length=200)),
                ('subtitle', models.CharField(blank=True, db_column='Subtitle', default='', max_length=300)),
                ('image_url', models.CharField(blank=True, db_column='ImageUrl', default='', max_length=500)),
                ('image_url_mobile', models.CharField(blank=True, db_column='ImageUrlMobile', default='', max_length=500)),
                ('link_kind', models.CharField(choices=[('collection', 'حملة'), ('category', 'فئة'), ('product', 'منتج'), ('url', 'رابط خارجي'), ('none', 'بلا وجهة')], db_column='LinkKind', default='none', max_length=20)),
                ('link_id', models.PositiveIntegerField(blank=True, db_column='LinkID', null=True)),
                ('link_url', models.CharField(blank=True, db_column='LinkUrl', default='', max_length=500)),
                ('source_id', models.PositiveIntegerField(blank=True, db_column='SourceID', null=True)),
                ('limit', models.PositiveIntegerField(db_column='Limit', default=12)),
                ('sort_order', models.PositiveIntegerField(db_column='SortOrder', default=0)),
                ('is_active', models.BooleanField(db_column='IsActive', default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_column='CreatedAt')),
                ('updated_at', models.DateTimeField(auto_now=True, db_column='UpdatedAt')),
                ('tenant', models.ForeignKey(db_column='TenantID', on_delete=django.db.models.deletion.CASCADE, related_name='store_home_blocks', to='tenants.tenant')),
            ],
            options={
                'db_table': 'store_home_blocks',
                'ordering': ['sort_order', 'id'],
                'managed': True,
            },
        ),
    ]
