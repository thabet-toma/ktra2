/**
 * هندسة النوافذ العائمة — مصدر واحد لموضع النافذة وحجمها:
 * السحب من شريط العنوان، والتحجيم من الحواف والزوايا، والحفظ في المتصفح كي
 * تعود النافذة حيث تركها المستخدم. الحساب هنا نقيّ بلا DOM ليبقى مُختبَراً.
 * يستهلكه `useDragResize` و`AseelFloatWindow` و`ActionBarRail`.
 *
 * الموضع بـ left/top بالبكسل الخام — محايد اتجاهياً، فلا قلب إشارة في RTL
 * (بخلاف عرض الأعمدة في `columnWidths.ts` حيث الحافة نفسها تنعكس).
 */

export type Rect = { x: number; y: number; w: number; h: number };

export type Viewport = { width: number; height: number };

/** اتجاه التحجيم: ‎-1 الحافة البادئة (تُزيح الموضع)، ‎+1 الحافة اللاحقة، 0 ثابت. */
export type ResizeDir = { dx: -1 | 0 | 1; dy: -1 | 0 | 1 };

/** حارس: لا تنكمش النافذة إلى ما دون محتوى صالح للقراءة. */
export const MIN_WINDOW_WIDTH = 280;
export const MIN_WINDOW_HEIGHT = 180;

/** تحت هذا العرض النافذة لوحٌ ملء الشاشة — لا سحب ولا تحجيم ولا هندسة محفوظة. */
export const MOBILE_BREAKPOINT = 768;

/** جهات إرساء شريط الإجراءات. `top` = سلوك اليوم داخل شريط العنوان. */
export const DOCK_SIDES = ['right', 'left', 'top'] as const;
export type DockSide = (typeof DOCK_SIDES)[number];

export const DEFAULT_DOCK_SIDE: DockSide = 'right';

const DOCK_KEY = 'ktra:actionBarDock';

type StorageLike = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
};

const browserStorage = (): StorageLike | null => {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
};

/** مفتاح الحفظ لكل نافذة على حدة — الاسم يصف النافذة لا الشاشة التي فتحتها. */
export const windowGeometryKey = (name: string): string => `ktra:win:${name}`;

/**
 * يُبقي المستطيل كاملاً داخل الشاشة: الحجم لا يتجاوزها، والموضع لا يخرج عنها.
 * يُستدعى بعد كل سحب وتحجيم **وعند الاسترجاع** — الشاشة قد تكون تغيّرت مقاسها
 * بين جلستين، فنافذةٌ محفوظة على شاشة أعرض تعود بلا هذا القصّ غير قابلة للوصول.
 */
export const clampRectToViewport = (rect: Rect, viewport: Viewport): Rect => {
  const maxW = Math.max(MIN_WINDOW_WIDTH, viewport.width);
  const maxH = Math.max(MIN_WINDOW_HEIGHT, viewport.height);
  const w = Math.round(Math.min(Math.max(rect.w, MIN_WINDOW_WIDTH), maxW));
  const h = Math.round(Math.min(Math.max(rect.h, MIN_WINDOW_HEIGHT), maxH));
  const x = Math.round(Math.min(Math.max(rect.x, 0), Math.max(0, viewport.width - w)));
  const y = Math.round(Math.min(Math.max(rect.y, 0), Math.max(0, viewport.height - h)));
  return { x, y, w, h };
};

/** موضع البداية: نافذة موسّطة بحجمها المطلوب، مقصوصة على الشاشة الحالية. */
export const centeredRect = (w: number, h: number, viewport: Viewport): Rect =>
  clampRectToViewport(
    { x: (viewport.width - w) / 2, y: (viewport.height - h) / 2, w, h },
    viewport,
  );

/** الإزاحة أثناء السحب — الحجم ثابت والموضع يتبع المؤشر. */
export const applyDrag = (start: Rect, dx: number, dy: number, viewport: Viewport): Rect =>
  clampRectToViewport({ ...start, x: start.x + dx, y: start.y + dy }, viewport);

/**
 * التحجيم أثناء السحب. الحافة المقابلة للمسحوبة تبقى مثبّتة — حتى عند بلوغ
 * الحدّ الأدنى، فلا «تقفز» النافذة حين يواصل المستخدم السحب.
 */
export const applyResize = (
  start: Rect, dir: ResizeDir, dx: number, dy: number, viewport: Viewport,
): Rect => {
  let { x, y, w, h } = start;

  if (dir.dx === 1) {
    w = start.w + dx;
  } else if (dir.dx === -1) {
    w = start.w - dx;
    x = start.x + dx;
  }
  if (dir.dy === 1) {
    h = start.h + dy;
  } else if (dir.dy === -1) {
    h = start.h - dy;
    y = start.y + dy;
  }

  if (w < MIN_WINDOW_WIDTH) {
    if (dir.dx === -1) x = start.x + start.w - MIN_WINDOW_WIDTH;
    w = MIN_WINDOW_WIDTH;
  }
  if (h < MIN_WINDOW_HEIGHT) {
    if (dir.dy === -1) y = start.y + start.h - MIN_WINDOW_HEIGHT;
    h = MIN_WINDOW_HEIGHT;
  }

  return clampRectToViewport({ x, y, w, h }, viewport);
};

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

/**
 * يقرأ الهندسة المحفوظة مقصوصةً على الشاشة الحالية، و`null` إن لم تُحفظ بعد أو
 * كان المخزون تالفاً — فيتولّى المستدعي حينها الموضع الافتراضي.
 */
export const readWindowGeometry = (
  name: string, viewport: Viewport, storage?: StorageLike | null,
): Rect | null => {
  const store = storage ?? browserStorage();
  if (!store || !name) return null;
  try {
    const raw = store.getItem(windowGeometryKey(name));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object') return null;
    const { x, y, w, h } = parsed as Record<string, unknown>;
    if (!isFiniteNumber(x) || !isFiniteNumber(y) || !isFiniteNumber(w) || !isFiniteNumber(h)) {
      return null;
    }
    return clampRectToViewport({ x, y, w, h }, viewport);
  } catch {
    return null;
  }
};

export const writeWindowGeometry = (
  name: string, rect: Rect, storage?: StorageLike | null,
): void => {
  const store = storage ?? browserStorage();
  if (!store || !name) return;
  try {
    store.setItem(windowGeometryKey(name), JSON.stringify(rect));
  } catch {
    // امتلاء/حظر التخزين لا يُسقط النافذة — الهندسة تبقى لهذه الجلسة فقط.
  }
};

/** جهة الإرساء المحفوظة — قائمة بيضاء، فقيمة غريبة في المخزون تعود للافتراضي. */
export const readDockSide = (storage?: StorageLike | null): DockSide => {
  const store = storage ?? browserStorage();
  if (!store) return DEFAULT_DOCK_SIDE;
  try {
    const raw = store.getItem(DOCK_KEY);
    return (DOCK_SIDES as readonly string[]).includes(raw ?? '')
      ? (raw as DockSide)
      : DEFAULT_DOCK_SIDE;
  } catch {
    return DEFAULT_DOCK_SIDE;
  }
};

export const writeDockSide = (side: DockSide, storage?: StorageLike | null): void => {
  const store = storage ?? browserStorage();
  if (!store || !(DOCK_SIDES as readonly string[]).includes(side)) return;
  try {
    store.setItem(DOCK_KEY, side);
  } catch {
    // كما في الهندسة: الفشل لا يُسقط الشريط.
  }
};

/** أقرب جهة إرساء لنقطة الإفلات — الحافة الأقرب تفوز، والأعلى يفوز قرب القمة. */
export const nearestDock = (px: number, py: number, viewport: Viewport): DockSide => {
  if (py <= viewport.height * 0.12) return 'top';
  return px > viewport.width / 2 ? 'right' : 'left';
};

export const isMobileViewport = (viewport: Viewport): boolean =>
  viewport.width < MOBILE_BREAKPOINT;
