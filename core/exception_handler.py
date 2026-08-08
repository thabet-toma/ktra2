from django.conf import settings
from rest_framework.views import exception_handler as drf_handler
from rest_framework.exceptions import ValidationError as DRFVE
from django.core.exceptions import ValidationError as DjangoVE
from rest_framework.response import Response
import logging
import math
import uuid

logger = logging.getLogger(__name__)


def _throttle_detail(wait):
    """رسالة 429 بلغة المستخدم: «بعد 46 دقيقة» لا «خلال 2760 ثواني».

    ترجمة DRF العربية تعطي الثواني خاماً، فيقرأ المستخدم رقماً من أربع خانات لا
    يخبره متى يعود.
    """
    prefix = "تجاوزت حدّ المحاولات المسموح بها."
    if not wait:
        return f"{prefix} أعد المحاولة بعد قليل."
    seconds = math.ceil(wait)
    if seconds < 60:
        return f"{prefix} أعد المحاولة بعد {seconds} ثانية."
    minutes = math.ceil(seconds / 60)
    if minutes < 60:
        return f"{prefix} أعد المحاولة بعد دقيقة." if minutes == 1 else f"{prefix} أعد المحاولة بعد {minutes} دقيقة."
    hours = math.ceil(minutes / 60)
    return f"{prefix} أعد المحاولة بعد ساعة." if hours == 1 else f"{prefix} أعد المحاولة بعد {hours} ساعات."


def custom_exception_handler(exc, context):
    if isinstance(exc, DjangoVE):
        if hasattr(exc, 'message_dict'):
            exc = DRFVE(detail=exc.message_dict)
        else:
            exc = DRFVE(detail=list(exc.messages) if hasattr(exc, 'messages') else [str(exc)])
    response = drf_handler(exc, context)
    # رمز منع مقروء آلياً (مثل engagement_inactive) كي تعرف الواجهة سبب الـ403
    # وتتصرف — بدل تخمين النص العربي. مقصور على 403 حتى لا يلوّث أخطاء الحقول.
    if (
        response is not None
        and response.status_code == 403
        and isinstance(response.data, dict)
        and isinstance(getattr(exc, "code", None), str)
    ):
        response.data.setdefault("code", exc.code)
    # 429: رمز آلي + مهلة مقروءة بدل «خلال 2760 ثواني».
    if (
        response is not None
        and response.status_code == 429
        and isinstance(response.data, dict)
    ):
        response.data["code"] = "throttled"
        response.data["detail"] = _throttle_detail(getattr(exc, "wait", None))
    if response is None:
        # Reuse the request-scoped trace id from RequestTracingMiddleware so the
        # 500 response, the request log line, and any client report share one
        # correlation id. Fall back to a fresh uuid if unavailable.
        from core.logger_middleware import get_current_trace_id
        trace_id = get_current_trace_id() or str(uuid.uuid4())
        logger.exception(f"Unhandled exception in view [trace_id:{trace_id}]")
        body = {
            "detail": "حدث خطأ داخلي في الخادم.",
            "code": "internal_error",
            "trace_id": trace_id,
        }
        # في التطوير وحده: نوع الاستثناء ونصّه داخل الاستجابة. بدونهما يبقى
        # البلاغ «بضرب إيرور» ونصّ الاستثناء حبيسَ طرفية الخادم — ومن يبلّغ عن
        # العطل ليس بالضرورة من يقرأ اللوغ. لا يُسرَّب شيء في الإنتاج
        # (DEBUG=False) حيث يبقى `trace_id` وحده هو الرابط.
        if getattr(settings, "DEBUG", False):
            body["error"] = f"{type(exc).__name__}: {exc}"[:500]
        return Response(body, status=500)
    return response
