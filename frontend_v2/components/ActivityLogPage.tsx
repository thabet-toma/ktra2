import React, { useCallback, useEffect, useMemo, useState } from "react";
import { History, Search, ArrowRight, User as UserIcon, RefreshCw } from "lucide-react";
import { getActivityLog, getActivityUsers } from "@/services/activityService";
import type { ActivityLogEntry, ActivityUserOption } from "@/types/activity";
import { actionMeta, entityLabel, formatActivityTime, ENTITY_LABELS } from "./activity/activityMeta";
import { ActivityChanges } from "./activity/ActivityChanges";

/** تاريخ اليوم محلياً بصيغة YYYY-MM-DD (بدون انزياح UTC). */
function todayLocal(): string {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

const ACTION_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "كل الإجراءات" },
  { value: "create", label: "إنشاء" },
  { value: "update", label: "تعديل" },
  { value: "delete", label: "حذف" },
  { value: "post", label: "ترحيل" },
  { value: "unpost", label: "إلغاء ترحيل" },
  { value: "duplicate", label: "نسخ" },
  { value: "payment", label: "دفعة" },
  { value: "login", label: "تسجيل دخول" },
  { value: "logout", label: "تسجيل خروج" },
];

const selectCls =
  "px-2.5 py-1.5 text-sm rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]";

export const ActivityLogPage: React.FC = () => {
  const [date, setDate] = useState<string>(todayLocal());
  const [userId, setUserId] = useState<string>("");
  const [action, setAction] = useState<string>("");
  const [entityType, setEntityType] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [rows, setRows] = useState<ActivityLogEntry[]>([]);
  const [users, setUsers] = useState<ActivityUserOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Drill-down: نشاط مستخدم واحد بالتفصيل (يشمل العرض/الفتح).
  const [drillUser, setDrillUser] = useState<ActivityUserOption | null>(null);
  const [drillDate, setDrillDate] = useState<string>(todayLocal());
  const [drillRows, setDrillRows] = useState<ActivityLogEntry[]>([]);
  const [drillLoading, setDrillLoading] = useState(false);

  useEffect(() => {
    getActivityUsers().then(setUsers).catch(() => setUsers([]));
  }, []);

  const loadFeed = useCallback(() => {
    setLoading(true);
    setError(null);
    getActivityLog({
      date,
      user: userId || undefined,
      action: action || undefined,
      entity_type: entityType || undefined,
      search: search || undefined,
    })
      .then(setRows)
      .catch((e: any) => setError(e?.message === "403" ? "هذه الصفحة متاحة للمدير فقط." : "تعذّر تحميل السجل."))
      .finally(() => setLoading(false));
  }, [date, userId, action, entityType, search]);

  useEffect(() => {
    const t = setTimeout(loadFeed, 250); // debounce للبحث
    return () => clearTimeout(t);
  }, [loadFeed]);

  const openDrill = useCallback((u: ActivityUserOption) => {
    setDrillUser(u);
    setDrillDate(todayLocal());
  }, []);

  useEffect(() => {
    if (!drillUser) return;
    let cancelled = false;
    setDrillLoading(true);
    getActivityLog({ user: drillUser.id, date: drillDate, include_views: true })
      .then((d) => { if (!cancelled) setDrillRows(d); })
      .catch(() => { if (!cancelled) setDrillRows([]); })
      .finally(() => { if (!cancelled) setDrillLoading(false); });
    return () => { cancelled = true; };
  }, [drillUser, drillDate]);

  const entityOptions = useMemo(
    () => [{ value: "", label: "كل المستندات" }, ...Object.entries(ENTITY_LABELS).map(([v, l]) => ({ value: v, label: l }))],
    [],
  );

  if (drillUser) {
    return (
      <div className="p-4 md:p-6 max-w-4xl mx-auto" dir="rtl">
        <button
          onClick={() => setDrillUser(null)}
          className="flex items-center gap-1.5 text-sm text-[var(--color-primary)] hover:underline mb-4"
        >
          <ArrowRight className="w-4 h-4" /> رجوع لسجل الكل
        </button>
        <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-full bg-[var(--color-primary)] flex items-center justify-center text-white font-bold">
              {drillUser.name?.charAt(0)}
            </div>
            <div>
              <h2 className="text-lg font-bold text-[var(--color-text)]">{drillUser.name}</h2>
              <p className="text-xs ktra-text-soft">رحلة المستخدم — تشمل الفتح والعرض</p>
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <span className="ktra-text-soft">اليوم:</span>
            <input type="date" value={drillDate} onChange={(e) => setDrillDate(e.target.value)} className={selectCls} />
          </label>
        </div>

        {drillLoading ? (
          <div className="text-center py-10 ktra-text-soft">جارٍ التحميل…</div>
        ) : drillRows.length === 0 ? (
          <div className="text-center py-12 ktra-text-soft">
            <History className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>لا يوجد نشاط في هذا اليوم</p>
          </div>
        ) : (
          <ol className="relative border-r-2 ktra-border-soft pr-4 space-y-4">
            {drillRows.map((r) => {
              const meta = actionMeta(r.action);
              return (
                <li key={r.id} className="relative">
                  <span className="absolute -right-[1.35rem] top-1 w-3 h-3 rounded-full bg-[var(--color-surface)] border-2 border-[var(--color-primary)]" />
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${meta.badge}`}>{r.action_label || meta.label}</span>
                    <span className="text-sm ktra-text-soft">{entityLabel(r.entity_type)}</span>
                    {r.entity_label && <span className="text-sm font-medium text-[var(--color-text)]">{r.entity_label}</span>}
                    <span className="text-xs ktra-text-soft mr-auto">{formatActivityTime(r.timestamp)}</span>
                  </div>
                  {r.metadata?.changes?.length ? (
                    <div className="mt-1"><ActivityChanges changes={r.metadata.changes} /></div>
                  ) : (
                    r.description && <p className="text-sm ktra-text-soft mt-0.5">{r.description}</p>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6" dir="rtl">
      <div className="flex items-center gap-3 mb-5">
        <div className="p-2 rounded-lg bg-[var(--color-surface-2)]">
          <History className="w-6 h-6 text-[var(--color-primary)]" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-[var(--color-text)]">سجل النشاط</h1>
          <p className="text-sm ktra-text-soft">كل ما فعله المستخدمون — اضغط على مستخدم لرؤية رحلته التفصيلية</p>
        </div>
      </div>

      {/* شريط الفلاتر */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <label className="flex items-center gap-1.5 text-sm">
          <span className="ktra-text-soft">التاريخ:</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={selectCls} />
        </label>
        <select value={userId} onChange={(e) => setUserId(e.target.value)} className={selectCls}>
          <option value="">كل المستخدمين</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
        <select value={action} onChange={(e) => setAction(e.target.value)} className={selectCls}>
          {ACTION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select value={entityType} onChange={(e) => setEntityType(e.target.value)} className={selectCls}>
          {entityOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <div className="relative">
          <Search className="w-4 h-4 absolute right-2 top-1/2 -translate-y-1/2 ktra-text-soft" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="بحث…"
            className={`${selectCls} pr-8`}
          />
        </div>
        <button onClick={loadFeed} className="p-1.5 rounded-md hover:bg-[var(--color-surface-2)]" title="تحديث">
          <RefreshCw className={`w-4 h-4 ktra-text-soft ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error ? (
        <div className="text-center py-12 text-red-600">{error}</div>
      ) : (
        <div className="overflow-x-auto rounded-lg border ktra-border-soft">
          <table className="w-full text-sm">
            <thead className="bg-[var(--color-surface-2)] text-[var(--color-text-muted)]">
              <tr>
                <th className="text-right font-semibold px-3 py-2 whitespace-nowrap">الوقت</th>
                <th className="text-right font-semibold px-3 py-2">المستخدم</th>
                <th className="text-right font-semibold px-3 py-2">الإجراء</th>
                <th className="text-right font-semibold px-3 py-2">المستند</th>
                <th className="text-right font-semibold px-3 py-2">التفاصيل</th>
                <th className="text-right font-semibold px-3 py-2 whitespace-nowrap">IP</th>
              </tr>
            </thead>
            <tbody>
              {loading && rows.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-10 ktra-text-soft">جارٍ التحميل…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-12 ktra-text-soft">
                  <History className="w-10 h-10 mx-auto mb-2 opacity-50" />لا يوجد نشاط بهذه الفلاتر
                </td></tr>
              ) : (
                rows.map((r) => {
                  const meta = actionMeta(r.action);
                  return (
                    <tr key={r.id} className="border-t ktra-border-soft hover:bg-[var(--color-surface-2)]/50">
                      <td className="px-3 py-2 whitespace-nowrap ktra-text-soft">{formatActivityTime(r.timestamp)}</td>
                      <td className="px-3 py-2">
                        {r.user ? (
                          <button
                            onClick={() => openDrill({ id: r.user!, name: r.user_name })}
                            className="flex items-center gap-1.5 text-[var(--color-primary)] hover:underline font-medium"
                          >
                            <UserIcon className="w-3.5 h-3.5" />{r.user_name}
                          </button>
                        ) : <span className="ktra-text-soft">{r.user_name}</span>}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${meta.badge}`}>
                          {r.action_label || meta.label}
                        </span>
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className="ktra-text-soft">{entityLabel(r.entity_type)}</span>
                        {r.entity_label && <span className="font-medium text-[var(--color-text)]"> {r.entity_label}</span>}
                      </td>
                      <td className="px-3 py-2 ktra-text-soft max-w-lg">
                        {r.metadata?.changes?.length ? (
                          <ActivityChanges changes={r.metadata.changes} />
                        ) : (
                          r.description
                        )}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap ktra-text-soft text-xs">{r.ip_address || "—"}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
