# Generated for GitHub #168: Silent migration copying Token rows to UserDevice

from django.db import migrations


def migrate_existing_tokens_to_devices(apps, schema_editor):
    """
    هجرة بيانات صامتة (GitHub #168):
    نسخ كل مفتاح توكن موجود في authtoken_token إلى جدول hr_userdevice
    بنفس القيمة تماماً، واسم «جهازٌ غير معروف»، وبلا user agent.
    لا يُرفض أي طلب مصادقة في يوم النشر.
    الصفوف القديمة في authtoken_token تُترك كما هي (خطوة رجعية آمنة).
    """
    Token = apps.get_model('authtoken', 'Token')
    UserDevice = apps.get_model('hr', 'UserDevice')

    existing_device_keys = set(UserDevice.objects.values_list('key', flat=True))
    to_create = []

    for token in Token.objects.all().iterator():
        if token.key not in existing_device_keys:
            to_create.append(
                UserDevice(
                    key=token.key,
                    user_id=token.user_id,
                    device_name="جهازٌ غير معروف",
                    label="",
                    user_agent="",
                    ip_address="",
                    created_at=token.created,
                    last_active_at=token.created,
                    is_primary=False,
                )
            )
            existing_device_keys.add(token.key)

    if to_create:
        UserDevice.objects.bulk_create(to_create)


def reverse_migration(apps, schema_editor):
    # نترك الصفوف دون حذف للحفاظ على استمرارية العمل
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0009_user_device'),
        ('authtoken', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            migrate_existing_tokens_to_devices,
            reverse_code=reverse_migration,
        ),
    ]
