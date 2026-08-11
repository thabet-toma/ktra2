/**
 * توليد بيان القيد تلقائياً من الحسابات — كما في البرامج المحاسبية المهنية.
 *
 * القاعدة المهنية: المستخدم لا يكتب البيان يدوياً في الحالة العادية؛ البيان
 * الإجمالي يُشتقّ من طرفَي القيد بصيغة «من ح/ … إلى ح/ …»، وبيان كل سطر يُشتقّ
 * من حسابه (وطرفه إن وُجد). أي كتابة يدوية تُصان ولا يدهسها التوليد.
 */

export type NarrationLine = {
  accountName: string;
  partnerName?: string;
  debit?: string | number;
  credit?: string | number;
};

const MAX_SIDE_ACCOUNTS = 2;

/** اسم الحساب كما يُقرأ في البيان — بلا اللاحقة اللاتينية «(Cash)» ولا الرمز. */
export function accountNarrationName(rawName: string): string {
  const name = String(rawName || '').trim();
  if (!name) return '';
  return name.replace(/\s*\([^)]*\)\s*$/, '').trim() || name;
}

const hasAmount = (v: string | number | undefined): boolean =>
  Math.abs(parseFloat(String(v ?? '')) || 0) > 0;

const isActive = (l: NarrationLine): boolean =>
  !!accountNarrationName(l.accountName) && (hasAmount(l.debit) || hasAmount(l.credit));

const joinSide = (names: string[]): string => {
  const shown = names.slice(0, MAX_SIDE_ACCOUNTS).join('، ');
  return names.length > MAX_SIDE_ACCOUNTS ? `${shown} وغيرها` : shown;
};

/** بيان السطر: البيان الإجمالي إن وُجد وإلا اسم الحساب، مع إلحاق اسم الطرف. */
export function buildLineNarration(line: NarrationLine, headerNarration: string): string {
  const account = accountNarrationName(line.accountName);
  if (!account) return '';
  const base = String(headerNarration || '').trim() || account;
  const partner = String(line.partnerName || '').trim();
  return partner ? `${base} — ${partner}` : base;
}

/** البيان الإجمالي: «من ح/ الحسابات المدينة إلى ح/ الحسابات الدائنة». */
export function buildHeaderNarration(lines: NarrationLine[]): string {
  const active = (lines || []).filter(isActive);
  const debits: string[] = [];
  const credits: string[] = [];
  for (const l of active) {
    const name = accountNarrationName(l.accountName);
    if (hasAmount(l.debit)) {
      if (!debits.includes(name)) debits.push(name);
    } else if (!credits.includes(name)) credits.push(name);
  }
  if (!debits.length || !credits.length) return '';
  return `من ح/ ${joinSide(debits)} إلى ح/ ${joinSide(credits)}`;
}

/** مثل `isGeneratedNarration` لكن لسطر واحد بالنظر إلى البيان الإجمالي. */
export function isGeneratedLineNarration(
  current: string,
  line: NarrationLine,
  headerNarration: string,
): boolean {
  const value = String(current || '').trim();
  if (!value) return true;
  if (value === buildLineNarration(line, headerNarration)) return true;
  // بيان إجمالي سابق تغيّر: يبقى السطر مولَّداً إن طابق حسابه/طرفه.
  return isGeneratedNarration(value, [line]);
}

/**
 * هل البيان الحالي مولَّد (فيجوز استبداله) أم كتبه المستخدم (فيُصان)؟
 * الفارغ مولَّد، وكذلك أي صيغة يعطيها المولّد نفسه لسطور القيد الحالية.
 */
export function isGeneratedNarration(current: string, lines: NarrationLine[]): boolean {
  const value = String(current || '').trim();
  if (!value) return true;
  if (value === buildHeaderNarration(lines)) return true;
  return (lines || []).some((l) => {
    const account = accountNarrationName(l.accountName);
    if (!account) return false;
    const partner = String(l.partnerName || '').trim();
    return value === account || (!!partner && value === `${account} — ${partner}`);
  });
}
