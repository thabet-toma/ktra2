/**
 * شجرة الحسابات كما تُعرض في أي نافذة اختيار حساب — مصدر واحد للترتيب والطيّ
 * والبحث. كان كل موضع يعرض الحسابات قائمةً مسطّحة يختلط فيها الأب بالابن بلا
 * ترتيب، فيستحيل معرفة موقع الحساب في الشجرة قبل اختياره.
 * يستهلكه `AccountTreePicker` وحقول اختيار الحساب في كل الشاشات.
 */

/**
 * الحدّ الأدنى الذي تحتاجه الشجرة. الحقول اختيارية عمداً: كل شاشة تعرّف نوع
 * الحساب على هواها (`code?: string` هنا، `code: string | null` هناك)، ولو
 * شدّدناها لَما قبِلَ الحقلُ نصفَ الشاشات.
 */
export interface AccountNodeLike {
  id: number;
  code?: string | null;
  name?: string | null;
  parent?: number | null;
  account_type?: string | null;
  is_active?: boolean;
}

export interface AccountTreeRow<T extends AccountNodeLike> {
  account: T;
  depth: number;
  hasChildren: boolean;
  expanded: boolean;
}

export interface AccountIndex<T extends AccountNodeLike> {
  byId: Map<number, T>;
  /** أبناء كل حساب مرتّبين بالكود؛ مفتاح `null` = الجذور. */
  childrenOf: Map<number | null, T[]>;
}

const codeOf = (a: AccountNodeLike): string => String(a.code ?? '');

/**
 * فهرس الشجرة. الحساب الذي غاب أبوه عن القائمة (تصفية جزئية من الخادم) يُعامَل
 * جذراً — وإلا اختفى من الشجرة كلها ولم يعد قابلاً للاختيار.
 */
export const buildAccountIndex = <T extends AccountNodeLike>(
  accounts: T[],
): AccountIndex<T> => {
  const byId = new Map<number, T>();
  for (const a of accounts) byId.set(a.id, a);

  const childrenOf = new Map<number | null, T[]>();
  for (const a of accounts) {
    const parent = a.parent != null && byId.has(a.parent) ? a.parent : null;
    const list = childrenOf.get(parent);
    if (list) list.push(a);
    else childrenOf.set(parent, [a]);
  }
  for (const list of childrenOf.values()) {
    list.sort((x, y) => codeOf(x).localeCompare(codeOf(y), 'en'));
  }
  return { byId, childrenOf };
};

/** معرّفات آباء الحساب من الأقرب إلى الجذر — لفتح الشجرة على الحساب المختار. */
export const ancestorIdsOf = <T extends AccountNodeLike>(
  index: AccountIndex<T>,
  accountId: number | null | undefined,
): number[] => {
  const out: number[] = [];
  if (accountId == null) return out;
  let cur = index.byId.get(accountId)?.parent ?? null;
  // حارس ضد حلقة أبوّة معطوبة في البيانات — لا نعلّق الواجهة.
  const seen = new Set<number>();
  while (cur != null && index.byId.has(cur) && !seen.has(cur)) {
    seen.add(cur);
    out.push(cur);
    cur = index.byId.get(cur)?.parent ?? null;
  }
  return out;
};

/** مطابقة البحث: الكود أو الاسم (بلا حساسية لحالة الأحرف). */
export const matchesAccountQuery = (a: AccountNodeLike, query: string): boolean => {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return `${codeOf(a)} ${a.name ?? ''}`.toLowerCase().includes(needle);
};

/**
 * معرّفات الحسابات المطابقة للبحث مع كل آبائها — الأب يظهر ليُرى موقع الابن
 * في الشجرة حتى لو لم يطابق هو نفسه.
 */
export const searchMatchIds = <T extends AccountNodeLike>(
  accounts: T[],
  index: AccountIndex<T>,
  query: string,
): Set<number> => {
  const keep = new Set<number>();
  for (const a of accounts) {
    if (!matchesAccountQuery(a, query)) continue;
    keep.add(a.id);
    for (const id of ancestorIdsOf(index, a.id)) keep.add(id);
  }
  return keep;
};

export interface VisibleRowsOptions {
  /** نص البحث؛ حين لا يكون فارغاً تُفتح الفروع المطابقة كلها. */
  query?: string;
  /** الفروع المفتوحة يدوياً (تُتجاهل أثناء البحث). */
  expanded?: ReadonlySet<number>;
}

/**
 * صفوف الشجرة الظاهرة بالترتيب (أب ثم أبناؤه) مع عمق كل صف.
 * أثناء البحث تُعرض المطابقات وآباؤها مفتوحةً كلها.
 */
export const visibleAccountRows = <T extends AccountNodeLike>(
  accounts: T[],
  index: AccountIndex<T>,
  { query = '', expanded }: VisibleRowsOptions = {},
): AccountTreeRow<T>[] => {
  const searching = query.trim().length > 0;
  const keep = searching ? searchMatchIds(accounts, index, query) : null;
  const rows: AccountTreeRow<T>[] = [];

  const walk = (parentId: number | null, depth: number) => {
    for (const account of index.childrenOf.get(parentId) ?? []) {
      if (keep && !keep.has(account.id)) continue;
      const children = index.childrenOf.get(account.id) ?? [];
      const hasChildren = keep
        ? children.some((c) => keep.has(c.id))
        : children.length > 0;
      const isOpen = searching ? true : !!expanded?.has(account.id);
      rows.push({ account, depth, hasChildren, expanded: hasChildren && isOpen });
      if (hasChildren && isOpen) walk(account.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
};

/** جذور النقدية في الشجرة المعيارية: النقدية، البنوك، صناديق النقدية. */
const CASH_CODE_ROOTS = ['1101', '1102', '1110'];

/**
 * هل يصلح الحساب صندوقاً/بنكاً؟ كان لكل شاشة نسختها من هذا الشرط (وثلاث منها
 * تختلف عن بعضها) فيظهر الصندوق في سند ويغيب عن سند. والشرط القديم `^110`
 * كان يبتلع 1103 المدينون و1104 المخزون و1105 الضريبة — حسابات لا تُدفع منها.
 */
export const isCashAccount = (a: AccountNodeLike): boolean => {
  const type = (a.account_type || '').toLowerCase();
  if (type === 'cash' || type === 'bank') return true;
  if (type !== 'asset') return false;
  const code = codeOf(a);
  if (CASH_CODE_ROOTS.some((root) => code.startsWith(root))) return true;
  return /صندوق|بنك|نقدية|cash|bank/i.test(a.name ?? '');
};

/** أنواع الحسابات ذات الطبيعة المدينة؛ البقية دائنة. */
const DEBIT_TYPES = ['asset', 'expense'];
/** أنواع حسابات الميزانية؛ البقية تُقفَل في الأرباح والخسائر. */
const BALANCE_TYPES = ['asset', 'liability', 'equity'];

const knownType = (a: AccountNodeLike): string | null => {
  const type = (a.account_type || '').toLowerCase();
  return DEBIT_TYPES.includes(type) || BALANCE_TYPES.includes(type) || type === 'revenue'
    ? type
    : null;
};

/**
 * طبيعة الحساب (مدين/دائن) مشتقّة من نوعه — لا تُدخَل يدوياً. كانت بطاقة الحساب
 * تعرض النوع وحده، والمستخدم يحتاج أن يعرف أين يقع الحساب في القيد.
 */
export const accountNature = (a: AccountNodeLike): 'debit' | 'credit' | null => {
  const type = knownType(a);
  if (!type) return null;
  return DEBIT_TYPES.includes(type) ? 'debit' : 'credit';
};

/** الحساب الختامي: ميزانية (يُرحَّل رصيده) أو أرباح وخسائر (يُقفَل آخر السنة). */
export const accountStatement = (a: AccountNodeLike): 'balance' | 'income' | null => {
  const type = knownType(a);
  if (!type) return null;
  return BALANCE_TYPES.includes(type) ? 'balance' : 'income';
};

/** مسار الحساب من الجذر إليه (شاملاً إياه) — لعرض موقعه في الشجرة نصّاً. */
export const accountPath = <T extends AccountNodeLike>(
  index: AccountIndex<T>,
  accountId: number | null | undefined,
): T[] => {
  if (accountId == null) return [];
  const self = index.byId.get(accountId);
  if (!self) return [];
  const parents = ancestorIdsOf(index, accountId)
    .map((id) => index.byId.get(id))
    .filter((a): a is T => !!a)
    .reverse();
  return [...parents, self];
};

/**
 * الكود المقترح لحساب جديد تحت أبٍ ما (`null` = جذر جديد): يكمل تسلسل الإخوة
 * بنفس طولهم، وبلا إخوةٍ يبني على كود الأب. يعود فارغاً حين يتعذّر الاستنتاج
 * بثقة (أكواد غير رقمية أو إخوة بأطوال مختلفة) — اقتراحٌ خاطئ أسوأ من لا اقتراح.
 */
export const nextChildCode = <T extends AccountNodeLike>(
  index: AccountIndex<T>,
  parentId: number | null,
): string => {
  const siblings = (index.childrenOf.get(parentId) ?? [])
    .map(codeOf)
    .filter((c) => /^\d+$/.test(c));
  if (siblings.length > 0) {
    const width = siblings[0].length;
    if (!siblings.every((c) => c.length === width)) return '';
    const next = Math.max(...siblings.map((c) => Number(c))) + 1;
    const out = String(next).padStart(width, '0');
    return out.length === width ? out : '';
  }
  if (parentId == null) return '';
  const parentCode = codeOf(index.byId.get(parentId) ?? ({} as AccountNodeLike));
  return /^\d+$/.test(parentCode) ? `${parentCode}01` : '';
};

/** تسمية الحساب في الحقل المغلق: «الكود — الاسم». */
export const accountLabel = (a: AccountNodeLike | null | undefined): string => {
  if (!a) return '';
  const code = codeOf(a).trim();
  const name = (a.name ?? '').trim();
  return code && name ? `${code} — ${name}` : code || name;
};
