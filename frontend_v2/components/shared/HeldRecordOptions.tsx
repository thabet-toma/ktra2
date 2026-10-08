/**
 * T4 — خيارا `<select>` لسجلٍّ يحمله مستندٌ قائم وغاب عن قائمة الاختيار لأنه أُوقف.
 *
 * `<select>` لا يعرض قيمةً لا خيار لها: طرفٌ أو منتجٌ أُوقف بعد كتابة المستند كان يظهر فارغاً.
 * الخياران يضيفان **المحدَّد حالياً** وحده (لا قائمة الموقوفين) ويَسمانه «(غير نشط)» —
 * فيُرى ولا يُختار لمستندٍ جديد، وبمجرد تبديل القيمة يختفي الخيار.
 */
import React from "react";
import { labelWithStatus } from "../../utils/activeStatus";

type WithId = { id: number | string };

/** خيار الطرف المحدَّد إن لم يكن في `partners` وكان بين `extras` (الأطراف المجلوبة فرادى). */
export const HeldPartnerOption: React.FC<{
  value: string | number | "";
  partners: ReadonlyArray<WithId>;
  extras: ReadonlyArray<WithId & { name: string; is_active?: boolean }>;
}> = ({ value, partners, extras }) => {
  const key = String(value ?? "");
  if (!key || partners.some((p) => String(p.id) === key)) return null;
  const held = extras.find((p) => String(p.id) === key);
  if (!held) return null;
  return <option value={key}>{labelWithStatus(held.name, held.is_active)}</option>;
};

/**
 * خيار المنتج المحدَّد على سطرٍ إن لم يكن في `products`. إن لم يُجلب (فشل الجلب) يُعرض
 * اسم السطر المحفوظ بلا وسم — لا يُدَّعى «غير نشط» دون دليل.
 */
export const HeldProductOption: React.FC<{
  value: string | number | "";
  products: ReadonlyArray<WithId>;
  extras: ReadonlyArray<WithId & { is_active?: boolean }>;
  /** اسم المنتج كما يعرضه المحرّر في خياراته. */
  label: (p: never) => string;
  /** اسم السطر المحفوظ مع المستند — احتياطٌ إن لم يُجلب المنتج. */
  fallbackName?: string;
}> = ({ value, products, extras, label, fallbackName }) => {
  const key = String(value ?? "");
  if (!key || products.some((p) => String(p.id) === key)) return null;
  const held = extras.find((p) => String(p.id) === key);
  const text = held
    ? labelWithStatus((label as (p: unknown) => string)(held), held.is_active)
    : (fallbackName || `#${key}`);
  return <option value={key}>{text}</option>;
};
