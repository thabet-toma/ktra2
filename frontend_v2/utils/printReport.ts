/**
 * طباعة/تصدير PDF لتقرير جدولي — مصدر واحد لكل الشاشات.
 *
 * يفتح نافذة طباعة بنمط تقارير الموقع (RTL، ترويسة، جدول مخطّط) ويستدعي
 * `window.print()`؛ ومن حوار الطباعة يختار المستخدم «حفظ كـ PDF». استُخرج من
 * تصدير المنتجات كي لا يتكرّر قالب الـHTML في كل شاشة.
 */

export type PrintColumn<T> = {
  header: string;
  /** قيمة الخلية — تُهرَّب تلقائياً. */
  value: (row: T) => string | number | null | undefined;
  /** أرقام: محاذاة يسار وخط أحادي. */
  numeric?: boolean;
};

export type PrintReportOptions<T> = {
  title: string;
  subtitle?: string;
  columns: PrintColumn<T>[];
  rows: T[];
  /** سطور معلومات فوق الجدول (رقم المستند، الطرف، الملاحظات…). */
  meta?: { label: string; value: string }[];
  /** سطر الإجمالي أسفل الجدول — بترتيب `columns` نفسه. فراغ في خلية بلا مجموع. */
  totals?: (string | number | null | undefined)[];
  /** نص ذيل اختياري (توقيع المستلم مثلاً). */
  footer?: string;
  /** رسالة عند غياب الصفوف. */
  emptyHint?: string;
  /** ورقة عرضية — جدولٌ عريض (كشف الساعات: عمود لكل يوم) لا يسع الطولية. */
  landscape?: boolean;
};

const esc = (v: unknown) =>
  String(v ?? "—")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

/**
 * يفتح نافذة الطباعة. يُعيد false إن منع المتصفح النوافذ المنبثقة، فتعرض
 * الشاشة رسالة بدل الصمت.
 */
export function printReport<T>(options: PrintReportOptions<T>): boolean {
  const {
    title, subtitle, columns, rows, meta = [], totals, footer, emptyHint,
    landscape = columns.length > 10,
  } = options;
  const win = window.open("", "_blank");
  if (!win) return false;

  const today = new Date().toISOString().slice(0, 10);
  const head = columns.map((c) => `<th>${esc(c.header)}</th>`).join("");
  const body = rows.length
    ? rows
        .map(
          (row) =>
            `<tr>${columns
              .map(
                (c) =>
                  `<td class="${c.numeric ? "num" : ""}"${
                    c.numeric ? ' style="direction: ltr"' : ""
                  }>${esc(c.value(row))}</td>`
              )
              .join("")}</tr>`
        )
        .join("")
    : `<tr><td colspan="${columns.length}" class="empty">${esc(
        emptyHint || "لا توجد بيانات"
      )}</td></tr>`;

  const totalsHtml = totals?.length
    ? `<tfoot><tr class="totals">${columns
        .map(
          (c, i) =>
            // خليّة بلا مجموع تبقى فارغة — لا شرطة توحي بقيمة مفقودة.
            `<td class="${c.numeric ? "num" : ""}"${
              c.numeric ? ' style="direction: ltr"' : ""
            }>${esc(totals[i] ?? "")}</td>`
        )
        .join("")}</tr></tfoot>`
    : "";

  const metaHtml = meta.length
    ? `<div class="meta">${meta
        .map((m) => `<span><b>${esc(m.label)}:</b> ${esc(m.value)}</span>`)
        .join("")}</div>`
    : "";

  win.document.open();
  win.document.write(`
    <html dir="rtl" lang="ar">
      <head>
        <title>${esc(title)} - ${today}</title>
        <style>
          body { font-family: system-ui, -apple-system, sans-serif; padding: 20px; color: #111827; }
          h2 { text-align: center; color: #1857a4; margin-bottom: 5px; }
          .subtitle { text-align: center; color: #6b7280; margin-bottom: 16px; font-size: 14px; }
          .meta { display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px;
                  color: #374151; margin-bottom: 12px; border: 1px solid #e5e7eb;
                  padding: 10px 12px; border-radius: 6px; background: #f9fafb; }
          table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }
          th, td { border: 1px solid #e5e7eb; padding: 10px 12px; text-align: right; }
          th { background-color: #f9fafb; color: #374151; font-weight: 600; }
          tr:nth-child(even) { background-color: #fcfcfd; }
          .num { text-align: left; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
          tfoot .totals td { background-color: #f3f4f6; font-weight: 700; border-top: 2px solid #d1d5db; }
          .empty { text-align: center; color: #6b7280; }
          .footer { margin-top: 28px; font-size: 13px; color: #374151; }
          @media print {
            body { padding: 0; }
            @page { margin: 1.5cm; size: ${landscape ? "landscape" : "auto"}; }
            /* الرأس يتكرّر في كل صفحة: بدونه تُقرأ الصفحة الثانية من كشفٍ
               طويل بلا عناوين أعمدة — أرقامٌ لا يُعرف ماذا تعني. الافتراضي
               في المتصفحات هذا السلوك، لكنه غير مضمون فيُصرَّح به. */
            thead { display: table-header-group; }
            tfoot { display: table-footer-group; }
            tr, td, th { break-inside: avoid; page-break-inside: avoid; }
          }
        </style>
      </head>
      <body>
        <h2>${esc(title)}</h2>
        <div class="subtitle">${esc(subtitle || "")}${
          subtitle ? " · " : ""
        }عدد السطور: ${rows.length} · التاريخ: ${today}</div>
        ${metaHtml}
        <table><thead><tr>${head}</tr></thead><tbody>${body}</tbody>${totalsHtml}</table>
        ${footer ? `<div class="footer">${esc(footer)}</div>` : ""}
        <script>window.onload = () => { window.print(); };</script>
      </body>
    </html>`);
  win.document.close();
  return true;
}
