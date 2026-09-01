/**
 * FEAT-1 — PurchaseSettingsPage: إعدادات الشراء (استراتيجية التسعير التلقائي).
 *
 * مرآة SalesSettingsPage للجانب الشرائي. تتحكّم في كيفية تعبئة سعر الوحدة
 * تلقائياً عند اختيار منتج في بند فاتورة الشراء (آخر سعر شراء / أقل سعر شراء).
 */
import React, { useCallback, useEffect, useState } from "react";
import { Loader2, Save, Info } from "lucide-react";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import { apiGetList } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { KitDocumentShell, type KitToolbarAction } from "../kit";
import { AccountTreeField } from "../accounting/AccountTreePicker";
import {
  SERIAL_ENTRY_MODE_HINT,
  SERIAL_ENTRY_MODE_OPTIONS,
  type SerialEntryMode,
} from "../../types/inventory";

type AccountOpt = { id: number; code?: string | null; name?: string | null; parent?: number | null; account_type?: string | null; is_active?: boolean };

const STRATEGIES: { value: string; label: string; hint: string }[] = [
  {
    value: "LAST_PURCHASE",
    label: "آخر سعر شراء",
    hint: "سعر الوحدة من أحدث فاتورة شراء مرحَّلة تحتوي هذا المنتج.",
  },
  {
    value: "LOWEST_PURCHASE",
    label: "أقل سعر شراء",
    hint: "أدنى سعر شراء تاريخي (كل الفترات) لهذا المنتج.",
  },
];

const PurchaseSettingsPage: React.FC = () => {
  const [strategy, setStrategy] = useState<string>("LAST_PURCHASE");
  // T-A4: الصندوق الافتراضي لفواتير الشراء.
  const [cashAccount, setCashAccount] = useState<number | null>(null);
  // استلام البضاعة للمخزن مع الترحيل، أو تأجيله لنافذة الاستلام ببنودها.
  const [receiveOnPost, setReceiveOnPost] = useState(true);
  // مستند الاستلام: تسميتاه (مرتبط/مستقل) وإتاحة المستقل والتعديل.
  const [receiptLabel, setReceiptLabel] = useState("إرسالية شراء");
  const [standaloneLabel, setStandaloneLabel] = useState("سند استلام");
  const [allowStandalone, setAllowStandalone] = useState(true);
  const [allowEditReceipt, setAllowEditReceipt] = useState(true);
  // T-SERIAL: نمط إدخال الرقم التسلسلي في بنود الشراء.
  const [serialMode, setSerialMode] = useState<SerialEntryMode>("off");
  // #34: المقابض السبعة لمحرّك التجديد — رقمان قائمان وخمسة تضبط تنبّؤ هولت.
  const [leadTimeDays, setLeadTimeDays] = useState("14");
  const [reviewPeriodDays, setReviewPeriodDays] = useState("30");
  const [forecastAlpha, setForecastAlpha] = useState("0.25");
  const [forecastBeta, setForecastBeta] = useState("0.15");
  const [forecastHistoryWeeks, setForecastHistoryWeeks] = useState("26");
  const [forecastTrendCapRatio, setForecastTrendCapRatio] = useState("0.33");
  const [forecastSafetyFactor, setForecastSafetyFactor] = useState("1.28");
  const [accounts, setAccounts] = useState<AccountOpt[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [banner, setBanner] = useState<{ ok: boolean; msg: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, accs] = await Promise.all([
        purchaseInvoiceApi.getSettings(),
        apiGetList<AccountOpt>("accounting/accounts/", { tenantId: resolveTenantId() }),
      ]);
      setStrategy(s.purchase_default_price_strategy || "LAST_PURCHASE");
      setCashAccount(s.default_cash_account ?? null);
      setReceiveOnPost(s.receive_on_post !== false);
      setReceiptLabel(s.receipt_doc_label || "إرسالية شراء");
      setStandaloneLabel(s.standalone_receipt_label || "سند استلام");
      setAllowStandalone(s.allow_standalone_receipt !== false);
      setAllowEditReceipt(s.allow_edit_receipt !== false);
      setSerialMode(s.serial_entry_mode || "off");
      setLeadTimeDays(String(s.default_lead_time_days ?? 14));
      setReviewPeriodDays(String(s.review_period_days ?? 30));
      setForecastAlpha(s.forecast_alpha ?? "0.25");
      setForecastBeta(s.forecast_beta ?? "0.15");
      setForecastHistoryWeeks(String(s.forecast_history_weeks ?? 26));
      setForecastTrendCapRatio(s.forecast_trend_cap_ratio ?? "0.33");
      setForecastSafetyFactor(s.forecast_safety_factor ?? "1.28");
      setAccounts(accs || []);
    } catch (e) {
      setBanner({ ok: false, msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setBanner(null);
    try {
      await purchaseInvoiceApi.updateSettings({
        purchase_default_price_strategy: strategy,
        default_cash_account: cashAccount,
        receive_on_post: receiveOnPost,
        receipt_doc_label: receiptLabel.trim() || "إرسالية شراء",
        standalone_receipt_label: standaloneLabel.trim() || "سند استلام",
        allow_standalone_receipt: allowStandalone,
        allow_edit_receipt: allowEditReceipt,
        serial_entry_mode: serialMode,
        default_lead_time_days: Number(leadTimeDays) || 14,
        review_period_days: Number(reviewPeriodDays) || 30,
        forecast_alpha: forecastAlpha,
        forecast_beta: forecastBeta,
        forecast_history_weeks: Number(forecastHistoryWeeks) || 26,
        forecast_trend_cap_ratio: forecastTrendCapRatio,
        forecast_safety_factor: forecastSafetyFactor,
      });
      setBanner({ ok: true, msg: "حُفظت إعدادات الشراء بنجاح." });
    } catch (e) {
      setBanner({ ok: false, msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  }, [
    strategy, cashAccount, receiveOnPost, receiptLabel, standaloneLabel,
    allowStandalone, allowEditReceipt, serialMode,
    leadTimeDays, reviewPeriodDays, forecastAlpha, forecastBeta,
    forecastHistoryWeeks, forecastTrendCapRatio, forecastSafetyFactor,
  ]);

  const actions: KitToolbarAction[] = [
    {
      key: "save",
      label: saving ? "جارٍ الحفظ…" : "حفظ",
      icon: saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />,
      onClick: handleSave,
      disabled: saving || loading,
    },
  ];

  return (
    <div className="min-h-[calc(100vh-5rem)]">
      <KitDocumentShell title="إعدادات الشراء" actions={actions}>
        {banner && (
          <div
            role="status"
            className={`ktra-banner ${banner.ok ? "ktra-banner--ok" : "ktra-banner--err"}`}
            style={{ margin: "8px" }}
          >
            {banner.msg}
          </div>
        )}
        <div className="p-4 max-w-2xl">
          <h3 className="font-bold mb-1 text-[var(--ktra-ink)]">
            استراتيجية تسعير بنود الشراء
          </h3>
          <p className="text-sm text-[var(--ktra-ink-soft)] mb-3 flex items-start gap-1">
            <Info className="h-4 w-4 mt-0.5 shrink-0" />
            <span>
              عند اختيار منتج في بند فاتورة شراء، يُقترح سعر الوحدة تلقائياً حسب
              هذه الاستراتيجية. القيمة المقترحة تبقى قابلة للتعديل دائماً، ولا
              تُدَس على سعر أدخلته يدوياً.
            </span>
          </p>

          {loading ? (
            <div className="flex items-center gap-2 text-[var(--ktra-ink-soft)]">
              <Loader2 className="h-4 w-4 animate-spin" /> جاري التحميل…
            </div>
          ) : (
            <div className="space-y-2">
              {STRATEGIES.map((s) => (
                <label
                  key={s.value}
                  className={`flex items-start gap-2 p-3 border rounded cursor-pointer ${
                    strategy === s.value
                      ? "border-[var(--ktra-accent)] bg-[var(--ktra-accent-soft,#f3f4f6)]"
                      : "border-[var(--ktra-border)]"
                  }`}
                >
                  <input
                    type="radio"
                    name="purchase_strategy"
                    value={s.value}
                    checked={strategy === s.value}
                    onChange={() => setStrategy(s.value)}
                    className="mt-1"
                  />
                  <span>
                    <b className="text-[var(--ktra-ink)]">{s.label}</b>
                    <span className="block text-sm text-[var(--ktra-ink-soft)]">
                      {s.hint}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          )}

          {/* استلام البضاعة مع الترحيل — مرآة «خصم المخزون عند الترحيل» في المبيعات. */}
          <div className="mt-6 pt-4 border-t border-[var(--ktra-border)]">
            <h3 className="font-bold mb-1 text-[var(--ktra-ink)]">استلام البضاعة مع الترحيل</h3>
            <p className="text-sm text-[var(--ktra-ink-soft)] mb-2 flex items-start gap-1">
              <Info className="h-4 w-4 mt-0.5 shrink-0" />
              <span>
                مفعّلاً: ترحيل فاتورة الشراء يُدخل كل بنودها للمستودع الافتراضي فوراً.
                معطّلاً: الترحيل محاسبي فقط، وتُستلَم البنود لاحقاً من زر «استلام
                البضاعة» داخل الفاتورة — يفتح كل البنود بالكامل ويمكن تعديل ما استُلم.
              </span>
            </p>
            <label className="flex items-center gap-2 cursor-pointer select-none text-[var(--ktra-ink)]">
              <input
                type="checkbox"
                disabled={loading}
                checked={receiveOnPost}
                onChange={(e) => setReceiveOnPost(e.target.checked)}
              />
              <span>استلام بضاعة الفاتورة للمخزن تلقائياً عند الترحيل</span>
            </label>
          </div>

          {/* مستند الاستلام: التسمية حرّة لكل شركة، والسند المستقل والتعديل اختياريان. */}
          <div className="mt-6 pt-4 border-t border-[var(--ktra-border)]">
            <h3 className="font-bold mb-1 text-[var(--ktra-ink)]">مستند الاستلام</h3>
            <p className="text-sm text-[var(--ktra-ink-soft)] mb-3 flex items-start gap-1">
              <Info className="h-4 w-4 mt-0.5 shrink-0" />
              <span>
                سمِّ المستند كما تسميه شركتك — الاسم يظهر في الشاشات والطباعة. المستند
                المرتبط بفاتورة اسم، والمستند بلا فاتورة (بضاعة وصلت قبل فاتورتها) اسم آخر.
              </span>
            </p>
            <div className="grid sm:grid-cols-2 gap-3 max-w-2xl">
              <label className="block">
                <span className="block text-sm text-[var(--ktra-ink-soft)] mb-1">
                  اسم المستند المرتبط بفاتورة
                </span>
                <input
                  className="ktra-input w-full"
                  disabled={loading}
                  value={receiptLabel}
                  onChange={(e) => setReceiptLabel(e.target.value)}
                  placeholder="إرسالية شراء"
                />
              </label>
              <label className="block">
                <span className="block text-sm text-[var(--ktra-ink-soft)] mb-1">
                  اسم المستند بلا فاتورة
                </span>
                <input
                  className="ktra-input w-full"
                  disabled={loading || !allowStandalone}
                  value={standaloneLabel}
                  onChange={(e) => setStandaloneLabel(e.target.value)}
                  placeholder="سند استلام"
                />
              </label>
            </div>
            <label className="flex items-center gap-2 cursor-pointer select-none text-[var(--ktra-ink)] mt-3">
              <input
                type="checkbox"
                disabled={loading}
                checked={allowStandalone}
                onChange={(e) => setAllowStandalone(e.target.checked)}
              />
              <span>السماح بمستند استلام بلا فاتورة مرتبطة</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer select-none text-[var(--ktra-ink)] mt-2">
              <input
                type="checkbox"
                disabled={loading}
                checked={allowEditReceipt}
                onChange={(e) => setAllowEditReceipt(e.target.checked)}
              />
              <span>السماح بتعديل/إلغاء الإرسالية بعد حفظها (يعكس أثرها ويعيد تطبيقه)</span>
            </label>
          </div>

          {/* T-SERIAL: نمط الأرقام التسلسلية في بنود الشراء — يخصّ المنتجات المتتبَّعة وحدها. */}
          <div className="mt-6 pt-4 border-t border-[var(--ktra-border)]">
            <h3 className="font-bold mb-1 text-[var(--ktra-ink)]">
              إدخال الأرقام التسلسلية في فاتورة الشراء
            </h3>
            <p className="text-sm text-[var(--ktra-ink-soft)] mb-2 flex items-start gap-1">
              <Info className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{SERIAL_ENTRY_MODE_HINT}</span>
            </p>
            <select
              className="ktra-input w-full max-w-md"
              disabled={loading}
              value={serialMode}
              onChange={(e) => setSerialMode(e.target.value as SerialEntryMode)}
            >
              {SERIAL_ENTRY_MODE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* T-A4: الصندوق الافتراضي لفواتير الشراء النقدية (مرآة إعدادات المبيعات). */}
          <div className="mt-6 pt-4 border-t border-[var(--ktra-border)]">
            <h3 className="font-bold mb-1 text-[var(--ktra-ink)]">حساب الصندوق الافتراضي (للنقدي)</h3>
            <p className="text-sm text-[var(--ktra-ink-soft)] mb-2 flex items-start gap-1">
              <Info className="h-4 w-4 mt-0.5 shrink-0" />
              <span>يُستخدم تلقائياً للدفعات النقدية في فواتير الشراء بدل اختيار صندوق لكل فاتورة.</span>
            </p>
            <div className="w-full max-w-md">
              <AccountTreeField
                accounts={accounts}
                value={cashAccount}
                onChange={(id) => setCashAccount(id)}
                purpose="cash"
                allowParents
                disabled={loading}
                placeholder="— لا شيء —"
                title="اختيار الصندوق / البنك"
              />
            </div>
          </div>

          {/* #34: المقابض السبعة لمحرّك التجديد — رقمان قائمان (المهلة/المراجعة)
              وخمسة تضبط تنبّؤ هولت والمسار التلقائي (ط11 على خريطة T-REORDER). */}
          <div className="mt-6 pt-4 border-t border-[var(--ktra-border)]">
            <h3 className="font-bold mb-1 text-[var(--ktra-ink)]">
              مقابض محرّك التجديد التلقائي
            </h3>
            <p className="text-sm text-[var(--ktra-ink-soft)] mb-3 flex items-start gap-1">
              <Info className="h-4 w-4 mt-0.5 shrink-0" />
              <span>
                تحكم في حساب البيع الأسبوعي والاتجاه وكمية الطلب المقترحة للأصناف
                الموضوعة على «تلقائي». القيم الافتراضية تناسب أغلب الحالات — عدّلها
                فقط إن شعرت أن الاقتراحات بطيئة بالتفاعل أو شديدة الحساسية.
              </span>
            </p>
            <div className="grid sm:grid-cols-2 gap-3 max-w-2xl">
              <label className="block">
                <span className="block text-sm text-[var(--ktra-ink-soft)] mb-1">
                  حساسية النظام للجديد (α)
                </span>
                <input
                  type="number" step="0.01" min="0.01" max="0.99"
                  className="ktra-input w-full"
                  disabled={loading}
                  value={forecastAlpha}
                  onChange={(e) => setForecastAlpha(e.target.value)}
                />
                <span className="block text-xs text-[var(--ktra-ink-soft)] mt-1">
                  لو حسّيته بطيء بالتفاعل زِدها، ولو بيقفز مع كل طلبية شاذّة قلّلها.
                </span>
              </label>
              <label className="block">
                <span className="block text-sm text-[var(--ktra-ink-soft)] mb-1">
                  حساسية الاتجاه (β)
                </span>
                <input
                  type="number" step="0.01" min="0.01" max="0.99"
                  className="ktra-input w-full"
                  disabled={loading}
                  value={forecastBeta}
                  onChange={(e) => setForecastBeta(e.target.value)}
                />
                <span className="block text-xs text-[var(--ktra-ink-soft)] mt-1">
                  نفس فكرة حساسية الجديد، لكن لسرعة تغيّر الاتجاه (صاعد/نازل) نفسه.
                </span>
              </label>
              <label className="block">
                <span className="block text-sm text-[var(--ktra-ink-soft)] mb-1">
                  كم أسبوعاً يرجع للوراء
                </span>
                <input
                  type="number" step="1" min="6"
                  className="ktra-input w-full"
                  disabled={loading}
                  value={forecastHistoryWeeks}
                  onChange={(e) => setForecastHistoryWeeks(e.target.value)}
                />
                <span className="block text-xs text-[var(--ktra-ink-soft)] mt-1">
                  طول السلسلة الأسبوعية التي يبني عليها الاتجاه — أقصر منها لا يكفي
                  ليستقرّ.
                </span>
              </label>
              <label className="block">
                <span className="block text-sm text-[var(--ktra-ink-soft)] mb-1">
                  سقف الاتجاه الصاعد (نسبة من البيع الأسبوعي)
                </span>
                <input
                  type="number" step="0.01" min="0.01"
                  className="ktra-input w-full"
                  disabled={loading}
                  value={forecastTrendCapRatio}
                  onChange={(e) => setForecastTrendCapRatio(e.target.value)}
                />
                <span className="block text-xs text-[var(--ktra-ink-soft)] mt-1">
                  يمنع بيعةً شاذّة واحدة من مضاعفة الحدّ المقترَح.
                </span>
              </label>
              <label className="block">
                <span className="block text-sm text-[var(--ktra-ink-soft)] mb-1">
                  حجم هامش الأمان
                </span>
                <input
                  type="number" step="0.01" min="0.01"
                  className="ktra-input w-full"
                  disabled={loading}
                  value={forecastSafetyFactor}
                  onChange={(e) => setForecastSafetyFactor(e.target.value)}
                />
                <span className="block text-xs text-[var(--ktra-ink-soft)] mt-1">
                  كلّما زاد اتّسع مخزون الأمان مقابل تذبذب دقّة التوقّعات السابقة.
                </span>
              </label>
              <label className="block">
                <span className="block text-sm text-[var(--ktra-ink-soft)] mb-1">
                  مهلة التوريد الافتراضية (يوم)
                </span>
                <input
                  type="number" step="1" min="1"
                  className="ktra-input w-full"
                  disabled={loading}
                  value={leadTimeDays}
                  onChange={(e) => setLeadTimeDays(e.target.value)}
                />
                <span className="block text-xs text-[var(--ktra-ink-soft)] mt-1">
                  تُستعمل حين لا يكفي سجلّ الطلبيات لاشتقاق مهلة المورّد فعلياً.
                </span>
              </label>
              <label className="block">
                <span className="block text-sm text-[var(--ktra-ink-soft)] mb-1">
                  فترة المراجعة (يوم)
                </span>
                <input
                  type="number" step="1" min="1"
                  className="ktra-input w-full"
                  disabled={loading}
                  value={reviewPeriodDays}
                  onChange={(e) => setReviewPeriodDays(e.target.value)}
                />
                <span className="block text-xs text-[var(--ktra-ink-soft)] mt-1">
                  كل كم يوماً تراجع الطلب — تحدّد الحدّ الأقصى المقترَح فوق نقطة الطلب.
                </span>
              </label>
            </div>
          </div>
        </div>
      </KitDocumentShell>
    </div>
  );
};

export default PurchaseSettingsPage;
