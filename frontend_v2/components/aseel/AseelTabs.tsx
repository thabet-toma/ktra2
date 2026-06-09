import React, { useState } from "react";

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
  const [localTab, setLocalTab] = useState(0);
  const activeIdx =
    activeTab != null
      ? tabs.findIndex((t) => t.key === activeTab)
      : localTab;
  const effectiveIdx = activeIdx >= 0 ? activeIdx : 0;
  const tab = tabs[effectiveIdx];

  return (
    <div className="aseel-tabscol">
      <div className="aseel-tabs" role="tablist">
        {tabs.map((t, i) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={i === effectiveIdx}
            className={`aseel-tab${i === effectiveIdx ? " aseel-tab--active" : ""}`}
            onClick={() => {
              if (activeTab != null) {
                onTabChange?.(t.key);
              } else {
                setLocalTab(i);
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
