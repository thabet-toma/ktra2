/**
 * سحب النافذة العائمة وتحجيمها — الحلقة المؤشِّرة وحدها هنا، والحساب كلّه في
 * `utils/windowGeometry.ts` كي يبقى مُختبَراً بلا DOM.
 *
 * Pointer Events + setPointerCapture: حدثٌ واحد يخدم الفأرة واللمس والقلم،
 * والالتقاط يبقي الحدث واصلاً حتى لو سبق المؤشرُ النافذةَ أثناء سحبٍ سريع
 * (وهو ما كان يُسقط سحب `AseelDenseTable` المبني على mousemove على المستند).
 *
 * الحفظ عند رفع الإصبع فقط — لا كتابةَ تخزينٍ في كل إطار.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Rect,
  ResizeDir,
  Viewport,
  applyDrag,
  applyResize,
  centeredRect,
  clampRectToViewport,
  isMobileViewport,
  readWindowGeometry,
  writeWindowGeometry,
} from '../utils/windowGeometry.ts';

/**
 * المستودع بلا `@types/react` (موثّق في `docs/modules/frontend.md`) فلا وجود
 * لمساحة الاسم React في ملفات ‎.ts — نصف الحدث بنيوياً بما نستعمله منه فعلاً،
 * فيقبل الحدثَ التركيبي من React والحدثَ الأصليَّ من DOM على السواء.
 */
export type PointerLikeEvent = {
  button: number;
  pointerId: number;
  pointerType: string;
  clientX: number;
  clientY: number;
  currentTarget: unknown;
  preventDefault: () => void;
};

const viewportOf = (): Viewport => ({
  width: typeof window === 'undefined' ? 1280 : window.innerWidth,
  height: typeof window === 'undefined' ? 800 : window.innerHeight,
});

type Options = {
  /** اسم الحفظ: `ktra:win:<name>`. فارغ = نافذة لا تُحفظ هندستها. */
  name?: string;
  /** المقاس الابتدائي حين لا توجد هندسة محفوظة. */
  defaultWidth: number;
  defaultHeight: number;
  enabled?: boolean;
};

type DragState = {
  pointerId: number;
  startRect: Rect;
  startX: number;
  startY: number;
  dir: ResizeDir | null;
};

export type DragResize = {
  rect: Rect;
  busy: boolean;
  isMobile: boolean;
  /** يُركّب على شريط العنوان: يبدأ السحب. */
  startDrag: (event: PointerLikeEvent) => void;
  /** يُركّب على مقبض حافة أو زاوية: يبدأ التحجيم بذلك الاتجاه. */
  startResize: (dir: ResizeDir) => (event: PointerLikeEvent) => void;
};

export const useDragResize = ({
  name, defaultWidth, defaultHeight, enabled = true,
}: Options): DragResize => {
  const [isMobile, setIsMobile] = useState(() => isMobileViewport(viewportOf()));
  const [rect, setRect] = useState<Rect>(() => {
    const viewport = viewportOf();
    const saved = name ? readWindowGeometry(name, viewport) : null;
    return saved ?? centeredRect(defaultWidth, defaultHeight, viewport);
  });
  const [busy, setBusy] = useState(false);
  const dragRef = useRef<DragState | null>(null);
  const rectRef = useRef(rect);
  rectRef.current = rect;

  /* تصغير نافذة المتصفح لا يترك النافذة معلّقة خارج المرأى. */
  useEffect(() => {
    const onResize = () => {
      const viewport = viewportOf();
      setIsMobile(isMobileViewport(viewport));
      setRect((current) => clampRectToViewport(current, viewport));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const begin = useCallback((event: PointerLikeEvent, dir: ResizeDir | null) => {
    if (!enabled || isMobileViewport(viewportOf())) return;
    if (event.button !== 0 && event.pointerType === 'mouse') return;
    event.preventDefault();
    const target = event.currentTarget as HTMLElement;
    try { target.setPointerCapture(event.pointerId); } catch { /* بعض المتصفحات ترفض — السحب يستمر بلا التقاط */ }
    dragRef.current = {
      pointerId: event.pointerId,
      startRect: rectRef.current,
      startX: event.clientX,
      startY: event.clientY,
      dir,
    };
    setBusy(true);
  }, [enabled]);

  useEffect(() => {
    if (!busy) return undefined;

    const move = (event: PointerEvent) => {
      const state = dragRef.current;
      if (!state || state.pointerId !== event.pointerId) return;
      const dx = event.clientX - state.startX;
      const dy = event.clientY - state.startY;
      const viewport = viewportOf();
      setRect(state.dir
        ? applyResize(state.startRect, state.dir, dx, dy, viewport)
        : applyDrag(state.startRect, dx, dy, viewport));
    };

    const finish = (event: PointerEvent) => {
      const state = dragRef.current;
      if (!state || state.pointerId !== event.pointerId) return;
      dragRef.current = null;
      setBusy(false);
      if (name) writeWindowGeometry(name, rectRef.current);
    };

    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', finish);
    document.addEventListener('pointercancel', finish);
    return () => {
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', finish);
      document.removeEventListener('pointercancel', finish);
    };
  }, [busy, name]);

  const startDrag = useCallback(
    (event: PointerLikeEvent) => begin(event, null),
    [begin],
  );

  const startResize = useCallback(
    (dir: ResizeDir) => (event: PointerLikeEvent) => begin(event, dir),
    [begin],
  );

  return { rect, busy, isMobile, startDrag, startResize };
};
