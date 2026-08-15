/**
 * مُنسّق حجم الملفات بالعربية — مصدر واحد لكل شاشة تعرض حجم مرفق.
 * وحدة واحدة تلقائياً حسب الحجم (بايت/ك.ب/م.ب/ج.ب)، والكسر عبر `formatNumber`
 * فيسقط العشري غير الدالّ («1.0 م.ب» تصير «1 م.ب»).
 */
// الامتداد صريح: هذا الملف مُختبَر بـ`node --test` الذي لا يحلّ الاستيراد بلا امتداد.
import { formatNumber } from './formatNumber.ts';

const KB = 1024;
const MB = 1024 ** 2;
const GB = 1024 ** 3;

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || bytes <= 0) {
    return '—';
  }
  if (bytes < KB) {
    return `${formatNumber(bytes, { maxDecimals: 0 })} بايت`;
  }
  if (bytes < MB) {
    return `${formatNumber(bytes / KB, { maxDecimals: 1 })} ك.ب`;
  }
  if (bytes < GB) {
    return `${formatNumber(bytes / MB, { maxDecimals: 1 })} م.ب`;
  }
  return `${formatNumber(bytes / GB, { maxDecimals: 1 })} ج.ب`;
}
