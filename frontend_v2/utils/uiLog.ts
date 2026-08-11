export type UiLogLevel = 'debug' | 'info' | 'warn' | 'error';

const UI_LOG_LEVEL_KEY = 'ktra.uiLogLevel';
const LOG_LEVEL_PRIORITY: Record<UiLogLevel, number> = {
    debug: 0,
    info: 1,
    warn: 2,
    error: 3,
};

const getConfiguredLevel = (): UiLogLevel => {
    try {
        const configuredLevel = localStorage.getItem(UI_LOG_LEVEL_KEY);
        if (configuredLevel && configuredLevel in LOG_LEVEL_PRIORITY) {
            return configuredLevel as UiLogLevel;
        }
    } catch {
        // Logging must remain best-effort when storage is unavailable.
    }

    return 'warn';
};

const log = (level: UiLogLevel, ...details: unknown[]): void => {
    if (LOG_LEVEL_PRIORITY[level] < LOG_LEVEL_PRIORITY[getConfiguredLevel()]) return;

    queueMicrotask(() => {
        console[level]('[K.T.R.A UI]', ...details);
    });
};

export const uiLog = {
    debug: (...details: unknown[]) => log('debug', ...details),
    info: (...details: unknown[]) => log('info', ...details),
    warn: (...details: unknown[]) => log('warn', ...details),
    error: (...details: unknown[]) => log('error', ...details),
};
