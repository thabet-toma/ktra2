/**
 * بنود المخلّص في إعدادات الشراء — البند المتكرّر يُضاف هنا باسمه وحسابه بدل «أخرى».
 * سطر التخليص يحمل البند إلى قيد الاستحقاق (`LogisticsClearanceLine.item_type`).
 */
import React, { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { AccountTreeField } from "../accounting/AccountTreePicker";
import {
  deleteClearanceItemType,
  listClearanceItemTypes,
  saveClearanceItemType,
  type ClearanceItemType,
} from "../../services/clearanceApi";
import { useToast } from "../../contexts/ToastContext";

type AccountOpt = { id: number; code?: string | null; name?: string | null; parent?: number | null; account_type?: string | null; is_active?: boolean };

export const ClearanceItemTypesSection: React.FC<{ accounts: AccountOpt[]; disabled?: boolean }> = ({ accounts, disabled }) => {
  const toast = useToast();
  const [rows, setRows] = useState<ClearanceItemType[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | "new" | null>(null);
  const [newName, setNewName] = useState("");
  const [newAccount, setNewAccount] = useState<number | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await listClearanceItemTypes());
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { void reload(); }, [reload]);

  const save = async (row: Partial<ClearanceItemType> & { name: string }, key: number | "new") => {
    setBusyId(key);
    try {
      await saveClearanceItemType(row);
      if (key === "new") { setNewName(""); setNewAccount(null); }
      await reload();
      toast("حُفظ بند المخلّص.", "success");
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (row: ClearanceItemType) => {
    setBusyId(row.id);
    try {
      await deleteClearanceItemType(row.id);
      await reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setBusyId(null);
    }
  };

  const locked = disabled || loading;

  return (
    <div className="mt-6">
      <h3 className="font-bold mb-1 text-[var(--ktra-ink)]">بنود المخلّص</h3>
      <p className="text-sm text-[var(--ktra-ink-soft)] mb-3">
        البنود التي تظهر في تخليص الشحنة، ولكلٍّ حسابُ مدينه في قيد الاستحقاق. البند المتكرّر
        أضِفه هنا بدل «أخرى». الحساب الفارغ يأخذ الحساب الافتراضي لنوع البند.
      </p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-[var(--ktra-ink-soft)]">
            <th className="p-1 text-start">البند</th>
            <th className="p-1 text-start">الحساب</th>
            <th className="w-20 p-1 text-center">فعّال</th>
            <th className="w-12 p-1" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-[var(--ktra-line)]">
              <td className="p-1">
                <input
                  className="ktra-input w-full"
                  disabled={locked || busyId === row.id}
                  defaultValue={row.name}
                  onBlur={(e) => {
                    const name = e.target.value.trim();
                    if (name && name !== row.name) void save({ id: row.id, name }, row.id);
                  }}
                />
              </td>
              <td className="p-1">
                <AccountTreeField
                  accounts={accounts}
                  value={row.account}
                  onChange={(id) => void save({ id: row.id, name: row.name, account: id }, row.id)}
                  purpose={["expense", "asset"]}
                  disabled={locked || busyId === row.id}
                  placeholder="— افتراضي النوع —"
                  title="حساب بند المخلّص"
                />
              </td>
              <td className="p-1 text-center">
                <input
                  type="checkbox"
                  disabled={locked || busyId === row.id}
                  checked={row.is_active}
                  onChange={(e) => void save({ id: row.id, name: row.name, is_active: e.target.checked }, row.id)}
                />
              </td>
              <td className="p-1 text-center">
                <button
                  type="button"
                  className="ktra-toolbtn ktra-toolbtn--danger"
                  disabled={locked || busyId === row.id}
                  title="حذف البند — التخليصات القائمة تحتفظ بحسابها"
                  onClick={() => void remove(row)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </td>
            </tr>
          ))}
          <tr className="border-t border-[var(--ktra-line)]">
            <td className="p-1">
              <input
                className="ktra-input w-full"
                disabled={locked}
                placeholder="بند جديد، مثلاً: رسوم الميناء"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
            </td>
            <td className="p-1">
              <AccountTreeField
                accounts={accounts}
                value={newAccount}
                onChange={(id) => setNewAccount(id)}
                purpose={["expense", "asset"]}
                disabled={locked}
                placeholder="— افتراضي النوع —"
                title="حساب البند الجديد"
              />
            </td>
            <td className="p-1" />
            <td className="p-1 text-center">
              <button
                type="button"
                className="ktra-toolbtn"
                disabled={locked || !newName.trim() || busyId === "new"}
                title="إضافة البند"
                onClick={() => void save({ name: newName.trim(), account: newAccount }, "new")}
              >
                {busyId === "new" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
};

export default ClearanceItemTypesSection;
