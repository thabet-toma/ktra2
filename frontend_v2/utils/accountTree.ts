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
  /** التصنيف الوظيفي المخزَّن في الخادم (`Account.sub_type`) حين تعرضه الشاشة. */
  sub_type?: string | null;
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

/**
 * معرّفات الحسابات القابلة للاختيار مع كل آبائها — بها تُقصّ الشجرة إلى فروع
 * الغرض وحدها: الأب غير المطابق يبقى ليُرى الموقع، وما ليس مطابقاً ولا أباً
 * لمطابق لا يُرسم إطلاقاً. نفس ميكانيكية `searchMatchIds`.
 */
export const selectableMatchIds = <T extends AccountNodeLike>(
  accounts: T[],
  index: AccountIndex<T>,
  isSelectable: (account: T) => boolean,
): Set<number> => {
  const keep = new Set<number>();
  for (const a of accounts) {
    if (!isSelectable(a)) continue;
    keep.add(a.id);
    for (const id of ancestorIdsOf(index, a.id)) keep.add(id);
  }
  return keep;
};

export interface VisibleRowsOptions<T extends AccountNodeLike = AccountNodeLike> {
  /** نص البحث؛ حين لا يكون فارغاً تُفتح الفروع المطابقة كلها. */
  query?: string;
  /** الفروع المفتوحة يدوياً (تُتجاهل أثناء البحث). */
  expanded?: ReadonlySet<number>;
  /**
   * شرط الانتقاء؛ حين يُمرَّر تُقصّ الشجرة إلى القابل للاختيار وآبائه.
   * غيابه = سلوك اليوم بالضبط: الشجرة كاملة.
   */
  isSelectable?: (account: T) => boolean;
}

/**
 * صفوف الشجرة الظاهرة بالترتيب (أب ثم أبناؤه) مع عمق كل صف.
 * أثناء البحث تُعرض المطابقات وآباؤها مفتوحةً كلها، ومع شرط انتقاء تُقصّ الشجرة
 * إلى فروعه — والقصّان يتقاطعان حين يجتمعان.
 */
export const visibleAccountRows = <T extends AccountNodeLike>(
  accounts: T[],
  index: AccountIndex<T>,
  { query = '', expanded, isSelectable }: VisibleRowsOptions<T> = {},
): AccountTreeRow<T>[] => {
  const searching = query.trim().length > 0;
  const searchKeep = searching ? searchMatchIds(accounts, index, query) : null;
  // صفر حساب قابل للاختيار ⇒ لا قصّ: شجرة فارغة طريق مسدود لا يخرج منه المستخدم.
  const selectableKeep = isSelectable
    ? selectableMatchIds(accounts, index, isSelectable)
    : null;
  const pruneKeep = selectableKeep && selectableKeep.size > 0 ? selectableKeep : null;
  const keep =
    searchKeep && pruneKeep
      ? new Set([...searchKeep].filter((id) => pruneKeep.has(id)))
      : searchKeep ?? pruneKeep;
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

/**
 * غرض الحقل الذي يُملأ: مصدر واحد لسؤال «أي الحسابات تصلح هنا؟». كانت كل شاشة
 * تعرّف الشرط بنفسها فتختلف الإجابة للحقل الواحد بين شاشة وأخرى.
 */
export type AccountPurpose =
  | 'cash' | 'bank' | 'receivable' | 'payable' | 'inventory'
  | 'asset' | 'liability' | 'equity' | 'revenue' | 'expense'
  | 'any';

/** الأغراض التي يجيب عنها التصنيف الوظيفي المخزَّن؛ البقية من `account_type`. */
const PURPOSE_SUB_TYPES: Record<string, string[]> = {
  cash: ['cash_box', 'bank'],
  bank: ['bank'],
  receivable: ['receivable'],
  payable: ['payable'],
  inventory: ['inventory'],
};

/** جذور النقدية في الشجرة المعيارية: النقدية، البنوك، صناديق النقدية. */
const CASH_CODE_ROOTS = ['1101', '1102', '1110'];

/**
 * الشرط القديم للصندوق — يبقى للحساب الذي لم يصنّفه الخادم بعد (شركة لم يمرّ
 * عليها الاشتقاق، أو شاشة لا تجلب `sub_type`). الشرط `^110` الأقدم كان يبتلع
 * 1103 المدينون و1104 المخزون و1105 الضريبة — حسابات لا تُدفع منها.
 */
const looksLikeCash = (a: AccountNodeLike): boolean => {
  const type = (a.account_type || '').toLowerCase();
  if (type === 'cash' || type === 'bank') return true;
  if (type !== 'asset') return false;
  const code = codeOf(a);
  if (CASH_CODE_ROOTS.some((root) => code.startsWith(root))) return true;
  return /صندوق|بنك|نقدية|cash|bank/i.test(a.name ?? '');
};

/**
 * هل يصلح الحساب لهذا الغرض؟ التصنيف المخزَّن هو الحجّة الأولى — وهو ما يجعل
 * «صندوق العهدة» المصنَّف مخزوناً لا يظهر في حقل الصندوق مهما كان اسمه.
 * تقبل مصفوفة للحقول المركّبة (رسوم الشراء = مصروف أو أصل).
 */
export const accountMatchesPurpose = (
  a: AccountNodeLike,
  purpose: AccountPurpose | readonly AccountPurpose[],
): boolean => {
  if (Array.isArray(purpose)) return purpose.some((p) => accountMatchesPurpose(a, p));
  const one = purpose as AccountPurpose;
  if (one === 'any') return true;
  const wanted = PURPOSE_SUB_TYPES[one];
  if (!wanted) return (a.account_type || '').toLowerCase() === one;
  const sub = (a.sub_type || '').toLowerCase();
  if (sub) return wanted.includes(sub);
  // بلا تصنيف مخزَّن: للنقدية وحدها شرطٌ قديم مشترك نسقط إليه، وبقية الأغراض
  // لا جواب لها إلا التصنيف — والشجرة الكاملة (fallback المنتقي) تنقذ المستخدم.
  return one === 'cash' ? looksLikeCash(a) : false;
};

/**
 * هل يصلح الحساب صندوقاً/بنكاً؟ يبقى الشرط المشترك حتى تسحبه الشاشات إلى
 * `purpose="cash"`.
 */
export const isCashAccount = (a: AccountNodeLike): boolean =>
  accountMatchesPurpose(a, 'cash');

export interface AccountSelectableOptions<T extends AccountNodeLike> {
  /** غرض الحقل؛ غيابه يعني أن الشاشة لم تصرّح بشرط. */
  purpose?: AccountPurpose | readonly AccountPurpose[];
  /**
   * السماح باختيار حساب أب — لفلاتر التقارير ودفتر الأستاذ: هي تختار نطاق عرض
   * لا هدف ترحيل. الافتراضي `false`: الترحيل لا يقع إلا على ورقة.
   */
  allowParents?: boolean;
  /** شرط خاص بالشاشة (قائمة يحدّدها الخادم مثلاً) يُركَّب فوق الافتراضي. */
  isSelectable?: (account: T) => boolean;
}

/**
 * شرط الانتقاء الواحد للمنتقي: مطابقٌ للغرض ونشطٌ وورقة، وفوقه شرط الشاشة إن
 * وُجد. يعود `undefined` حين لا شرط أصلاً — فيبقى كل شيء قابلاً للاختيار وتُعرض
 * الشجرة كاملة، أي سلوك اليوم بلا تغيير.
 */
export const buildAccountSelectable = <T extends AccountNodeLike>(
  index: AccountIndex<T>,
  { purpose, allowParents = false, isSelectable }: AccountSelectableOptions<T> = {},
): ((account: T) => boolean) | undefined => {
  if (!purpose && !isSelectable) return undefined;
  return (account: T) => {
    if (isSelectable && !isSelectable(account)) return false;
    if (!purpose) return true;
    if (!accountMatchesPurpose(account, purpose)) return false;
    if (account.is_active === false) return false;
    if (!allowParents && (index.childrenOf.get(account.id)?.length ?? 0) > 0) return false;
    return true;
  };
};

/**
 * شرط الانتقاء الفعليّ بعد قياسه على الحسابات الحاضرة — وهو ما تستعمله الشاشات.
 *
 * `buildAccountSelectable` يصف الشرط المثالي؛ هذه تتحقّق أن له مطابقاً واحداً
 * على الأقل. حين لا يطابقه شيء — شركة لم يصنّف الخادم شجرتها بعد — يسقط الغرض
 * ويبقى شرط الشاشة وحده. بدون هذا السقوط كانت الشجرة تُعرض كاملة (لأن القصّ
 * يتعطّل) بينما يبقى الانتقاء على شرط الغرض، فيرى المستخدم كل حساباته ولا
 * يستطيع اختيار واحد: طريق مسدود يراه ولا يفهمه.
 *
 * شرط الشاشة لا يسقط أبداً: قائمةٌ يحدّدها الخادم تبقى ملزِمة ولو خلت.
 */
export const resolveAccountSelectable = <T extends AccountNodeLike>(
  accounts: readonly T[],
  index: AccountIndex<T>,
  options: AccountSelectableOptions<T> = {},
): ((account: T) => boolean) | undefined => {
  const strict = buildAccountSelectable(index, options);
  if (!strict || accounts.some(strict)) return strict;
  return buildAccountSelectable(index, { isSelectable: options.isSelectable });
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
