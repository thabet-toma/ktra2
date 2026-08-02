import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0003_assistantlesson'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DevelopmentNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('status', models.CharField(choices=[('todo', 'قيد الانتظار'), ('in_progress', 'قيد التنفيذ'), ('done', 'مكتملة')], default='todo', max_length=20)),
                ('priority', models.CharField(choices=[('low', 'منخفضة'), ('medium', 'متوسطة'), ('high', 'عالية')], default='medium', max_length=20)),
                ('assignee', models.CharField(blank=True, default='', max_length=150)),
                ('due_date', models.DateField(blank=True, null=True)),
                ('position', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_development_notes', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updated_development_notes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'development_notes',
                'ordering': ['position', '-updated_at', '-id'],
            },
        ),
    ]
