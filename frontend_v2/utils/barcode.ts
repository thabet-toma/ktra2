/**
 * باركود EAN-13: إكمال خانة التحقق + رسم رمز قابل للمسح + طباعة ملصقات.
 *
 * لماذا ترميز مكتوب هنا بدل حزمة `jsbarcode`: كل ما نحتاجه رمزٌ واحد (EAN-13)
 * قاعدته ثابتة منذ عقود ونحو ستين سطراً، بينما الحزمة تجلب عشرة رموز لا نستعملها
 * وتفرض تبعية جديدة على مشروعٍ يُبنى على استضافة مشتركة — والأهم أنّ الوحدة النقية
 * هنا تُختبر بـ`node --test` مقابل باركود معروف، وهو بالضبط ما تطالب به معايير القبول.
 *
 * خانة التحقق هي **القاعدة نفسها** الموجودة في `inventory/serials.py::ean13_check_digit`؛
 * الخادم يبقى المرجع عند الحفظ (يرفض التكرار)، وهذه نسخة العرض الفوري لا بديلٌ عنه.
 *
 * وحدة نقية عند الاستيراد: لا تلمس `window` إلا داخل `printBarcodeLabels` وقت النداء،
 * فتُستورَد في اختبارات Node بلا متصفّح.
 */

export const EAN13_LENGTH = 13;

/** ترميز الخانة اليسرى الفردي (L) — الأساس، وبقية الجداول مشتقّة منه. */
const L_CODES = [
  "0001101", "0011001", "0010011", "0111101", "0100011",
  "0110001", "0101111", "0111011", "0110111", "0001011",
];

/** الخانة اليمنى (R) = مكمّل L بت ببت. */
const R_CODES = L_CODES.map((c) => c.replace(/[01]/g, (b) => (b === "0" ? "1" : "0")));

/** الخانة اليسرى الزوجي (G) = R معكوساً. */
const G_CODES = R_CODES.map((c) => c.split("").reverse().join(""));

/**
 * الرقم الأول لا يُرسم رمزاً — يُرمَّز في **نمط تعاقب** L/G للخانات الست اليسرى.
 * هذا ما يجعل EAN-13 يحمل ثلاثة عشر رقماً في اثني عشر موضعاً.
 */
const PARITY = [
  "LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
  "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL",
];

const GUARD_SIDE = "101";
const GUARD_CENTER = "01010";

/** أرقام فقط — أي فاصل أو مسافة يكتبها المستخدم يسقط. */
export const onlyDigits = (value: string): string => String(value ?? "").replace(/\D/g, "");

/**
 * خانة التحقق لاثني عشر رقماً: مجموع موزون (1، 3 بالتناوب) ثم مكمّل العشرة.
 * ترمي على أي دخل ليس اثني عشر رقماً — الصمت هنا يُنتج باركوداً لا يُمسَح.
 */
export function ean13CheckDigit(twelve: string): string {
  const digits = String(twelve ?? "");
  if (digits.length !== 12 || !/^\d{12}$/.test(digits)) {
    throw new Error("حساب خانة التحقق يتطلب 12 رقماً.");
  }
  let total = 0;
  for (let i = 0; i < 12; i++) total += Number(digits[i]) * (i % 2 ? 3 : 1);
  return String((10 - (total % 10)) % 10);
}

/** باركود سليم البنية وخانة التحقق. */
export function isValidEan13(code: string): boolean {
  const value = String(code ?? "");
  if (!/^\d{13}$/.test(value)) return false;
  return ean13CheckDigit(value.slice(0, 12)) === value[12];
}

export type Ean13Completion = {
  /** الباركود الكامل بخانة تحقق سليمة. */
  code: string;
  /** ما جرى للرقم المُدخَل — يُعرض للمستخدم كي لا يتغيّر رقمه بصمت. */
  note: string;
  /** خانة التحقق المُدخَلة كانت خاطئة فصُحّحت. */
  corrected: boolean;
};

/**
 * يُكمل رقماً كتبه المستخدم إلى EAN-13 صالح.
 *
 * أقل من 12 رقماً يُصفَّر من اليسار (الترقيم الداخلي يقرأ الرقم كعدد لا كنص)، و12
 * تُضاف لها خانة التحقق، و13 تُفحص وتُصحَّح خانتها إن أخطأت — والتصحيح **يُقال**
 * لا يُبتلع. أكثر من 13 يُقتصّ على الاثني عشر الأولى.
 */
export function completeEan13(input: string): Ean13Completion | null {
  const digits = onlyDigits(input);
  if (!digits) return null;

  if (digits.length === EAN13_LENGTH) {
    const expected = ean13CheckDigit(digits.slice(0, 12));
    if (expected === digits[12]) {
      return { code: digits, note: "الباركود صالح (خانة التحقق سليمة).", corrected: false };
    }
    return {
      code: digits.slice(0, 12) + expected,
      note: `خانة التحقق كانت ${digits[12]} والصحيح ${expected} — صُحّحت.`,
      corrected: true,
    };
  }

  if (digits.length > EAN13_LENGTH) {
    const body = digits.slice(0, 12);
    return {
      code: body + ean13CheckDigit(body),
      note: `الرقم أطول من ${EAN13_LENGTH} خانة — اعتُمدت أول 12 خانة وأُضيفت خانة التحقق.`,
      corrected: true,
    };
  }

  const body = digits.padStart(12, "0");
  return {
    code: body + ean13CheckDigit(body),
    note: digits.length === 12
      ? "أُضيفت خانة التحقق."
      : `أُكمل الرقم إلى 12 خانة بأصفار بادئة وأُضيفت خانة التحقق.`,
    corrected: false,
  };
}

/**
 * تسلسل الوحدات (95 خانة) للرمز: حارس + ست خانات يسرى + حارس أوسط + ست يمنى + حارس.
 * «1» عمود أسود و«0» أبيض.
 */
export function ean13Modules(code: string): string {
  if (!isValidEan13(code)) throw new Error("باركود EAN-13 غير صالح.");
  const parity = PARITY[Number(code[0])];
  let bits = GUARD_SIDE;
  for (let i = 0; i < 6; i++) {
    const digit = Number(code[1 + i]);
    bits += parity[i] === "L" ? L_CODES[digit] : G_CODES[digit];
  }
  bits += GUARD_CENTER;
  for (let i = 0; i < 6; i++) bits += R_CODES[Number(code[7 + i])];
  return bits + GUARD_SIDE;
}

export type Ean13SvgOptions = {
  /** عرض الوحدة بالبكسل — 2 تقريباً حجم المتجر القياسي. */
  moduleWidth?: number;
  /** ارتفاع الأعمدة (بلا الأرقام). */
  barHeight?: number;
  /** حجم خطّ الأرقام المقروءة. */
  fontSize?: number;
};

/** أعمدة الحارس تنزل أطول من الباقي — علامة EAN القياسية التي يقرؤها الماسح. */
const GUARD_POSITIONS = new Set<number>();
for (let i = 0; i < 3; i++) GUARD_POSITIONS.add(i);
for (let i = 45; i < 50; i++) GUARD_POSITIONS.add(i);
for (let i = 92; i < 95; i++) GUARD_POSITIONS.add(i);

/**
 * رمز EAN-13 كـ SVG جاهز للطباعة (نصّ، لا DOM) — مصدر واحد للمعاينة في الكرت
 * وللملصق المطبوع. مناطق الهدوء (11 وحدة يساراً و7 يميناً) جزء من المواصفة:
 * بدونها يفشل المسح مهما كانت الأعمدة صحيحة.
 */
export function ean13Svg(code: string, options: Ean13SvgOptions = {}): string {
  const bits = ean13Modules(code);
  const mw = options.moduleWidth ?? 2;
  const barHeight = options.barHeight ?? 60;
  const fontSize = options.fontSize ?? 11;

  const quietLeft = 11;
  const quietRight = 7;
  const totalModules = quietLeft + 95 + quietRight;
  const width = totalModules * mw;
  const guardDrop = fontSize * 0.9;
  const height = barHeight + guardDrop + fontSize + 2;

  let bars = "";
  for (let i = 0; i < bits.length; i++) {
    if (bits[i] !== "1") continue;
    const x = (quietLeft + i) * mw;
    const h = GUARD_POSITIONS.has(i) ? barHeight + guardDrop : barHeight;
    bars += `<rect x="${x}" y="0" width="${mw}" height="${h}" fill="#000"/>`;
  }

  const textY = barHeight + guardDrop + fontSize;
  const digit = (value: string, centerModule: number) =>
    `<text x="${centerModule * mw}" y="${textY}" font-size="${fontSize}" ` +
    `font-family="monospace" text-anchor="middle" fill="#000">${value}</text>`;

  // الرقم الأول خارج الرمز يساراً، والستّ التالية تحت النصف الأيسر، والستّ الأخيرة
  // تحت النصف الأيمن — مواضعها بين أعمدة الحارس تماماً كما في الملصق التجاري.
  let texts = digit(code[0], quietLeft - 4);
  for (let i = 0; i < 6; i++) texts += digit(code[1 + i], quietLeft + 3 + i * 7 + 3.5);
  for (let i = 0; i < 6; i++) texts += digit(code[7 + i], quietLeft + 50 + i * 7 + 3.5);

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" ` +
    `viewBox="0 0 ${width} ${height}" role="img" aria-label="باركود ${code}">` +
    `<rect x="0" y="0" width="${width}" height="${height}" fill="#fff"/>` +
    bars + texts +
    `</svg>`
  );
}

const esc = (value: unknown) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

export type BarcodeLabel = {
  barcode: string;
  name: string;
  /** سعر البيع كنصّ مُنسَّق مسبقاً (utils/formatNumber) — لا تنسيق هنا. */
  price?: string | null;
  /** رقم المنتج — يفيد الجرد حين يكون الاسم طويلاً. */
  sku?: string | null;
};

/**
 * صفحة الملصقات كنصّ HTML — مفصولة عن فتح النافذة كي تُبنى وتُفحَص بلا متصفّح
 * (وهي بالضبط ما يُطبع، لا نسخة منه).
 * تُعيد "" إن لم يبق ملصق صالح.
 */
export function barcodeLabelsHtml(labels: BarcodeLabel[], copies = 1): string {
  const count = Math.max(1, Math.min(Math.floor(copies) || 1, 200));
  const printable = labels.filter((l) => isValidEan13(l.barcode));
  if (!printable.length) return "";

  const cells: string[] = [];
  for (const label of printable) {
    const svg = ean13Svg(label.barcode, { moduleWidth: 2, barHeight: 50, fontSize: 11 });
    const html =
      `<div class="label">` +
      `<div class="name">${esc(label.name)}</div>` +
      `<div class="code">${svg}</div>` +
      `<div class="foot">` +
      (label.sku ? `<span>${esc(label.sku)}</span>` : `<span></span>`) +
      (label.price ? `<span class="price">${esc(label.price)}</span>` : `<span></span>`) +
      `</div></div>`;
    for (let i = 0; i < count; i++) cells.push(html);
  }

  return `
    <html dir="rtl" lang="ar">
      <head>
        <title>ملصقات الباركود</title>
        <style>
          body { font-family: system-ui, -apple-system, sans-serif; padding: 10px; color: #111827; }
          .sheet { display: flex; flex-wrap: wrap; gap: 6px; }
          .label { width: 240px; border: 1px dashed #d1d5db; border-radius: 4px;
                   padding: 6px; text-align: center; break-inside: avoid; page-break-inside: avoid; }
          .name { font-size: 12px; font-weight: 600; margin-bottom: 2px;
                  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
          .code { direction: ltr; line-height: 0; }
          .foot { display: flex; justify-content: space-between; font-size: 11px;
                  color: #374151; margin-top: 2px; }
          .price { font-weight: 700; direction: ltr; }
          @media print {
            body { padding: 0; }
            .label { border-color: transparent; }
            @page { margin: 8mm; }
          }
        </style>
      </head>
      <body>
        <div class="sheet">${cells.join("")}</div>
        <script>window.onload = () => { window.print(); };</script>
      </body>
    </html>`;
}

/**
 * يفتح نافذة طباعة بملصقات المنتج (نفس نمط «تصدير PDF للطباعة» في المنتجات: نافذة
 * HTML ثم `window.print()` ومن الحوار «حفظ كـ PDF»). يُعيد false إن لم يوجد ملصق
 * صالح أو منع المتصفّح النوافذ المنبثقة، فتُظهر الشاشة رسالة بدل الصمت.
 */
export function printBarcodeLabels(labels: BarcodeLabel[], copies = 1): boolean {
  const html = barcodeLabelsHtml(labels, copies);
  if (!html) return false;
  const win = window.open("", "_blank");
  if (!win) return false;
  win.document.open();
  win.document.write(html);
  win.document.close();
  return true;
}
