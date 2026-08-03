/**
 * T-RESERVEVIS: قراءة الحجز في فاتورة البيع — مصدر واحد لما تعرضه الخلايا وما
 * يقوله التنبيه.
 *
 * الخادم يرفض ترحيل فاتورة تسحب كمية محجوزة لطلبية **زبون آخر**
 * (`sales.services.guard_reserved_stock`)، لكن المستخدم كان يكتشف ذلك بعد
 * الترحيل. هذه الدوال تعيد بناء **نفس القاعدة** على صفوف «تقرير المحجوزات»
 * (نفس مصدر الحارس) فتُرى الأرقام قبل الرفض لا بعده:
 *   المتاح للبيع = الرصيد − المحجوز لغير هذا الزبون.
 * حجز الزبون نفسه لا يُطرَح — حجزُه لا يمنعه هو.
 */

/** صف حجز — مقتطع من `ReservedStockRow` بما يكفي للحساب (لا تبعية بالـ API). */
export type ReservationHold = {
  order_id: number;
  order_number: string;
  customer_id: number;
  customer_name: string;
  product_id: number;
  quantity: string | number;
};

export type ProductReservation = {
  /** المحجوز الذي يزاحم هذه الفاتورة (بعد استثناء حجوزات زبونها). */
  reserved: number;
  /** حجز الزبون نفسه — يُعرض للعلم ولا يُطرح من المتاح. */
  ownReserved: number;
  holders: { orderId: number; orderNumber: string; customerName: string; quantity: number }[];
};

const num = (value: string | number | null | undefined): number => {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
};

/**
 * يجمع صفوف الحجز لكل صنف. `excludeCustomerId` = زبون الفاتورة الحالية:
 * حجوزاته تُحسب في `ownReserved` ولا تدخل `reserved`.
 */
export function buildReservationIndex(
  rows: ReservationHold[],
  excludeCustomerId?: number | null,
): Map<number, ProductReservation> {
  const index = new Map<number, ProductReservation>();
  for (const row of rows) {
    const entry = index.get(row.product_id)
      ?? { reserved: 0, ownReserved: 0, holders: [] };
    const quantity = num(row.quantity);
    if (excludeCustomerId != null && row.customer_id === excludeCustomerId) {
      entry.ownReserved += quantity;
    } else {
      entry.reserved += quantity;
      entry.holders.push({
        orderId: row.order_id,
        orderNumber: row.order_number,
        customerName: row.customer_name,
        quantity,
      });
    }
    index.set(row.product_id, entry);
  }
  return index;
}

/** المتاح للبيع على هذه الفاتورة = الرصيد − المحجوز لغير زبونها. */
export function availableForSale(
  onHand: string | number | null | undefined,
  entry?: ProductReservation,
): number {
  return num(onHand) - (entry?.reserved ?? 0);
}

export type ReservedSaleLine = {
  productId: number;
  quantity: string | number;
  onHand: string | number;
  name: string;
  /** الخدمة والصنف الذي يسمح بالسالب معفيان — كما في حارس الخادم. */
  exempt?: boolean;
};

export type ReservedSaleWarning = {
  name: string;
  quantity: number;
  available: number;
  reserved: number;
  holders: string[];
};

/**
 * تنبيه لكل صنف تتجاوز كميتُه المتاحَ بعد الحجز. الكميات تُجمَّع لكل صنف —
 * سطران من نفس الصنف يزاحمان الحجز مجتمعَين لا كلٌّ على حدة (نفس تجميع الحارس).
 */
export function reservedSaleWarnings(
  lines: ReservedSaleLine[],
  index: Map<number, ProductReservation>,
): ReservedSaleWarning[] {
  const requested = new Map<number, { quantity: number; onHand: number; name: string }>();
  for (const line of lines) {
    if (line.exempt || !line.productId) continue;
    const entry = requested.get(line.productId)
      ?? { quantity: 0, onHand: num(line.onHand), name: line.name };
    entry.quantity += num(line.quantity);
    requested.set(line.productId, entry);
  }

  const warnings: ReservedSaleWarning[] = [];
  for (const [productId, line] of requested) {
    const entry = index.get(productId);
    if (!entry || entry.reserved <= 0) continue;
    const available = line.onHand - entry.reserved;
    if (line.quantity <= available + 1e-6) continue;
    warnings.push({
      name: line.name,
      quantity: line.quantity,
      available,
      reserved: entry.reserved,
      holders: entry.holders.map((h) => `${h.orderNumber} (${h.customerName})`),
    });
  }
  return warnings;
}
