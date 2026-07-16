
import { Product, SearchQuery } from '../types';

function mockProducts(query: SearchQuery): Product[] {
  const base = query.description?.slice(0, 40) || "منتج";
  const price = Number(query.targetPrice) || 25;
  return [
    {
      name: `${base} — عرض تجريبي`,
      price: price * 0.9,
      imageUrl: "https://placehold.co/400x400/e2e8f0/1e293b?text=Demo",
      store: "مورد تجريبي",
      similarity: 88,
      url: `https://www.alibaba.com/trade/search?SearchText=${encodeURIComponent(base)}`,
      description: "نتيجة توضيحية؛ البحث الذكي يحتاج تكاملاً آمناً من الخادم.",
    },
    {
      name: `${base} — بديل 2`,
      price: price * 1.05,
      imageUrl: "https://placehold.co/400x400/f1f5f9/475569?text=Demo+2",
      store: "عرض توضيحي",
      similarity: 72,
      url: "https://www.alibaba.com",
      description: "نتيجة تجريبية بدون مفتاح API.",
    },
  ];
}

/**
 * Keep the sourcing workflow usable without exposing a third-party credential
 * in the browser bundle. Real AI search must be restored through an
 * authenticated backend endpoint; no such endpoint exists in this repository.
 */
export const findProducts = async (query: SearchQuery): Promise<Product[]> =>
  mockProducts(query);
