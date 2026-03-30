
import { GoogleGenAI, Type } from "@google/genai";
import { Product, SearchQuery, GeminiAnalysis } from '../types';

const getApiKey = (): string => {
  const fromDefine =
    typeof process !== "undefined" && process.env && (process.env as any).API_KEY
      ? String((process.env as any).API_KEY)
      : "";
  const vite = import.meta.env?.VITE_GEMINI_API_KEY;
  return (fromDefine && fromDefine !== "undefined" ? fromDefine : "") || (vite ? String(vite) : "");
};

let _ai: GoogleGenAI | null = null;
const getAi = (): GoogleGenAI | null => {
  const key = getApiKey().trim();
  if (!key) return null;
  if (!_ai) _ai = new GoogleGenAI({ apiKey: key });
  return _ai;
};

const fileToGenerativePart = async (file: File) => {
  const base64EncodedDataPromise = new Promise<string>((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve((reader.result as string).split(',')[1]);
    reader.readAsDataURL(file);
  });
  return {
    inlineData: { data: await base64EncodedDataPromise, mimeType: file.type },
  };
};

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
      description: "أضف GEMINI_API_KEY في ملف .env لاستخدام البحث بالذكاء الاصطناعي.",
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

export const findProducts = async (query: SearchQuery): Promise<Product[]> => {
  const ai = getAi();
  if (!ai) {
    console.warn(
      "[geminiService] لا يوجد GEMINI_API_KEY — استخدم نتائج تجريبية. ضع المفتاح في .env (GEMINI_API_KEY أو VITE_GEMINI_API_KEY)."
    );
    return mockProducts(query);
  }

  try {
    const imagePart = await fileToGenerativePart(query.image);
    const promptText = `
      You are an expert product sourcing agent for Chinese markets (AliExpress, Alibaba, 1688).
      Analyze this product image and description: "${query.description}".
      Target Price: $${query.targetPrice}.
      Generate 6-10 realistic recommendations in JSON with products: name, price, store, similarity, url, description.
    `;
    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: { parts: [imagePart, { text: promptText }] },
      config: {
        responseMimeType: "application/json",
        responseSchema: {
            type: Type.OBJECT,
            properties: {
                marketAnalysis: { type: Type.STRING },
                recommendedPriceRange: { type: Type.STRING },
                products: { 
                    type: Type.ARRAY,
                    items: {
                        type: Type.OBJECT,
                        properties: {
                            name: { type: Type.STRING },
                            price: { type: Type.NUMBER },
                            store: { type: Type.STRING },
                            similarity: { type: Type.NUMBER },
                            url: { type: Type.STRING },
                            description: { type: Type.STRING }
                        }
                    }
                }
            }
        }
      },
    });
    if (!response.text) throw new Error("Gemini failed.");
    const data = JSON.parse(response.text) as GeminiAnalysis;
    return data.products.map((p, index) => ({
        name: p.name,
        price: p.price,
        imageUrl: index === 0 
            ? 'https://placehold.co/400x400/e2e8f0/1e293b?text=Best+Match'
            : `https://placehold.co/400x400/f1f5f9/475569?text=${encodeURIComponent(p.name.substring(0, 20))}`,
        store: p.store,
        similarity: p.similarity,
        url: p.url,
        description: p.description
    }));
  } catch (error) {
    console.error("Error in Gemini sourcing workflow:", error);
    throw error;
  }
};
