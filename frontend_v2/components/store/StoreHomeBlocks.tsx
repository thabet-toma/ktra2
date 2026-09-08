/**
 * كتلُ الصفحة الرئيسية للمتجر (THA-166 م٦) — تُعرَض فوق الشبكة القائمة،
 * والشبكةُ تبقى تحتها كما هي (قاعدة السقوط: بلا كتلٍ لا فرق يُرى).
 *
 * ملفٌّ مستقلٌّ تحت `components/store/` على غرار `StoreCatalogSlider`/
 * `StoreProductCard` — لا يستورد من `components/kit` أيّ مكوّنٍ يجرّ سياقاً،
 * فيبقى مسار المتجر خفيفاً وكسولَ التحميل كما هو.
 */
import React from "react";
import { ArrowLeft } from "lucide-react";
import type { StoreHomeBlock, StoreProfile } from "../../services/storeApi";
import { StoreProductCard } from "./StoreProductCard";

interface StoreHomeBlocksProps {
  blocks: StoreHomeBlock[];
  profile: StoreProfile | null;
  onOpenProduct: (productId: number, name?: string) => void;
  onOpenCollection?: (collectionSlug: string) => void;
  onOpenCategory?: (categoryId: number) => void;
}

/** `link.target` قد يصل رقماً أو نصاً (توافقٌ خلفي) — المعرّف وحده الحاكم. */
function targetCategoryId(target: string | number | null): number | null {
  if (target === null || target === undefined) return null;
  const n = typeof target === "number" ? target : parseInt(target, 10);
  return Number.isFinite(n) ? n : null;
}

/** صفٌّ أفقيٌّ قابلٌ للتمرير على الجوّال، وشبكةٌ من فوق `sm:` — لا عمودٌ طويلٌ يبتلع الصفحة. */
const ROW_SCROLLER_CLASS =
  "flex gap-3 overflow-x-auto pb-2 scrollbar-none sm:grid sm:grid-cols-3 sm:overflow-visible md:grid-cols-4";

export const StoreHomeBlocks: React.FC<StoreHomeBlocksProps> = ({
  blocks,
  profile,
  onOpenProduct,
  onOpenCollection,
  onOpenCategory,
}) => {
  if (!blocks.length) return null;

  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 pt-6 sm:px-6">
      {blocks.map((block) => {
        if (block.kind === "hero") {
          const isCollectionLink = block.link.kind === "collection" && typeof block.link.target === "string";
          const categoryId = block.link.kind === "category" ? targetCategoryId(block.link.target) : null;
          const isCategoryLink = categoryId !== null;
          const isUrlLink = block.link.kind === "url" && !!block.link.url;
          const clickable = isCollectionLink || isCategoryLink || isUrlLink;

          const content = (
            <>
              {(block.image_url || block.image_url_mobile) && (
                <picture>
                  {block.image_url_mobile && (
                    <source media="(max-width: 640px)" srcSet={block.image_url_mobile} />
                  )}
                  <img
                    src={block.image_url || block.image_url_mobile || ""}
                    alt={block.title || ""}
                    className="h-40 w-full object-cover sm:h-64 md:h-80"
                  />
                </picture>
              )}
              {(block.title || block.subtitle) && (
                <div className="bg-white p-4 text-center dark:bg-slate-900">
                  {block.title && (
                    <h3 className="text-base font-black text-slate-900 dark:text-white sm:text-xl">
                      {block.title}
                    </h3>
                  )}
                  {block.subtitle && (
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{block.subtitle}</p>
                  )}
                </div>
              )}
            </>
          );

          const wrapperClass = `block overflow-hidden rounded-3xl border border-slate-200 shadow-sm dark:border-slate-800 ${
            clickable ? "cursor-pointer" : ""
          }`;

          if (isUrlLink) {
            return (
              <a
                key={block.id}
                href={block.link.url as string}
                target="_blank"
                rel="noopener noreferrer"
                className={wrapperClass}
              >
                {content}
              </a>
            );
          }
          if (isCollectionLink && onOpenCollection) {
            return (
              <button
                key={block.id}
                type="button"
                onClick={() => onOpenCollection(block.link.target as string)}
                className={`w-full text-right ${wrapperClass}`}
              >
                {content}
              </button>
            );
          }
          if (isCategoryLink && onOpenCategory && categoryId !== null) {
            return (
              <button
                key={block.id}
                type="button"
                onClick={() => onOpenCategory(categoryId)}
                className={`w-full text-right ${wrapperClass}`}
              >
                {content}
              </button>
            );
          }
          return (
            <div key={block.id} className={wrapperClass}>
              {content}
            </div>
          );
        }

        if (block.kind === "active_campaigns") {
          if (!block.campaigns.length) return null;
          return (
            <div key={block.id}>
              {block.title && (
                <h3 className="mb-3 text-base font-black text-slate-900 dark:text-white">{block.title}</h3>
              )}
              <div className={ROW_SCROLLER_CLASS}>
                {block.campaigns.map((col) => (
                  <button
                    key={col.id}
                    type="button"
                    onClick={() => onOpenCollection?.(col.slug)}
                    className="w-48 shrink-0 overflow-hidden rounded-2xl border border-slate-200 bg-white text-right shadow-sm transition hover:shadow-md dark:border-slate-800 dark:bg-slate-900 sm:w-auto"
                  >
                    {col.banner_image_url && (
                      <img src={col.banner_image_url} alt={col.title} className="h-24 w-full object-cover" />
                    )}
                    <div className="p-3">
                      {col.badge_text && (
                        <span className="mb-1 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                          {col.badge_text}
                        </span>
                      )}
                      <p className="text-xs font-bold text-slate-900 dark:text-white">{col.title}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          );
        }

        // campaign_row · category_row · featured · most_viewed — صفّ منتجات،
        // وبطاقةُ المنتج هي `StoreProductCard` نفسُها — لا نسخةٌ ثانية.
        if (!block.products.length) return null;
        const seeAllSlug =
          block.link.kind === "collection" && typeof block.link.target === "string"
            ? block.link.target
            : null;
        const seeAllCategoryId = block.link.kind === "category" ? targetCategoryId(block.link.target) : null;
        return (
          <div key={block.id}>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                {block.title && (
                  <h3 className="text-base font-black text-slate-900 dark:text-white">{block.title}</h3>
                )}
                {block.subtitle && (
                  <p className="text-xs text-slate-500 dark:text-slate-400">{block.subtitle}</p>
                )}
              </div>
              {seeAllSlug && onOpenCollection && (
                <button
                  type="button"
                  onClick={() => onOpenCollection(seeAllSlug)}
                  className="flex shrink-0 items-center gap-1 text-xs font-bold text-[var(--store-primary,#2563eb)] hover:underline"
                >
                  <span>عرض الكل</span>
                  <ArrowLeft className="h-3.5 w-3.5" />
                </button>
              )}
              {seeAllCategoryId !== null && onOpenCategory && (
                <button
                  type="button"
                  onClick={() => onOpenCategory(seeAllCategoryId)}
                  className="flex shrink-0 items-center gap-1 text-xs font-bold text-[var(--store-primary,#2563eb)] hover:underline"
                >
                  <span>عرض الكل</span>
                  <ArrowLeft className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            <div className={ROW_SCROLLER_CLASS}>
              {block.products.map((product) => (
                <div key={product.id} className="w-40 shrink-0 sm:w-auto">
                  <StoreProductCard
                    product={product}
                    currency={profile?.currency ?? null}
                    onOpen={(item) => onOpenProduct(item.id, item.name_ar || item.name_en || undefined)}
                  />
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default StoreHomeBlocks;
