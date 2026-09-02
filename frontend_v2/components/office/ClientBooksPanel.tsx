import React, { useState } from 'react';
import { BookOpenCheck, Building2, Loader2, Plus } from 'lucide-react';

import { useCompany } from '../../contexts/CompanyContext';
import { useToast } from '../../contexts/ToastContext';
import { COMPANY_TEMPLATES, DEFAULT_COMPANY_TEMPLATE, companyTemplateByKey } from '../../utils/companyTemplates';
import { formatDateValue } from '../../utils/formatDate';

/**
 * ISSUE #65 — «دفاتر عملائي»: البابُ الذي كان ناقصاً.
 *
 * المحرّك كامل منذ #52 (`Tenant.managed_by`، نقطة `managed-books`، حصّة الخطة،
 * وصول مدير المكتب) وبلا مستدعٍ واحد في الواجهة — فكان صاحب المكتب يستطيع أن
 * يُصدر فاتورة أتعاب لزبونه ولا يستطيع أن يمسك دفاتره.
 *
 * لوحة واحدة تُركَّب في القشرتين: قشرة المحاسب القانوني (`/office`) وقائمةُ
 * شركةٍ بقالب مكتب محاسبة. **القالب الافتراضي للدفتر `general` لا قالب المكتب**:
 * الزبون محلٌّ تجاري له مخزون ومشتريات، والقالب المحاسبي وُضع لمكتبٍ لا لزبونه.
 */
export const ClientBooksPanel: React.FC = () => {
  const toast = useToast();
  const {
    managedBooks,
    officeTenantId,
    openManagedBook,
    createManagedBook,
    loading,
  } = useCompany();
  const [opening, setOpening] = useState(false);
  const [name, setName] = useState('');
  const [template, setTemplate] = useState<string>(DEFAULT_COMPANY_TEMPLATE);
  const [saving, setSaving] = useState(false);

  if (officeTenantId === null) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
        هذه الشاشة لمكاتب المحاسبة: تظهر لمن يدير شركةً أُنشئت بقالب «مكتب محاسبة».
      </div>
    );
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      toast('اكتب اسم الدفتر أولاً.', 'error');
      return;
    }
    setSaving(true);
    try {
      const book = await createManagedBook(trimmed, template);
      toast(`فُتح دفتر «${book.CompanyName}». ادخل إليه لتبدأ إدخال فواتيره.`, 'success');
      setName('');
      setOpening(false);
    } catch (caught) {
      // رسالة الحصّة تصل من الخادم كما هي («بلغتَ حدّ …») — تُعرض لا تُستبدل.
      toast((caught as Error).message || 'تعذّر فتح الدفتر.', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-black text-slate-900 dark:text-white">دفاتر عملائي</h2>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            دفترٌ مستقلٌّ لكل زبون تمسك حساباته: تدخل إليه فتُدخل فواتيره ومشترياته
            كأنك فيه، وتعود إلى مكتبك بزرّ واحد. الدفاتر لا تظهر في مبدّل الشركات.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpening((prev) => !prev)}
          className="flex items-center gap-2 rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white"
        >
          <Plus className="h-4 w-4" />افتح دفتراً جديداً
        </button>
      </div>

      {opening && (
        <form onSubmit={submit} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-xs font-bold text-slate-500 dark:text-slate-400">اسم الدفتر</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="اسم الزبون التجاري"
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800"
              />
            </label>
            <label className="block">
              <span className="text-xs font-bold text-slate-500 dark:text-slate-400">قالب الدفتر</span>
              <select
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800"
              >
                {COMPANY_TEMPLATES.map((item) => (
                  <option key={item.key} value={item.key}>{item.name}</option>
                ))}
              </select>
            </label>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {companyTemplateByKey(template)?.description}
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded-xl bg-emerald-600 px-5 py-2.5 font-bold text-white disabled:opacity-60"
            >
              {saving ? 'جارٍ الفتح…' : 'افتح الدفتر'}
            </button>
            <button
              type="button"
              onClick={() => setOpening(false)}
              className="rounded-xl border border-slate-300 px-5 py-2.5 font-bold dark:border-slate-700"
            >
              إلغاء
            </button>
          </div>
        </form>
      )}

      {loading && managedBooks.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" />جارٍ تحميل الدفاتر…
        </p>
      ) : managedBooks.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
          لا دفاتر بعد. افتح دفتراً لأول زبون تمسك حساباته.
        </p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {managedBooks.map((book) => (
            <li
              key={book.TenantID}
              className="flex flex-col justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
            >
              <div>
                <p className="flex items-center gap-2 font-black text-slate-900 dark:text-white">
                  <Building2 className="h-4 w-4 text-indigo-600" />{book.CompanyName}
                </p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  {companyTemplateByKey(book.template || '')?.name || 'عام / تجاري'}
                  {' · '}فُتح في {formatDateValue(book.CreatedAt)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => openManagedBook(book.TenantID)}
                className="flex items-center justify-center gap-2 rounded-xl bg-indigo-700 px-4 py-2 font-bold text-white"
              >
                <BookOpenCheck className="h-4 w-4" />ادخل إلى الدفتر
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default ClientBooksPanel;
