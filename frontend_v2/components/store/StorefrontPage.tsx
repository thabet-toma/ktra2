/**
 * واجهة متجر شركة واحدة — `/store/<slug>` لزائر بلا جلسة.
 *
 * ثلاث حالات نهائية لا حالتان: متجرٌ فيه أصناف، ومتجرٌ لا أصناف منشورة فيه،
 * و**متجرٌ غير موجود** (404: slug مجهول أو متجر مقفل أو شركة أخرى). الثالثة
 * ليست شاشة فارغة: الرابط يصل الزائرَ عبر واتساب، فصفحةٌ بيضاء تجعله يظنّ
 * الشبكة عطلت بينما الرابط نفسه خطأ.
 *
 * قوائم البراند والتصنيف تُبنى ممّا وصل من نتائج (اتحاد لا يتقلّص): الخادم
 * لا يقدّم نقطة facets، والقائمة المشتقّة من الصفحة الحالية وحدها كانت
 * ستُفرِغ نفسها بمجرّد أن يختار الزائر تصفية.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Copy, MessageCircle, MapPin, Search, Store as StoreIcon, X } from "lucide-react";

import { LoadingSpinner } from "../LoadingSpinner";
import { useToast } from "../../contexts/ToastContext";
import { useDocumentDescription, useDocumentTitle } from "../../hooks/useDocumentTitle";
import {
  getStoreProducts,
  getStoreProfile,
  isStoreNotFound,
  STORE_SORTS,
  type StoreProduct,
  type StoreProfile,
  type StoreSort,
} from "../../services/storeApi";
import { whatsappLink } from "../../utils/storeLinks";
import { StoreProductCard } from "./StoreProductCard";

interface StorefrontPageProps {
  slug: string;
  onOpenProduct: (productId: number) => void;
}

interface Facets {
  brands: string[];
  categories: string[];
}

function mergeFacets(previous: Facets, products: StoreProduct[]): Facets {
  const brands = new Set(previous.brands);
  const categories = new Set(previous.categories);
  products.forEach((product) => {
    if (product.brand) brands.add(product.brand);
    if (product.category_name) categories.add(product.category_name);
  });
  return {
    brands: [...brands].sort((a, b) => a.localeCompare(b, "ar")),
    categories: [...categories].sort((a, b) => a.localeCompare(b, "ar")),
  };
}

export const StorefrontPage: React.FC<StorefrontPageProps> = ({ slug, onOpenProduct }) => {
  const toast = useToast();

  const [profile, setProfile] = useState<StoreProfile | null>(null);
  const [products, setProducts] = useState<StoreProduct[]>([]);
  const [facets, setFacets] = useState<Facets>({ brands: [], categories: [] });
  const [count, setCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState<StoreSort>("");

  const pageRef = useRef(1);
  // كل تحميلٍ يحمل رقمه: ردٌّ بطيء لتصفيةٍ أُلغيت كان سيهبط بعد الردّ الحالي
  // فيعرض نتائج لا تطابق ما تُظهره الحقول.
  const requestRef = useRef(0);

  const storeName = profile?.name || "المتجر";
  useDocumentTitle(profile ? `${storeName} — المتجر الإلكتروني` : "المتجر الإلكتروني");
  useDocumentDescription(
    profile
      ? `تصفّح منتجات ${storeName} وأسعارها${profile.address ? ` — ${profile.address}` : ""}. للطلب تواصل معنا مباشرة.`
      : "متجر إلكتروني على منصة K.T.R.A.",
  );

  // بحثٌ مؤجَّل: طلبٌ لكل ضغطة حرف على نقطة مجهولة يستهلك سقف الخنق نفسه.
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 350);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    let alive = true;
    setProfile(null);
    getStoreProfile(slug)
      .then((data) => { if (alive) setProfile(data); })
      .catch((e: unknown) => {
        if (!alive) return;
        if (isStoreNotFound(e)) setMissing(true);
        else setError(e instanceof Error ? e.message : "تعذّر فتح المتجر");
      });
    return () => { alive = false; };
  }, [slug]);

  const load = useCallback(async () => {
    const ticket = ++requestRef.current;
    setLoading(true);
    setError(null);
    try {
      const page = await getStoreProducts(slug, { q: search, brand, category, sort, page: 1 });
      if (ticket !== requestRef.current) return;
      pageRef.current = 1;
      setProducts(page.results);
      setCount(page.count);
      setHasNext(page.hasNext);
      setFacets((previous) => mergeFacets(previous, page.results));
      setMissing(false);
    } catch (e: unknown) {
      if (ticket !== requestRef.current) return;
      if (isStoreNotFound(e)) setMissing(true);
      else setError(e instanceof Error ? e.message : "تعذّر تحميل المنتجات");
    } finally {
      if (ticket === requestRef.current) setLoading(false);
    }
  }, [slug, search, brand, category, sort]);

  useEffect(() => { void load(); }, [load]);

  const loadMore = useCallback(async () => {
    if (loadingMore) return;
    const ticket = requestRef.current;
    setLoadingMore(true);
    try {
      const next = pageRef.current + 1;
      const page = await getStoreProducts(slug, { q: search, brand, category, sort, page: next });
      if (ticket !== requestRef.current) return;
      pageRef.current = next;
      setProducts((previous) => [...previous, ...page.results]);
      setCount(page.count);
      setHasNext(page.hasNext);
      setFacets((previous) => mergeFacets(previous, page.results));
    } catch (e: unknown) {
      if (ticket === requestRef.current) {
        setError(e instanceof Error ? e.message : "تعذّر تحميل المزيد");
      }
    } finally {
      setLoadingMore(false);
    }
  }, [slug, search, brand, category, sort, loadingMore]);

  const copyStoreLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast("تم نسخ رابط المتجر", "success");
    } catch {
      // الحافظة ممنوعة (اتصال غير آمن أو رفض المستخدم) — نقول ذلك بدل الصمت.
      toast("تعذّر النسخ — انسخ الرابط من شريط العنوان", "error");
    }
  }, [toast]);

  const filtersActive = Boolean(search || brand || category || sort);
  const clearFilters = useCallback(() => {
    setSearchInput("");
    setSearch("");
    setBrand("");
    setCategory("");
    setSort("");
  }, []);

  const storeWhatsapp = useMemo(
    () => whatsappLink(profile?.phone, `مرحباً ${storeName}، أود الاستفسار عن منتجاتكم.`),
    [profile?.phone, storeName],
  );

  if (missing) {
    return (
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-100 p-6 dark:bg-slate-900">
        <div className="w-full max-w-lg rounded-3xl bg-white p-8 text-center shadow-xl dark:bg-slate-800">
          <StoreIcon className="mx-auto h-14 w-14 text-slate-300 dark:text-slate-600" />
          <h1 className="mt-4 text-xl font-black text-slate-900 dark:text-white">لا يوجد متجر بهذا الرابط</h1>
          <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">
            الرابط الذي فتحته (<span className="font-mono">/store/{slug}</span>) لا يقود إلى متجر مفتوح.
            تأكّد من نسخه كاملاً كما وصلك، أو اطلب من الشركة رابط متجرها من جديد.
          </p>
          <a
            href="/store"
            className="mt-6 inline-block rounded-xl bg-blue-600 px-6 py-3 font-bold text-white transition hover:bg-blue-700"
          >
            ما هي متاجر K.T.R.A؟
          </a>
        </div>
      </div>
    );
  }

  return (
    <div dir="rtl" className="min-h-screen bg-slate-100 dark:bg-slate-900">
      <header className="bg-white shadow-sm dark:bg-slate-800">
        <div className="mx-auto max-w-7xl px-4 py-6">
          <div className="flex flex-wrap items-center gap-4">
            {profile?.logo_url ? (
              <img src={profile.logo_url} alt={storeName} className="h-16 w-16 rounded-2xl object-contain" />
            ) : (
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-600 text-white">
                <StoreIcon className="h-8 w-8" />
              </div>
            )}
            <div className="flex-1">
              <h1 className="text-2xl font-black text-slate-900 dark:text-white">{storeName}</h1>
              {profile?.address ? (
                <p className="mt-1 flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400">
                  <MapPin className="h-4 w-4" />
                  {profile.address}
                </p>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {storeWhatsapp ? (
                <a
                  href={storeWhatsapp}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-emerald-600 px-4 text-sm font-bold text-white transition hover:bg-emerald-700"
                >
                  <MessageCircle className="h-4 w-4" />
                  تواصل واتساب
                </a>
              ) : profile?.phone ? (
                <a
                  href={`tel:${profile.phone}`}
                  className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-slate-300 px-4 text-sm font-bold text-slate-700 transition hover:bg-slate-50 dark:border-slate-600 dark:text-slate-200"
                >
                  <MessageCircle className="h-4 w-4" />
                  {profile.phone}
                </a>
              ) : null}
              <button
                type="button"
                onClick={() => void copyStoreLink()}
                className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-slate-300 px-4 text-sm font-bold text-slate-700 transition hover:bg-slate-50 dark:border-slate-600 dark:text-slate-200"
              >
                <Copy className="h-4 w-4" />
                نسخ الرابط
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="border-b border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <input
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="ابحث بالاسم أو الماركة…"
              aria-label="بحث في منتجات المتجر"
              className="min-h-11 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-700 dark:text-white"
            />
            <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          </div>

          <div className="flex flex-wrap gap-2">
            {facets.brands.length > 0 ? (
              <select
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
                aria-label="تصفية بالماركة"
                className="min-h-11 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-700 dark:text-white"
              >
                <option value="">كل الماركات</option>
                {facets.brands.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            ) : null}

            {facets.categories.length > 0 ? (
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                aria-label="تصفية بالتصنيف"
                className="min-h-11 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-700 dark:text-white"
              >
                <option value="">كل التصنيفات</option>
                {facets.categories.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            ) : null}

            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as StoreSort)}
              aria-label="ترتيب النتائج"
              className="min-h-11 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-700 dark:text-white"
            >
              {STORE_SORTS.map((option) => (
                <option key={option.key} value={option.key}>{option.label}</option>
              ))}
            </select>

            {filtersActive ? (
              <button
                type="button"
                onClick={clearFilters}
                className="inline-flex min-h-11 items-center gap-1 rounded-xl border border-red-200 bg-red-50 px-3 text-sm font-bold text-red-700 transition hover:bg-red-100 dark:border-red-900 dark:bg-red-900/20 dark:text-red-300"
              >
                <X className="h-4 w-4" />
                إلغاء التصفية
              </button>
            ) : null}
          </div>
        </div>
      </div>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {error ? (
          <div role="alert" className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-center font-bold text-red-800 dark:border-red-900 dark:bg-red-900/20 dark:text-red-300">
            {error}
          </div>
        ) : null}

        {loading ? (
          <div className="flex justify-center py-20"><LoadingSpinner showText={false} /></div>
        ) : products.length === 0 ? (
          <div className="py-20 text-center">
            <StoreIcon className="mx-auto h-16 w-16 text-slate-300 dark:text-slate-600" />
            <h2 className="mt-4 text-lg font-bold text-slate-700 dark:text-slate-200">
              {filtersActive ? "لا نتائج مطابقة لبحثك" : "لا توجد منتجات معروضة بعد"}
            </h2>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
              {filtersActive ? "جرّب كلمة أخرى أو ألغِ التصفية." : "هذا المتجر لم ينشر أصنافاً حتى الآن — عُد لاحقاً."}
            </p>
            {filtersActive ? (
              <button
                type="button"
                onClick={clearFilters}
                className="mt-6 rounded-xl bg-blue-600 px-6 py-3 font-bold text-white transition hover:bg-blue-700"
              >
                عرض كل المنتجات
              </button>
            ) : null}
          </div>
        ) : (
          <>
            <p className="mb-4 text-sm font-bold text-slate-500 dark:text-slate-400">
              {`عرض ${products.length} من ${count} منتجاً`}
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 sm:gap-6">
              {products.map((product) => (
                <StoreProductCard
                  key={product.id}
                  product={product}
                  currency={profile?.currency ?? null}
                  onOpen={(item) => onOpenProduct(item.id)}
                />
              ))}
            </div>

            {hasNext ? (
              <div className="mt-10 text-center">
                <button
                  type="button"
                  onClick={() => void loadMore()}
                  disabled={loadingMore}
                  className="rounded-xl border-2 border-blue-600 bg-white px-8 py-3 font-bold text-blue-600 transition hover:bg-blue-50 disabled:opacity-60 dark:bg-slate-800 dark:text-blue-400"
                >
                  {loadingMore ? "جارٍ التحميل…" : "عرض المزيد"}
                </button>
              </div>
            ) : null}
          </>
        )}
      </main>

      <footer className="mt-8 border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
        <p>{storeName} — الأسعار والتوفّر قابلة للتغيير. للطلب تواصل مع المتجر مباشرة.</p>
        <p className="mt-1">
          متجر على منصة <a href="/" className="font-bold text-blue-600 hover:underline dark:text-blue-400">K.T.R.A</a>
        </p>
      </footer>
    </div>
  );
};

export default StorefrontPage;
