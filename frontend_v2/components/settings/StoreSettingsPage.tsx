/**
 * ST-3 — «متجري»: الشاشة الوحيدة التي يفتح منها المدير متجره ويقرّر ما يُعرض فيه.
 *
 * قرارها المركزي: **المعرّف نفسه هو مفتاح التفعيل** (`Tenant.store_slug`) —
 * `null` = مقفل. فلا مفتاح «تشغيل» ثانٍ يمكن أن يناقض الرابط، ولا حالة «متجر
 * مفعّل بلا رابط» يقف المستخدم أمامها بلا شيء ينسخه.
 *
 * ولا نقطة نشرٍ خادمية جديدة: النشر والسعر والوصف حقولٌ قائمة على `Product`
 * تقبلها `ProductViewSet` بـPATCH — الشاشة واجهةٌ فوق ما هو مبنيّ.
 *
 * مراجعة أول تفعيل (`confirmFirstActivation`) هي السطر الأهم هنا، وسببها في
 * تعليقها: `is_for_sale_online` علمٌ قديم له معنى تسعيري سابق للمتجر.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Copy, ExternalLink, Loader2, Lock, Store } from "lucide-react";

import {
  getPublishedProducts,
  getStoreAdminProducts,
  setStoreSlug,
  storeAdminProductName,
  updateProductPublishing,
  type StoreAdminProduct,
  type StoreAdminScope,
} from "../../services/storeAdminApi";
import { useCompany } from "../../contexts/CompanyContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { clientLogger } from "../../services/logger";
import { humanizeDrfError } from "../../utils/drfError";
import { formatNumber } from "../../utils/formatNumber";
import { storeHomeUrl } from "../../utils/storeLinks";
import { AseelDocumentShell, type AseelToolbarAction } from "../aseel";

/** ما يحرّره المستخدم في صفّ قبل الحفظ — فارغ يعني «لا سعر متجر خاص». */
type RowDraft = { online_price: string; online_description: string };

const SCOPES: { key: StoreAdminScope; label: string }[] = [
  { key: "published", label: "المعروضة في المتجر" },
  { key: "unpublished", label: "غير المعروضة" },
  { key: "all", label: "كل الأصناف" },
];

const input =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-sm text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/50";

const draftOf = (product: StoreAdminProduct): RowDraft => ({
  online_price: product.online_price ?? "",
  online_description: product.online_description ?? "",
});

/**
 * قائمة ما سيصير علنياً — تُعرض داخل حوار التأكيد قبل أول فتح للمتجر.
 * أسماء لا عدداً مجرّداً: «١٧ صنفاً» لا تُخبر المدير إن كان بينها ما لا يريد نشره.
 */
const PublishedPreview: React.FC<{ items: StoreAdminProduct[]; total: number }> = ({
  items,
  total,
}) => (
  <div className="space-y-2">
    <p>
      هذه الشركة تحمل <strong>{formatNumber(total)}</strong> صنفاً معلَّماً «للبيع عبر
      الإنترنت» من قبل. بمجرّد فتح المتجر تصير هذه الأصناف — بأسمائها وأسعارها وصورها —
      مرئيةً لأي زائر يفتح الرابط.
    </p>
    <ul className="max-h-40 overflow-y-auto rounded-md border border-[var(--color-border)] p-2 text-xs">
      {items.map((item) => (
        <li key={item.id} className="py-0.5">
          • {storeAdminProductName(item)}
        </li>
      ))}
      {total > items.length && (
        <li className="py-0.5 opacity-70">… وغيرها {formatNumber(total - items.length)}</li>
      )}
    </ul>
    <p>
      إن كان فيها ما لا تريد عرضه، اختر «راجع القائمة أولاً» — يبقى المتجر مقفلاً وتفتح
      الشاشة على المعروضة كي تُلغي عرض ما تشاء ثم تفتحه.
    </p>
  </div>
);

export const StoreSettingsPage: React.FC = () => {
  const { currentCompany, refreshCompanies } = useCompany();
  const confirm = useConfirm();
  const toast = useToast();

  const savedSlug = currentCompany?.store_slug || "";
  const [slugInput, setSlugInput] = useState(savedSlug);
  const [savingSlug, setSavingSlug] = useState(false);

  const [scope, setScope] = useState<StoreAdminScope>("published");
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<StoreAdminProduct[]>([]);
  const [drafts, setDrafts] = useState<Record<number, RowDraft>>({});
  const [count, setCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [savingRow, setSavingRow] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // الشركة تُبدَّل من شريط الشركات دون مغادرة الشاشة — الحقل يتبع الشركة النشطة.
  useEffect(() => { setSlugInput(savedSlug); }, [savedSlug]);

  const storeLink = savedSlug ? storeHomeUrl(window.location.origin, savedSlug) : null;

  const load = useCallback(async (nextPage: number, replace: boolean) => {
    setLoading(true);
    setErr(null);
    try {
      const paged = await getStoreAdminProducts({ scope, search, page: nextPage });
      setRows((prev) => (replace ? paged.results : [...prev, ...paged.results]));
      setDrafts((prev) => {
        const next = replace ? {} : { ...prev };
        for (const item of paged.results) next[item.id] = draftOf(item);
        return next;
      });
      setCount(paged.count);
      setHasNext(paged.hasNext);
      setPage(nextPage);
    } catch (e) {
      setErr(humanizeDrfError(e));
    } finally {
      setLoading(false);
    }
  }, [scope, search]);

  // البحث مؤجَّل: الجدول خادميّ الترقيم، فكل ضغطة مفتاح بلا تأجيل طلبٌ كامل.
  useEffect(() => {
    const timer = window.setTimeout(() => { void load(1, true); }, 350);
    return () => window.clearTimeout(timer);
  }, [load]);

  /**
   * الحارس الذي أضافه هذا الترقيم: `is_for_sale_online` ليس علماً جديداً — هو
   * في المخطط منذ ما قبل المتجر ورفيقه `online_price` تقرؤه الفوترة سعراً
   * افتراضياً حين يخلو الكرت من سعر بيع، فقد تكون الشركة علّمته على أصناف بلا
   * أي نيّة نشر. لحظةَ اختيار المعرّف يتغيّر معنى العلم تحتها بصمت. فلا فتح
   * أول إلا بعد عرض ما سيُعرَض.
   */
  const confirmFirstActivation = async (): Promise<boolean> => {
    const published = await getPublishedProducts();
    if (published.count === 0) return true;
    const ok = await confirm({
      title: "قبل فتح المتجر",
      message: <PublishedPreview items={published.results} total={published.count} />,
      confirmText: "افتح المتجر واعرضها",
      cancelText: "راجع القائمة أولاً",
      danger: true,
    });
    if (!ok) {
      setScope("published");
      toast("المتجر ما زال مقفلاً. هذه هي الأصناف التي كانت ستُعرض.", "info");
    }
    return ok;
  };

  const handleSaveSlug = async () => {
    if (!currentCompany) return;
    const slug = slugInput.trim();
    if (!slug || slug === savedSlug) return;

    if (!savedSlug) {
      if (!(await confirmFirstActivation())) return;
    } else {
      const ok = await confirm({
        title: "تغيير رابط المتجر",
        message:
          `كل رابط وزّعته بالمعرّف «${savedSlug}» سيتوقّف عن العمل فوراً — الرسائل ` +
          `المرسلة على واتساب، والروابط المحفوظة عند زبائنك. لا تحويل من القديم إلى ` +
          `الجديد.`,
        confirmText: "غيّر المعرّف",
        cancelText: "أبقِ القديم",
        danger: true,
      });
      if (!ok) return;
    }

    setSavingSlug(true);
    setErr(null);
    try {
      await setStoreSlug(currentCompany.TenantID, slug);
      await refreshCompanies();
      clientLogger.info("store.slug_saved", { first: !savedSlug });
      toast(savedSlug ? "تم تغيير رابط المتجر." : "فُتح متجرك — انسخ الرابط وشاركه.", "success");
    } catch (e) {
      setErr(humanizeDrfError(e));
    } finally {
      setSavingSlug(false);
    }
  };

  const handleCloseStore = async () => {
    if (!currentCompany || !savedSlug) return;
    const ok = await confirm({
      title: "إقفال المتجر",
      message:
        `سيتوقّف الرابط عن العمل وتصير صفحة المتجر «غير موجودة» لكل زائر. ` +
        `أصنافك وأسعارها تبقى كما هي، وتقدر أن تفتحه ثانيةً بنفس المعرّف متى شئت.`,
      confirmText: "أقفل المتجر",
      cancelText: "أبقِه مفتوحاً",
      danger: true,
    });
    if (!ok) return;
    setSavingSlug(true);
    setErr(null);
    try {
      await setStoreSlug(currentCompany.TenantID, "");
      await refreshCompanies();
      clientLogger.info("store.closed", {});
      toast("أُقفل المتجر.", "success");
    } catch (e) {
      setErr(humanizeDrfError(e));
    } finally {
      setSavingSlug(false);
    }
  };

  const handleCopy = async () => {
    if (!storeLink) return;
    try {
      await navigator.clipboard.writeText(storeLink);
      toast("تم نسخ رابط المتجر.", "success");
    } catch {
      toast("تعذّر النسخ — حدّد الرابط وانسخه يدوياً.", "error");
    }
  };

  /**
   * تبديل العرض يُطبَّق فوراً (بلا زر حفظ): المستخدم يرى أثره في نفس اللحظة —
   * الصفّ يغادر التبويب حين لم يعد ينتمي إليه، بدل أن يبقى معروضاً بحالة كاذبة.
   */
  const togglePublish = async (product: StoreAdminProduct) => {
    const next = !product.is_for_sale_online;
    setSavingRow(product.id);
    setErr(null);
    try {
      await updateProductPublishing(product.id, { is_for_sale_online: next });
      if (scope === "all") {
        setRows((prev) => prev.map((r) =>
          r.id === product.id ? { ...r, is_for_sale_online: next } : r));
      } else {
        setRows((prev) => prev.filter((r) => r.id !== product.id));
        setCount((c) => Math.max(0, c - 1));
      }
      toast(next ? "أصبح الصنف معروضاً في المتجر." : "لم يعد الصنف معروضاً.", "success");
    } catch (e) {
      setErr(humanizeDrfError(e));
    } finally {
      setSavingRow(null);
    }
  };

  const saveRow = async (product: StoreAdminProduct) => {
    const draft = drafts[product.id];
    if (!draft) return;
    setSavingRow(product.id);
    setErr(null);
    try {
      const saved = await updateProductPublishing(product.id, {
        // فارغ = «لا سعر متجر خاص» ⇒ يعرض المتجر سعر البيع. `null` لا `""`:
        // النصّ الفارغ على حقل عشري خطأ تحقّق، والمقصود هو محو القيمة.
        online_price: draft.online_price.trim() === "" ? null : draft.online_price.trim(),
        online_description: draft.online_description.trim(),
      });
      setRows((prev) => prev.map((r) => (r.id === product.id ? { ...r, ...saved } : r)));
      setDrafts((prev) => ({ ...prev, [product.id]: draftOf({ ...product, ...saved }) }));
      toast("حُفظ.", "success");
    } catch (e) {
      setErr(humanizeDrfError(e));
    } finally {
      setSavingRow(null);
    }
  };

  const isDirty = (product: StoreAdminProduct): boolean => {
    const draft = drafts[product.id];
    if (!draft) return false;
    const saved = draftOf(product);
    return draft.online_price !== saved.online_price
      || draft.online_description !== saved.online_description;
  };

  const toolbarActions: AseelToolbarAction[] = useMemo(() => {
    const actions: AseelToolbarAction[] = [];
    if (storeLink) {
      actions.push(
        { key: "copy", label: "نسخ الرابط", icon: <Copy />, onClick: () => { void handleCopy(); } },
        {
          key: "open",
          label: "فتح المتجر",
          icon: <ExternalLink />,
          onClick: () => window.open(storeLink, "_blank", "noopener"),
        },
        {
          key: "close",
          label: "إقفال المتجر",
          icon: <Lock />,
          onClick: () => { void handleCloseStore(); },
          disabled: savingSlug,
        },
      );
    }
    return actions;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeLink, savingSlug]);

  const inner = (
    <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-4" dir="rtl">
      {err && (
        <div role="alert" className="rounded-md border border-[var(--color-danger)] bg-[color-mix(in_srgb,var(--color-danger)_8%,transparent)] px-3 py-2 text-sm">
          {err}
        </div>
      )}

      {/* ── حالة المتجر ورابطه ───────────────────────────────────────── */}
      <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Store className="h-5 w-5 text-[var(--color-primary)]" />
          <h3 className="text-base font-bold">
            {savedSlug ? "متجرك مفتوح" : "متجرك مقفل"}
          </h3>
        </div>

        <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
          {savedSlug
            ? "هذا رابط متجرك — انسخه وأرسله لزبائنك على واتساب. يفتحه أي شخص بلا تسجيل دخول، ولا يرى فيه غير الأصناف التي تعرضها أنت."
            : "اختر معرّفاً بالإنجليزية (حروف صغيرة وأرقام وشرطات، من ٣ إلى ٤٠ حرفاً) يصير رابط متجرك. لن يرى أحد شيئاً قبل أن تفتحه."}
        </p>

        {storeLink && (
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2">
            <code className="flex-1 text-sm break-all">{storeLink}</code>
            <button
              type="button"
              onClick={() => { void handleCopy(); }}
              className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold hover:bg-[var(--color-surface-3)]"
            >
              نسخ
            </button>
          </div>
        )}

        <div className="flex flex-wrap items-end gap-2">
          <label className="block">
            <span className="text-xs font-medium text-[var(--color-text-muted)]">معرّف المتجر</span>
            <input
              className={`${input} mt-1 w-64`}
              value={slugInput}
              onChange={(e) => setSlugInput(e.target.value)}
              placeholder="my-shop"
              dir="ltr"
              disabled={savingSlug}
            />
          </label>
          <button
            type="button"
            onClick={() => { void handleSaveSlug(); }}
            disabled={savingSlug || !slugInput.trim() || slugInput.trim() === savedSlug}
            className="rounded-md bg-[var(--color-primary)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            {savingSlug ? "..." : savedSlug ? "غيّر المعرّف" : "افتح المتجر"}
          </button>
          {savedSlug && (
            <button
              type="button"
              onClick={() => { void handleCloseStore(); }}
              disabled={savingSlug}
              className="rounded-md border border-[var(--color-border)] px-4 py-2 text-sm font-semibold hover:bg-[var(--color-surface-2)] disabled:opacity-50"
            >
              إقفال المتجر
            </button>
          )}
        </div>
      </section>

      {/* ── ما يُعرض في المتجر ───────────────────────────────────────── */}
      <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-3">
        <h3 className="text-base font-bold">ما يُعرض في المتجر</h3>
        <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
          اترك «سعر المتجر» فارغاً ليعرض المتجر سعر البيع المعتاد. الأرصدة والتكاليف لا
          تُعرض للزوار إطلاقاً — الزائر يرى حالة توفّر فقط.
          {/* قائمة المتجر مُكاشة 60 ثانية (`store/views.py`) — قوله هنا أرخص من
              أن يظنّ المستخدم أن تعديله لم يُحفظ فيعيده مرّات. */}
          {" "}وقد يتأخّر ظهور تعديلك في المتجر حتى دقيقة.
        </p>
        {/* `online_price` حقلٌ واحد يقرؤه المتجر ومحرّر فاتورة البيع معاً
            (`SalesInvoiceEditor.tsx`) — مقايضةٌ مقصودة موثَّقة في
            `docs/modules/store.md`. قولُها هنا يمنع تخفيضاً «للمتجر» يهبط
            بالسعر المقترح في الفواتير دون أن ينتبه صاحبه. */}
        <p className="text-xs text-amber-700 dark:text-amber-400 leading-relaxed">
          انتبه: «سعر المتجر» هو نفسه السعر الذي يقترحه محرّر فاتورة البيع لهذا الصنف —
          تخفيضه هنا يخفضه هناك أيضاً.
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-md border border-[var(--color-border)] overflow-hidden">
            {SCOPES.map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => setScope(s.key)}
                className={`px-3 py-1.5 text-xs font-semibold ${scope === s.key ? "bg-[var(--color-primary)] text-white" : "hover:bg-[var(--color-surface-2)]"}`}
              >
                {s.label}
              </button>
            ))}
          </div>
          <input
            className={`${input} w-64`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="ابحث باسم الصنف أو رقمه أو الماركة"
          />
          <span className="text-xs text-[var(--color-text-muted)]">
            {loading ? "..." : `${formatNumber(count)} صنفاً`}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-right text-xs text-[var(--color-text-muted)]">
                <th className="p-2 font-semibold">الصنف</th>
                <th className="p-2 font-semibold">سعر البيع</th>
                <th className="p-2 font-semibold">سعر المتجر</th>
                <th className="p-2 font-semibold">وصف المتجر</th>
                <th className="p-2 font-semibold">معروض</th>
                <th className="p-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((product) => {
                const draft = drafts[product.id] ?? draftOf(product);
                const busy = savingRow === product.id;
                return (
                  <tr key={product.id} className="border-t border-[var(--color-border)]">
                    <td className="p-2">
                      <div className="font-semibold">{storeAdminProductName(product)}</div>
                      <div className="text-xs text-[var(--color-text-muted)]">
                        {[product.sku, product.brand, product.category_name].filter(Boolean).join(" · ")}
                      </div>
                    </td>
                    <td className="p-2 whitespace-nowrap">
                      {formatNumber(product.sale_price, { maxDecimals: 4, fallback: "—" })}
                    </td>
                    <td className="p-2">
                      <input
                        className={`${input} w-28`}
                        value={draft.online_price}
                        onChange={(e) => setDrafts((prev) => ({
                          ...prev,
                          [product.id]: { ...draft, online_price: e.target.value },
                        }))}
                        placeholder="سعر البيع"
                        inputMode="decimal"
                        dir="ltr"
                        disabled={busy}
                      />
                    </td>
                    <td className="p-2">
                      <input
                        className={`${input} min-w-48`}
                        value={draft.online_description}
                        onChange={(e) => setDrafts((prev) => ({
                          ...prev,
                          [product.id]: { ...draft, online_description: e.target.value },
                        }))}
                        placeholder="وصف يراه الزائر"
                        disabled={busy}
                      />
                    </td>
                    <td className="p-2">
                      <input
                        type="checkbox"
                        checked={product.is_for_sale_online}
                        onChange={() => { void togglePublish(product); }}
                        disabled={busy}
                        aria-label={`عرض ${storeAdminProductName(product)} في المتجر`}
                        className="h-4 w-4 accent-[var(--color-primary)]"
                      />
                    </td>
                    <td className="p-2">
                      <button
                        type="button"
                        onClick={() => { void saveRow(product); }}
                        disabled={busy || !isDirty(product)}
                        className="rounded-md border border-[var(--color-border)] px-3 py-1 text-xs font-semibold hover:bg-[var(--color-surface-2)] disabled:opacity-40"
                      >
                        {busy ? "..." : "حفظ"}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-6 text-center text-sm text-[var(--color-text-muted)]">
                    {scope === "published"
                      ? "لا صنف معروضاً بعد — افتح تبويب «غير المعروضة» واختر ما تعرضه."
                      : "لا أصناف مطابقة."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {hasNext && (
          <button
            type="button"
            onClick={() => { void load(page + 1, false); }}
            disabled={loading}
            className="w-full rounded-md border border-[var(--color-border)] py-2 text-sm font-semibold hover:bg-[var(--color-surface-2)] disabled:opacity-50"
          >
            {loading ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : "عرض المزيد"}
          </button>
        )}
      </section>
    </div>
  );

  return (
    <div style={{ minHeight: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title="متجري"
        state={savedSlug ? `مفتوح — ${savedSlug}` : "مقفل"}
        actions={toolbarActions}
        header={<></>}
      >
        {inner}
      </AseelDocumentShell>
    </div>
  );
};

export default StoreSettingsPage;
