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
      <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-900/30 rounded-xl p-3 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-bold text-amber-900 dark:text-amber-200">
              تنبيه: NoSQL متوقف بعد الترحيل إلى SQL
            </div>
            <div className="text-xs text-amber-900/80 dark:text-amber-200/80 mt-1 leading-5">
              بعد تحويل البيانات إلى الجداول SQL، الرجاء استخدام صفحات SQL فقط.
              لا تعتمد على صفحات Firebase/NoSQL القديمة لإنشاء أو تعديل البيانات.
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
            className="px-3 py-1.5 rounded-lg border border-amber-200 dark:border-amber-900/30 bg-white dark:bg-gray-800 text-amber-900 dark:text-amber-200 hover:bg-amber-100 dark:hover:bg-amber-900/20 text-xs whitespace-nowrap"
          >
            فهمت
          </button>
        </div>
      </div>
    </div>
  );
};

