/**
 * M2-COGS: خيارات طريقة احتساب تكلفة البضاعة المباعة في إعدادات المبيعات
 * وحساب جدول مثال §4 من طبقات المخزون.
 *
 * ملاحظة: `avco` مخفيٌّ من القائمة عمداً حتى تذكرة M5 (الخادم يرفضه أيضاً).
 */
export const COGS_COST_METHOD_OPTIONS = [
  { value: "fifo", label: "الوارد أولاً يصرف أولاً (FIFO)" },
  { value: "standard", label: "السعر الثابت (التكلفة المعيارية)" },
  { value: "last_purchase", label: "آخر سعر شراء" },
] as const;

export type CogsCostMethod = typeof COGS_COST_METHOD_OPTIONS[number]["value"];

const VALID_METHODS = new Set<string>(COGS_COST_METHOD_OPTIONS.map((o) => o.value));

/** طريقتا اللقطة الثابتة اللتان تتطلّبان حساب فروقات تكلفة (مرآة `FIXED_SNAPSHOT_METHODS`). */
export function isFixedSnapshotMethod(method?: string | null): boolean {
  return method === "standard" || method === "last_purchase";
}

/** القيمة المفقودة أو غير المعروفة (ومنه `avco` قبل M5) تُعامَل `fifo`. */
export function normalizeCogsCostMethod(method?: string | null): CogsCostMethod {
  return method && VALID_METHODS.has(method)
    ? (method as CogsCostMethod)
    : "fifo";
}

export type ExampleLayer = {
  qty: number;
  unitCost: number;
};

export type CogsExampleScenario = {
  layers: readonly ExampleLayer[];
  sellQty: number;
  standardUnitCost: number;
};

/** سيناريو القبول الإلزامي (§4): استلام 8@10 ثم 4@16 ثم بيع 10، وسعر ثابت 11. */
export const DEFAULT_COGS_EXAMPLE_SCENARIO: CogsExampleScenario = {
  layers: [
    { qty: 8, unitCost: 10 },
    { qty: 4, unitCost: 16 },
  ],
  sellQty: 10,
  standardUnitCost: 11,
};

export type VarianceSide = "debit" | "credit" | "none";

export type CogsExampleRow = {
  method: CogsCostMethod;
  label: string;
  cogs: number;
  varianceSide: VarianceSide;
  varianceAmount: number;
  inventoryCredit: number;
  remainingInventory: number;
};

export const round2 = (n: number): number => Math.round(n * 100) / 100;

/**
 * يحسب أرقام جدول المثال (§4) من الطبقات لا أرقاماً ثابتة:
 * - دائن المخزون والتكلفة الفعلية يُحسبان باستهلاك FIFO للطبقات لكل الطرق الثلاث الظاهرة.
 * - الفروقات (§3.2) = دائن المخزون − تكلفة المبيعات:
 *   موجب ⇒ مدين، سالب ⇒ دائن، صفر ⇒ بلا فرق (`none`).
 */
export function computeCogsExampleRows(
  scenario: CogsExampleScenario = DEFAULT_COGS_EXAMPLE_SCENARIO,
): CogsExampleRow[] {
  let toConsume = scenario.sellQty;
  let fifoCost = 0;
  let remainingInventory = 0;
  for (const layer of scenario.layers) {
    const take = Math.min(toConsume, Math.max(0, layer.qty));
    const left = layer.qty - take;
    fifoCost += take * layer.unitCost;
    remainingInventory += left * layer.unitCost;
    toConsume -= take;
  }
  fifoCost = round2(fifoCost);
  remainingInventory = round2(remainingInventory);

  const lastUnitCost =
    scenario.layers.length > 0
      ? scenario.layers[scenario.layers.length - 1].unitCost
      : 0;

  return COGS_COST_METHOD_OPTIONS.map((opt) => {
    let cogs: number;
    switch (opt.value) {
      case "fifo":
        cogs = fifoCost;
        break;
      case "standard":
        cogs = round2(scenario.sellQty * scenario.standardUnitCost);
        break;
      case "last_purchase":
        cogs = round2(scenario.sellQty * lastUnitCost);
        break;
    }
    const inventoryCredit = fifoCost;
    const diff = round2(inventoryCredit - cogs);
    const varianceSide: VarianceSide =
      diff > 0 ? "debit" : diff < 0 ? "credit" : "none";
    return {
      method: opt.value,
      label: opt.label,
      cogs,
      varianceSide,
      varianceAmount: Math.abs(diff),
      inventoryCredit,
      remainingInventory,
    };
  });
}

export function formatCogsVariance(side: VarianceSide, amount: number): string {
  if (side === "none" || amount === 0) return "—";
  return `${side === "debit" ? "مدين" : "دائن"} ${amount}`;
}
