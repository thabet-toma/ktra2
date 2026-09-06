/**
 * مواصفة #147 (المرحلة 5أ) — «عروض عامة»: ردودُ موردين **مجهولين** كتبوا
 * اسمهم على رابطٍ عامٍّ لطلبيةٍ، دون أن يدخلوا قاعدة بياناتك. جدولٌ ثانٍ داخل
 * تبويب «العروض والأوامر» — **ليس تبويباً ثالثاً ولا قسماً قابلاً للطيّ**
 * (خريطة #138، القرار 5 والتذكرة #145): ردٌّ جديد لا يجوز أن يختبئ خلف نقرة
 * أحدٌ لا يعرف أنّ خلفها جديداً.
 *
 * الاعتمادُ لا يقع من صفّ الجدول أبداً — فتحُ الردّ (كلّ سطر بسعره) هو ما
 * يسبق زرَّي «اعتماد»/«رفض» (البند 6، قرار المالك الصريح: لا توقيعَ على
 * شيكٍ على بياض).
 */
import React, { useEffect, useMemo, useState } from "react";
import { Inbox, X, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import {
  approvePublicSupplierQuoteRequest,
  getPublicSupplierQuoteRequestMatches,
  listPublicSupplierQuoteRequests,
  rejectPublicSupplierQuoteRequest,
  type PublicQuoteRequestMatchDto,
  type PublicSupplierQuoteRequestDto,
  type PurchaseRFQDto,
} from "../../../services/procurementDocumentsApi";
import { KitDenseTable, type DenseColumn } from "../../kit";
import { formatMoney } from "../../../utils/formatNumber";
import { formatDateTimeValue } from "../../../utils/formatDate";
import { useToast } from "../../../contexts/ToastContext";
import { useConfirm } from "../../../contexts/ConfirmContext";

interface Props {
  /** طلبيات النطاق الحالي (محلي/استيراد) — لفلتر الطلبية وحساب إجمالي بنودها. */
  rfqs: PurchaseRFQDto[];
  /** يزداد كلما أعاد الشاشة الأمّ تحميل بياناتها — يُعيد جلب هذا الجدول أيضاً. */
  reloadSignal: number;
  /** اعتمادٌ ناجح يُنشئ عرضاً جديداً — الشاشة الأمّ تُحدِّث عروضها وطلبياتها. */
  onApproved: () => void;
}

const lineTotal = (row: PublicSupplierQuoteRequestDto): number =>
  row.lines.reduce((sum, line) => sum + Number(line.unit_price || 0), 0);

const STATUS_LABELS: Record<string, string> = {
  all: "كل الحالات",
  pending: "بانتظار المراجعة",
  approved: "مقبول",
  rejected: "مرفوض",
};

const ROW_COLOR: Record<string, string | undefined> = {
  pending: undefined,
  approved: "var(--ktra-ok, #267346)",
  rejected: "var(--ktra-ink-soft)",
};

type DisplayRow = PublicSupplierQuoteRequestDto & { _rowColor?: string };

type SortKey = "supplier_name" | "submitted_at" | "total";

export const PublicQuoteRequestsSection: React.FC<Props> = ({ rfqs, reloadSignal, onApproved }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [rows, setRows] = useState<PublicSupplierQuoteRequestDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [rfqFilter, setRfqFilter] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("submitted_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [selected, setSelected] = useState<PublicSupplierQuoteRequestDto | null>(null);
  const [approveOpen, setApproveOpen] = useState(false);
  const [matches, setMatches] = useState<PublicQuoteRequestMatchDto[] | null>(null);
  const [matchesLoading, setMatchesLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const rfqIds = useMemo(() => new Set(rfqs.map((r) => r.id)), [rfqs]);
  const rfqLineCount = useMemo(
    () => new Map(rfqs.map((r) => [r.id, r.lines.length])),
    [rfqs],
  );

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    listPublicSupplierQuoteRequests()
      .then((list) => { if (active) setRows(list); })
      .catch((cause) => {
        if (active) setError(cause instanceof Error ? cause.message : "تعذّر تحميل العروض العامة");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reloadSignal]);

  // نطاقُ الشاشة الأمّ (محلي/استيراد) — ردٌّ على طلبيةٍ من نطاقٍ آخر لا يظهر هنا.
  const scopedRows = useMemo(
    () => rows.filter((row) => rfqIds.has(row.rfq)),
    [rows, rfqIds],
  );
  const pendingCount = useMemo(
    () => scopedRows.filter((row) => row.status === "pending").length,
    [scopedRows],
  );

  /* مواصفة #147، القصّة ٨: «أُنبَّه حين يتجاوز عددُ الردود حدّاً غير معتاد،
   * **دون أن يُغلَق الرابطُ من تلقاء نفسه**». تنبيهٌ لا حاجز — قرارُ المجموعة ج
   * صريح: لا سقفَ رقميّ ولا إغلاقَ آليّ (البحثُ عبر ستّة أنظمة مشابهة لم يجد
   * سقفاً كهذا في أيٍّ منها)، لأن رابطاً يُغلَق فجأةً على مورّدٍ حقيقيّ خسارةٌ
   * مؤكّدة بينما الردُّ العابث لا يمسّ الدفاتر أصلاً. فالعدُّ يُقال للمالك
   * ويقرّر هو. العتبة على **الطلبية الواحدة** لا على الشاشة كلّها: عشرون ردّاً
   * موزّعةً على خمس طلبيات نشاطٌ عاديّ، وعشرون على طلبيةٍ واحدة ليست كذلك. */
  const UNUSUAL_REPLIES_PER_RFQ = 20;
  const floodedRfqs = useMemo(() => {
    const perRfq = new Map<number, { label: string; count: number }>();
    for (const row of scopedRows) {
      const label = row.rfq_number || `#${row.rfq}`;
      const seen = perRfq.get(row.rfq);
      perRfq.set(row.rfq, { label, count: (seen?.count ?? 0) + 1 });
    }
    return [...perRfq.values()].filter((r) => r.count >= UNUSUAL_REPLIES_PER_RFQ);
  }, [scopedRows]);
  const floodHint = floodedRfqs.length > 0 ? (
    <p className="mt-1 text-[11px] text-[var(--ktra-warn-fg,#8a5a00)]">
      عددُ الردود غيرُ معتاد على{" "}
      {floodedRfqs.map((r) => `${r.label} (${r.count})`).join("، ")} — الرابط ما
      زال مفتوحاً ولن يُغلَق تلقائياً؛ أوقفه من شاشة الطلبية إن شئت.
    </p>
  ) : null;

  // مواصفة #147 (خريطة #138، البند 27): رابطٌ عامٌّ حيٌّ بلا أيّ ردٍّ عليه بعد —
  // «كي لا أنساه». `scopedRows` بلا فلتر حالة، فردٌّ مرفوضٌ يُسقط الطلبية من
  // هذه القائمة أيضاً (وصل ردٌّ فعلاً، لم يُنسَ الرابط).
  const forgottenLinkRfqs = useMemo(
    () => rfqs.filter((r) => r.public_share_is_live && !scopedRows.some((row) => row.rfq === r.id)),
    [rfqs, scopedRows],
  );
  const forgottenLinkHint = forgottenLinkRfqs.length > 0 ? (
    <p className="mt-1 text-[11px] ktra-text-soft">
      تذكير: رابطٌ عامٌّ مفتوحٌ بلا أيّ ردّ بعد على{" "}
      {forgottenLinkRfqs.map((r) => r.rfq_number || `مسودة #${r.id}`).join("، ")}.
    </p>
  ) : null;

  const visibleRows = useMemo(() => {
    const term = search.trim().toLowerCase();
    let list = scopedRows.filter((row) => {
      if (statusFilter !== "all" && row.status !== statusFilter) return false;
      if (rfqFilter !== "all" && String(row.rfq) !== rfqFilter) return false;
      if (term) {
        const haystack = `${row.supplier_name} ${row.supplier_email} ${row.rfq_number || ""}`.toLowerCase();
        if (!haystack.includes(term)) return false;
      }
      return true;
    });
    list = [...list].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "supplier_name") cmp = a.supplier_name.localeCompare(b.supplier_name, "ar");
      else if (sortKey === "total") cmp = lineTotal(a) - lineTotal(b);
      else cmp = new Date(a.submitted_at).getTime() - new Date(b.submitted_at).getTime();
      return sortDir === "asc" ? cmp : -cmp;
    });
    return list.map((row): DisplayRow => ({ ...row, _rowColor: ROW_COLOR[row.status] }));
  }, [scopedRows, search, statusFilter, rfqFilter, sortKey, sortDir]);

  const refresh = () => {
    listPublicSupplierQuoteRequests()
      .then(setRows)
      .catch((cause) => toast(cause instanceof Error ? cause.message : "تعذّر تحديث القائمة", "error"));
  };

  const openApproveDialog = async (row: PublicSupplierQuoteRequestDto) => {
    setApproveOpen(true);
    setMatches(null);
    setMatchesLoading(true);
    try {
      const results = await getPublicSupplierQuoteRequestMatches(row.id);
      setMatches(results);
    } catch (cause) {
      toast(cause instanceof Error ? cause.message : "تعذّر تحميل اقتراحات المطابقة", "error");
      setMatches([]);
    } finally {
      setMatchesLoading(false);
    }
  };

  const confirmApprove = async (partnerId: number | null) => {
    if (!selected) return;
    setBusy(true);
    try {
      const result = await approvePublicSupplierQuoteRequest(selected.id, partnerId ?? undefined);
      toast(`تم الاعتماد — أُنشئ عرض السعر ${result.quotation_id ? "بنجاح" : ""}`.trim(), "success");
      setApproveOpen(false);
      setSelected(null);
      refresh();
      onApproved();
    } catch (cause) {
      toast(cause instanceof Error ? cause.message : "تعذّر اعتماد الردّ", "error");
    } finally {
      setBusy(false);
    }
  };

  const handleReject = async (row: PublicSupplierQuoteRequestDto) => {
    const ok = await confirm({
      title: "رفض الردّ",
      message: `رفض ردّ «${row.supplier_name}»؟ يبقى الصفّ محفوظاً بحالة مرفوض — لا حذف.`,
      confirmText: "رفض",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await rejectPublicSupplierQuoteRequest(row.id);
      toast("تم رفض الردّ", "success");
      setSelected(null);
      refresh();
    } catch (cause) {
      toast(cause instanceof Error ? cause.message : "تعذّر رفض الردّ", "error");
    } finally {
      setBusy(false);
    }
  };

  const columns: DenseColumn<DisplayRow>[] = [
    {
      key: "supplier_name", header: "الاسم", sortable: true,
      // البند 5: يُعرض حرفياً كما كتبه المورّد — بلا تطبيع ولا تنسيق.
      render: (row) => <span dir="auto">{row.supplier_name}</span>,
    },
    {
      key: "supplier_email", header: "البريد الإلكتروني",
      render: (row) => <span dir="ltr" className="text-[11px]">{row.supplier_email}</span>,
    },
    {
      key: "rfq_number", header: "الطلبية", width: "110px",
      render: (row) => <b className="tabular-nums">{row.rfq_number || `#${row.rfq}`}</b>,
    },
    {
      key: "total", header: "الإجمالي", width: "130px", align: "center", numeric: true, sortable: true,
      render: (row) => <>{formatMoney(lineTotal(row))} {row.currency_code || ""}</>,
    },
    {
      key: "priced", header: "التسعير", width: "100px", align: "center",
      render: (row) => <>{`مُسعَّر ${row.lines.length} من ${rfqLineCount.get(row.rfq) ?? row.lines.length}`}</>,
    },
    {
      key: "submitted_at", header: "وقت الوصول", width: "150px", sortable: true,
      render: (row) => <>{formatDateTimeValue(row.submitted_at)}</>,
    },
  ];

  if (!loading && scopedRows.length === 0 && forgottenLinkRfqs.length === 0) return null;

  // لا جدول ردودٍ لعرضه — التذكير وحده، سطرٌ خافتٌ لا قسمٌ كامل.
  if (!loading && scopedRows.length === 0) {
    return <div className="mt-4 px-1">{forgottenLinkHint}</div>;
  }

  return (
    <div className="mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
      <div className="flex items-center gap-2">
        <Inbox className="h-4 w-4 ktra-text-soft" aria-hidden="true" />
        <h3 className="font-bold text-[var(--color-text)]">
          عروض عامة — بانتظار اعتمادك ({pendingCount})
        </h3>
      </div>
      <p className="mt-1 text-[11px] ktra-text-soft">
        ردودٌ من غرباء كتبوا اسمهم على رابطٍ عامٍّ لطلبيةٍ — لم تدخل دفاترك، ولم
        يُنشأ لها أيّ حساب مورّد بعد. الاعتماد وحده يُنشئ الاثنين معاً.
      </p>
      {forgottenLinkHint}
      {floodHint}

      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="ktra-field">
          <span className="ktra-field-label">بحث</span>
          <input
            className="ktra-input"
            placeholder="بحث بالاسم / البريد / رقم الطلبية…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">الحالة</span>
          <select className="ktra-input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">الطلبية</span>
          <select className="ktra-input" value={rfqFilter} onChange={(e) => setRfqFilter(e.target.value)}>
            <option value="all">كل الطلبيات</option>
            {rfqs.map((r) => (
              <option key={r.id} value={String(r.id)}>{r.rfq_number || `مسودة #${r.id}`}</option>
            ))}
          </select>
        </label>
      </div>

      {error && (
        <div className="ktra-banner ktra-banner--err mt-2" role="alert">{error}</div>
      )}

      <div className="mt-2">
        <KitDenseTable<DisplayRow>
          columns={columns}
          rows={visibleRows}
          getRowKey={(row) => row.id}
          loading={loading}
          emptyHint="لا نتائج مطابقة"
          rowColorKey="_rowColor"
          sortKey={sortKey}
          sortDir={sortDir}
          onSort={(key, dir) => { setSortKey(key as SortKey); setSortDir(dir); }}
          onRowClick={(row) => setSelected(row)}
        />
      </div>

      {selected && (
        <DetailDialog
          row={selected}
          totalLines={rfqLineCount.get(selected.rfq) ?? selected.lines.length}
          busy={busy}
          onClose={() => setSelected(null)}
          onApprove={() => void openApproveDialog(selected)}
          onReject={() => void handleReject(selected)}
        />
      )}

      {approveOpen && selected && (
        <ApproveDialog
          row={selected}
          matches={matches}
          loading={matchesLoading}
          busy={busy}
          onConfirm={(partnerId) => void confirmApprove(partnerId)}
          onClose={() => setApproveOpen(false)}
        />
      )}
    </div>
  );
};

const DetailDialog: React.FC<{
  row: PublicSupplierQuoteRequestDto;
  totalLines: number;
  busy: boolean;
  onClose: () => void;
  onApprove: () => void;
  onReject: () => void;
}> = ({ row, totalLines, busy, onClose, onApprove, onReject }) => (
  <div dir="rtl" className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true">
    <div className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl">
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
        <div>
          <h3 className="font-bold text-[var(--color-text)]" dir="auto">{row.supplier_name}</h3>
          <span className="text-[11px] ktra-text-soft" dir="ltr">{row.supplier_email}</span>
        </div>
        <button type="button" onClick={onClose} className="rounded p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]" title="إغلاق">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 text-sm">
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[12px]">
          <dt className="ktra-text-soft">الطلبية</dt>
          <dd>{row.rfq_number || `#${row.rfq}`}</dd>
          <dt className="ktra-text-soft">الهاتف</dt>
          <dd dir="ltr">{row.supplier_phone || "—"}</dd>
          <dt className="ktra-text-soft">وقت الوصول</dt>
          <dd>{formatDateTimeValue(row.submitted_at)}</dd>
          <dt className="ktra-text-soft">عنوان الإرسال (IP)</dt>
          <dd dir="ltr">{row.submitted_ip || "—"}</dd>
          <dt className="ktra-text-soft">الحالة</dt>
          <dd>{row.status_display}{row.decided_by_name ? ` — ${row.decided_by_name}` : ""}</dd>
        </dl>

        {row.general_note && (
          <div className="mt-3 rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2 text-[12px]">
            <div className="mb-1 font-semibold ktra-text-soft">ملاحظة المورّد العامة</div>
            {row.general_note}
          </div>
        )}

        <table className="ktra-grid mt-3 w-full" data-variant="list">
          <thead>
            <tr>
              <th className="text-right">الصنف</th>
              <th className="w-24 text-center">السعر</th>
              <th className="text-right">ملاحظة المورّد</th>
            </tr>
          </thead>
          <tbody>
            {row.lines.map((line) => (
              <tr key={line.id}>
                <td dir="auto">{line.name_snapshot}</td>
                <td className="ktra-num text-center">{formatMoney(line.unit_price)}</td>
                <td className="text-[11px] ktra-text-soft">{line.supplier_note || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-2 text-[11px] ktra-text-soft">
          مُسعَّر {row.lines.length} من {totalLines} بنداً — الإجمالي{" "}
          <b className="text-[var(--color-text)]">
            {formatMoney(lineTotal(row))} {row.currency_code || ""}
          </b>
        </div>
      </div>

      {row.status === "pending" && (
        <div className="flex justify-end gap-2 border-t border-[var(--color-border)] px-4 py-3">
          <button
            type="button"
            disabled={busy}
            onClick={onReject}
            className="flex items-center gap-1 rounded-lg border border-red-300 px-4 py-1.5 text-sm font-semibold text-red-700 hover:bg-red-50"
          >
            <XCircle className="h-4 w-4" /> رفض
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onApprove}
            className="flex items-center gap-1 rounded-lg bg-emerald-600 px-4 py-1.5 text-sm font-bold text-white hover:bg-emerald-700"
          >
            <CheckCircle2 className="h-4 w-4" /> اعتماد
          </button>
        </div>
      )}
    </div>
  </div>
);

const SIGNAL_LABELS: Record<string, string> = {
  email: "بريدٌ مطابق",
  name: "اسمٌ مطابق",
  tax_number: "رقمٌ ضريبيّ شبيه",
};

const ApproveDialog: React.FC<{
  row: PublicSupplierQuoteRequestDto;
  matches: PublicQuoteRequestMatchDto[] | null;
  loading: boolean;
  busy: boolean;
  onConfirm: (partnerId: number | null) => void;
  onClose: () => void;
}> = ({ row, matches, loading, busy, onConfirm, onClose }) => {
  const [choice, setChoice] = useState<number | "new" | null>(null);

  return (
    <div dir="rtl" className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true">
      <div className="flex max-h-[90vh] w-full max-w-md flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
          <h3 className="font-bold text-[var(--color-text)]">اعتماد ردّ «{row.supplier_name}»</h3>
          <button type="button" onClick={onClose} className="rounded p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]" title="إغلاق">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          <p className="mb-3 text-[11px] ktra-text-soft">
            اختر طرفاً قائماً يُنسَب إليه هذا العرض، أو أنشئ مورّداً جديداً. لا شيء مُختارٌ مسبقاً.
          </p>

          {loading && <div className="py-4 text-center text-sm ktra-text-soft">جاري تحميل الاقتراحات…</div>}

          {!loading && (
            <div className="flex flex-col gap-2">
              {(matches || []).map((match) => (
                <label
                  key={match.partner_id}
                  className={`flex cursor-pointer flex-col gap-1 rounded-lg border p-2 text-sm ${
                    choice === match.partner_id
                      ? "border-[var(--color-primary)] bg-[var(--color-surface-2)]"
                      : "border-[var(--color-border)]"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="approve-match"
                      checked={choice === match.partner_id}
                      onChange={() => setChoice(match.partner_id)}
                    />
                    <span className="font-semibold">{match.name}</span>
                    <span className="text-[10px] ktra-text-soft">
                      {match.signals.map((s) => SIGNAL_LABELS[s] || s).join(" · ")}
                    </span>
                  </span>
                  {match.already_recipient && (
                    <span className="mr-6 flex items-center gap-1 rounded border border-amber-300 bg-amber-50 px-2 py-1 text-[10px] font-medium text-amber-800">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      هذا الطرف مستقبِلٌ مسمّىً بالفعل على هذه الطلبية — تحقّق من
                      ردّه الحقيقي على رابطه الخاص قبل الاعتماد عليه هنا.
                    </span>
                  )}
                </label>
              ))}

              <label
                className={`flex cursor-pointer items-center gap-2 rounded-lg border p-2 text-sm ${
                  choice === "new"
                    ? "border-[var(--color-primary)] bg-[var(--color-surface-2)]"
                    : "border-[var(--color-border)]"
                }`}
              >
                <input
                  type="radio"
                  name="approve-match"
                  checked={choice === "new"}
                  onChange={() => setChoice("new")}
                />
                <span className="font-semibold">أنشئ مورّداً جديداً</span>
                <span className="text-[10px] ktra-text-soft">باسم «{row.supplier_name}»</span>
              </label>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-[var(--color-border)] px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-[var(--color-border)] px-4 py-1.5 text-sm text-[var(--color-text-muted)]"
          >
            إلغاء
          </button>
          <button
            type="button"
            disabled={choice === null || busy}
            onClick={() => onConfirm(choice === "new" ? null : (choice as number))}
            className="rounded-lg bg-emerald-600 px-4 py-1.5 text-sm font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            اعتماد
          </button>
        </div>
      </div>
    </div>
  );
};
