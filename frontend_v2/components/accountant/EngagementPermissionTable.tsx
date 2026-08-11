import React from 'react';
import type { AccountantPermissionEntry } from '../../types/accountant';

export const EngagementPermissionTable: React.FC<{
  permissions: AccountantPermissionEntry[];
  selected: string[];
  onChange: (selected: string[]) => void;
  disabled?: boolean;
}> = ({ permissions, selected, onChange, disabled = false }) => {
  const groups: Record<string, AccountantPermissionEntry[]> = {};
  for (const permission of permissions) {
    (groups[permission.group] ||= []).push(permission);
  }
  const selectedSet = new Set(selected);

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-700">
      {(Object.entries(groups) as [string, AccountantPermissionEntry[]][]).map(([group, entries]) => (
        <section key={group} className="border-b border-slate-200 last:border-b-0 dark:border-slate-700">
          <h3 className="bg-slate-50 px-4 py-3 font-black text-slate-800 dark:bg-slate-800 dark:text-white">{group}</h3>
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {entries.map((entry) => (
              <label key={entry.key} className="flex cursor-pointer items-center gap-3 px-4 py-3 text-sm text-slate-700 dark:text-slate-200">
                <input
                  type="checkbox"
                  checked={selectedSet.has(entry.key)}
                  disabled={disabled}
                  onChange={(event) => onChange(
                    event.target.checked
                      ? [...selected, entry.key]
                      : selected.filter((key) => key !== entry.key),
                  )}
                  className="h-5 w-5 rounded border-slate-300 text-blue-600"
                />
                <span className="flex-1">{entry.label}</span>
                <code className="hidden text-xs text-slate-400 sm:block">{entry.key}</code>
              </label>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
};
