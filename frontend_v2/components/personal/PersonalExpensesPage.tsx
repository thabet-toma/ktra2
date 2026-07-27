/**
 * PersonalExpensesPage — «مصاريفي الشخصية».
 *
 * دفتر جيب خاص بالمستخدم وحده: لا يراه مدير الشركة ولا يظهر في أي تقرير مالي،
 * ولا علاقة له بشجرة الحسابات (لا حساب، لا قيد، لا ترحيل) — الخادم
 * `hr.PersonalExpenseViewSet` يفرض العزل بـ user=request.user.
 *
 * حالة الدفع «مدفوعة» مربع اختيار (لا قائمة نقدي/آجل) — نفس اصطلاح الفواتير.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Wallet, Plus, Trash2, RefreshCw, ChevronRight, ChevronLeft, Loader2, Pencil, X, Check,
} from "lucide-react";
import { formatMoney } from "../../utils/formatNumber";
import { formatDateLocalized, todayIso } from "../../utils/formatDate";
import {
  monthKeyOf, monthKeyLabel, shiftMonthKey, validateExpenseDraft,
} from "../../utils/personalExpenses";
import {
  listPersonalExpenses,
  fetchPersonalExpenseSummary,
  createPersonalExpense,
  updatePersonalExpense,
  deletePersonalExpense,
  PERSONAL_EXPENSE_CATEGORIES,
  type PersonalExpense,
  type PersonalExpenseCategory,
  type PersonalExpenseSummary,
} from "../../services/personalExpensesApi";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";

const EMPTY_DRAFT = {
  date: todayIso(),
  title: "",
  category: "other" as PersonalExpenseCategory,
  amount: "",
  is_paid: true,
  notes: "",
};

export const PersonalExpensesPage: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();

  const [month, setMonth] = useState(() => monthKeyOf(todayIso()));
  const [category, setCategory] = useState<PersonalExpenseCategory | "">("");
  const [paidFilter, setPaidFilter] = useState<"" | "true" | "false">("");

  const [rows, setRows] = useState<PersonalExpense[]>([]);
  const [summary, setSummary] = useState<PersonalExpenseSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [draft, setDraft] = useState({ ...EMPTY_DRAFT });
  const [editingId, setEditingId] = useState<number | null>(null);

  const filters = useMemo(
    () => ({ month, category, is_paid: paidFilter }),
    [month, category, paidFilter],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [list, sum] = await Promise.all([
        listPersonalExpenses(filters),
        fetchPersonalExpenseSummary(filters),
      ]);
      setRows(list);
      setSummary(sum);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "تعذر تحميل المصاريف");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  const resetDraft = () => {
    setDraft({ ...EMPTY_DRAFT, date: todayIso() });
    setEditingId(null);
  };

  const save = async () => {
    const invalid = validateExpenseDraft(draft);
    if (invalid) {
      setErr(invalid);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const payload = {
        date: draft.date,
        title: draft.title.trim(),
        category: draft.category,
        amount: String(Number(draft.amount)),
        is_paid: draft.is_paid,
        notes: draft.notes.trim(),
      };
      if (editingId) {
        await updatePersonalExpense(editingId, payload);
        toast("تم تعديل المصروف", "success");
      } else {
        await createPersonalExpense(payload);
        toast("تم تسجيل المصروف", "success");
      }
      resetDraft();
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "تعذر الحفظ");
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (row: PersonalExpense) => {
    setEditingId(row.id);
    setDraft({
      date: row.date,
      title: row.title,
      category: row.category,
      amount: row.amount,
      is_paid: row.is_paid,
      notes: row.notes || "",
    });
  };

  const togglePaid = async (row: PersonalExpense) => {
    setBusy(true);
    try {
      await updatePersonalExpense(row.id, { is_paid: !row.is_paid });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "تعذر التحديث");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (row: PersonalExpense) => {
    const ok = await confirm({
      title: "حذف مصروف",
      message: `سيُحذف «${row.title}» نهائياً من مصاريفك الشخصية.`,
      confirmText: "حذف",
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await deletePersonalExpense(row.id);
      if (editingId === row.id) resetDraft();
      toast("تم الحذف", "success");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "تعذر الحذف");
    } finally {
      setBusy(false);
    }
  };

  const maxCategoryTotal = Math.max(
    1,
    ...(summary?.by_category || []).map((c) => Number(c.total) || 0),
  );

  const inputClass =
    "h-10 px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] focus:ring-1 focus:ring-emerald-500 outline-none";

  return (
    <div dir="rtl" className="space-y-4 p-3 md:p-4">
      {/* الترويسة + متصفّح الشهور */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-lg font-bold text-[var(--color-text)]">
          <Wallet className="w-5 h-5 text-[var(--color-primary)]" />
          مصاريفي الشخصية
          <span className="text-[11px] font-normal text-[var(--color-text-muted)]">
            خاصة بك وحدك — لا تظهر لأحد ولا تدخل حسابات الشركة
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setMonth(shiftMonthKey(month, -1))}
            className="p-2 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
            title="الشهر السابق"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
          <span className="min-w-[9rem] text-center font-semibold text-[var(--color-text)]">
            {monthKeyLabel(month)}
          </span>
          <button
            onClick={() => setMonth(shiftMonthKey(month, 1))}
            className="p-2 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
            title="الشهر التالي"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            onClick={() => void load()}
            className="p-2 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
            title="تحديث"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {err && (
        <div className="p-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] text-sm text-red-600 dark:text-red-400">
          {err}
        </div>
      )}

      {/* مؤشرات الشهر */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "إجمالي الشهر", value: summary?.total, tone: "text-[var(--color-text)]" },
          { label: "مدفوعة", value: summary?.paid_total, tone: "text-emerald-600 dark:text-emerald-400" },
          { label: "غير مدفوعة", value: summary?.unpaid_total, tone: "text-amber-600 dark:text-amber-400" },
          { label: "عدد المصاريف", value: summary ? String(summary.count) : undefined, tone: "text-[var(--color-text)]", raw: true },
        ].map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
          >
            <div className="text-[11px] text-[var(--color-text-muted)]">{card.label}</div>
            <div className={`text-xl font-bold ${card.tone}`}>
              {card.value === undefined ? "—" : card.raw ? card.value : formatMoney(card.value)}
            </div>
          </div>
        ))}
      </div>

      {/* نموذج التسجيل/التعديل */}
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 space-y-3">
        <div className="text-sm font-bold text-[var(--color-text)]">
          {editingId ? "تعديل مصروف" : "تسجيل مصروف"}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[140px_1fr_170px_140px_auto] gap-2">
          <input
            type="date"
            className={inputClass}
            value={draft.date}
            onChange={(e) => setDraft({ ...draft, date: e.target.value })}
            title="التاريخ"
          />
          <input
            className={inputClass}
            placeholder="البيان (مثال: تعبئة وقود)"
            value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          />
          <select
            className={inputClass}
            value={draft.category}
            onChange={(e) => setDraft({ ...draft, category: e.target.value as PersonalExpenseCategory })}
            title="الفئة"
          >
            {PERSONAL_EXPENSE_CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
          <input
            className={inputClass}
            inputMode="decimal"
            placeholder="المبلغ"
            value={draft.amount}
            onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
          />
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-sm text-[var(--color-text)] cursor-pointer select-none">
              <input
                type="checkbox"
                className="w-4 h-4 accent-emerald-600"
                checked={draft.is_paid}
                onChange={(e) => setDraft({ ...draft, is_paid: e.target.checked })}
              />
              مدفوعة
            </label>
            <button
              onClick={() => void save()}
              disabled={busy}
              className="h-10 px-4 rounded-lg bg-[var(--color-primary)] text-[var(--color-primary-foreground)] font-semibold flex items-center gap-1.5 disabled:opacity-60"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              {editingId ? "حفظ" : "إضافة"}
            </button>
            {editingId && (
              <button
                onClick={resetDraft}
                className="h-10 px-3 rounded-lg border border-[var(--color-border)] text-[var(--color-text-muted)]"
                title="إلغاء التعديل"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
        <input
          className={`${inputClass} w-full`}
          placeholder="ملاحظات (اختياري)"
          value={draft.notes}
          onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
        {/* الجدول */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 p-2 border-b border-[var(--color-border)]">
            <select
              className={`${inputClass} h-9 text-sm`}
              value={category}
              onChange={(e) => setCategory(e.target.value as PersonalExpenseCategory | "")}
              title="تصفية بالفئة"
            >
              <option value="">كل الفئات</option>
              {PERSONAL_EXPENSE_CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
            <select
              className={`${inputClass} h-9 text-sm`}
              value={paidFilter}
              onChange={(e) => setPaidFilter(e.target.value as "" | "true" | "false")}
              title="تصفية بحالة الدفع"
            >
              <option value="">الكل</option>
              <option value="true">مدفوعة</option>
              <option value="false">غير مدفوعة</option>
            </select>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--color-surface-2)] text-[var(--color-text-muted)] text-xs">
                <tr>
                  <th className="p-2 text-right font-semibold">التاريخ</th>
                  <th className="p-2 text-right font-semibold">البيان</th>
                  <th className="p-2 text-right font-semibold">الفئة</th>
                  <th className="p-2 text-left font-semibold">المبلغ</th>
                  <th className="p-2 text-center font-semibold">مدفوعة</th>
                  <th className="p-2 text-center font-semibold">إجراءات</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.id}
                    className={`border-t border-[var(--color-border)] ${editingId === row.id ? "bg-[var(--color-surface-2)]" : ""}`}
                  >
                    <td className="p-2 text-[var(--color-text-muted)] whitespace-nowrap">
                      {formatDateLocalized(row.date)}
                    </td>
                    <td className="p-2 text-[var(--color-text)]">
                      {row.title}
                      {row.notes && (
                        <div className="text-[11px] text-[var(--color-text-muted)]">{row.notes}</div>
                      )}
                    </td>
                    <td className="p-2 text-[var(--color-text-muted)] whitespace-nowrap">
                      {row.category_label}
                    </td>
                    <td className="p-2 text-left font-bold text-[var(--color-text)] whitespace-nowrap">
                      {formatMoney(row.amount)}
                    </td>
                    <td className="p-2 text-center">
                      <input
                        type="checkbox"
                        className="w-4 h-4 accent-emerald-600"
                        checked={row.is_paid}
                        disabled={busy}
                        onChange={() => void togglePaid(row)}
                        title={row.is_paid ? "مدفوعة" : "غير مدفوعة"}
                      />
                    </td>
                    <td className="p-2">
                      <div className="flex items-center justify-center gap-1">
                        <button
                          onClick={() => startEdit(row)}
                          className="p-1.5 rounded text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
                          title="تعديل"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => void remove(row)}
                          className="p-1.5 rounded text-red-600 hover:bg-[var(--color-surface-2)]"
                          title="حذف"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!rows.length && !loading && (
                  <tr>
                    <td colSpan={6} className="p-6 text-center text-[var(--color-text-muted)]">
                      لا مصاريف في هذا الشهر — سجّل أول مصروف من الأعلى.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* توزيع الفئات */}
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 space-y-2">
          <div className="text-sm font-bold text-[var(--color-text)]">توزيع الفئات</div>
          {summary?.by_category.length ? (
            summary.by_category.map((c) => (
              <div key={c.category} className="space-y-1">
                <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
                  <span>{c.label}</span>
                  <span className="font-bold text-[var(--color-text)]">{formatMoney(c.total)}</span>
                </div>
                <div className="h-1.5 rounded bg-[var(--color-surface-3)] overflow-hidden">
                  <div
                    className="h-full bg-[var(--color-primary)]"
                    style={{ width: `${Math.round((Number(c.total) / maxCategoryTotal) * 100)}%` }}
                  />
                </div>
              </div>
            ))
          ) : (
            <div className="text-xs text-[var(--color-text-muted)]">لا بيانات لهذا الشهر.</div>
          )}
          <div className="pt-2 mt-1 border-t border-[var(--color-border)] flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)]">
            <Check className="w-3 h-3" />
            هذه الشاشة مستقلة عن المحاسبة — لا تُنشئ قيوداً ولا تمسّ شجرة الحسابات.
          </div>
        </div>
      </div>
    </div>
  );
};

export default PersonalExpensesPage;
