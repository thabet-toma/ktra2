import React, { useState } from "react";
import { X, Save, UserPlus, Loader2 } from "lucide-react";
import { apiPostObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { eventBus } from "../../utils/eventBus";

/**
 * task16: مودال إضافة عميل سريع من محرر فاتورة المبيعات.
 *
 * كان زر «إضافة عميل» يفتح `SupplierModal` (يُنشئ مورداً!) — هنا نُنشئ شريكاً من
 * نوع Customer مباشرة عبر `partners/` (نفس مسار صفحة العملاء)، ثم نبثّ حدث
 * partners لتحديث قوائم العملاء، ونعيد العميل المُنشأ ليُختار في الفاتورة.
 */
export interface QuickAddedCustomer {
  id: number;
  name: string;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSaveSuccess: (customer: QuickAddedCustomer) => void;
}

export const CustomerQuickAddModal: React.FC<Props> = ({ isOpen, onClose, onSaveSuccess }) => {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [creditLimit, setCreditLimit] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!isOpen) return null;

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
      })) as { id: number; name?: string };
      // حدّث قوائم العملاء في الشاشات المشتركة
      eventBus.publish("partners");
      onSaveSuccess({ id: created.id, name: created.name || name.trim() });
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
          <button onClick={handleSave} disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium disabled:opacity-50">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            حفظ
          </button>
        </div>
      </div>
    </div>
  );
};
