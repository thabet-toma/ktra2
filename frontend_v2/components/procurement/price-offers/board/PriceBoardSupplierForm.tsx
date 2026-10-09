/**
 * نموذج عمود المورد في جدول الأسعار (PB-2) — إضافةً وتعديلاً بالحقول نفسها.
 *
 * - المورد: `KitAutocomplete` على الموردين الدوليين، والنص الحر مسموح (مورّد لم
 *   يُسجَّل بعد) — الوسم يقول أيهما.
 * - ملف العرض بطريقتين متجاورتين: رابط (Drive وغيره، http(s) حصراً) أو رفع ملف
 *   (صورة/PDF/Excel). فشل الرفع رسالةٌ لا تعطّل الرابط.
 * - سعر الصرف: مخفيّ في الإضافة حتى يردّ الخادم 400 على `exchange_rate` (لا سعر
 *   معرَّف لهذه العملة)، فتظهر الخانة مع رسالة الخادم ويُعاد الإرسال بها.
 */
import React, { useEffect, useMemo, useState } from "react";
import { Loader2, Paperclip, X } from "lucide-react";
import { KitAutocomplete, type KitAutocompleteOption } from "../../../kit/KitAutocomplete";
import { KitDateInput } from "../../../kit/KitDateInput";
import { FileDropZone } from "../../../ui/FileDropZone";
import { cloudinaryService } from "../../../../services/cloudinaryService";
import {
  listBoardCurrencies,
  type BoardCurrency,
  type PriceBoardAttachment,
  type PriceBoardSupplierDto,
  type PriceBoardSupplierWrite,
} from "../../../../services/priceBoardApi";
import type { Supplier } from "../../../../types/supplier";
import { isHttpUrl } from "../../../../utils/priceBoard";
import { formatNumber } from "../../../../utils/formatNumber";
import { todayIso } from "../../../../utils/formatDate";

interface Props {
  mode: "create" | "edit";
  initial?: PriceBoardSupplierDto;
  baseCurrencyCode: string;
  /** الموردون الدوليون (مع غير المصنَّفين) — نفس مصدر شاشة العروض الدولية. */
  suppliers: Supplier[];
  /** يرمي عند الفشل: الخطأ يُعرض هنا، وخطأ `exchange_rate` يكشف الخانة اليدوية. */
  onSubmit: (body: PriceBoardSupplierWrite) => Promise<void>;
}

const fieldLabel = "text-xs ktra-text-soft";
const linkOf = (url: string) => {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
};

export const PriceBoardSupplierForm: React.FC<Props> = ({
  mode, initial, baseCurrencyCode, suppliers, onSubmit,
}) => {
  const [name, setName] = useState(initial?.supplier_name ?? "");
  const [supplierId, setSupplierId] = useState<number | null>(initial?.supplier ?? null);
  const [currencies, setCurrencies] = useState<BoardCurrency[]>([]);
  const [currencyId, setCurrencyId] = useState<number | null>(initial?.currency ?? null);
  const initialRate = initial ? formatNumber(initial.exchange_rate, { maxDecimals: 6 }) : "";
  const [rate, setRate] = useState(initialRate);
  const [rateError, setRateError] = useState<string | null>(null);
  const [offerDate, setOfferDate] = useState(initial?.offer_date ?? (mode === "create" ? todayIso() : ""));
  const [terms, setTerms] = useState(initial?.terms ?? "");
  const [attachments, setAttachments] = useState<PriceBoardAttachment[]>(initial?.attachments ?? []);
  const [linkUrl, setLinkUrl] = useState("");
  const [linkName, setLinkName] = useState("");
  const [linkError, setLinkError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currenciesError, setCurrenciesError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listBoardCurrencies()
      .then((rows) => {
        if (!active) return;
        setCurrencies(rows);
        setCurrencyId((current) => current
          ?? rows.find((c) => c.Code === baseCurrencyCode)?.CurrencyID
          ?? rows[0]?.CurrencyID
          ?? null);
      })
      .catch((cause) => {
        if (active) setCurrenciesError(cause instanceof Error ? cause.message : "تعذّر تحميل العملات");
      });
    return () => { active = false; };
  }, [baseCurrencyCode]);

  const supplierOptions = useMemo<KitAutocompleteOption[]>(
    () => suppliers.map((s) => ({ id: s.id, label: s.tradeName, sub: s.alias || s.country || undefined })),
    [suppliers],
  );

  /**
   * تغيير العملة يُسقط سعر الصرف المكتوب: رقمٌ لعملةٍ سابقة لو بقي لحوّل أسعار
   * العمود كلها بسعرٍ خاطئ بصمت. الفارغ يتركه للخادم يحسمه من جدول الأسعار.
   */
  const changeCurrency = (next: number | null) => {
    setCurrencyId(next);
    setRateError(null);
    setRate(mode === "edit" && initial && next === initial.currency ? initialRate : "");
  };

  const addLink = () => {
    const url = linkUrl.trim();
    if (!isHttpUrl(url)) {
      setLinkError("الرابط يجب أن يبدأ بـ http:// أو https://");
      return;
    }
    setLinkError(null);
    setAttachments((prev) => [...prev, { name: linkName.trim() || linkOf(url), url, type: "link" }]);
    setLinkUrl("");
    setLinkName("");
  };

  const uploadFiles = async (files: File[]) => {
    setUploading(true);
    setUploadError(null);
    const uploaded: PriceBoardAttachment[] = [];
    try {
      for (const file of files) {
        const url = await cloudinaryService.uploadFile(file);
        uploaded.push({ name: file.name, url, type: file.type, size: file.size });
      }
    } catch (cause) {
      setUploadError(`${cause instanceof Error ? cause.message : "فشل رفع الملف"} — يمكنك لصق رابط الملف بدلاً من رفعه.`);
    } finally {
      // ما رُفع قبل الفشل يبقى مرفقاً: ضياعه بعد رفعٍ ناجح أسوأ من إبقائه.
      if (uploaded.length) setAttachments((prev) => [...prev, ...uploaded]);
      setUploading(false);
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError("اكتب اسم المورد أو اخترْه من القائمة");
      return;
    }
    if (currencyId == null) {
      setError("اختر عملة العرض");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        supplier_name: name.trim(),
        supplier: supplierId,
        currency: currencyId,
        // في التعديل لا يُرسَل السعر إلا إذا غيّره المستخدم: فتغيير العملة مع خانة سعرٍ
        // فارغة يترك الخادم يحسم سعر العملة الجديدة من جدول الأسعار.
        ...(rate.trim() && (mode === "create" || rate.trim() !== initialRate)
          ? { exchange_rate: rate.trim() }
          : {}),
        offer_date: offerDate || null,
        terms: terms.trim(),
        attachments,
      });
      setRateError(null);
    } catch (cause) {
      const fieldErrors = (cause as { fieldErrors?: Record<string, string> }).fieldErrors ?? {};
      if (fieldErrors.exchange_rate) {
        setRateError(fieldErrors.exchange_rate);
      } else {
        setError(cause instanceof Error ? cause.message : "تعذّر حفظ المورد");
      }
    } finally {
      setSaving(false);
    }
  };

  const showRate = mode === "edit" || rateError !== null;

  return (
    <form className="flex flex-col gap-3" onSubmit={(e) => { void submit(e); }}>
      <div className="flex flex-col gap-1">
        <span className={fieldLabel}>المورد</span>
        <KitAutocomplete
          value={name}
          options={supplierOptions}
          placeholder="اكتب اسم المورد…"
          onPick={(id) => {
            const picked = suppliers.find((s) => String(s.id) === String(id));
            setSupplierId(Number(id));
            if (picked) setName(picked.tradeName);
          }}
          onFreeText={(text) => { setSupplierId(null); setName(text); }}
          createLabel={(text) => `إبقاء «${text}» اسماً حراً (مورد غير مسجَّل)`}
          // النص المكتوب لا يضيع إن غادر المستخدم بلا اختيار — وحين يكون مورد
          // مسجَّل مختاراً فالكتابة بحثٌ عن بديل لا استبدال لاسمه.
          onTextChange={supplierId == null ? (text) => setName(text) : undefined}
        />
        <span className="text-[11px] ktra-text-soft">
          {supplierId != null ? "مورد في النظام" : "اسم حر — غير مرتبط بمورد مسجَّل"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1">
          <span className={fieldLabel}>عملة العرض</span>
          <select
            className="ktra-input"
            value={currencyId ?? ""}
            onChange={(e) => changeCurrency(e.target.value ? Number(e.target.value) : null)}
          >
            {currencies.map((c) => (
              <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}{c.Name ? ` — ${c.Name}` : ""}</option>
            ))}
          </select>
        </label>
        <div className="flex flex-col gap-1">
          <span className={fieldLabel}>تاريخ العرض</span>
          <KitDateInput className="ktra-input" value={offerDate} onChange={setOfferDate} />
        </div>
      </div>
      {currenciesError && <p className="text-xs text-[var(--ktra-danger)]" role="alert">{currenciesError}</p>}

      {showRate && (
        <label className="flex flex-col gap-1">
          <span className={fieldLabel}>سعر الصرف إلى {baseCurrencyCode || "عملة الأساس"}</span>
          <input
            dir="ltr"
            inputMode="decimal"
            className={`ktra-input ${rateError ? "border-[var(--ktra-danger)]" : ""}`}
            value={rate}
            aria-invalid={rateError !== null}
            placeholder="مثال: 0.138"
            onChange={(e) => setRate(e.target.value)}
          />
          {rateError && (
            <span className="text-xs text-[var(--ktra-danger)]" role="alert">
              {rateError}، ثم اضغط الحفظ مرة أخرى.
            </span>
          )}
        </label>
      )}

      <label className="flex flex-col gap-1">
        <span className={fieldLabel}>الشروط</span>
        <input className="ktra-input" value={terms} placeholder="FOB · مدة التجهيز" onChange={(e) => setTerms(e.target.value)} />
      </label>

      <div className="flex flex-col gap-2 rounded border border-[var(--ktra-line)] p-2">
        <span className={fieldLabel}>ملف العرض — رابط أو رفع ملف (PDF أو صورة أو Excel)</span>
        <div className="flex flex-col gap-1">
          <div className="grid grid-cols-[1fr_auto] gap-1">
            <input
              dir="ltr"
              className="ktra-input"
              placeholder="https://… (Google Drive وغيره)"
              value={linkUrl}
              aria-invalid={linkError !== null}
              onChange={(e) => { setLinkUrl(e.target.value); setLinkError(null); }}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addLink(); } }}
            />
            <button type="button" className="ktra-btn" onClick={addLink}>إضافة الرابط</button>
          </div>
          <input
            className="ktra-input"
            placeholder="اسم الملف (اختياري)"
            value={linkName}
            onChange={(e) => setLinkName(e.target.value)}
          />
          {linkError && <span className="text-xs text-[var(--ktra-danger)]" role="alert">{linkError}</span>}
        </div>
        <FileDropZone
          accept="image-pdf-excel"
          multiple
          busy={uploading}
          variant="compact"
          interactionRequired
          hint="اضغط لرفع ملف العرض أو اسحبه إلى هنا"
          subHint="PDF · صورة · Excel (.xlsx / .xls)"
          onFiles={(files) => { void uploadFiles(files); }}
        />
        {uploadError && <p className="text-xs text-[var(--ktra-danger)]" role="alert">{uploadError}</p>}
        {attachments.length > 0 && (
          <ul className="flex flex-col gap-1">
            {attachments.map((file, index) => (
              <li key={`${file.url}-${index}`} className="flex items-center justify-between gap-2 rounded bg-[var(--ktra-panel)] px-2 py-1 text-xs">
                <a
                  className="ktra-text-accent flex min-w-0 items-center gap-1 hover:underline"
                  href={isHttpUrl(file.url) ? file.url : undefined}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Paperclip className="h-3 w-3 shrink-0" />
                  <span className="truncate">{file.name || linkOf(file.url)}</span>
                </a>
                <button
                  type="button"
                  className="ktra-toolbtn"
                  aria-label={`إزالة ${file.name}`}
                  onClick={() => setAttachments((prev) => prev.filter((_, i) => i !== index))}
                >
                  <X className="h-3 w-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && <p className="rounded bg-[var(--ktra-danger-bg)] px-2 py-1 text-xs text-[var(--ktra-danger)]" role="alert">{error}</p>}

      <div className="flex justify-end gap-2">
        <button type="submit" className="ktra-btn-primary px-4 py-1.5 text-sm font-semibold disabled:opacity-50" disabled={saving || uploading}>
          {saving ? <Loader2 className="inline h-4 w-4 animate-spin" /> : mode === "create" ? "إضافة المورد" : "حفظ التعديلات"}
        </button>
      </div>
    </form>
  );
};
