/**
 * عرض مستندي احترافي للقراءة فقط — يخدم كل المستندات (مبيعات، شراء، دولية، صفقات).
 *
 * شكوى المالك: «بدي أفتح الفاتورة أو الصفقة ألاقي واجهة احترافية مخصصة للعرض،
 * مش تكست فاضي». وضع العرض السابق كان **نفس نموذج التحرير بحقول معطّلة**، فيبدو
 * صفوفاً من المربّعات الرمادية لا مستنداً.
 *
 * البنية تتبع المتعارف عليه في منتجات الفوترة الاحترافية:
 *   ترويسة (هوية + نوع المستند + رقمه + شارة الحالة)
 *   → شريط مؤشرات (الإجمالي / المدفوع / المتبقي …)
 *   → كتل الأطراف (من / إلى) + بيانات وصفية
 *   → جدول البنود
 *   → كتلة المجاميع (الإجمالي بارز)
 *   → أقسام إضافية (دفعات، ملاحظات، مرفقات)
 *
 * مكوّن **عرض بحت**: لا يجلب بيانات ولا يعدّلها. كل مستند يمرّر واصفه، فلا
 * يتكرر بناء الواجهة أربع مرات وتتباعد الشاشات (DRY).
 */
import React from "react";
import { FileText } from "lucide-react";
import { useTenantSettings } from "../../hooks/useTenantSettings";

export type AseelViewTone = "ok" | "warn" | "danger" | "info" | "muted";

export interface AseelViewStatus {
  label: string;
  tone?: AseelViewTone;
}

export interface AseelViewMetric {
  label: string;
  value: React.ReactNode;
  tone?: AseelViewTone;
}

export interface AseelViewField {
  label: string;
  value: React.ReactNode;
  /** يمتد على عرض الكتلة (عناوين، ملاحظات طويلة) */
  wide?: boolean;
}

export interface AseelViewParty {
  title: string;
  icon?: React.ReactNode;
  fields: AseelViewField[];
}

export interface AseelViewColumn<T> {
  key: string;
  header: string;
  align?: "right" | "center" | "left";
  width?: string;
  /** أرقام: خط ثابت واتجاه LTR كي لا تنقلب الإشارة بصرياً في RTL */
  numeric?: boolean;
  render: (row: T, index: number) => React.ReactNode;
}

export interface AseelViewTotal {
  label: string;
  value: React.ReactNode;
  /** السطر الرئيسي (الإجمالي) — أكبر وأبرز */
  emphasis?: boolean;
  tone?: AseelViewTone;
}

export interface AseelViewSection {
  key: string;
  title: string;
  content: React.ReactNode;
}

export interface AseelDocumentViewProps<T> {
  /** «فاتورة مبيعات» */
  title: string;
  /** «SALES INVOICE» — سطر لاتيني صغير تحت العنوان */
  subtitle?: string;
  documentNumber?: string;
  status?: AseelViewStatus;
  metrics?: AseelViewMetric[];
  parties?: AseelViewParty[];
  meta?: AseelViewField[];
  columns: AseelViewColumn<T>[];
  rows: T[];
  rowKey?: (row: T, index: number) => React.Key;
  totals?: AseelViewTotal[];
  sections?: AseelViewSection[];
  emptyRowsHint?: string;
  /** يُعرض أسفل المستند (شروط، توقيع) */
  footer?: React.ReactNode;
}

const TONE_CLASS: Record<AseelViewTone, string> = {
  ok: "bg-emerald-100 text-emerald-800 border-emerald-200",
  warn: "bg-amber-100 text-amber-800 border-amber-200",
  danger: "bg-rose-100 text-rose-800 border-rose-200",
  info: "bg-sky-100 text-sky-800 border-sky-200",
  muted: "bg-[var(--color-surface-3)] text-[var(--color-text)] border-[var(--color-border)]",
};

const METRIC_VALUE_TONE: Record<AseelViewTone, string> = {
  ok: "text-emerald-700",
  warn: "text-amber-700",
  danger: "text-rose-700",
  info: "text-sky-700",
  muted: "text-[var(--color-text)]",
};

function FieldRow({ field }: { field: AseelViewField; key?: React.Key }) {
  return (
    <div
      className={
        field.wide
          ? "flex flex-col gap-0.5"
          : "flex items-baseline justify-between gap-3"
      }
    >
      <span className="text-[11px] text-[var(--color-text-muted)] shrink-0">{field.label}</span>
      <span className="text-[12px] font-semibold text-[var(--color-text)] text-left break-words">
        {field.value ?? "—"}
      </span>
    </div>
  );
}

/**
 * جدول بنود بنفس تنسيق المستند — مُصدَّر كي تستعمله الأقسام الإضافية
 * (دفعات الصفقة، أقساطها …) فلا يتكرر التنسيق ولا يتباعد (DRY).
 */
export function AseelViewTable<T>({
  columns,
  rows,
  rowKey,
  emptyHint = "لا توجد بنود",
  showIndex = true,
}: {
  columns: AseelViewColumn<T>[];
  rows: T[];
  rowKey?: (row: T, index: number) => React.Key;
  emptyHint?: string;
  showIndex?: boolean;
}) {
  const alignClass = (align?: AseelViewColumn<T>["align"]) =>
    align === "center" ? "text-center" : align === "left" ? "text-left" : "text-right";

  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm">
      <table className="w-full border-collapse text-right">
        <thead>
          <tr className="bg-slate-800 text-[11px] font-bold text-white">
            {showIndex && <th className="w-10 px-2 py-2 text-center">#</th>}
            {columns.map((c) => (
              <th
                key={c.key}
                style={c.width ? { width: c.width } : undefined}
                className={`px-3 py-2 ${alignClass(c.align)}`}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="text-[12px]">
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length + (showIndex ? 1 : 0)}
                className="px-3 py-6 text-center text-slate-400"
              >
                {emptyHint}
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr
                key={rowKey ? rowKey(row, index) : index}
                className="border-b border-slate-100 last:border-0 hover:bg-[var(--color-surface-2)] dark:border-slate-700"
              >
                {showIndex && (
                  <td className="px-2 py-2 text-center text-slate-400">{index + 1}</td>
                )}
                {columns.map((c) => (
                  <td
                    key={c.key}
                    dir={c.numeric ? "ltr" : undefined}
                    className={`px-3 py-2 ${c.numeric ? "font-mono" : ""} ${alignClass(c.align)}`}
                  >
                    {c.render(row, index)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function AseelDocumentView<T>({
  title,
  subtitle,
  documentNumber,
  status,
  metrics,
  parties,
  meta,
  columns,
  rows,
  rowKey,
  totals,
  sections,
  emptyRowsHint = "لا توجد بنود",
  footer,
}: AseelDocumentViewProps<T>) {
  const { identity } = useTenantSettings();

  return (
    <div dir="rtl" className="aseel-doc-view flex flex-col gap-3 p-3 overflow-auto">
      {/* ── الترويسة ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          {identity?.logo_url ? (
            <img
              src={identity.logo_url}
              alt="شعار الشركة"
              className="h-12 w-12 rounded-xl border border-[var(--color-border)] object-cover"
            />
          ) : (
            <div className="rounded-xl bg-slate-800 p-2.5 text-white">
              <FileText size={22} />
            </div>
          )}
          <div>
            {identity?.company_name_primary && (
              <div className="text-sm font-black leading-tight text-[var(--color-text)]">
                {identity.company_name_primary}
              </div>
            )}
            <h2 className="text-lg font-black leading-tight text-[var(--color-text)]">
              {title}
            </h2>
            {subtitle && (
              <p className="text-[10px] font-bold tracking-wide text-slate-400">{subtitle}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          {documentNumber && (
            <div className="text-left">
              <span className="block text-[11px] text-[var(--color-text-muted)]">رقم المستند</span>
              <span className="font-mono text-base font-bold text-[var(--color-text)]" dir="ltr">
                {documentNumber}
              </span>
            </div>
          )}
          {status && (
            <span
              className={`rounded-full border px-3 py-1 text-xs font-bold ${
                TONE_CLASS[status.tone || "muted"]
              }`}
            >
              {status.label}
            </span>
          )}
        </div>
      </div>

      {/* ── شريط المؤشرات ────────────────────────────────────────── */}
      {metrics && metrics.length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {metrics.map((m, i) => (
            <div
              key={`${m.label}-${i}`}
              className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 shadow-sm"
            >
              <span className="block text-[11px] text-[var(--color-text-muted)]">{m.label}</span>
              <span
                className={`block text-base font-bold ${
                  METRIC_VALUE_TONE[m.tone || "muted"]
                } dark:text-slate-100`}
              >
                {m.value}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* ── الأطراف + البيانات الوصفية ───────────────────────────── */}
      {((parties && parties.length > 0) || (meta && meta.length > 0)) && (
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
          {parties?.map((p) => (
            <div
              key={p.title}
              className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm"
            >
              <div className="flex items-center gap-1.5 border-b border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-xs font-bold text-[var(--color-text)]">
                {p.icon}
                {p.title}
              </div>
              <div className="space-y-1.5 p-3">
                {p.fields.map((f, i) => (
                  <FieldRow key={`${f.label}-${i}`} field={f} />
                ))}
              </div>
            </div>
          ))}
          {meta && meta.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm">
              <div className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-xs font-bold text-[var(--color-text)]">
                بيانات المستند
              </div>
              <div className="space-y-1.5 p-3">
                {meta.map((f, i) => (
                  <FieldRow key={`${f.label}-${i}`} field={f} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── جدول البنود ──────────────────────────────────────────── */}
      <AseelViewTable
        columns={columns}
        rows={rows}
        rowKey={rowKey}
        emptyHint={emptyRowsHint}
      />

      {/* ── المجاميع ─────────────────────────────────────────────── */}
      {totals && totals.length > 0 && (
        <div className="flex justify-start">
          <div className="w-full max-w-sm overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm">
            {totals.map((t, i) => (
              <div
                key={`${t.label}-${i}`}
                className={`flex items-baseline justify-between gap-4 px-4 py-2 ${
                  t.emphasis
                    ? "border-t-2 border-slate-800 bg-[var(--color-surface-2)]"
                    : "border-b border-slate-100 last:border-0 dark:border-slate-700"
                }`}
              >
                <span
                  className={
                    t.emphasis
                      ? "text-sm font-black text-[var(--color-text)]"
                      : "text-[12px] text-[var(--color-text-muted)]"
                  }
                >
                  {t.label}
                </span>
                <span
                  dir="ltr"
                  className={`font-mono ${
                    t.emphasis
                      ? "text-lg font-black text-[var(--color-text)]"
                      : `text-[13px] font-semibold ${METRIC_VALUE_TONE[t.tone || "muted"]}`
                  }`}
                >
                  {t.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── أقسام إضافية (دفعات، ملاحظات، مرفقات) ────────────────── */}
      {sections?.map((s) => (
        <div
          key={s.key}
          className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm"
        >
          <div className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-xs font-bold text-[var(--color-text)]">
            {s.title}
          </div>
          <div className="p-3 text-[12px]">{s.content}</div>
        </div>
      ))}

      {footer && <div className="text-[11px] text-[var(--color-text-muted)]">{footer}</div>}
    </div>
  );
}
