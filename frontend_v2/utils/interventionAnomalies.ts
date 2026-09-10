/**
 * كشف وتصنيف الشذوذات لشريط التدخل (م٦).
 *
 * أربعة أنواع شذوذ لا غير:
 * 1. critical_delay (تأخر حرج)
 * 2. absent_with_work (موظف غائب وعليه عمل)
 * 3. overloaded (حمل زائد موزون بمستهدف السعة)
 * 4. low_score (درجة أداء هابطة)
 *
 * الترتيب: الأسوأ أولاً بحسب وزن الخطورة ثم مقياس الفرز.
 */

export const ANOMALY_CRITICAL_DELAY = 'critical_delay' as const;
export const ANOMALY_ABSENT_WITH_WORK = 'absent_with_work' as const;
export const ANOMALY_OVERLOADED = 'overloaded' as const;
export const ANOMALY_LOW_SCORE = 'low_score' as const;

export type PlatformAnomalyType =
  | typeof ANOMALY_CRITICAL_DELAY
  | typeof ANOMALY_ABSENT_WITH_WORK
  | typeof ANOMALY_OVERLOADED
  | typeof ANOMALY_LOW_SCORE;

export const SUPPORTED_ANOMALY_TYPES: readonly PlatformAnomalyType[] = [
  ANOMALY_CRITICAL_DELAY,
  ANOMALY_ABSENT_WITH_WORK,
  ANOMALY_OVERLOADED,
  ANOMALY_LOW_SCORE,
];

export interface PlatformAnomaly {
  type: PlatformAnomalyType | string;
  anomaly_type?: PlatformAnomalyType | string;
  type_display?: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | string;
  severity_weight: number;
  sort_metric: number;
  employee_id?: number | null;
  employee_name?: string | null;
  tenant_id?: number | null;
  tenant_name?: string | null;
  work_order_id?: number | null;
  work_order_title?: string | null;
  message: string;
  created_at?: string;
}

export interface AnomalyMeta {
  label: string;
  badgeClass: string;
  borderClass: string;
  bgClass: string;
  textClass: string;
}

const ANOMALY_META: Record<PlatformAnomalyType, AnomalyMeta> = {
  [ANOMALY_CRITICAL_DELAY]: {
    label: 'تأخر حرج',
    badgeClass: 'bg-rose-100 text-rose-800 border-rose-200',
    borderClass: 'border-rose-400',
    bgClass: 'bg-rose-50/70',
    textClass: 'text-rose-700',
  },
  [ANOMALY_ABSENT_WITH_WORK]: {
    label: 'غائب وعليه عمل',
    badgeClass: 'bg-amber-100 text-amber-800 border-amber-200',
    borderClass: 'border-amber-400',
    bgClass: 'bg-amber-50/70',
    textClass: 'text-amber-700',
  },
  [ANOMALY_OVERLOADED]: {
    label: 'حمل زائد',
    badgeClass: 'bg-orange-100 text-orange-800 border-orange-200',
    borderClass: 'border-orange-400',
    bgClass: 'bg-orange-50/70',
    textClass: 'text-orange-700',
  },
  [ANOMALY_LOW_SCORE]: {
    label: 'درجة هابطة',
    badgeClass: 'bg-purple-100 text-purple-800 border-purple-200',
    borderClass: 'border-purple-400',
    bgClass: 'bg-purple-50/70',
    textClass: 'text-purple-700',
  },
};

export function isSupportedAnomalyType(type: string): type is PlatformAnomalyType {
  return SUPPORTED_ANOMALY_TYPES.includes(type as PlatformAnomalyType);
}

export function getAnomalyMeta(type: string): AnomalyMeta {
  const normalized = (type || '').toLowerCase();
  if (isSupportedAnomalyType(normalized)) {
    return ANOMALY_META[normalized];
  }
  return {
    label: 'تنبيه تشغيلي',
    badgeClass: 'bg-slate-100 text-slate-700 border-slate-200',
    borderClass: 'border-slate-300',
    bgClass: 'bg-slate-50',
    textClass: 'text-slate-600',
  };
}

export function getAnomalyNormalizedType(anomaly: PlatformAnomaly): string {
  return (anomaly.type || anomaly.anomaly_type || '').toLowerCase();
}

/**
 * ترتيب الشذوذات: الأسوأ أولاً.
 * 1. وزن الخطورة تنازلياً (severity_weight).
 * 2. مقياس الفرز تنازلياً (sort_metric: مدة التأخر بالساعات، الفارق عن السعة، مدة الغياب).
 */
export function sortAnomaliesWorstFirst(anomalies: PlatformAnomaly[]): PlatformAnomaly[] {
  return [...anomalies].sort((a, b) => {
    const weightDiff = (b.severity_weight ?? 0) - (a.severity_weight ?? 0);
    if (weightDiff !== 0) {
      return weightDiff;
    }
    return (b.sort_metric ?? 0) - (a.sort_metric ?? 0);
  });
}
