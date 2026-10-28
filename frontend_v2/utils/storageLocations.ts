/**
 * TASK-2b — موقعُ التخزين لكل مخزن: المنطقُ الخالص وحدَه (بلا React ولا fetch).
 *
 * الخادم (TASK-2a) يرفض رفضاً عربيّاً صريحاً: `grid` بلا عمودٍ أو صفّ، `code`
 * بلا رمز، ومخزناً مكرَّراً في القائمة. ورسائلُ هذا الملف هي رسائلُه **حرفاً**
 * (`inventory/serializers.py`): صياغةٌ ثانية لنفس الرفض تُنتج نصّين لما هو قاعدةٌ
 * واحدة، ويرى المستخدم هذا مرّةً وذاك مرّة.
 *
 * وحدَه `PUT` **يستبدل** كلَّ مواقع المنتج — فحمولةُ الحفظ تصف الحالة النهائية،
 * ولا تُرسَل إلا إن تغيّرت عمّا حُمِّل (`storageLocationsChanged`).
 */

export type StorageKind = "grid" | "code";

/** حدود الخادم (`ProductStorageLocation`): العمود والصف 20، والرمز 50. */
export const STORAGE_COLUMN_MAX = 20;
export const STORAGE_ROW_MAX = 20;
export const STORAGE_CODE_MAX = 50;

/** صفُّ موقعٍ كما يردّه الخادم (`GET`/`PUT` `products/{id}/storage-locations/`). */
export interface StorageLocationRow {
  id: number;
  warehouse: number;
  warehouse_name: string;
  kind: StorageKind;
  column: string;
  row: string;
  code: string;
  /** صيغة العرض الوحيدة على الخادم: `عمود {column} · صف {row}` أو الرمز. */
  label: string;
}

/** جسمُ `PUT` — الحقول الخمسة وحدها؛ المعرّف والاسم من الخادم. */
export interface StorageLocationBody {
  warehouse: number;
  kind: StorageKind;
  column: string;
  row: string;
  code: string;
}

/** سطرُ المحرّر — نصٌّ كما كتبه المستخدم، يُقصّ عند التحويل لا أثناء الكتابة. */
export interface StorageLocationDraft {
  warehouse: number | null;
  /** اسمُ المخزن لتسمية الرسائل وللعرض؛ يصل من الخادم أو من القائمة. */
  warehouse_name: string;
  kind: StorageKind;
  column: string;
  row: string;
  code: string;
}

/** أقلُّ ما تقرؤه الشاشة من صفّ `warehouses/`. */
export interface WarehouseOption {
  id: number;
  name: string;
  is_active?: boolean;
  is_default?: boolean;
}

/** رسالةُ رفضٍ عند حقلٍ في سطرٍ بعينه (الفهرس من ترتيب السطور). */
export interface StorageLocationIssue {
  index: number;
  field: "warehouse" | "column" | "row" | "code";
  message: string;
}

/** سطرٌ فارغ — ويُقترح له المخزن الممرَّر إن وُجد. */
export const blankStorageLocationDraft = (
  warehouse?: WarehouseOption | null,
): StorageLocationDraft => ({
  warehouse: warehouse?.id ?? null,
  warehouse_name: warehouse?.name ?? "",
  kind: "grid",
  column: "",
  row: "",
  code: "",
});

/** صفوفُ الخادم ← سطورُ المحرّر (حمولةُ `GET` وحمولةُ ردّ `PUT` نفسُ الشكل). */
export const storageDraftsFromRows = (
  rows: readonly StorageLocationRow[],
): StorageLocationDraft[] =>
  rows.map((row) => ({
    warehouse: row.warehouse,
    warehouse_name: row.warehouse_name ?? "",
    kind: row.kind === "code" ? "code" : "grid",
    column: row.column ?? "",
    row: row.row ?? "",
    code: row.code ?? "",
  }));

/**
 * نصُّ الموقع المعروض — مطابقٌ لصياغة الخادم حرفاً (`ProductStorageLocation.label`)
 * فيُرى في المحرّر ما سيُرى في الكرت.
 */
export const storageLocationLabel = (
  kind: StorageKind,
  column: string,
  row: string,
  code: string,
): string => (kind === "grid"
  ? `عمود ${column.trim()} · صف ${row.trim()}`
  : code.trim());

/**
 * سطورُ المحرّر ← جسمُ `PUT`: قصُّ القيم، وتفريغُ حقول النوع الآخر.
 *
 * `grid` يُرسل عمودَه وصفَّه و`code: ''`، و`code` يُرسل رمزه و`column`/`row`
 * فارغين — لأن الخادم يُفرّغ ما لا يخصّ النوع بالضبط، وموقعٌ يحمل الاثنين
 * يُقرأ ناقصاً في `label`. والسطرُ الذي لم يُختر له مخزن يُستبعد (وإنما يمنعه
 * `storageLocationIssues` قبل الإرسال أصلاً).
 */
export const storageLocationsPayload = (
  drafts: readonly StorageLocationDraft[],
): StorageLocationBody[] =>
  drafts
    .filter((draft) => draft.warehouse != null)
    .map((draft) => {
      const grid = draft.kind !== "code";
      return {
        warehouse: draft.warehouse as number,
        kind: grid ? "grid" : "code",
        column: grid ? draft.column.trim() : "",
        row: grid ? draft.row.trim() : "",
        code: grid ? "" : draft.code.trim(),
      };
    });

/** رسائلُ الرفض كلُّها، برسائل الخادم نفسها وترتيب السطور. */
export function storageLocationIssues(
  drafts: readonly StorageLocationDraft[],
): StorageLocationIssue[] {
  const issues: StorageLocationIssue[] = [];
  const seen = new Set<number>();
  drafts.forEach((draft, index) => {
    if (draft.warehouse == null) {
      issues.push({ index, field: "warehouse", message: "المخزن مطلوب لكل موقع" });
      return;
    }
    if (seen.has(draft.warehouse)) {
      const name = draft.warehouse_name.trim() || `#${draft.warehouse}`;
      issues.push({
        index, field: "warehouse",
        message: `المخزن «${name}» مكرَّر في القائمة — `
          + "موقعٌ واحد لكل منتجٍ في المخزن",
      });
      return;
    }
    seen.add(draft.warehouse);

    if (draft.kind === "code") {
      const code = draft.code.trim();
      if (!code) {
        issues.push({ index, field: "code", message: "رمز القسم مطلوب لنوع «رمز القسم»" });
      } else if (code.length > STORAGE_CODE_MAX) {
        issues.push({
          index, field: "code",
          message: `رمز القسم لا يزيد على ${STORAGE_CODE_MAX} حرفاً`,
        });
      }
      return;
    }

    const column = draft.column.trim();
    const row = draft.row.trim();
    if (!column) {
      issues.push({ index, field: "column", message: "عمود الموقع مطلوب لنوع «عمود وصف»" });
    } else if (column.length > STORAGE_COLUMN_MAX) {
      issues.push({
        index, field: "column",
        message: `العمود لا يزيد على ${STORAGE_COLUMN_MAX} حرفاً`,
      });
    }
    if (!row) {
      issues.push({ index, field: "row", message: "صفّ الموقع مطلوب لنوع «عمود وصف»" });
    } else if (row.length > STORAGE_ROW_MAX) {
      issues.push({
        index, field: "row",
        message: `الصف لا يزيد على ${STORAGE_ROW_MAX} حرفاً`,
      });
    }
  });
  return issues;
}

/** مفتاحُ المقارنة: الجسم نفسُه بمفتاح المخزن — فلا يهمّ ترتيبُ السطور. */
const payloadByWarehouse = (
  drafts: readonly StorageLocationDraft[],
): Map<number, StorageLocationBody> =>
  new Map(storageLocationsPayload(drafts).map((row) => [row.warehouse, row]));

/**
 * هل تغيّر شيء عمّا حُمِّل؟ `PUT` يستبدل القائمة كاملةً، فلا تُكلَّف كتابةٌ
 * لم تحدث — وترتيبُ السطور وحدَه ليس تغييراً (الحذف والإضافة يعيدان الترتيب
 * بلا أن يختلف موقع).
 */
export function storageLocationsChanged(
  before: readonly StorageLocationDraft[],
  after: readonly StorageLocationDraft[],
): boolean {
  const saved = payloadByWarehouse(before);
  const edited = payloadByWarehouse(after);
  if (saved.size !== edited.size) return true;
  for (const [warehouse, row] of saved) {
    const other = edited.get(warehouse);
    if (
      other == null
      || other.kind !== row.kind
      || other.column !== row.column
      || other.row !== row.row
      || other.code !== row.code
    ) {
      return true;
    }
  }
  return false;
}

/**
 * خياراتُ قائمة المخزن في سطر: الفعّالة، زائدَ المخزن المختار في السطر نفسه ولو
 * صار معطَّلاً (كي لا يُمحى ما هو محفوظٌ بمجرّد فتح الكرت)، ناقصَ ما اختاره
 * سطرٌ آخر — موقعٌ واحد لكل منتجٍ في المخزن.
 */
export function storageWarehouseChoices(
  warehouses: readonly WarehouseOption[],
  drafts: readonly StorageLocationDraft[],
  index: number,
): WarehouseOption[] {
  const taken = new Set<number>();
  drafts.forEach((draft, i) => {
    if (i !== index && draft.warehouse != null) taken.add(draft.warehouse);
  });
  const current = drafts[index]?.warehouse ?? null;
  return warehouses.filter(
    (warehouse) => (warehouse.is_active !== false || warehouse.id === current)
      && !taken.has(warehouse.id),
  );
}

/** المخزن المقترح لسطرٍ جديد: الافتراضي إن كان حراً، وإلّا أوّلُ مخزنٍ حرّ. */
export function nextStorageWarehouse(
  warehouses: readonly WarehouseOption[],
  drafts: readonly StorageLocationDraft[],
): WarehouseOption | null {
  const free = storageWarehouseChoices(warehouses, drafts, -1);
  return free.find((warehouse) => warehouse.is_default) ?? free[0] ?? null;
}
