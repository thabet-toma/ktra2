export const KTRA_CACHE_PREFIX = "ktra-";

export function isKtraCacheName(cacheName: string): boolean {
  return cacheName.startsWith(KTRA_CACHE_PREFIX);
}

/** Only unregister the worker whose same-origin scope actually covers this page. */
export function serviceWorkerScopeCoversPage(scope: string, pageUrl: string): boolean {
  try {
    const scopeUrl = new URL(scope);
    const page = new URL(pageUrl);
    return scopeUrl.origin === page.origin && page.pathname.startsWith(scopeUrl.pathname);
  } catch {
    return false;
  }
}
