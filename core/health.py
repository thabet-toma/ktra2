import json
import logging
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse

logger = logging.getLogger("core.health")
client_logger = logging.getLogger("client_logs")

def health_check(request):
    if request.method in ('GET', 'HEAD'):
        return HttpResponse("OK", status=200)
    return HttpResponse("Method Not Allowed", status=405)

@csrf_exempt
def client_logs(request):
    if request.method != 'POST':
        return HttpResponse("Method Not Allowed", status=405)
    try:
        data = json.loads(request.body)
        logs = data if isinstance(data, list) else [data]
        
        for entry in logs:
            level = str(entry.get('level', 'info')).upper()
            message = entry.get('message', '')
            timestamp = entry.get('timestamp')
            trace_id = entry.get('traceId') or getattr(request, 'trace_id', 'N/A')
            extra = entry.get('extra', {})
            
            log_msg = f"[ClientLog] [{level}] TraceID: {trace_id} - Msg: {message} - Extra: {extra} - TS: {timestamp}"
            
            if level == 'ERROR':
                client_logger.error(log_msg)
            elif level in ('WARNING', 'WARN'):
                client_logger.warning(log_msg)
            elif level == 'DEBUG':
                client_logger.debug(log_msg)
            else:
                client_logger.info(log_msg)
                
        return JsonResponse({"status": "success"}, status=200)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
