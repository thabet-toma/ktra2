import uuid
import time
import logging
import threading

logger = logging.getLogger("core.request_tracing")
_thread_locals = threading.local()

def get_current_trace_id():
    return getattr(_thread_locals, 'trace_id', None)

class RequestTracingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    # Paths too noisy to log on every request (e.g. the 30s offline heartbeat).
    SKIP_LOG_PREFIXES = ('/api/health',)

    def __call__(self, request):
        trace_id = request.headers.get('X-Trace-ID') or request.headers.get('X-Request-ID')
        if not trace_id:
            trace_id = str(uuid.uuid4())

        request.trace_id = trace_id
        _thread_locals.trace_id = trace_id

        start_time = time.time()
        try:
            response = self.get_response(request)
            duration = time.time() - start_time

            if not request.path.startswith(self.SKIP_LOG_PREFIXES):
                level = logging.WARNING if response.status_code >= 500 else logging.INFO
                logger.log(
                    level,
                    f"Request: {request.method} {request.get_full_path()} - "
                    f"Status: {response.status_code} - "
                    f"Duration: {duration:.4f}s - "
                    f"TraceID: {trace_id}"
                )

            response['X-Trace-ID'] = trace_id
            return response
        finally:
            # Always clear the thread local to avoid leaking across requests
            # that reuse the same worker thread.
            if hasattr(_thread_locals, 'trace_id'):
                del _thread_locals.trace_id
