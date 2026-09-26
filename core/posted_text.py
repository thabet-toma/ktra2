"""نصوص المستند المرحَّل: الملاحظة ورقم المستند الخارجي تُعدَّل بعد الترحيل — وحدها.

المستند المرحَّل يرفض التعديل (`POSTED_DOC_WARNING`) لأن قيده يعكس مبالغه وحساباته
وتاريخه وطرفه. الملاحظة لا أثر محاسبي لها، فتُعدَّل والمستند مرحَّلٌ وموزَّع — بقائمة
حقولٍ **صريحة** لكل نموذج (`POSTED_TEXT_FIELDS`) لا «كلّ ما ليس مالياً»: حقلٌ جديد يُضاف
للنموذج غداً يبقى مقفلاً حتى يُضاف هنا عمداً.

- أيّ حقلٍ خارج القائمة على مستندٍ مرحَّل ⇒ رفضٌ برسالة الترحيل وأسماء الحقول.
- الحفظ بـ`update()` على الأعمدة المسموحة وحدها (بلا `save()` ولا إشاراته): لا يمسّ
  مبلغاً ولا حساباً ولا تاريخاً ولا طرفاً ولا عملةً ولا توزيعاً.
- وصف القيد المشتقّ من الملاحظة يتبعها (`sync`) — نصُّه وحده، عبر
  `accounting.services.rewrite_journal_texts`.
- كلّ تعديلٍ في سجلّ النشاط: القيمة قبل/بعد والمستخدم.

`PostedTextEditMixin` يربط ذلك بمسار التعديل القائم (PUT/PATCH) لكل ViewSet، و
`save_posted_text` للمسارات الخاصة (دفعات التخليص والإرسالية).
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.activity import build_activity_changes, describe_activity_changes, log_activity
from core.api_defaults import POSTED_DOC_WARNING

logger = logging.getLogger(__name__)

#: «app.Model» ← الحقول النصّية المسموح تعديلها على المستند المرحَّل، وتسمياتها في السجلّ.
POSTED_TEXT_FIELDS: dict[str, dict[str, str]] = {
    'sales.SupplierPayment': {'notes': 'الملاحظات'},
    'sales.CustomerPayment': {'notes': 'الملاحظات'},
    'sales.CreditDebitNote': {'reason': 'السبب'},
    'sales.SalesInvoice': {'notes': 'الملاحظات'},
    'logistics.PurchaseInvoice': {'notes': 'الملاحظات', 'supplier_invoice_number': 'رقم فاتورة المورد'},
    'logistics.LogisticsClearancePayment': {'notes': 'الملاحظات'},
    'logistics.LocalShipmentPayment': {'notes': 'الملاحظات'},
    'logistics.LogisticsPayment': {'notes': 'الملاحظات'},
}


def posted_text_labels(model) -> dict[str, str]:
    return POSTED_TEXT_FIELDS.get(f"{model._meta.app_label}.{model.__name__}", {})


def reject_locked_fields(instance, data) -> None:
    """مستندٌ مرحَّل: أيّ مفتاحٍ خارج قائمة نموذجه ⇒ رفضٌ كما قبل هذه القائمة."""
    locked = sorted(set(data) - set(posted_text_labels(type(instance))))
    if locked:
        raise ValidationError({'detail': POSTED_DOC_WARNING, 'can_unpost': True, 'locked_fields': locked})


def _clean(instance, field: str, value) -> str:
    text = '' if value is None else str(value).strip()
    max_length = instance._meta.get_field(field).max_length
    if max_length and len(text) > max_length:
        raise ValidationError({field: f"النصّ أطول من {max_length} حرفاً."})
    return text


def save_posted_text(instance, data, *, entity_type: str, entity_label: str, request=None,
                     partner_ids=None, sync=None) -> list[dict]:
    """يحفظ الحقول النصّية المسموحة وحدها ويُسجّلها. يُرجع فروقات السجلّ ([] = لا تغيير).

    `sync(instance, before)`: يُحدّث وصف القيد المشتقّ من النصّ — داخل المعاملة نفسها.
    """
    reject_locked_fields(instance, data)
    labels = posted_text_labels(type(instance))
    model = type(instance)
    before = {f: getattr(instance, f) or '' for f in data}
    after = {f: _clean(instance, f, data[f]) for f in data}
    changed = {f: v for f, v in after.items() if v != before[f]}
    if not changed:
        return []
    columns = dict(changed)
    for field in model._meta.concrete_fields:
        if getattr(field, 'auto_now', False):
            columns[field.name] = timezone.now()
    with transaction.atomic():
        model._base_manager.filter(pk=instance.pk).update(**columns)
        for field, value in columns.items():
            setattr(instance, field, value)
        if sync is not None:
            sync(instance, before)
        changes = build_activity_changes(before=before, after=after, labels=labels)
        log_activity(
            action='update', entity_type=entity_type, entity_id=instance.pk, entity_label=entity_label,
            description=f"تعديل نصّ مستند مرحَّل — {describe_activity_changes(changes)}",
            metadata={'changes': changes, 'posted': True}, partner_ids=partner_ids, request=request,
        )
    logger.info("posted_text.update %s id=%s fields=%s", entity_type, instance.pk, sorted(changed))
    return changes


class PostedTextEditMixin:
    """مسار التعديل القائم (PUT/PATCH) على مستندٍ مرحَّل يقبل حقول القائمة وحدها.

    الـViewSet يُعرّف `posted_text_entity_type` و`is_posted_document(instance)`، واختيارياً
    `posted_text_perm` (صلاحية التعديل نفسها) و`posted_text_label(instance)`/
    `posted_text_partner_ids(instance)` و`sync_posted_text(instance, before)`.
    المسودة تمرّ بالمسار العادي كما كانت.
    """
    posted_text_entity_type = ''
    posted_text_perm: str | None = None

    def is_posted_document(self, instance) -> bool:
        return bool(getattr(instance, 'is_posted', False))

    def posted_text_label(self, instance) -> str:
        return f"#{instance.pk}"

    def posted_text_partner_ids(self, instance) -> list:
        partner_id = getattr(instance, 'partner_id', None)
        return [partner_id] if partner_id else []

    def sync_posted_text(self, instance, before) -> None:
        """لا وصف قيدٍ مشتقٌّ من النصّ افتراضياً."""

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not self.is_posted_document(instance):
            return super().update(request, *args, **kwargs)
        if self.posted_text_perm:
            from core.access import require_perm

            require_perm(request, self.posted_text_perm)
        save_posted_text(
            instance, request.data, entity_type=self.posted_text_entity_type,
            entity_label=self.posted_text_label(instance), request=request,
            partner_ids=self.posted_text_partner_ids(instance), sync=self.sync_posted_text,
        )
        return Response(self.get_serializer(instance).data)


__all__ = ['POSTED_TEXT_FIELDS', 'PostedTextEditMixin', 'posted_text_labels', 'reject_locked_fields',
           'save_posted_text']
