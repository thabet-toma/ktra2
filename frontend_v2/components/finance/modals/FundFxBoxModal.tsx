import React, { useCallback, useEffect, useState } from "react";
import { Loader2, X, Banknote, ArrowRightLeft } from "lucide-react";
import { accountingApi, type CashBoxLedgerLink } from "../../../services/accountingApi";

interface Props {
  isOpen: boolean;
  /** صندوق العملة الأجنبية (الدولار) المراد تمويله */
  ledger: CashBoxLedgerLink | null;
  /** صناديق الشيقل المتاحة كمصدر للتحويل */
  ilsBoxes: CashBoxLedgerLink[];
  onClose: () => void;
  /** بعد نجاح التمويل — لتحديث الأرصدة في القائمة */
  onFunded: () => void;
}

type FxLots = Awaited<ReturnType<typeof accountingApi.getFxBoxLots>>;

const today = () => new Date().toISOString().slice(0, 10);

export const FundFxBoxModal: React.FC<Props> = ({ isOpen, ledger, ilsBoxes, onClose, onFunded }) => {
  const [mode, setMode] = useState<"capital" | "transfer">("capital");
  const [amount, setAmount] = useState("");
  const [rate, setRate] = useState("");
  const [date, setDate] = useState(today());
  const [ilsBoxId, setIlsBoxId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lots, setLots] = useState<FxLots | null>(null);

  const loadLots = useCallback(async () => {
    if (!ledger) return;
    try {
      setLots(await accountingApi.getFxBoxLots(ledger.id));
    } catch {
      setLots(null);
    }
  }, [ledger]);

  useEffect(() => {
    if (isOpen && ledger) {
      setMode("capital"); setAmount(""); setRate(""); setDate(today());
      setIlsBoxId(""); setError(null);
      void loadLots();
    }
  }, [isOpen, ledger, loadLots]);

  if (!isOpen || !ledger) return null;

  const ils = (Number(amount) || 0) * (Number(rate) || 0);

  const submit = async () => {
    setError(null);
    const amt = Number(amount), r = Number(rate);
    if (!(amt > 0) || !(r > 0)) { setError("المبلغ وسعر الصرف يجب أن يكونا موجبين."); return; }
    if (mode === "transfer" && !ilsBoxId) { setError("اختر صندوق الشيقل المصدر."); return; }
    setBusy(true);
    try {
      if (mode === "capital") {
        await accountingApi.fundFxBoxFromCapital(ledger.id, { amount, rate, date });
      } else {
        await accountingApi.transferIlsToFxBox(ledger.id, {
          ils_box_id: Number(ilsBoxId), amount, rate, date });
      }
      setAmount(""); setRate("");
      await loadLots();
      onFunded();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر التمويل");
    } finally {
      setBusy(false);
    }
  };

  const tab = (m: "capital" | "transfer", label: string, icon: React.ReactNode) => (
    <button
      type="button"
      onClick={() => setMode(m)}
      className={`flex items-center gap-1.5 px-3 py-2 text-sm font-semibold rounded-lg border ${
        mode === m
          ? "bg-blue-600 text-white border-blue-600"
          : "bg-[var(--color-surface-2)] text-[var(--color-text)] border-[var(--color-border)]"
      }`}
    >
      {icon}{label}
    </button>
  );

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4" dir="rtl">
      <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-gray-800 shadow-2xl p-6 max-h-[88vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-bold dark:text-white">
            تمويل {ledger.name} <span className="text-sm font-mono text-gray-500">({ledger.currency_code})</span>
          </h3>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700" aria-label="إغلاق">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* الرصيد الحالي */}
        {lots && (
          <div className="mb-4 p-3 rounded-lg bg-[var(--color-surface-2)] text-sm flex justify-between">
            <span>الرصيد: <strong>{lots.fc_balance}</strong> {ledger.currency_code}</span>
            <span>القيمة بالشيقل (FIFO): <strong>{lots.ils_value}</strong></span>
          </div>
        )}

        <div className="flex gap-2 mb-4">
          {tab("capital", "إيداع من رأس المال", <Banknote className="w-4 h-4" />)}
          {tab("transfer", "تحويل من صندوق الشيقل", <ArrowRightLeft className="w-4 h-4" />)}
        </div>

        {error && <div className="p-3 mb-3 text-xs bg-red-50 text-red-700 rounded-lg border border-red-200 font-semibold">{error}</div>}

        <div className="space-y-3">
          {mode === "transfer" && (
            <label className="block">
              <span className="text-xs font-bold opacity-80 block mb-1">صندوق الشيقل المصدر</span>
              <select className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]"
                value={ilsBoxId} onChange={(e) => setIlsBoxId(e.target.value)}>
                <option value="">— اختر —</option>
                {ilsBoxes.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.currency_code})</option>)}
              </select>
            </label>
          )}
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs font-bold opacity-80 block mb-1">المبلغ ({ledger.currency_code})</span>
              <input type="number" min="0" step="any" className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]"
                value={amount} onChange={(e) => setAmount(e.target.value)} />
            </label>
            <label className="block">
              <span className="text-xs font-bold opacity-80 block mb-1">سعر الصرف (شيقل/{ledger.currency_code})</span>
              <input type="number" min="0" step="any" className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]"
                value={rate} onChange={(e) => setRate(e.target.value)} />
            </label>
          </div>
          <label className="block">
            <span className="text-xs font-bold opacity-80 block mb-1">التاريخ</span>
            <input type="date" className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]"
              value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          {ils > 0 && (
            <p className="text-xs text-gray-500">القيمة بالشيقل: <strong>{ils.toLocaleString()}</strong> — تُضاف كطبقة FIFO جديدة.</p>
          )}
        </div>

        {/* الطبقات */}
        {lots && lots.lots.length > 0 && (
          <div className="mt-4">
            <h4 className="text-sm font-bold mb-2 dark:text-white">طبقات FIFO</h4>
            <table className="w-full text-xs border border-[var(--color-border)] rounded-lg overflow-hidden">
              <thead>
                <tr className="bg-[var(--color-surface-2)] text-right">
                  <th className="px-2 py-1.5">التاريخ</th>
                  <th className="px-2 py-1.5">المتبقّي</th>
                  <th className="px-2 py-1.5">السعر</th>
                  <th className="px-2 py-1.5">المصدر</th>
                </tr>
              </thead>
              <tbody>
                {lots.lots.map((l) => (
                  <tr key={l.id} className="border-t border-[var(--color-border)]">
                    <td className="px-2 py-1.5">{l.lot_date}</td>
                    <td className="px-2 py-1.5 font-mono">{l.remaining_fc} / {l.original_fc}</td>
                    <td className="px-2 py-1.5 font-mono">{l.rate}</td>
                    <td className="px-2 py-1.5">{l.source === "capital" ? "رأس المال" : "تحويل شيقل"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex justify-end gap-2 mt-5">
          <button type="button" onClick={onClose}
            className="px-4 py-2 text-sm font-semibold rounded-lg border border-[var(--color-border)]">إغلاق</button>
          <button type="button" onClick={() => void submit()} disabled={busy}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-bold text-white rounded-lg bg-blue-600 disabled:opacity-50">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Banknote className="w-4 h-4" />}
            تمويل
          </button>
        </div>
      </div>
    </div>
  );
};
