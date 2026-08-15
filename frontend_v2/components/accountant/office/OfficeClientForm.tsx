import React, { useState } from 'react';

import {
  createPracticeClient,
  updatePracticeClient,
  type PracticeClientRecord,
} from '../../../services/accountantPracticeApi';
import { useToast } from '../../../contexts/ToastContext';
import { OfficeField, OfficeInput, OfficeModal, OfficeTextarea } from './OfficeUi';

/**
 * «إضافة زبون» — الحقول التي يتوقّعها مكتب المحاسبة عند فتح ملفٍ جديد: الاسم
 * التجاري وحده إلزامي، والباقي يُملأ متى عُرف. النموذج نفسه يخدم التعديل، فلا
 * تُكتب قواعد الحقول مرتين.
 */
export type OfficeClientDraft = Partial<PracticeClientRecord>;

const FIELDS: { key: keyof PracticeClientRecord; label: string; type?: string }[] = [
  { key: 'contact_first', label: 'الاسم الأول' },
  { key: 'contact_last', label: 'الاسم الأخير' },
  { key: 'phone', label: 'الهاتف', type: 'tel' },
  { key: 'mobile', label: 'الجوال', type: 'tel' },
  { key: 'email', label: 'البريد الإلكتروني', type: 'email' },
  { key: 'sector', label: 'القطاع' },
  { key: 'tax_number', label: 'الرقم الضريبي' },
];

export const OfficeClientForm: React.FC<{
  client?: PracticeClientRecord;
  onClose: () => void;
  onSaved: (client: PracticeClientRecord) => void;
}> = ({ client, onClose, onSaved }) => {
  const toast = useToast();
  const [draft, setDraft] = useState<OfficeClientDraft>({
    trade_name: client?.trade_name || '',
    contact_first: client?.contact_first || '',
    contact_last: client?.contact_last || '',
    phone: client?.phone || '',
    mobile: client?.mobile || '',
    email: client?.email || '',
    address: client?.address || '',
    sector: client?.sector || '',
    tax_number: client?.tax_number || '',
    notes: client?.notes || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (key: keyof PracticeClientRecord, value: string) =>
    setDraft((current) => ({ ...current, [key]: value }));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!String(draft.trade_name || '').trim()) {
      setError('الاسم التجاري مطلوب.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const response = client
        ? await updatePracticeClient(client.id, draft)
        : await createPracticeClient(draft);
      toast(client ? 'حُفظت بيانات الزبون.' : `أُضيف الزبون «${response.client.trade_name}».`, 'success');
      onSaved(response.client);
    } catch (caught) {
      // رسالة الخادم عربية جاهزة (`{code, detail}`) — تُعرض كما هي، فهي أدقّ من أي
      // نص عامّ: «يوجد زبون بهذا الاسم» ≠ «تعذّر الحفظ».
      setError((caught as Error).message || 'تعذّر حفظ بيانات الزبون.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <OfficeModal
      title={client ? `تعديل بيانات ${client.trade_name}` : 'إضافة زبون'}
      onClose={onClose}
      wide
      footer={(
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-slate-300 px-5 py-2.5 font-bold dark:border-slate-700">
            إلغاء
          </button>
          <button
            type="submit"
            form="office-client-form"
            disabled={saving}
            className="rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white disabled:opacity-50"
          >
            {saving ? 'جارٍ الحفظ…' : 'حفظ'}
          </button>
        </>
      )}
    >
      <form id="office-client-form" onSubmit={submit} className="space-y-4">
        {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">{error}</p>}

        <OfficeField label="الاسم التجاري" required hint="اسم الزبون كما يُعرف في مراسلاته — وهو وحده الإلزامي.">
          {(id) => (
            <OfficeInput
              id={id}
              value={draft.trade_name || ''}
              onChange={(event) => set('trade_name', event.target.value)}
              autoFocus
            />
          )}
        </OfficeField>

        <div className="grid gap-4 sm:grid-cols-2">
          {FIELDS.map((field) => (
            <OfficeField key={String(field.key)} label={field.label}>
              {(id) => (
                <OfficeInput
                  id={id}
                  type={field.type}
                  value={String(draft[field.key] ?? '')}
                  onChange={(event) => set(field.key, event.target.value)}
                />
              )}
            </OfficeField>
          ))}
        </div>

        <OfficeField label="العنوان">
          {(id) => (
            <OfficeTextarea
              id={id}
              rows={2}
              value={draft.address || ''}
              onChange={(event) => set('address', event.target.value)}
            />
          )}
        </OfficeField>

        <OfficeField label="ملاحظات">
          {(id) => (
            <OfficeTextarea
              id={id}
              rows={3}
              value={draft.notes || ''}
              onChange={(event) => set('notes', event.target.value)}
            />
          )}
        </OfficeField>
      </form>
    </OfficeModal>
  );
};

export default OfficeClientForm;
