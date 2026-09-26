"""سند «الزيادة» يحمل أصله: الصنف والمستحق والدفعة الأصلية — وتعبئة القائم.

1. سجلّ التدقيق `SPLIT_OVERPAYMENT` (فصلُ دفعةٍ مرحَّلة بالأمر أو بتعديل الاستحقاق):
   الدفعة معرّفه، والسند «on-account voucher #N» في نصّه.
2. ما بقي (فصلٌ لحظة الترحيل بلا سجلّ): ملاحظة السند «دفعة تحت الحساب — زيادة دفعة
   تخليص #3 — …» أو «… إرسالية LS-0003 · …» — والدفعة حين تكون وحيدةً على المستند بتاريخ السند.
"""
import re

from django.db import migrations, models

NOTE_PREFIX = "دفعة تحت الحساب — زيادة دفعة "
VOUCHER_RE = re.compile(r"on-account voucher #(\d+)")
CLEARANCE_RE = re.compile(r"^تخليص #(\d+)")
LOCAL_RE = re.compile(r"^إرسالية ([^\s·]+)")
PAYMENT_KIND = {'LogisticsClearancePayment': 'clearance', 'LocalShipmentPayment': 'local'}


def backfill(apps, schema_editor):
    SupplierPayment = apps.get_model('sales', 'SupplierPayment')
    AuditLog = apps.get_model('accounting', 'AccountingAuditLog')
    ClearancePayment = apps.get_model('logistics', 'LogisticsClearancePayment')
    LocalPayment = apps.get_model('logistics', 'LocalShipmentPayment')
    LocalShipment = apps.get_model('logistics', 'LocalShipment')
    payment_models = {'clearance': (ClearancePayment, 'clearance_id'), 'local': (LocalPayment, 'local_shipment_id')}

    for log in AuditLog.objects.filter(action='SPLIT_OVERPAYMENT').order_by('pk'):
        kind = PAYMENT_KIND.get(log.model_name)
        match = VOUCHER_RE.search(log.change_details or '')
        if not kind or not match:
            continue
        model, doc_field = payment_models[kind]
        payment = model.objects.filter(pk=log.object_id, tenant_id=log.tenant_id).first()
        if payment is None:
            continue
        SupplierPayment.objects.filter(
            pk=int(match.group(1)), tenant_id=log.tenant_id, split_from_kind='',
        ).update(split_from_kind=kind, split_from_doc_id=getattr(payment, doc_field),
                 split_from_payment_id=payment.pk)

    for voucher in SupplierPayment.objects.filter(split_from_kind='', notes__startswith=NOTE_PREFIX):
        label = voucher.notes[len(NOTE_PREFIX):]
        kind = doc_id = None
        match = CLEARANCE_RE.match(label)
        if match:
            kind, doc_id = 'clearance', int(match.group(1))
        else:
            match = LOCAL_RE.match(label)
            if match:
                kind, number = 'local', match.group(1)
                # إرساليةٌ بلا رقم وُسمت بمعرّفها («إرسالية #12»).
                doc_id = int(number[1:]) if re.fullmatch(r"#\d+", number) else LocalShipment.objects.filter(
                    tenant_id=voucher.tenant_id, shipment_number=number,
                ).values_list('pk', flat=True).first()
        if not kind or not doc_id:
            continue
        model, doc_field = payment_models[kind]
        candidates = list(model.objects.filter(
            tenant_id=voucher.tenant_id, payment_date=voucher.payment_date, **{doc_field: doc_id},
        ).values_list('pk', flat=True)[:2])
        SupplierPayment.objects.filter(pk=voucher.pk).update(
            split_from_kind=kind, split_from_doc_id=doc_id,
            split_from_payment_id=candidates[0] if len(candidates) == 1 else None,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0048_supplierpayment_adjust_surplus'),
        ('accounting', '0046_journalline_amount_currency'),
        ('logistics', '0096_note_allocations'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplierpayment',
            name='split_from_kind',
            field=models.CharField(blank=True, db_column='SplitFromKind', default='', max_length=10),
        ),
        migrations.AddField(
            model_name='supplierpayment',
            name='split_from_doc_id',
            field=models.IntegerField(blank=True, db_column='SplitFromDocID', null=True),
        ),
        migrations.AddField(
            model_name='supplierpayment',
            name='split_from_payment_id',
            field=models.IntegerField(blank=True, db_column='SplitFromPaymentID', null=True),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
