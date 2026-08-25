import React, { useState } from "react";
import { resolveActiveTabKey } from "../../utils/tabSelection";

export interface KitTabItem {
  key: string;
  label: string;
  content: React.ReactNode;
}

export interface KitTabsProps {
  tabs: KitTabItem[];
  activeTab?: string;
  onTabChange?: (key: string) => void;
}

export const KitTabs: React.FC<KitTabsProps> = ({
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
    <div className="ktra-tabscol">
      <div className="ktra-tabs" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={t.key === activeKey}
            className={`ktra-tab${t.key === activeKey ? " ktra-tab--active" : ""}`}
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
      <div className="ktra-tabpanel" role="tabpanel">
        {tab?.content}
      </div>
    </div>
  );
};
