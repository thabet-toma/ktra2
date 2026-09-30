/**
 * فهرسُ الإعدادات (#75/#69): «صفحة كبيرة غير منظّمة… أوّل ما أفوت يكون بس عناوين
 * الإعدادات، ولمّا أكبس على واحد يبيّن اللي تحته».
 *
 * الدخولُ يعرض بطاقاتِ الأقسام مع بحثٍ يطابق العنوانَ وأسماءَ الحقول
 * (`utils/settingsIndex.ts`)، والكبسةُ تفتح القسمَ وحده مع رجوعٍ للفهرس. القسمُ
 * المفتوح في الرابط (`?section=`) فزرُّ «رجوع» المتصفح يعيد الفهرس، والرابطُ
 * يُحفظ ويُرسَل. وهذا نمطُ Odoo (أقسامٌ وبحث) بلا أكورديون: `CollapsibleSection`
 * ممنوعٌ بـ`docs/ui_density_rules.md`، وقسمٌ واحدٌ مرئيٌّ هو ما تطلبه القاعدة.
 *
 * **الأقسامُ تبقى مركَّبةً مخفيّةً** وهي مغلقة (إلا `lazy`): تعديلٌ لم يُحفظ في قسمٍ
 * لا يضيع بالانتقال لغيره قبل «حفظ»، وحقولُ الشاشة كلُّها تبقى في الصفحة لإحصاء
 * التكافؤ (`e2e/feature-parity-census.spec.ts`) — الإخفاءُ ترتيبٌ لا حذف.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRight, ChevronLeft, ExternalLink, Search, X, type LucideIcon } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { filterSettingsSections, type SettingsIndexEntry } from '../../utils/settingsIndex';

export interface SettingsIndexSection extends SettingsIndexEntry {
  icon?: LucideIcon;
  /** محتوى القسم حين يُفتح. */
  content?: React.ReactNode;
  /** لا يُركَّب إلا مفتوحاً — لقسمٍ يجلب بياناتٍ ثقيلةً عند تركيبه. */
  lazy?: boolean;
  /** قسمٌ يعيش في شاشته: الكبسةُ تنقل إليها بدل فتحه هنا. */
  to?: string;
}

interface SettingsIndexProps {
  title: string;
  subtitle?: string;
  /** `false` داخل `KitDocumentShell` الذي يعرض العنوانَ في شريطه — لا عنوانان متتاليان. */
  showTitle?: boolean;
  sections: SettingsIndexSection[];
}

export const SETTINGS_SECTION_PARAM = 'section';

const scrollToTop = () => {
  const scroller = document.querySelector<HTMLElement>('main.app-content');
  if (scroller) scroller.scrollTop = 0;
  else window.scrollTo(0, 0);
};

export const SettingsIndex: React.FC<SettingsIndexProps> = ({ title, subtitle, showTitle = true, sections }) => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState('');
  // رجوعٌ في التاريخ إن كنّا دفعنا القسمَ إليه، وإلا (رابطٌ مباشر) حذفُ المعامل بلا دفع.
  const pushedRef = useRef(false);
  const requested = searchParams.get(SETTINGS_SECTION_PARAM);
  // قسمٌ غيرُ معروفٍ أو محجوبٌ عن هذا المستخدم يسقط إلى الفهرس لا إلى صفحةٍ فارغة.
  const active = sections.find((section) => section.id === requested && !section.to) ?? null;
  const visible = useMemo(() => filterSettingsSections(sections, query), [sections, query]);

  useEffect(() => {
    if (!requested) pushedRef.current = false;
    scrollToTop();
  }, [requested]);

  const setSection = (id: string | null, replace: boolean) => setSearchParams((prev) => {
    const next = new URLSearchParams(prev);
    if (id) next.set(SETTINGS_SECTION_PARAM, id);
    else next.delete(SETTINGS_SECTION_PARAM);
    return next;
  }, { replace });
  const open = (section: SettingsIndexSection) => {
    if (section.to) { navigate(section.to); return; }
    pushedRef.current = true;
    setSection(section.id, false);
  };
  const back = () => {
    if (pushedRef.current) { pushedRef.current = false; navigate(-1); return; }
    setSection(null, true);
  };

  return (
    <div dir="rtl" className="space-y-3" data-testid="settings-index">
      {active ? (
        <nav className="flex flex-wrap items-center gap-2 text-sm" aria-label="مسار الإعدادات">
          <button type="button" onClick={back} className="inline-flex items-center gap-1 font-bold text-[var(--color-primary)] hover:underline">
            <ArrowRight className="h-4 w-4" />
            كل الإعدادات
          </button>
          <span className="ktra-text-soft" aria-hidden="true">/</span>
          <span className="ktra-text-soft">{title}</span>
          <span className="ktra-text-soft" aria-hidden="true">/</span>
          <span className="font-bold text-[var(--color-text)]" aria-current="page">{active.title}</span>
        </nav>
      ) : (
        <>
          <header className="flex flex-wrap items-end justify-between gap-3 border-b border-[var(--color-border)] pb-3">
            <div>
              {showTitle && <h1 className="text-base font-bold text-[var(--color-text)]">{title}</h1>}
              <p className="mt-0.5 text-xs ktra-text-soft">{subtitle ?? 'اختر قسماً لتفتحه، أو ابحث باسم الإعداد.'}</p>
            </div>
            <label className="relative block w-full sm:w-72">
              <span className="sr-only">ابحث عن إعداد</span>
              <Search className="pointer-events-none absolute start-2 top-1/2 h-4 w-4 -translate-y-1/2 ktra-text-soft" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter' && visible.length === 1) open(visible[0]); }}
                placeholder="ابحث عن إعداد…"
                aria-label="ابحث عن إعداد"
                className="ktra-input w-full ps-8"
              />
            </label>
          </header>
          {visible.length === 0 ? (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-[var(--color-border)] p-4 text-sm ktra-text-soft" role="status">
              لا إعداد يطابق «{query.trim()}».
              <button type="button" onClick={() => setQuery('')} className="inline-flex items-center gap-1 font-bold text-[var(--color-primary)] hover:underline">
                <X className="h-3.5 w-3.5" />
                مسح البحث
              </button>
            </div>
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" aria-label={`أقسام ${title}`}>
              {visible.map((section) => {
                const Icon = section.icon;
                return (
                  <li key={section.id}>
                    <button
                      type="button"
                      onClick={() => open(section)}
                      data-testid={`settings-card-${section.id}`}
                      className="group flex h-full w-full items-start gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-right transition-colors hover:border-[var(--color-primary)]"
                    >
                      {Icon && <Icon className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-primary)]" aria-hidden="true" />}
                      <span className="min-w-0 flex-1">
                        <span className="block font-bold text-[var(--color-text)]">{section.title}</span>
                        <span className="mt-0.5 block text-xs ktra-text-soft">{section.description}</span>
                      </span>
                      {section.to
                        ? <ExternalLink className="mt-0.5 h-4 w-4 shrink-0 ktra-text-soft" aria-label="صفحة مستقلة" />
                        : <ChevronLeft className="mt-0.5 h-4 w-4 shrink-0 ktra-text-soft transition-transform group-hover:-translate-x-0.5" aria-hidden="true" />}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
      {sections
        .filter((section) => !section.to && (!section.lazy || section.id === active?.id))
        .map((section) => (
          <section key={section.id} className={section.id === active?.id ? undefined : 'hidden'} aria-label={section.title} data-settings-section={section.id}>
            {section.content}
          </section>
        ))}
    </div>
  );
};
