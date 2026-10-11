"""التزامن المتفائل للمستندات: `ETag` على القراءة و`If-Match` على الكتابة (RFC 9110).

المشكلة: طرفان (تطبيق المستودع الخارجي والمحاسب في المنصة) يعدّلان المستند نفسه عبر
الـAPI، فيمحو PATCH الثاني تعديل الأول بصمت. الحل المعياري (وما تفعله QuickBooks بـ
`SyncToken`): كل قراءة تُرجع `ETag`، والكتابة التي تحمل `If-Match` بغير الحالي تُرفض
بـ412 **قبل أيّ كتابة**.

- التوكن قويٌّ مقتبس: `"<ميكروثانيات منذ الإيبوك>"` مشتقٌّ من `updated_at` بدقّته الكاملة
  — لا عدّاد جديد يُخزَّن ولا عمود. لذلك يجب أن يتحرّك `updated_at` عند كل تعديلٍ حقيقي
  (`save()` الكامل يفعل، و`save(update_fields=[...])` لا يفعل إلا إن ذُكر فيها).
- غياب `If-Match` ⇒ لا فحص (الواجهة الداخلية تعمل كما كانت)، و`*` ⇒ «أيّ نسخةٍ قائمة».
- القائمة المفصولة بفواصل مقبولة. المقارنة قوية (لا `W/` ضعيفة) كما يوجب RFC لـIf-Match.
- ترويسة `ETag` تُحقن في ردود retrieve/create/update/partial_update و`customer_approval` فقط، وتُقرأ من القاعدة
  بالمعرّف الذي تحمله الاستجابة: الإرسالية تُستبدل بصفٍّ جديد عند التعديل (عكس ثم تطبيق)
  فتحمل الاستجابة معرّفها الجديد، والترحيل التلقائي عند الإنشاء يعدّل الصفّ بعد التسلسل.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from rest_framework import serializers, status
from rest_framework.response import Response

logger = logging.getLogger(__name__)

_EPOCH = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)
_MICROSECOND = timedelta(microseconds=1)

STALE_DOCUMENT_MESSAGE = "المستند عُدّل منذ قراءتك — أعد قراءته ثم أعد التعديل"
STALE_DOCUMENT_CODE = "stale_document"

# `customer_approval`: نقطة قرار الزبون على المبيعات تعدّل المستند فتُرجع توكنه الجديد.
_ETAG_ACTIONS = {"retrieve", "create", "update", "partial_update", "customer_approval"}


def etag_from_stamp(stamp: datetime) -> str:
    return f'"{(stamp - _EPOCH) // _MICROSECOND}"'


def etag_for(instance) -> str | None:
    """توكن المستند الحالي من `updated_at`؛ `None` إن لم يكن للمستند ختمُ تعديل."""
    stamp = getattr(instance, "updated_at", None)
    return None if stamp is None else etag_from_stamp(stamp)


def parse_if_match(header: str | None) -> list[str] | None:
    """قيمة `If-Match` ← قائمة توكنات؛ `None` = لا شرط (غائبة أو فارغة)."""
    if header is None or not header.strip():
        return None
    return [token.strip() for token in header.split(",") if token.strip()]


class OptimisticConcurrencyMixin:
    """يُوضع **أولاً** في قواعد الـViewSet: يفحص `If-Match` قبل أيّ مسار تعديل (بما فيه
    `PostedTextEditMixin` وعكس الإرسالية)، ثم يحقن `ETag` في الردود.

    `partial_update` في DRF يمرّ عبر `update`، فيكفي اعتراضه وحده.
    """

    def update(self, request, *args, **kwargs):
        if parse_if_match(request.META.get("HTTP_IF_MATCH")) is not None:
            stale = self.precondition_failed(request, self.get_object())
            if stale is not None:
                return stale
        return super().update(request, *args, **kwargs)

    def precondition_failed(self, request, instance):
        """412 إن حمل الطلب `If-Match` لا يطابق الحالي، وإلا `None`.

        نقطةٌ عامة لـViewSet يعرّف `update` بنفسه (الإرسالية) فيحجب `update` هذا.
        """
        tokens = parse_if_match(request.META.get("HTTP_IF_MATCH"))
        if tokens is None or "*" in tokens:
            return None
        current = etag_for(instance)
        if current in tokens:
            return None
        logger.info(
            "concurrency.stale %s id=%s user=%s",
            instance._meta.model_name, instance.pk, getattr(request.user, "pk", None),
        )
        return Response(
            {
                "error": STALE_DOCUMENT_MESSAGE,
                "code": STALE_DOCUMENT_CODE,
                "current_etag": current,
                "updated_at": serializers.DateTimeField().to_representation(instance.updated_at),
            },
            status=status.HTTP_412_PRECONDITION_FAILED,
        )

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if (
            getattr(self, "action", None) in _ETAG_ACTIONS
            and response.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
            and isinstance(response.data, dict)
            and response.data.get("id") is not None
        ):
            stamp = (
                self.queryset.model._base_manager
                .filter(pk=response.data["id"]).values_list("updated_at", flat=True).first()
            )
            if stamp is not None:
                response["ETag"] = etag_from_stamp(stamp)
        return response


__all__ = ["OptimisticConcurrencyMixin", "STALE_DOCUMENT_CODE", "STALE_DOCUMENT_MESSAGE",
           "etag_for", "etag_from_stamp", "parse_if_match"]
