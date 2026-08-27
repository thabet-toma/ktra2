/**
 * M0 verification page — /ui-kit
 * Exercises the whole Kit shell layer with sample data laid out like the
 * owner's «فواتير الشراء» screenshot, so M0 can be visually + behaviourally
 * verified WITHOUT touching any backend or real screen.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { formatMoney } from '../../utils/formatNumber';
import { getSkin } from '../../styles/skin';
import {
  Plus,
  Save,
  Trash2,
  Ban,
  FolderOpen,
  Table2,
  Receipt,
  Printer,
  RefreshCw,
  FileSearch,
  FileBarChart2,
  MoreHorizontal,
  LogOut,
  HelpCircle,
  User,
  Calendar,
} from 'lucide-react';
import {
  KitDocumentShell,
  KitDocumentView,
  KitGrid,
  KitIndexPicker,
  KitFloatWindow,
  KitFormSection,
  KitDenseTable,
  KitReportTable,
  KitStatusBarItem,
  KitDateInput,
  useRecordNavigation,
  useKitKeymap,
  useKitIndexKeymap,
  useKitFieldShortcuts,
  type KitGridColumn,
  type KitIndexColumn,
  type KitToolbarAction,
  type DenseColumn,
  type ReportColumn,
} from './index';

interface DemoInvoice { id: number; number: string; account: string; }
interface DemoLine { sku: string; name: string; unit: string; qty: string; price: string; }
interface DemoAccount { code: string; name: string; kind: string; }

const DEMO_INVOICES: DemoInvoice[] = [
  { id: 101, number: '۱۰۱', account: 'شركة خالد الخواجا' },
  { id: 102, number: '۱۰۲', account: 'بكدار' },
  { id: 103, number: '۱۰۳', account: 'محلات بليل' },
  { id: 104, number: '۱۰٤', account: 'مبيعات نقدية' },
];

const DEMO_ACCOUNTS: DemoAccount[] = [
  { code: '1101', name: 'الصندوق', kind: 'أصول' },
  { code: '1103', name: 'البنك العربي', kind: 'أصول' },
  { code: '4101', name: 'المبيعات', kind: 'إيراد' },
  { code: '2101', name: 'الموردون', kind: 'خصوم' },
  { code: '5101', name: 'المشتريات', kind: 'متاجرة' },
];

const fld = (label: string, node: React.ReactNode) => (
  <label className="ktra-field">
    <span className="ktra-field-label">{label}</span>
    {node}
  </label>
);

export const KitStory: React.FC = () => {
  const [skin, setSkin] = useState(() => getSkin());
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [floatOpen, setFloatOpen] = useState(false);
  const [lastKey, setLastKey] = useState('—');
  const [account, setAccount] = useState('');
  const [lines, setLines] = useState<DemoLine[]>([
    { sku: '', name: '', unit: 'عدد', qty: '1', price: '0' },
  ]);

  useEffect(() => {
    const handleSkinChange = () => setSkin(getSkin());
    window.addEventListener('ktra:skin', handleSkinChange);
    return () => window.removeEventListener('ktra:skin', handleSkinChange);
  }, []);

  const nav = useRecordNavigation<DemoInvoice>({
    items: DEMO_INVOICES,
    getId: (r) => r.id,
    currentId,
    onSelect: setCurrentId,
  });

  useKitKeymap(
    {
      F2: () => setLastKey('F2 — طباعة الفاتورة'),
      F3: () => setLastKey('F3 — إيصال القبض'),
      F6: () => { setLastKey('F6 — بحث'); setPickerOpen(true); },
      F12: () => setLastKey('F12 — تخزين'),
      Escape: () => setLastKey('Esc — إلغاء'),
      plus: () => { setLastKey('+ — فهرس'); setPickerOpen(true); },
      star: () => { setLastKey('* — التالي'); nav.next(); },
      minus: () => { setLastKey('- — السابق'); nav.prev(); },
    },
    { enabled: !pickerOpen },
  );

  const cols: KitGridColumn<DemoLine>[] = useMemo(
    () => [
      { key: '_n', header: 'مسلسل', width: '52px', align: 'center', readOnly: true },
      { key: 'sku', header: 'رقم المنتج', width: '120px' },
      { key: 'name', header: 'وصف المنتج' },
      { key: 'unit', header: 'الوحدة', width: '90px', align: 'center' },
      { key: 'qty', header: 'الكمية', width: '90px', type: 'number' },
      { key: 'price', header: 'سعر الوحدة', width: '110px', type: 'number' },
      { key: '_total', header: 'السعر الإجمالي', width: '120px', type: 'number', readOnly: true },
    ],
    [],
  );

  const accountCols: KitIndexColumn<DemoAccount>[] = [
    { key: 'code', header: 'رقم الحساب', width: '110px', value: (r) => r.code },
    { key: 'name', header: 'اسم الحساب', value: (r) => r.name },
    { key: 'kind', header: 'النوع', width: '110px', value: (r) => r.kind },
  ];

  const actions: KitToolbarAction[] = [
    { key: 'add', label: 'إضافة', icon: <Plus />, onClick: () => nav.goNew() },
    { key: 'save', label: 'تخزين', icon: <Save />, onClick: () => setLastKey('تخزين') },
    { key: 'del', label: 'حذف', icon: <Trash2 />, danger: true, onClick: () => setLastKey('حذف') },
    { key: 'cancel', label: 'إلغاء', icon: <Ban />, onClick: () => setLastKey('إلغاء') },
    { key: 'open', label: 'فتح', icon: <FolderOpen />, onClick: () => setLastKey('فتح') },
    { key: 'grid', label: 'جدول', icon: <Table2 />, separatorBefore: true, onClick: () => setLastKey('جدول') },
    { key: 'voucher', label: 'سند الصرف', icon: <Receipt />, onClick: () => setLastKey('سند الصرف') },
    { key: 'print', label: 'طباعة الفاتورة', icon: <Printer />, onClick: () => setLastKey('طباعة') },
    { key: 'prices', label: 'تحديث أسعار المنتجات', icon: <RefreshCw />, onClick: () => setLastKey('تحديث الأسعار') },
    { key: 'cons', label: 'مراجعة إرساليات الفاتورة', icon: <FileSearch />, onClick: () => setLastKey('الإرساليات') },
    { key: 'rep', label: 'تقارير القوائم', icon: <FileBarChart2 />, separatorBefore: true, onClick: () => setLastKey('تقارير') },
    { key: 'more', label: 'أوامر أخرى', icon: <MoreHorizontal />, onClick: () => setLastKey('أوامر') },
    { key: 'exit', label: 'إنهاء وخروج', icon: <LogOut />, onClick: () => setLastKey('خروج') },
    { key: 'help', label: 'المساعدة', icon: <HelpCircle />, onClick: () => setLastKey('مساعدة') },
  ];

  const cur = DEMO_INVOICES.find((i) => i.id === currentId);

  return (
    <div data-skin={skin} style={{ height: 'calc(100vh - 7rem)' }}>
      <KitDocumentShell
        title="فواتير الشراء"
        state={cur ? `فاتورة ${cur.number}` : 'فاتورة جديدة'}
        company="الشركة العامة للزهور [ السنة المالية 1996 ]"
        nav={nav}
        actions={actions}
        header={
          <>
            {fld('رقم الفاتورة', <input className="ktra-input" defaultValue={cur?.number ?? ''} />)}
            {fld('دفتر', <input className="ktra-input" data-ktra-key="1" defaultValue="0" />)}
            {fld('التاريخ', <input className="ktra-input" type="date" defaultValue="2026-05-19" />)}
            {fld('الساعة', <input className="ktra-input" defaultValue="09:24:45 ص" />)}
            {fld('تاريخ ثاني', <input className="ktra-input" type="date" />)}
            {fld('تاريخ الاستحقاق', <input className="ktra-input" type="date" />)}
            {fld(
              'رقم الحساب',
              <input
                className="ktra-input ktra-input--hl"
                data-ktra-key="1"
                value={account}
                onChange={(e) => setAccount(e.target.value)}
              />,
            )}
            {fld('الاسم', <input className="ktra-input" defaultValue={cur?.account ?? ''} />)}
            {fld('العنوان', <input className="ktra-input" />)}
            {fld('مشتغل مرخص', <input className="ktra-input" />)}
            {fld('عملة الفاتورة', <input className="ktra-input" defaultValue="شيكل جديد" />)}
            {fld('سعر العملة', <input className="ktra-input" data-ktra-key="1" defaultValue="1.00000" />)}
            {fld('رقم المستند', <input className="ktra-input" />)}
            <label className="ktra-field" style={{ gridColumn: '1 / -1' }}>
              <input type="checkbox" />
              <span className="ktra-field-label" style={{ flex: 'unset' }}>
                الأسعار تشمل ض.ق.م
              </span>
            </label>
          </>
        }
        tabs={[
          { key: 'notes', label: 'الملاحظات', content: <textarea className="ktra-input" rows={3} style={{ width: '100%' }} /> },
          { key: 'accounts', label: 'الحسابات / مركز التكلفة', content: <span>تصنيف أول / تصنيف ثاني / مركز التكلفة …</span> },
          { key: 'other', label: 'بيانات أخرى', content: <span>تعبئة من … · رقم فاتورة المقاصة …</span> },
        ]}
        totals={
          <>
            <div className="ktra-total-row"><span>المجموع بدون الضريبة</span><span className="ktra-total-value">0.00</span></div>
            <div className="ktra-total-row"><span>خصم مكتسب</span><span className="ktra-total-value">0.00</span></div>
            <div className="ktra-total-row"><span>خصم مكتسب %</span><span className="ktra-total-value">0.00</span></div>
            <div className="ktra-total-row"><span>الضريبة المضافة 16%</span><span className="ktra-total-value">0.00</span></div>
            <div className="ktra-total-row"><span>مدفوع نقدا</span><span className="ktra-total-value">0.00</span></div>
            <div className="ktra-total-row ktra-total-row--grand"><span>مبلغ الفاتورة الإجمالي</span><span className="ktra-total-value">0.00</span></div>
          </>
        }
        status={
          <>
            <span className="ktra-status-item">المستخدم <b>admin</b></span>
            <span className="ktra-status-item">رقم القيد <b>—</b></span>
            <span className="ktra-status-item">رقم الحركة <b>—</b></span>
            <span className="ktra-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
            <span className="ktra-status-item">آخر مفتاح <b>{lastKey}</b></span>
            <label className="ktra-status-item"><input type="checkbox" defaultChecked /> قابل للتعديل</label>
          </>
        }
      >
        <KitGrid<DemoLine>
          columns={cols}
          rows={lines}
          getRowKey={(_, i) => i}
          getCell={(row, key) => {
            if (key === '_n') return lines.indexOf(row) + 1;
            if (key === '_total')
              return (Number(row.qty) || 0) * (Number(row.price) || 0);
            return (row as unknown as Record<string, string>)[key];
          }}
          onChange={(ri, key, value) =>
            setLines((prev) =>
              prev.map((r, i) => (i === ri ? { ...r, [key]: value } : r)),
            )
          }
          onAddRow={() =>
            setLines((prev) => [...prev, { sku: '', name: '', unit: 'عدد', qty: '1', price: '0' }])
          }
        />
      </KitDocumentShell>

      <KitIndexPicker<DemoAccount>
        open={pickerOpen}
        title="فهرس الحسابات"
        rows={DEMO_ACCOUNTS}
        columns={accountCols}
        getRowKey={(r) => r.code}
        searchValue={(r) => `${r.code} ${r.name} ${r.kind}`}
        onSelect={(r) => {
          setAccount(r.code);
          setPickerOpen(false);
          setLastKey(`اختير ${r.code} ${r.name}`);
        }}
        onClose={() => setPickerOpen(false)}
      />

      {/* ─ T-WIN: النافذة العائمة — تُسحب من عنوانها وتُحجَّم من حوافها ─ */}
      <div className="mt-8 p-4 border-t border-[var(--ktra-border)]">
        <h3 className="text-lg font-bold mb-4 text-amber-700">T-WIN: النافذة العائمة</h3>
        <button
          type="button"
          className="ktra-btn"
          data-testid="story-open-float"
          onClick={() => setFloatOpen(true)}
        >
          افتح نافذة عائمة
        </button>
        <KitFloatWindow
          open={floatOpen}
          onClose={() => setFloatOpen(false)}
          name="kit-demo"
          title="نافذة تجريبية"
          defaultWidth={520}
          defaultHeight={360}
          modal={false}
          rootProps={{ 'data-testid': 'story-float-win' } as React.HTMLAttributes<HTMLDivElement>}
        >
          <div className="p-4 text-[var(--ktra-ink)]">
            اسحبها من شريط العنوان، وحجّمها من أي حافة أو زاوية. موضعها وحجمها
            يعودان كما تركتهما بعد إعادة تحميل الصفحة.
          </div>
        </KitFloatWindow>
      </div>

      {/* ─ N0 + N1: أمثلة الـ primitives الجديدة ──────────────────── */}
      <div className="mt-8 p-4 border-t border-[var(--ktra-border)]">
        <h3 className="text-lg font-bold mb-4 text-amber-700">N0 + N1: مكوّنات جديدة</h3>

        {/* KitFormSection */}
        <KitFormSection title="مثال: قسم نموذج فرعي" cols={3}>
          {fld('حقل 1', <input className="ktra-input" placeholder="..." />)}
          {fld('حقل 2', <input className="ktra-input" placeholder="..." />)}
          {fld('حقل 3', <input className="ktra-input" placeholder="..." />)}
        </KitFormSection>

        {/* KitDenseTable */}
        <div className="mt-4">
          <h4 className="font-bold mb-2">KitDenseTable — جدول إدارة</h4>
          <KitDenseTable<DemoInvoice>
            columns={[
              { key: 'number', header: 'الرقم', width: '80px', sortable: true },
              { key: 'account', header: 'الحساب', sortable: true },
              { key: 'id', header: 'المعرّف', width: '80px', align: 'center', numeric: true },
            ] as DenseColumn<DemoInvoice>[]}
            rows={DEMO_INVOICES}
            getRowKey={(r) => r.id}
            onRowDoubleClick={(r) => setLastKey(`فتح فاتورة ${r.number}`)}
          />
        </div>

        {/* KitReportTable */}
        <div className="mt-4">
          <h4 className="font-bold mb-2">KitReportTable — جدول تقرير</h4>
          <KitReportTable<DemoLine>
            columns={[
              { key: 'sku', header: 'المنتج' },
              { key: 'name', header: 'البيان' },
              { key: 'qty', header: 'الكمية', numeric: true },
              { key: 'price', header: 'السعر', numeric: true },
            ] as ReportColumn<DemoLine>[]}
            rows={lines.filter((l) => l.sku)}
            totals={{ qty: String(lines.reduce((s, l) => s + Number(l.qty), 0)), price: '—' }}
            exportable
          />
        </div>

        {/* KitStatusBarItem */}
        <div className="mt-4">
          <h4 className="font-bold mb-2">KitStatusBarItem — عناصر شريط الحالة</h4>
          <div className="flex gap-4 flex-wrap">
            <KitStatusBarItem label="المستخدم" value="admin" icon={<User className="h-3 w-3" />} />
            <KitStatusBarItem label="التاريخ" value="2026-05-21" icon={<Calendar className="h-3 w-3" />} />
            <KitStatusBarItem label="الحالة" value="متصل" />
          </div>
        </div>

        {/* N1-T5 — KitDateInput */}
        <DateInputStoryPanel />

        {/* عرض مستندي للقراءة — نفس المكوّن الذي يخدم المبيعات والشراء والصفقات */}
        <DocumentViewStoryPanel />
      </div>
    </div>
  );
};

const DateInputStoryPanel: React.FC = () => {
  const [d, setD] = React.useState<string>(new Date().toISOString().slice(0, 10));
  return (
    <div className="mt-4">
      <h4 className="font-bold mb-2">KitDateInput — حقل تاريخ مع تقويم سنوي</h4>
      <p className="text-xs text-[var(--color-text-muted)] mb-2">
        داخل الحقل: * يَزيد يوم · - يَنقص يوم · + يَزيد شهر · double-click يَفتح التقويم السنوي.
      </p>
      <div className="flex gap-3 items-center">
        <KitDateInput value={d} onChange={setD} style={{ width: 180 }} />
        <span className="text-xs">القيمة الحالية: <b>{d || '—'}</b></span>
      </div>
    </div>
  );
};

type StoryLine = { name: string; qty: number; price: number; discount: number; total: number };

const DocumentViewStoryPanel: React.FC = () => {
  const rows: StoryLine[] = [
    { name: 'بطارية 15 كيلو zj مايكل', qty: 10, price: 783, discount: 0, total: 7830 },
    { name: 'بطارية 30 كيلو zj مايكل', qty: 10, price: 1231, discount: 0, total: 12310 },
    { name: 'شاحن سريع 60W', qty: 4, price: 145.5, discount: 20, total: 562 },
  ];
  const money = (n: number) => `${formatMoney(n)} ILS`;
  return (
    <div className="mt-4">
      <h4 className="font-bold mb-2">KitDocumentView — عرض مستندي للقراءة</h4>
      <p className="text-xs text-[var(--color-text-muted)] mb-2">
        يفتح المستند على هذا العرض، و«تحرير» في شريط الأدوات يفتح نموذج التحرير.
      </p>
      <div className="border rounded-xl overflow-hidden bg-[var(--color-surface-2)]">
        <KitDocumentView<StoryLine>
          title="فاتورة مبيعات"
          subtitle="SALES INVOICE"
          documentNumber="SI-2026-0042"
          status={{ label: 'مرحّلة', tone: 'ok' }}
          metrics={[
            { label: 'الإجمالي', value: money(20702), tone: 'info' },
            { label: 'المدفوع', value: money(20702), tone: 'ok' },
            { label: 'المتبقي', value: money(0) },
            { label: 'نوع الفاتورة', value: 'نقدي', tone: 'ok' },
          ]}
          parties={[
            {
              title: 'العميل',
              fields: [
                { label: 'الاسم', value: 'مؤسسة النور التجارية' },
                { label: 'الهاتف', value: '0599-123456' },
              ],
            },
          ]}
          meta={[
            { label: 'تاريخ الفاتورة', value: '2026-07-19' },
            { label: 'تاريخ الاستحقاق', value: '2026-08-19' },
            { label: 'العملة', value: 'ILS' },
            { label: 'قيد اليومية', value: '#13200' },
          ]}
          columns={[
            { key: 'name', header: 'المنتج', render: (r) => <span className="font-semibold">{r.name}</span> },
            { key: 'qty', header: 'الكمية', width: '80px', align: 'center', numeric: true, render: (r) => formatMoney(r.qty) },
            { key: 'price', header: 'سعر الوحدة', width: '110px', align: 'left', numeric: true, render: (r) => formatMoney(r.price) },
            { key: 'disc', header: 'الخصم', width: '90px', align: 'left', numeric: true, render: (r) => formatMoney(r.discount) },
            { key: 'total', header: 'الإجمالي', width: '120px', align: 'left', numeric: true, render: (r) => <b>{formatMoney(r.total)}</b> },
          ]}
          rows={rows}
          totals={[
            { label: 'المجموع قبل الضريبة', value: money(17693.16) },
            { label: 'خصم الفاتورة', value: money(20) },
            { label: 'الضريبة', value: money(3008.84) },
            { label: 'الإجمالي', value: money(20702), emphasis: true },
          ]}
          sections={[{ key: 'notes', title: 'ملاحظات', content: 'تسليم على عنوان العميل خلال 3 أيام عمل.' }]}
        />
      </div>
    </div>
  );
};
