/**
 * THA-132 — تبويبات سياق فاتورة المبيعات: أثر المخزون · حساب العميل · المرفقات.
 *
 * المستند مركز سياق لا نموذج إدخال: من داخله يُرى ماذا فعل بالمخزون وبحساب
 * الطرف. مرجع «الأصيل» يضع «رقم الحركة المخزنية» على وجه الفاتورة ويجعله مدخلاً
 * «للاستعلام عن الحركات» (`docs/aseel_reference/invoices.txt`) — فتبويب المخزون
 * هنا هو ذلك المدخل: حركات **هذه الفاتورة**، لا تاريخ الصنف (ذاك في كرت الصنف).
 *
 * **الكسل شرطٌ لا تحسين**: كل مكوّن هنا يجلب داخل `useEffect` عند تركيبه،
 * و`AseelDocumentShell` لا يركّب إلا محتوى التبويب النشط — ففتح الفاتورة لا
 * يُصدر أياً من هذه النداءات. يحرسه `e2e/sales-invoice-context-tabs.spec.ts`
 * بعدّ النداءات لا بالثقة.
 */
import React, { useCallback, useEffect, useState } from "react";
import { Paperclip, Trash2, FileText } from "lucide-react";
import { LedgerTable, DocRefCell, type LedgerColumn } from "../shared/LedgerTable";
import { FileDropZone } from "../ui/FileDropZone";
import { cloudinaryService } from "../../services/cloudinaryService";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { clientLogger } from "../../services/logger";
import {
  getInvoiceStockMovements,
  getInvoiceCustomerLedger,
  listInvoiceAttachments,
  addInvoiceAttachment,
  deleteInvoiceAttachment,
  type InvoiceStockMovementRow,
  type InvoiceStockMovementsResponse,
  type InvoiceLedgerRow,
  type InvoiceLedgerResponse,
  type InvoiceAttachmentRow,
} from "../../services/salesApi";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** حالة إخفاق موحّدة **بمخرج**: لا شاشة خطأ بلا زر إعادة محاولة. */
const TabError: React.FC<{ message: string; onRetry: () => void }> = ({
  message,
  onRetry,
}) => (
  <div role="alert" className="p-4 text-center">
    <p className="text-sm text-[var(--aseel-danger,#c00)]">{message}</p>
    <button type="button" className="aseel-addrow mt-2" onClick={onRetry}>
      إعادة المحاولة
    </button>
  </div>
);

/** لافتة تشرح **سبب** الفراغ — جدولٌ فارغ بلا تفسير يُقرأ كعطل. */
const Notice: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="mb-2 rounded border border-[var(--aseel-border)] bg-[var(--color-surface-2)] px-3 py-2 text-xs text-[var(--aseel-ink-soft)]">
    {children}
  </div>
);

/* ── 1) أثر الفاتورة على المخزون ───────────────────────────────────────────── */

const stockColumns: LedgerColumn<InvoiceStockMovementRow>[] = [
  { key: "id", header: "رقم الحركة", render: (r) => <span className="font-mono">{r.id}</span> },
  { key: "date", header: "التاريخ", render: (r) => formatDateLocalized(r.date) || "—" },
  { key: "product_name", header: "الصنف", render: (r) => r.product_name },
  { key: "movement_type_label", header: "النوع", render: (r) => r.movement_type_label },
  { key: "warehouse", header: "المستودع", render: (r) => r.warehouse || "—" },
  {
    key: "qty_in", header: "وارد", align: "center",
    render: (r) => (Number(r.qty_in) ? formatQuantity(r.qty_in) : "—"),
  },
  {
    key: "qty_out", header: "صادر", align: "center",
    render: (r) => (Number(r.qty_out) ? formatQuantity(r.qty_out) : "—"),
  },
  {
    key: "quantity_before", header: "الرصيد قبل", align: "center",
    render: (r) => formatQuantity(r.quantity_before),
  },
  {
    key: "running_balance", header: "الرصيد بعد", align: "center",
    render: (r) => <b>{formatQuantity(r.running_balance)}</b>,
  },
  {
    key: "total_cost", header: "التكلفة", align: "center",
    render: (r) => formatMoney(r.total_cost, "—"),
  },
];

export const InvoiceStockTab: React.FC<{ invoiceId: number }> = ({ invoiceId }) => {
  const [data, setData] = useState<InvoiceStockMovementsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    clientLogger.info("invoice.tab_open", { tab: "stock", invoiceId });
    getInvoiceStockMovements(invoiceId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(errText(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [invoiceId]);

  useEffect(() => load(), [load]);

  if (error) return <TabError message={`تعذّر تحميل حركة المخزون: ${error}`} onRetry={load} />;

  // سبب الفراغ يأتي من الخادم لا من تخمين الواجهة.
  const notice = !data || data.count > 0 ? null
    : !data.is_posted
      ? "الفاتورة لم تُرحَّل بعد — لا حركة مخزون حتى ترحيلها."
      : !data.stock_on_post
        ? `الترحيل لا يخصم المخزون في هذه الفاتورة — تُخصم البضاعة عند التسليم (الحالة: ${data.delivery_status_display || "غير مسلَّمة"}).`
        : "لا حركة مخزون — قد تكون كل البنود خدمات.";

  return (
    <div className="p-2">
      {notice && <Notice>{notice}</Notice>}
      <LedgerTable<InvoiceStockMovementRow>
        columns={stockColumns}
        rows={data?.results || []}
        loading={loading}
        emptyText="لا توجد حركات مخزون لهذه الفاتورة."
        summaryRow={
          data && data.count > 0 ? (
            <span>
              {formatQuantity(data.count)} حركة · إجمالي التكلفة{" "}
              <b>{formatMoney(data.total_cost)}</b>
            </span>
          ) : undefined
        }
      />
    </div>
  );
};

/* ── 2) حساب العميل: الرصيد قبل الفاتورة وبعدها ────────────────────────────── */

const ledgerColumns: LedgerColumn<InvoiceLedgerRow>[] = [
  { key: "date", header: "التاريخ", render: (r) => formatDateLocalized(r.date) || "—" },
  {
    key: "reference", header: "المستند",
    render: (r) => (
      <DocRefCell
        referenceType={r.reference_type}
        referenceId={r.reference_id}
        label={r.description || `#${r.reference_id ?? "—"}`}
      />
    ),
  },
  { key: "debit", header: "مدين", align: "center", render: (r) => formatMoney(r.debit, "—") },
  { key: "credit", header: "دائن", align: "center", render: (r) => formatMoney(r.credit, "—") },
  {
    key: "balance_before", header: "الرصيد قبل", align: "center",
    render: (r) => formatMoney(r.balance_before),
  },
  {
    key: "running_balance", header: "الرصيد بعد", align: "center",
    render: (r) => <b>{formatMoney(r.running_balance)}</b>,
  },
];

export const InvoiceCustomerLedgerTab: React.FC<{ invoiceId: number }> = ({ invoiceId }) => {
  const [data, setData] = useState<InvoiceLedgerResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    clientLogger.info("invoice.tab_open", { tab: "customer_ledger", invoiceId });
    getInvoiceCustomerLedger(invoiceId)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(errText(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [invoiceId]);

  useEffect(() => load(), [load]);

  if (error) return <TabError message={`تعذّر تحميل حركة الحساب: ${error}`} onRetry={load} />;

  const anchor = data?.anchor ?? null;

  return (
    <div className="p-2">
      {anchor ? (
        // «ماذا فعلت هذه الفاتورة بالحساب؟» — من كشف الحساب نفسه، لا من حسابٍ
        // موازٍ في الواجهة. الأثر هو كامل قيد الذمم لا «المتبقّي» منه.
        <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
          <div className="rounded border border-[var(--aseel-border)] p-2">
            <div className="text-xs text-[var(--aseel-ink-soft)]">الرصيد قبل الفاتورة</div>
            <div className="text-base font-bold" dir="ltr">{formatMoney(anchor.balance_before)}</div>
          </div>
          <div className="rounded border border-[var(--aseel-border)] p-2">
            <div className="text-xs text-[var(--aseel-ink-soft)]">أثر الفاتورة</div>
            <div className="text-base font-bold" dir="ltr">{formatMoney(anchor.effect)}</div>
          </div>
          <div className="rounded border border-[var(--aseel-border)] p-2">
            <div className="text-xs text-[var(--aseel-ink-soft)]">الرصيد بعدها</div>
            <div className="text-base font-bold" dir="ltr">{formatMoney(anchor.balance_after)}</div>
          </div>
        </div>
      ) : !loading && (
        <Notice>
          {data?.reason === "no_customer"
            ? "لا عميل على هذه الفاتورة، فلا حركة حساب."
            : "الفاتورة لم تُرحَّل بعد — لم تمسّ حساب العميل، والرصيد أدناه هو رصيده الحالي."}
        </Notice>
      )}
      <LedgerTable<InvoiceLedgerRow>
        columns={ledgerColumns}
        rows={data?.results || []}
        loading={loading}
        emptyText="لا توجد حركات على حساب هذا العميل."
        // سطر الفاتورة نفسها مميَّز داخل كشفها — وإلا ضاع بين جيرانه.
        rowClassName={(r) =>
          r.is_anchor ? "bg-amber-50 font-bold dark:bg-amber-900/20" : ""
        }
        summaryRow={
          data ? (
            <span>
              الرصيد الختامي للحساب <b dir="ltr">{formatMoney(data.closing_balance)}</b>
              {data.customer_name ? ` — ${data.customer_name}` : ""}
            </span>
          ) : undefined
        }
      />
    </div>
  );
};

/* ── 3) المرفقات ───────────────────────────────────────────────────────────── */

export const InvoiceAttachmentsTab: React.FC<{
  invoiceId: number;
  readOnly?: boolean;
}> = ({ invoiceId, readOnly }) => {
  const [rows, setRows] = useState<InvoiceAttachmentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const confirm = useConfirm();

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    clientLogger.info("invoice.tab_open", { tab: "attachments", invoiceId });
    listInvoiceAttachments(invoiceId)
      .then((d) => { if (!cancelled) setRows(Array.isArray(d) ? d : []); })
      .catch((e) => { if (!cancelled) setError(errText(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [invoiceId]);

  useEffect(() => load(), [load]);

  // الرفع فوري لا مؤجَّل: الفاتورة المرحّلة لا تُعدَّل، فربط المرفق بحفظها كان
  // يعني ألّا يُرفق إيصالٌ بعد الترحيل أبداً.
  const upload = useCallback(async (files: File[]) => {
    setBusy(true);
    try {
      for (const file of files) {
        const url = await cloudinaryService.uploadFile(file);
        const created = await addInvoiceAttachment(invoiceId, url);
        setRows((prev) => [...prev, created]);
      }
      toast("تم إرفاق الملف.", "success");
    } catch (e) {
      toast(`تعذّر رفع المرفق: ${errText(e)}`, "error");
    } finally {
      setBusy(false);
    }
  }, [invoiceId, toast]);

  const remove = useCallback(async (row: InvoiceAttachmentRow) => {
    if (!(await confirm({ message: `حذف المرفق «${row.filename}»؟` }))) return;
    try {
      await deleteInvoiceAttachment(invoiceId, row.id);
      setRows((prev) => prev.filter((r) => r.id !== row.id));
    } catch (e) {
      toast(`تعذّر حذف المرفق: ${errText(e)}`, "error");
    }
  }, [invoiceId, confirm, toast]);

  if (error) return <TabError message={`تعذّر تحميل المرفقات: ${error}`} onRetry={load} />;

  return (
    <div className="p-2">
      {!readOnly && (
        <FileDropZone
          onFiles={(files) => { void upload(files); }}
          accept="image-pdf"
          multiple
          busy={busy}
          variant="compact"
          hint="اضغط للاختيار، اسحب الملف إلى هنا، أو الصق صورة (Ctrl+V)"
          subHint="صور وملفات PDF — تُحفظ فوراً ولو كانت الفاتورة مرحّلة"
        />
      )}
      {loading ? (
        <div className="p-4 text-center text-[var(--aseel-ink-soft)]">جارٍ التحميل…</div>
      ) : rows.length === 0 ? (
        <div className="p-4 text-center text-[var(--aseel-ink-soft)]">
          لا مرفقات على هذه الفاتورة بعد.
        </div>
      ) : (
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
          {rows.map((row) => (
            <div
              key={row.id}
              className="group relative overflow-hidden rounded-lg border border-[var(--aseel-border)] bg-[var(--color-surface-2)]"
            >
              <a
                href={row.url}
                target="_blank"
                rel="noopener noreferrer"
                title={row.filename}
                className="flex aspect-square items-center justify-center"
              >
                {row.file_type === "PDF" ? (
                  <FileText className="h-8 w-8 text-red-600" />
                ) : (
                  <img src={row.url} alt={row.filename} className="h-full w-full object-cover" />
                )}
              </a>
              <div className="truncate px-1 py-0.5 text-[10px] text-[var(--aseel-ink-soft)]">
                {row.filename}
              </div>
              {!readOnly && (
                <button
                  type="button"
                  title="حذف المرفق"
                  onClick={() => { void remove(row); }}
                  className="absolute top-1 start-1 rounded-md bg-black/60 p-1 text-white opacity-0 transition-opacity hover:bg-[var(--color-danger)] group-hover:opacity-100"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export const InvoiceAttachmentsTabIcon = Paperclip;
