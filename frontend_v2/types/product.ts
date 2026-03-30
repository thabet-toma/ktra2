
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
    quantity?: number;
    notes?: string;
    hsCodePrimary?: string;
    hsCodeAlternative?: string;
    createdAt: string;
    updatedAt: string;
    isActive?: boolean;
    storeName?: string;
    storeDescription?: string;
    salePrice?: number;
}

export interface GeminiAnalysis {
    mainSearchTerm: string;
    keywords: string[];
    recommendedPriceRange: string;
    marketAnalysis: string;
    products: Product[];
}
