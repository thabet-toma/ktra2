/**
 * T-REORDER: حالة المنتج داخل مستندات البيع — شارةٌ واحدة وبدائلُ نوعٍ واحد.
 *
 * لماذا هنا لا في كل شاشة: منتقي المنتج يظهر في فاتورة البيع وعرض السعر وطلبية
 * الزبون وسند التسليم، وكلٌّ منها كان يبني سطره الثانوي بيده. شارةُ «نفذ» التي
 * تُكتب أربع مرّات تتباعد عند أول تعديل، والحالةُ نفسها يحسمها الخادم أصلاً
 * (`inventory/stock_status.py`) فلا تُعاد هنا — تُقرأ.
 *
 * والبديل: منتجات **نفس النوع** (`group_key` الخادمي) التي عليها رصيد. هذا هو
 * الفرق بين «الرصيد 0» و«الرصيد 0، وهذا الموديل الجديد منه أربعون» — الأولى
 * تُنهي البيع والثانية تُتمّه.
 */

export type StockTone = 'danger' | 'warn';

export interface StockBadge {
  text: string;
  tone: StockTone;
  title: string;
}

export interface StockLike {
  id: number;
  /** من الخادم: out_of_stock | low_stock | overstock | in_stock */
  stock_status?: string | null;
  is_service?: boolean | null;
  group_key?: string | null;
  quantity_on_hand?: string | number | null;
  available_quantity?: string | number | null;
}

/** المتاح إن أرسله الخادم، وإلّا الرصيد — لا تُعاد قاعدة الحجز هنا. */
export function availableOf(p: StockLike): number {
  const raw = p.available_quantity ?? p.quantity_on_hand ?? 0;
  const n = Number(raw);
  return Number.isFinite(n) ? n : 0;
}

/**
 * شارة المنتج في القائمة. الخدمة بلا مخزون فبلا شارة — «نفذ» على بند خدمة
 * إنذارٌ كاذب. و«متوفّر» بلا شارة عمداً: القائمة تُنبِّه ولا تُزيَّن.
 */
export function stockBadgeFor(p: StockLike): StockBadge | undefined {
  if (p.is_service) return undefined;
  if (p.stock_status === 'out_of_stock') {
    return { text: 'نفذ', tone: 'danger', title: 'لا رصيد متاح — راجع البدائل من نفس النوع' };
  }
  if (p.stock_status === 'low_stock') {
    return { text: 'منخفض', tone: 'warn', title: 'الرصيد المتاح بلغ الحد الأدنى' };
  }
  return undefined;
}

/** هل يستحق هذا المنتج اقتراح بديل — أي أن بيعه متعثّر الآن. */
export function needsAlternative(p: StockLike | undefined | null): boolean {
  if (!p || p.is_service) return false;
  return p.stock_status === 'out_of_stock' || p.stock_status === 'low_stock';
}

/**
 * بدائل المنتج: موديلات نفس النوع التي عليها رصيد متاح، الأوفر أولاً.
 * منتجٌ بلا `group_key` بلا بدائل — لا نخمّن التبادل من تشابه الاسم.
 */
export function stockAlternatives<T extends StockLike>(all: T[], target: T, limit = 5): T[] {
  const key = (target.group_key || '').trim();
  if (!key) return [];
  return all
    .filter((p) => p.id !== target.id
      && (p.group_key || '').trim() === key
      && !p.is_service
      && availableOf(p) > 0)
    .sort((a, b) => availableOf(b) - availableOf(a))
    .slice(0, limit);
}
