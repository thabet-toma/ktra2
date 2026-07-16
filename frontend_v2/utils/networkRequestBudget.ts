/** Remaining time in a request-wide deadline; never returns a negative delay. */
export function remainingRequestBudgetMs(deadlineMs: number, nowMs = Date.now()): number {
  return Math.max(0, deadlineMs - nowMs);
}

/** Retry only when its backoff leaves actual time for the next attempt. */
export function retryFitsRequestBudget(
  deadlineMs: number,
  delayMs: number,
  nowMs = Date.now(),
): boolean {
  return nowMs + delayMs < deadlineMs;
}
