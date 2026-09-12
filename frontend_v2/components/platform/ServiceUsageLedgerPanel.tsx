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

  if (loading) return <p className="text-xs text-slate-400">…تحميل دفتر الاستخدام</p>;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-bold text-slate-800">دفترُ الاستخدام</h3>
          <p className="text-[10px] text-slate-400">
            سجلٌّ غيرُ قابلٍ للمحو — يُنتَج بعد اعتماد المُسلَّم حصراً، والإلغاءُ عكسٌ لا حذف
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="px-3 py-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg"
        >
          تحديث
        </button>
      </div>

      {error && (
        <p className="mb-3 px-3 py-2 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg">{error}</p>
      )}

      {events.length === 0 ? (
        <p className="text-xs text-slate-400">لا أحداث استخدامٍ بعد</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-200">
                <th className="text-right py-2 font-semibold">الشركة</th>
                <th className="text-right py-2 font-semibold">النوع</th>
                <th className="text-right py-2 font-semibold">المصدر</th>
                <th className="text-right py-2 font-semibold">البنود</th>
                <th className="text-right py-2 font-semibold">الوحدات</th>
                <th className="text-right py-2 font-semibold">الكتالوج</th>
                <th className="text-right py-2 font-semibold">الموظف</th>
                <th className="text-right py-2 font-semibold">الاعتماد</th>
                <th className="text-right py-2 font-semibold" />
              </tr>
            </thead>
            <tbody>
              {events.map((e) => {
                const isReversal = e.event_type === "reversal";
                const alreadyReversed = reversedIds.has(e.id);
                return (
                  <tr key={e.id} className="border-b border-slate-100">
                    <td className="py-2 text-slate-700">{e.company_name}</td>
                    <td className="py-2">
                      <span
                        className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                          isReversal ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"
                        }`}
                      >
                        {e.event_type_display}
                      </span>
                    </td>
                    <td className="py-2 text-slate-600">
                      {e.source_type_display} #{formatNumber(e.source_id)}
                    </td>
                    <td className="py-2 text-slate-600">
                      {formatNumber(e.line_count_snapshot)}
                      {/* مصدرُ العدد هو مادّةُ الاعتراض: مرصودٌ من المستند أم مُصرَّحٌ به. */}
                      <span
                        className={`mr-1 text-[10px] ${
                          e.line_count_source === "observed" ? "text-emerald-600" : "text-amber-600"
                        }`}
                      >
                        ({e.line_count_source_display})
                      </span>
                    </td>
                    <td className="py-2 font-semibold text-slate-800">{formatNumber(e.units)}</td>
                    <td className="py-2 text-slate-500">v{formatNumber(e.catalog_version)}</td>
                    <td className="py-2 text-slate-600">{e.employee_name || "—"}</td>
                    <td className="py-2 text-slate-500">{formatDateTimeValue(e.approved_at) || "—"}</td>
                    <td className="py-2 text-left">
                      {!isReversal && !alreadyReversed && reversingId !== e.id && (
                        <button
                          type="button"
                          onClick={() => {
                            setReversingId(e.id);
                            setReversalReason("");
                          }}
                          className="px-2 py-1 text-[10px] font-semibold text-white bg-red-600 hover:bg-red-700 rounded-md"
                        >
                          عكس
                        </button>
                      )}
                      {reversingId === e.id && (
                        <div className="flex items-center gap-1 justify-end">
                          <input
                            type="text"
                            value={reversalReason}
                            onChange={(ev) => setReversalReason(ev.target.value)}
                            placeholder="سبب العكس (إلزاميّ)"
                            className="w-48 px-2 py-1 text-[10px] border border-slate-200 rounded-md"
                          />
                          <button
                            type="button"
                            onClick={() => void handleReverse(e)}
                            disabled={busyReverse === e.id || !reversalReason.trim()}
                            className="px-2 py-1 text-[10px] font-semibold text-white bg-red-600 hover:bg-red-700 rounded-md disabled:opacity-50"
                          >
                            تأكيد
                          </button>
                          <button
                            type="button"
                            onClick={() => setReversingId(null)}
                            className="px-2 py-1 text-[10px] font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-md"
                          >
                            إلغاء
                          </button>
                        </div>
                      )}
                      {alreadyReversed && <span className="text-[10px] text-slate-400">معكوس</span>}
                      {isReversal && e.reason && (
                        <span className="text-[10px] text-slate-400">{e.reason}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
