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
        trace_id = str(uuid.uuid4())
        logger.exception(f"Unhandled exception in view [trace_id:{trace_id}]")
        return Response({
            "detail": "حدث خطأ داخلي في الخادم.",
            "code": "internal_error",
            "trace_id": trace_id
        }, status=500)
    return response
