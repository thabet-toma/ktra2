import React, { useCallback, useEffect, useMemo, useState } from "react";
import { History, Search, ArrowRight, User as UserIcon, RefreshCw } from "lucide-react";
import { DocRefCell } from "@/components/shared/LedgerTable";
import { getActivityLog, getActivityUsers } from "@/services/activityService";
import type { ActivityLogEntry, ActivityRange, ActivityUserOption } from "@/types/activity";
import { formatNumber } from "@/utils/formatNumber";
import { formatDateValue } from "@/utils/formatDate";
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

/** المدى الزمني — الأسماء تُرسل كما هي إلى `?range=` عدا «مخصص». */
const RANGE_OPTIONS: { value: ActivityRange; label: string }[] = [
  { value: "today", label: "اليوم" },
  { value: "yesterday", label: "أمس" },
  { value: "week", label: "هذا الأسبوع" },
  { value: "month", label: "هذا الشهر" },
  { value: "quarter", label: "هذا الربع" },
  { value: "year", label: "هذه السنة" },
  { value: "all", label: "الكل" },
  { value: "custom", label: "مخصص" },
];

const selectCls =
  "px-2.5 py-1.5 text-sm rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]";

const chipCls = (active: boolean) =>
  `px-3 py-1 text-sm rounded-full border transition-colors ${
    active
      ? "bg-[var(--color-primary)] text-white border-[var(--color-primary)] font-semibold"
      : "ktra-border-soft ktra-text-soft hover:bg-[var(--color-surface-2)]"
  }`;

/** استعلام المدى: «مخصص» يرسل الحدّين، وما عداه يرسل الاسم الجاهز. */
function rangeQuery(range: ActivityRange, from: string, to: string) {
  if (range !== "custom") return { range };
  return { date_from: from || undefined, date_to: to || undefined };
}

/**
 * صفوف مجمَّعة بيومها، بترتيب ورودها (تنازلي زمنياً من الخادم).
 *
 * التجميع ضرورة لا زينة: المدى صار يمتدّ أسبوعاً أو سنة، وجدارُ صفوفٍ بلا فاصلٍ
 * يوميّ يُخفي متى وقع ماذا — وهو أوّل ما يُسأل عنه سجلّ التدقيق.
 */
function groupByDay(rows: ActivityLogEntry[]): { day: string; rows: ActivityLogEntry[] }[] {
  const groups: { day: string; rows: ActivityLogEntry[] }[] = [];
  for (const row of rows) {
    const day = (row.timestamp || "").slice(0, 10);
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.rows.push(row);
    else groups.push({ day, rows: [row] });
  }
  return groups;
}

/** تفصيل الصف: القائمة المبنيّة إن وُجدت، وإلا الوصف النصّي. */
const RowDetails: React.FC<{ row: ActivityLogEntry }> = ({ row }) =>
  row.metadata?.changes?.length ? (
    <ActivityChanges changes={row.metadata.changes} />
  ) : (
    <span className="ktra-text-soft">{row.description}</span>
  );

export const ActivityLogPage: React.FC = () => {
  const [range, setRange] = useState<ActivityRange>("today");
  const [dateFrom, setDateFrom] = useState<string>(todayLocal());
  const [dateTo, setDateTo] = useState<string>(todayLocal());
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
  const [drillRange, setDrillRange] = useState<ActivityRange>("today");
  const [drillRows, setDrillRows] = useState<ActivityLogEntry[]>([]);
  const [drillLoading, setDrillLoading] = useState(false);

  useEffect(() => {
    getActivityUsers().then(setUsers).catch(() => setUsers([]));
  }, []);

  const loadFeed = useCallback(() => {
    setLoading(true);
    setError(null);
    getActivityLog({
      ...rangeQuery(range, dateFrom, dateTo),
      user: userId || undefined,
      action: action || undefined,
      entity_type: entityType || undefined,
      search: search || undefined,
    })
      .then(setRows)
      .catch((e: any) => setError(e?.message === "403" ? "هذه الصفحة متاحة للمدير فقط." : "تعذّر تحميل السجل."))
      .finally(() => setLoading(false));
  }, [range, dateFrom, dateTo, userId, action, entityType, search]);

  useEffect(() => {
    const t = setTimeout(loadFeed, 250); // debounce للبحث
    return () => clearTimeout(t);
  }, [loadFeed]);

  const openDrill = useCallback((u: ActivityUserOption) => {
    setDrillUser(u);
    setDrillRange("today");
  }, []);

  useEffect(() => {
    if (!drillUser) return;
    let cancelled = false;
    setDrillLoading(true);
    getActivityLog({ user: drillUser.id, range: drillRange, include_views: true })
      .then((d) => { if (!cancelled) setDrillRows(d); })
      .catch(() => { if (!cancelled) setDrillRows([]); })
      .finally(() => { if (!cancelled) setDrillLoading(false); });
    return () => { cancelled = true; };
  }, [drillUser, drillRange]);

  const entityOptions = useMemo(
    () => [{ value: "", label: "كل المستندات" }, ...Object.entries(ENTITY_LABELS).map(([v, l]) => ({ value: v, label: l }))],
    [],
  );

  const dayGroups = useMemo(() => groupByDay(rows), [rows]);

  /* شريط المدى — مشترك بين الجدول العام ورحلة المستخدم. */
  const RangeChips: React.FC<{ value: ActivityRange; onChange: (r: ActivityRange) => void }> = ({ value, onChange }) => (
    <div className="flex flex-wrap items-center gap-1.5">
      {RANGE_OPTIONS.map((o) => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)} className={chipCls(value === o.value)}>
          {o.label}
        </button>
      ))}
    </div>
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
        <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-full bg-[var(--color-primary)] flex items-center justify-center text-white font-bold">
              {drillUser.name?.charAt(0)}
            </div>
            <div>
              <h2 className="text-lg font-bold text-[var(--color-text)]">{drillUser.name}</h2>
              <p className="text-xs ktra-text-soft">رحلة المستخدم — تشمل الفتح والعرض</p>
            </div>
          </div>
          <span className="text-xs ktra-text-soft">{formatNumber(drillRows.length)} حدثاً</span>
        </div>
        <div className="mb-4">
          <RangeChips
            value={drillRange === "custom" ? "today" : drillRange}
            onChange={(r) => setDrillRange(r === "custom" ? "today" : r)}
          />
        </div>

        {drillLoading ? (
          <div className="text-center py-10 ktra-text-soft">جارٍ التحميل…</div>
        ) : drillRows.length === 0 ? (
          <div className="text-center py-12 ktra-text-soft">
            <History className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>لا يوجد نشاط في هذا المدى</p>
          </div>
        ) : (
          groupByDay(drillRows).map((group) => (
            <section key={group.day} className="mb-5">
              <h3 className="text-xs font-bold ktra-text-soft mb-2">
                {formatDateValue(group.day) || group.day} — {formatNumber(group.rows.length)} حدثاً
              </h3>
              <ol className="relative border-r-2 ktra-border-soft pr-4 space-y-4">
                {group.rows.map((r) => {
                  const meta = actionMeta(r.action);
                  return (
                    <li key={r.id} className="relative">
                      <span className="absolute -right-[1.35rem] top-1 w-3 h-3 rounded-full bg-[var(--color-surface)] border-2 border-[var(--color-primary)]" />
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-xs px-2 py-0.5 rounded-full ${meta.badge}`}>{r.action_label || meta.label}</span>
                        <span className="text-sm ktra-text-soft">{entityLabel(r.entity_type)}</span>
                        {r.entity_label && (
                          <span className="text-sm font-medium text-[var(--color-text)]">
                            <DocRefCell referenceType={r.entity_type} referenceId={r.entity_id} label={r.entity_label} />
                          </span>
                        )}
                        <span className="text-xs ktra-text-soft mr-auto">{formatActivityTime(r.timestamp)}</span>
                      </div>
                      <div className="mt-0.5 text-sm"><RowDetails row={r} /></div>
                    </li>
                  );
                })}
              </ol>
            </section>
          ))
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

      {/* المدى الزمني */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <RangeChips value={range} onChange={setRange} />
        {range === "custom" && (
          <div className="flex items-center gap-1.5 text-sm">
            <span className="ktra-text-soft">من:</span>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className={selectCls} />
            <span className="ktra-text-soft">إلى:</span>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className={selectCls} />
          </div>
        )}
      </div>

      {/* شريط الفلاتر */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
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
        <span className="text-xs ktra-text-soft mr-auto">
          {formatNumber(rows.length)} حدثاً في {formatNumber(dayGroups.length)} يوم
        </span>
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
                dayGroups.map((group) => (
                  <React.Fragment key={group.day}>
                    <tr className="bg-[var(--color-surface-2)]">
                      <td colSpan={6} className="px-3 py-1.5 text-xs font-bold ktra-text-soft">
                        {formatDateValue(group.day) || group.day} — {formatNumber(group.rows.length)} حدثاً
                      </td>
                    </tr>
                    {group.rows.map((r) => {
                      const meta = actionMeta(r.action);
                      return (
                        <tr key={r.id} className="border-t ktra-border-soft hover:bg-[var(--color-surface-2)]/50 align-top">
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
                            {r.entity_label && (
                              <span className="font-medium text-[var(--color-text)]">
                                {" "}
                                <DocRefCell referenceType={r.entity_type} referenceId={r.entity_id} label={r.entity_label} />
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 max-w-lg"><RowDetails row={r} /></td>
                          <td className="px-3 py-2 whitespace-nowrap ktra-text-soft text-xs">{r.ip_address || "—"}</td>
                        </tr>
                      );
                    })}
                  </React.Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
