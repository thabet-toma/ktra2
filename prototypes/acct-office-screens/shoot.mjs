// PROTOTYPE — throwaway. Renders the six screens to PNG.
// Playwright lives in the main checkout, not in this worktree.
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import { mkdir, readFile } from 'node:fs/promises';

const require = createRequire('D:/Users/asus/Desktop/ktra/frontend_v2/package.json');
const { chromium } = require('playwright');

const here = path.dirname(fileURLToPath(import.meta.url));
const shotsDir = path.join(here, 'screenshots');
const FONT = 'IBM Plex Sans Arabic';

const VIEWPORTS = {
  mobile: { width: 390, height: 844, deviceScaleFactor: 3 },
  desktop: { width: 1440, height: 900, deviceScaleFactor: 2 },
  a4: { width: 794, height: 1123, deviceScaleFactor: 2 },
};

const SCREENS = [
  { html: '01-today.html', png: '01-اليوم.png', mode: 'mobile' },
  { html: '02-ready-to-send.html', png: '02-جاهز-للإرسال.png', mode: 'mobile' },
  { html: '03-client-file.html', png: '03-ملف-الزبون.png', mode: 'desktop' },
  { html: '04-fee-invoice.html', png: '04-فاتورة-أتعاب.png', mode: 'a4', selector: '#doc' },
  { html: '05-payment-notice.html', png: '05-إشعار-دفع.png', mode: 'a4', selector: '#doc' },
  { html: '06-expense-accounts.html', png: '06-حسابات-المصروفات.png', mode: 'desktop' },
];

const A4_MAX_HEIGHT = 1123;

function fail(screen, message) {
  throw new Error(`[${screen.html}] ${message}`);
}

async function settle(page, screen) {
  // Tailwind's browser build compiles after load; wait until a utility actually applies.
  try {
    await page.waitForFunction(() => {
      const el = document.querySelector('.tabular-nums');
      return !!el && getComputedStyle(el).fontVariantNumeric === 'tabular-nums';
    }, null, { timeout: 20000 });
  } catch {
    fail(screen, 'Tailwind CDN did not compile (no utility classes applied)');
  }

  await page.evaluate(async (font) => {
    await document.fonts.load(`16px "${font}"`);
    await document.fonts.ready;
  }, FONT);

  await page.waitForLoadState('networkidle');
}

async function verify(page, screen) {
  const report = await page.evaluate((font) => {
    const family = font;
    const faces = [...document.fonts].filter((f) => f.family.replace(/["']/g, '').trim() === family);
    const canvas = document.createElement('canvas').getContext('2d');
    const width = (fam) => {
      canvas.font = `40px ${fam}`;
      return canvas.measureText('مكتب النور 2,250 ₪').width;
    };
    return {
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      check: document.fonts.check(`16px "${family}"`),
      faces: faces.length,
      loaded: faces.filter((f) => f.status === 'loaded').length,
      rendered: width(`"${family}"`),
      fallback: width('"NoSuchFamilyProbeXYZ"'),
    };
  }, FONT);

  if (report.scrollWidth > report.innerWidth) {
    fail(screen, `horizontal overflow: scrollWidth ${report.scrollWidth} > innerWidth ${report.innerWidth}`);
  }
  // document.fonts.check() alone stays true when a family does not exist at all, so it is
  // backed by two signals that do collapse: declared+loaded faces, and a width that differs
  // from a deliberately missing family.
  if (!report.check) {
    fail(screen, `document.fonts.check says "${FONT}" is not loaded`);
  }
  if (report.faces === 0 || report.loaded === 0 || Math.abs(report.rendered - report.fallback) < 0.5) {
    fail(screen, `webfont "${FONT}" is not actually applied (declared faces ${report.faces}, loaded ${report.loaded}, width ${report.rendered} vs fallback ${report.fallback})`);
  }

  if (screen.mode === 'a4') {
    const box = await page.locator(screen.selector).evaluate((el) => {
      const r = el.getBoundingClientRect();
      return { width: r.width, height: r.height };
    });
    if (box.height > A4_MAX_HEIGHT) {
      fail(screen, `A4 content is ${Math.round(box.height)}px tall — overflows one page (max ${A4_MAX_HEIGHT}px)`);
    }
    return box;
  }
  return null;
}

async function verifyDocumentsGrid(page, screen) {
  const grid = await page.evaluate(() => {
    const table = document.querySelector('table');
    if (!table) return null;
    const headerCells = table.querySelectorAll('thead tr:first-child th').length;
    return {
      monthColumns: headerCells - 1, // first header cell is the document label column
      rows: [...table.querySelectorAll('tbody tr')].map((tr) => ({
        label: (tr.querySelector('th')?.textContent || '').trim(),
        cells: tr.querySelectorAll('td').length,
      })),
    };
  });

  if (!grid) fail(screen, 'documents grid table not found');
  if (grid.monthColumns < 1) fail(screen, `documents grid has no month columns (header cells: ${grid.monthColumns + 1})`);

  const wrong = grid.rows.filter((row) => row.cells !== grid.monthColumns);
  if (wrong.length) {
    fail(screen, `documents grid cell count !== month headers (${grid.monthColumns}): ${wrong.map((row) => `"${row.label}" has ${row.cells} td`).join('; ')}`);
  }
}

async function pngSize(file) {
  const buf = await readFile(file);
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

const browser = await chromium.launch();
const written = [];

try {
  await mkdir(shotsDir, { recursive: true });

  for (const screen of SCREENS) {
    const viewport = VIEWPORTS[screen.mode];
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: viewport.deviceScaleFactor,
      colorScheme: 'light',
      locale: 'ar',
    });
    const page = await context.newPage();

    await page.goto(pathToFileURL(path.join(here, screen.html)).href, { waitUntil: 'load' });
    await settle(page, screen);
    const a4 = await verify(page, screen);
    if (screen.html === '03-client-file.html') await verifyDocumentsGrid(page, screen);

    const pngPath = path.join(shotsDir, screen.png);
    if (screen.mode === 'a4') {
      await page.locator(screen.selector).screenshot({ path: pngPath });
    } else {
      await page.screenshot({ path: pngPath, fullPage: true });
    }

    const size = await pngSize(pngPath);
    written.push(size);
    const a4Note = a4 ? ` · A4 element ${Math.round(a4.width)} × ${Math.round(a4.height)} css px (fits one page)` : '';
    console.log(`${screen.png} — ${size.width} × ${size.height} px${a4Note}`);
    await context.close();
  }
} catch (error) {
  await browser.close();
  console.error(`\nFAILED: ${error.message}`);
  process.exit(1);
}

await browser.close();
console.log(`\n${written.length} PNG written to ${path.relative(process.cwd(), shotsDir)}`);
