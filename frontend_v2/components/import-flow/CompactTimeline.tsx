import React from "react";

type StepStatus = "done" | "current" | "pending";

interface TimelineStep {
  key: string;
  label: string;
  status: StepStatus;
  onClick?: () => void;
}

interface CompactTimelineProps {
  steps: TimelineStep[];
}

const DOT: Record<StepStatus, string> = { done: "●", current: "◐", pending: "○" };

export function CompactTimeline({ steps }: CompactTimelineProps) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 4, height: 32,
      padding: "0 8px", background: "var(--ktra-bg-strip, #f5f5f5)",
      borderRadius: "var(--ktra-radius, 4px)", fontSize: "var(--ktra-fs-sm, 12px)",
      overflowX: "auto", whiteSpace: "nowrap", direction: "ltr",
    }}>
      {steps.map((s, i) => (
        <React.Fragment key={s.key}>
          <span
            onClick={s.onClick}
            style={{
              cursor: s.onClick ? "pointer" : "default",
              opacity: s.status === "pending" ? 0.45 : 1,
              fontWeight: s.status === "current" ? 600 : 400,
              display: "inline-flex", alignItems: "center", gap: 2,
            }}
          >
            <span style={{ fontSize: 14 }}>{DOT[s.status]}</span>
            <span>{s.label}</span>
          </span>
          {i < steps.length - 1 && <span style={{ color: "#999", margin: "0 2px" }}>→</span>}
        </React.Fragment>
      ))}
    </div>
  );
}
