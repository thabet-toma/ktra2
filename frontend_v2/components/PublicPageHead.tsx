import React from "react";

import { findPublicPage } from "../constants/publicPages";

/**
 * وسوم الرأس لصفحة عامة من `constants/publicPages.ts` — بدعم React 19 الأصلي:
 * `<title>` و`<meta>` و`<link rel="canonical">` تُرفع إلى `<head>` أينما صُيِّرت،
 * وتُزال عند مغادرة الصفحة. نسخُ `index.html` الثابتة (`data-seo`) يحذفها
 * `index.tsx` عند الإقلاع كي لا يتعارض وسمان.
 */
export const PublicPageHead: React.FC<{ path: string }> = ({ path }) => {
  const page = findPublicPage(path);
  if (!page) return null;
  return (
    <>
      <title>{page.title}</title>
      <meta name="description" content={page.description} />
      <link rel="canonical" href={page.canonical} />
      <meta property="og:url" content={page.canonical} />
    </>
  );
};
