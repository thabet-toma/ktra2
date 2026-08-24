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
 * T-WIN: المظهر انتقل إلى كلاسات المنتقي المشتركة — كان أنماطاً inline
 * بـ zIndex 9999 وألواناً ثابتة لا ترى الجلد ولا الوضع الداكن.
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
    <div
      className="aseel-picker-mask aseel-picker-mask--end"
      dir="rtl"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="aseel-picker aseel-sidepanel"
        style={{ "--sidepanel-w": `${width}px` } as React.CSSProperties}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="aseel-picker-head">
          <span>{title}</span>
          <button type="button" className="aseel-toolbtn" onClick={onClose} aria-label="إغلاق">
            <X size={16} />
          </button>
        </div>
        <div className="aseel-picker-body aseel-sidepanel__body">
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}
