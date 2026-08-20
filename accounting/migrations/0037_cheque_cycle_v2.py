"""CHQ-1 — مخطط دورة الشيك الجديدة.

`status` و`movement_type` عمودا varchar أصلاً، فتوسيع الـchoices بلا DDL فعلي
على البيانات. الجديد الحقيقي مفتاحان أجنبيان: `endorsed_to` (مستفيد التظهير)
و`ChequeMovement.journal` (قيد الحركة). **لا هجرة بيانات على صفوف الشيكات** —
قاعدة الـcutover: القديم يكمل مساره والجديد يبدأ على المسار الجديد.

الاستثناء الوحيد: ربطُ الحركات القديمة بقيودها حيث يكون الربط قاطعاً — قيد
واحد فقط يطابق `(CHEQUE_<MOVE>, cheque_id)`. best-effort وقابل للعكس.
"""

import django.db.models.deletion
from django.db import migrations, models


def link_existing_movement_journals(apps, schema_editor):
    """يملأ `ChequeMovement.journal` للحركات القديمة — بلا تخمين.

    القيود القديمة رُحِّلت بمرجع `(CHEQUE_<MOVE>, cheque_id)`، فالربط قاطع
    فقط حين يكون للشيك حركةٌ واحدة من ذلك النوع وقيدٌ واحد يطابقها. أي غموض
    (حركتان من النوع نفسه على الشيك) يُترك فارغاً بدل ربط مُختلَق.
    """
    Cheque = apps.get_model('accounting', 'Cheque')
    ChequeMovement = apps.get_model('accounting', 'ChequeMovement')
    JournalHeader = apps.get_model('accounting', 'JournalHeader')

    tenant_of = dict(Cheque.objects.values_list('id', 'tenant_id'))
    rows = list(
        ChequeMovement.objects
        .filter(journal__isnull=True)
        .values_list('id', 'cheque_id', 'movement_type')
    )
    counts = {}
    for _mid, cheque_id, movement_type in rows:
        key = (cheque_id, movement_type)
        counts[key] = counts.get(key, 0) + 1

    for movement_id, cheque_id, movement_type in rows:
        if counts[(cheque_id, movement_type)] != 1:
            continue  # حركتان من النوع نفسه — لا مرجع يميّز قيد أيّهما
        tenant_id = tenant_of.get(cheque_id)
        if tenant_id is None:
            continue
        # عزل الشركة صريح: المرجع وحده لا يضمنه، وقيد شركة أخرى لا يُربط أبداً.
        journal_ids = list(
            JournalHeader.objects.filter(
                tenant_id=tenant_id,
                reference_type=f"CHEQUE_{movement_type.upper()}",
                reference_id=cheque_id,
            ).values_list('id', flat=True)[:2]
        )
        if len(journal_ids) == 1:
            ChequeMovement.objects.filter(pk=movement_id).update(
                journal_id=journal_ids[0])


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0036_opening_balance'),
        ('partners', '0014_partner_idx_partner_tenant_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='cheque',
            name='endorsed_to',
            field=models.ForeignKey(blank=True, db_column='EndorsedToPartnerID', help_text='الطرف الذي ظُهِّر له الشيك', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='endorsed_cheques', to='partners.partner'),
        ),
        migrations.AddField(
            model_name='chequemovement',
            name='journal',
            field=models.ForeignKey(blank=True, db_column='JournalID', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cheque_movements', to='accounting.journalheader'),
        ),
        migrations.AlterField(
            model_name='cheque',
            name='status',
            field=models.CharField(choices=[('Draft', 'Draft'), ('Received', 'Received'), ('Under_Collection', 'Under Collection'), ('Collected', 'Collected'), ('Bounced', 'Bounced'), ('Returned', 'Returned'), ('Settled', 'Settled'), ('Endorsed', 'Endorsed'), ('Cancelled', 'Cancelled')], db_column='Status', default='Draft', max_length=50),
        ),
        migrations.AlterField(
            model_name='chequemovement',
            name='movement_type',
            field=models.CharField(choices=[('receive', 'استلام'), ('deposit', 'إيداع'), ('redeposit', 'إعادة إيداع'), ('withdraw', 'صرف'), ('collect', 'تحصيل'), ('endorse', 'تظهير'), ('bounce', 'رفض'), ('return_to_customer', 'إرجاع للعميل'), ('cancel', 'إلغاء'), ('settle', 'تسوية')], db_column='MovementType', max_length=30),
        ),
        migrations.RunPython(
            link_existing_movement_journals,
            migrations.RunPython.noop,
        ),
    ]
