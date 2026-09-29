/**
 * THA-24 م2 — قواعد بطاقة الكفالة الصرفة (بلا React وبلا شبكة).
 *
 * قاعدتان تحكمان هذا الملف، وهما نفسهما قاعدتا الخادم (`after_sales/models.py`):
 *
 * - **الحالة مشتقّة** من تاريخ الانتهاء مقابل اليوم — لا حالة تُخزَّن ولا تُرسَل.
 *   ما هنا عرضٌ لما يحسبه الخادم، لا حسابٌ ثانٍ ينافسه.
 * - **الشهور تقويمية**: 31 يناير + شهر = 28/29 فبراير، لا `+30 يوماً`. كفالة سنة
 *   ليست 360 يوماً، والفرق يظهر على أول بطاقة تُفحص في نهاية مدّتها.
 *
 * الاشتقاق هنا **معاينة** للمستخدم قبل الحفظ فقط؛ التاريخ المخزَّن يبقى ما
 * يحسبه الخادم عند الإنشاء.
 */
// الامتداد صريح: `node --test` يشغّل هذا الملف مباشرةً ولا يحلّ الاستيراد بدونه.
import { formatDateValue } from "./formatDate.ts";
import { formatNumber } from "./formatNumber.ts";

/** مصدر البطاقة — تلقائية من ترحيل فاتورة بيع، أو يدوية أنشأها مستخدم. */
export type WarrantySource = "auto_sale" | "manual";

/**
 * الحالة كما يردّها الخادم (`WarrantyCard.status_on`، #222): `ended` تغلب
 * دائماً — بطاقةٌ أُنهيت بمرجعٍ أو إلغاء ترحيلٍ لا تصير «سارية» أبداً حتى لو
 * بقي تاريخ انتهائها في المستقبل. وإلا فمشتقّةٌ من `end_date` كما كانت.
 */
export type WarrantyStatus = "active" | "expired" | "ended" | "voided";

/** كفالة سارية تنتهي خلال هذه المدة تُعرض بلون تنبيه لا بلون اطمئنان. */
export const WARRANTY_NEAR_EXPIRY_DAYS = 30;

const pad = (n: number) => String(n).padStart(2, "0");

const daysInMonth = (year: number, month1to12: number): number =>
  new Date(Date.UTC(year, month1to12, 0)).getUTCDate();

/**
 * يضيف شهوراً تقويمية إلى تاريخ `YYYY-MM-DD` ويردّ الصيغة نفسها.
 *
 * مرآة `after_sales.models.add_months`: اليوم يُثبَّت على آخر الشهر حين يقصر.
 * الحساب على النص لا على `Date` المحلي — إنشاء `Date` من نص بلا منطقة زمنية
 * يزيح اليوم يوماً كاملاً على أجهزة شرق غرينتش.
 */
export function addWarrantyMonths(startIso: string, months: number): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec((startIso || "").trim());
  if (!match) return "";
  const [, y, m, d] = match;
  const added = Math.trunc(Number(months) || 0);
  const total = Number(y) * 12 + (Number(m) - 1) + added;
  const year = Math.floor(total / 12);
  const month = (total % 12) + 1;
  const day = Math.min(Number(d), daysInMonth(year, month));
  return `${year}-${pad(month)}-${pad(day)}`;
}

/**
 * تاريخ الانتهاء المعروض قبل الحفظ: الصريح يتقدّم دائماً على المشتقّ — من كتب
 * تاريخاً بيده لا تُعاد كتابته من المدة.
 */
export function deriveWarrantyEnd(
  startIso: string,
  months: number | null,
  explicitEndIso?: string | null,
): string {
  const explicit = (explicitEndIso || "").trim();
  if (explicit) return explicit;
  if (!startIso || !months) return "";
  return addWarrantyMonths(startIso, months);
}

export const warrantyStatusLabel = (status: WarrantyStatus): string => {
  if (status === "active") return "سارية";
  // #222: «غير سارية» لا «منتهية» — الانتهاء بواقعة (مرجع/إلغاء ترحيل) ليس
  // انقضاء مدّة، ولا يجوز أن تظهر بطاقة جهازٍ أُرجع «سارية» أبداً.
  if (status === "ended") return "غير سارية";
  // #236: الإلغاء قرارُ التاجر (تلاعب/سوء استخدام) لا انقضاء مدّة ولا واقعة بيع.
  if (status === "voided") return "ملغاة";
  return "منتهية";
};

/**
 * «باقٍ ١٢ يوماً» / «انتهت منذ ٣٠ يوماً» — الرقم وحده يُقرأ خطأً على المنتهية،
 * إذ يعود من الخادم بإشارة سالبة.
 *
 * المنتهية بواقعة (#222) لا تُقرأ من الأيام أصلاً: نهايتها قد تبقى في
 * المستقبل (جهازٌ أُرجع قبل أن تنقضي مدّته)، فحسابُ «منذ كم يوماً» منها كذبٌ.
 */
export function warrantyRemainingText(
  status: WarrantyStatus,
  daysRemaining: number,
): string {
  if (status === "ended") return "لم تعد سارية";
  if (status === "voided") return "أُلغيت — لا تغطي أعطالاً جديدة";
  const days = Number(daysRemaining) || 0;
  if (status !== "active") return `انتهت منذ ${formatNumber(Math.abs(days))} يوماً`;
  if (days === 0) return "تنتهي اليوم";
  return `باقٍ ${formatNumber(days)} يوماً`;
}

/**
 * حالة طبقة كفالة المصنع (#232) — `null` من الخادم يعني «لا يوجد» صراحةً
 * (بطاقةٌ بسياسة بلا جهة كفالة مصنع)، لا نقصاً في البيانات ولا خطأ تحميل.
 * وإلا فنفس مفردات طبقة التاجر (`WarrantyStatus`) — طبقتان مستقلتان بمفرداتٍ
 * واحدة، لا لهجتين.
 */
export function manufacturerWarrantyStatusLabel(status: WarrantyStatus | null): string {
  return status === null ? "لا يوجد" : warrantyStatusLabel(status);
}

/** مرآة `warrantyRemainingText` لطبقة المصنع — «لا يوجد» بدل حساب أيامٍ لا معنى لها. */
export function manufacturerWarrantyRemainingText(
  status: WarrantyStatus | null,
  daysRemaining: number | null,
): string {
  if (status === null) return "لا يوجد";
  return warrantyRemainingText(status, daysRemaining ?? 0);
}

/**
 * #234 — «الكمية المغطاة N من Q» لبطاقة «كفالة على الفاتورة» (بلا رقم
 * تسلسلي، كالإطارات): التغطية محسوبةٌ في الخادم (`quantity − returned_quantity`)
 * ولا تُعاد هنا — هذه واجهة عرضٍ فقط، مرآة `WarrantyCard.covered_quantity`.
 */
export function warrantyCoveredQuantityLabel(coveredQuantity: number, quantity: number): string {
  return `الكمية المغطاة ${formatNumber(coveredQuantity)} من ${formatNumber(quantity)}`;
}

/**
 * #233 — معاينة أثر سياسة كفالة `serial` قبل الحفظ (قصّتا المالك 6 و7):
 * البراندات الشقيقة التي سيرتفع تتبّعها معها (مزامنة العائلة)، وعدد الوحدات
 * غير المرقَّمة الآن لكل منتج معنيّ — تصل جاهزةً من `GET
 * warranty-policies/serial-impact/` (`services/afterSalesApi.ts`).
 */
export interface WarrantySerialImpactUnitsRow {
  productName: string;
  count: number;
}

/** لا تأكيد لازم إن لم يكن هناك أخٌ سيُتتبَّع معه ولا وحدةٌ غير مرقَّمة —
 *  سياسةٌ على منتجٍ وحيدٍ بلا مخزونٍ قديم لا تستحق مقاطعة المستخدم. */
export function serialImpactNeedsConfirmation(input: {
  siblingCount: number;
  unitsRows: WarrantySerialImpactUnitsRow[];
}): boolean {
  return input.siblingCount > 0 || input.unitsRows.some((row) => row.count > 0);
}

/** سطور رسالة التأكيد — سطرٌ للإخوة (إن وُجدوا)، وسطرٌ لكل منتجٍ له وحداتٌ
 *  غير مرقَّمة (الصفر يُستبعد: لا داعي لإخبار المستخدم بما لا يعنيه). */
export function serialImpactConfirmationLines(input: {
  siblingNames: string[];
  unitsRows: WarrantySerialImpactUnitsRow[];
}): string[] {
  const lines: string[] = [];
  if (input.siblingNames.length > 0) {
    lines.push(
      `سيُفعَّل تتبّع الرقم التسلسلي أيضاً على البراندات الشقيقة: ${input.siblingNames.join("، ")}.`,
    );
  }
  input.unitsRows
    .filter((row) => row.count > 0)
    .forEach((row) => {
      lines.push(
        `«${row.productName}»: ${formatNumber(row.count)} وحدة غير مرقَّمة في المخزون حالياً ` +
        "— سيُطلب رقمها التسلسلي عند بيعها.",
      );
    });
  return lines;
}

/* ── كفالة المصنع على سطر الشراء (#235) ─────────────────────────────────────
 * قيمةٌ تُملأ مسبقاً من سياسة المنتج ويعدّلها المستخدم على السطر. لا صفّ على
 * الخادم = السياسة؛ صفٌّ بجهةٍ فارغة = «لا يوجد» صريحة. */

/** أقصى مدة كفالة بالأشهر يقبلها الخادم (`LINE_WARRANTY_MAX_MONTHS`). */
export const LINE_WARRANTY_MAX_MONTHS = 600;

export interface PurchaseLineWarrantyValue {
  manufacturer_warrantor: number | null;
  manufacturer_months: number;
  supplier_months: number | null;
}

export interface PurchaseLineWarrantyPolicy {
  manufacturer_warrantor: number | null;
  manufacturer_months: number;
  supplier_months: number;
}

/** كفالة المورّد في الصفقة بالسنوات ← أشهر (واجهةٌ فقط؛ الخادم لا يقرأ الصفقة). */
export function dealWarrantyYearsToMonths(years: unknown): number {
  const value = Number(years);
  if (!Number.isFinite(value) || value <= 0) return 0;
  return Math.round(value * 12);
}

/**
 * القيمة الابتدائية للسطر: طبقة المصنع من السياسة، وكفالة المورّد من الصفقة
 * إن حملت مدّةً (فاتورة الاستيراد) وإلا من السياسة.
 */
export function purchaseLineWarrantyFromPolicy(
  policy: PurchaseLineWarrantyPolicy,
  dealWarrantyYears?: unknown,
): PurchaseLineWarrantyValue {
  const dealMonths = dealWarrantyYearsToMonths(dealWarrantyYears);
  return {
    manufacturer_warrantor: policy.manufacturer_warrantor,
    manufacturer_months: policy.manufacturer_months,
    supplier_months: dealMonths > 0 ? dealMonths : policy.supplier_months,
  };
}

/** وسم «يختلف عن السياسة» — طبقة المصنع وحدها؛ كفالة المورّد ثانوية ولا تُوسَم. */
export function purchaseLineWarrantyDiffers(
  value: PurchaseLineWarrantyValue,
  policy: PurchaseLineWarrantyPolicy,
): boolean {
  return (
    value.manufacturer_warrantor !== policy.manufacturer_warrantor ||
    value.manufacturer_months !== policy.manufacturer_months
  );
}

/** الحمولة المرسلة: أعداد صحيحة، وكفالة المورّد الفارغة `null`. */
export function purchaseLineWarrantyPayload(
  value: PurchaseLineWarrantyValue,
): PurchaseLineWarrantyValue {
  const supplier = value.supplier_months;
  return {
    manufacturer_warrantor: value.manufacturer_warrantor,
    manufacturer_months: Math.trunc(Number(value.manufacturer_months) || 0),
    supplier_months:
      supplier === null || supplier === undefined || Number.isNaN(Number(supplier))
        ? null
        : Math.trunc(Number(supplier)),
  };
}

/** فحصٌ مبكّر يطابق الخادم — يردّ رسالةً عربيةً أو `null` إن صحّ السطر. */
export function purchaseLineWarrantyProblem(value: PurchaseLineWarrantyValue): string | null {
  const payload = purchaseLineWarrantyPayload(value);
  if (payload.manufacturer_months < 0 || payload.manufacturer_months > LINE_WARRANTY_MAX_MONTHS) {
    return `مدة كفالة المصنع بين 0 و${formatNumber(LINE_WARRANTY_MAX_MONTHS)} شهراً.`;
  }
  if (
    payload.supplier_months !== null &&
    (payload.supplier_months < 0 || payload.supplier_months > LINE_WARRANTY_MAX_MONTHS)
  ) {
    return `مدة كفالة المورّد بين 0 و${formatNumber(LINE_WARRANTY_MAX_MONTHS)} شهراً.`;
  }
  if (payload.manufacturer_warrantor === null && payload.manufacturer_months > 0) {
    return "بلا جهة كفالة مصنع، مدتها يجب أن تكون صفراً.";
  }
  if (payload.manufacturer_warrantor !== null && payload.manufacturer_months === 0) {
    return "اخترت جهة كفالة مصنع — حدّد مدتها بالأشهر، أو أزل الجهة.";
  }
  return null;
}


// ── #236: إلغاء كفالة التاجر ورفضها لهذا العطل ─────────────────────────────

/** أسباب الإلغاء والرفض — مرآة `WarrantyCard.VOID_REASON_CHOICES` حرفياً. */
export const WARRANTY_VOID_REASONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "physical_damage", label: "ضرر مادي" },
  { value: "liquid", label: "تعرّض لسوائل" },
  { value: "opened_outside", label: "فُتح خارج المركز" },
  { value: "tampered", label: "عبث بالأختام أو البرمجيات" },
  { value: "misuse", label: "سوء استخدام" },
  { value: "other", label: "أخرى" },
];

/** الحدّ الأدنى لسبب التراجع/التقصير — مرآة `MIN_UNDO_REASON_CHARS` في الخادم. */
export const WARRANTY_MIN_UNDO_REASON_CHARS = 5;

export const warrantyVoidReasonLabel = (reason: string): string =>
  WARRANTY_VOID_REASONS.find((r) => r.value === reason)?.label ?? "";

/** فحصٌ مبكّر يطابق الخادم: سببٌ من القائمة، و«أخرى» تستلزم ملاحظة. */
export function warrantyVoidProblem(reason: string, note: string): string | null {
  if (!reason) return "اختر سبب الإلغاء.";
  if (!WARRANTY_VOID_REASONS.some((r) => r.value === reason)) return "سبب الإلغاء غير معروف.";
  if (reason === "other" && !note.trim()) return "اكتب ملاحظة توضّح السبب حين يكون «أخرى».";
  return null;
}

/** سبب التراجع أو التقصير: خمسة أحرف فعلية على الأقل بعد حذف الفراغ. */
export const warrantyUndoReasonValid = (reason: string): boolean =>
  (reason || "").trim().length >= WARRANTY_MIN_UNDO_REASON_CHARS;

/**
 * سجلّ البطاقة: التقصير يُسجَّل بنوع «تمديد» و`reason_code="shorten"`، فتسميةُ
 * الخادم وحدها تقرؤه تمديداً — وهو عكسه.
 */
export const warrantyEventLabel = (
  eventType: string,
  reasonCode: string,
  serverLabel: string,
): string => (eventType === "extend" && reasonCode === "shorten" ? "تقصير" : serverLabel);

export interface WarrantyVoidImpactPart {
  product_name: string;
  empty_price: boolean;
}

export interface WarrantyVoidImpactOrder {
  order_number: string;
  returns_to_approval: boolean;
  parts: WarrantyVoidImpactPart[];
}

/** سطرٌ عربيّ لكل أمر صيانة يمسّه الإلغاء — يُعرض في نافذة المعاينة. */
export function warrantyVoidImpactLine(order: WarrantyVoidImpactOrder): string {
  const parts: string[] = [];
  if (order.parts.length > 0) {
    parts.push(`${formatNumber(order.parts.length)} قطعة تُحاسَب بسعر البيع`);
  }
  const empty = order.parts.filter((p) => p.empty_price).length;
  if (empty > 0) {
    parts.push(`${formatNumber(empty)} منها بلا سعر (صفر)`);
  }
  if (order.returns_to_approval) parts.push("يعود إلى انتظار الموافقة");
  return `${order.order_number}: ${parts.length ? parts.join("، ") : "يفقد تغطية الكفالة"}`;
}

// ── #238: طباعة الشهادة وسحب البطاقة اليدوية ──────────────────────────────

/** رسالة النافذة المحجوبة — الطباعة تحتاج نافذةً تُفتح من النقرة نفسها. */
export const WARRANTY_PRINT_BLOCKED_TEXT =
  "منع المتصفح نافذة الطباعة. اسمح بالنوافذ المنبثقة لهذا الموقع ثم أعد المحاولة.";

/** #241: تحذير الإصلاح المدفوع رغم الإحالة — يُعرض قبل القبول ويسجّله الخادم في أحداث الأمر. */
export const REFERRAL_PAID_REPAIR_WARNING =
  "الجهاز ما زال ضمن كفالة المصنع، والإصلاح عندنا قد يُسقطها. هل يصرّ الزبون على إصلاح مدفوع عندنا؟";

/** البطاقة المنتهية (سُحبت أو أُرجع جهازها…) لا تُطبع لها شهادة — يرفضها الخادم. */
export const warrantyCardPrintable = (card: { ended: boolean }): boolean => !card.ended;

/** عدد البطاقات القابلة للطباعة على فاتورة — 0 يُخفي زرّها وشريطها. */
export const countPrintableWarrantyCards = (cards: ReadonlyArray<{ ended: boolean }>): number =>
  cards.filter(warrantyCardPrintable).length;

export const warrantyInvoicePrintLabel = (count: number): string =>
  `اطبع كفالات الفاتورة (${formatNumber(count)})`;

export type WarrantyRemovalMode = "delete" | "withdraw" | "unwithdraw" | null;

/**
 * «حذف» لبطاقةٍ لم يَرَها أحد، و«سحب» لما صدر للزبون، و«تراجع عن السحب» لما سُحب.
 * الحسم للخادم (`can_delete`)؛ التلقائية لا حذف ولا سحب لها (تتبع فاتورتها)،
 * والمنتهية لغير السحب (إرجاع جهاز…) لا يُسحب عليها شيء.
 */
export function warrantyRemovalMode(card: {
  source: WarrantySource;
  can_delete: boolean;
  ended: boolean;
  end_reason: string;
}): WarrantyRemovalMode {
  if (card.source !== "manual") return null;
  if (card.can_delete) return "delete";
  if (card.ended) return card.end_reason === "withdrawn" ? "unwithdraw" : null;
  return "withdraw";
}

/** #237: مصدر `<img>` لرمز QR الخادميّ — data URI فلا يُنفَّذ أي سكربت داخل SVG. */
export function warrantyQrImageSrc(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

// ── #240: الاستقبال الموحّد ────────────────────────────────────────────────

/** مرآة `PHONE_KEY_LENGTH` في `after_sales/models.py` — مفتاح المطابقة آخر تسعة أرقام. */
export const PHONE_KEY_LENGTH = 9;

/**
 * مرآة `phone_key_of` في الخادم: الأرقام الهندية والفارسية تُحوَّل إلى لاتينية،
 * وأي رمز غير رقمي يسقط، وأقصر من تسعة أرقام يعطي فراغاً (لا يُبحث به).
 * للعرض المسبق فقط — الحسم للخادم.
 */
export function phoneKeyOf(raw: string | null | undefined): string {
  const digits = (raw || "")
    .replace(/[\u0660-\u0669]/g, (ch) => String(ch.charCodeAt(0) - 0x0660))
    .replace(/[\u06F0-\u06F9]/g, (ch) => String(ch.charCodeAt(0) - 0x06f0))
    .replace(/\D/g, "");
  return digits.length >= PHONE_KEY_LENGTH ? digits.slice(-PHONE_KEY_LENGTH) : "";
}

/** حكم الاستقبال كما يردّه الخادم (`intake_verdict`) — الواجهة ترسمه ولا تحسبه. */
export type IntakeVerdict = "ended" | "dealer" | "referral" | "voided_paid" | "expired_paid";

export type IntakeVerdictTone = "green" | "grey" | "red";

export const INTAKE_VERDICT_LABELS: Record<IntakeVerdict, string> = {
  dealer: "مغطى بكفالة التاجر",
  referral: "خارج كفالة التاجر — كفالة المصنع سارية: يُحال إلى جهة الكفالة",
  voided_paid: "الكفالة ملغاة — الإصلاح مدفوع",
  expired_paid: "انتهت الكفالة — الإصلاح مدفوع",
  ended: "لم تعد الكفالة سارية (أُرجع الجهاز أو أُلغي البيع) — الإصلاح مدفوع",
};

export const intakeVerdictLabel = (verdict: IntakeVerdict): string =>
  INTAKE_VERDICT_LABELS[verdict] ?? "";

/** الأخضر مكسبٌ للزبون (تغطية أو إحالة)، والأحمر إلغاءٌ بقرار التاجر، وما عداهما رمادي. */
export function intakeVerdictTone(verdict: IntakeVerdict): IntakeVerdictTone {
  if (verdict === "dealer" || verdict === "referral") return "green";
  if (verdict === "voided_paid") return "red";
  return "grey";
}

export const INTAKE_VERDICT_TONE_CLASSES: Record<IntakeVerdictTone, string> = {
  green: "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-200",
  grey: "border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text)]",
  red: "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200",
};

/** نصّ تأكيد قطعة الفاتورة — يطابق ما يشترطه الخادم قبل احتساب التغطية. */
export const INVOICE_PIECE_CONFIRM_TEXT = "تأكّدت أن القطعة من هذه الفاتورة";

export interface DuplicateOpenOrder {
  id: number;
  order_number: string;
  status: string;
  status_display: string;
}

/** الأمر المفتوح الذي رفض الخادم (409 `duplicate_open_order`) الاستقبال بسببه، أو `null` لأي خطأ آخر. */
export function duplicateOpenOrderOf(cause: unknown): DuplicateOpenOrder | null {
  const failure = cause as { status?: number; data?: { code?: string; existing_order?: DuplicateOpenOrder } } | null;
  if (!failure || failure.status !== 409 || failure.data?.code !== "duplicate_open_order") return null;
  return failure.data.existing_order ?? null;
}

/** سبب الفتح رغم الأمر المفتوح: خمسة أحرف فعلية على الأقل، كسبب التراجع. */
export const duplicateReasonValid = (reason: string): boolean => warrantyUndoReasonValid(reason);

/** رابط QR ممسوح (`/api/w/<رمز>`) أو الرمز المجرّد (22 حرفاً) — يُحلّ بـ`resolve-scan` لا بالبحث. */
export function looksLikeWarrantyScan(text: string): boolean {
  const value = (text || "").trim();
  return /^[A-Za-z0-9_-]{22}$/.test(value) || /\/api\/w\/[A-Za-z0-9_-]{22}\/?(?:[?#].*)?$/.test(value);
}


/* ══════════════════════════════════════════════════════════════════════════
 * #242 — سجل الصيانات في البطاقة وشريط الكفالة بطبقتيه (نصوص عرضٍ خالصة)
 * ══════════════════════════════════════════════════════════════════════════ */

/**
 * سطر كفالة التاجر في شريط أمر الصيانة. الملغاة والمنتهية بواقعة لا يُقرآن من
 * تاريخٍ ولا أيام (نهايتهما قد تبقى في المستقبل) — نصّ `warrantyRemainingText` وحده.
 */
export function dealerWarrantyLine(
  status: WarrantyStatus,
  endIso: string | null,
  daysRemaining: number,
): string {
  if (status === "voided" || status === "ended") {
    return `كفالة التاجر: ${warrantyRemainingText(status, daysRemaining)}`;
  }
  return `كفالة التاجر تنتهي ${formatDateValue(endIso)} — ${warrantyRemainingText(status, daysRemaining)}`;
}

/** سطر كفالة المصنع — فارغٌ حين لا جهة (`null`/غائب): لا سطر يُرسم، لا «لا يوجد». */
export function manufacturerWarrantyLine(
  status: WarrantyStatus | null | undefined,
  endIso: string | null,
  daysRemaining: number | null,
  warrantorName: string,
): string {
  if (!status) return "";
  const who = warrantorName ? `كفالة المصنع (${warrantorName})` : "كفالة المصنع";
  if (status === "voided" || status === "ended") {
    return `${who}: ${warrantyRemainingText(status, daysRemaining ?? 0)}`;
  }
  return `${who} تنتهي ${formatDateValue(endIso)} — ${warrantyRemainingText(status, daysRemaining ?? 0)}`;
}

export const warrantyOrderCoverageLabel = (covered: boolean): string =>
  covered ? "مغطّى بالكفالة" : "مدفوع";

/** نص حدثٍ في السجل: «تمديد: من ← إلى — النص». */
export function warrantyTimelineEventText(event: {
  event_type: string;
  event_type_label: string;
  reason_code: string;
  text: string;
  old_end_date: string | null;
  new_end_date: string | null;
}): string {
  let line = warrantyEventLabel(event.event_type, event.reason_code, event.event_type_label);
  if (event.old_end_date && event.new_end_date) {
    line += `: ${formatDateValue(event.old_end_date)} ← ${formatDateValue(event.new_end_date)}`;
  }
  if (event.text) line += ` — ${event.text}`;
  return line;
}

/** روابط عميقة تستهلكها الشاشتان القائمتان (`?order=` و`?card=`) — بلا مسار جديد. */
export const warrantyServiceOrderLink = (orderId: number): string =>
  `/after-sales/service-orders?order=${orderId}`;
export const warrantyCardLink = (cardId: number): string => `/after-sales?card=${cardId}`;
