import React, { useCallback, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useDragResize } from "../../hooks/useDragResize.ts";
import type { ResizeDir } from "../../utils/windowGeometry.ts";

/**
 * T-WIN — النافذة العائمة الموحّدة: تُسحب من شريط عنوانها وتُحجَّم من حوافها
 * الأربع وزواياها الأربع، وتعود حيث تركها المستخدم.
 *
 * موضعها من النظام: المحتوى **الثانوي** (كرت صنف، معاينة ملف، حاسبة). المستند
 * الرئيسي يبقى ملء الشاشة كما في Odoo/Zoho — لا MDI حر.
 *
 * على الجوال (<768px) تصير لوحاً ملء الشاشة بلا سحب ولا تحجيم، والهندسة
 * المحفوظة تُتجاهل (القواعد في `styles/index.css` قسم T-WIN).
 */

/** الحواف الثمانية: اسم المقبض ← اتجاه التحجيم. */
const GRIPS: Array<{ key: string; dir: ResizeDir }> = [
  { key: "n", dir: { dx: 0, dy: -1 } },
  { key: "s", dir: { dx: 0, dy: 1 } },
  { key: "w", dir: { dx: -1, dy: 0 } },
  { key: "e", dir: { dx: 1, dy: 0 } },
  { key: "nw", dir: { dx: -1, dy: -1 } },
  { key: "ne", dir: { dx: 1, dy: -1 } },
  { key: "sw", dir: { dx: -1, dy: 1 } },
  { key: "se", dir: { dx: 1, dy: 1 } },
];

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export interface KitFloatWindowProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  /** اسم الحفظ (`ktra:win:<name>`). اتركه فارغاً لنافذة لا تُحفظ هندستها. */
  name?: string;
  defaultWidth?: number;
  defaultHeight?: number;
  /** حاجبة: تُظلم ما خلفها وتُغلق بالنقر خارجها. غير الحاجبة تترك العمل مرئياً. */
  modal?: boolean;
  /** أزرار تُعرض في شريط العنوان يسار زر الإغلاق. */
  barExtras?: React.ReactNode;
  /** شريط سفلي مثبَّت — لا ينزلق مع المحتوى (أزرار القرار مكانها هنا). */
  footer?: React.ReactNode;
  /** يُمرَّر إلى جذر النافذة — يستعمله المهاجَرون للاحتفاظ بعلاماتهم القديمة. */
  rootProps?: React.HTMLAttributes<HTMLDivElement>;
  children: React.ReactNode;
}

export const KitFloatWindow: React.FC<KitFloatWindowProps> = ({
  open,
  onClose,
  title,
  name,
  defaultWidth = 760,
  defaultHeight = 520,
  modal = true,
  barExtras,
  footer,
  rootProps,
  children,
}) => {
  const titleId = useId();
  const winRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const { rect, busy, isMobile, startDrag, startResize } = useDragResize({
    name,
    defaultWidth,
    defaultHeight,
    enabled: open,
  });

  /* التركيز يعود من حيث أتى — لا يُترك المستخدم في فراغ بعد الإغلاق. */
  useEffect(() => {
    if (!open) return undefined;
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    const frame = requestAnimationFrame(() => {
      const first = winRef.current?.querySelector(FOCUSABLE) as HTMLElement | null;
      (first ?? winRef.current)?.focus();
    });
    return () => {
      cancelAnimationFrame(frame);
      restoreFocusRef.current?.focus?.();
    };
  }, [open]);

  const onKeyDown = useCallback((event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab" || !modal) return;
    const nodes = (Array.from(
      winRef.current?.querySelectorAll(FOCUSABLE) ?? [],
    ) as HTMLElement[]).filter((node) => node.offsetParent !== null);
    if (nodes.length === 0) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }, [modal, onClose]);

  if (!open) return null;

  /* الهندسة متغيّراتُ CSS لا أنماط مظهر — المظهر كلّه يبقى في الورقة. */
  const geometry = isMobile
    ? undefined
    : ({
        "--win-x": `${rect.x}px`,
        "--win-y": `${rect.y}px`,
        "--win-w": `${rect.w}px`,
        "--win-h": `${rect.h}px`,
      } as React.CSSProperties);

  const { className: extraClass, ...restRootProps } = rootProps ?? {};

  return createPortal(
    <div
      className={`ktra-float-mask${modal ? " ktra-float-mask--dim" : ""}`}
      onMouseDown={(event) => {
        if (modal && event.target === event.currentTarget) onClose();
      }}
    >
      <div
        {...restRootProps}
        ref={winRef}
        dir="rtl"
        role="dialog"
        aria-modal={modal}
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`ktra-float-win${busy ? " ktra-float-win--busy" : ""}${extraClass ? ` ${extraClass}` : ""}`}
        style={geometry}
        onKeyDown={onKeyDown}
      >
        <div className="ktra-float-win__bar" onPointerDown={startDrag}>
          <span className="ktra-float-win__title" id={titleId}>{title}</span>
          {barExtras}
          <button
            type="button"
            className="ktra-toolbtn"
            onClick={onClose}
            onPointerDown={(event) => event.stopPropagation()}
            title="إغلاق"
            aria-label="إغلاق"
          >
            <X size={15} />
          </button>
        </div>

        <div className="ktra-float-win__body">{children}</div>
        {footer ? <div className="ktra-float-win__foot">{footer}</div> : null}

        {!isMobile && GRIPS.map(({ key, dir }) => (
          <div
            key={key}
            className={`ktra-float-win__grip ktra-float-win__grip--${key}`}
            data-grip={key}
            onPointerDown={startResize(dir)}
          />
        ))}
      </div>
    </div>,
    document.body,
  );
};
