/**
 * N5-T6 — PriceOfferManagement (L3) — KitDenseTable لعروض الأسعار
 * المرجع: العروض والطلبيات.txt:4-9
 */
import React, { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { PriceOffer, Item, Supplier, PriceOfferStatus } from "../../types";
import {
  itemsService,
  suppliersService,
  priceOffersService,
  type PriceOfferScope,
} from "../../services/firestoreService";
import type { DenseColumn } from "../kit/KitDenseTable";
import { PriceOfferForm } from "./price-offers/PriceOfferForm";
import { CommercialDocumentsList } from "../shared/CommercialDocumentsList";
import { FilePreviewModal } from "../shared/FilePreviewModal";
import { ImageIcon, Paperclip } from "lucide-react";
import type { PriceOfferAttachment } from "../../types/offer";
import {
  cancelPurchaseOrder,
  confirmPurchaseOrder,
  convertPurchaseOrderToInvoice,
  convertSupplierQuotationToPurchaseInvoice,
  convertSupplierQuotationToPurchaseOrder,
  getSupplierQuotation,
} from "../../services/procurementDocumentsApi";
import { quotationToDraftDeal } from "../../utils/quotationToDraftDeal";
import { documentSerialDisplay, elideDocumentNumber } from "../../utils/documentNumberDisplay";
import { ConvertTargetDialog, type ConvertTarget } from "../sales/ConvertTargetDialog";
import { openInNewTab } from "../../utils/openInNewTab";
import { useToast } from "../../contexts/ToastContext";
import {
  canConvertImportOffer,
  isOfferStruckThrough,
  procurementDocKind,
  procurementStatusLabel,
} from "../../utils/documentBadges";

const STATUS_LABELS: Record<string, string> = {
  initial: "مسودة",
  pending_info: "بانتظار معلومات",
  under_discussion: "قيد المناقشة",
  approved_for_shipping: "معتمد للشحن",
  rejected: "مرفوض",
};

/** T-IMPOFFER: نطاق الاستيراد يقرأ الحالة كقرار ملاءمة (انظر PriceOfferForm). */
const IMPORT_STATUS_LABELS: Record<string, string> = {
  initial: "مسودة",
  pending_info: "بانتظار معلومات",
  under_discussion: "قيد المناقشة",
  approved_for_shipping: "ملائم",
  rejected: "غير ملائم",
};

const STATUS_COLORS: Record<string, string> = {
  initial: "var(--ktra-ink-soft)",
  pending_info: "var(--ktra-warn, #b8800a)",
  under_discussion: "var(--ktra-accent, #1857a4)",
  approved_for_shipping: "var(--ktra-ok, #267346)",
  rejected: "var(--ktra-danger, #c00)",
};

const fmtDate = (d: string | undefined) => {
  if (!d) return "—";
  return formatDateValue(d);
};

import { formatMoney } from "@/utils/formatNumber";
import { formatDateValue } from "../../utils/formatDate";
const fmtAmt = (n: number | undefined) => formatMoney(n);

interface Props {
  scope?: PriceOfferScope;
}

export const PriceOfferManagement: React.FC<Props> = (props) => {
  const scope: PriceOfferScope = props.scope ?? "purchase";
  const statusLabels = scope === "import" ? IMPORT_STATUS_LABELS : STATUS_LABELS;
  const toast = useToast();
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<"list" | "form">("list");
  const [offers, setOffers] = useState<PriceOffer[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<PriceOfferStatus | "all">("all");

  const [currentOffer, setCurrentOffer] = useState<Partial<PriceOffer>>({
    status: "initial", items: [], subtotal: 0, discountAmount: 0,
    taxRate: 0, taxAmount: 0, grandTotal: 0, internalNotes: "",
  });
  const [isReadOnly, setIsReadOnly] = useState(false);
  // T-IMPOFFER: معاينة ملف العرض من القائمة نفسها — بلا فتح المستند.
  const [previewFile, setPreviewFile] = useState<PriceOfferAttachment | null>(null);
  // T-PLINEAGE: العرض المحلي له وجهتان (طلبية / فاتورة) — الاختيار داخل الموقع.
  const [convertOffer, setConvertOffer] = useState<PriceOffer | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    let active = true;
    const pending = new Set(["offers", "items", "suppliers"]);
    const settle = (key: string) => {
      pending.delete(key);
      if (active && pending.size === 0) setLoading(false);
    };
    const fail = (key: string, message: string) => (cause: unknown) => {
      if (active) {
        setError(cause instanceof Error ? `${message}: ${cause.message}` : message);
      }
      settle(key);
    };
    const u1 = priceOffersService.subscribeToPriceOffers(
      (rows) => { if (active) setOffers(rows); settle("offers"); },
      scope,
      fail("offers", "تعذّر تحميل العروض"),
    );
    const u2 = itemsService.subscribeToItems(
      (rows) => { if (active) setItems(rows); settle("items"); },
      fail("items", "تعذّر تحميل الأصناف"),
    );
    // T-IMPOFFER: الموردون مفصولون — شاشة الاستيراد تعرض الدوليين (مع غير
    // المصنَّفين) وشاشة الشراء المحليين، فلا يُختار مصنع صيني لطلبية محلية.
    const u3 = suppliersService.subscribeToSuppliers(
      (rows) => { if (active) setSuppliers(rows); settle("suppliers"); },
      fail("suppliers", "تعذّر تحميل الموردين"),
      scope === "import" ? "international" : "local",
    );
    return () => {
      active = false;
      u1();
      u2();
      u3();
    };
  }, [scope, reloadKey]);

  // T-PLINEAGE: `?doc=quote-12` يفتح المستند مباشرةً — رابط الفاتورة إلى مصدرها
  // يجب أن يصل إلى المستند نفسه لا إلى قائمة يبحث فيها المستخدم عنه.
  const [pendingDocId, setPendingDocId] = useState<string | null>(
    () => new URLSearchParams(window.location.search).get("doc"),
  );
  const syncOpenDocumentPath = (documentId?: string) => {
    const url = new URL(window.location.href);
    if (documentId) url.searchParams.set("doc", documentId);
    else url.searchParams.delete("doc");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  };
  useEffect(() => {
    if (!pendingDocId || loading) return;
    const target = offers.find((offer) => offer.id === pendingDocId);
    if (!target) return;
    setPendingDocId(null);
    void openEdit(target);
  }, [pendingDocId, loading, offers]);

  // الرقم يُعرض تسلسلاً وحده (`IQ-0006` ← `6`) ليأخذ المربّعُ الصورةَ كاملةً.
  // البادئة تعود **للقائمة كلّها** إن جعل الاختصارُ صفّين متطابقين — شاشة الشراء
  // تخلط عرض سعر (`PQ`) وطلبية (`PO`) فقد يلتقي تسلسلاهما. القياس على `offers`
  // لا على المفلتَر: البحث لا يقلب شكل الأرقام تحت يد المستخدم.
  const serialsCollide = useMemo(() => {
    const seen = new Set<string>();
    for (const o of offers) {
      const serial = documentSerialDisplay(o.offerNumber || o.id.slice(0, 8));
      if (seen.has(serial)) return true;
      seen.add(serial);
    }
    return false;
  }, [offers]);

  const filtered = useMemo(() => {
    const s = search.toLowerCase();
    return offers.filter((o) => {
      if (filterStatus !== "all" && o.status !== filterStatus) return false;
      if (s) {
        const sup = suppliers.find((x) => x.id === o.supplierId)?.tradeName || "";
        return (
          sup.toLowerCase().includes(s) ||
          (o.offerNumber || "").toLowerCase().includes(s) ||
          (o.orderName || "").toLowerCase().includes(s) ||
          (o.orderDescription || "").toLowerCase().includes(s)
        );
      }
      return true;
    });
  }, [offers, suppliers, search, filterStatus]);

  const openNew = () => {
    syncOpenDocumentPath();
    setCurrentOffer({
      status: "initial", items: [], subtotal: 0, discountAmount: 0,
      taxRate: 0, taxAmount: 0, grandTotal: 0, internalNotes: "",
    });
    setIsReadOnly(false);
    setViewMode("form");
  };

  const openEdit = async (offer: PriceOffer, readOnly = false) => {
    setLoading(true);
    setError(null);
    try {
      const detail = await priceOffersService.getPriceOfferById(offer.id, scope);
      const resolved = detail || offer;
      setCurrentOffer(resolved);
      setIsReadOnly(
        readOnly
        || resolved.backendStatus === "converted"
        || resolved.backendStatus === "confirmed"
        || resolved.backendStatus === "cancelled"
        || resolved.backendStatus === "invoiced"
        || resolved.backendStatus === "closed"
      );
      setViewMode("form");
      syncOpenDocumentPath(resolved.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذّر فتح المستند");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (offerData: Partial<PriceOffer>) => {
    setSaving(true);
    try {
      if (offerData.id) {
        const updatedOffer = offerData as PriceOffer;
        const saved = await priceOffersService.updatePriceOfferInDb(updatedOffer, scope);
        setOffers((prev) => prev.map((row) => row.id === updatedOffer.id ? saved : row));
      } else {
        const newOffer: PriceOffer = {
          ...(offerData as PriceOffer),
          id: "",
          offerNumber: offerData.offerNumber || "",
          createdAt: offerData.createdAt || new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        const saved = await priceOffersService.addPriceOfferToDb(newOffer, scope);
        setOffers((prev) => [saved, ...prev]);
      }
      setError(null);
      setViewMode("list");
      syncOpenDocumentPath();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "فشل حفظ المستند");
      throw e;
    } finally {
      setSaving(false);
    }
  };

  /**
   * إجراءات دورة المستند (تأكيد/تحويل/إلغاء).
   *
   * كان النجاح صامتاً: يُعاد التحميل فقط، والحالة تُعرض بنفس النص قبله وبعده
   * («معتمد للشحن») ⇒ يبدو التحويل كأنه لم يحدث. الآن يُعلن الناتج باسم المستند
   * المُنشأ، ويُسمّى المستند الجديد في الرسالة.
   */
  const runLifecycleAction = async (
    action: () => Promise<unknown>,
    successMessage?: (result: unknown) => string,
  ) => {
    setSaving(true);
    setError(null);
    try {
      const result = await action();
      setReloadKey((key) => key + 1);
      if (successMessage) toast(successMessage(result), "success");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "تعذّر تنفيذ الإجراء";
      setError(message);
      toast(message, "error");
    } finally {
      setSaving(false);
    }
  };

  /** مسار المستند الناتج — الرقم بلا رابط يُلزم المستخدم بالبحث عنه يدوياً. */
  const linkedDocPath = (offer: PriceOffer): string | null => {
    if (!offer.linkedDocId) return null;
    if (offer.linkedDocKind === "invoice") return `/purchase-invoices/${offer.linkedDocId}`;
    if (offer.linkedDocKind === "deal") return `/deals/${offer.linkedDocId}`;
    return null;
  };

  /** تحويل العرض المحلي إلى الوجهة المختارة (طلبية تسبق التسليم، فاتورة تُثبت الذمّة). */
  const convertLocalOffer = (offer: PriceOffer, target: ConvertTarget) => {
    const id = Number(offer.id.replace("quote-", ""));
    setConvertOffer(null);
    void runLifecycleAction(
      () => target === "invoice"
        ? convertSupplierQuotationToPurchaseInvoice(id)
        : convertSupplierQuotationToPurchaseOrder(id),
      (result) => {
        const payload = result as {
          order?: { order_number?: string };
          invoice?: { invoice_number?: string };
        };
        return target === "invoice"
          ? `تم تحويل العرض إلى فاتورة شراء ${payload?.invoice?.invoice_number || ""}`.trim()
          : `تم تحويل العرض إلى طلبية شراء ${payload?.order?.order_number || ""}`.trim();
      },
    );
  };

  /**
   * T113-2: «تحويل إلى صفقة» لم يعد ينشئ شيئاً — يفتح محرّر صفقة معبّأً من العرض
   * وغير محفوظ. لا صفقة ولا مورد ولا صنف قبل أن يضغط المستخدم «حفظ» في المحرّر.
   * تُقرأ نسخة طازجة من العرض قبل الفتح: القائمة قد تكون قديمة، وتحويل عرضٍ
   * حُوّل في تبويب آخر يجب أن يقول أين ذهب لا أن يفتح محرّراً مصيره الرفض.
   */
  const openDraftDealFromOffer = async (offer: PriceOffer) => {
    setSaving(true);
    setError(null);
    try {
      const quotation = await getSupplierQuotation(Number(offer.id.replace("quote-", "")));
      if (quotation.status !== "accepted") {
        const claimedBy = quotation.converted_deal?.ref_number;
        toast(
          claimedBy
            ? `العرض ${quotation.quotation_number} محوَّل بالفعل إلى الصفقة ${claimedBy}.`
            : `العرض ${quotation.quotation_number} يلزمه قرار «ملائم» قبل تحويله إلى صفقة.`,
          "error",
        );
        setReloadKey((key) => key + 1);
        return;
      }
      navigate("/deals/new", {
        state: {
          draftDeal: quotationToDraftDeal(
            quotation,
            suppliers.map((s) => ({ id: s.id, name: s.tradeName, alias: s.alias })),
          ),
        },
      });
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "تعذّر فتح صفقة من هذا العرض";
      setError(message);
      toast(message, "error");
    } finally {
      setSaving(false);
    }
  };

  const columns: DenseColumn<PriceOffer>[] = [
    // T-IMPOFFER: «وإذا غير ملائم يكون معلَّم على أنه مشطوب» — الشطب على رقم
    // المستند نفسه فيُقرأ القرار من مسح الصفوف بلا فتح أي عرض.
    // THA-116 (#31, مراجعة المالك): «الصورة تملأ مربّعها، والرقم ما ياكل منه» —
    // المربّع صار 72px والخانة 128px، والرقم تسلسلاً وحده. الصورة هي ما يميّز
    // العرض بصرياً في قائمة الاستيراد، والبادئة الثابتة كانت تأخذ ثلثَي الخانة.
    { key: "offerNumber", header: "رقم المستند", width: "128px",
      render: (o) => {
        const firstImage = (o.attachments || []).find((file) =>
          (file.type || "").toLowerCase().startsWith("image/")
          || /\.(png|jpe?g|webp|gif)(?:\?.*)?$/i.test(file.url || ""),
        );
        const number = o.offerNumber || o.id.slice(0, 8);
        return (
          <div className="flex items-center gap-1.5">
            {/* المربّع نفسه هو الحاوية (`h-18 w-18` = 72px + `overflow-hidden`)
                والصورة تملأه
                بـ`h-full w-full object-cover`: صورة عمودية أو أعرض من مربّعها
                تُقصّ ولا تُترك بهامش. الخلفية المحايدة للصور الشفافة — بلا
                خلفية يظهر تناوب ألوان الصفوف من خلف الصورة. */}
            {firstImage ? (
              <button type="button"
                className="block h-18 w-18 shrink-0 overflow-hidden rounded border border-[var(--color-border)] bg-[var(--color-surface-2)]"
                title={`عرض «${firstImage.name || "الصورة"}»`}
                onClick={(e) => { e.stopPropagation(); setPreviewFile(firstImage); }}>
                <img src={firstImage.url} alt="" className="h-full w-full object-cover" />
              </button>
            ) : (
              <span className="flex h-18 w-18 shrink-0 items-center justify-center rounded border border-dashed border-[var(--color-border)] ktra-text-soft"
                title="لا توجد صورة توضيحية">
                <ImageIcon className="h-7 w-7" aria-hidden="true" />
              </span>
            )}
            {/* الرقم لا يزاحم الصورة: الصورة `shrink-0` والرقم `min-w-0 truncate`
                فالفائض يُقصّ داخل الخلية بدل أن يوسّعها على حساب جارتها. والمعروض
                تسلسلٌ وحده (`documentSerialDisplay`) إلا حين يتصادم تسلسلان في
                القائمة — عندها يعود القصّ الأوسط الكامل. الكامل دائماً في `title`
                وفي البحث. وبلا `.ktra-cell-clip`: قيده بالبكسل لا يتبع سحب حدّ
                العمود (THA-347)، و`min-w-0` داخل صفّ مرن يتبعه. */}
            <b dir="auto" title={number}
              className="min-w-0 truncate tabular-nums"
              style={isOfferStruckThrough(o.backendStatus)
                ? { textDecoration: "line-through", opacity: 0.6 }
                : undefined}>
              {serialsCollide ? elideDocumentNumber(number) : documentSerialDisplay(number)}
            </b>
          </div>
        );
      } },
    { key: "orderSummary", header: "اسم ووصف الطلبية", width: "240px",
      render: (o) => (
        <div className="min-w-0 leading-tight">
          <div className="truncate font-semibold text-[var(--color-text)]" title={o.orderName || ""}>
            {o.orderName || "—"}
          </div>
          {o.orderDescription && (
            <div className="mt-0.5 line-clamp-2 text-[10px] ktra-text-soft" title={o.orderDescription}>
              {o.orderDescription}
            </div>
          )}
        </div>
      ) },
    { key: "supplier", header: "المورد",
      render: (o) => (
        <span style={isOfferStruckThrough(o.backendStatus)
          ? { textDecoration: "line-through", opacity: 0.6 }
          : undefined}>
          {suppliers.find((s) => s.id === o.supplierId)?.tradeName || o.factoryName || "—"}
        </span>
      ) },
    { key: "date", header: "التاريخ", width: "100px",
      render: (o) => <>{fmtDate(o.createdAt)}</> },
    { key: "items", header: "الأصناف", width: "70px", align: "center",
      render: (o) => <>{(o.items || []).length}</> },
    // T-IMPOFFER: ملف العرض ظاهر في القائمة، والنقر عليه يفتح معاينة وسط الشاشة.
    { key: "files", header: "الملف", width: "60px", align: "center",
      render: (o) => {
        const files = o.attachments || [];
        if (files.length === 0) return <span className="ktra-text-soft">—</span>;
        return (
          <button
            type="button"
            className="ktra-text-accent inline-flex items-center gap-0.5"
            title={`عرض «${files[0].name || "الملف"}»`}
            onClick={(e) => { e.stopPropagation(); setPreviewFile(files[0]); }}
          >
            <Paperclip className="h-3.5 w-3.5" />
            {files.length > 1 && <span className="text-[10px]">{files.length}</span>}
          </button>
        );
      } },
    { key: "total", header: "الإجمالي", width: "120px", align: "center", numeric: true,
      render: (o) => <>{fmtAmt(o.grandTotal)}</> },
    // الحالة من حالة الخادم الحقيقية لا من قاموس العرض القديم: «مؤكَّدة» و«محوَّلة
    // إلى فاتورة» كانتا تظهران «معتمد للشحن» كلتاهما، والمستند المرتبط لا يظهر.
    // T-OFFERSTATE: العمود «الحالة» في الجانبين — «القرار» يفترض أن كل صف حُسم،
    // بينما «بانتظار معلومات» و«قيد المناقشة» حالتان قبل أي قرار.
    { key: "status", header: "الحالة", width: "190px",
      render: (o) => {
        const kind = procurementDocKind(o.id, scope);
        return (
          <div className="flex flex-col leading-tight">
            <span style={{ color: STATUS_COLORS[o.status] || "inherit" }}>
              {procurementStatusLabel(kind, o.backendStatus, statusLabels[o.status])}
            </span>
            {o.linkedDocNumber && (
              linkedDocPath(o) ? (
                <button
                  type="button"
                  className="ktra-text-accent text-[10px] text-right hover:underline"
                  title={`فتح ${o.linkedDocNumber}`}
                  onClick={(e) => { e.stopPropagation(); openInNewTab(linkedDocPath(o)!); }}
                >
                  ← {o.linkedDocNumber}
                </button>
              ) : (
                <span className="text-[10px] ktra-text-soft">← {o.linkedDocNumber}</span>
              )
            )}
            {/* T-RECVIS: أين وصلت بضاعة هذه الطلبية. الطلبية لا تُشقّ (طلبيةٌ
                واحدة ← فاتورةٌ واحدة ← إرساليات متعددة)، فالجواب على فاتورتها. */}
            {o.linkedDocReceiptText && (
              <span
                className={`text-[10px] ${o.linkedDocHasRemaining
                  ? "text-[var(--ktra-warn)]" : "ktra-text-soft"}`}
                title="الاستلام يكمل على الفاتورة — الطلبية تتحوّل كاملةً مرّةً واحدة"
              >
                {o.linkedDocReceiptText}
              </span>
            )}
            {/* التفصيل بجانب الحالة: «غير ملائم» بلا سبب — أو «بانتظار معلومات»
                بلا ما يُنتظَر — لا يعلّم أحداً شيئاً عند مسح القائمة. */}
            {o.decisionReason && (
              <span className="text-[10px] ktra-text-soft" title={o.decisionReason}>
                {o.backendStatus === "pending_info" ? "بانتظار: " : "السبب: "}
                {o.decisionReason}
              </span>
            )}
          </div>
        );
      }
    },
    { key: "actions", header: "إجراءات", width: "250px", align: "center",
      render: (o) => (
        <div className="flex flex-wrap items-center justify-center gap-2 text-xs">
          <button className="ktra-text-accent hover:underline"
            onClick={(e) => { e.stopPropagation(); void openEdit(o); }}>
            {o.backendStatus === "converted" ? "عرض" : "تعديل"}
          </button>
          {o.id.startsWith("quote-") && canConvertImportOffer(o.backendStatus) && (
            <button className="text-green-600 hover:underline" disabled={saving}
              onClick={(e) => {
                e.stopPropagation();
                // الاستيراد وجهته واحدة (الصفقة هي الطلبية التشغيلية)، والشراء
                // المحلي وجهتان فيُسأل عنهما بدل فرض المرور بطلبية.
                if (scope === "import") {
                  void openDraftDealFromOffer(o);
                  return;
                }
                setConvertOffer(o);
              }}
              title={scope === "import"
                ? "يفتح صفقة معبّأة من العرض — لا تُنشأ حتى تضغط «حفظ»"
                : undefined}>
              {scope === "import" ? "تحويل إلى صفقة" : "تحويل…"}
            </button>
          )}
          {/* T-IMPOFFER: العرض غير الملائم لا يُحوَّل — نقول ذلك بدل إخفاء الزر بصمت. */}
          {o.id.startsWith("quote-")
            && scope === "import"
            && o.backendStatus !== "accepted"
            && o.backendStatus !== "converted" && (
            <span className="ktra-text-soft text-[10px]" title="حوّل العرض بعد اعتباره ملائماً">
              {isOfferStruckThrough(o.backendStatus)
                ? "غير ملائم — لا يُحوَّل"
                : "يلزمه قرار «ملائم» للتحويل"}
            </span>
          )}
          {o.id.startsWith("order-") && o.backendStatus === "draft" && (
            <button className="text-green-600 hover:underline" disabled={saving}
              onClick={(e) => {
                e.stopPropagation();
                void runLifecycleAction(
                  () => confirmPurchaseOrder(Number(o.id.replace("order-", ""))),
                  () => `تم تأكيد الطلبية ${o.offerNumber}`,
                );
              }}>
              تأكيد
            </button>
          )}
          {o.id.startsWith("order-") && o.backendStatus === "confirmed" && (
            <>
              <button className="text-blue-600 hover:underline" disabled={saving}
                onClick={(e) => {
                  e.stopPropagation();
                  void runLifecycleAction(
                    () => convertPurchaseOrderToInvoice(
                      Number(o.id.replace("order-", "")),
                    ),
                    (result) => {
                      const payload = result as {
                        invoice?: { invoice_number?: string };
                      };
                      return `تم تحويل الطلبية إلى فاتورة شراء ${
                        payload?.invoice?.invoice_number || ""
                      }`.trim();
                    },
                  );
                }}>
                تحويل لفاتورة
              </button>
              <button className="text-amber-600 hover:underline" disabled={saving}
                onClick={(e) => {
                  e.stopPropagation();
                  void runLifecycleAction(
                    () => cancelPurchaseOrder(Number(o.id.replace("order-", ""))),
                    () => `تم إلغاء الطلبية ${o.offerNumber}`,
                  );
                }}>
                إلغاء
              </button>
            </>
          )}
        </div>
      )
    },
  ];

  if (viewMode === "form") {
    return (
      <PriceOfferForm
        offer={currentOffer}
        items={items}
        suppliers={suppliers}
        scope={scope}
        isReadOnly={isReadOnly}
        saving={saving}
        onSave={handleSave}
        onCancel={() => {
          setViewMode("list");
          syncOpenDocumentPath();
        }}
      />
    );
  }

  return (
    <>
      <CommercialDocumentsList<PriceOffer>
        title={scope === "import" ? "عروض وطلبيات الاستيراد" : "عروض وطلبيات الشراء"}
        state={scope === "import" ? "مستندات الاستيراد" : "مستندات الشراء"}
        rows={filtered}
        columns={columns}
        getRowKey={(offer) => offer.id}
        loading={loading}
        error={error}
        emptyHint="لا توجد عروض أو طلبيات"
        countLabel={`${offers.length} مستند`}
        searchValue={search}
        searchPlaceholder="بحث بالرقم / اسم أو وصف الطلبية / المورد…"
        onSearchChange={setSearch}
        statusValue={filterStatus}
        statusOptions={[
          { value: "all", label: "كل الحالات" },
          ...Object.entries(statusLabels).map(([value, label]) => ({ value, label })),
        ]}
        onStatusChange={(value) => setFilterStatus(value as PriceOfferStatus | "all")}
        onNew={openNew}
        onReload={() => setReloadKey((key) => key + 1)}
        newLabel="عرض / طلبية جديدة"
        onRowDoubleClick={(offer) => void openEdit(offer)}
      />
      <FilePreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />
      {convertOffer && (
        <ConvertTargetDialog
          title={`تحويل عرض السعر ${convertOffer.offerNumber || ""}`.trim()}
          hint="اختر الوجهة — الطلبية التزام شراء يسبق التسليم، والفاتورة تُثبت الذمّة للمورد."
          orderDescription="طلبية شراء للمورد تُؤكَّد ثم تُحوَّل إلى فاتورة — بلا قيد محاسبي."
          invoiceDescription="فاتورة شراء مسودة مباشرةً — تُثبت ذمّة المورد عند ترحيلها."
          onPick={(target) => convertLocalOffer(convertOffer, target)}
          onClose={() => setConvertOffer(null)}
        />
      )}
    </>
  );
};
