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
  columns: ReportColumnDto[];
  rows: ReportRow[];
  totals: Record<string, string>;
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
