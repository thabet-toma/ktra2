from rest_framework.views import exception_handler as drf_handler
from rest_framework.exceptions import ValidationError as DRFVE
from django.core.exceptions import ValidationError as DjangoVE
from rest_framework.response import Response
import logging
import uuid

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    if isinstance(exc, DjangoVE):
        if hasattr(exc, 'message_dict'):
            exc = DRFVE(detail=exc.message_dict)
        else:
            exc = DRFVE(detail=list(exc.messages) if hasattr(exc, 'messages') else [str(exc)])
    response = drf_handler(exc, context)
    if response is None:
        # Reuse the request-scoped trace id from RequestTracingMiddleware so the
        # 500 response, the request log line, and any client report share one
        # correlation id. Fall back to a fresh uuid if unavailable.
        from core.logger_middleware import get_current_trace_id
        trace_id = get_current_trace_id() or str(uuid.uuid4())
        logger.exception(f"Unhandled exception in view [trace_id:{trace_id}]")
        return Response({
            "detail": "حدث خطأ داخلي في الخادم.",
            "code": "internal_error",
            "trace_id": trace_id
        }, status=500)
    return response
