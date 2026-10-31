import React, { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import {
  createOfficeClient,
  getOfficeSettings,
  listOfficeClients,
  type OfficeClientRow,
  type OfficeSettingsPayload,
} from '../../services/accountingOfficeApi';
import {
  CLIENT_QUERY_PARAM,
  clientIdFromSearch,
  clientStatusBadgeClass,
  officeSizeOf,
  showsOfficeAssignment,
} from '../../utils/accountingOffice';
import { humanizeThrown } from '../../utils/drfError';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import { OfficeClientFile } from './OfficeClientFile';
import { OfficeFirstRunStep } from './OfficeFirstRunStep';
import {
  OfficeEmpty,
  OfficeError,
  OfficeSkeleton,
  officeInputClass,
  officePrimaryButtonClass,
} from './OfficeUi';

type StatusFilter = 'active' | 'ended' | 'all';

const FILTERS: { key: StatusFilter; label: string }[] = [
  { key: 'active', label: 'نشط' },
  { key: 'ended', label: 'منتهي' },
  { key: 'all', label: 'الكل' },
];

/**
 * ISSUE #271 — شاشة البداية لهذا القالب: قائمة الزبائن.
 *
 * **أول تشغيلٍ قبل القائمة**: ما دام نظامُ المكتب الضريبي أو حجمُه غير مختارٍ
 * تعرض الشاشةُ الخطوةَ لا جدولاً فارغاً — وإلا افتُتح المكتب على «لا زبائن» وهو
 * يظنّ أن عليه إضافة زبونٍ بينما الناقصُ إعدادٌ يخصّه هو.
 *
 * **والملفّ في العنوان لا في حالةٍ داخليّة**: `/accounting-office/clients?client=<id>`
 * — فالتحديث يُبقي الملفّ مفتوحاً، وزرُّ الرجوع في المتصفح يعود إلى القائمة،
 * ورابطُ الزبون من شاشة الإعدادات يفتح ملفّه. والقراءةُ والكتابةُ عبر
 * `useSearchParams` (react-router) كباقي شاشات المستودع، والبناءُ والقراءة في
 * `utils/accountingOffice.ts` بدالّتين مُختبَرتين.
 */
export const OfficeClientsScreen: React.FC = () => {
  const toast = useToast();
  // الخادم هو الحكم: هذه الأعلام تُخفي أزرار الكتابة ولا تحميها (وهي محميّةٌ
  // بـ`office.clients.write` على كل نقطة). وحجمُ المكتب يخفي **عرضاً** لا صلاحية.
  const { can } = usePermissions();
  const canWrite = can('office.clients.write');
  const [searchParams, setSearchParams] = useSearchParams();
  const [settings, setSettings] = useState<OfficeSettingsPayload | null>(null);
  const [clients, setClients] = useState<OfficeClientRow[]>([]);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [status, setStatus] = useState<StatusFilter>('active');
  const selectedId = clientIdFromSearch(`?${searchParams.toString()}`);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState('');
  const [newFileNumber, setNewFileNumber] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshToken, setRefreshToken] = useState(0);

  const loadSettings = useCallback(() => {
    return getOfficeSettings()
      .then(setSettings)
      .catch((failure) => setError(humanizeThrown(failure, 'تعذّر تحميل إعدادات المكتب.')));
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  /**
   * بحثُ القائمة كمنتقي الجهات في ملفّ الزبون: تأخيرٌ 250مث للنصّ وحده، وتجاهلُ
   * الردود القديمة — كان كلُّ حرفٍ يُطلق طلباً ويفوز آخرها وصولاً لا آخرها
   * إرسالاً. وتغييرُ الفلتر و`refreshToken` («أعد المحاولة»، الرجوعُ من ملفّ) فوريّان.
   */
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (settings?.first_run_required) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    listOfficeClients({ q: debouncedSearch, status })
      .then((rows) => {
        if (!cancelled) setClients(rows);
      })
      .catch((failure) => {
        if (!cancelled) setError(humanizeThrown(failure, 'تعذّر تحميل قائمة الزبائن.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedSearch, status, settings?.first_run_required, refreshToken]);

  const retryClients = useCallback(() => {
    setRefreshToken((token) => token + 1);
  }, []);

  /** فتحُ ملفٍّ وكلُّ ما يغيّره — مستقرّان كي لا يُعاد تحميل الملفّ مع كل رسم. */
  const openClient = useCallback(
    (clientId: number) => {
      setSearchParams({ [CLIENT_QUERY_PARAM]: String(clientId) });
    },
    [setSearchParams],
  );

  const backToList = useCallback(() => {
    setSearchParams({});
    setRefreshToken((token) => token + 1);
  }, [setSearchParams]);

  const handleMissingClient = useCallback(() => {
    backToList();
    toast('هذا الزبون غير موجود — رجعتَ إلى القائمة.', 'error');
  }, [backToList, toast]);

  const submitNewClient = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newName.trim()) return;
    try {
      const created = await createOfficeClient({
        name: newName.trim(),
        tax_file_number: newFileNumber.trim(),
      });
      toast('أُضيف الزبون وبطاقته الضريبية', 'success');
      setNewName('');
      setNewFileNumber('');
      setAdding(false);
      openClient(created.id);
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر إضافة الزبون.'), 'error');
    }
  };

  if (!settings) {
    return error ? (
      <OfficeError message={error} onRetry={() => loadSettings()} />
    ) : (
      <OfficeSkeleton />
    );
  }

  if (settings.first_run_required) {
    return (
      <OfficeFirstRunStep
        payload={settings}
        onDone={() => {
          loadSettings();
        }}
      />
    );
  }

  const officeSize = officeSizeOf(settings.settings);
  // «شخص واحد» لا عمودَ مسؤولٍ ولا إسنادَ فيه: صاحبُ المكتب يعرف زبائنه.
  const showsResponsible = showsOfficeAssignment(officeSize);

  if (selectedId !== null) {
    return (
      <OfficeClientFile
        clientId={selectedId}
        officeSize={officeSize}
        onBack={backToList}
        onMissing={handleMissingClient}
      />
    );
  }

  return (
    <div className="space-y-4">
      <header className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-[20px] font-bold text-slate-900 dark:text-slate-100">الزبائن</h1>
            <p className="mt-1 text-[12px] text-slate-500 dark:text-slate-400">
              كلُّ زبونٍ منشأةٌ بملفّ ضريبيٍّ واحد. محلّان لصاحبٍ واحد = زبونان.
            </p>
          </div>
          {canWrite ? (
            <button
              type="button"
              onClick={() => setAdding((prev) => !prev)}
              className={officePrimaryButtonClass}
            >
              {adding ? 'إلغاء' : 'أضف زبون'}
            </button>
          ) : null}
        </div>

        {adding && canWrite ? (
          <form
            onSubmit={submitNewClient}
            className="mt-4 flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/50"
          >
            <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
              الاسم
              <input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                required
                className={`${officeInputClass} mt-1 block w-64`}
              />
            </label>
            <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
              رقم الملف الضريبي (اختياري)
              <input
                value={newFileNumber}
                onChange={(event) => setNewFileNumber(event.target.value)}
                className={`${officeInputClass} mt-1 block w-48 tabular-nums`}
              />
            </label>
            <button type="submit" className={officePrimaryButtonClass}>
              احفظ وأفتح الملف
            </button>
          </form>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="ابحث بالاسم أو رقم الملف…"
            className={`${officeInputClass} w-72`}
          />
          <div className="flex items-center gap-1">
            {FILTERS.map((filter) => (
              <button
                key={filter.key}
                type="button"
                onClick={() => setStatus(filter.key)}
                className={
                  status === filter.key
                    ? 'rounded-lg bg-teal-50 px-2.5 py-1 text-[11.5px] font-semibold text-teal-800 dark:bg-teal-950/40 dark:text-teal-300'
                    : 'rounded-lg px-2.5 py-1 text-[11.5px] font-medium text-slate-500 dark:text-slate-400'
                }
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {error ? <OfficeError message={error} onRetry={retryClients} /> : null}

      {loading ? (
        <OfficeSkeleton />
      ) : clients.length === 0 ? (
        <OfficeEmpty
          title="لا زبائن في هذا الفلتر"
          hint="أضف زبوناً لتبدأ بطاقته الضريبية وجهاته وملاحظاته."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-200 text-start text-[10.5px] font-medium text-slate-400 dark:border-slate-700 dark:text-slate-500">
                <th className="px-4 py-2 text-start">الزبون</th>
                <th className="px-4 py-2 text-start">رقم الملف الضريبي</th>
                <th className="px-4 py-2 text-start">النظام الضريبي</th>
                {/* «شخص واحد» يخفي عمود الموظف: لا موظفَ غيره في المكتب. */}
                {showsResponsible ? (
                  <th className="px-4 py-2 text-start">المسؤول</th>
                ) : null}
                <th className="px-4 py-2 text-start">الحالة</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((client) => (
                <tr
                  key={client.id}
                  onClick={() => openClient(client.id)}
                  className="cursor-pointer border-b border-slate-100 last:border-b-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50"
                >
                  <td className="px-4 py-2.5 text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
                    {client.name}
                  </td>
                  <td className="px-4 py-2.5 text-[12px] tabular-nums text-slate-600 dark:text-slate-300">
                    {client.tax_file_number || '—'}
                  </td>
                  <td className="px-4 py-2.5 text-[12px] text-slate-600 dark:text-slate-300">
                    {client.tax_system_label}
                  </td>
                  {showsResponsible ? (
                    <td className="px-4 py-2.5 text-[12px] text-slate-600 dark:text-slate-300">
                      {client.responsible_name || '—'}
                    </td>
                  ) : null}
                  <td className="px-4 py-2.5">
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${clientStatusBadgeClass(client.status)}`}
                    >
                      {client.status_label}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
