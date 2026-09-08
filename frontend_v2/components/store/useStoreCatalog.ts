/**
 * حالة الفلترة والشبكة المشتركة بين الرئيسية وصفحة الفئة (THA-166 م٧، قسم د).
 *
 * ملفٌّ خالصٌ بلا استيراد من `components/kit` ولا سياق React — يبقى مسار
 * المتجر خفيفاً وكسولَ التحميل (انظر القيد المعماري في وصف المهمة).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getStoreProducts,
  isStoreNotFound,
  type StoreFacets,
  type StoreProduct,
  type StoreProductListResult,
  type StoreProductQuery,
  type StorePriceRange,
  type StoreSort,
} from "../../services/storeApi";

/**
 * دالّةُ جلبٍ محقونة — الافتراضي `getStoreProducts(slug, query)` (الرئيسية
 * والفئة). صفحة الحملة تحقن دالّتها الخاصّة (تمرّ عبر `getStoreCollectionDetail`
 * وتُقيَّد بمنتجات الحملة وحدها) بدل نسخِ منطق الجلب/الفلترة/الصفحات هنا ثانية.
 * **يجب أن تبقى مرجعيّةُ الدالّة مستقرّة** (`useCallback` عند المستدعي) وإلا
 * أعاد كلُّ عرضٍ الجلبَ من جديد.
 */
export type StoreCatalogFetcher = (query: StoreProductQuery) => Promise<StoreProductListResult>;

export interface StoreCatalogOptions {
  /** فئةٌ مبدئيّة (صفحة الفئة) — تُحمَّل مرّةً واحدة، والمستخدم حرٌّ بعدها بتغييرها. */
  initialCategoryIds?: number[];
  fetcher?: StoreCatalogFetcher;
}

function joinIds(ids: number[]): string | undefined {
  return ids.length ? ids.join(",") : undefined;
}

export function useStoreCatalog(slug: string, options: StoreCatalogOptions = {}) {
  // مُثبَّتةٌ بـ`useCallback` كي لا تتغيّر مرجعيّتُها كلَّ عرضٍ حين لا يُحقَن
  // بديلٌ — وإلا أعاد اعتمادُ `load`/`loadMore` عليها الجلبَ في حلقةٍ لا تتوقّف.
  const defaultFetcher = useCallback(
    (query: StoreProductQuery) => getStoreProducts(slug, query),
    [slug],
  );
  const fetcher = options.fetcher ?? defaultFetcher;
  const [products, setProducts] = useState<StoreProduct[]>([]);
  const [facets, setFacets] = useState<StoreFacets | null>(null);
  const [priceRange, setPriceRange] = useState<StorePriceRange | null>(null);
  const [count, setCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [brandIds, setBrandIds] = useState<number[]>([]);
  const [categoryIds, setCategoryIds] = useState<number[]>(options.initialCategoryIds || []);
  const [onSale, setOnSale] = useState(false);
  const [isNew, setIsNew] = useState(false);
  const [inStock, setInStock] = useState(false);
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [sort, setSort] = useState<StoreSort>("");

  const pageRef = useRef(1);
  const requestRef = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 350);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const load = useCallback(async () => {
    const ticket = ++requestRef.current;
    setLoading(true);
    setError(null);
    try {
      const page = await fetcher({
        q: search,
        brand: joinIds(brandIds),
        category: joinIds(categoryIds),
        onSale,
        isNew,
        inStock,
        minPrice: minPrice || undefined,
        maxPrice: maxPrice || undefined,
        sort,
        page: 1,
      });
      if (ticket !== requestRef.current) return;
      pageRef.current = 1;
      setProducts(page.results);
      setCount(page.count);
      setHasNext(page.hasNext);
      // العدّاداتُ تصل بالصفحة الأولى دائماً؛ حين تغيب (احتمالٌ نظريّ) تبقى
      // القيمة السابقة بدل إفراغ الشريط الجانبي فجأة.
      if (page.facets) setFacets(page.facets);
      setPriceRange(page.price_range ?? null);
      setMissing(false);
    } catch (e: unknown) {
      if (ticket !== requestRef.current) return;
      if (isStoreNotFound(e)) setMissing(true);
      else setError(e instanceof Error ? e.message : "تعذّر تحميل المنتجات");
    } finally {
      if (ticket === requestRef.current) setLoading(false);
    }
  }, [fetcher, search, brandIds, categoryIds, onSale, isNew, inStock, minPrice, maxPrice, sort]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadMore = useCallback(async () => {
    if (loadingMore) return;
    const ticket = requestRef.current;
    setLoadingMore(true);
    try {
      const next = pageRef.current + 1;
      const page = await fetcher({
        q: search,
        brand: joinIds(brandIds),
        category: joinIds(categoryIds),
        onSale,
        isNew,
        inStock,
        minPrice: minPrice || undefined,
        maxPrice: maxPrice || undefined,
        sort,
        page: next,
      });
      if (ticket !== requestRef.current) return;
      pageRef.current = next;
      setProducts((previous) => [...previous, ...page.results]);
      setCount(page.count);
      setHasNext(page.hasNext);
    } catch (e: unknown) {
      if (ticket === requestRef.current) {
        setError(e instanceof Error ? e.message : "تعذّر تحميل المزيد");
      }
    } finally {
      setLoadingMore(false);
    }
  }, [fetcher, search, brandIds, categoryIds, onSale, isNew, inStock, minPrice, maxPrice, sort, loadingMore]);

  const toggleBrand = useCallback((id: number) => {
    setBrandIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }, []);

  const toggleCategory = useCallback((id: number) => {
    setCategoryIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }, []);

  const setPriceBounds = useCallback((min: string, max: string) => {
    setMinPrice(min);
    setMaxPrice(max);
  }, []);

  /** عددُ محاور الفلترة المطبَّقة — للزرّ العائم على الجوّال «تصفية (٣)». لا يحسب النص أو الفرز. */
  const activeFacetCount =
    brandIds.length +
    categoryIds.length +
    (onSale ? 1 : 0) +
    (isNew ? 1 : 0) +
    (inStock ? 1 : 0) +
    (minPrice || maxPrice ? 1 : 0);

  const filtersActive = Boolean(search) || activeFacetCount > 0 || Boolean(sort);

  const clearFilters = useCallback(() => {
    setSearchInput("");
    setSearch("");
    setBrandIds([]);
    setCategoryIds([]);
    setOnSale(false);
    setIsNew(false);
    setInStock(false);
    setMinPrice("");
    setMaxPrice("");
    setSort("");
  }, []);

  return {
    products,
    facets,
    priceRange,
    count,
    hasNext,
    loading,
    loadingMore,
    missing,
    error,
    loadMore,
    searchInput,
    setSearchInput,
    brandIds,
    toggleBrand,
    categoryIds,
    toggleCategory,
    setCategoryIds,
    onSale,
    setOnSale,
    isNew,
    setIsNew,
    inStock,
    setInStock,
    minPrice,
    maxPrice,
    setPriceBounds,
    sort,
    setSort,
    activeFacetCount,
    filtersActive,
    clearFilters,
  };
}

export type UseStoreCatalogResult = ReturnType<typeof useStoreCatalog>;
