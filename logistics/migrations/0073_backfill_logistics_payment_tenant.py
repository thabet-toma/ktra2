"""P1-5 (SCALABILITY_AUDIT): تعبئة شركة دفعات اللوجستيات من وثيقتها الأم.

`0072` أضاف الحقل فارغاً؛ هذه تملؤه للصفوف القائمة. بلا هذه الخطوة تصير كل
الدفعات التاريخية `tenant=NULL` فتختفي من القوائم والداشبورد فور تحويل
الفلترة من `Q(deal__tenant) | Q(shipment__tenant)` إلى `tenant=`.

مصدر الحقيقة هو نفس المصدر الذي كان الـOR القديم يقرؤه:
  دفعة صفقة  → `deal.tenant`
  دفعة شحنة  → `shipment.tenant`
فالنتيجة مطابقة لما كان يظهر قبل الهجرة تماماً، لا اجتهاد فيها.

دفعة بلا صفقة وبلا شحنة (إن وُجدت) تبقى NULL — وهي كانت أصلاً خارج نتيجة
الـOR القديم، فلا سلوك يتغيّر لها.

التحديث بـ`update()` لا `save()` عمداً: نحن داخل هجرة، والنموذج التاريخي بلا
منطق `save()` المشتقّ، والمطلوب كتابة جماعية لا سطراً سطراً.
و`Subquery` لا `F('deal__tenant')`: Django يرفض عبور الضمّة داخل `UPDATE`
(`Joined field references are not permitted in this query`).
"""
from django.db import migrations
from django.db.models import OuterRef, Subquery


def backfill_tenant(apps, schema_editor):
    LogisticsPayment = apps.get_model('logistics', 'LogisticsPayment')
    LogisticsDeal = apps.get_model('logistics', 'LogisticsDeal')
    LogisticsShipment = apps.get_model('logistics', 'LogisticsShipment')

    LogisticsPayment.objects.filter(
        tenant__isnull=True, deal__isnull=False,
    ).update(tenant=Subquery(
        LogisticsDeal.objects.filter(pk=OuterRef('deal_id')).values('tenant_id')[:1]
    ))

    LogisticsPayment.objects.filter(
        tenant__isnull=True, shipment__isnull=False,
    ).update(tenant=Subquery(
        LogisticsShipment.objects.filter(pk=OuterRef('shipment_id')).values('tenant_id')[:1]
    ))


def clear_tenant(apps, schema_editor):
    LogisticsPayment = apps.get_model('logistics', 'LogisticsPayment')
    LogisticsPayment.objects.update(tenant=None)


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0072_logisticspayment_tenant_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_tenant, clear_tenant),
    ]
