/**
 * T-SCAN — «ما الذي في يدي؟»: لوحةٌ واحدة تحلّ الباركود والسيريال والـIMEI
 * ورمز الصنف وجزءَ الاسم، بلا أن يختار المستخدم النوع.
 *
 * **لماذا لوحةٌ لا شاشة**: المسح فعلٌ عابر أثناء عملٍ آخر — الموظف على الطاولة
 * والزبون أمامه يناوله علبة. إخراجُه من شاشته إلى شاشة بحثٍ يُفقده سياقه ثم
 * يُلزمه الرجوع. اللوحة تُفتح فوق ما هو فيه وتُغلق فيعود حيث كان، وما يحتاج
 * متابعةً (الفاتورة، كرت الصنف) يُفتح في **تبويب** لا في مكان عمله.
 *
 * **الخادم يقرّر والواجهة تعرض**: نوعُ الرقم (`kind`) ونطاقُ الصلاحية (`scope`)
 * وترتيبُ المطابقات كلّها تصل محسوبةً من `core/scan.py`. لا Luhn هنا ولا خانة
 * تحقّق EAN ولا فحصَ صلاحية — نسخةٌ ثانية من قاعدة هي انحرافٌ ينتظر موعده.
 *
 * **الكاميرا وHTTPS**: `getUserMedia` مقفولة على غير السياق الآمن بقرار
 * المتصفح. الزرّ يُعطَّل ويشرح **قبل** الضغط لا بعده — زرٌّ يُضغط فيفشل أسوأ من
 * زرٍّ مُعطَّل مكتوبٍ سببه.
 *
 * **ولماذا `createPortal`**: مستدعيها الأول زرٌّ في `.app-header`، وتلك عنصرٌ
 * `sticky` بـ`z-index: 50` — أي **سياق تكديس**. فطبقةٌ `fixed` مولودةٌ داخله
 * تبقى محبوسةً فيه مهما رُفع رقمها، فتظهر تحت الترويسة نفسها ومقصوصةً بها.
 * ظهر ذلك في أول تصويرٍ للوحة: البطاقة تُرسَم والترويسة فوقها. الحقن في
 * `document.body` يُخرجها من السياق إلى جذر الصفحة حيث تنتمي الطبقات.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  AlertCircle, Camera, Loader2, PackageSearch, Search, ShieldCheck,
  ShieldOff, Smartphone, Wrench, X,
} from "lucide-react";
import { openInNewTab } from "@/utils/openInNewTab";
import { formatDateLocalized } from "../../utils/formatDate";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { humanizeThrown } from "../../utils/drfError";
import {
  scanApi,
  type ScanDeviceMatch,
  type ScanKind,
  type ScanProductMatch,
  type ScanResult,
  type ScanUnitMatch,
} from "../../services/scanApi";
import { BarcodeScannerModal } from "./BarcodeScannerModal";

/** مهلة التهدئة قبل النداء — الكتابة اليدوية تُطلق حرفاً بعد حرف. */
const DEBOUNCE_MS = 350;

/** أقصر نصّ يستحقّ نداءً — حرفٌ واحد يُرجع نصف الكتالوج بلا فائدة. */
const MIN_TERM = 2;

const KIND_LABEL: Record<ScanKind, string> = {
  imei: "IMEI",
  barcode: "باركود",
  text: "نصّ",
};

const MATCHED_ON_LABEL: Record<ScanProductMatch["matched_on"], string> = {
  barcode: "مطابقة باركود",
  sku: "مطابقة رمز الصنف",
  partial: "مطابقة جزئية",
};

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">{label}</span>
    <span className="text-[var(--font-size-sm)] text-[var(--color-text)]">{children}</span>
  </div>
);

/** رابطٌ يفتح مستنداً في تبويب — النصّ وحده حين لا مستند خلفه. */
const DocLink: React.FC<{ href: string | null; label: string | null }> = ({ href, label }) => {
  if (!label) return <span className="text-[var(--color-text-muted)]">—</span>;
  if (!href) return <>{label}</>;
  return (
    <button
      type="button"
      onClick={() => openInNewTab(href, label)}
      className="text-[var(--color-primary)] underline underline-offset-2 hover:opacity-80"
    >
      {label}
    </button>
  );
};

/* ─────────────────────────── بطاقة القطعة ─────────────────────────── */

const UnitCard: React.FC<{ unit: ScanUnitMatch }> = ({ unit }) => {
  const sold = unit.status === "sold";
  const warranty = unit.warranty;
  const activeCard = warranty?.cards.find((card) => card.status === "active")
    ?? warranty?.cards[0]
    ?? null;

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Smartphone className="h-4 w-4 text-[var(--color-primary)]" />
        <span className="font-semibold text-[var(--color-text)]">{unit.product_name}</span>
        <span className="rounded bg-[var(--color-muted)] px-1.5 py-0.5 text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
          {unit.product_sku}
        </span>
        <span
          className={`rounded px-1.5 py-0.5 text-[var(--font-size-xs)] ${
            sold
              ? "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200"
              : "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
          }`}
        >
          {unit.status_display}
        </span>
        <span className="ms-auto font-mono text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
          {unit.serial}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Field label="المورد">{unit.supplier_name || "—"}</Field>
        <Field label="فاتورة الشراء">
          <DocLink
            href={unit.purchase_invoice ? `/purchase-invoices/${unit.purchase_invoice}` : null}
            label={unit.purchase_invoice_number}
          />
        </Field>
        <Field label="تاريخ الشراء">
          {unit.purchase_date ? formatDateLocalized(unit.purchase_date) : "—"}
        </Field>
        {/* «سعر الشراء» لا «التكلفة»: التكلفة المستوردة تُبنى فوقه بالشحن
            والتخليص، وتسميتُه تكلفةً تجعل الموظف يسعّر مقايضةً برقمٍ ناقص. */}
        <Field label="سعر الشراء">
          {unit.purchase_unit_price ? formatMoney(unit.purchase_unit_price) : "—"}
        </Field>

        <Field label="العميل">{unit.customer_name || "—"}</Field>
        <Field label="هاتف العميل">{unit.customer_phone || "—"}</Field>
        <Field label="فاتورة البيع">
          <DocLink
            href={unit.sales_invoice ? `/sales/invoices/${unit.sales_invoice}` : null}
            label={unit.sales_invoice_number}
          />
        </Field>
        <Field label="تاريخ البيع">
          {unit.sold_at ? formatDateLocalized(unit.sold_at) : "—"}
        </Field>
      </div>

      {/* الكفالة — تغيب كلّها حين لا تكون وحدة «ما بعد البيع» مرخَّصةً أو
          مصرّحاً بها، ولا يُقال للمستخدم إن هناك ما لا يراه. */}
      {warranty && (
        <div
          className={`mt-3 flex flex-wrap items-center gap-2 rounded-md px-2.5 py-2 ${
            warranty.covered
              ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-900/25 dark:text-emerald-100"
              : "bg-[var(--color-muted)] text-[var(--color-text-muted)]"
          }`}
          data-testid="scan-warranty"
        >
          {warranty.covered
            ? <ShieldCheck className="h-4 w-4" />
            : <ShieldOff className="h-4 w-4" />}
          <span className="text-[var(--font-size-sm)] font-medium">
            {warranty.covered ? "الكفالة سارية" : "لا كفالة سارية"}
          </span>
          {activeCard?.end_date && (
            <span className="text-[var(--font-size-xs)]">
              حتى {formatDateLocalized(activeCard.end_date)}
              {typeof activeCard.days_remaining === "number" && activeCard.days_remaining >= 0
                ? ` — يتبقّى ${formatQuantity(activeCard.days_remaining)} يوماً`
                : ""}
            </span>
          )}
          {warranty.supplier_covered && (
            <span className="rounded bg-[var(--color-surface)] px-1.5 py-0.5 text-[var(--font-size-xs)]">
              كفالة المورد سارية
            </span>
          )}
        </div>
      )}

      {/* سجلّ الصيانات — «مسح الرقم يستدعي سجلّ القطعة كاملاً». */}
      {unit.service_orders.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 flex items-center gap-1.5 text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
            <Wrench className="h-3.5 w-3.5" />
            صيانات سابقة ({formatQuantity(unit.service_orders.length)})
          </div>
          <ul className="flex flex-col gap-1">
            {unit.service_orders.map((order) => (
              <li
                key={order.id}
                className="flex flex-wrap items-center gap-2 rounded border border-[var(--color-border)] px-2 py-1 text-[var(--font-size-sm)]"
              >
                <span className="font-medium">{order.order_number || `#${order.id}`}</span>
                <span className="text-[var(--color-text-muted)]">
                  {order.order_date ? formatDateLocalized(order.order_date) : "—"}
                </span>
                <span className="rounded bg-[var(--color-muted)] px-1.5 py-0.5 text-[var(--font-size-xs)]">
                  {order.status_display}
                </span>
                <span className="truncate text-[var(--color-text-muted)]">{order.complaint}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

/* ─────────────────────────── صفوف أخفّ ─────────────────────────── */

const DeviceRow: React.FC<{ device: ScanDeviceMatch }> = ({ device }) => (
  <button
    type="button"
    onClick={() => openInNewTab("/sensitive-devices", "سجل الأجهزة الحساسة")}
    className="flex w-full flex-wrap items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-start hover:bg-[var(--color-muted)]"
  >
    <Smartphone className="h-4 w-4 text-[var(--color-text-muted)]" />
    <span className="font-medium text-[var(--color-text)]">{device.model_name}</span>
    <span className="rounded bg-[var(--color-muted)] px-1.5 py-0.5 text-[var(--font-size-xs)]">
      {device.status_display}
    </span>
    <span className="text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
      {device.customer_name} · {device.customer_phone}
    </span>
    <span className="ms-auto font-mono text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
      {device.imei || device.serial_number}
    </span>
  </button>
);

const ProductRow: React.FC<{ product: ScanProductMatch }> = ({ product }) => (
  <button
    type="button"
    onClick={() => openInNewTab(`/products/${product.id}`, "كرت الصنف")}
    className="flex w-full flex-wrap items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-start hover:bg-[var(--color-muted)]"
  >
    <PackageSearch className="h-4 w-4 text-[var(--color-text-muted)]" />
    <span className="font-medium text-[var(--color-text)]">{product.name}</span>
    <span className="rounded bg-[var(--color-muted)] px-1.5 py-0.5 text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
      {product.sku}
    </span>
    {product.brand && (
      <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
        {product.brand}
      </span>
    )}
    {/* اليقين موسومٌ يقيناً والترجيح ترجيحاً — كي لا يُقرأ سطرٌ مرجَّح يقيناً. */}
    <span
      className={`rounded px-1.5 py-0.5 text-[var(--font-size-xs)] ${
        product.matched_on === "partial"
          ? "bg-[var(--color-muted)] text-[var(--color-text-muted)]"
          : "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200"
      }`}
    >
      {MATCHED_ON_LABEL[product.matched_on]}
    </span>
    <span className="ms-auto text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
      الرصيد {formatQuantity(product.quantity_on_hand)} · {formatMoney(product.sale_price)}
    </span>
  </button>
);

/* ─────────────────────────── اللوحة ─────────────────────────── */

export const ScanLookupPanel: React.FC<{
  onClose: () => void;
  /** ما يُعرض قبل الكتابة — المستدعي يملأه بما يفيد في مكانه (روابط سريعة
   *  مثلاً). حالة الفراغ مساحةٌ مهدورة لو تُركت نصّاً إرشادياً وحده. */
  emptyState?: React.ReactNode;
}> = ({ onClose, emptyState }) => {
  const [term, setTerm] = useState("");
  const [result, setResult] = useState<ScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [camera, setCamera] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  /** كل نداء يحمل رقم جيله: ردٌّ متأخّر لنصٍّ قديم لا يدهس ردّ النصّ الحالي. */
  const generation = useRef(0);

  // الكاميرا مقفولة على غير السياق الآمن بقرار المتصفح لا بقرارنا.
  const secure = typeof window !== "undefined" && window.isSecureContext;

  useEffect(() => { inputRef.current?.focus(); }, []);

  const run = useCallback(async (raw: string) => {
    const value = raw.trim();
    const mine = ++generation.current;
    if (value.length < MIN_TERM) {
      setResult(null);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const payload = await scanApi.lookup(value);
      if (generation.current === mine) setResult(payload);
    } catch (cause) {
      if (generation.current === mine) {
        setResult(null);
        setError(humanizeThrown(cause));
      }
    } finally {
      if (generation.current === mine) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void run(term), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [term, run]);

  /** قراءة الكاميرا تُطلق النداء فوراً — لا تهدئة على فعلٍ مقصود واحد. */
  const onDetect = useCallback((value: string) => {
    setTerm(value);
    void run(value);
  }, [run]);

  const units = useMemo(
    () => (result?.matches.filter((m): m is ScanUnitMatch => m.type === "unit") ?? []),
    [result],
  );
  const devices = useMemo(
    () => (result?.matches.filter((m): m is ScanDeviceMatch => m.type === "device") ?? []),
    [result],
  );
  const products = useMemo(
    () => (result?.matches.filter((m): m is ScanProductMatch => m.type === "product") ?? []),
    [result],
  );

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-black/50 p-0 sm:p-6"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      data-testid="scan-panel"
    >
      {/* `--color-surface` لا `--color-bg`: الثاني **غير موجود** في نظام الألوان
          (`styles/index.css` يعرّف `--color-surface` و`--color-muted` ولا يعرّفه)،
          و`var()` بلا قيمة يسقط إلى شفّاف — فكانت اللوحة زجاجاً يظهر خلفه محتوى
          الصفحة. أمسكه تصويرُ العنصر وحده: الاختبارات كلّها خضراء عليه. */}
      <div
        className="flex h-full w-full flex-col overflow-hidden border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl sm:h-auto sm:max-h-[85vh] sm:max-w-3xl sm:rounded-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-[var(--color-border)] px-4 py-3">
          <Search className="h-4 w-4 text-[var(--color-primary)]" />
          <h2 className="font-semibold text-[var(--color-text)]">التعرّف على رقم</h2>
          <button
            type="button"
            onClick={onClose}
            className="ms-auto rounded p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-muted)]"
            aria-label="إغلاق"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="border-b border-[var(--color-border)] px-4 py-3">
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              value={term}
              onChange={(event) => setTerm(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") void run(term); }}
              placeholder="باركود · رقم تسلسلي · IMEI · رمز الصنف · جزء من الاسم"
              className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-[var(--font-size-sm)] text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"
              data-testid="scan-input"
            />
            <button
              type="button"
              onClick={() => setCamera(true)}
              disabled={!secure}
              title={
                secure
                  ? "مسح بالكاميرا"
                  : "الكاميرا لا تعمل على اتصال غير آمن — افتح النظام عبر HTTPS"
              }
              className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-2 text-[var(--font-size-sm)] text-[var(--color-text)] hover:bg-[var(--color-muted)] disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="scan-camera"
            >
              <Camera className="h-4 w-4" />
              <span className="hidden sm:inline">كاميرا</span>
            </button>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-2 text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
            {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {result && term.trim().length >= MIN_TERM && (
              <span className="rounded bg-[var(--color-muted)] px-1.5 py-0.5">
                قُرئ كـ{KIND_LABEL[result.kind]}
              </span>
            )}
            {/* الشرط يُقال قبل الضغط لا بعده — الفشل الصامت هو ما نتجنّبه. */}
            {!secure && (
              <span className="flex items-center gap-1 text-amber-700 dark:text-amber-300">
                <AlertCircle className="h-3.5 w-3.5" />
                الكاميرا تتطلّب HTTPS — الكتابة والماسح اليدوي يعملان على أي اتصال.
              </span>
            )}
          </div>
        </div>

        {/* أرضية النتائج أغمق درجةً من اللوحة كي تبرز البطاقات فوقها — وكلاهما
            على `--color-surface` كان سيجعل الحدود وحدها تفصلهما. */}
        <div className="flex flex-1 flex-col gap-2 overflow-y-auto bg-[var(--color-muted)] px-4 py-3">
          {error && (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-[var(--font-size-sm)] text-red-800 dark:bg-red-900/30 dark:text-red-200">
              {error}
            </div>
          )}

          {units.map((unit) => <UnitCard key={`u-${unit.id}`} unit={unit} />)}
          {devices.map((device) => <DeviceRow key={`d-${device.id}`} device={device} />)}
          {products.map((product) => <ProductRow key={`p-${product.id}`} product={product} />)}

          {result?.unregistered && (
            <div
              className="flex flex-col gap-2 rounded-lg border border-dashed border-[var(--color-border)] px-3 py-4 text-center"
              data-testid="scan-unregistered"
            >
              <span className="text-[var(--font-size-sm)] font-medium text-[var(--color-text)]">
                غير مسجَّل — لا صنف ولا وحدة ولا جهاز بهذا الرقم.
              </span>
              <div className="flex flex-wrap justify-center gap-2">
                {/* لا زرّ «سجّل رقماً تسلسلياً» هنا: الترقيم يصف مخزوناً قائماً
                    ويلزمه صنفٌ ورصيدٌ يسقُفه (`register_existing_serials`)،
                    ومدخلُه كرت الصنف. زرٌّ يقود إلى طريق مسدود أسوأ من غيابه. */}
                {result.scope.devices && (
                  <button
                    type="button"
                    onClick={() => openInNewTab("/sensitive-devices", "سجل الأجهزة الحساسة")}
                    className="rounded-lg bg-[var(--color-primary)] px-3 py-1.5 text-[var(--font-size-sm)] text-white hover:opacity-90"
                  >
                    سجّله جهازاً حسّاساً
                  </button>
                )}
                {result.scope.products && (
                  <button
                    type="button"
                    onClick={() => openInNewTab("/items", "الأصناف")}
                    className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-[var(--font-size-sm)] text-[var(--color-text)] hover:bg-[var(--color-muted)]"
                  >
                    ابحث في الأصناف
                  </button>
                )}
              </div>
            </div>
          )}

          {!result && !loading && !error && (
            <>
              <p className="px-1 pb-2 pt-4 text-center text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
                امسح الملصق أو اكتب الرقم — يُعرَف نوعه من شكله بلا اختيار منك.
              </p>
              {emptyState}
            </>
          )}
        </div>
      </div>

      {camera && (
        <BarcodeScannerModal
          title="مسح الرقم بالكاميرا"
          hint="صوّب على الملصق — الباركود أو رقم الجهاز"
          onDetect={onDetect}
          onClose={() => setCamera(false)}
        />
      )}
    </div>,
    document.body,
  );
};

export default ScanLookupPanel;
