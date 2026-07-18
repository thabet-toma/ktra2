"""Logging handlers that work across all supported Python runtimes."""

import logging
import logging.handlers
import queue


class NonBlockingConsoleHandler(logging.Handler):
    """Send formatted log records to stderr through a background listener."""

    def __init__(self):
        super().__init__()
        log_queue = queue.Queue()
        self._console_handler = logging.StreamHandler()
        self._queue_handler = logging.handlers.QueueHandler(log_queue)
        self._listener = logging.handlers.QueueListener(
            log_queue,
            self._console_handler,
            respect_handler_level=True,
        )
        self._listener.start()
        self._listener_closed = False

    def setFormatter(self, formatter):
        super().setFormatter(formatter)
        self._queue_handler.setFormatter(formatter)

    def emit(self, record):
        self._queue_handler.emit(record)

    def close(self):
        if not self._listener_closed:
            self._listener_closed = True
            self._listener.stop()
            self._queue_handler.close()
            self._console_handler.close()
        super().close()
