import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_DOCK_SIDE,
  MIN_WINDOW_HEIGHT,
  MIN_WINDOW_WIDTH,
  applyDrag,
  applyResize,
  centeredRect,
  clampRectToViewport,
  isMobileViewport,
  nearestDock,
  readDockSide,
  readWindowGeometry,
  windowGeometryKey,
  writeDockSide,
  writeWindowGeometry,
} from './windowGeometry.ts';

const memoryStorage = (seed: Record<string, string> = {}) => {
  const data = new Map(Object.entries(seed));
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => { data.set(key, value); },
    dump: () => Object.fromEntries(data),
  };
};

const VIEW = { width: 1280, height: 800 };

test('مفتاح الحفظ يحمل اسم النافذة لا الشاشة', () => {
  assert.equal(windowGeometryKey('product-card'), 'ktra:win:product-card');
});

test('السحب يزيح الموضع ولا يمسّ الحجم', () => {
  const moved = applyDrag({ x: 100, y: 100, w: 600, h: 400 }, 40, -25, VIEW);
  assert.deepEqual(moved, { x: 140, y: 75, w: 600, h: 400 });
});

test('السحب لا يُخرج النافذة عن الشاشة في أي جهة', () => {
  const start = { x: 100, y: 100, w: 600, h: 400 };
  assert.deepEqual(applyDrag(start, -500, -500, VIEW), { x: 0, y: 0, w: 600, h: 400 });
  assert.deepEqual(applyDrag(start, 5000, 5000, VIEW), { x: 680, y: 400, w: 600, h: 400 });
});

test('سحب الحافة اللاحقة يوسّع، والبادئة توسّع وتُزيح الموضع معاً', () => {
  const start = { x: 200, y: 150, w: 600, h: 400 };
  assert.deepEqual(
    applyResize(start, { dx: 1, dy: 0 }, 50, 0, VIEW),
    { x: 200, y: 150, w: 650, h: 400 },
  );
  assert.deepEqual(
    applyResize(start, { dx: -1, dy: 0 }, -50, 0, VIEW),
    { x: 150, y: 150, w: 650, h: 400 },
  );
  assert.deepEqual(
    applyResize(start, { dx: -1, dy: -1 }, -50, -30, VIEW),
    { x: 150, y: 120, w: 650, h: 430 },
  );
});

test('عند بلوغ الحدّ الأدنى تبقى الحافة المقابلة مثبّتة فلا تقفز النافذة', () => {
  const start = { x: 200, y: 150, w: 400, h: 300 };
  const shrunk = applyResize(start, { dx: -1, dy: -1 }, 5000, 5000, VIEW);
  assert.equal(shrunk.w, MIN_WINDOW_WIDTH);
  assert.equal(shrunk.h, MIN_WINDOW_HEIGHT);
  assert.equal(shrunk.x, start.x + start.w - MIN_WINDOW_WIDTH, 'الحافة اليمنى لم تتحرك');
  assert.equal(shrunk.y, start.y + start.h - MIN_WINDOW_HEIGHT, 'الحافة السفلى لم تتحرك');
});

test('الحجم لا يتجاوز الشاشة ولا ينزل تحت الحدّ الأدنى', () => {
  const huge = clampRectToViewport({ x: 0, y: 0, w: 9000, h: 9000 }, VIEW);
  assert.deepEqual(huge, { x: 0, y: 0, w: 1280, h: 800 });
  const tiny = clampRectToViewport({ x: 0, y: 0, w: 10, h: 10 }, VIEW);
  assert.deepEqual(tiny, { x: 0, y: 0, w: MIN_WINDOW_WIDTH, h: MIN_WINDOW_HEIGHT });
});

test('النافذة الافتراضية موسّطة', () => {
  assert.deepEqual(centeredRect(600, 400, VIEW), { x: 340, y: 200, w: 600, h: 400 });
});

test('الحفظ والقراءة يدوران على نفس المفتاح', () => {
  const storage = memoryStorage();
  writeWindowGeometry('calc', { x: 10, y: 20, w: 320, h: 420 }, storage);
  assert.deepEqual(
    readWindowGeometry('calc', VIEW, storage),
    { x: 10, y: 20, w: 320, h: 420 },
  );
});

test('هندسة محفوظة على شاشة أعرض تعود مقصوصةً لا خارج المرأى', () => {
  const storage = memoryStorage({
    'ktra:win:card': JSON.stringify({ x: 1800, y: 1200, w: 900, h: 700 }),
  });
  const restored = readWindowGeometry('card', { width: 1024, height: 768 }, storage);
  assert.deepEqual(restored, { x: 124, y: 68, w: 900, h: 700 });
});

test('مخزون تالف أو ناقص لا يرمي — يعود null فيتولّى المستدعي الافتراضي', () => {
  assert.equal(readWindowGeometry('card', VIEW, memoryStorage({ 'ktra:win:card': 'x' })), null);
  assert.equal(readWindowGeometry('card', VIEW, memoryStorage()), null);
  assert.equal(
    readWindowGeometry('card', VIEW, memoryStorage({ 'ktra:win:card': '{"x":1,"y":2}' })),
    null,
  );
});

test('جهة الإرساء تُحفظ وتُقرأ، والقيمة الغريبة تعود للافتراضي', () => {
  const storage = memoryStorage();
  assert.equal(readDockSide(storage), DEFAULT_DOCK_SIDE);
  writeDockSide('left', storage);
  assert.equal(readDockSide(storage), 'left');
  writeDockSide('bottom' as never, storage);
  assert.equal(readDockSide(storage), 'left', 'القيمة خارج القائمة البيضاء لا تُكتب');
  assert.equal(readDockSide(memoryStorage({ 'ktra:actionBarDock': 'north' })), DEFAULT_DOCK_SIDE);
});

test('أقرب جهة إرساء: القمة أولاً ثم النصف الأقرب', () => {
  assert.equal(nearestDock(640, 20, VIEW), 'top');
  assert.equal(nearestDock(1200, 400, VIEW), 'right');
  assert.equal(nearestDock(80, 400, VIEW), 'left');
});

test('الجوال يُعرف بالعرض وحده', () => {
  assert.equal(isMobileViewport({ width: 420, height: 900 }), true);
  assert.equal(isMobileViewport({ width: 768, height: 900 }), false);
});
