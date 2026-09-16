import React, { useEffect, useState } from "react";
import {
  listUsageEvents,
  reverseUsageEvent,
  ServiceUsageEventRow,
} from "../../services/platformWorkOrdersApi";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { formatNumber } from "../../utils/formatNumber";
import { formatDateTimeValue } from "../../utils/formatDate";
import {
  CcCard,
  CcEmpty,
  CcPill,
  CcSectionTitle,
  CcStatTile,
  CcTable,
  CcThead,
  CcTh,
  CcTr,
  CcTd,
} from "./ui";

/** رسالةٌ موحَّدةٌ تميّز 403 عن غيره بدل نصّ الخادم الخام. */
const describeError = (cause: unknown, fallback: string): string =>
  describePlatformOpsError(cause, "ليس لديك تصريحٌ لمراجعة دفتر الاستخدام.", fallback);

/**
 * دفترُ الاستخدام (القصة ١٩): «أريد رؤية سجلّ استهلاكٍ غير قابلٍ للمحو **ومصدرَ كلّ
 * وحدة**، لكي أراجع أيّ اعتراض». فلا يكفي عرضُ الوحدات — يُعرض لكلّ حدثٍ مستندُه
 * ونسخةُ الكتالوج التي حُسب بها ولقطةُ عدد بنوده **ومصدرُ ذلك العدد** (مرصودٌ أم
 * مُصرَّحٌ به)، وهي مادّةُ الاعتراض نفسُها.
 *
 * والإلغاءُ **لا حذف**: عكسٌ بسببٍ مكتوبٍ يُنشئ حدثاً جديداً يشير إلى أصله.
 */
export const ServiceUsageLedgerPanel: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const [events, setEvents] = useState<ServiceUsageEventRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyReverse, setBusyReverse] = useState<number | null>(null);
  // سببُ العكس يُكتب **داخل الصفّ** لا في حوار متصفّح: `window.prompt` محظورةٌ في
  // هذا المستودع (انظر `components/common/PromptDialog.tsx`) — بلا RTL ولا تمييزَ
  // للنصّ، وهذا مسارٌ يغيّر ما يُفوتَر على العميل.
  const [reversingId, setReversingId] = useState<number | null>(null);
  const [reversalReason, setReversalReason] = useState("");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setEvents(await listUsageEvents());
    } catch (err: unknown) {
      setError(describeError(err, "تعذّر تحميل دفتر الاستخدام."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  /** معرّفاتُ الأحداث التي عُكست سلفاً — يُشار إليها من حدث العكس عبر `reversed_event`. */
  const reversedIds = new Set(
    events.filter((e) => e.reversed_event !== null).map((e) => e.reversed_event as number),
  );

  const handleReverse = async (event: ServiceUsageEventRow) => {
    const reason = reversalReason.trim();
    if (!reason) {
      toast("سببُ العكس مطلوب.", "error");
      return;
    }
    const proceed = await confirm({
      title: "عكسُ حدث استخدام",
      message:
        `سيُنشأ حدثُ عكسٍ جديدٌ لـ${formatNumber(event.units)} وحدة — لا حذفَ للأصل. ` +
        "وإن كان الحدثُ من دورةٍ فُوترت سلفاً فلن يتغيّر عدّادُ الدورة الجارية.",
      confirmText: "عكس",
      danger: true,
    });
    if (!proceed) return;
    setBusyReverse(event.id);
    try {
      await reverseUsageEvent(event.id, reason);
      toast("سُجِّل حدثُ العكس في الدفتر.", "success");
      setReversingId(null);
      setReversalReason("");
      await load();
    } catch (err: unknown) {
      toast(describeError(err, "تعذّر عكسُ الحدث."), "error");
    } finally {
      setBusyReverse(null);
    }
  };

  if (loading) {
    return (
      <CcCard className="p-6" dir="rtl">
        <div className="py-12 text-center text-xs text-cc-text-muted">جاري تحميل دفتر الاستخدام...</div>
      </CcCard>
    );
  }

  return (
    <div className="space-y-6" dir="rtl">
      {events.length > 0 && (
        <section className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <CcCard className="p-4 shadow-cc-card">
            <CcStatTile
              label="إجمالي الأحداث المسجّلة"
              value={events.length}
              tone="accent"
            />
          </CcCard>
          <CcCard className="p-4 shadow-cc-card">
            <CcStatTile
              label="الأحداث المعكوسة"
              value={reversedIds.size}
              tone={reversedIds.size > 0 ? "warning" : "neutral"}
            />
          </CcCard>
        </section>
      )}

      <CcCard className="p-4 sm:p-6">
        <CcSectionTitle
          title="دفترُ الاستخدام"
          subtitle="سجلٌّ غيرُ قابلٍ للمحو — يُنتَج بعد اعتماد المُسلَّم حصراً، والإلغاءُ عكسٌ لا حذف"
          badge={events.length}
          action={
            <button
              type="button"
              onClick={() => void load()}
              className="rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs font-semibold text-cc-text hover:bg-cc-surface transition"
            >
              تحديث
            </button>
          }
          className="mb-4"
        />

        {error && (
          <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300">
            {error}
          </div>
        )}

        {events.length === 0 ? (
          <CcEmpty title="لا أحداث استخدامٍ بعد" />
        ) : (
          <CcTable>
            <CcThead>
              <tr>
                <CcTh>الشركة</CcTh>
                <CcTh>النوع</CcTh>
                <CcTh>المصدر</CcTh>
                <CcTh>البنود</CcTh>
                <CcTh>الوحدات</CcTh>
                <CcTh>الكتالوج</CcTh>
                <CcTh>الموظف</CcTh>
                <CcTh>الاعتماد</CcTh>
                <CcTh />
              </tr>
            </CcThead>
            <tbody>
              {events.map((e) => {
                const isReversal = e.event_type === "reversal";
                const alreadyReversed = reversedIds.has(e.id);
                return (
                  <CcTr key={e.id}>
                    <CcTd className="font-medium text-cc-text">{e.company_name}</CcTd>
                    <CcTd>
                      <CcPill tone={isReversal ? "danger" : "success"}>
                        {e.event_type_display}
                      </CcPill>
                    </CcTd>
                    <CcTd className="text-cc-text-muted">
                      {e.source_type_display} #{formatNumber(e.source_id)}
                    </CcTd>
                    <CcTd className="text-cc-text-muted">
                      {formatNumber(e.line_count_snapshot)}
                      {/* مصدرُ العدد هو مادّةُ الاعتراض: مرصودٌ من المستند أم مُصرَّحٌ به. */}
                      <span
                        className={`mr-1 text-[10px] font-semibold ${
                          e.line_count_source === "observed" ? "text-emerald-400" : "text-amber-400"
                        }`}
                      >
                        ({e.line_count_source_display})
                      </span>
                    </CcTd>
                    <CcTd className="font-semibold text-cc-text">{formatNumber(e.units)}</CcTd>
                    <CcTd className="text-cc-text-muted">v{formatNumber(e.catalog_version)}</CcTd>
                    <CcTd className="text-cc-text">{e.employee_name || "—"}</CcTd>
                    <CcTd className="text-cc-text-muted">{formatDateTimeValue(e.approved_at) || "—"}</CcTd>
                    <CcTd className="text-left">
                      {!isReversal && !alreadyReversed && reversingId !== e.id && (
                        <button
                          type="button"
                          onClick={() => {
                            setReversingId(e.id);
                            setReversalReason("");
                          }}
                          className="rounded-lg px-2.5 py-1 text-[11px] font-bold text-rose-400 border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 transition"
                        >
                          عكس
                        </button>
                      )}
                      {reversingId === e.id && (
                        <div className="flex items-center gap-1.5 justify-end">
                          <input
                            type="text"
                            value={reversalReason}
                            onChange={(ev) => setReversalReason(ev.target.value)}
                            placeholder="سبب العكس (إلزاميّ)"
                            className="w-44 rounded-lg border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-[11px] text-cc-text placeholder:text-rose-400/60 focus:outline-none focus:ring-1 focus:ring-rose-500"
                          />
                          <button
                            type="button"
                            onClick={() => void handleReverse(e)}
                            disabled={busyReverse === e.id || !reversalReason.trim()}
                            className="rounded-lg bg-rose-600 px-2.5 py-1 text-[11px] font-bold text-white hover:bg-rose-500 transition disabled:opacity-50"
                          >
                            تأكيد
                          </button>
                          <button
                            type="button"
                            onClick={() => setReversingId(null)}
                            className="rounded-lg bg-cc-surface-2 border border-cc-border px-2.5 py-1 text-[11px] font-bold text-cc-text-muted hover:text-cc-text transition"
                          >
                            إلغاء
                          </button>
                        </div>
                      )}
                      {alreadyReversed && <CcPill tone="neutral">معكوس</CcPill>}
                      {isReversal && e.reason && (
                        <span className="text-[10px] text-cc-text-muted">{e.reason}</span>
                      )}
                    </CcTd>
                  </CcTr>
                );
              })}
            </tbody>
          </CcTable>
        )}
      </CcCard>
    </div>
  );
};
