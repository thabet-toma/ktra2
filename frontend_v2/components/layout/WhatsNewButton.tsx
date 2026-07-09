import React, { useState, useEffect } from 'react';
import { Sparkles, X } from 'lucide-react';

/**
 * «ما الجديد» — زر في الشريط العلوي يفتح لوحة منزلقة من اليسار تشرح آخر التحديثات.
 *
 * لإضافة تحديث جديد: أضِف عنصراً في أعلى مصفوفة CHANGELOG (الأحدث أولاً) وارفع رقم
 * `version`. شارة النقطة تظهر تلقائياً لكل مستخدم لم يفتح اللوحة بعد آخر إصدار.
 */
type ChangeEntry = {
  version: string;
  date: string;
  title: string;
  items: string[];
};

const CHANGELOG: ChangeEntry[] = [
  {
    version: '2026.07.09',
    date: '٩ تموز ٢٠٢٦',
    title: 'سجل نشاط المستخدمين، تحسينات الأسعار والمخزون',
    items: [
      'إضافة "سجل نشاط المستخدمين" شامل: صفحة جديدة (في إدارة الموظفين) تتيح للمدير متابعة كل تفاصيل رحلة المستخدم (بما في ذلك عرض الصفحات)، مع إضافة قسم "سجل نشاط" مخصص داخل الفواتير والصفقات لتوضيح من قام بالعمليات.',
      'تحديث أسعار الشراء المقترحة: القائمة المنسدلة في المشتريات والصفقات أصبحت تعرض دائماً السعرين (أقل سعر وآخر سعر) للمقارنة، مع تعبئة الحقل تلقائياً بآخر سعر شراء.',
      'إعادة إظهار "الكمية المتاحة" بجانب اسم الصنف في القائمة المنسدلة عند البحث داخل فاتورة المبيعات.',
      'إيقاف تحديث عمود "المتاح" وإخفاء تنبيه تجاوز المخزون في فواتير المبيعات المُرحلة (Posted) لتظل الفاتورة كسجل تاريخي ثابت.',
    ],
  },
  {
    version: '2026.07.08',
    date: '٨ تموز ٢٠٢٦',
    title: 'إزالة الأصفار العشرية الزائدة من كل الموقع',
    items: [
      'صارت كل الأرقام تُعرض بدون أصفار عشرية زائدة (١١٠٫٠٠٠٠ ⇐ ١١٠، و٦٦٠٫٠٠ ⇐ ٦٦٠)، مع إبقاء المنازل التي فيها رقم فعلي (١٨٧٫٥ تبقى ١٨٧٫٥).',
      'حقول الكمية والسعر والخصم في الفواتير والمرتجعات تُنظَّف تلقائياً عند فتح الفاتورة، فلا ترجع الأصفار بعد التعديل.',
      'شمل الإصلاح كل التقارير المحاسبية (ميزان المراجعة، قائمة الدخل، الميزانية، دفتر الأستاذ، ض.ق.م، القيود، الشيكات)، وقوائم وطباعة الفواتير والصفقات، ومدفوعات العملاء والموردين.',
    ],
  },
];

const LATEST_VERSION = CHANGELOG[0]?.version ?? '';
const SEEN_KEY = 'ktra_whatsnew_seen_version';

export const WhatsNewButton: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [hasUnseen, setHasUnseen] = useState(false);

  useEffect(() => {
    try {
      setHasUnseen(localStorage.getItem(SEEN_KEY) !== LATEST_VERSION);
    } catch {
      /* تخزين غير متاح — تجاهل */
    }
  }, []);

  const openPanel = () => {
    setOpen(true);
    setHasUnseen(false);
    try {
      localStorage.setItem(SEEN_KEY, LATEST_VERSION);
    } catch {
      /* تخزين غير متاح — تجاهل */
    }
  };

  // إغلاق باللمس على Esc
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={openPanel}
        className="relative flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm font-medium text-[var(--color-primary)] hover:bg-[var(--color-surface-2)] transition-colors"
        title="ما الجديد في آخر تحديث"
        aria-label="ما الجديد"
      >
        <Sparkles className="w-4 h-4" />
        <span className="hidden sm:inline">ما الجديد</span>
        {hasUnseen && (
          <span className="absolute -top-0.5 -start-0.5 w-2.5 h-2.5 rounded-full bg-red-500 ring-2 ring-[var(--color-surface)]" />
        )}
      </button>

      {open && (
        <>
          {/* الخلفية المعتّمة */}
          <div
            className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[1px]"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />

          {/* اللوحة المنزلقة من اليسار */}
          <aside
            dir="rtl"
            className="fixed top-0 left-0 z-50 h-full w-[92vw] max-w-[380px] bg-[var(--color-surface)] shadow-2xl border-e border-gray-200 dark:border-gray-700 flex flex-col animate-[whatsnew-in_.22s_ease-out]"
            role="dialog"
            aria-label="ما الجديد"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gradient-to-l from-[var(--color-primary)]/10 to-transparent">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-[var(--color-primary)]" />
                <h2 className="text-base font-bold text-[var(--color-text)]">ما الجديد</h2>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="p-1.5 rounded-md text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 transition-colors"
                aria-label="إغلاق"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
              {CHANGELOG.map((entry, idx) => (
                <div key={entry.version}>
                  <div className="flex items-center gap-2 mb-2">
                    {idx === 0 && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[var(--color-primary)] text-white">
                        الأحدث
                      </span>
                    )}
                    <span className="text-xs text-[var(--color-text-muted)]">{entry.date}</span>
                  </div>
                  <h3 className="text-sm font-bold text-[var(--color-text)] mb-2">{entry.title}</h3>
                  <ul className="space-y-2">
                    {entry.items.map((item, i) => (
                      <li key={i} className="flex gap-2 text-sm text-[var(--color-text)] leading-relaxed">
                        <span className="mt-1.5 w-1.5 h-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>

            <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 text-[11px] text-center text-[var(--color-text-muted)]">
              K.T.R.A — نظام إدارة متكامل
            </div>
          </aside>

          <style>{`@keyframes whatsnew-in{from{transform:translateX(-100%);opacity:.6}to{transform:translateX(0);opacity:1}}`}</style>
        </>
      )}
    </>
  );
};
