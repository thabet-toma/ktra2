/**
 * ISSUE #114 (مواصفة #108 §١١) — طباعة الطلبية.
 *
 * الترويسةُ القائمة (هوية الشركة عبر `useTenantSettings`) كما هي بلا تغيير.
 * مهلةُ الردّ تُطبع **إن حُدِّدت فقط** — تختفي بلا سطرٍ فارغ حين تُترَك.
 * **لا خانة توقيعٍ للمورد**: الرابطُ الخارجي (#115) يوقّع باسمٍ وIP، وخانةُ
 * توقيعٍ على ورقةٍ تُصوَّر وتُرسَل واتساب شكلٌ بلا أثر.
 *
 * جدول البنود يُبنى بحمولة `utils/purchaseRfqPrintPayload.ts` —
 * `getPrintColumns('rfq')` — فـ«السعر التقديري» غائبٌ لأنه لا يدخل باني
 * الحمولة أصلاً، لا لأن الشاشة تخفي عموداً.
 */
import React from 'react';
import { Printer, X, FileText } from 'lucide-react';
import type { PurchaseRFQDto } from '../../../services/procurementDocumentsApi';
import { useAuth } from '../../../contexts/AuthContext';
import { useTenantSettings } from '../../../hooks/useTenantSettings';
import { buildPurchaseRfqPrintRows, purchaseRfqPrintColumns } from '../../../utils/purchaseRfqPrintPayload';
import { formatDateValue } from '../../../utils/formatDate';
import { formatQuantity } from '../../../utils/formatNumber';

interface Props {
  rfq: PurchaseRFQDto;
  onClose?: () => void;
}

const SCOPE_TITLE: Record<PurchaseRFQDto['scope'], string> = {
  local: 'طلبية شراء',
  import: 'طلبية استيراد',
};

export const PurchaseRFQPrintView: React.FC<Props> = ({ rfq, onClose }) => {
  const { currentUser } = useAuth();
  const { identity } = useTenantSettings();

  const handlePrint = () => window.print();

  const columns = purchaseRfqPrintColumns();
  const rows = buildPurchaseRfqPrintRows(rfq);

  const cellText = (value: unknown, key: string): string => {
    if (value === undefined || value === null || value === '') return '-';
    if (key === 'quantity') return formatQuantity(value);
    return String(value);
  };

  return (
    <div className="fixed inset-0 z-50 ktra-bg-panel flex justify-center overflow-auto py-8 print:p-0 print:ktra-bg-field print:static print:block" dir="rtl">
      <style>
        {`
          @media print {
            @page { size: A4; margin: 10mm; }
            body * { visibility: hidden; }
            #print-portal, #print-portal * { visibility: visible; }
            #print-portal {
              position: absolute; left: 0; top: 0; width: 100%; margin: 0; padding: 0;
              background: white;
            }
            .no-print, .no-print * { display: none !important; visibility: hidden !important; }
            * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
          }
        `}
      </style>

      <div className="fixed top-4 right-4 flex gap-2 no-print z-[60]">
        <button onClick={handlePrint} className="flex items-center gap-2 ktra-bg-panel text-white px-4 py-2 rounded-full shadow-lg hover:ktra-bg-panel font-bold text-sm">
          <Printer size={16} /> طباعة الطلبية
        </button>
        {onClose && (
          <button onClick={onClose} className="flex items-center gap-2 ktra-bg-field ktra-text-ink px-4 py-2 rounded-full shadow-lg hover:ktra-bg-panel border ktra-border-soft font-bold text-sm">
            <X size={16} /> إغلاق
          </button>
        )}
      </div>

      <div
        id="print-portal"
        className="w-[210mm] min-h-[297mm] ktra-bg-field shadow-2xl p-8 relative flex flex-col ktra-text-ink print:shadow-none print:w-full print:h-auto font-sans"
      >
        {/* الترويسة — هوية الشركة كما هي */}
        <div className="flex justify-between items-center border-b-2 ktra-border-soft pb-4 mb-4">
          <div className="flex gap-4 items-center">
            {identity?.logo_url ? (
              <img src={identity.logo_url} alt="شعار الشركة" className="w-14 h-14 rounded-xl object-cover border ktra-border-soft" />
            ) : (
              <div className="ktra-bg-panel text-white p-3 rounded-xl">
                <FileText size={28} />
              </div>
            )}
            <div>
              {identity?.company_name_primary && (
                <div className="text-lg font-black ktra-text-ink leading-tight">{identity.company_name_primary}</div>
              )}
              {(identity?.address || identity?.phone) && (
                <div className="text-[10px] ktra-text-soft">
                  {[identity?.address, identity?.phone && `هاتف: ${identity.phone}`].filter(Boolean).join(' — ')}
                </div>
              )}
              <h1 className={`font-black ktra-text-ink leading-none ${identity?.company_name_primary ? 'text-base mt-1' : 'text-2xl'}`}>
                {SCOPE_TITLE[rfq.scope]}
              </h1>
              <p className="text-xs font-bold ktra-text-soft mt-1">PURCHASE RFQ</p>
            </div>
          </div>

          <div className="text-left text-xs space-y-1">
            <div className="flex gap-2 justify-end"><span className="font-bold ktra-text-ink text-sm">{rfq.rfq_number || 'مسودة'}</span> <span className="ktra-text-soft">REF:</span></div>
            <div className="flex gap-2 justify-end"><span className="font-medium ktra-text-ink">{formatDateValue(rfq.rfq_date)}</span> <span className="ktra-text-soft">DATE:</span></div>
            {currentUser?.name && (
              <div className="flex gap-2 justify-end"><span className="font-medium ktra-text-ink">{currentUser.name}</span> <span className="ktra-text-soft">USER:</span></div>
            )}
          </div>
        </div>

        {/* مهلة الردّ — تظهر إن حُدِّدت فقط */}
        {rfq.reply_deadline && (
          <div className="mb-4 border ktra-border-soft rounded-lg px-3 py-2 flex items-center justify-between text-xs ktra-bg-panel">
            <span className="ktra-text-soft font-bold">مهلة الردّ:</span>
            <span className="font-bold ktra-text-ink">{formatDateValue(rfq.reply_deadline)}</span>
          </div>
        )}

        {/* جدول البنود */}
        <div className="mb-4 border ktra-border-soft rounded-lg overflow-hidden shadow-sm">
          <table className="w-full text-right border-collapse">
            <thead className="ktra-bg-panel text-white text-[10px] font-bold">
              <tr>
                {columns.map((col) => (
                  <th key={col.key} className="py-2 px-3 border-r ktra-border-soft last:border-r-0">
                    {col.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="text-[11px]">
              {rows.map((row, index) => (
                <tr key={index} className="border-b ktra-border-soft last:border-0 hover:ktra-bg-panel">
                  {columns.map((col) => (
                    <td key={col.key} className="py-2 px-3 border-l ktra-border-soft last:border-l-0">
                      {cellText((row as Record<string, unknown>)[col.key], col.key)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ملاحظات داخلية */}
        {rfq.notes && (
          <div className="mb-4 border ktra-border-soft rounded-lg p-3 ktra-bg-panel text-[11px]">
            <span className="font-bold ktra-text-soft block mb-1">ملاحظات:</span>
            <p className="font-bold ktra-text-ink leading-relaxed">{rfq.notes}</p>
          </div>
        )}

        {/* لا خانة توقيع للمورد — الرابط الخارجي يوقّع باسمٍ وIP */}

        <div className="mt-auto pt-4 border-t ktra-border-soft flex justify-between text-[10px] ktra-text-soft font-medium">
          <p>Internal Secure Document - Unauthorized sharing is prohibited</p>
          <p>Generated: {new Date().toLocaleString('en-GB')}</p>
        </div>
      </div>
    </div>
  );
};
