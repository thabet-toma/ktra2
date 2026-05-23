from rest_framework.views import exception_handler as drf_handler
from rest_framework.exceptions import ValidationError as DRFVE
from django.core.exceptions import ValidationError as DjangoVE
import logging

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    if isinstance(exc, DjangoVE):
        if hasattr(exc, 'message_dict'):
            exc = DRFVE(detail=exc.message_dict)
        else:
            exc = DRFVE(detail=list(exc.messages) if hasattr(exc, 'messages') else [str(exc)])
    response = drf_handler(exc, context)
    if response is None:
        logger.exception("Unhandled exception in view")
    return response
