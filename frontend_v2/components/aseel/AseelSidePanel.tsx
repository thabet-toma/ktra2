import React, { useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

export interface AseelSidePanelProps {
  open: boolean;
  onClose: () => void;
  title: string;
  width?: number;
  children: React.ReactNode;
}

/**
 * AseelSidePanel — right-sliding panel for browse/view (not decision modals).
 * Renders via portal to document.body.
 * Closes on ESC, click-outside mask, or X button.
 */
export function AseelSidePanel({ open, onClose, title, width = 380, children }: AseelSidePanelProps) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); onClose(); }
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [open, handleKeyDown]);

  if (!open) return null;

  return createPortal(
    <div style={{
      position: "fixed", inset: 0, zIndex: 9999,
      display: "flex", justifyContent: "flex-end",
      background: "rgba(0,0,0,0.15)",
      direction: "rtl",
    }} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        width, height: "100%",
        background: "var(--aseel-bg-panel, #fff)",
        borderLeft: "1px solid var(--aseel-border, #ddd)",
        display: "flex", flexDirection: "column",
        transform: open ? "translateX(0)" : "translateX(100%)",
        transition: "transform 0.2s ease",
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "8px 12px", borderBottom: "1px solid var(--aseel-border, #ddd)",
          fontSize: "var(--aseel-fs, 13px)", fontWeight: 600,
        }}>
          <span>{title}</span>
          <button type="button" onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", padding: 4 }}>
            <X size={16} />
          </button>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 8 }}>
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}
