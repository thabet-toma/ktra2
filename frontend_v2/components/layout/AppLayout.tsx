import React, { useState, useEffect } from 'react';
import { Sidebar } from '../Sidebar';
import { User, AppView } from '../../types';
import {
  DensitySwitch,
} from './DensitySwitch';
import {
  ThemeToggle,
} from './ThemeToggle';
import { PriceVisibilityToggle } from './PriceVisibilityToggle';
import {
  GlobalSearch,
} from './GlobalSearch';
import {
  CompanySwitcher,
} from './CompanySwitcher';
import {
  BranchSwitcher,
} from './BranchSwitcher';
import { KitCalculatorButton } from '../kit';
import { ActionBarRail } from './ActionBarRail';
import { QuickAccessBar } from './QuickAccessBar';
import { GlobalContextMenu } from './GlobalContextMenu';
import { NotificationCenter } from '../notifications/NotificationCenter';
import { WhatsNewButton } from './WhatsNewButton';
import { CustomerNotesTab } from '../partners/CustomerNotesTab';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useCompany } from '../../contexts/CompanyContext';
import { formatNumber } from '../../utils/formatNumber';
// استيراد مباشر لا عبر barrel الـimport-flow: البرميل يجرّ ImportDocumentScreen
// كاملةً إلى حزمة القشرة ويُبطل تقسيم الحِزَم.
import { ImportJourneyGuide } from '../import-flow/ImportJourneyGuide';
import { platformNoteTarget, type PlatformNoteTarget } from '../../utils/entityLinks';
import { openInNewTab, TAB_OPENED_EVENT, type TabOpenedDetail } from '../../utils/openInNewTab';
import { setCurrentTabLabel } from '../../utils/tabLink';
import { VIEW_LABELS } from './Breadcrumb';
import { useToast } from '../../contexts/ToastContext';
import {
  User as UserIcon,
  Calendar,
  Sparkles,
  LogOut,
  Copy,
  SlidersHorizontal,
  NotebookPen,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { formatDateValue } from "../../utils/formatDate";

/**
 * T-TRIAL: شريط انتهاء الاشتراك — يظهر في آخر سبعة أيام وبعد الانتهاء، ويختفي
 * تماماً لأي اشتراك بلا تاريخ. الأرقام والتاريخ يأتيان محسوبين من الخادم
 * (`subscription_days_left` / `subscription_ends_at`) لأن الحارس الذي يمنع
 * الكتابة يقرأ التاريخ بتوقيت الخادم؛ حسابُه هنا كان سيُظهر «يتبقّى يوم» لمن
 * مُنع فعلاً. الظهور لا يُلغى بالإغلاق: حالةٌ قائمة لا إشعارٌ عابر.
 */
const SubscriptionExpiryBanner: React.FC = () => {
  const { currentCompany } = useCompany();
  const daysLeft = currentCompany?.subscription_days_left;
  if (!currentCompany || daysLeft === null || daysLeft === undefined) return null;
  const expired = daysLeft < 0;
  if (!expired && daysLeft > 7) return null;
  const endsAt = formatDateValue(currentCompany.subscription_ends_at ?? '');
  const message = expired
    ? `انتهى اشتراك «${currentCompany.CompanyName}» بتاريخ ${endsAt} — الحساب للقراءة والطباعة فقط، ولا يمكن حفظ أي مستند. تواصل مع إدارة المنصة للتجديد.`
    : daysLeft === 0
      ? `اليوم آخر يوم في اشتراك «${currentCompany.CompanyName}» (${endsAt}) — بعده يصير الحساب للقراءة فقط.`
      : `يتبقّى ${formatNumber(daysLeft, { maxDecimals: 0 })} يوماً على انتهاء اشتراك «${currentCompany.CompanyName}» في ${endsAt}.`;
  return (
    <div
      role="alert"
      data-testid="subscription-expiry-banner"
      className={`flex-shrink-0 border-b px-4 py-2 text-sm font-semibold ${
        expired
          ? 'border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/50 dark:text-red-200'
          : 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/50 dark:text-amber-200'
      }`}
    >
      {message}
    </div>
  );
};

/**
 * ISSUE #65 — «أنت داخل دفتر عميلك». حالةٌ قائمة لا إشعارٌ عابر، فلا تُغلَق:
 * كل شاشة معروضة الآن تكتب في دفتر الزبون لا في دفتر المكتب، وخلطُ الاثنين هو
 * بالضبط ما تمنعه هذه الشاشة. والزرّ هو **طريق العودة الظاهر** الذي اشترطته
 * التذكرة — بلا لمس عنوان URL ولا مبدّل شركاتٍ لا يحوي الدفتر أصلاً.
 */
const ManagedBookBanner: React.FC = () => {
  const { currentCompany, insideManagedBook, returnToOffice } = useCompany();
  if (!insideManagedBook || !currentCompany) return null;
  return (
    <div
      role="status"
      data-testid="managed-book-banner"
      className="flex flex-shrink-0 flex-wrap items-center justify-between gap-2 border-b border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-semibold text-indigo-900 dark:border-indigo-900/60 dark:bg-indigo-950/50 dark:text-indigo-200"
    >
      <span>
        أنت داخل دفتر عميلك «{currentCompany.CompanyName}» — كل ما تحفظه هنا يخصّه هو لا مكتبك.
      </span>
      <button
        type="button"
        onClick={returnToOffice}
        className="rounded-lg bg-indigo-700 px-3 py-1.5 text-xs font-bold text-white"
      >
        العودة إلى المكتب
      </button>
    </div>
  );
};

interface AppLayoutProps {
  user: User;
  activeView: AppView;
  onNavigate: (view: AppView, targetId?: string) => void;
  children: React.ReactNode;
  /** N0-T5: callback لفتح صفحة ثوابت المجموعة (F11). */
  onOpenGroupConstants?: () => void;
  /** مسار قائمة الشاشة الحالية (`VIEW_PATHS[activeView]`) — وجهةُ «رجوع» حين
   *  لا سابقة في هذا التبويب (`utils/backTarget.ts`). */
  listPath?: string;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  user,
  activeView,
  onNavigate,
  children,
  onOpenGroupConstants,
  listPath,
}) => {
  const { logout } = useAuth();
  const confirm = useConfirm();
  const toast = useToast();
  const [density, setDensity] = useState<'comfortable' | 'compact'>('comfortable');
  const [notesTarget, setNotesTarget] = useState<PlatformNoteTarget | null>(null);

  const openPlatformNotes = () => {
    const heading = document.querySelector<HTMLElement>('main h1, main h2, main h3')
      ?.textContent?.trim();
    setNotesTarget(platformNoteTarget(
      window.location.pathname,
      window.location.search,
      heading || document.title || 'الصفحة الحالية',
    ));
  };
  // وعي التبويبات: هذا التبويب يعلن اسم شاشته للتبويبات الأخرى، فيقدر تبويبٌ
  // فُتح منه أن يقول «فُتح من: فواتير المبيعات» بلا جدول مسارات ثانٍ.
  useEffect(() => {
    setCurrentTabLabel(VIEW_LABELS[activeView] ?? String(activeView));
  }, [activeView]);

  // ...وفتحُ تبويبٍ جديد يُعلن عن نفسه **هنا** أيضاً: المتصفّح قد يفتحه في
  // الخلفية فلا يرى المستخدم شيئاً ويظنّ الضغطة لم تعمل.
  useEffect(() => {
    const onTabOpened = (event: Event) => {
      const detail = (event as CustomEvent<TabOpenedDetail>).detail;
      const name = detail?.label?.trim();
      toast(name ? `فُتح في تبويب جديد: ${name}` : 'فُتح في تبويب جديد', 'info');
    };
    window.addEventListener(TAB_OPENED_EVENT, onTabOpened);
    return () => window.removeEventListener(TAB_OPENED_EVENT, onTabOpened);
  }, [toast]);

  // N0-T5: F11 global keymap → يفتح GroupConstantsPage كـ modal portal
  useEffect(() => {
    if (!onOpenGroupConstants) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'F11') {
        e.preventDefault();
        onOpenGroupConstants();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onOpenGroupConstants]);

  return (
    <div className="app-shell flex flex-col h-screen overflow-hidden bg-[var(--color-surface)]" data-density={density}>
      {/* task13 M6: حُذف chip العنوان (كان يكرر تسمية الشريط الجانبي والـ breadcrumb)
           ونُقلت «السنة المالية» إلى شريط الحالة السفلي بجانب المستخدم/الدور. */}
      <div className="ktra-titlebar ktra-app-chrome flex-shrink-0">
        <div className="ktra-company flex items-center gap-3">
          <CompanySwitcher />
          <BranchSwitcher />
          
          {/* T-N1: المساعد الذكي */}
          <button
            type="button"
            onClick={() => onNavigate('smart-assistant')}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm font-medium transition-colors ${
              activeView === 'smart-assistant'
                ? 'bg-[var(--color-primary)] text-white'
                : 'text-[var(--color-primary-emphasis)] hover:bg-[var(--color-surface-2)]'
            }`}
            title="المساعد الذكي"
          >
            <Sparkles className="w-4 h-4" />
            <span className="hidden sm:inline">المساعد الذكي</span>
          </button>
          
          {/* شريط الإجراءات السريعة — رفٌّ عائم قابل للإرساء (T-WIN) */}
          <ActionBarRail user={user} onNavigate={onNavigate} />
        </div>
        <div className="flex items-center gap-3 ms-auto">
          {/* العناصر المنقولة من الشريط السفلي */}
          <div className="hidden xl:flex items-center gap-2 text-xs text-[var(--color-text-muted)] border-e border-[var(--color-border)] pe-3 me-1">
            <UserIcon className="w-3.5 h-3.5" />
            <span className="font-semibold text-[var(--color-text)]">{user.name}</span>
            <span className="text-[var(--color-border)]">|</span>
            <span>الدور: {user.role === 'manager' ? 'مدير' : user.role === 'procurement' ? 'مشتريات' : 'موظف'}</span>
            <span className="text-[var(--color-border)]">|</span>
            <Calendar className="w-3.5 h-3.5" />
            <span>{formatDateValue(new Date())}</span>
            <span className="text-[var(--color-border)]">|</span>
            <span>السنة المالية {new Date().getFullYear()}</span>
          </div>

          <GlobalSearch userRole={user.role} onNavigate={onNavigate} />
          {/* ما الجديد — لوحة تشرح آخر التحديثات */}
          <WhatsNewButton />
          <button
            type="button"
            onClick={openPlatformNotes}
            className="flex items-center justify-center rounded-md p-1.5 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)]"
            title="ملاحظة / تذكير على الصفحة الحالية"
            aria-label="ملاحظة أو تذكير على الصفحة الحالية"
          >
            <NotebookPen className="h-4 w-4" />
          </button>
          {/* إشعارات الموقع (الجرس) — تذكيرات الزبائن/الشحنات */}
          <NotificationCenter currentUserId={user.id} onNavigate={onNavigate} />
          {/* ثوابت المجموعة — زر مرئي بديل للمفتاح F11 */}
          {onOpenGroupConstants && (
            <button
              type="button"
              onClick={onOpenGroupConstants}
              className="p-1.5 rounded-md text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)] transition-colors flex items-center justify-center"
              title="ثوابت المجموعة (F11)"
              aria-label="ثوابت المجموعة"
            >
              <SlidersHorizontal className="w-4 h-4" />
            </button>
          )}
          {/* task16 E15: حاسبة بأيقونة — تفتح عند الطلب فقط */}
          <KitCalculatorButton />
          <DensitySwitch value={density} onChange={setDensity} />
          <PriceVisibilityToggle />
          <ThemeToggle />
          <button
            onClick={() => openInNewTab(
              window.location.pathname + window.location.search + window.location.hash,
              VIEW_LABELS[activeView] ?? undefined,
            )}
            className="p-1.5 rounded-md text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)] transition-colors flex items-center justify-center"
            title="فتح في علامة تبويب جديدة (تكرار الصفحة)"
            aria-label="تكرار الصفحة"
          >
            <Copy className="w-4 h-4" />
          </button>
          <div className="w-px h-4 bg-[var(--color-border)] mx-1"></div>
          <button
            onClick={async () => {
              if (await confirm({ message: 'هل تريد تأكيد تسجيل الخروج؟' })) {
                logout();
              }
            }}
            className="p-1.5 rounded-md text-[var(--color-danger)] hover:bg-[color-mix(in_srgb,var(--color-danger)_10%,transparent)] transition-colors flex items-center justify-center"
            title="تسجيل الخروج"
            aria-label="تسجيل الخروج"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="app-workspace flex flex-1 min-h-0 overflow-hidden">
        <Sidebar user={user} activeView={activeView} setView={onNavigate} />

        <div className="app-main flex flex-col flex-1 min-w-0">
          {/* شريط الوصول السريع — رجوع + المسار + الاختصارات + مرسى المرشد،
              يُطوى بضغطة (أو Ctrl+F1) ويُحفظ الاختيار لصاحبه. */}
          <QuickAccessBar
            activeView={activeView}
            onNavigate={onNavigate}
            listPath={listPath}
            userId={user.id}
          />
          <ManagedBookBanner />
          <SubscriptionExpiryBanner />
          <main className="app-content overflow-auto flex-1">
            {children}
          </main>
        </div>
      </div>

      {/* مرشد رحلة الاستيراد — يرافق المستخدم في كل الشاشات حتى الفاتورة الدولية */}
      <ImportJourneyGuide />

      {/* قائمة زر الفأرة اليمنى العامّة — تعمل في كامل الموقع (تُستثنى الحقول والقوائم الموضعية) */}
      <GlobalContextMenu user={user} onNavigate={onNavigate} />
      {notesTarget && (
        <div
          className="ktra-overlay-mask z-[70] flex items-center justify-center p-3"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setNotesTarget(null);
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="platform-notes-title"
            className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--elev-5)]"
          >
            <header className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
              <div>
                <h2 id="platform-notes-title" className="text-sm font-bold">ملاحظات وتذكيرات الصفحة</h2>
                <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{notesTarget.target_label}</p>
              </div>
              <button
                type="button"
                autoFocus
                className="ktra-toolbtn"
                onClick={() => setNotesTarget(null)}
                aria-label="إغلاق ملاحظات الصفحة"
              >
                إغلاق
              </button>
            </header>
            <div className="overflow-y-auto">
              <CustomerNotesTab target={notesTarget} />
            </div>
          </section>
        </div>
      )}
    </div>
  );
};
