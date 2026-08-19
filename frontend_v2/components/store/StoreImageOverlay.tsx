import React from "react";
import { Flame, Sparkles, Tag, Zap } from "lucide-react";
import type { StoreImageOverlayData } from "../../services/storeApi";

export const OVERLAY_COLOR_PRESETS: {
  key: string;
  name: string;
  badgeBg: string;
  badgeText: string;
  bannerBg: string;
  bannerText: string;
  canvasBg: string;
  canvasText: string;
}[] = [
  {
    key: "red_fire",
    name: "أحمر ناري (عروض ساخنة)",
    badgeBg: "bg-gradient-to-r from-rose-600 via-red-600 to-amber-600",
    badgeText: "text-white",
    bannerBg: "bg-red-600/95 backdrop-blur-sm",
    bannerText: "text-white",
    canvasBg: "#dc2626",
    canvasText: "#ffffff",
  },
  {
    key: "gold_luxury",
    name: "ذهبي ملكي (فخامة وتميز)",
    badgeBg: "bg-gradient-to-r from-amber-500 via-yellow-400 to-amber-600",
    badgeText: "text-amber-950 font-black",
    bannerBg: "bg-amber-500/95 backdrop-blur-sm",
    bannerText: "text-amber-950 font-black",
    canvasBg: "#f59e0b",
    canvasText: "#451a03",
  },
  {
    key: "emerald_fresh",
    name: "أخضر زمردي (توفير وحصري)",
    badgeBg: "bg-gradient-to-r from-emerald-600 to-teal-600",
    badgeText: "text-white",
    bannerBg: "bg-emerald-600/95 backdrop-blur-sm",
    bannerText: "text-white",
    canvasBg: "#059669",
    canvasText: "#ffffff",
  },
  {
    key: "blue_pro",
    name: "أزرق ملكي (رسمي وموثوق)",
    badgeBg: "bg-gradient-to-r from-blue-600 to-indigo-600",
    badgeText: "text-white",
    bannerBg: "bg-blue-600/95 backdrop-blur-sm",
    bannerText: "text-white",
    canvasBg: "#2563eb",
    canvasText: "#ffffff",
  },
  {
    key: "neon_purple",
    name: "بنفسجي نيون (عصري وجريء)",
    badgeBg: "bg-gradient-to-r from-fuchsia-600 to-purple-600",
    badgeText: "text-white",
    bannerBg: "bg-purple-600/95 backdrop-blur-sm",
    bannerText: "text-white",
    canvasBg: "#9333ea",
    canvasText: "#ffffff",
  },
  {
    key: "dark_glass",
    name: "أسود زجاجي (أنيق وفاخر)",
    badgeBg: "bg-slate-900/90 backdrop-blur-md border border-white/20",
    badgeText: "text-white",
    bannerBg: "bg-slate-900/95 backdrop-blur-md border-t border-white/10",
    bannerText: "text-white",
    canvasBg: "#0f172a",
    canvasText: "#ffffff",
  },
];

export const OVERLAY_STYLE_PRESETS = [
  { key: "diagonal_ribbon", name: "شريط مائل بالزاوية (Corner Ribbon)" },
  { key: "bottom_banner", name: "شريط إعلاني سفلي عريض (Bottom Banner)" },
  { key: "pill_badge", name: "شارة عائمة في الزاوية (Floating Pill Badge)" },
  { key: "glass_tag", name: "بطاقة زجاجية مدمجة (Glass Card)" },
];

export interface StoreImageOverlayProps {
  overlay?: StoreImageOverlayData | null;
  className?: string;
}

export const StoreImageOverlay: React.FC<StoreImageOverlayProps> = ({
  overlay,
  className = "",
}) => {
  if (!overlay || !overlay.text || !overlay.text.trim()) {
    return null;
  }

  const text = overlay.text.trim();
  const style = overlay.style || "diagonal_ribbon";
  const colorKey = overlay.color || "red_fire";
  const color =
    OVERLAY_COLOR_PRESETS.find((c) => c.key === colorKey) ||
    OVERLAY_COLOR_PRESETS[0];

  if (style === "diagonal_ribbon") {
    return (
      <div
        className={`pointer-events-none absolute -top-1 -right-1 z-10 overflow-hidden w-28 h-28 ${className}`}
      >
        <div
          className={`absolute top-5 -right-7 w-32 py-1 text-center font-black text-[10px] sm:text-[11px] shadow-lg shadow-black/25 transform rotate-45 tracking-wide ${color.badgeBg} ${color.badgeText}`}
        >
          {text}
        </div>
      </div>
    );
  }

  if (style === "bottom_banner") {
    return (
      <div
        className={`pointer-events-none absolute inset-x-0 bottom-0 z-10 flex items-center justify-center gap-1.5 px-3 py-1.5 text-center text-xs font-black shadow-lg ${color.bannerBg} ${color.bannerText} ${className}`}
      >
        <Flame className="h-3.5 w-3.5 fill-current shrink-0 animate-pulse" />
        <span className="truncate">{text}</span>
      </div>
    );
  }

  if (style === "pill_badge") {
    return (
      <div
        className={`pointer-events-none absolute top-2 right-2 z-10 flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-black shadow-md ${color.badgeBg} ${color.badgeText} ${className}`}
      >
        <Sparkles className="h-3 w-3 shrink-0 fill-current" />
        <span>{text}</span>
      </div>
    );
  }

  // glass_tag
  return (
    <div
      className={`pointer-events-none absolute top-2 right-2 z-10 flex items-center gap-1 rounded-xl px-2.5 py-1 text-[11px] font-black backdrop-blur-md shadow-md ${color.badgeBg} ${color.badgeText} ${className}`}
    >
      <Zap className="h-3 w-3 shrink-0 fill-current" />
      <span>{text}</span>
    </div>
  );
};

/**
 * دالة مساعدة لرسم وتوليد صورة إعلانية جاهزة على Canvas وتنزيلها
 */
export async function downloadAdCreativeImage(opts: {
  imageUrl: string;
  text: string;
  style: string;
  colorKey: string;
  productName?: string;
}): Promise<void> {
  const { imageUrl, text, style, colorKey, productName } = opts;
  const color =
    OVERLAY_COLOR_PRESETS.find((c) => c.key === colorKey) ||
    OVERLAY_COLOR_PRESETS[0];

  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("Canvas context is not supported"));
          return;
        }

        const width = img.naturalWidth || 1000;
        const height = img.naturalHeight || 1000;
        canvas.width = width;
        canvas.height = height;

        // 1. رسم صورة المنتج الأصلية
        ctx.drawImage(img, 0, 0, width, height);

        ctx.save();

        if (style === "diagonal_ribbon") {
          // رسم شريط مائل بالزاوية العلوية اليمنى
          const ribbonHeight = Math.max(50, width * 0.08);
          ctx.translate(width, 0);
          ctx.rotate((45 * Math.PI) / 180);

          ctx.fillStyle = color.canvasBg;
          ctx.shadowColor = "rgba(0, 0, 0, 0.4)";
          ctx.shadowBlur = 20;
          ctx.fillRect(-width * 0.4, width * 0.08, width * 0.8, ribbonHeight);

          ctx.fillStyle = color.canvasText;
          ctx.font = `bold ${Math.max(22, Math.floor(ribbonHeight * 0.48))}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(text, 0, width * 0.08 + ribbonHeight / 2);
        } else if (style === "bottom_banner") {
          // رسم شريط إعلاني عريض أسفل الصورة
          const bannerH = Math.max(70, height * 0.12);
          ctx.fillStyle = color.canvasBg;
          ctx.shadowColor = "rgba(0, 0, 0, 0.4)";
          ctx.shadowBlur = 15;
          ctx.fillRect(0, height - bannerH, width, bannerH);

          ctx.fillStyle = color.canvasText;
          ctx.font = `bold ${Math.max(26, Math.floor(bannerH * 0.42))}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(text, width / 2, height - bannerH / 2);
        } else {
          // pill_badge / glass_tag
          const badgeW = Math.min(width * 0.8, Math.max(220, text.length * 24));
          const badgeH = Math.max(55, height * 0.08);
          const badgeX = width - badgeW - 30;
          const badgeY = 30;
          const radius = style === "pill_badge" ? badgeH / 2 : 20;

          ctx.fillStyle = color.canvasBg;
          ctx.shadowColor = "rgba(0, 0, 0, 0.35)";
          ctx.shadowBlur = 18;

          ctx.beginPath();
          ctx.roundRect(badgeX, badgeY, badgeW, badgeH, radius);
          ctx.fill();

          ctx.fillStyle = color.canvasText;
          ctx.font = `bold ${Math.max(22, Math.floor(badgeH * 0.45))}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(text, badgeX + badgeW / 2, badgeY + badgeH / 2);
        }

        ctx.restore();

        // 3. تصدير الصورة وتنزيلها للمستخدم
        const dataUrl = canvas.toDataURL("image/jpeg", 0.95);
        const link = document.createElement("a");
        const cleanName = (productName || "ad-creative")
          .replace(/[^\w\u0600-\u06FF]+/g, "-")
          .toLowerCase();
        link.download = `${cleanName}-promo.jpg`;
        link.href = dataUrl;
        link.click();
        resolve();
      } catch (err) {
        reject(err);
      }
    };
    img.onerror = () => reject(new Error("Failed to load source image for canvas"));
    img.src = imageUrl;
  });
}
