
export interface Product {
    name: string;
    price: number;
    imageUrl: string;
    store: string;
    similarity: number;
    url: string;
    description?: string;
}

export interface SearchQuery {
    image: File;
    description: string;
    targetPrice: number;
}

export interface Category {
    id: string;
    name: string;
    createdAt?: string;
}

export interface Brand {
    id: string;
    name: string;
    createdAt?: string;
}

export interface SubCategory {
    id: string;
    name: string;
    categoryId: string;
    createdAt?: string;
}

export interface Item {
    id: string;
    name: string;
    modelNumber?: string;
    categoryId: string;
    categoryName: string;
    subCategoryId?: string;
    subCategoryName?: string;
    brandId?: string;
    brandName?: string;
    specifications: string;
    imageUrls: string[];
    /** #147 M2: صورة البراند المرجعية الواحدة (`Product.image_url`) — يراها
     *  المورّد على رابط طلب عرض السعر العام؛ منفصلة عن `imageUrls` (مرفقات
     *  الداتا شيت). */
    imageUrl?: string;
    quantity?: number;
    notes?: string;
    hsCodePrimary?: string;
    hsCodeAlternative?: string;
    /**
     * T-SUPSKU: أرقام كتالوج الموردين لهذا المنتج، مفصولةً بمسافات.
     *
     * نصٌّ واحد لا مصفوفة: المنتقي يطابق ولا يعرض كلَّ رقمٍ على حدة، والحمولة
     * تُقاس على كتالوج كامل يُجلب دفعةً واحدة.
     */
    supplierCodes?: string;
    createdAt: string;
    updatedAt: string;
    isActive?: boolean;
    storeName?: string;
    storeDescription?: string;
    salePrice?: number;
    /** T-SERIAL: باركود المنتج — مصدر البحث السريع بالماسح في مستندات الشراء. */
    barcode?: string;
    /** T-SERIAL: المنتج يتتبّع وحداته برقم تسلسلي (`Product.is_serialized`). */
    isSerialized?: boolean;
    /** #22: «المنتج» (الأب) الذي يتبعه هذا البراند — من `family_id`/`family_name`
     *  في عقد `view=lookup`. الأب نفسه لا يظهر أبداً كبندٍ قابلٍ للإدراج. */
    familyId?: string;
    familyName?: string;
    /** ISSUE #133: حالة المخزون (نفذ/منخفض) كما يحسمها الخادم
     *  (`inventory/stock_status.py`) — تصل جاهزة ضمن عقد `view=lookup`، لا
     *  تُعاد حسابها هنا. تغذّي شارة المنتقي (`utils/stockBadge`). */
    stock_status?: string | null;
    /** ISSUE #133: خدمة لا بضاعة — بلا مخزون، فبلا شارة ولا حجز يُحسب لها. */
    is_service?: boolean | null;
    /** ISSUE #133: المتاح بعد خصم المحجوز كما يرسله عقد المنتقي بجانب الرصيد. */
    available_quantity?: string | number | null;
    /** ISSUE #133: الرصيد الفعلي (لا `quantity` أعلاه — ذاك الحدّ الأدنى
     *  `min_stock_level` لنموذج تحرير الصنف). يغذّي «الرصيد: X» في شارة
     *  المنتقي والحساب المحلي للمتاح بعد الحجز (`utils/reservedStock`). */
    quantity_on_hand?: string | number | null;
}

export interface GeminiAnalysis {
    mainSearchTerm: string;
    keywords: string[];
    recommendedPriceRange: string;
    marketAnalysis: string;
    products: Product[];
}
