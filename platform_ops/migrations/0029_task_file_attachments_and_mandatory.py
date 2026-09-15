"""‏#213-ب — ملفُّ المهمّة: مرفقاتٌ وإجباريّةٌ معلَنة.

**‏`is_mandatory` بافتراضٍ `True` على صفوفٍ قائمة، وهذا مقصود.** المهامُّ التي
أُنشئت قبل هذا التغيير أُسندت بلا خيار، ومنطقُها القديم كان يعرضها للقبول —
فوسمُها «اختياريّة» بأثرٍ رجعيٍّ كذبٌ على قارئها. والحقلُ يصف نيّةَ الإسناد لا
حالةَ الإسناد: صفوفُ `PlatformTaskAssignment` القائمة **لا تُلمَس** هنا، فمن كان
`OFFERED` يبقى `OFFERED` ويُقبَل بيده كما اعتاد. القاعدةُ الجديدة تحكم الإسنادَ
الجديدَ وحدَه.

وجدولُ المرفقات جديدٌ بالكامل — لا بياناتٍ تُنقَل ولا صفوفَ تُفحص قبلَه، فلا
`RunPython` هنا. وقيدُ `CheckConstraint` تفرضه MySQL 8.0.16 فصاعداً — وهو ما يعمل عليه الإنتاج —
بخلاف الفرادةِ المشروطةِ التي تتجاهلها بصمتٍ أيّ إصدار (انظر `0028`). **وليس
ضماناً كونيّاً**: جانغو يُسقط القيدَ بلا خطأٍ حيث `supports_table_check_constraints`
كاذبة (MariaDB، وMySQL أقدم)، والاختباراتُ على SQLite تفرضه دائماً فلا ترى الفرق.
فالحراسةُ البايثونيّةُ في `attach_to_platform_task` باقيةٌ ومصدرُ الرسالة العربيّة.

وقياسُ الإنتاج قبل الكتابة: لا مرفقاتٍ إطلاقاً (الجدولُ لم يكن موجوداً).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('platform_ops', '0028_conditional_uniqueness_becomes_real'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='platformtask',
            name='is_mandatory',
            field=models.BooleanField(default=True, help_text='الإجباريّةُ تُقبَل فورَ إسنادها؛ الاختياريّةُ تُعرَض وللموظّف قبولُها.', verbose_name='إجباريّة'),
        ),
        migrations.CreateModel(
            name='PlatformTaskAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('brief', 'شرحُ المدير'), ('work', 'ملفُّ الموظّف أثناء العمل'), ('delivery', 'مرفقُ تسليم')], db_index=True, max_length=10, verbose_name='الدور')),
                ('url', models.TextField(verbose_name='رابطُ الملفّ')),
                ('name', models.CharField(blank=True, default='', max_length=255, verbose_name='اسمُ الملفّ')),
                ('content_type', models.CharField(blank=True, default='', max_length=120, verbose_name='نوعُ المحتوى')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الرفع')),
                ('employee', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='platform_task_attachments', to='platform_ops.platformemployee', verbose_name='الموظّف')),
                ('submission', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='platform_ops.platformtasksubmission', verbose_name='التسليم')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='platform_ops.platformtask', verbose_name='المهمّة')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='الرافع')),
            ],
            options={
                'verbose_name': 'مرفق مهمّة منصّة',
                'verbose_name_plural': 'مرفقات مهامّ المنصّة',
                'ordering': ['created_at', 'id'],
                'indexes': [models.Index(fields=['task', 'kind', 'created_at'], name='platform_op_task_id_9e5a75_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('employee__isnull', True), ('kind', 'brief'), ('submission__isnull', True)), models.Q(('employee__isnull', False), ('kind', 'work'), ('submission__isnull', True)), models.Q(('employee__isnull', False), ('kind', 'delivery'), ('submission__isnull', False)), _connector='OR'), name='platform_ops_task_attachment_role_is_coherent')],
            },
        ),
    ]
