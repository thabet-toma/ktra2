"""P0-3 (SCALABILITY_AUDIT): نسب سجلات الحضور والنقاط لشركة صاحبها الحقيقي.

`attendanceSessions` و`attendanceRecords` و`pointsHistory` كانت في
`GLOBAL_COLLECTIONS` ⇒ أي مستخدم من أي شركة يقرأ سجلات حضور ونقاط موظفي كل
الشركات. آخر ثغرة P0 مفتوحة.

لماذا لم تُغلَق في الجلسة الأمنية (2026-08-11): تقييدها بلا هجرة كان يُخفي
تاريخ الحضور والنقاط كاملاً (كل الوثائق `tenant=NULL`، والقراءة المُنطاقة
تفشل مغلقةً بحقّ منذ P0-4)، والهجرة الساذجة التي تنسب اليتيمة لشركة #1 كانت
**تمحو** تاريخ بقية الشركات بإسناده لشركة واحدة.

الهجرة هنا تنسب كل وثيقة لمالكها الفعلي، والمالك مستخرَج من بنية الوثيقة
نفسها لا من تخمين:

  pointsHistory/{userId}/days/{date}   ← المستخدم هو المقطع الثاني من المسار
  attendanceRecords/{uuid}             ← data['userId']
  attendanceSessions/{uuid}            ← data['createdBy'] (المدير الذي فتحها)

ثم المستخدم → شركته عبر `UserCompanyMembership`.

**تفشل مغلقةً عمداً:** وثيقة لا يُحسم مالكها (مستخدم محذوف، أو عضو في أكثر
من شركة فلا يُعرف لأيّها السجل) تبقى `tenant=NULL` ⇒ غير مقروءة لأحد بدل أن
تُنسب لشركة قد لا تملكها. إخفاء سجلٍّ يخصّ الغير أهون من كشفه، وعدد ما بقي
يُطبع في السجل ليُعالَج يدوياً إن لزم.

العكس (`reverse`) يعيدها كلها إلى NULL — أي إلى ما قبل النسب، لا إلى حالة
«عالمية»، لأن العالمية سلوك في `views.GLOBAL_COLLECTIONS` لا بيانات.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)

SCOPED_PREFIXES = ('attendanceSessions/', 'attendanceRecords/', 'pointsHistory/')


def _owner_user_id(path, data):
    """يستخرج معرّف المستخدم المالك من مسار الوثيقة أو حمولتها."""
    if path.startswith('pointsHistory/'):
        parts = path.split('/')
        return parts[1] if len(parts) > 1 else None
    if path.startswith('attendanceRecords/'):
        return (data or {}).get('userId')
    if path.startswith('attendanceSessions/'):
        return (data or {}).get('createdBy')
    return None


def attribute_to_owner_company(apps, schema_editor):
    FirestoreMirrorDoc = apps.get_model('bridge', 'FirestoreMirrorDoc')
    UserCompanyMembership = apps.get_model('tenants', 'UserCompanyMembership')

    # خريطة مستخدم → شركة، وحدها الوحيدة القابلة للحسم. من له عضويتان فأكثر
    # يُترك بلا نسب: لا يوجد في الوثيقة ما يدلّ على أيّ شركة تخصّها.
    tenant_by_user = {}
    ambiguous = set()
    for membership in UserCompanyMembership.objects.all().values('user_id', 'tenant_id'):
        uid = membership['user_id']
        if uid in tenant_by_user and tenant_by_user[uid] != membership['tenant_id']:
            ambiguous.add(uid)
        tenant_by_user[uid] = membership['tenant_id']
    for uid in ambiguous:
        tenant_by_user.pop(uid, None)

    attributed = 0
    unresolved = 0
    for prefix in SCOPED_PREFIXES:
        docs = FirestoreMirrorDoc.objects.filter(
            tenant__isnull=True, path__startswith=prefix,
        ).only('id', 'path', 'data')
        for doc in docs.iterator(chunk_size=500):
            raw_owner = _owner_user_id(doc.path, doc.data)
            try:
                owner_id = int(raw_owner)
            except (TypeError, ValueError):
                unresolved += 1
                continue
            tenant_id = tenant_by_user.get(owner_id)
            if tenant_id is None:
                unresolved += 1
                continue
            FirestoreMirrorDoc.objects.filter(pk=doc.pk).update(tenant_id=tenant_id)
            attributed += 1

    logger.warning(
        "P0-3 bridge attribution: attributed=%s unresolved=%s "
        "(unresolved stay tenant=NULL and are readable by nobody)",
        attributed, unresolved,
    )


def clear_attribution(apps, schema_editor):
    FirestoreMirrorDoc = apps.get_model('bridge', 'FirestoreMirrorDoc')
    for prefix in SCOPED_PREFIXES:
        FirestoreMirrorDoc.objects.filter(path__startswith=prefix).update(tenant=None)


class Migration(migrations.Migration):

    dependencies = [
        ('bridge', '0004_attribute_orphan_scoped_docs'),
        ('tenants', '0018_alter_rolepermission_role_and_more'),
    ]

    operations = [
        migrations.RunPython(attribute_to_owner_company, clear_attribution),
    ]
