/**
 * T4 — مستندٌ قائم يحمل منتجاً أو طرفاً أُوقف بعد كتابته.
 *
 * منتقيات المستندات (`lookup/products/`، `partners/lookup/`) تُخفي الموقوف كي لا يدخل
 * مستنداً جديداً، فمحرِّرٌ يبني خريطة الأسماء من المنتقي نفسه كان سيعرض سطراً بلا اسم.
 * هذان الخطّافان يجلبان ما يغيب فقط — فرادى من نقطة الاسترجاع غير المفلترة بالحالة — ويُرجعان
 * صفوفاً **إضافية** تُدمج في خريطة العرض وحدها، **لا** في خيارات الاختيار: الموقوف يُرى ولا يُختار.
 */
import { useEffect, useRef, useState } from "react";
import { fetchProductsByIds } from "../services/inventoryApi";
import { apiGetObject } from "../services/restApi";
import { missingRecordIds } from "../utils/activeStatus";
import { resolveTenantId } from "../utils/tenantContext";

type HasId = { id: number | string };

function useMissingRecords<T extends HasId>(
  used: ReadonlyArray<unknown>,
  known: ReadonlyArray<T>,
  fetchMany: (ids: number[]) => Promise<T[]>,
): T[] {
  const [extras, setExtras] = useState<T[]>([]);
  // معرّفات جُرّبت (نجحت أو فشلت): تمنع إعادة الطلب في كل رسم، وفشلُ معرّفٍ لا يتكرّر.
  const tried = useRef<Set<number>>(new Set());
  const alive = useRef(true);
  const fetchRef = useRef(fetchMany);
  fetchRef.current = fetchMany;
  const usedKey = used.map((u) => String(u ?? "")).join(",");

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  useEffect(() => {
    // القائمة لم تصل بعد ⇒ كل المعرّفات «ناقصة» ظاهراً؛ ننتظرها كي لا نجلب ما سيصل مجاناً.
    if (known.length === 0) return;
    const ids = missingRecordIds(used, known, tried.current);
    if (ids.length === 0) return;
    ids.forEach((id) => tried.current.add(id));
    void fetchRef.current(ids).then((rows) => {
      if (!alive.current || rows.length === 0) return;
      setExtras((prev) => {
        const byId = new Map<string, T>(prev.map((r) => [String(r.id), r]));
        rows.forEach((r) => byId.set(String(r.id), r));
        return [...byId.values()];
      });
    });
    // `used` ممثَّلٌ بمفتاحه النصّي حتى لا تُعيد مصفوفةٌ جديدة كل رسمٍ تشغيل الأثر.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [usedKey, known]);

  return extras;
}

/** منتجات يحملها المستند وليست في قائمة المنتقي النشطة (موقوفة غالباً). */
export function useMissingProducts<T extends HasId>(
  usedProductIds: ReadonlyArray<unknown>,
  knownProducts: ReadonlyArray<T>,
): T[] {
  return useMissingRecords<T>(
    usedProductIds,
    knownProducts,
    (ids) => fetchProductsByIds<T>(ids, resolveTenantId()),
  );
}

/** أطراف (عملاء/موردون) يحملها المستند وليست في `partners/lookup/` النشطة. */
export function useMissingPartners<T extends HasId>(
  usedPartnerIds: ReadonlyArray<unknown>,
  knownPartners: ReadonlyArray<T>,
): T[] {
  return useMissingRecords<T>(
    usedPartnerIds,
    knownPartners,
    async (ids) => {
      const tenantId = resolveTenantId();
      const settled = await Promise.allSettled(
        ids.map((id) => apiGetObject<T>(`partners/${id}/`, { tenantId })),
      );
      return settled.flatMap((r) => (r.status === "fulfilled" ? [r.value] : []));
    },
  );
}
