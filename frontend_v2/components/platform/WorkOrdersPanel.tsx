import React, { useEffect, useMemo, useState } from "react";
import {
  addWorkOrderComment,
  assignWorkOrder,
  changeWorkOrderPriority,
  createWorkOrder,
  getEmployeeWorkOrderQueue,
  linkWorkOrderDocument,
  listWorkOrderComments,
  listWorkOrderDeliverables,
  listWorkOrderDocumentLinks,
  listWorkOrders,
  ReviewDeliverableApprovedResponse,
  reviewWorkOrderDeliverable,
  RejectionCategory,
  SERVICE_DOCUMENT_TYPE_LABELS,
  SERVICE_DOCUMENT_TYPES,
  ServiceDocumentType,
  submitWorkOrderDeliverable,
  transitionWorkOrder,
  WorkOrderCommentRow,
  WorkOrderDeliverableRow,
  WorkOrderDetailRow,
  WorkOrderDocumentLinkRow,
  WORK_ORDER_STATUS_LABELS,
  WORK_ORDER_TRANSITIONS,
  WorkOrderPriority,
  WorkOrderStatus,
} from "../../services/platformWorkOrdersApi";
import { listAssignmentCandidates, type AssignmentCandidateRow } from "../../services/platformOpsApi";
import { CompanyPicker } from "./CompanyPicker";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { useAuth } from "../../contexts/AuthContext";
import { usePlatformStaffCapabilitiesState } from "../../hooks/usePlatformStaffCapabilities";
import { CcCard, CcEmpty, CcPill, CcSectionTitle, CcSkeleton } from "./ui";
import type { CcTone } from "../../utils/ccTone";

/** خياراتُ نموذج الأولويّة وحدها — عرضُ صفٍّ قائمٍ يبقى من `priority_display` الخادميّ. */
const PRIORITY_OPTION_LABELS: Record<WorkOrderPriority, string> = {
  low: "منخفضة",
  normal: "عادية",
  high: "مرتفعة",
  urgent: "عاجلة",
};
const PRIORITY_OPTIONS: WorkOrderPriority[] = ["low", "normal", "high", "urgent"];

/**
 * ألوانٌ فقط — **لا تسميات**. اسمُ الأولوية يأتي من الخادم (`priority_display`)
 * كما ينصّ تعليقُ `WorkOrderSerializer` نفسُه: «ولا يجوز أن تُترجمها الواجهةُ
 * بجدولٍ ثانٍ يتباعد». والصنفُ التنسيقيُّ لا يُرسَل من الخادم فيبقى هنا.
 */
const PRIORITY_TONES: Record<WorkOrderPriority, CcTone> = {
  low: "neutral",
  normal: "accent",
  high: "warning",
  urgent: "danger",
};

const STATUS_TONES: Record<string, CcTone> = {
  received: "neutral",
  screening: "neutral",
  data_entry: "accent",
  review: "violet",
  approval: "accent",
  closed: "success",
  waiting_customer: "warning",
  cancelled: "danger",
};

const REVIEW_STATUS_TONES: Record<string, CcTone> = {
  approved: "success",
  rejected: "danger",
  pending: "warning",
};

/**
 * مفاتيحُ خيارات قائمة الردّ — تُبنى منها `<option>` فيلزمها مفاتيحُ محلّيّة.
 * أمّا **عرضُ** التصنيف على مُسلَّمٍ مردودٍ فمن `rejection_category_display` الخادميّ.
 */
const REJECTION_CATEGORY_LABELS: Record<Exclude<RejectionCategory, "">, string> = {
  employee_error: "خطأ الموظف",
  customer_new_info: "معلومات جديدة من العميل",
  other: "أخرى",
};

/** رسالةُ الخطأ الموحَّدة لأسطح المنصّة — تميّز 403 عن غيره بدل عرض نصّ الخادم الخام. */
const describeError = (cause: unknown, fallback: string): string =>
  describePlatformOpsError(cause, "ليس لديك تصريحٌ لهذا الإجراء على أمر العمل.", fallback);

/**
 * `toLocale*` ممنوعةٌ في هذا المستودع: بالعربية تُصيّر التاريخَ تقويماً هجريّاً،
 * وأرقامُها تتبدّل بين جهازٍ وآخر بحسب بيانات ICU. `formatDateTimeValue` هي صيغةُ
 * الموقع الواحدة: `dd/MM/yyyy HH:mm` بأرقامٍ لاتينية.
 */
function formatDateTime(value: string | null | undefined): string {
  return formatDateTimeValue(value) || "—";
}

const WorkOrderDetail: React.FC<{
  workOrder: WorkOrderDetailRow;
  isManager: boolean;
  onChanged: (updated: WorkOrderDetailRow) => void;
}> = ({ workOrder, isManager, onChanged }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [comments, setComments] = useState<WorkOrderCommentRow[]>([]);
  const [links, setLinks] = useState<WorkOrderDocumentLinkRow[]>([]);
  const [deliverables, setDeliverables] = useState<WorkOrderDeliverableRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [candidates, setCandidates] = useState<AssignmentCandidateRow[]>([]);
  const [assigneeChoice, setAssigneeChoice] = useState<string>("");
  const [busyAssign, setBusyAssign] = useState(false);
  const [priorityChoice, setPriorityChoice] = useState<WorkOrderPriority>(workOrder.priority);
  const [busyPriority, setBusyPriority] = useState(false);

  const [newComment, setNewComment] = useState("");
  const [commentVisibility, setCommentVisibility] = useState<"internal" | "client_visible">("internal");
  const [busyComment, setBusyComment] = useState(false);

  const [linkDocType, setLinkDocType] = useState<ServiceDocumentType>("sales_invoice");
  const [linkDocId, setLinkDocId] = useState("");
  const [linkLineCount, setLinkLineCount] = useState("1");
  const [busyLink, setBusyLink] = useState(false);
  const [recountReason, setRecountReason] = useState("");
  const [needsRecountReason, setNeedsRecountReason] = useState(false);

  const [deliverableContent, setDeliverableContent] = useState("");
  const [selectedLinkIds, setSelectedLinkIds] = useState<number[]>([]);
  const [busyDeliverable, setBusyDeliverable] = useState(false);

  const [busyTransition, setBusyTransition] = useState<WorkOrderStatus | null>(null);

  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const [rejectionCategory, setRejectionCategory] = useState<Exclude<RejectionCategory, "">>("employee_error");
  const [busyReview, setBusyReview] = useState<number | null>(null);

  const allowedNext = WORK_ORDER_TRANSITIONS[workOrder.status] || [];
  const unlinkedForSubmit = links.filter((l) => !l.deliverable);

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, l, d] = await Promise.all([
        listWorkOrderComments(workOrder.id),
        listWorkOrderDocumentLinks(workOrder.id),
        listWorkOrderDeliverables(workOrder.id),
      ]);
      setComments(c);
      setLinks(l);
      setDeliverables(d);
    } catch (err: any) {
      setError(err?.message || "تعذر تحميل تفاصيل أمر العمل.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDetail();
    setSelectedLinkIds([]);
    setPriorityChoice(workOrder.priority);
    setAssigneeChoice(workOrder.assignee ? String(workOrder.assignee) : "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workOrder.id]);

  useEffect(() => {
    if (!isManager) {
      setCandidates([]);
      return;
    }
    let cancelled = false;
    listAssignmentCandidates(workOrder.tenant)
      .then((rows) => { if (!cancelled) setCandidates(rows); })
      .catch(() => { if (!cancelled) setCandidates([]); });
    return () => { cancelled = true; };
  }, [isManager, workOrder.tenant]);

  const handleAssign = async () => {
    setBusyAssign(true);
    setError(null);
    try {
      const updated = await assignWorkOrder(workOrder.id, assigneeChoice ? Number(assigneeChoice) : null);
      onChanged(updated);
      toast(assigneeChoice ? "تم إسناد أمر العمل." : "أُعيد أمر العمل إلى الطابور.", "success");
    } catch (err: unknown) {
      toast(describeError(err, "تعذّر إسناد أمر العمل."), "error");
    } finally {
      setBusyAssign(false);
    }
  };

  const handleChangePriority = async () => {
    if (priorityChoice === workOrder.priority) return;
    setBusyPriority(true);
    setError(null);
    try {
      const updated = await changeWorkOrderPriority(workOrder.id, priorityChoice);
      onChanged(updated);
      toast("تم تعديل الأولوية.", "success");
    } catch (err: unknown) {
      toast(describeError(err, "تعذّر تعديل الأولوية."), "error");
      setPriorityChoice(workOrder.priority);
    } finally {
      setBusyPriority(false);
    }
  };

  const handleTransition = async (target: WorkOrderStatus) => {
    setBusyTransition(target);
    setError(null);
    setNotice(null);
    try {
      const updated = await transitionWorkOrder(workOrder.id, target, workOrder.updated_at);
      onChanged(updated);
      setNotice(`تم النقل إلى: ${WORK_ORDER_STATUS_LABELS[target]}`);
    } catch (err: any) {
      if (err?.status === 409 && err?.data?.current) {
        onChanged(err.data.current);
        setError("تغيّرت حالة أمر العمل منذ آخر قراءة — عُرضت النسخة الحالية.");
      } else {
        setError(err?.message || "تعذر تنفيذ النقل.");
      }
    } finally {
      setBusyTransition(null);
    }
  };

  const handleAddComment = async () => {
    if (!newComment.trim()) return;
    setBusyComment(true);
    setError(null);
    try {
      const comment = await addWorkOrderComment(workOrder.id, newComment.trim(), commentVisibility);
      setComments((prev) => [...prev, comment]);
      setNewComment("");
    } catch (err: any) {
      setError(err?.message || "تعذر إضافة التعليق.");
    } finally {
      setBusyComment(false);
    }
  };

  const handleLinkDocument = async () => {
    const docId = Number(linkDocId);
    if (!docId || docId < 1) {
      setError("رقم المستند مطلوب.");
      return;
    }
    setBusyLink(true);
    setError(null);
    try {
      const reason = recountReason.trim();
      const link = await linkWorkOrderDocument(workOrder.id, {
        document_type: linkDocType,
        document_id: docId,
        line_count: Number(linkLineCount) || 1,
        ...(reason ? { recount_reason: reason } : {}),
      });
      setLinks((prev) => [...prev, link]);
      setLinkDocId("");
      setRecountReason("");
      setNeedsRecountReason(false);
      if (reason) toast("أُعيد احتسابُ المستند بسببٍ موثَّق.", "success");
    } catch (err: unknown) {
      // 409 ليس طريقاً مسدوداً: المستندُ محتسَبٌ سلفاً ⇒ يُفتح حقلُ السبب ليعتمده
      // مديرُ العمليات. و403 `manager_only` يعني أنّ من يحاول ليس مديراً.
      const code = (err as { code?: string; response?: { data?: { code?: string } } })?.code
        ?? (err as { response?: { data?: { code?: string } } })?.response?.data?.code;
      if (code === "document_already_charged") {
        setNeedsRecountReason(true);
        setError("هذا المستند احتُسب سلفاً — إعادةُ احتسابه تلزمها موافقةُ مدير العمليات بسببٍ مكتوب.");
      } else if (code === "manager_only") {
        setNeedsRecountReason(false);
        setRecountReason("");
        setError("إعادةُ احتساب مستندٍ محتسَبٍ سلفاً متاحةٌ لمدير العمليات وحدَه.");
      } else {
        setError(describeError(err, "تعذّر ربط المستند."));
      }
    } finally {
      setBusyLink(false);
    }
  };

  const toggleLinkSelection = (id: number) => {
    setSelectedLinkIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handleSubmitDeliverable = async () => {
    setBusyDeliverable(true);
    setError(null);
    try {
      const deliverable = await submitWorkOrderDeliverable(workOrder.id, {
        kind: "note",
        content: deliverableContent,
        document_link_ids: selectedLinkIds,
      });
      setDeliverables((prev) => [...prev, deliverable]);
      setDeliverableContent("");
      setSelectedLinkIds([]);
      await loadDetail();
    } catch (err: any) {
      setError(err?.message || "تعذر تسليم العمل.");
    } finally {
      setBusyDeliverable(false);
    }
  };

  const handleApprove = async (deliverableId: number) => {
    // الاعتمادُ يخصم من حصّة العميل ويمنح الموظّفَ إنجازاً، ولا يُلغى إلا بحدث عكسٍ
    // مسجَّل (لا حذف) — فلا يكون بنقرةٍ واحدةٍ بلا تأكيد.
    const proceed = await confirm({
      title: "اعتماد المُسلَّم",
      message: "سيولّد الاعتمادُ وحداتِ استخدامٍ تُخصم من حصّة العميل وتُحتسب إنجازاً للموظّف. متابعة؟",
      confirmText: "اعتماد",
      danger: false,
    });
    if (!proceed) return;
    setBusyReview(deliverableId);
    setError(null);
    try {
      const res = await reviewWorkOrderDeliverable(workOrder.id, deliverableId, { review_status: "approved" });
      const asApproved = res as ReviewDeliverableApprovedResponse;
      if (asApproved.usage_events) {
        toast(
          `اعتُمد المُسلَّم — وُلِّد ${formatNumber(asApproved.usage_events.length)} حدث استخدام في الدفتر.`,
          "success",
        );
      }
      await loadDetail();
    } catch (err: unknown) {
      toast(describeError(err, "تعذّر اعتماد المُسلَّم."), "error");
    } finally {
      setBusyReview(null);
    }
  };

  const handleReject = async (deliverableId: number) => {
    if (!rejectionReason.trim()) {
      setError("سبب الرفض إلزامي.");
      return;
    }
    setBusyReview(deliverableId);
    setError(null);
    try {
      await reviewWorkOrderDeliverable(workOrder.id, deliverableId, {
        review_status: "rejected",
        rejection_reason: rejectionReason.trim(),
        rejection_category: rejectionCategory,
      });
      setRejectingId(null);
      setRejectionReason("");
      toast("رُدَّ المُسلَّم بسببٍ مصنَّف — لا وحداتٍ تُحتسب.", "success");
      await loadDetail();
    } catch (err: unknown) {
      toast(describeError(err, "تعذّر ردّ المُسلَّم."), "error");
    } finally {
      setBusyReview(null);
    }
  };

  return (
    <div className="space-y-4" dir="rtl">
      {error && (
        <CcCard tone="danger" className="p-3 text-xs text-rose-400">
          {error}
        </CcCard>
      )}
      {notice && (
        <CcCard tone="success" className="p-3 text-xs text-emerald-400">
          {notice}
        </CcCard>
      )}

      {/* الإسناد والأولوية — مدير العمليات وحده (القصص ١٣، ٣٤) */}
      {isManager && (
        <CcCard className="p-4 space-y-3">
          <h3 className="text-xs font-bold text-cc-text">الإسناد والأولوية</h3>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={assigneeChoice}
              onChange={(e) => setAssigneeChoice(e.target.value)}
              className="px-2 py-1.5 text-xs bg-cc-bg border border-cc-border text-cc-text rounded-lg min-w-[180px] focus:outline-none focus:border-sky-500"
            >
              <option value="">بلا مسؤول (طابور)</option>
              {candidates.map((c) => (
                <option key={c.employee} value={c.employee}>
                  {c.employee_name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleAssign}
              disabled={busyAssign}
              className="px-3 py-1.5 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-lg disabled:opacity-50 transition-colors"
            >
              {busyAssign ? "..." : "إسناد"}
            </button>
            <select
              value={priorityChoice}
              onChange={(e) => setPriorityChoice(e.target.value as WorkOrderPriority)}
              className="px-2 py-1.5 text-xs bg-cc-bg border border-cc-border text-cc-text rounded-lg focus:outline-none focus:border-sky-500"
            >
              {PRIORITY_OPTIONS.map((p) => (
                <option key={p} value={p}>
                  {PRIORITY_OPTION_LABELS[p]}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleChangePriority}
              disabled={busyPriority || priorityChoice === workOrder.priority}
              className="px-3 py-1.5 text-xs font-semibold text-cc-text bg-cc-surface-2 hover:bg-cc-border border border-cc-border rounded-lg disabled:opacity-50 transition-colors"
            >
              {busyPriority ? "..." : "حفظ الأولوية"}
            </button>
          </div>
          <p className="text-[10px] text-cc-text-muted mt-1">
            المسؤول الحالي: {workOrder.assignee_name || "بلا مسؤول"} — الأولوية الحالية: {workOrder.priority_display}
          </p>
        </CcCard>
      )}

      {/* نقل الحالة */}
      <CcCard className="p-4 space-y-3">
        <h3 className="text-xs font-bold text-cc-text">نقل الحالة</h3>
        <div className="flex flex-wrap gap-2">
          {allowedNext.length === 0 ? (
            <span className="text-xs text-cc-text-muted">لا انتقالات متاحة من هذه الحالة</span>
          ) : (
            allowedNext.map((target) => (
              <button
                key={target}
                type="button"
                onClick={() => handleTransition(target)}
                disabled={busyTransition === target}
                className="px-3 py-1.5 text-xs font-semibold text-cc-text bg-cc-surface-2 hover:bg-cc-border border border-cc-border rounded-lg disabled:opacity-50 transition-colors"
              >
                {busyTransition === target ? "..." : `→ ${WORK_ORDER_STATUS_LABELS[target]}`}
              </button>
            ))
          )}
        </div>
      </CcCard>

      {loading ? (
        <CcSkeleton variant="card" count={3} />
      ) : (
        <>
          {/* ربط المستندات */}
          <CcCard className="p-4 space-y-3">
            <h3 className="text-xs font-bold text-cc-text">ربط مستند</h3>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={linkDocType}
                onChange={(e) => setLinkDocType(e.target.value as ServiceDocumentType)}
                className="px-2 py-1.5 text-xs bg-cc-bg border border-cc-border text-cc-text rounded-lg focus:outline-none focus:border-sky-500"
              >
                {SERVICE_DOCUMENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {SERVICE_DOCUMENT_TYPE_LABELS[t]}
                  </option>
                ))}
              </select>
              <input
                type="number"
                min={1}
                placeholder="رقم المستند"
                value={linkDocId}
                onChange={(e) => setLinkDocId(e.target.value)}
                className="w-28 px-2 py-1.5 text-xs bg-cc-bg border border-cc-border text-cc-text rounded-lg focus:outline-none focus:border-sky-500"
              />
              <input
                type="number"
                min={1}
                placeholder="عدد السطور"
                value={linkLineCount}
                onChange={(e) => setLinkLineCount(e.target.value)}
                className="w-24 px-2 py-1.5 text-xs bg-cc-bg border border-cc-border text-cc-text rounded-lg focus:outline-none focus:border-sky-500"
              />
              <button
                type="button"
                onClick={handleLinkDocument}
                disabled={busyLink}
                className="px-3 py-1.5 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-lg disabled:opacity-50 transition-colors"
              >
                ربط
              </button>
            </div>
            {needsRecountReason && (
              <div className="flex items-center gap-2 mb-2">
                <input
                  type="text"
                  value={recountReason}
                  onChange={(e) => setRecountReason(e.target.value)}
                  placeholder="سبب إعادة الاحتساب (لمدير العمليات)"
                  className="flex-1 px-2 py-1.5 text-xs border border-amber-500/30 bg-amber-500/10 text-amber-300 rounded-lg focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleLinkDocument}
                  disabled={busyLink || !recountReason.trim()}
                  className="px-3 py-1.5 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-500 rounded-lg disabled:opacity-50 transition-colors"
                >
                  إعادة الاحتساب
                </button>
              </div>
            )}
            {links.length === 0 ? (
              <p className="text-xs text-cc-text-muted">لا مستندات مرتبطة بعد</p>
            ) : (
              <ul className="space-y-1.5">
                {links.map((l) => (
                  <li key={l.id} className="text-xs flex items-center gap-2 text-cc-text">
                    <input
                      type="checkbox"
                      disabled={!!l.deliverable}
                      checked={selectedLinkIds.includes(l.id)}
                      onChange={() => toggleLinkSelection(l.id)}
                      className="rounded border-cc-border bg-cc-bg"
                    />
                    <span>
                      {l.document_type_display} #{formatNumber(l.document_id)} — {formatNumber(l.line_count)} سطر
                      {/* مصدرُ العدد ظاهرٌ للمعتمِد: المرصودُ من المستند غيرُ المُصرَّح به. */}
                      <span
                        className={`mr-1 ${
                          l.line_count_source === "observed" ? "text-emerald-400" : "text-amber-400"
                        }`}
                      >
                        ({l.line_count_source_display})
                      </span>
                      {l.deliverable ? " (مُرتبط بمُسلَّم)" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CcCard>

          {/* تسليم عمل */}
          <CcCard className="p-4 space-y-3">
            <h3 className="text-xs font-bold text-cc-text">تسليم عمل (مُسلَّم جديد)</h3>
            <textarea
              value={deliverableContent}
              onChange={(e) => setDeliverableContent(e.target.value)}
              placeholder="ملاحظة التسليم..."
              rows={2}
              className="w-full px-3 py-2 text-xs bg-cc-bg border border-cc-border text-cc-text rounded-lg focus:outline-none focus:border-sky-500"
            />
            <p className="text-[11px] text-cc-text-muted">
              اختر أعلاه المستندات المرتبطة غير المُسلَّمة بعد لضمّها ({unlinkedForSubmit.length} متاحة، {selectedLinkIds.length} مختارة).
            </p>
            <button
              type="button"
              onClick={handleSubmitDeliverable}
              disabled={busyDeliverable}
              className="px-3.5 py-2 text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg disabled:opacity-50 transition-colors"
            >
              {busyDeliverable ? "جارٍ التسليم..." : "تسليم"}
            </button>
          </CcCard>

          {/* المُسلَّمات والمراجعة */}
          <CcCard className="p-4 space-y-3">
            <h3 className="text-xs font-bold text-cc-text">المُسلَّمات</h3>
            {deliverables.length === 0 ? (
              <p className="text-xs text-cc-text-muted">لا مُسلَّمات بعد</p>
            ) : (
              <ul className="space-y-3">
                {deliverables.map((d) => (
                  <li key={d.id} className="border border-cc-border rounded-lg p-3 bg-cc-surface-2/40">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-cc-text">{d.kind_display}</span>
                      <CcPill tone={REVIEW_STATUS_TONES[d.review_status] || "warning"}>
                        {d.review_status_display}
                      </CcPill>
                    </div>
                    {d.content && <p className="text-xs text-cc-text-muted mb-1">{d.content}</p>}
                    {d.review_status === "rejected" && (
                      <p className="text-[11px] text-rose-400">
                        سبب الرفض ({d.rejection_category_display}): {d.rejection_reason}
                      </p>
                    )}
                    {/* الحكمُ على المُسلَّم — مدير العمليات وحدَه (القصة ١٤).
                        الخادمُ يردّ `manager_only` لغيره، وهذه اللوحةُ نفسُها
                        تُركَّب في قشرة الموظّف: فبدون الشرط كان صاحبُ المُسلَّم
                        يرى «اعتماد» و«رفض» على عملِه هو — وهو الحكمُ الذي يخصم
                        من حصّة العميل ويُحتسب إنجازاً له. وحالتُه تبقى مقروءةً
                        له في الشارة أعلاه، فالمحجوبُ الفعلُ لا الخبر. */}
                    {isManager && d.review_status === "pending" && (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleApprove(d.id)}
                          disabled={busyReview === d.id}
                          className="px-3 py-1 text-[11px] font-bold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg disabled:opacity-50 transition-colors"
                        >
                          اعتماد
                        </button>
                        {rejectingId === d.id ? (
                          <>
                            <select
                              value={rejectionCategory}
                              onChange={(e) => setRejectionCategory(e.target.value as Exclude<RejectionCategory, "">)}
                              className="px-2 py-1 text-[11px] bg-cc-bg border border-cc-border text-cc-text rounded-lg focus:outline-none"
                            >
                              {(Object.keys(REJECTION_CATEGORY_LABELS) as Array<Exclude<RejectionCategory, "">>).map(
                                (cat) => (
                                  <option key={cat} value={cat}>
                                    {REJECTION_CATEGORY_LABELS[cat]}
                                  </option>
                                ),
                              )}
                            </select>
                            <input
                              type="text"
                              value={rejectionReason}
                              onChange={(e) => setRejectionReason(e.target.value)}
                              placeholder="سبب الرفض"
                              className="px-2 py-1 text-[11px] bg-cc-bg border border-cc-border text-cc-text rounded-lg flex-1 min-w-[160px] focus:outline-none"
                            />
                            <button
                              type="button"
                              onClick={() => handleReject(d.id)}
                              disabled={busyReview === d.id}
                              className="px-3 py-1 text-[11px] font-bold text-white bg-rose-600 hover:bg-rose-500 rounded-lg disabled:opacity-50 transition-colors"
                            >
                              تأكيد الرفض
                            </button>
                            <button
                              type="button"
                              onClick={() => setRejectingId(null)}
                              className="px-2 py-1 text-[11px] text-cc-text-muted hover:text-cc-text"
                            >
                              إلغاء
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setRejectingId(d.id)}
                            className="px-3 py-1 text-[11px] font-bold text-rose-400 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 rounded-lg transition-colors"
                          >
                            رفض
                          </button>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CcCard>

          {/* التعليقات */}
          <CcCard className="p-4 space-y-3">
            <h3 className="text-xs font-bold text-cc-text">التعليقات</h3>
            {comments.length === 0 ? (
              <p className="text-xs text-cc-text-muted">لا تعليقات بعد</p>
            ) : (
              <ul className="space-y-2 mb-3">
                {comments.map((c) => (
                  <li key={c.id} className="text-xs">
                    <span className="font-semibold text-cc-text">{c.author_name}</span>{" "}
                    <span className="text-[10px] text-cc-text-muted">({c.visibility_display})</span>
                    <p className="text-cc-text-muted mt-0.5">{c.content}</p>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={commentVisibility}
                onChange={(e) => setCommentVisibility(e.target.value as "internal" | "client_visible")}
                className="px-2 py-1.5 text-xs bg-cc-bg border border-cc-border text-cc-text rounded-lg focus:outline-none"
              >
                <option value="internal">داخلي</option>
                <option value="client_visible">مرئي للعميل</option>
              </select>
              <input
                type="text"
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                placeholder="أضف تعليقاً..."
                className="flex-1 min-w-[200px] px-3 py-1.5 text-xs bg-cc-bg border border-cc-border text-cc-text rounded-lg focus:outline-none focus:border-sky-500"
              />
              <button
                type="button"
                onClick={handleAddComment}
                disabled={busyComment}
                className="px-3 py-1.5 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-lg disabled:opacity-50 transition-colors"
              >
                إرسال
              </button>
            </div>
          </CcCard>
        </>
      )}
    </div>
  );
};

const NewWorkOrderForm: React.FC<{ onCreated: () => void }> = ({ onCreated }) => {
  const [tenantId, setTenantId] = useState<number | null>(null);
  const [tenantName, setTenantName] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!tenantId || !title.trim()) {
      setError("الشركة والعنوان إلزاميان.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createWorkOrder({ tenant: tenantId, title: title.trim() });
      setTitle("");
      onCreated();
    } catch (err: any) {
      setError(err?.message || "تعذر إنشاء أمر العمل.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <CcCard className="p-4 space-y-3" dir="rtl">
      <h3 className="text-xs font-bold text-cc-text">أمر عمل جديد</h3>
      {error && <p className="text-xs text-rose-400">{error}</p>}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-start">
        <CompanyPicker
          value={tenantId}
          onChange={(id, name) => {
            setTenantId(id);
            setTenantName(name);
          }}
        />
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="عنوان أمر العمل"
          className="px-3 py-1.5 text-xs bg-cc-bg border border-cc-border text-cc-text rounded-lg focus:outline-none focus:border-sky-500"
        />
        <button
          type="button"
          onClick={handleCreate}
          disabled={busy}
          className="px-3.5 py-2 text-xs font-bold text-white bg-sky-600 hover:bg-sky-500 rounded-lg disabled:opacity-50 transition-colors"
        >
          {busy ? "..." : `إنشاء${tenantName ? ` لـ${tenantName}` : ""}`}
        </button>
      </div>
    </CcCard>
  );
};

export const WorkOrdersPanel: React.FC = () => {
  const { currentUser } = useAuth();
  // فشلُ نداء القدرات لا يُترجَم إلى «لستَ مديراً»: أفعالُ المدير تُخفى، لكنّ سبباً
  // وزرَّ إعادةِ محاولةٍ يظهران — وإلا اختفت أزرارُ الإنشاء والإسناد بلا تفسير.
  const { capabilities, failed: capabilitiesFailed, reload: reloadCapabilities } =
    usePlatformStaffCapabilitiesState(
      currentUser?.id ? String(currentUser.id) : undefined,
      !!currentUser?.isSuperAdmin,
    );
  const isManager = capabilities.is_platform_admin;
  const [queue, setQueue] = useState<WorkOrderDetailRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const selected = useMemo(() => queue.find((w) => w.id === selectedId) || null, [queue, selectedId]);

  const loadQueue = async () => {
    setLoading(true);
    setError(null);
    try {
      // `/queue/` طابورٌ **شخصيّ**: مقصورٌ على `assignee__user=request.user` عبر
      // ارتباطاته، فيعود فارغاً دائماً لمدير العمليات — ولا `PlatformEmployee` له
      // ولا ارتباط — بينما الإنشاءُ والاعتمادُ والردُّ في هذه اللوحة للمدير وحدَه.
      // و`/work-orders/` نطاقٌ يشتقّه الخادم للدورين: كلُّ الشركات المؤهَّلة للمدير،
      // وشركاتُ الارتباطات النشطة للموظّف. فتُدمجان: طابورُك أوّلاً بترتيب الخادم،
      // ثمّ بقيّةُ ما يقع في نطاقك — بلا استنساخِ قاعدةِ الترتيب في العميل.
      const [mine, scoped] = await Promise.all([getEmployeeWorkOrderQueue(), listWorkOrders()]);
      const mineIds = new Set(mine.map((w) => w.id));
      setQueue([...mine, ...scoped.filter((w) => !mineIds.has(w.id))]);
    } catch (err: unknown) {
      setError(describeError(err, "تعذّر تحميل أوامر العمل."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadQueue();
  }, []);

  const handleChanged = (updated: WorkOrderDetailRow) => {
    setQueue((prev) => prev.map((w) => (w.id === updated.id ? { ...w, ...updated } : w)));
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" dir="rtl">
      <div className="lg:col-span-1 space-y-4">
        <CcCard className="p-4 space-y-4">
          <CcSectionTitle
            title="طابور أوامر العمل"
            action={
              isManager ? (
                <button
                  type="button"
                  onClick={() => setShowCreate((v) => !v)}
                  className="px-2.5 py-1 text-xs font-bold text-sky-400 bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/30 rounded-lg transition-colors"
                >
                  {showCreate ? "إخفاء" : "+ جديد"}
                </button>
              ) : undefined
            }
          />

          {error && <p className="text-xs text-rose-400">{error}</p>}

          {capabilitiesFailed && (
            <div className="flex items-center justify-between gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2 text-[11px] text-amber-300">
              <span>تعذّر التحقّق من صلاحيّاتك، فأفعالُ مدير العمليات مخفيّةٌ مؤقّتاً.</span>
              <button
                type="button"
                onClick={reloadCapabilities}
                className="px-2 py-1 font-bold bg-amber-500/20 hover:bg-amber-500/30 rounded-lg transition-colors"
              >
                إعادة المحاولة
              </button>
            </div>
          )}

          {loading ? (
            <CcSkeleton variant="card" count={4} />
          ) : queue.length === 0 ? (
            <CcEmpty title="لا أوامر عمل في طابورك حالياً" />
          ) : (
            <ul className="space-y-2">
              {queue.map((w) => (
                <li key={w.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(w.id)}
                    className={`w-full text-right p-3 rounded-lg border transition-all ${
                      w.id === selectedId
                        ? "border-sky-500/50 bg-sky-500/10 shadow-sm"
                        : "border-cc-border bg-cc-surface hover:bg-cc-surface-2"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-bold text-cc-text truncate">{w.title}</span>
                      <CcPill tone={PRIORITY_TONES[w.priority] || "neutral"}>
                        {w.priority_display || w.priority}
                      </CcPill>
                    </div>
                    <div className="flex items-center justify-between gap-2 mt-1.5 text-[11px] text-cc-text-muted">
                      <span className="truncate">{w.company_name}</span>
                      <CcPill tone={STATUS_TONES[w.status] || "neutral"}>
                        {w.status_display || WORK_ORDER_STATUS_LABELS[w.status as WorkOrderStatus] || w.status}
                      </CcPill>
                    </div>
                    <div className="text-[10px] text-cc-text-muted mt-1">أجل: {formatDateTime(w.deadline_at)}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CcCard>
        {isManager && showCreate && <NewWorkOrderForm onCreated={loadQueue} />}
      </div>

      <div className="lg:col-span-2">
        {!selected ? (
          <CcCard className="p-12 text-center">
            <CcEmpty title="اختر أمر عملٍ من الطابور لعرض تفاصيله" />
          </CcCard>
        ) : (
          <WorkOrderDetail workOrder={selected} isManager={isManager} onChanged={handleChanged} />
        )}
      </div>
    </div>
  );
};

export default WorkOrdersPanel;
