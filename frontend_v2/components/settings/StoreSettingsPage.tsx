/**
 * لوحة التحكم وإدارة المتجر الإلكتروني — ST-3 & ST-4 & ST-5
 *
 * إدارة الرابط العام، المنتجات والصور المخصصة، الطلب المسبق، الحملات والمجموعات الإعلانية، وتخصيص المظهر والهوية.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowUpRight,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  Download,
  Flame,
  Globe,
  Image as ImageIcon,
  ImagePlus,
  Layers,
  LayoutGrid,
  Loader2,
  Lock,
  Megaphone,
  MessageCircle,
  Palette,
  Plus,
  RefreshCw,
  Search,
  Share2,
  ShoppingBag,
  Sparkles,
  Store,
  Tag,
  Trash2,
  Type,
  Upload,
  X,
} from "lucide-react";

import {
  StoreImageOverlay,
  downloadAdCreativeImage,
  OVERLAY_COLOR_PRESETS,
  OVERLAY_STYLE_PRESETS,
} from "../store/StoreImageOverlay";

import { useCompany } from "../../contexts/CompanyContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { CloudinaryService } from "../../services/cloudinaryService";
import { clientLogger } from "../../services/logger";
import {
  addStoreCollectionItemAdmin,
  createStoreCollectionAdmin,
  createStoreProduct,
  createStoreProductImage,
  deleteStoreCollectionAdmin,
  deleteStoreCollectionItemAdmin,
  deleteStoreProduct,
  deleteStoreProductImage,
  getPublishedProducts,
  getStoreAdminProducts,
  getStoreCollectionItemsAdmin,
  getStoreCollectionsAdmin,
  getStoreProductImages,
  getStoreThemeSettings,
  setStoreSlug,
  storeAdminProductName,
  updateProductPublishing,
  updateStoreCollectionAdmin,
  updateStoreProductImage,
  updateStoreThemeSettings,
  type StoreAdminProduct,
  type StoreAdminScope,
  type StoreCollectionAdmin,
  type StoreCollectionItemAdmin,
  type StoreProductImageAdmin,
  type StoreThemeSettings,
} from "../../services/storeAdminApi";
import { humanizeDrfError } from "../../utils/drfError";
import { formatNumber } from "../../utils/formatNumber";
import { storeHomeUrl } from "../../utils/storeLinks";
import { KitDocumentShell, type KitToolbarAction } from "../kit";

const cloudinaryService = new CloudinaryService();

type ActiveTab = "overview" | "products" | "campaigns" | "theme";

type RowDraft = {
  online_price: string;
  online_description: string;
  allow_preorder: boolean;
};

const SCOPES: { key: StoreAdminScope; label: string }[] = [
  { key: "published", label: "المعروضة في المتجر" },
  { key: "unpublished", label: "غير المعروضة" },
  { key: "all", label: "كل الأصناف" },
];

const draftOf = (product: StoreAdminProduct): RowDraft => ({
  online_price: product.online_price ?? "",
  online_description: product.online_description ?? "",
  allow_preorder: product.allow_preorder ?? false,
});

export const StoreSettingsPage: React.FC = () => {
  const { currentCompany, refreshCompanies } = useCompany();
  const confirm = useConfirm();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<ActiveTab>("overview");

  // المتجر والمعرّف
  const savedSlug = currentCompany?.store_slug || "";
  const [slugInput, setSlugInput] = useState(savedSlug);
  const [savingSlug, setSavingSlug] = useState(false);

  // جدول الأصناف
  const [scope, setScope] = useState<StoreAdminScope>("published");
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<StoreAdminProduct[]>([]);
  const [drafts, setDrafts] = useState<Record<number, RowDraft>>({});
  const [count, setCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [page, setPage] = useState(1);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [savingRow, setSavingRow] = useState<number | null>(null);

  // نافذة إدارة صور المتجر المخصصة للصنف
  const [selectedProductForMedia, setSelectedProductForMedia] =
    useState<StoreAdminProduct | null>(null);
  const [customImages, setCustomImages] = useState<StoreProductImageAdmin[]>([]);
  const [loadingMedia, setLoadingMedia] = useState(false);
  const [uploadingMedia, setUploadingMedia] = useState(false);

  // نافذة تخصيص النص الإعلاني وشريط العرض فوق الصورة
  const [editingOverlayImage, setEditingOverlayImage] =
    useState<StoreProductImageAdmin | null>(null);
  const [overlayForm, setOverlayForm] = useState({
    text: "",
    style: "diagonal_ribbon",
    colorKey: "red_fire",
  });
  const [savingOverlay, setSavingOverlay] = useState(false);
  const [downloadingAd, setDownloadingAd] = useState(false);

  // نافذة إضافة منتج جديد للمتجر مباشرة
  const [isCreatingProductModal, setIsCreatingProductModal] = useState(false);
  const [creatingProduct, setCreatingProduct] = useState(false);
  const [newProductForm, setNewProductForm] = useState({
    name_ar: "",
    name_en: "",
    brand: "",
    sku: "",
    online_price: "",
    online_description: "",
    allow_preorder: true,
    is_for_sale_online: true,
  });
  const [newProductImages, setNewProductImages] = useState<string[]>([]);
  const [uploadingNewProductImage, setUploadingNewProductImage] = useState(false);

  // المجموعات والحملات الإعلانية
  const [collections, setCollections] = useState<StoreCollectionAdmin[]>([]);
  const [loadingCollections, setLoadingCollections] = useState(false);
  const [selectedCollection, setSelectedCollection] =
    useState<StoreCollectionAdmin | null>(null);
  const [collectionItems, setCollectionItems] = useState<StoreCollectionItemAdmin[]>([]);
  const [loadingItems, setLoadingItems] = useState(false);
  const [isEditingCollectionModal, setIsEditingCollectionModal] = useState(false);
  const [collectionForm, setCollectionForm] = useState<Partial<StoreCollectionAdmin>>({
    title: "",
    slug: "",
    description: "",
    banner_image_url: "",
    badge_text: "",
    is_active: true,
  });

  // إعدادات المظهر والهوية
  const [themeSettings, setThemeSettings] = useState<StoreThemeSettings>({
    hero_title: "",
    hero_subtitle: "",
    announcement_bar: "",
    show_announcement: false,
    theme_preset: "modern_clean",
    primary_color: "#2563eb",
    accent_color: "#10b981",
    background_color: "#f8fafc",
    background_image_url: null,
    background_style: "cover",
    banner_image_url: null,
    instagram_url: null,
    tiktok_url: null,
    facebook_url: null,
    snapchat_url: null,
    whatsapp_number: null,
    catalog_mode_default: "grid",
    allow_cart: true,
  });
  const [loadingTheme, setLoadingTheme] = useState(false);
  const [savingTheme, setSavingTheme] = useState(false);

  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setSlugInput(savedSlug);
  }, [savedSlug]);

  const storeLink = savedSlug ? storeHomeUrl(window.location.origin, savedSlug) : null;

  // تحميل المنتجات
  const loadProducts = useCallback(
    async (nextPage: number, replace: boolean) => {
      setLoadingProducts(true);
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
        setLoadingProducts(false);
      }
    },
    [scope, search],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadProducts(1, true);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [loadProducts]);

  // تحميل المجموعات
  const loadCollections = useCallback(async () => {
    if (!savedSlug) return;
    setLoadingCollections(true);
    try {
      const data = await getStoreCollectionsAdmin();
      setCollections(data);
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    } finally {
      setLoadingCollections(false);
    }
  }, [savedSlug, toast]);

  // تحميل إعدادات المظهر
  const loadThemeSettings = useCallback(async () => {
    if (!savedSlug) return;
    setLoadingTheme(true);
    try {
      const data = await getStoreThemeSettings();
      setThemeSettings(data);
    } catch (e) {
      // قد لا تكون منشأة بعد
    } finally {
      setLoadingTheme(false);
    }
  }, [savedSlug]);

  useEffect(() => {
    if (activeTab === "campaigns") {
      void loadCollections();
    } else if (activeTab === "theme") {
      void loadThemeSettings();
    }
  }, [activeTab, loadCollections, loadThemeSettings]);

  // فتح / تغيير معرّف المتجر
  const handleSaveSlug = async () => {
    if (!currentCompany) return;
    const slug = slugInput.trim();
    if (!slug || slug === savedSlug) return;

    if (!savedSlug) {
      const published = await getPublishedProducts();
      if (published.count > 0) {
        const ok = await confirm({
          title: "فتح المتجر للزوار",
          message: `سيتم فتح المتجر بالمعرف «${slug}» وسيتم عرض ${published.count} منتج معلّم للبيع. هل تود المتابعة؟`,
          confirmText: "افتح المتجر الآن",
          cancelText: "إلغاء",
        });
        if (!ok) return;
      }
    }

    setSavingSlug(true);
    setErr(null);
    try {
      await setStoreSlug(currentCompany.TenantID, slug);
      await refreshCompanies();
      toast(savedSlug ? "تم تحديث رابط المتجر بنجاح." : "مبروك! تم فتح متجرك الإلكتروني.", "success");
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
      message: "هل أنت متأكد من إقفال المتجر؟ سيتوقف الرابط عن العمل ولن يتمكن الزبائن من الوصول إليه.",
      confirmText: "أقفل المتجر",
      cancelText: "تراجع",
      danger: true,
    });
    if (!ok) return;

    setSavingSlug(true);
    try {
      await setStoreSlug(currentCompany.TenantID, "");
      await refreshCompanies();
      toast("تم إقفال المتجر.", "info");
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    } finally {
      setSavingSlug(false);
    }
  };

  // تبديل حالة النشر للصنف
  const togglePublish = async (product: StoreAdminProduct) => {
    const next = !product.is_for_sale_online;
    setSavingRow(product.id);
    try {
      await updateProductPublishing(product.id, { is_for_sale_online: next });
      if (scope === "all") {
        setRows((prev) =>
          prev.map((r) => (r.id === product.id ? { ...r, is_for_sale_online: next } : r)),
        );
      } else {
        setRows((prev) => prev.filter((r) => r.id !== product.id));
        setCount((c) => Math.max(0, c - 1));
      }
      toast(next ? "تم عرض المنتج في المتجر" : "تم إلغاء عرض المنتج", "success");
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    } finally {
      setSavingRow(null);
    }
  };

  // تبديل إتاحة الطلب المسبق (Pre-order toggle)
  const togglePreorder = async (product: StoreAdminProduct) => {
    const next = !product.allow_preorder;
    setSavingRow(product.id);
    try {
      await updateProductPublishing(product.id, { allow_preorder: next });
      setRows((prev) =>
        prev.map((r) => (r.id === product.id ? { ...r, allow_preorder: next } : r)),
      );
      toast(
        next
          ? "ميزة الطلب المسبق مفعّلة — يمكن للزبائن طلبه حتى لو نفد المخزون"
          : "تم إلغاء ميزة الطلب المسبق",
        "success",
      );
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    } finally {
      setSavingRow(null);
    }
  };

  // حفظ تعديلات الصف (السعر الخاص والوصف)
  const saveProductRow = async (product: StoreAdminProduct) => {
    const draft = drafts[product.id];
    if (!draft) return;
    setSavingRow(product.id);
    try {
      const saved = await updateProductPublishing(product.id, {
        online_price: draft.online_price.trim() === "" ? null : draft.online_price.trim(),
        online_description: draft.online_description.trim(),
        allow_preorder: draft.allow_preorder,
      });
      setRows((prev) => prev.map((r) => (r.id === product.id ? { ...r, ...saved } : r)));
      toast("تم حفظ التعديلات", "success");
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    } finally {
      setSavingRow(null);
    }
  };

  // ── إدارة الصور المخصصة ────────────────────────────────────────────────
  const openMediaModal = async (product: StoreAdminProduct) => {
    setSelectedProductForMedia(product);
    setLoadingMedia(true);
    try {
      const imgs = await getStoreProductImages(product.id);
      setCustomImages(imgs);
    } catch (e) {
      toast("تعذّر جلب صور المتجر للمنتج", "error");
    } finally {
      setLoadingMedia(false);
    }
  };

  const handleUploadCustomImage = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedProductForMedia) return;

    setUploadingMedia(true);
    try {
      const url = await cloudinaryService.uploadFile(file);
      const created = await createStoreProductImage({
        product: selectedProductForMedia.id,
        image_url: url,
        is_cover: customImages.length === 0,
        sort_order: customImages.length + 1,
      });
      setCustomImages((prev) => [...prev, created]);
      toast("تم رفع صورة المتجر بنجاح", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "فشل رفع الصورة", "error");
    } finally {
      setUploadingMedia(false);
      e.target.value = "";
    }
  };

  const handleSetCoverImage = async (image: StoreProductImageAdmin) => {
    try {
      await updateStoreProductImage(image.id, { is_cover: true });
      setCustomImages((prev) =>
        prev.map((img) => ({
          ...img,
          is_cover: img.id === image.id,
        })),
      );
      toast("تم تعيين الصورة كصورة غلاف رئيسية في المتجر", "success");
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    }
  };

  const handleDeleteCustomImage = async (image: StoreProductImageAdmin) => {
    try {
      await deleteStoreProductImage(image.id);
      setCustomImages((prev) => prev.filter((img) => img.id !== image.id));
      toast("تم حذف الصورة بنجاح", "success");
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    }
  };

  const handleOpenOverlayModal = (image: StoreProductImageAdmin) => {
    setEditingOverlayImage(image);
    setOverlayForm({
      text: image.overlay_text || "",
      style: image.overlay_style || "diagonal_ribbon",
      colorKey: image.overlay_color || "red_fire",
    });
  };

  const handleSaveImageOverlay = async () => {
    if (!editingOverlayImage) return;
    try {
      setSavingOverlay(true);
      const updated = await updateStoreProductImage(editingOverlayImage.id, {
        overlay_text: overlayForm.text.trim(),
        overlay_style: overlayForm.style,
        overlay_color: overlayForm.colorKey,
      });
      setCustomImages((prev) =>
        prev.map((img) => (img.id === updated.id ? updated : img)),
      );
      toast("تم حفظ النص الإعلاني على الصورة بنجاح!", "success");
      setEditingOverlayImage(null);
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    } finally {
      setSavingOverlay(false);
    }
  };

  const handleDownloadAdCreative = async () => {
    if (!editingOverlayImage) return;
    try {
      setDownloadingAd(true);
      await downloadAdCreativeImage({
        imageUrl: editingOverlayImage.image_url,
        text: overlayForm.text.trim() || "عرض خاص",
        style: overlayForm.style,
        colorKey: overlayForm.colorKey,
        productName: selectedProductForMedia
          ? storeAdminProductName(selectedProductForMedia)
          : "product-ad",
      });
      toast("تم تصدير وتحميل صورة الإعلان بنجاح!", "success");
    } catch {
      toast("تعذر تحميل الصورة، يرجى التأكد من اتصال الإنترنت والمحاولة ثانية", "error");
    } finally {
      setDownloadingAd(false);
    }
  };

  // ── إضافة وحذف منتجات المتجر المباشرة ────────────────────────────────────
  const handleUploadNewProductImage = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingNewProductImage(true);
    try {
      const url = await cloudinaryService.uploadFile(file);
      setNewProductImages((prev) => [...prev, url]);
      toast("تم رفع الصورة بنجاح", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "فشل رفع الصورة", "error");
    } finally {
      setUploadingNewProductImage(false);
      e.target.value = "";
    }
  };

  const handleCreateStoreProduct = async () => {
    if (!newProductForm.name_ar.trim()) {
      toast("يرجى إدخال اسم المنتج بالعربية", "error");
      return;
    }
    setCreatingProduct(true);
    try {
      const created = await createStoreProduct({
        ...newProductForm,
        initial_images: newProductImages,
      });
      setRows((prev) => [created, ...prev]);
      setDrafts((prev) => ({
        ...prev,
        [created.id]: draftOf(created),
      }));
      setCount((prev) => prev + 1);
      setIsCreatingProductModal(false);
      setNewProductForm({
        name_ar: "",
        name_en: "",
        brand: "",
        sku: "",
        online_price: "",
        online_description: "",
        allow_preorder: true,
        is_for_sale_online: true,
      });
      setNewProductImages([]);
      toast("تمت إضافة المنتج للمتجر بنجاح!", "success");
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    } finally {
      setCreatingProduct(false);
    }
  };

  const handleDeleteStoreProduct = async (product: StoreAdminProduct) => {
    const ok = await confirm({
      title: "حذف الصنف من المتجر",
      message: `هل أنت متأكد من حذف «${storeAdminProductName(product)}» من المتجر؟`,
      confirmText: "حذف",
      cancelText: "إلغاء",
      danger: true,
    });
    if (!ok) return;

    try {
      await deleteStoreProduct(product.id);
      setRows((prev) => prev.filter((p) => p.id !== product.id));
      setCount((prev) => Math.max(0, prev - 1));
      toast("تم حذف الصنف من المتجر بنجاح", "success");
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    }
  };

  // ── إدارة المجموعات والحملات ──────────────────────────────────────────
  const openCollectionDetail = async (col: StoreCollectionAdmin) => {
    setSelectedCollection(col);
    setLoadingItems(true);
    try {
      const items = await getStoreCollectionItemsAdmin(col.id);
      setCollectionItems(items);
    } catch (e) {
      toast("تعذّر جلب عناصر المجموعة", "error");
    } finally {
      setLoadingItems(false);
    }
  };

  const handleSaveCollectionForm = async () => {
    if (!collectionForm.title || !collectionForm.slug) {
      toast("يرجى ملء عنوان الحملة والمعرف", "error");
      return;
    }

    try {
      if (collectionForm.id) {
        const updated = await updateStoreCollectionAdmin(collectionForm.id, collectionForm);
        setCollections((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
        toast("تم تحديث الحملة بنجاح", "success");
      } else {
        const created = await createStoreCollectionAdmin(collectionForm);
        setCollections((prev) => [created, ...prev]);
        toast("تم إنشاء الحملة الإعلانية بنجاح", "success");
      }
      setIsEditingCollectionModal(false);
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    }
  };

  const handleDeleteCollection = async (col: StoreCollectionAdmin) => {
    const ok = await confirm({
      title: "حذف الحملة / المجموعة",
      message: `هل أنت متأكد من حذف «${col.title}»؟ سيتوقف رابط الإعلان المرتبط بها.`,
      confirmText: "حذف نهائي",
      cancelText: "إلغاء",
      danger: true,
    });
    if (!ok) return;

    try {
      await deleteStoreCollectionAdmin(col.id);
      setCollections((prev) => prev.filter((c) => c.id !== col.id));
      if (selectedCollection?.id === col.id) setSelectedCollection(null);
      toast("تم حذف الحملة بنجاح", "success");
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    }
  };

  const handleAddItemToCollection = async (productId: number) => {
    if (!selectedCollection) return;
    try {
      const item = await addStoreCollectionItemAdmin({
        collection: selectedCollection.id,
        product: productId,
        sort_order: collectionItems.length + 1,
      });
      setCollectionItems((prev) => [...prev, item]);
      setCollections((prev) =>
        prev.map((c) =>
          c.id === selectedCollection.id
            ? { ...c, items_count: (c.items_count || 0) + 1 }
            : c,
        ),
      );
      toast("تمت إضافة المنتج للحملة", "success");
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    }
  };

  const handleDeleteCollectionItem = async (itemId: number) => {
    try {
      await deleteStoreCollectionItemAdmin(itemId);
      setCollectionItems((prev) => prev.filter((i) => i.id !== itemId));
      if (selectedCollection) {
        setCollections((prev) =>
          prev.map((c) =>
            c.id === selectedCollection.id
              ? { ...c, items_count: Math.max(0, (c.items_count || 1) - 1) }
              : c,
          ),
        );
      }
      toast("تمت إزالة المنتج من الحملة", "success");
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    }
  };

  // ── حفظ إعدادات المظهر والهوية ─────────────────────────────────────────
  const handleSaveThemeSettings = async () => {
    setSavingTheme(true);
    try {
      const saved = await updateStoreThemeSettings(themeSettings);
      setThemeSettings(saved);
      toast("تم حفظ إعدادات المظهر والهوية بنجاح!", "success");
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    } finally {
      setSavingTheme(false);
    }
  };

  const handleUploadThemeImage = async (
    field: "background_image_url" | "banner_image_url",
    file: File,
  ) => {
    try {
      toast("جارٍ رفع الصورة...", "info");
      const url = await cloudinaryService.uploadFile(file);
      setThemeSettings((prev) => ({ ...prev, [field]: url }));
      toast("تم رفع الصورة بنجاح", "success");
    } catch (e) {
      toast("فشل رفع الصورة", "error");
    }
  };

  return (
    <KitDocumentShell
      title="إدارة وتخصيص المتجر الإلكتروني"
      subtitle="تحكم كامل في المنتجات المعروضة، صور المتجر المخصصة، الحملات الإعلانية، والمظهر والتصميم"
    >
      <div className="space-y-6 font-sans" dir="rtl">
        {/* أشرطة التبويب الرئيسية */}
        <div className="flex items-center gap-2 overflow-x-auto border-b border-slate-200 pb-2 dark:border-slate-800">
          <button
            type="button"
            onClick={() => setActiveTab("overview")}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition ${
              activeTab === "overview"
                ? "bg-blue-600 text-white shadow-md shadow-blue-600/20"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            <Globe className="h-4 w-4" />
            <span>نظرة عامة والروابط</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("products")}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition ${
              activeTab === "products"
                ? "bg-blue-600 text-white shadow-md shadow-blue-600/20"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            <LayoutGrid className="h-4 w-4" />
            <span>المنتجات والصور المخصصة</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("campaigns")}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition ${
              activeTab === "campaigns"
                ? "bg-blue-600 text-white shadow-md shadow-blue-600/20"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            <Megaphone className="h-4 w-4" />
            <span>المجموعات والحملات الإعلانية</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("theme")}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition ${
              activeTab === "theme"
                ? "bg-blue-600 text-white shadow-md shadow-blue-600/20"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
          >
            <Palette className="h-4 w-4" />
            <span>المظهر والتخصيص</span>
          </button>
        </div>

        {/* ── TAB 1: OVERVIEW ────────────────────────────────────────────── */}
        {activeTab === "overview" && (
          <div className="space-y-6">
            {/* بطاقة التحكم في الرابط والتفعيل */}
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <h3 className="text-base font-black text-slate-900 dark:text-white">
                رابط المتجر ومعرف الشركة
              </h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                المعرف الإنجليزي الفريد الذي يصل من خلاله زبائنك لمتجرك
              </p>

              <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="flex flex-1 items-center rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-800" dir="ltr">
                  <span className="text-slate-400 font-mono select-none">/store/</span>
                  <input
                    type="text"
                    value={slugInput}
                    onChange={(e) => setSlugInput(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))}
                    placeholder="my-store-name"
                    className="flex-1 bg-transparent px-1 font-mono font-bold text-slate-900 focus:outline-none dark:text-white"
                  />
                </div>

                <button
                  type="button"
                  onClick={handleSaveSlug}
                  disabled={savingSlug || slugInput === savedSlug || !slugInput}
                  className="rounded-2xl bg-blue-600 px-6 py-2.5 text-xs font-bold text-white shadow-md shadow-blue-600/20 transition hover:bg-blue-700 disabled:opacity-50"
                >
                  {savingSlug ? "جارٍ الحفظ…" : savedSlug ? "تغيير الرابط" : "فتح المتجر الآن"}
                </button>

                {savedSlug && (
                  <button
                    type="button"
                    onClick={handleCloseStore}
                    disabled={savingSlug}
                    className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2.5 text-xs font-bold text-rose-700 transition hover:bg-rose-100 dark:border-rose-900 dark:bg-rose-900/20 dark:text-rose-300"
                  >
                    إقفال المتجر
                  </button>
                )}
              </div>

              {savedSlug && storeLink && (
                <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-200/80 bg-emerald-50/50 p-4 dark:border-emerald-900/50 dark:bg-emerald-950/20">
                  <div className="flex items-center gap-2 text-emerald-800 dark:text-emerald-300">
                    <CheckCircle2 className="h-5 w-5" />
                    <span className="text-xs font-bold">متجرك نشط ومتاح أونلاين على الرابط:</span>
                    <a
                      href={storeLink}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono font-bold underline dir-ltr"
                    >
                      {storeLink}
                    </a>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(storeLink);
                        toast("تم نسخ رابط المتجر", "success");
                      }}
                      className="flex items-center gap-1 rounded-xl bg-white px-3 py-1.5 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 dark:bg-slate-800 dark:text-slate-200"
                    >
                      <Copy className="h-3.5 w-3.5" />
                      <span>نسخ</span>
                    </button>
                    <a
                      href={storeLink}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white shadow-sm transition hover:bg-emerald-700"
                    >
                      <ArrowUpRight className="h-3.5 w-3.5" />
                      <span>معاينة مباشرة</span>
                    </a>
                  </div>
                </div>
              )}
            </div>

            {/* بطاقات الإحصاء السريع */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-500 dark:text-slate-400">حالة المتجر</span>
                  <div className={`h-2.5 w-2.5 rounded-full ${savedSlug ? "bg-emerald-500 ring-4 ring-emerald-500/20" : "bg-slate-300"}`} />
                </div>
                <h4 className="mt-3 text-lg font-black text-slate-900 dark:text-white">
                  {savedSlug ? "مفتوح ويستقبل طلبات" : "مقفل حالياً"}
                </h4>
              </div>

              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-500 dark:text-slate-400">المنتجات المعروضة</span>
                  <ShoppingBag className="h-4 w-4 text-blue-500" />
                </div>
                <h4 className="mt-3 text-lg font-black text-slate-900 dark:text-white">
                  {count} صنف معروض
                </h4>
              </div>

              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-500 dark:text-slate-400">الحملات النشطة</span>
                  <Megaphone className="h-4 w-4 text-amber-500" />
                </div>
                <h4 className="mt-3 text-lg font-black text-slate-900 dark:text-white">
                  {collections.length} حملات ترويجية
                </h4>
              </div>
            </div>
          </div>
        )}

        {/* ── TAB 2: PRODUCTS & MEDIA ───────────────────────────────────── */}
        {activeTab === "products" && (
          <div className="space-y-4">
            {/* رأس التبويب وأدوات البحث والتصفية */}
            <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setNewProductForm({
                      name_ar: "",
                      name_en: "",
                      brand: "",
                      sku: "",
                      online_price: "",
                      online_description: "",
                      allow_preorder: true,
                      is_for_sale_online: true,
                    });
                    setNewProductImages([]);
                    setIsCreatingProductModal(true);
                  }}
                  className="flex items-center gap-1.5 rounded-xl bg-blue-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-sm shadow-blue-600/20 transition hover:bg-blue-700"
                >
                  <Plus className="h-4 w-4" />
                  <span>إضافة منتج جديد للمتجر</span>
                </button>

                <div className="mx-1 hidden h-4 w-px bg-slate-200 sm:block dark:bg-slate-700" />

                {SCOPES.map((sc) => (
                  <button
                    key={sc.key}
                    type="button"
                    onClick={() => setScope(sc.key)}
                    className={`rounded-xl px-3 py-1.5 text-xs font-bold transition ${
                      scope === sc.key
                        ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
                    }`}
                  >
                    {sc.label}
                  </button>
                ))}
              </div>

              <div className="relative w-full sm:w-64">
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="بحث في الأصناف…"
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 pr-8 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                />
                <Search className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
              </div>
            </div>

            {/* جدول المنتجات */}
            <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="overflow-x-auto">
                <table className="w-full text-right text-xs">
                  <thead className="border-b border-slate-200 bg-slate-50 text-[11px] font-bold text-slate-500 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-400">
                    <tr>
                      <th className="p-3.5">الصنف</th>
                      <th className="p-3.5">عرض بالمتجر</th>
                      <th className="p-3.5">سعر المتجر</th>
                      <th className="p-3.5">طلب مسبق (بدون مخزون)</th>
                      <th className="p-3.5">وصف المتجر</th>
                      <th className="p-3.5 text-center">صور المتجر</th>
                      <th className="p-3.5 text-center">إجراءات</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80">
                    {loadingProducts ? (
                      <tr>
                        <td colSpan={7} className="py-12 text-center text-slate-400">
                          <Loader2 className="mx-auto h-6 w-6 animate-spin" />
                          <span className="mt-2 block text-xs">جارٍ تحميل المنتجات…</span>
                        </td>
                      </tr>
                    ) : rows.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-12 text-center text-slate-400">
                          لا توجد أصناف مطابقة للتصفية.
                        </td>
                      </tr>
                    ) : (
                      rows.map((product) => {
                        const draft = drafts[product.id] || draftOf(product);
                        const isBusy = savingRow === product.id;
                        return (
                          <tr key={product.id} className="transition hover:bg-slate-50/70 dark:hover:bg-slate-800/40">
                            <td className="p-3.5 font-bold text-slate-900 dark:text-white">
                              <div>{storeAdminProductName(product)}</div>
                              <div className="text-[10px] font-mono text-slate-400">{product.sku || `ID: ${product.id}`}</div>
                            </td>

                            <td className="p-3.5">
                              <button
                                type="button"
                                onClick={() => togglePublish(product)}
                                disabled={isBusy}
                                className={`inline-flex items-center gap-1 rounded-xl px-2.5 py-1 text-[11px] font-bold transition ${
                                  product.is_for_sale_online
                                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300"
                                    : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400"
                                }`}
                              >
                                {product.is_for_sale_online ? "معروض" : "مخفي"}
                              </button>
                            </td>

                            <td className="p-3.5">
                              <input
                                type="text"
                                value={draft.online_price}
                                onChange={(e) =>
                                  setDrafts((prev) => ({
                                    ...prev,
                                    [product.id]: { ...draft, online_price: e.target.value },
                                  }))
                                }
                                placeholder={product.sale_price ? `الافتراضي (${product.sale_price})` : "سعر خاص"}
                                className="w-28 rounded-xl border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              />
                            </td>

                            <td className="p-3.5">
                              <button
                                type="button"
                                onClick={() => togglePreorder(product)}
                                disabled={isBusy}
                                className={`inline-flex items-center gap-1 rounded-xl px-2.5 py-1 text-[11px] font-bold transition ${
                                  product.allow_preorder
                                    ? "bg-indigo-50 text-indigo-700 border border-indigo-200 dark:bg-indigo-950/60 dark:text-indigo-300"
                                    : "bg-slate-100 text-slate-400 hover:text-slate-600 dark:bg-slate-800"
                                }`}
                                title="يتيح بيع المنتج واستقبال الطلبات حتى لو كان الرصيد المخزني صفراً"
                              >
                                {product.allow_preorder ? "مفعّل (عند الطلب)" : "معطل"}
                              </button>
                            </td>

                            <td className="p-3.5">
                              <input
                                type="text"
                                value={draft.online_description}
                                onChange={(e) =>
                                  setDrafts((prev) => ({
                                    ...prev,
                                    [product.id]: { ...draft, online_description: e.target.value },
                                  }))
                                }
                                placeholder="وصف مخصص للمتجر…"
                                className="w-48 rounded-xl border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              />
                            </td>

                            <td className="p-3.5 text-center">
                              <button
                                type="button"
                                onClick={() => openMediaModal(product)}
                                className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                              >
                                <ImageIcon className="h-3.5 w-3.5 text-blue-500" />
                                <span>إدارة الصور</span>
                              </button>
                            </td>

                            <td className="p-3.5 text-center">
                              <div className="flex items-center justify-center gap-1">
                                <button
                                  type="button"
                                  onClick={() => saveProductRow(product)}
                                  disabled={isBusy}
                                  className="rounded-xl bg-slate-900 px-3 py-1 text-xs font-bold text-white transition hover:bg-blue-600 disabled:opacity-50 dark:bg-slate-700 dark:hover:bg-blue-600"
                                >
                                  {isBusy ? "…" : "حفظ"}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleDeleteStoreProduct(product)}
                                  className="rounded-xl p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/50"
                                  title="حذف من المتجر"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ── TAB 3: CAMPAIGNS & COLLECTIONS ────────────────────────────── */}
        {activeTab === "campaigns" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-black text-slate-900 dark:text-white">
                  الحملات الإعلانية وروابط التواصل الاجتماعي
                </h3>
                <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  أنشئ صفحات هبوط مخصصة لحملات TikTok و Meta بمنتج مميز أو باقة عروض ورابط مباشر
                </p>
              </div>

              <button
                type="button"
                onClick={() => {
                  setCollectionForm({
                    title: "",
                    slug: "",
                    description: "",
                    banner_image_url: "",
                    badge_text: "خصم خاص",
                    is_active: true,
                  });
                  setIsEditingCollectionModal(true);
                }}
                className="flex items-center gap-1.5 rounded-2xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white shadow-md shadow-blue-600/20 transition hover:bg-blue-700"
              >
                <Plus className="h-4 w-4" />
                <span>إنشاء حملة جديدة</span>
              </button>
            </div>

            {/* قائمة الحملات */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {collections.map((col) => {
                const campaignUrl = `${window.location.origin}/store/${encodeURIComponent(savedSlug)}/c/${encodeURIComponent(col.slug)}`;
                return (
                  <div
                    key={col.id}
                    className="flex flex-col justify-between rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-2">
                        {col.badge_text ? (
                          <span className="flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                            <Flame className="h-3 w-3 fill-current" />
                            {col.badge_text}
                          </span>
                        ) : <div />}

                        <span className={`h-2 w-2 rounded-full ${col.is_active ? "bg-emerald-500" : "bg-slate-300"}`} />
                      </div>

                      <h4 className="mt-2 text-base font-black text-slate-900 dark:text-white">
                        {col.title}
                      </h4>
                      <p className="font-mono text-[11px] text-slate-400">/c/{col.slug}</p>

                      {col.description && (
                        <p className="mt-2 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">
                          {col.description}
                        </p>
                      )}

                      <div className="mt-4 flex items-center gap-2 text-xs font-bold text-slate-600 dark:text-slate-300">
                        <Tag className="h-3.5 w-3.5 text-blue-500" />
                        <span>{col.items_count || 0} منتجات بالحملة</span>
                      </div>
                    </div>

                    <div className="mt-6 flex flex-col gap-2 border-t border-slate-100 pt-4 dark:border-slate-800">
                      <div className="flex items-center justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            navigator.clipboard.writeText(campaignUrl);
                            toast("تم نسخ رابط الحملة الإعلانية لنشره على السوشيال ميديا", "success");
                          }}
                          className="flex flex-1 items-center justify-center gap-1 rounded-xl border border-slate-200 bg-slate-50 py-2 text-xs font-bold text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                        >
                          <Share2 className="h-3.5 w-3.5" />
                          <span>نسخ رابط الإعلان</span>
                        </button>

                        <a
                          href={campaignUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center justify-center rounded-xl bg-blue-50 p-2 text-blue-600 hover:bg-blue-100 dark:bg-blue-950 dark:text-blue-400"
                          title="معاينة صفحة الإعلان"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </div>

                      <div className="flex items-center justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => openCollectionDetail(col)}
                          className="flex-1 rounded-xl bg-slate-900 py-1.5 text-xs font-bold text-white transition hover:bg-blue-600 dark:bg-slate-800"
                        >
                          إدارة منتجات الحملة
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            setCollectionForm(col);
                            setIsEditingCollectionModal(true);
                          }}
                          className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300"
                        >
                          تعديل
                        </button>

                        <button
                          type="button"
                          onClick={() => handleDeleteCollection(col)}
                          className="rounded-xl border border-rose-200 p-1.5 text-rose-600 hover:bg-rose-50 dark:border-rose-900 dark:text-rose-400"
                          title="حذف الحملة"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── TAB 4: THEME & BRANDING ────────────────────────────────────── */}
        {activeTab === "theme" && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              {/* قسم الهوية والترويسات */}
              <div className="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <h3 className="text-base font-black text-slate-900 dark:text-white">
                  عناوين المتجر والشريط الترويجي
                </h3>

                <div className="space-y-3">
                  <div>
                    <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                      عنوان المتجر الرئيسي (Hero Title)
                    </label>
                    <input
                      type="text"
                      value={themeSettings.hero_title || ""}
                      onChange={(e) => setThemeSettings((prev) => ({ ...prev, hero_title: e.target.value }))}
                      placeholder="مثال: أحدث تشكيلة أزياء لعام 2026"
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                      الوصف الترحيبي الفرعي (Hero Subtitle)
                    </label>
                    <textarea
                      rows={2}
                      value={themeSettings.hero_subtitle || ""}
                      onChange={(e) => setThemeSettings((prev) => ({ ...prev, hero_subtitle: e.target.value }))}
                      placeholder="مثال: تسوق أفضل الموديلات بجودة عالية مع توصيل لكافة المناطق"
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    />
                  </div>

                  <div className="rounded-2xl border border-slate-100 bg-slate-50/50 p-4 dark:border-slate-800 dark:bg-slate-800/40">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                        تفعيل شريط الإعلانات أعلى الصفحة
                      </span>
                      <input
                        type="checkbox"
                        checked={themeSettings.show_announcement}
                        onChange={(e) =>
                          setThemeSettings((prev) => ({ ...prev, show_announcement: e.target.checked }))
                        }
                        className="h-4 w-4 rounded accent-blue-600"
                      />
                    </div>
                    {themeSettings.show_announcement && (
                      <input
                        type="text"
                        value={themeSettings.announcement_bar || ""}
                        onChange={(e) =>
                          setThemeSettings((prev) => ({ ...prev, announcement_bar: e.target.value }))
                        }
                        placeholder="مثال: 🔥 عروض نهاية الأسبوع — خصم 20% على كافة المنتجات!"
                        className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      />
                    )}
                  </div>
                </div>
              </div>

              {/* قسم الخلفية والبانر */}
              <div className="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <h3 className="text-base font-black text-slate-900 dark:text-white">
                  صورة الخلفية والبانر الترويجي
                </h3>

                <div className="space-y-4">
                  {/* بانر المتجر */}
                  <div>
                    <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                      صورة البانر العلوي (Banner Image)
                    </label>
                    <div className="flex items-center gap-3">
                      {themeSettings.banner_image_url ? (
                        <img
                          src={themeSettings.banner_image_url}
                          alt="Banner"
                          className="h-16 w-32 rounded-xl object-cover border border-slate-200 dark:border-slate-700"
                        />
                      ) : (
                        <div className="flex h-16 w-32 items-center justify-center rounded-xl bg-slate-100 text-xs text-slate-400 dark:bg-slate-800">
                          بلا بانر
                        </div>
                      )}
                      <label className="flex cursor-pointer items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200">
                        <Upload className="h-4 w-4" />
                        <span>رفع بانر جديد</span>
                        <input
                          type="file"
                          accept="image/*"
                          className="hidden"
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (f) handleUploadThemeImage("banner_image_url", f);
                          }}
                        />
                      </label>
                    </div>
                  </div>

                  {/* صورة الخلفية */}
                  <div>
                    <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                      صورة خلفية المتجر (Background Image)
                    </label>
                    <div className="flex items-center gap-3">
                      {themeSettings.background_image_url ? (
                        <img
                          src={themeSettings.background_image_url}
                          alt="BG"
                          className="h-16 w-20 rounded-xl object-cover border border-slate-200 dark:border-slate-700"
                        />
                      ) : (
                        <div className="flex h-16 w-20 items-center justify-center rounded-xl bg-slate-100 text-xs text-slate-400 dark:bg-slate-800">
                          بلا خلفية
                        </div>
                      )}
                      <label className="flex cursor-pointer items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200">
                        <Upload className="h-4 w-4" />
                        <span>رفع صورة خلفية</span>
                        <input
                          type="file"
                          accept="image/*"
                          className="hidden"
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (f) handleUploadThemeImage("background_image_url", f);
                          }}
                        />
                      </label>
                    </div>

                    {themeSettings.background_image_url && (
                      <div className="mt-2 flex items-center gap-2">
                        <span className="text-[11px] font-bold text-slate-500">طريقة العرض:</span>
                        <select
                          value={themeSettings.background_style || "cover"}
                          onChange={(e) =>
                            setThemeSettings((prev) => ({ ...prev, background_style: e.target.value }))
                          }
                          className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                        >
                          <option value="cover">تغطية كاملة (Cover)</option>
                          <option value="repeat_pattern">نقش مكرر (Pattern)</option>
                        </select>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* قسم وسائل التواصل والواتساب */}
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <h3 className="text-base font-black text-slate-900 dark:text-white">
                روابط التواصل الاجتماعي وواتساب الطلبات
              </h3>

              <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    رابط Instagram
                  </label>
                  <input
                    type="url"
                    value={themeSettings.instagram_url || ""}
                    onChange={(e) => setThemeSettings((prev) => ({ ...prev, instagram_url: e.target.value }))}
                    placeholder="https://instagram.com/..."
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    رابط TikTok
                  </label>
                  <input
                    type="url"
                    value={themeSettings.tiktok_url || ""}
                    onChange={(e) => setThemeSettings((prev) => ({ ...prev, tiktok_url: e.target.value }))}
                    placeholder="https://tiktok.com/@..."
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    رابط Facebook
                  </label>
                  <input
                    type="url"
                    value={themeSettings.facebook_url || ""}
                    onChange={(e) => setThemeSettings((prev) => ({ ...prev, facebook_url: e.target.value }))}
                    placeholder="https://facebook.com/..."
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    رابط Snapchat
                  </label>
                  <input
                    type="url"
                    value={themeSettings.snapchat_url || ""}
                    onChange={(e) => setThemeSettings((prev) => ({ ...prev, snapchat_url: e.target.value }))}
                    placeholder="https://snapchat.com/add/..."
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>
              </div>
            </div>

            {/* زر الحفظ العائم */}
            <div className="flex justify-end pt-4">
              <button
                type="button"
                onClick={handleSaveThemeSettings}
                disabled={savingTheme}
                className="flex items-center gap-2 rounded-2xl bg-blue-600 px-8 py-3.5 text-xs font-bold text-white shadow-lg shadow-blue-600/30 transition hover:bg-blue-700 active:scale-95 disabled:opacity-50"
              >
                {savingTheme ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                <span>حفظ كافة تخصيصات المظهر</span>
              </button>
            </div>
          </div>
        )}

        {/* ── MODAL: إدارة صور المتجر المخصصة للصنف ──────────────────────── */}
        {selectedProductForMedia && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
            <div className="w-full max-w-2xl rounded-3xl bg-white p-6 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4 dark:border-slate-800">
                <div>
                  <h3 className="text-base font-black text-slate-900 dark:text-white">
                    صور المتجر المخصصة: {storeAdminProductName(selectedProductForMedia)}
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    هذه الصور ستظهر لزبائن المتجر بدقة وتنسيق احترافي
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedProductForMedia(null)}
                  className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* معرض الصور الحالي */}
              <div className="my-6">
                {loadingMedia ? (
                  <div className="py-12 text-center text-slate-400">
                    <Loader2 className="mx-auto h-6 w-6 animate-spin" />
                    <span className="mt-2 block text-xs">جارٍ جلب الصور…</span>
                  </div>
                ) : customImages.length === 0 ? (
                  <div className="rounded-2xl border-2 border-dashed border-slate-200 p-8 text-center dark:border-slate-800">
                    <ImageIcon className="mx-auto h-12 w-12 text-slate-300 dark:text-slate-700" />
                    <p className="mt-2 text-xs font-bold text-slate-600 dark:text-slate-300">
                      لم ترفع صوراً مخصصة لهذا المنتج بعد
                    </p>
                    <p className="text-[11px] text-slate-400">
                      يعرض المتجر حالياً صور النظام الافتراضية إن وُجدت
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                    {customImages.map((img) => (
                      <div
                        key={img.id}
                        className="group relative overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-800 dark:bg-slate-800"
                      >
                        <div className="relative aspect-square w-full overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-900">
                          <img
                            src={img.image_url}
                            alt=""
                            className="h-full w-full object-cover"
                          />
                          {/* شريط الإعلان المخصص */}
                          {img.overlay_text ? (
                            <StoreImageOverlay
                              overlay={{
                                text: img.overlay_text,
                                style: img.overlay_style,
                                color: img.overlay_color,
                              }}
                            />
                          ) : img.is_cover ? (
                            <span className="absolute top-2 right-2 rounded-lg bg-blue-600 px-2 py-0.5 text-[10px] font-bold text-white shadow">
                              صورة الغلاف
                            </span>
                          ) : null}
                        </div>

                        <div className="mt-2 flex items-center justify-between gap-1 px-1">
                          <button
                            type="button"
                            onClick={() => handleOpenOverlayModal(img)}
                            className="flex items-center gap-1 rounded-lg bg-amber-500/10 px-2 py-1 text-[10px] font-bold text-amber-700 hover:bg-amber-500/20 dark:bg-amber-500/20 dark:text-amber-300"
                            title="تخصيص نص إعلاني على الصورة"
                          >
                            <Sparkles className="h-3 w-3 shrink-0" />
                            <span className="truncate">{img.overlay_text ? "تعديل الإعلان" : "نص إعلاني"}</span>
                          </button>

                          <div className="flex items-center gap-1.5 shrink-0">
                            {!img.is_cover && (
                              <button
                                type="button"
                                onClick={() => handleSetCoverImage(img)}
                                className="text-[10px] font-bold text-blue-600 hover:underline dark:text-blue-400"
                              >
                                غلاف
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => handleDeleteCustomImage(img)}
                              className="text-rose-500 hover:text-rose-700"
                              title="حذف الصورة"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* شريط الرفع */}
              <div className="flex items-center justify-between border-t border-slate-100 pt-4 dark:border-slate-800">
                <label className="flex cursor-pointer items-center gap-2 rounded-2xl bg-blue-600 px-5 py-2.5 text-xs font-bold text-white shadow-md shadow-blue-600/20 transition hover:bg-blue-700">
                  {uploadingMedia ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
                  <span>{uploadingMedia ? "جارٍ الرفع والمعالجة…" : "رفع صورة جديدة للمتجر"}</span>
                  <input
                    type="file"
                    accept="image/*"
                    disabled={uploadingMedia}
                    onChange={handleUploadCustomImage}
                    className="hidden"
                  />
                </label>

                <button
                  type="button"
                  onClick={() => setSelectedProductForMedia(null)}
                  className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300"
                >
                  إغلاق
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── MODAL: محرر النص والشريط الإعلاني فوق الصورة ────────────────── */}
        {editingOverlayImage && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4 backdrop-blur-md">
            <div className="w-full max-w-3xl rounded-3xl bg-white p-6 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800 max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4 dark:border-slate-800">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-tr from-amber-500 to-rose-500 text-white shadow-lg shadow-rose-500/20">
                    <Sparkles className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-black text-slate-900 dark:text-white">
                      تخصيص نص إعلاني وبادج مائل فوق الصورة
                    </h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      اكتب نص العرض الترويجي واختر النمط واللون مع المعاينة والتنزيل الفوري
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setEditingOverlayImage(null)}
                  className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-12">
                {/* عمود المعاينة الحية */}
                <div className="md:col-span-5 flex flex-col items-center">
                  <div className="relative aspect-square w-full max-w-[280px] overflow-hidden rounded-3xl border-2 border-slate-200 bg-slate-100 shadow-xl dark:border-slate-800 dark:bg-slate-800">
                    <img
                      src={editingOverlayImage.image_url}
                      alt="معاينة"
                      className="h-full w-full object-cover"
                    />
                    <StoreImageOverlay
                      overlay={{
                        text: overlayForm.text || "عرض خاص لأسبوع",
                        style: overlayForm.style,
                        color: overlayForm.colorKey,
                      }}
                    />
                  </div>
                  <span className="mt-3 text-center text-xs font-bold text-slate-400">
                    معاينة حية ومباشرة فوق الصورة
                  </span>

                  {/* زر تنزيل صورة الإعلان الفوري */}
                  <button
                    type="button"
                    onClick={handleDownloadAdCreative}
                    disabled={downloadingAd}
                    className="mt-4 flex w-full max-w-[280px] items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-purple-600 to-indigo-600 px-4 py-2.5 text-xs font-black text-white shadow-lg shadow-purple-600/25 transition hover:from-purple-700 hover:to-indigo-700 active:scale-95 disabled:opacity-50"
                  >
                    {downloadingAd ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4" />
                    )}
                    <span>تحميل صورة الإعلان (Instagram/TikTok)</span>
                  </button>
                </div>

                {/* عمود خيارات النص والتصميم */}
                <div className="md:col-span-7 space-y-4">
                  {/* إدخال النص */}
                  <div>
                    <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                      النص المكتوب على الصورة
                    </label>
                    <input
                      type="text"
                      value={overlayForm.text}
                      onChange={(e) =>
                        setOverlayForm((prev) => ({ ...prev, text: e.target.value }))
                      }
                      placeholder="مثال: 🔥 عرض خاص لأسبوع — السعر 100 ₪"
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs font-bold focus:border-blue-500 focus:bg-white focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    />

                    {/* مقترحات سريعة */}
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {[
                        "🔥 عرض خاص لأسبوع",
                        "💥 خصم 30% لفترة محدودة",
                        "🚚 توصيل مجاني وسريع",
                        "⭐ الأكثر مبيعاً",
                        "⚡ تصفية شاملة",
                      ].map((preset) => (
                        <button
                          key={preset}
                          type="button"
                          onClick={() =>
                            setOverlayForm((prev) => ({ ...prev, text: preset }))
                          }
                          className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[10px] font-bold text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                        >
                          {preset}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* نمط الشريط وموضعه */}
                  <div>
                    <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                      نمط وموضع الشريط الإعلاني
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      {OVERLAY_STYLE_PRESETS.map((st) => (
                        <button
                          key={st.key}
                          type="button"
                          onClick={() =>
                            setOverlayForm((prev) => ({ ...prev, style: st.key }))
                          }
                          className={`rounded-xl border p-2.5 text-right text-xs font-bold transition ${
                            overlayForm.style === st.key
                              ? "border-blue-500 bg-blue-50/50 text-blue-700 shadow-sm dark:bg-blue-900/30 dark:text-blue-300"
                              : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                          }`}
                        >
                          {st.name}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* سمة اللون */}
                  <div>
                    <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                      لون وسمة الشريط
                    </label>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                      {OVERLAY_COLOR_PRESETS.map((col) => (
                        <button
                          key={col.key}
                          type="button"
                          onClick={() =>
                            setOverlayForm((prev) => ({ ...prev, colorKey: col.key }))
                          }
                          className={`flex items-center gap-2 rounded-xl border p-2 text-right text-xs font-bold transition ${
                            overlayForm.colorKey === col.key
                              ? "border-blue-500 bg-blue-50/50 text-blue-700 shadow-sm dark:bg-blue-900/30 dark:text-blue-300"
                              : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                          }`}
                        >
                          <span
                            className="h-4 w-4 shrink-0 rounded-full border border-black/10 shadow"
                            style={{ backgroundColor: col.canvasBg }}
                          />
                          <span className="truncate text-[11px]">{col.name.split(" ")[0]}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* أزرار الإجراءات */}
              <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => {
                    setOverlayForm({ text: "", style: "diagonal_ribbon", colorKey: "red_fire" });
                  }}
                  className="text-xs font-bold text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                >
                  مسح النص الإعلاني
                </button>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setEditingOverlayImage(null)}
                    className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300"
                  >
                    إلغاء
                  </button>
                  <button
                    type="button"
                    onClick={handleSaveImageOverlay}
                    disabled={savingOverlay}
                    className="flex items-center gap-2 rounded-2xl bg-blue-600 px-6 py-2 text-xs font-black text-white shadow-lg shadow-blue-600/30 transition hover:bg-blue-700 active:scale-95 disabled:opacity-50"
                  >
                    {savingOverlay ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Check className="h-4 w-4" />
                    )}
                    <span>حفظ النص على الصورة للمتجر</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── MODAL: إنشاء / تعديل حملة إعلانية ─────────────────────────── */}
        {isEditingCollectionModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
            <div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4 dark:border-slate-800">
                <h3 className="text-base font-black text-slate-900 dark:text-white">
                  {collectionForm.id ? "تعديل الحملة الإعلانية" : "إنشاء حملة إعلانية جديدة"}
                </h3>
                <button
                  type="button"
                  onClick={() => setIsEditingCollectionModal(false)}
                  className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="my-4 space-y-3">
                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    عنوان الحملة / المجموعة <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={collectionForm.title || ""}
                    onChange={(e) => {
                      const t = e.target.value;
                      setCollectionForm((prev) => ({
                        ...prev,
                        title: t,
                        slug: prev.slug || t.toLowerCase().replace(/[\s_]+/g, "-"),
                      }));
                    }}
                    placeholder="مثال: عروض العيد الحصرية"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    معرف الرابط (Slug) <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={collectionForm.slug || ""}
                    onChange={(e) =>
                      setCollectionForm((prev) => ({
                        ...prev,
                        slug: e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""),
                      }))
                    }
                    placeholder="eid-offers"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-mono focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    dir="ltr"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    نص البادج الترويجي (Badge)
                  </label>
                  <input
                    type="text"
                    value={collectionForm.badge_text || ""}
                    onChange={(e) =>
                      setCollectionForm((prev) => ({ ...prev, badge_text: e.target.value }))
                    }
                    placeholder="مثال: خصم 20% / إعلان ممول"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    وصف الحملة
                  </label>
                  <textarea
                    rows={2}
                    value={collectionForm.description || ""}
                    onChange={(e) =>
                      setCollectionForm((prev) => ({ ...prev, description: e.target.value }))
                    }
                    placeholder="شرح موجز عن العرض لرواد مواقع التواصل…"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>

                <div className="flex items-center justify-between rounded-xl bg-slate-50 p-3 dark:bg-slate-800">
                  <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
                    الحملة مفعّلة ونشطة
                  </span>
                  <input
                    type="checkbox"
                    checked={collectionForm.is_active}
                    onChange={(e) =>
                      setCollectionForm((prev) => ({ ...prev, is_active: e.target.checked }))
                    }
                    className="h-4 w-4 rounded accent-blue-600"
                  />
                </div>
              </div>

              <div className="mt-6 flex justify-end gap-2 border-t border-slate-100 pt-4 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsEditingCollectionModal(false)}
                  className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300"
                >
                  إلغاء
                </button>
                <button
                  type="button"
                  onClick={handleSaveCollectionForm}
                  className="rounded-xl bg-blue-600 px-6 py-2 text-xs font-bold text-white shadow-md shadow-blue-600/20 hover:bg-blue-700"
                >
                  حفظ الحملة
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── MODAL: إدارة منتجات الحملة المحددة ──────────────────────────── */}
        {selectedCollection && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
            <div className="w-full max-w-2xl rounded-3xl bg-white p-6 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800 max-h-[90vh] flex flex-col">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4 dark:border-slate-800">
                <div>
                  <h3 className="text-base font-black text-slate-900 dark:text-white">
                    منتجات حملة: {selectedCollection.title}
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    أضف المنتجات التي ستظهر حصراً في صفحة هبوط هذا الإعلان
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedCollection(null)}
                  className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* إضافة صنف للحملة */}
              <div className="my-4 flex gap-2">
                <select
                  id="add-prod-select"
                  className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                >
                  <option value="">اختر صنفاً لإضافته للحملة…</option>
                  {rows
                    .filter((r) => !collectionItems.some((item) => item.product === r.id))
                    .map((r) => (
                      <option key={r.id} value={r.id}>
                        {storeAdminProductName(r)} ({r.sku || `ID: ${r.id}`})
                      </option>
                    ))}
                </select>
                <button
                  type="button"
                  onClick={() => {
                    const sel = document.getElementById("add-prod-select") as HTMLSelectElement;
                    if (sel?.value) handleAddItemToCollection(Number(sel.value));
                  }}
                  className="rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold text-white hover:bg-blue-700"
                >
                  إضافة للحملة
                </button>
              </div>

              {/* قائمة العناصر */}
              <div className="flex-1 overflow-y-auto space-y-2 py-2">
                {loadingItems ? (
                  <div className="py-8 text-center text-slate-400">
                    <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                  </div>
                ) : collectionItems.length === 0 ? (
                  <p className="py-8 text-center text-xs text-slate-400">
                    لم تضف منتجات لهذه الحملة بعد.
                  </p>
                ) : (
                  collectionItems.map((item) => (
                    <div
                      key={item.id}
                      className="flex items-center justify-between rounded-2xl border border-slate-100 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-800/50"
                    >
                      <div className="flex items-center gap-3">
                        {item.image_url ? (
                          <img
                            src={item.image_url}
                            alt=""
                            className="h-10 w-10 rounded-xl object-cover"
                          />
                        ) : (
                          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-200 text-xs text-slate-400 dark:bg-slate-700">
                            -
                          </div>
                        )}
                        <div>
                          <h4 className="text-xs font-bold text-slate-900 dark:text-white">
                            {item.product_name}
                          </h4>
                          <span className="text-[10px] text-slate-400 font-mono">
                            {item.sku || `ID: ${item.product}`}
                          </span>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleDeleteCollectionItem(item.id)}
                        className="rounded-lg p-1.5 text-slate-400 hover:text-rose-600"
                        title="إزالة من الحملة"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))
                )}
              </div>

              <div className="mt-4 flex justify-end border-t border-slate-100 pt-4 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setSelectedCollection(null)}
                  className="rounded-xl bg-slate-900 px-6 py-2 text-xs font-bold text-white dark:bg-slate-700"
                >
                  تم
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── MODAL: إضافة منتج جديد للمتجر مباشرة ────────────────────── */}
        {isCreatingProductModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
            <div className="flex max-h-[90vh] w-full max-w-xl flex-col rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4 dark:border-slate-800">
                <div>
                  <h3 className="text-base font-black text-slate-900 dark:text-white">
                    إضافة منتج جديد للمتجر مباشرة
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    أضف منتجاً أو خدمة أو عرضاً خاصاً للمتجر دون الحاجة لربطه بالمخزن أو شجرة الأصناف
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setIsCreatingProductModal(false)}
                  className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="my-4 flex-1 space-y-4 overflow-y-auto pr-1">
                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    اسم المنتج في المتجر <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={newProductForm.name_ar}
                    onChange={(e) =>
                      setNewProductForm((prev) => ({ ...prev, name_ar: e.target.value }))
                    }
                    placeholder="مثال: ثلاجة دولابي فاخرة LG 18 قدم"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                      الاسم بالإنجليزية (اختياري)
                    </label>
                    <input
                      type="text"
                      value={newProductForm.name_en}
                      onChange={(e) =>
                        setNewProductForm((prev) => ({ ...prev, name_en: e.target.value }))
                      }
                      placeholder="LG Refrigerator 18 Cu Ft"
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      dir="ltr"
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                      الماركة / البراند (Brand)
                    </label>
                    <input
                      type="text"
                      value={newProductForm.brand}
                      onChange={(e) =>
                        setNewProductForm((prev) => ({ ...prev, brand: e.target.value }))
                      }
                      placeholder="مثال: LG / Samsung"
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                      سعر البيع بالمتجر
                    </label>
                    <input
                      type="number"
                      step="any"
                      value={newProductForm.online_price}
                      onChange={(e) =>
                        setNewProductForm((prev) => ({ ...prev, online_price: e.target.value }))
                      }
                      placeholder="مثال: 3500"
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                      رمز المنتج SKU (يولّد تلقائياً إن تُرك فارغاً)
                    </label>
                    <input
                      type="text"
                      value={newProductForm.sku}
                      onChange={(e) =>
                        setNewProductForm((prev) => ({ ...prev, sku: e.target.value }))
                      }
                      placeholder="ST-XXXX"
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-mono focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      dir="ltr"
                    />
                  </div>
                </div>

                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    وصف ومواصفات المنتج للمتجر
                  </label>
                  <textarea
                    rows={3}
                    value={newProductForm.online_description}
                    onChange={(e) =>
                      setNewProductForm((prev) => ({ ...prev, online_description: e.target.value }))
                    }
                    placeholder="شرح موجز عن المنتج والمواصفات التي يراها الزبائن…"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>

                {/* خيارات الطلب المسبق والنشر */}
                <div className="space-y-2 rounded-2xl border border-slate-100 bg-slate-50/70 p-3.5 dark:border-slate-800 dark:bg-slate-800/40">
                  <label className="flex cursor-pointer items-center justify-between">
                    <div>
                      <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                        إتاحة البيع بالطلب المسبق / عند الطلب
                      </span>
                      <p className="text-[10px] text-slate-400">
                        يتيح للزبائن طلب المنتج عبر السلة والواتساب حتى بدون توفر رصيد مخزني حالي
                      </p>
                    </div>
                    <input
                      type="checkbox"
                      checked={newProductForm.allow_preorder}
                      onChange={(e) =>
                        setNewProductForm((prev) => ({ ...prev, allow_preorder: e.target.checked }))
                      }
                      className="h-4 w-4 rounded accent-blue-600"
                    />
                  </label>

                  <label className="flex cursor-pointer items-center justify-between border-t border-slate-200/60 pt-2 dark:border-slate-700/60">
                    <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                      نشر وعرض المنتج فورياً في المتجر
                    </span>
                    <input
                      type="checkbox"
                      checked={newProductForm.is_for_sale_online}
                      onChange={(e) =>
                        setNewProductForm((prev) => ({ ...prev, is_for_sale_online: e.target.checked }))
                      }
                      className="h-4 w-4 rounded accent-blue-600"
                    />
                  </label>
                </div>

                {/* قسم رفع الصور للمنتج الجديد */}
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
                      صور المنتج في المتجر ({newProductImages.length})
                    </label>
                    <label className="flex cursor-pointer items-center gap-1 rounded-xl bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300">
                      {uploadingNewProductImage ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <ImagePlus className="h-3.5 w-3.5 text-blue-500" />
                      )}
                      <span>{uploadingNewProductImage ? "جارٍ الرفع…" : "رفع صورة"}</span>
                      <input
                        type="file"
                        accept="image/*"
                        disabled={uploadingNewProductImage}
                        onChange={handleUploadNewProductImage}
                        className="hidden"
                      />
                    </label>
                  </div>

                  {newProductImages.length > 0 && (
                    <div className="grid grid-cols-3 gap-2">
                      {newProductImages.map((imgUrl, idx) => (
                        <div
                          key={idx}
                          className="group relative overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800"
                        >
                          <img
                            src={imgUrl}
                            alt=""
                            className="aspect-square w-full object-cover"
                          />
                          {idx === 0 && (
                            <span className="absolute top-1 right-1 rounded bg-blue-600 px-1.5 py-0.5 text-[9px] font-bold text-white shadow">
                              الغلاف
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={() =>
                              setNewProductImages((prev) => prev.filter((_, i) => i !== idx))
                            }
                            className="absolute bottom-1 left-1 rounded bg-rose-600 p-1 text-white opacity-90 transition hover:opacity-100"
                            title="حذف الصورة"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-2 flex justify-end gap-2 border-t border-slate-100 pt-4 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsCreatingProductModal(false)}
                  disabled={creatingProduct}
                  className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300"
                >
                  إلغاء
                </button>
                <button
                  type="button"
                  onClick={handleCreateStoreProduct}
                  disabled={creatingProduct}
                  className="flex items-center gap-2 rounded-xl bg-blue-600 px-6 py-2 text-xs font-bold text-white shadow-md shadow-blue-600/20 hover:bg-blue-700 disabled:opacity-50"
                >
                  {creatingProduct && <Loader2 className="h-4 w-4 animate-spin" />}
                  <span>{creatingProduct ? "جارٍ الإضافة…" : "إضافة المنتج للمتجر"}</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </KitDocumentShell>
  );
};

export default StoreSettingsPage;

