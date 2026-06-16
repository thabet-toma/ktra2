import React, { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiGetObject } from '../../services/restApi';
import { resolveTenantId } from '../../utils/tenantContext';
import { AseelDocumentShell, AseelTab } from '../aseel';
import { AccountingGeneralLedgerPage } from '../accounting/AccountingGeneralLedgerPage';

interface PartnerApi {
  id: number;
  name: string;
  legal_name?: string | null;
  partner_type: string;
  phone?: string | null;
  email?: string | null;
  city?: string | null;
  country?: string | null;
  street_address?: string | null;
  state_or_province?: string | null;
  postal_code?: string | null;
  tax_number?: string | null;
  credit_limit?: string | null;
  linked_account?: {
    id: number;
    code: string;
    name: string;
  };
}

export const PartnerProfilePage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [partner, setPartner] = useState<PartnerApi | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const tenantId = useMemo(() => resolveTenantId(), []);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    apiGetObject<PartnerApi>(`partners/${id}/`, { tenantId })
      .then((data) => {
        setPartner(data);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [id, tenantId]);

  const tabs: AseelTab[] = [
    {
      key: 'details',
      label: 'التفاصيل',
      content: (
        <div className="p-4 grid grid-cols-2 gap-4 text-sm">
          {partner && (
            <>
              <div><span className="text-[var(--aseel-ink-soft)]">الاسم:</span> <b>{partner.name}</b></div>
              <div><span className="text-[var(--aseel-ink-soft)]">الاسم القانوني:</span> <b>{partner.legal_name || '—'}</b></div>
              <div><span className="text-[var(--aseel-ink-soft)]">النوع:</span> <b>{partner.partner_type === 'Customer' ? 'عميل' : partner.partner_type === 'Supplier' ? 'مورد' : partner.partner_type}</b></div>
              <div><span className="text-[var(--aseel-ink-soft)]">الهاتف:</span> <b>{partner.phone || '—'}</b></div>
              <div><span className="text-[var(--aseel-ink-soft)]">البريد الإلكتروني:</span> <b>{partner.email || '—'}</b></div>
              <div><span className="text-[var(--aseel-ink-soft)]">الرقم الضريبي:</span> <b>{partner.tax_number || '—'}</b></div>
              <div><span className="text-[var(--aseel-ink-soft)]">حد الائتمان:</span> <b>{partner.credit_limit || '—'}</b></div>
              <div className="col-span-2"><span className="text-[var(--aseel-ink-soft)]">العنوان:</span> <b>{[partner.street_address, partner.city, partner.state_or_province, partner.country].filter(Boolean).join(', ') || '—'}</b></div>
            </>
          )}
        </div>
      )
    },
    {
      key: 'balance_summary',
      label: 'ملخص الرصيد',
      content: (
        <div className="p-4 text-center text-[var(--aseel-ink-soft)]">
          <p>قريباً: ملخص الأرصدة المستحقة والمدفوعات.</p>
        </div>
      )
    },
    {
      key: 'account_movement',
      label: 'حركة الحساب',
      content: (
        partner?.linked_account?.id ? (
          <div className="border border-[var(--aseel-border)] rounded overflow-hidden">
            <AccountingGeneralLedgerPage initialAccountId={partner.linked_account.id} />
          </div>
        ) : (
          <div className="p-4 text-center text-[var(--aseel-danger)]">
            لا يوجد حساب مالي مرتبط بهذا الشريك لعرض كشف الحساب.
          </div>
        )
      )
    },
    {
      key: 'invoices',
      label: 'الفواتير',
      content: (
        <div className="p-4 text-center text-[var(--aseel-ink-soft)]">
          <p>قريباً: قائمة الفواتير المرتبطة بهذا الشريك.</p>
        </div>
      )
    },
    {
      key: 'membership',
      label: 'العضوية',
      content: (
        <div className="p-4 text-center text-[var(--aseel-ink-soft)]">
          <p>قريباً: تفاصيل العضوية ونقاط الولاء.</p>
        </div>
      )
    },
    {
      key: 'timeline',
      label: 'الجدول الزمني',
      content: (
        <div className="p-4 text-center text-[var(--aseel-ink-soft)]">
          <p>قريباً: سجل نشاطات الشريك.</p>
        </div>
      )
    }
  ];

  return (
    <div data-skin="aseel" className="min-h-[calc(100vh-5rem)]">
      <AseelDocumentShell
        title={partner ? `كشف حساب: ${partner.name}` : 'جاري التحميل...'}
        actions={[
          {
            key: 'back',
            label: 'عودة',
            onClick: () => navigate(-1)
          }
        ]}
        tabs={tabs}
        status={
          error ? <span className="text-[var(--aseel-danger)]">{error}</span> :
          loading ? <span>جاري التحميل...</span> :
          <span className="aseel-status-item">{partner?.partner_type === 'Customer' ? 'عميل' : 'مورد'}</span>
        }
      >
        <></>
      </AseelDocumentShell>
    </div>
  );
};
