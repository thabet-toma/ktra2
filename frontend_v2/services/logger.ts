interface LogEntry {
  level: "info" | "warn" | "error" | "debug";
  message: string;
  timestamp: number;
  traceId?: string;
  extra?: Record<string, unknown>;
}

class ClientLogger {
  private buffer: LogEntry[] = [];
  private isFlushScheduled = false;

  public log(
    level: LogEntry["level"],
    message: string,
    extra?: Record<string, unknown>,
    traceId?: string
  ) {
    const entry: LogEntry = {
      level,
      message,
      timestamp: Date.now(),
      traceId,
      extra,
    };
    this.buffer.push(entry);
    this.scheduleFlush();
  }

  public info(message: string, extra?: Record<string, unknown>, traceId?: string) {
    this.log("info", message, extra, traceId);
  }

  public warn(message: string, extra?: Record<string, unknown>, traceId?: string) {
    this.log("warn", message, extra, traceId);
  }

  public error(message: string, extra?: Record<string, unknown>, traceId?: string) {
    this.log("error", message, extra, traceId);
  }

  public debug(message: string, extra?: Record<string, unknown>, traceId?: string) {
    this.log("debug", message, extra, traceId);
  }

  private scheduleFlush() {
    if (this.isFlushScheduled || this.buffer.length === 0) {
      return;
    }
    this.isFlushScheduled = true;

    const flushFn = () => {
      const logsToFlush = [...this.buffer];
      this.buffer = [];
      this.isFlushScheduled = false;

      if (logsToFlush.length === 0) return;

      const payload = JSON.stringify(logsToFlush);

      fetch("/api/client-logs/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: payload,
      }).catch((err) => {
        console.warn("Failed to flush client logs:", err);
        // Put back in buffer to retry next time if buffer hasn't grown too large
        if (this.buffer.length < 500) {
          this.buffer.unshift(...logsToFlush);
        }
      });
    };

    if (typeof requestIdleCallback === "function") {
      requestIdleCallback(() => flushFn(), { timeout: 2000 });
    } else {
      setTimeout(flushFn, 2000);
    }
  }
}

export const clientLogger = new ClientLogger();
