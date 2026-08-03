/**
 * تنبيه ملاحظة عاجلة على طرف المعاملة — عميلاً كان أو مورداً.
 *
 * الملاحظة ذات الأولوية «عاجل» غير المنجزة التي حلّ موعدها (أو تأخّر عنه) يجب أن
 * تظهر لكل مستخدم يفتح معاملة لهذا الطرف، لا لصاحبها وحده. مصدر حقيقة واحد
 * (`customer-notes/alerts/`) يخدم فاتورة البيع وفاتورة الشراء وسندي القبض/الصرف
 * فلا يتكرّر منطق الاستحقاق في كل شاشة (DRY).
 */
import React, { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { fetchPartnerNoteAlerts, type PartnerNoteAlertRow } from '../../services/customerNotesApi';
import { formatDateLocalized } from '../../utils/formatDate';
import { clientLogger } from '../../services/logger';

export interface PartnerNoteAlertProps {
  /** معرّف طرف المعاملة — بلا معرّف لا يُستدعى الخادم ولا يُعرَض شيء. */
  partnerId?: number | string | null;
  className?: string;
}

export const PartnerNoteAlert: React.FC<PartnerNoteAlertProps> = ({ partnerId, className }) => {
  const [alerts, setAlerts] = useState<PartnerNoteAlertRow[]>([]);

  useEffect(() => {
    if (partnerId == null || partnerId === '') { setAlerts([]); return; }
    let alive = true;
    fetchPartnerNoteAlerts(partnerId)
      .then((rows) => {
        if (!alive) return;
        setAlerts(rows || []);
        if (rows?.length) {
          clientLogger.info('partner.note_alert_shown', {
            partner: String(partnerId), count: rows.length,
          });
        }
      })
      .catch(() => { if (alive) setAlerts([]); });
    return () => { alive = false; };
  }, [partnerId]);

  if (alerts.length === 0) return null;

  return (
    <div
      dir="rtl"
      role="alert"
      className={`rounded-lg border-2 border-red-500 bg-red-50 p-3 dark:bg-red-900/20 ${className || ''}`}
    >
      <div className="mb-1 flex items-center gap-1.5 text-sm font-bold text-red-700 dark:text-red-300">
        <AlertTriangle className="h-4 w-4" />
        ملاحظة عاجلة على هذا الطرف ({alerts.length})
      </div>
      <ul className="space-y-1">
        {alerts.map((note) => (
          <li key={note.id} className="text-xs text-red-800 dark:text-red-200">
            <b>{note.title}</b>
            <span className="text-[10px] opacity-80"> — استحقّت {formatDateLocalized(note.remind_on)}</span>
            {note.body && <div className="whitespace-pre-wrap opacity-90">{note.body}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default PartnerNoteAlert;
