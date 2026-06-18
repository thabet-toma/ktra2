/**
 * FEAT-1 — PurchaseSettingsPage: إعدادات الشراء (استراتيجية التسعير التلقائي).
 *
 * مرآة SalesSettingsPage للجانب الشرائي. تتحكّم في كيفية تعبئة سعر الوحدة
 * تلقائياً عند اختيار صنف في بند فاتورة الشراء (آخر سعر شراء / أقل سعر شراء).
 */
import React, { useCallback, useEffect, useState } from "react";
import { Loader2, Save, Info } from "lucide-react";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import { AseelDocumentShell, type AseelToolbarAction } from "../aseel";

const STRATEGIES: { value: string; label: string; hint: string }[] = [
  {
    value: "LAST_PURCHASE",
    label: "آخر سعر شراء",
    hint: "سعر الوحدة من أحدث فاتورة شراء مرحَّلة تحتوي هذا الصنف.",
  },
  {
    value: "LOWEST_PURCHASE",
    label: "أقل سعر شراء",
    hint: "أدنى سعر شراء تاريخي (كل الفترات) لهذا الصنف.",
  },
];

const PurchaseSettingsPage: React.FC = () => {
  const [strategy, setStrategy] = useState<string>("LAST_PURCHASE");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [banner, setBanner] = useState<{ ok: boolean; msg: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const s = await purchaseInvoiceApi.getSettings();
      setStrategy(s.purchase_default_price_strategy || "LAST_PURCHASE");
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
      });
      setBanner({ ok: true, msg: "حُفظت إعدادات الشراء بنجاح." });
    } catch (e) {
      setBanner({ ok: false, msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  }, [strategy]);

  const actions: AseelToolbarAction[] = [
    {
      key: "save",
      label: saving ? "جارٍ الحفظ…" : "حفظ",
      icon: saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />,
      onClick: handleSave,
      disabled: saving || loading,
    },
  ];

  return (
    <div data-skin="aseel" className="min-h-[calc(100vh-5rem)]">
      <AseelDocumentShell title="إعدادات الشراء" actions={actions}>
        {banner && (
          <div
            role="status"
            className={`aseel-banner ${banner.ok ? "aseel-banner--ok" : "aseel-banner--err"}`}
            style={{ margin: "8px" }}
          >
            {banner.msg}
          </div>
        )}
        <div className="p-4 max-w-2xl">
          <h3 className="font-bold mb-1 text-[var(--aseel-ink)]">
            استراتيجية تسعير بنود الشراء
          </h3>
          <p className="text-sm text-[var(--aseel-ink-soft)] mb-3 flex items-start gap-1">
            <Info className="h-4 w-4 mt-0.5 shrink-0" />
            <span>
              عند اختيار صنف في بند فاتورة شراء، يُقترح سعر الوحدة تلقائياً حسب
              هذه الاستراتيجية. القيمة المقترحة تبقى قابلة للتعديل دائماً، ولا
              تُدَس على سعر أدخلته يدوياً.
            </span>
          </p>

          {loading ? (
            <div className="flex items-center gap-2 text-[var(--aseel-ink-soft)]">
              <Loader2 className="h-4 w-4 animate-spin" /> جاري التحميل…
            </div>
          ) : (
            <div className="space-y-2">
              {STRATEGIES.map((s) => (
                <label
                  key={s.value}
                  className={`flex items-start gap-2 p-3 border rounded cursor-pointer ${
                    strategy === s.value
                      ? "border-[var(--aseel-accent)] bg-[var(--aseel-accent-soft,#f3f4f6)]"
                      : "border-[var(--aseel-border)]"
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
                    <b className="text-[var(--aseel-ink)]">{s.label}</b>
                    <span className="block text-sm text-[var(--aseel-ink-soft)]">
                      {s.hint}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          )}
        </div>
      </AseelDocumentShell>
    </div>
  );
};

export default PurchaseSettingsPage;
