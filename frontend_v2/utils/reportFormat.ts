/**
 * T-REPORTS: عرض خلايا التقارير وتصديرها — منطق نقيّ مشترك بين شاشة التقرير
 * وتصدير CSV والطباعة، فلا يختلف ما يُطبع عمّا يُرى.
 * نوع العمود يأتي من الخادم (`kind`) ولا تُخمّنه الواجهة.
 */
// الامتداد صريح: هذا الملف مُختبَر بـ`node --test` الذي لا يحلّ الاستيراد بلا امتداد.
import { formatNumber } from './formatNumber.ts';
import { formatDateLocalized } from './formatDate.ts';

export type ReportColumnKind = 'text' | 'money' | 'number' | 'int' | 'date';

export interface ReportColumnDto {
  key: string;
  header: string;
  kind: ReportColumnKind;
  total?: boolean;
  width?: string | null;
}

export interface ReportFilterOption {
  value: string;
  label: string;
}

export interface ReportFilterDto {
  key: string;
  label: string;
  /** date | customer | supplier | partner | product | warehouse | account | cash_account | select | text */
  kind: string;
  options?: ReportFilterOption[];
  default?: string | null;
}

export interface ReportSummaryDto {
  key: string;
  title: string;
  description: string;
  permission: string | null;
  screen_path: string | null;
  /** مسار المستند خلف السطر بقوالب من مفاتيح الصف — «/sales/invoices/{id}». */
  row_link?: string | null;
  filters: ReportFilterDto[];
  columns: ReportColumnDto[];
}

export interface ReportCategoryDto {
  key: string;
  label: string;
  reports: ReportSummaryDto[];
}

export type ReportRow = Record<string, unknown>;

export interface ReportResultDto {
  key: string;
  title: string;
  category: string;
  description: string;
  row_link?: string | null;
  columns: ReportColumnDto[];
  rows: ReportRow[];
  totals: Record<string, string>;
  /** عدد الصفوف قبل القصّ — الإجماليات محسوبة عليه كاملاً لا على المعروض. */
  total_rows?: number;
  truncated?: boolean;
  generated_at: string;
}

/** الأعمدة الرقمية تُحاذى وتُعرض بخط جدولي — قرار واحد لا شرط في كل شاشة. */
export const isNumericKind = (kind: ReportColumnKind): boolean =>
  kind === 'money' || kind === 'number' || kind === 'int';

/**
 * نص الخلية كما يُعرض ويُصدَّر. المال والأرقام عبر `formatNumber` (قاعدة G1 —
 * لا أصفار زائدة)، والتواريخ بالشكل المحلي، والفراغ شرطة لا سلسلة خالية.
 */
export const formatReportCell = (value: unknown, kind: ReportColumnKind): string => {
  if (value === null || value === undefined || value === '') return '—';
  switch (kind) {
    case 'money':
      // فاصل الآلاف في المال وحده — التقارير تُقرأ بالعين لا بالحاسبة.
      return formatNumber(value, { maxDecimals: 2, group: true });
    case 'number':
      return formatNumber(value, { maxDecimals: 3 });
    case 'int':
      return formatNumber(value, { maxDecimals: 0 });
    case 'date':
      return formatDateLocalized(String(value)) || String(value);
    default:
      return String(value);
  }
};

/** فلاتر غير الفارغة فقط — كي لا يمتلئ الرابط بمفاتيح بلا قيم. */
export const reportQuery = (values: Record<string, string>): Record<string, string> => {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(values)) {
    const trimmed = (value ?? '').trim();
    if (trimmed) out[key] = trimmed;
  }
  return out;
};

/** القيم الابتدائية للفلاتر: افتراضي الخادم، وإلا فارغ. */
export const initialFilterValues = (
  filters: ReportFilterDto[],
  seed: Record<string, string> = {},
): Record<string, string> => {
  const out: Record<string, string> = {};
  for (const filter of filters) {
    out[filter.key] = seed[filter.key] ?? filter.default ?? '';
  }
  return out;
};

/**
 * نطاقات الفترة الجاهزة — «هذا الشهر» بضغطة بدل كتابة تاريخين، كما في دفترة
 * وزوهو. التاريخ يُبنى من أجزاء محليّة صريحة لا عبر `toLocale*`/`toISOString`:
 * الأولى تُعطي هجرياً أو أرقاماً هنديّة حسب جهاز المستخدم، والثانية تُزيح اليوم
 * بفارق المنطقة الزمنية فتُسقط حركات آخر يوم من الفترة.
 */
export type DatePresetKey =
  | 'today' | 'week' | 'month' | 'quarter' | 'year' | 'prev-month' | 'prev-year' | 'all';

export const DATE_PRESETS: { key: DatePresetKey; label: string }[] = [
  { key: 'today', label: 'اليوم' },
  { key: 'week', label: 'هذا الأسبوع' },
  { key: 'month', label: 'هذا الشهر' },
  { key: 'quarter', label: 'هذا الربع' },
  { key: 'year', label: 'هذه السنة' },
  { key: 'prev-month', label: 'الشهر الماضي' },
  { key: 'prev-year', label: 'السنة الماضية' },
  { key: 'all', label: 'كل الفترات' },
];

const isoLocal = (date: Date): string => {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
};

/** `{from, to}` للنطاق المختار. «كل الفترات» يُفرِغ الحقلين لا يملؤهما بحدّ وهمي. */
export const datePresetRange = (
  preset: DatePresetKey,
  today: Date = new Date(),
): { from: string; to: string } => {
  const year = today.getFullYear();
  const month = today.getMonth();
  const at = (y: number, m: number, d: number) => isoLocal(new Date(y, m, d));
  switch (preset) {
    case 'today':
      return { from: isoLocal(today), to: isoLocal(today) };
    case 'week': {
      // الأسبوع يبدأ السبت في التقويم العربي — لا الأحد ولا الإثنين.
      const start = new Date(today);
      start.setDate(today.getDate() - ((today.getDay() + 1) % 7));
      return { from: isoLocal(start), to: isoLocal(today) };
    }
    case 'month':
      return { from: at(year, month, 1), to: at(year, month + 1, 0) };
    case 'quarter': {
      const first = Math.floor(month / 3) * 3;
      return { from: at(year, first, 1), to: at(year, first + 3, 0) };
    }
    case 'year':
      return { from: at(year, 0, 1), to: at(year, 11, 31) };
    case 'prev-month':
      return { from: at(year, month - 1, 1), to: at(year, month, 0) };
    case 'prev-year':
      return { from: at(year - 1, 0, 1), to: at(year - 1, 11, 31) };
    case 'all':
    default:
      return { from: '', to: '' };
  }
};

/** مسار المستند خلف صفٍّ بعينه، أو null إن نقص أحد مفاتيح القالب. */
export const resolveRowLink = (
  template: string | null | undefined,
  row: ReportRow,
): string | null => {
  if (!template) return null;
  let missing = false;
  const path = template.replace(/\{(\w+)\}/g, (_match, key: string) => {
    const value = row[key];
    if (value === null || value === undefined || value === '') {
      missing = true;
      return '';
    }
    return encodeURIComponent(String(value));
  });
  return missing ? null : path;
};

const csvCell = (value: string) => `"${value.replace(/"/g, '""')}"`;

/**
 * CSV بترميز UTF-8 مع BOM — بلا BOM يفتح Excel العربية مشوّهة.
 * يشمل سطر الإجماليات كي يطابق المطبوع.
 */
export const reportToCsv = (result: ReportResultDto): string => {
  const lines = [result.columns.map((c) => csvCell(c.header)).join(',')];
  for (const row of result.rows) {
    lines.push(
      result.columns
        .map((c) => csvCell(formatReportCell(row[c.key], c.kind)))
        .join(','),
    );
  }
  const hasTotals = Object.keys(result.totals || {}).length > 0;
  if (hasTotals) {
    lines.push(
      result.columns
        .map((c, i) => {
          if (result.totals[c.key] !== undefined) {
            return csvCell(formatReportCell(result.totals[c.key], c.kind));
          }
          return csvCell(i === 0 ? 'الإجمالي' : '');
        })
        .join(','),
    );
  }
  return `﻿${lines.join('\n')}`;
};

/** اسم ملف التصدير: عنوان التقرير + تاريخ التوليد، بلا محارف تكسر النظام. */
export const reportFileName = (result: ReportResultDto, extension = 'csv'): string => {
  const date = (result.generated_at || '').slice(0, 10) || 'report';
  const safeTitle = result.title.replace(/[\\/:*?"<>|]/g, '-').trim();
  return `${safeTitle} — ${date}.${extension}`;
};
