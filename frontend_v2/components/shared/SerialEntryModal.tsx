/**
 * T-SERIAL: نافذة الأرقام التسلسلية لبند مستند — واحدة للشراء والبيع.
 *
 * `capture` (الشراء): الوحدة تدخل المخزن الآن، فالأرقام تُنشأ — إمّا برقم بداية
 * وعدد فتُولَّد السلسلة **من الخادم** (قاعدة التزايد مكانها واحد)، أو واحداً
 * واحداً بالمسح/الكتابة. عدد الأرقام هو الكمية: المالك يبدأ من رقم والعدد يقود
 * الأكواد، فالكمية تتبع القائمة لا العكس.
 *
 * `pick` (البيع): الوحدة موجودة أصلاً، فالمستخدم يختار **أيّها** يخرج — من قائمة
 * «في المخزن» لهذا الصنف، بالبحث أو بالمسح. و«تلقائي» خيار صريح لا فراغ: لا
 * يرسل أرقاماً ويترك الخادم يخصّص الأقدم (FIFO).
 *
 * الإلزام كله خادمي؛ ما هنا إرشادٌ يمنع الخطأ قبل وقوعه لا حارسٌ يُعتمد عليه.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Hash, Loader2, Plus, Search, Trash2, X } from "lucide-react";
import { inventoryApi, type ProductSerialRow } from "../../services/inventoryApi";
import { humanizeThrown } from "../../utils/drfError";

interface Props {
  mode: "capture" | "pick";
  productId: number;
  productName: string;
  /** كمية البند الحالية — مرجع العدّ («المختار 2 من 3»). */
  quantity: number;
  /** الأرقام المحفوظة على البند. */
  value: string[];
  /** النمط `required` — يُظهر نقص العدد بوضوح (والمنع نفسه عند الترحيل). */
  required?: boolean;
  readOnly?: boolean;
  onClose: () => void;
  /** `capture` يعيد الأرقام والكمية الجديدة معاً؛ `pick` يعيد المختار فقط. */
  onSave: (serials: string[]) => void;
}

const clean = (raw: string) => raw.trim();

export const SerialEntryModal: React.FC<Props> = ({
  mode,
  productId,
  productName,
  quantity,
  value,
  required = false,
  readOnly = false,
  onClose,
  onSave,
}) => {
  const [serials, setSerials] = useState<string[]>(() => value.filter(Boolean));
  const [start, setStart] = useState("");
  const [count, setCount] = useState(() => {
    const remaining = Math.max(0, Math.trunc(quantity) - value.filter(Boolean).length);
    return String(remaining > 0 ? remaining : Math.max(1, Math.trunc(quantity) || 1));
  });
  const [scan, setScan] = useState("");
  const [search, setSearch] = useState("");
  const [pool, setPool] = useState<ProductSerialRow[]>([]);
  const [loading, setLoading] = useState(mode === "pick");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** «تلقائي» = لا أرقام على البند؛ الخادم يخصّص الأقدم عند الترحيل. */
  const [auto, setAuto] = useState(() => mode === "pick" && value.filter(Boolean).length === 0);
  const scanRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    scanRef.current?.focus();
  }, []);

  useEffect(() => {
    if (mode !== "pick") return;
    let cancelled = false;
    setLoading(true);
    inventoryApi
      .getProductSerials(productId, "in_stock")
      .then((rows) => { if (!cancelled) { setPool(rows); setError(null); } })
      .catch((e) => { if (!cancelled) setError(humanizeThrown(e, "تعذّر تحميل وحدات هذا الصنف")); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [mode, productId]);

  /** أرقام مختارة على البند لم تعد «في المخزن» (فاتورة مرحّلة تُعاد قراءتها). */
  const chosenOutsidePool = useMemo(() => {
    const inPool = new Set(pool.map((r) => r.serial));
    return serials.filter((s) => !inPool.has(s));
  }, [pool, serials]);

  const duplicates = useMemo(() => {
    const seen = new Set<string>();
    const dupes = new Set<string>();
    for (const s of serials) {
      if (seen.has(s)) dupes.add(s);
      seen.add(s);
    }
    return dupes;
  }, [serials]);

  const wholeQty = Math.max(0, Math.trunc(quantity));
  const chosenCount = auto ? 0 : serials.length;
  // في الشراء الكمية تتبع القائمة، فلا نقص إلا حين تُترك القائمة فارغة تماماً.
  const incomplete = required && (mode === "capture" ? serials.length === 0 : chosenCount !== wholeQty);

  /** التكرار يُقال لا يُبتلَع: رقمان متطابقان وحدتان لا تُفرَّقان، وإسقاط أحدهما
   *  بصمت يُنقص العدد بلا إخبار (نفس قاعدة `normalize_serials` خادمياً). */
  const addSerial = useCallback((raw: string, current: string[]) => {
    const serial = clean(raw);
    if (!serial) return;
    if (current.includes(serial)) {
      setError(`الرقم «${serial}» مُدخَل مسبقاً في هذا البند.`);
      return;
    }
    setError(null);
    setSerials([...current, serial]);
  }, []);

  const removeSerial = (index: number) =>
    setSerials((prev) => prev.filter((_, i) => i !== index));

  const generate = async () => {
    const from = clean(start);
    if (!from) {
      setError("اكتب رقم البداية أولاً — مثال: SN-0098.");
      return;
    }
    const howMany = Number(count);
    if (!Number.isFinite(howMany) || howMany < 1) {
      setError("عدد الوحدات يجب أن يكون 1 أو أكثر.");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const generated = await inventoryApi.generateSerials(from, Math.trunc(howMany));
      const merged = [...serials];
      const skipped: string[] = [];
      for (const s of generated) {
        if (merged.includes(s)) skipped.push(s);
        else merged.push(s);
      }
      setSerials(merged);
      setError(skipped.length
        ? `أرقام مُدخَلة مسبقاً لم تُضَف: ${skipped.join("، ")}`
        : null);
      setStart("");
    } catch (e) {
      setError(humanizeThrown(e, "تعذّر توليد الأرقام"));
    } finally {
      setGenerating(false);
    }
  };

  /** المسح في وضع الاختيار: الرقم الممسوح يُختار من المتاح لا يُنشأ. */
  const scanPick = (raw: string) => {
    const serial = clean(raw);
    if (!serial) return;
    const hit = pool.find((r) => r.serial === serial);
    if (!hit) {
      setError(`الرقم «${serial}» غير متوفر في مخزن هذا الصنف.`);
      return;
    }
    setError(null);
    setAuto(false);
    setSerials((prev) => (prev.includes(serial) ? prev : [...prev, serial]));
    setScan("");
  };

  const togglePick = (serial: string) => {
    setAuto(false);
    setSerials((prev) =>
      prev.includes(serial) ? prev.filter((s) => s !== serial) : [...prev, serial],
    );
  };

  const filteredPool = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return pool;
    return pool.filter((r) => r.serial.toLowerCase().includes(term));
  }, [pool, search]);

  const submit = () => {
    if (duplicates.size > 0) {
      setError("هناك أرقام مكرّرة — احذف التكرار قبل الحفظ.");
      return;
    }
    onSave(auto && mode === "pick" ? [] : serials);
  };

  const title = mode === "capture" ? "الأرقام التسلسلية للبند" : "اختيار الوحدات المباعة";

  return (
    <div
      dir="rtl"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3 sm:p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl aseel-bg-field dark:aseel-bg-panel shadow-xl border aseel-border-soft">
        <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b aseel-border-soft sticky top-0 aseel-bg-field dark:aseel-bg-panel">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-[var(--color-primary)] text-white rounded-xl">
              <Hash className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base sm:text-lg font-bold aseel-text-ink dark:text-white">{title}</h3>
              <p className="text-xs aseel-text-soft">{productName}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 aseel-text-soft hover:aseel-bg-panel rounded-lg"
            aria-label="إغلاق"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 sm:p-6 space-y-4">
          {error && (
            <div className="p-3 rounded-lg aseel-bg-panel aseel-text-state text-sm border aseel-border-soft">
              {error}
            </div>
          )}

          {mode === "capture" ? (
            <>
              <div className="rounded-lg border aseel-border-soft p-3 space-y-2">
                <div className="text-xs font-bold aseel-text-ink dark:aseel-text-soft">
                  توليد سلسلة — ابدأ برقم والعدد يزيد الكود تلقائياً
                </div>
                <div className="flex flex-wrap items-end gap-2">
                  <label className="flex flex-col gap-1 flex-1 min-w-[160px]">
                    <span className="text-[11px] aseel-text-soft">رقم البداية</span>
                    <input
                      className="h-9 px-2 border aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel text-sm"
                      dir="ltr"
                      disabled={readOnly || generating}
                      value={start}
                      onChange={(e) => setStart(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") { e.preventDefault(); void generate(); }
                      }}
                      placeholder="SN-0098"
                    />
                  </label>
                  <label className="flex flex-col gap-1 w-24">
                    <span className="text-[11px] aseel-text-soft">عدد الوحدات</span>
                    <input
                      type="number"
                      min={1}
                      className="h-9 px-2 border aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel text-sm text-center"
                      disabled={readOnly || generating}
                      value={count}
                      onChange={(e) => setCount(e.target.value)}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => void generate()}
                    disabled={readOnly || generating}
                    className="h-9 flex items-center gap-1.5 px-4 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] disabled:opacity-50 text-white rounded-lg text-sm font-medium"
                  >
                    {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                    توليد
                  </button>
                </div>
              </div>

              <label className="flex flex-col gap-1">
                <span className="text-[11px] aseel-text-soft">أو امسح/اكتب رقماً واحداً ثم ⏎</span>
                <input
                  ref={scanRef}
                  className="h-9 px-2 border aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel text-sm"
                  dir="ltr"
                  disabled={readOnly}
                  value={scan}
                  onChange={(e) => setScan(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter") return;
                    e.preventDefault();
                    addSerial(scan, serials);
                    setScan("");
                  }}
                  placeholder="امسح الباركود أو اكتب الرقم ⏎"
                />
              </label>
            </>
          ) : (
            <>
              <label className="flex items-start gap-2 rounded-lg border aseel-border-soft p-3 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  disabled={readOnly}
                  checked={auto}
                  onChange={(e) => {
                    setAuto(e.target.checked);
                    if (e.target.checked) setSerials([]);
                  }}
                />
                <span className="text-sm">
                  <b className="aseel-text-ink dark:text-white">تلقائي — أي وحدة</b>
                  <span className="block text-[11px] aseel-text-soft">
                    بلا اختيار: يخصّص الخادم أقدم الوحدات المتاحة عند الترحيل.
                  </span>
                </span>
              </label>

              <div className="flex flex-wrap gap-2">
                <div className="relative flex-1 min-w-[160px]">
                  <div className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none">
                    <Search className="w-3.5 h-3.5 aseel-text-soft" />
                  </div>
                  <input
                    className="w-full h-9 pr-7 px-2 border aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel text-sm"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="ابحث عن رقم…"
                  />
                </div>
                <input
                  ref={scanRef}
                  className="h-9 px-2 border aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel text-sm flex-1 min-w-[160px]"
                  dir="ltr"
                  disabled={readOnly}
                  value={scan}
                  onChange={(e) => setScan(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter") return;
                    e.preventDefault();
                    scanPick(scan);
                  }}
                  placeholder="امسح الرقم لاختياره ⏎"
                />
              </div>
            </>
          )}

          {/* القائمة — المُدخَل (شراء) أو المتاح للاختيار (بيع) */}
          {mode === "capture" ? (
            <div className="rounded-lg border aseel-border-soft overflow-hidden">
              {serials.length === 0 ? (
                <div className="py-8 text-center aseel-text-soft text-sm">
                  لا أرقام بعد — ولّد سلسلة أو امسح رقماً.
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="aseel-bg-panel aseel-text-soft text-xs">
                    <tr>
                      <th className="px-2 py-2 w-10 text-center font-medium">#</th>
                      <th className="px-3 py-2 text-right font-medium">الرقم التسلسلي</th>
                      <th className="px-2 py-2 w-12" />
                    </tr>
                  </thead>
                  <tbody>
                    {serials.map((s, i) => (
                      <tr key={`${s}-${i}`} className="border-t aseel-border-soft">
                        <td className="px-2 py-1.5 text-center aseel-text-soft">{i + 1}</td>
                        <td
                          className={`px-3 py-1.5 font-mono ${duplicates.has(s) ? "text-red-600 font-bold" : "aseel-text-ink dark:aseel-text-soft"}`}
                          dir="ltr"
                        >
                          {s}
                          {duplicates.has(s) && (
                            <span dir="rtl" className="mr-2 text-[11px] font-sans">مكرَّر</span>
                          )}
                        </td>
                        <td className="px-2 py-1.5 text-center">
                          {!readOnly && (
                            <button
                              type="button"
                              onClick={() => removeSerial(i)}
                              className="p-1 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                              title="حذف الرقم"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ) : (
            <div className="rounded-lg border aseel-border-soft overflow-hidden max-h-64 overflow-y-auto">
              {loading ? (
                <div className="flex items-center gap-2 justify-center py-8 aseel-text-soft">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>جارٍ التحميل…</span>
                </div>
              ) : filteredPool.length === 0 && chosenOutsidePool.length === 0 ? (
                <div className="py-8 text-center aseel-text-soft text-sm">
                  لا وحدات مُرقَّمة في مخزن هذا الصنف — «تلقائي» يترك البند بلا تتبّع.
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="aseel-bg-panel aseel-text-soft text-xs sticky top-0">
                    <tr>
                      <th className="px-2 py-2 w-10" />
                      <th className="px-3 py-2 text-right font-medium">الرقم التسلسلي</th>
                      <th className="px-3 py-2 text-right font-medium">مصدر الوحدة</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chosenOutsidePool.map((s) => (
                      <tr key={`kept-${s}`} className="border-t aseel-border-soft">
                        <td className="px-2 py-1.5 text-center">
                          <input
                            type="checkbox"
                            checked
                            disabled={readOnly}
                            onChange={() => togglePick(s)}
                            aria-label={s}
                          />
                        </td>
                        <td className="px-3 py-1.5 font-mono" dir="ltr">{s}</td>
                        <td className="px-3 py-1.5 aseel-text-soft text-xs">مختار على هذا البند</td>
                      </tr>
                    ))}
                    {filteredPool.map((row) => (
                      <tr key={row.id} className="border-t aseel-border-soft">
                        <td className="px-2 py-1.5 text-center">
                          <input
                            type="checkbox"
                            checked={serials.includes(row.serial)}
                            disabled={readOnly}
                            onChange={() => togglePick(row.serial)}
                            aria-label={row.serial}
                          />
                        </td>
                        <td className="px-3 py-1.5 font-mono" dir="ltr">{row.serial}</td>
                        <td className="px-3 py-1.5 aseel-text-soft text-xs">
                          {row.purchase_invoice_number
                            ? `فاتورة ${row.purchase_invoice_number}${row.supplier_name ? ` — ${row.supplier_name}` : ""}`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t aseel-border-soft">
            <div className="text-xs">
              {mode === "capture" ? (
                <span className={incomplete ? "text-red-600 font-bold" : "aseel-text-ink dark:aseel-text-soft"}>
                  {serials.length > 0
                    ? <>عدد الأرقام: <b>{serials.length}</b> — كمية البند ستصبح <b>{serials.length}</b></>
                    : <>لا أرقام — الكمية تبقى <b>{wholeQty}</b>{required ? " والترحيل سيُرفض" : ""}</>}
                </span>
              ) : (
                <span className={incomplete ? "text-red-600 font-bold" : "aseel-text-ink dark:aseel-text-soft"}>
                  المختار: <b>{chosenCount}</b> من الكمية <b>{wholeQty}</b>
                  {auto && <span className="aseel-text-soft"> — تخصيص تلقائي</span>}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 aseel-text-ink dark:aseel-text-soft aseel-bg-panel rounded-lg"
              >
                إلغاء
              </button>
              <button
                onClick={submit}
                disabled={readOnly || duplicates.size > 0}
                className="px-5 py-2 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium"
              >
                حفظ الأرقام
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SerialEntryModal;
