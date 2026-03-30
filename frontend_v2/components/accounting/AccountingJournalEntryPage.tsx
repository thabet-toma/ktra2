import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type {
  AccountingAccount,
  AccountingPartner,
  CostCenterDto,
} from "../../types/accounting";
import {
  ArrowRight,
  Plus,
  Trash2,
  Save,
  CheckCircle,
  Loader2,
} from "lucide-react";

type LineState = {
  id?: number;
  accountId: string;
  partnerId: string;
  costCenterId: string;
  debit: string;
  credit: string;
};

const emptyLine = (): LineState => ({
  accountId: "",
  partnerId: "",
  costCenterId: "",
  debit: "",
  credit: "",
});

interface Props {
  journalId: number | null;
  onBack: () => void;
}

export const AccountingJournalEntryPage: React.FC<Props> = ({
  journalId,
  onBack,
}) => {
  const [accounts, setAccounts] = useState<AccountingAccount[]>([]);
  const [partners, setPartners] = useState<AccountingPartner[]>([]);
  const [costCenters, setCostCenters] = useState<CostCenterDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [posted, setPosted] = useState(false);

  const [header, setHeader] = useState({
    transaction_date: new Date().toISOString().split("T")[0],
    description: "",
    reference_type: "",
    reference_id: "",
  });

  const [lines, setLines] = useState<LineState[]>([
    emptyLine(),
    emptyLine(),
    emptyLine(),
  ]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [acc, part, cc] = await Promise.all([
        accountingApi.getAccounts(),
        accountingApi.getPartners().catch(() => []),
        accountingApi.getCostCenters().catch(() => []),
      ]);
      const accList = (acc as AccountingAccount[]).filter((a) => a.is_active);
      setAccounts(accList);
      setPartners(part as AccountingPartner[]);
      setCostCenters(cc as CostCenterDto[]);

      if (journalId != null) {
        const j = await accountingApi.getJournal(journalId);
        setPosted(!!j.is_posted);
        setHeader({
          transaction_date: j.transaction_date || "",
          description: j.description || "",
          reference_type: j.reference_type || "",
          reference_id: j.reference_id != null ? String(j.reference_id) : "",
        });
        const mapped: LineState[] = (j.lines || []).map(
          (line: {
            id?: number;
            account: number;
            debit: string;
            credit: string;
            partner?: number | null;
            cost_center?: number | null;
          }) => ({
            id: line.id,
            accountId: String(line.account),
            partnerId: line.partner != null ? String(line.partner) : "",
            costCenterId:
              line.cost_center != null ? String(line.cost_center) : "",
            debit:
              parseFloat(String(line.debit)) > 0
                ? String(line.debit)
                : "",
            credit:
              parseFloat(String(line.credit)) > 0
                ? String(line.credit)
                : "",
          })
        );
        while (mapped.length < 3) mapped.push(emptyLine());
        setLines(mapped);
      } else {
        setPosted(false);
        setLines([emptyLine(), emptyLine(), emptyLine()]);
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, [journalId]);

  useEffect(() => {
    load();
  }, [load]);

  const updateLine = (i: number, patch: Partial<LineState>) => {
    if (posted) return;
    setLines((prev) => {
      const next = [...prev];
      const row = { ...next[i], ...patch };
      if (patch.debit && parseFloat(patch.debit) > 0) row.credit = "";
      if (patch.credit && parseFloat(patch.credit) > 0) row.debit = "";
      next[i] = row;
      if (i === next.length - 1 && (row.accountId || row.debit || row.credit)) {
        next.push(emptyLine());
      }
      return next;
    });
  };

  const removeLine = (i: number) => {
    if (posted) return;
    setLines((prev) => {
      const next = prev.filter((_, idx) => idx !== i);
      return next.length ? next : [emptyLine()];
    });
  };

  const totalDebit = lines.reduce(
    (s, l) => s + (parseFloat(l.debit) || 0),
    0
  );
  const totalCredit = lines.reduce(
    (s, l) => s + (parseFloat(l.credit) || 0),
    0
  );
  const diff = totalDebit - totalCredit;
  const balanced = Math.abs(diff) < 0.005 && totalDebit > 0;

  const validate = (): string | null => {
    if (!header.transaction_date) return "التاريخ مطلوب";
    if (!header.description.trim()) return "البيان مطلوب";
    const active = lines.filter(
      (l) =>
        l.accountId &&
        (parseFloat(l.debit) > 0 || parseFloat(l.credit) > 0)
    );
    if (active.length < 2) return "يجب طرفان على الأقل بمبالغ";
    if (!balanced) return `القيد غير متوازن (فرق ${diff.toFixed(2)})`;
    return null;
  };

  const buildPayload = () => {
    const active = lines.filter(
      (l) =>
        l.accountId &&
        (parseFloat(l.debit) > 0 || parseFloat(l.credit) > 0)
    );
    return {
      transaction_date: header.transaction_date,
      description: header.description.trim(),
      reference_type: header.reference_type.trim() || null,
      reference_id: header.reference_id.trim()
        ? parseInt(header.reference_id, 10)
        : null,
      is_posted: false,
      lines: active.map((l) => {
        const line: Record<string, unknown> = {
          account: parseInt(l.accountId, 10),
          debit: parseFloat(l.debit) || 0,
          credit: parseFloat(l.credit) || 0,
          partner: l.partnerId ? parseInt(l.partnerId, 10) : null,
          cost_center: l.costCenterId ? parseInt(l.costCenterId, 10) : null,
        };
        if (l.id) line.id = l.id;
        return line;
      }),
    };
  };

  const saveOnly = async () => {
    const v = validate();
    if (v) {
      setErr(v);
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      const payload = buildPayload();
      if (journalId != null) {
        await accountingApi.updateJournal(journalId, payload);
      } else {
        await accountingApi.createJournal(payload);
      }
      onBack();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setSaving(false);
    }
  };

  const saveAndPost = async () => {
    const v = validate();
    if (v) {
      setErr(v);
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      const payload = buildPayload();
      let id = journalId;
      if (id != null) {
        await accountingApi.updateJournal(id, payload);
      } else {
        const created = await accountingApi.createJournal(payload);
        id = created.id;
      }
      if (id != null) await accountingApi.postJournal(id);
      onBack();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ أو الترحيل");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="py-20 text-center text-gray-500">جاري التحميل…</div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400"
        >
          <ArrowRight className="w-4 h-4" />
          العودة لدفتر اليومية
        </button>
        {posted && (
          <span className="text-emerald-600 text-sm font-medium">
            هذا القيد مرحّل — للقراءة فقط
          </span>
        )}
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm">
          {err}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
        <div>
          <label className="block text-xs text-gray-500 mb-1">التاريخ</label>
          <input
            type="date"
            disabled={posted}
            className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600 disabled:opacity-60"
            value={header.transaction_date}
            onChange={(e) =>
              setHeader((h) => ({ ...h, transaction_date: e.target.value }))
            }
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">مرجع</label>
          <div className="flex gap-2">
            <input
              disabled={posted}
              placeholder="نوع"
              className="flex-1 border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600 disabled:opacity-60"
              value={header.reference_type}
              onChange={(e) =>
                setHeader((h) => ({ ...h, reference_type: e.target.value }))
              }
            />
            <input
              disabled={posted}
              placeholder="رقم"
              className="w-24 border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600 disabled:opacity-60"
              value={header.reference_id}
              onChange={(e) =>
                setHeader((h) => ({ ...h, reference_id: e.target.value }))
              }
            />
          </div>
        </div>
        <div className="md:col-span-2">
          <label className="block text-xs text-gray-500 mb-1">البيان</label>
          <textarea
            disabled={posted}
            rows={2}
            className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600 disabled:opacity-60"
            value={header.description}
            onChange={(e) =>
              setHeader((h) => ({ ...h, description: e.target.value }))
            }
          />
        </div>
      </div>

      <div className="overflow-x-auto bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-900/50">
            <tr>
              <th className="text-right p-2">حساب</th>
              <th className="text-right p-2 hidden lg:table-cell">شريك</th>
              <th className="text-right p-2 hidden xl:table-cell">مركز تكلفة</th>
              <th className="text-right p-2 w-28">مدين</th>
              <th className="text-right p-2 w-28">دائن</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {lines.map((line, i) => (
              <tr key={i} className="border-t border-gray-100 dark:border-gray-700">
                <td className="p-2">
                  <select
                    disabled={posted}
                    className="w-full max-w-[220px] border rounded-lg px-2 py-1.5 dark:bg-gray-900 dark:border-gray-600 text-xs"
                    value={line.accountId}
                    onChange={(e) =>
                      updateLine(i, { accountId: e.target.value })
                    }
                  >
                    <option value="">— حساب —</option>
                    {accounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.code} — {a.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="p-2 hidden lg:table-cell">
                  <select
                    disabled={posted}
                    className="w-full max-w-[160px] border rounded-lg px-2 py-1.5 dark:bg-gray-900 dark:border-gray-600 text-xs"
                    value={line.partnerId}
                    onChange={(e) =>
                      updateLine(i, { partnerId: e.target.value })
                    }
                  >
                    <option value="">—</option>
                    {partners.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="p-2 hidden xl:table-cell">
                  <select
                    disabled={posted}
                    className="w-full max-w-[140px] border rounded-lg px-2 py-1.5 dark:bg-gray-900 dark:border-gray-600 text-xs"
                    value={line.costCenterId}
                    onChange={(e) =>
                      updateLine(i, { costCenterId: e.target.value })
                    }
                  >
                    <option value="">—</option>
                    {costCenters.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="p-2">
                  <input
                    disabled={posted}
                    type="number"
                    step="0.01"
                    className="w-full border rounded-lg px-2 py-1.5 dark:bg-gray-900 dark:border-gray-600"
                    value={line.debit}
                    onChange={(e) =>
                      updateLine(i, { debit: e.target.value })
                    }
                  />
                </td>
                <td className="p-2">
                  <input
                    disabled={posted}
                    type="number"
                    step="0.01"
                    className="w-full border rounded-lg px-2 py-1.5 dark:bg-gray-900 dark:border-gray-600"
                    value={line.credit}
                    onChange={(e) =>
                      updateLine(i, { credit: e.target.value })
                    }
                  />
                </td>
                <td className="p-2">
                  {!posted && (
                    <button
                      type="button"
                      onClick={() => removeLine(i)}
                      className="p-1 text-red-600 hover:bg-red-50 rounded"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-gray-50 dark:bg-gray-900/30 font-medium">
            <tr>
              <td colSpan={3} className="p-3 text-left">
                {!balanced && totalDebit + totalCredit > 0 && (
                  <span className="text-amber-600 text-xs">
                    الفرق: {diff.toFixed(2)}
                  </span>
                )}
              </td>
              <td className="p-3">{totalDebit.toFixed(2)}</td>
              <td className="p-3">{totalCredit.toFixed(2)}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>

      {!posted && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() =>
              setLines((prev) => [...prev, emptyLine()])
            }
            className="flex items-center gap-2 px-4 py-2 border rounded-lg dark:border-gray-600 text-sm"
          >
            <Plus className="w-4 h-4" />
            سطر
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={saveOnly}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            حفظ
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={saveAndPost}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <CheckCircle className="w-4 h-4" />
            )}
            حفظ وترحيل
          </button>
        </div>
      )}
    </div>
  );
};
