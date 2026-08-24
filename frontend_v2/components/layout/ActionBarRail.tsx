import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { GripVertical } from "lucide-react";
import { AppView, User } from "../../types";
import { clientLogger } from "../../services/logger";
import { GlobalActionBar } from "./GlobalActionBar";
import {
  DOCK_SIDES,
  DockSide,
  isMobileViewport,
  nearestDock,
  readDockSide,
  writeDockSide,
} from "../../utils/windowGeometry";

/**
 * T-WIN — شريط الإجراءات السريعة: رفٌّ عمودي عائم يُسحب ويُرسى حيث يريح
 * المستخدم (يمين/يسار)، أو يعود شريطاً أفقياً داخل شريط العنوان.
 *
 * لماذا رفٌّ لا شريطُ عنوان: الإجراءات السريعة يد المستخدم اليمنى طوال اليوم،
 * وشريط العنوان مزدحم بخمسة عشر عنصراً. الأشرطة العائمة القابلة للإرساء نمطٌ
 * قائم في الأدوات الاحترافية (Figma / ClickUp).
 *
 * الوضع `top` يعرض حرفياً ترميز الشريط الأفقي في موضعه من شريط العنوان — فهو
 * مفتاح التراجع، وهو الوضع المفروض على الجوال حيث لا مكان لرفٍّ عائم.
 *
 * ⚠ الرفّ يُحقن بـ`createPortal` إلى `body`: شريط العنوان سياق تراص، وطبقةٌ
 * `fixed` تولد داخله تُحبس فيه (قاعدة 4.1 في `docs/modules/frontend.md`).
 */

interface Props {
  user: User;
  onNavigate: (view: AppView, targetId?: string) => void;
}

const DOCK_LABEL: Record<DockSide, string> = {
  right: "يمين الشاشة",
  left: "يسار الشاشة",
  top: "شريط العنوان",
};

export const ActionBarRail: React.FC<Props> = ({ user, onNavigate }) => {
  const [dock, setDock] = useState<DockSide>(() => readDockSide());
  const [narrow, setNarrow] = useState(
    () => isMobileViewport({
      width: typeof window === "undefined" ? 1280 : window.innerWidth,
      height: typeof window === "undefined" ? 800 : window.innerHeight,
    }),
  );
  /** موضع الرفّ تحت الإصبع أثناء السحب — null يعني مُرسىً. */
  const [dragPoint, setDragPoint] = useState<{ x: number; y: number } | null>(null);
  const [target, setTarget] = useState<DockSide | null>(null);
  const railRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onResize = () => setNarrow(isMobileViewport({
      width: window.innerWidth, height: window.innerHeight,
    }));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const startDrag = (event: React.PointerEvent) => {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    event.preventDefault();
    const pointerId = event.pointerId;

    const move = (e: PointerEvent) => {
      if (e.pointerId !== pointerId) return;
      setDragPoint({ x: e.clientX, y: e.clientY });
      setTarget(nearestDock(e.clientX, e.clientY, {
        width: window.innerWidth, height: window.innerHeight,
      }));
    };
    const finish = (e: PointerEvent) => {
      if (e.pointerId !== pointerId) return;
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", finish);
      document.removeEventListener("pointercancel", finish);
      const side = nearestDock(e.clientX, e.clientY, {
        width: window.innerWidth, height: window.innerHeight,
      });
      setDragPoint(null);
      setTarget(null);
      setDock(side);
      writeDockSide(side);
      clientLogger.info("app.action_bar_docked");
    };
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", finish);
    document.addEventListener("pointercancel", finish);
    setDragPoint({ x: event.clientX, y: event.clientY });
  };

  /* الجوال يُجبَر على شريط العنوان مهما كان المحفوظ — بلا كتابة تخزين، فالتفضيل
     على الحاسوب يبقى كما تركه المستخدم. */
  const effective: DockSide = narrow ? "top" : dock;

  if (effective === "top") {
    return (
      <div className="flex items-center gap-1" data-action-bar-dock="top">
        <GlobalActionBar user={user} onNavigate={onNavigate} dock="top" />
        {!narrow && (
          <button
            type="button"
            className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-primary-emphasis)] rounded-lg cursor-grab active:cursor-grabbing"
            style={{ touchAction: "none" }}
            onPointerDown={startDrag}
            title="اسحب لإرساء شريط الإجراءات على حافة الشاشة"
            aria-label="تغيير موضع شريط الإجراءات"
          >
            <GripVertical className="w-3.5 h-3.5" />
          </button>
        )}
        {dragPoint && createPortal(<DockZones target={target} />, document.body)}
      </div>
    );
  }

  const dragging = dragPoint !== null;
  const floating: React.CSSProperties | undefined = dragPoint
    ? { top: dragPoint.y, left: dragPoint.x, right: "auto", transform: "translate(-50%, -20px)" }
    : undefined;

  return createPortal(
    <>
      <div
        ref={railRef}
        className={`aseel-rail aseel-rail--${effective}${dragging ? " aseel-rail--busy" : ""}`}
        style={floating}
        data-action-bar-dock={effective}
        data-testid="action-bar-rail"
      >
        <button
          type="button"
          className="aseel-rail__grip"
          style={{ touchAction: "none" }}
          onPointerDown={startDrag}
          title={`اسحب لتغيير الموضع — الآن: ${DOCK_LABEL[effective]}`}
          aria-label="تغيير موضع شريط الإجراءات"
        >
          <GripVertical className="w-3.5 h-3.5" />
        </button>
        <GlobalActionBar user={user} onNavigate={onNavigate} dock={effective} />
      </div>
      {dragging && <DockZones target={target} />}
    </>,
    document.body,
  );
};

/** مناطق الإرساء الثلاث — تُضاء أثناء السحب فيرى المستخدم أين سيستقرّ الشريط. */
const DockZones: React.FC<{ target: DockSide | null }> = ({ target }) => (
  <>
    {DOCK_SIDES.map((side) => (
      <div
        key={side}
        className={`aseel-dockzone aseel-dockzone--${side}${target === side ? " aseel-dockzone--active" : ""}`}
        data-dockzone={side}
      />
    ))}
  </>
);
