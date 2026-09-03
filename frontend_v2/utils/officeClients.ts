import type { PracticeClientRecord } from '../services/accountantPracticeApi';
import type { EngagementStatus, WorkspaceCompany } from '../types/accountant';

/**
 * B3 — «زبائني» قائمةٌ واحدة من مصدرين، **دمجاً على الواجهة لا على الجدول**:
 * الارتباطات (`AccountantEngagement` — شركة حقيقية على المنصة بدفاترها) وسجل
 * المكتب (`PracticeClient` — زبون أدخله المحاسب يدوياً). الجدار بينهما يبقى كما
 * هو في الخادم؛ ما يُوحَّد هنا هو ما يراه المحاسب، فزبونه زبونٌ واحد سواء كانت
 * دفاتره عندنا أم لا.
 *
 * الزبون المربوط (`engagement_id` غير فارغ) **صفٌّ واحد لا صفّان**: هو الشركة
 * نفسها، وله عندها بابان — دفاترها على المنصة، وملفه في المكتب.
 *
 * دوالّ صرفة (لا React ولا شبكة) كي تُختبر وحدها.
 */
export type OfficeClientKind = 'platform' | 'external';
export type OfficeClientGroup = 'open' | 'pending' | 'archived';

export interface OfficeClientRow {
  /** مفتاح العرض — فريد عبر المصدرين معاً. */
  key: string;
  kind: OfficeClientKind;
  group: OfficeClientGroup;
  name: string;
  /** شركة المنصة إن وُجدت — بها يُفتح ملف الدفاتر القائم. */
  tenantId: number | null;
  engagementId: number | null;
  /** صفّ سجل المكتب إن وُجد — به يُفتح ملف الزبون الخارجي. */
  practiceId: number | null;
  /** حالة الارتباط لصفوف المنصة، وحالة السجل لصفوف المكتب. */
  engagementStatus: EngagementStatus | null;
  /** هل دفاتر الشركة مفتوحة فعلاً (ارتباط نشط)؟ */
  accessible: boolean;
  sector: string;
  taxNumber: string;
  phone: string;
  hint: string;
}

export const OFFICE_CLIENT_BADGES: Record<OfficeClientKind, string> = {
  platform: 'على المنصة',
  external: 'خارجي',
};

export const OFFICE_CLIENT_BADGE_TONES: Record<OfficeClientKind, string> = {
  platform: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200',
  external: 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
};

const GROUP_ORDER: Record<OfficeClientGroup, number> = { open: 0, pending: 1, archived: 2 };

const contactName = (client: PracticeClientRecord) =>
  [client.contact_first, client.contact_last].filter(Boolean).join(' ');

/**
 * سببُ إغلاق الملف لا «مغلق» وحدها: ارتباطٌ نشط على شركة لم تفعّل وحدة البوابة
 * ليس بانتظار موافقة أحد — قول ذلك يمنع المحاسب من انتظار ردٍّ لن يأتي.
 */
export function platformHint(company: WorkspaceCompany): string {
  if (!company.accessible) {
    return company.status === 'active'
      ? 'الشركة لم تفعّل وحدة بوابة المحاسب — دفاترها لا تُفتح حتى تفعّلها.'
      : 'بانتظار موافقة الشركة — الملف لا يُفتح قبلها.';
  }
  return company.last_period
    ? `آخر فترة مُراجَعة: ${company.last_period.period_from} → ${company.last_period.period_to}`
    : 'لم تُراجَع أي فترة بعد';
}

const externalHint = (client: PracticeClientRecord) => {
  const parts = [contactName(client), client.sector, client.mobile || client.phone].filter(Boolean);
  return parts.length > 0 ? parts.join(' · ') : 'لا بيانات اتصال بعد';
};

/**
 * يدمج المصدرين في قائمة واحدة مرتّبة: المفتوح ثم المعلّق ثم المؤرشف، وداخل كل
 * مجموعة ترتيب أبجدي عربي.
 *
 * المؤرشفون **لا يُحذفون من القائمة** — يُجمعون في آخرها كي يبقى الاسترجاع
 * ممكناً؛ الأرشفة ليست طريقاً مسدوداً (مراجعة 2 من ISSUE #86: حالة طبقة
 * المكتب، لا الطرف — انظر `PracticeClientRecord.status`).
 */
export function mergeOfficeClients(
  engagements: WorkspaceCompany[],
  practiceClients: PracticeClientRecord[],
): OfficeClientRow[] {
  const linked = new Map<number, PracticeClientRecord>();
  for (const client of practiceClients) {
    if (client.engagement_id !== null) linked.set(client.engagement_id, client);
  }

  const rows: OfficeClientRow[] = engagements.map((company) => {
    const record = linked.get(company.engagement_id);
    return {
      key: `engagement-${company.engagement_id}`,
      kind: 'platform',
      group: company.accessible ? 'open' : 'pending',
      name: record?.trade_name || company.company_name,
      tenantId: company.tenant_id,
      engagementId: company.engagement_id,
      practiceId: record?.id ?? null,
      engagementStatus: company.status,
      accessible: company.accessible,
      sector: record?.sector || '',
      taxNumber: record?.tax_number || '',
      phone: record?.mobile || record?.phone || '',
      hint: platformHint(company),
    };
  });

  const seenEngagements = new Set(engagements.map((company) => company.engagement_id));
  for (const client of practiceClients) {
    // ارتباطٌ لم يصل في قائمة الشركات (مُلغى مثلاً) لا يبتلع صفّ الزبون: يبقى
    // ظاهراً كملف مكتب، وإلا اختفى زبونٌ من القائمة لأن شركته ألغت الارتباط.
    if (client.engagement_id !== null && seenEngagements.has(client.engagement_id)) continue;
    rows.push({
      key: `practice-${client.id}`,
      kind: 'external',
      group: client.status === 'archived' ? 'archived' : 'open',
      name: client.trade_name,
      tenantId: client.tenant_id,
      engagementId: client.engagement_id,
      practiceId: client.id,
      engagementStatus: null,
      accessible: false,
      sector: client.sector,
      taxNumber: client.tax_number,
      phone: client.mobile || client.phone,
      hint: externalHint(client),
    });
  }

  return rows.sort((left, right) => {
    const byGroup = GROUP_ORDER[left.group] - GROUP_ORDER[right.group];
    return byGroup !== 0 ? byGroup : left.name.localeCompare(right.name, 'ar');
  });
}

/** تصفية محلية فوق البحث الخادمي — كي لا يومض الجدول بين ضغطتَي مفتاح. */
export function filterOfficeClients(rows: OfficeClientRow[], search: string): OfficeClientRow[] {
  const needle = search.trim().toLowerCase();
  if (!needle) return rows;
  return rows.filter((row) =>
    [row.name, row.sector, row.taxNumber, row.phone]
      .some((value) => value.toLowerCase().includes(needle)));
}
