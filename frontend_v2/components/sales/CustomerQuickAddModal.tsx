import React, { useEffect, useState } from "react";
import { X, Save, UserPlus, Loader2, AlertTriangle } from "lucide-react";
import { apiGetList, apiPostObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { eventBus } from "../../utils/eventBus";
import { uiLog } from "../../utils/uiLog";

/**
 * task16: مودال إضافة عميل سريع من محرر فاتورة المبيعات.
 *
 * كان زر «إضافة عميل» يفتح `SupplierModal` (يُنشئ مورداً!) — هنا نُنشئ شريكاً من
 * نوع Customer مباشرة عبر `partners/` (نفس مسار صفحة العملاء)، ثم نبثّ حدث
 * partners لتحديث قوائم العملاء، ونعيد العميل المُنشأ ليُختار في الفاتورة.
 *
 * T-QUICKPARTY: النافذة تُفتح بالاسم الذي كتبه المستخدم في حقل العميل
 * (`initialName`)، فالكتابة لا تُعاد مرتين. والاسم وحده إلزامي — النوع محسوم
 * (عميل) لأن المُنادي فاتورة مبيعات، والباقي يُكمَّل لاحقاً من بطاقة العميل.
 *
 * وفحصُ تكرارٍ قبل الحفظ (لا بعده): الاسم — بعد سكونٍ قصير — يسأل الخادم عن
 * أطراف باسم قريب عبر `partners/lookup/?search=` الذي يبحث في كل الأنواع وفي
 * كامل الشركة (لا في الـ500 المحمَّلة في الشاشة وحدها). سببه أن أشهر شكوى على هذا
 * المسار في المنتجات المحترفة هي عميلٌ ثانٍ يُخلق من خطأ طباعي؛ فالتحذير
 * يظهر ومعه زرُّ «اختره» — تحذيرٌ لا منع، لأن اسمين متطابقين لطرفين مختلفين
 * أمرٌ واقع.
 */
export interface QuickAddedCustomer {
  id: number;
  name: string;
  partner_type?: string;
  credit_limit?: string | null;
  linked_account?: number | null;
  phone?: string | null;
}

/** طرفٌ قائم باسم قريب — مرشّح لأن يكون هو المقصود بدل إنشاء نسخة ثانية. */
interface SimilarPartner {
  id: number;
  name: string;
  partner_type?: string;
  phone?: string | null;
  credit_limit?: string | null;
  linked_account?: number | null;
}

/**
 * كلمة البحث عن الشبيه: أطول كلمة في الاسم (٣ أحرف فأكثر)، وإلا الاسم كاملاً.
 *
 * بحث الخادم `name__icontains` يطابق **احتواءً**، فإرسال الاسم كاملاً يمسك
 * «زبون الاختبار» حين يُكتب «زبون» ويفوّته حين يُكتب «زبون الاختبار الجديد» —
 * وهذا هو الاتجاه الأخطر (الاسم الأطول هو ما يكتبه من لا يعرف أن الطرف مسجَّل).
 * أطولُ كلمة هي أميز ما في الاسم عادةً، فتمسك الاتجاهين بنداءٍ واحد.
 */
const similarityTerm = (name: string): string => {
  const words = name.trim().split(/\s+/).filter((w) => w.length >= 3);
  if (words.length === 0) return name.trim();
  return words.reduce((longest, w) => (w.length > longest.length ? w : longest));
};

const PARTY_LABELS: Record<string, string> = {
  Customer: "عميل",
  Supplier: "مورد",
  FreightForwarder: "وكيل شحن",
  CustomsBroker: "مخلّص",
  LocalTransporter: "ناقل محلي",
  Carrier: "ناقل",
};

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSaveSuccess: (customer: QuickAddedCustomer) => void;
  /** T-QUICKPARTY: الاسم المكتوب في حقل العميل — يُعبَّأ مسبقاً. */
  initialName?: string;
}

export const CustomerQuickAddModal: React.FC<Props> = ({ isOpen, onClose, onSaveSuccess, initialName }) => {
  const [name, setName] = useState(initialName || "");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [creditLimit, setCreditLimit] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [similar, setSimilar] = useState<SimilarPartner[]>([]);

  /* فحص التكرار: مؤجَّل 350مللي كي لا يُنادى الخادم على كل ضغطة مفتاح، ومحروس
     بـ`alive` كي لا تكتب استجابةٌ متأخّرة فوق نتيجة اسمٍ أحدث. */
  useEffect(() => {
    const term = name.trim();
    if (!isOpen || term.length < 2) {
      setSimilar([]);
      return;
    }
    let alive = true;
    const timer = window.setTimeout(() => {
      apiGetList<SimilarPartner>("partners/lookup/", {
        tenantId: resolveTenantId(),
        query: { search: similarityTerm(term), limit: 5 },
      })
        .then((rows) => { if (alive) setSimilar(rows || []); })
        .catch(() => { if (alive) setSimilar([]); });
    }, 350);
    return () => { alive = false; window.clearTimeout(timer); };
  }, [name, isOpen]);

  if (!isOpen) return null;

  const selectExisting = (row: SimilarPartner) => {
    uiLog.info("اختير طرف قائم بدل إنشاء عميل مكرّر.", { id: row.id, typed: name.trim() });
    onSaveSuccess({
      id: row.id,
      name: row.name,
      partner_type: row.partner_type,
      credit_limit: row.credit_limit ?? null,
      linked_account: row.linked_account ?? null,
      phone: row.phone ?? null,
    });
  };

  const handleSave = async () => {
    if (!name.trim()) {
      setErr("اسم العميل مطلوب.");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      const credit = creditLimit.trim() === "" ? null : Number(creditLimit);
      const payload: Record<string, unknown> = {
        name: name.trim(),
        partner_type: "Customer",
        phone: phone.trim() || null,
        email: email.trim() || null,
        credit_limit: credit != null && !Number.isNaN(credit) ? String(credit) : null,
      };
      const created = (await apiPostObject("partners/", payload, {
        tenantId: resolveTenantId(),
      })) as SimilarPartner;
      uiLog.info("أُنشئ عميل من محرّر الفاتورة.", { id: created.id });
      // حدّث قوائم العملاء في الشاشات المشتركة
      eventBus.publish("partners");
      onSaveSuccess({
        id: created.id,
        name: created.name || name.trim(),
        partner_type: created.partner_type || "Customer",
        credit_limit: created.credit_limit ?? null,
        linked_account: created.linked_account ?? null,
        phone: created.phone ?? null,
      });
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل حفظ العميل.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
      dir="rtl"
    >
      <div className="bg-[var(--color-surface)] rounded-xl shadow-2xl w-full max-w-md border border-[var(--color-border)]">
        <div className="p-4 border-b border-[var(--color-border)] flex justify-between items-center">
          <h2 className="text-lg font-bold text-[var(--color-text)] flex items-center gap-2">
            <UserPlus className="w-5 h-5 text-blue-500" />
            إضافة عميل جديد
          </h2>
          <button onClick={onClose} className="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-text-muted)] rounded-full">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {err && (
            <div className="p-2.5 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-600 dark:text-red-400 text-sm">
              {err}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium mb-1">الاسم <span className="text-red-500">*</span></label>
            <input
              autoFocus
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") void handleSave(); }}
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500"
              placeholder="اسم العميل"
            />
          </div>

          {similar.length > 0 && (
            <div
              data-testid="quick-add-similar"
              className="p-2.5 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg space-y-1.5"
            >
              <div className="flex items-center gap-1.5 text-amber-700 dark:text-amber-400 text-xs font-bold">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                أطراف مسجَّلة باسم قريب — اختره بدل إنشاء نسخة ثانية
              </div>
              {similar.map((row) => {
                const isCustomer = (row.partner_type || "") === "Customer";
                return (
                  <div key={row.id} className="flex items-center justify-between gap-2 text-xs">
                    <span className="text-[var(--color-text)] truncate">
                      #{row.id} — {row.name}
                      <span className="text-[var(--color-text-muted)]">
                        {" "}({PARTY_LABELS[row.partner_type || ""] || "طرف"}{row.phone ? ` · ${row.phone}` : ""})
                      </span>
                    </span>
                    {isCustomer ? (
                      <button
                        type="button"
                        onClick={() => selectExisting(row)}
                        className="shrink-0 px-2 py-0.5 bg-amber-600 text-white rounded font-medium hover:bg-amber-700"
                      >
                        اختره
                      </button>
                    ) : (
                      // ليس عميلاً — لا يظهر في قائمة عملاء الفاتورة أصلاً، فاختياره
                      // هنا كان سيُسند مُعرّفاً يعود الحقل بعده فارغاً.
                      <span className="shrink-0 text-[var(--color-text-muted)]">ليس عميلاً</span>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1">الهاتف</label>
              <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">حد الائتمان</label>
              <input type="number" value={creditLimit} onChange={(e) => setCreditLimit(e.target.value)}
                placeholder="0.00"
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">البريد الإلكتروني</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-blue-500" />
          </div>
        </div>

        <div className="p-4 border-t border-[var(--color-border)] flex justify-end gap-2">
          <button onClick={onClose}
            className="px-4 py-2 bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text)] rounded-lg hover:bg-[var(--color-surface-2)] font-medium">
            إلغاء
          </button>
          <button onClick={handleSave} disabled={saving} data-testid="quick-add-save"
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            حفظ
          </button>
        </div>
      </div>
    </div>
  );
};
