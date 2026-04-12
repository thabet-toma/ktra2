import React, { useMemo, useState } from "react";

export const NoSqlMigrationBanner: React.FC<{ isManager: boolean }> = ({
  isManager,
}) => {
  const storageKey = "ktra_no_sql_migration_banner_dismissed_v1";
  const [dismissed, setDismissed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(storageKey) === "1";
    } catch {
      return false;
    }
  });

  const shouldShow = useMemo(() => isManager && !dismissed, [isManager, dismissed]);

  if (!shouldShow) return null;

  return (
    <div className="mx-3 sm:mx-6 mb-3">
      <div className="bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-700 rounded-xl p-3 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-800 dark:text-slate-100">
              العمل يتم عبر قاعدة SQL
            </div>
            <div className="text-xs text-slate-600 dark:text-slate-400 mt-1 leading-5">
              تجنّب إنشاء أو تعديل بيانات من واجهات NoSQL القديمة بعد الترحيل.
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              setDismissed(true);
              try {
                localStorage.setItem(storageKey, "1");
              } catch {
                // ignore
              }
            }}
            className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-gray-800 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs whitespace-nowrap"
          >
            فهمت
          </button>
        </div>
      </div>
    </div>
  );
};

