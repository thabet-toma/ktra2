import React, { useState } from "react";
import { resolveActiveTabKey } from "../../utils/tabSelection";

export interface AseelTabItem {
  key: string;
  label: string;
  content: React.ReactNode;
}

export interface AseelTabsProps {
  tabs: AseelTabItem[];
  activeTab?: string;
  onTabChange?: (key: string) => void;
}

export const AseelTabs: React.FC<AseelTabsProps> = ({
  tabs,
  activeTab,
  onTabChange,
}) => {
  // التتبّع بالمعرّف لا بالفهرس — تغيّر طول المصفوفة وقت التشغيل كان يقفز
  // بالمستخدم إلى تبويب آخر (utils/tabSelection.ts).
  const [pickedKey, setPickedKey] = useState<string | null>(null);
  const activeKey =
    activeTab != null
      ? resolveActiveTabKey(tabs, activeTab)
      : resolveActiveTabKey(tabs, pickedKey);
  const tab = tabs.find((t) => t.key === activeKey);

  return (
    <div className="aseel-tabscol">
      <div className="aseel-tabs" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={t.key === activeKey}
            className={`aseel-tab${t.key === activeKey ? " aseel-tab--active" : ""}`}
            onClick={() => {
              if (activeTab != null) {
                onTabChange?.(t.key);
              } else {
                setPickedKey(t.key);
              }
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="aseel-tabpanel" role="tabpanel">
        {tab?.content}
      </div>
    </div>
  );
};
