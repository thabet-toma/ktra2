/**
 * N4-T9 — SupplierPaymentsPage (N-F4، جديد) «سند صرف»
 * Ref: task5.md:744-746 + المعاملات المالية.txt:1-80
 *
 * مرآة N4-T4 (CustomerPayments) لكن للموردين:
 *   - Dr Accounts Payable (المورد) / Cr Cash/Bank
 *   - يَدعم نقد + شيكات + خصم المصدر (withholding) + توزيع على فواتير شراء
 *
 * يَعتمد على N8-T12 backend (SupplierPayment + endpoint /purchase/payments/).
 * نموذج الإنشاء مستخرَج في {@link NewSupplierPaymentModal} ويُعاد استخدامه في
 * بطاقة الشريك (كبسة «سند صرف جديد» على المورد).
 */
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { apiGetList } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { accountingApi } from "../../services/accountingApi";
import {
  AseelDocumentShell,
  AseelDenseTable,
  useAseelKeymap,
  type DenseColumn,
  type AseelToolbarAction,
  type AseelTab,
} from "../aseel";
import { Plus, X, RefreshCw, AlertTriangle, Banknote } from "lucide-react";
import { NewSupplierPaymentModal } from "./NewSupplierPaymentModal";

type Partner = { id: number; name: string };
type Account = { id: number; code: string; name: string; account_type?: string };

interface SupplierPaymentRow {
  id: number;
  partner: number;
  partner_name?: string;
  payment_date: string;
  amount: string;
  cash_or_bank_account: number;
  is_posted: boolean;
  journal?: number | null;
  notes?: string | null;
}

import { formatMoney } from "@/utils/formatNumber";
const fmt = (n: string | number) => formatMoney(n);

export const SupplierPaymentsPage: React.FC = () => {
  const navigate = useNavigate();
  const [payments, setPayments] = useState<SupplierPaymentRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [search, setSearch] = useState(
    () => new URLSearchParams(window.location.search).get("payment_id") || "",
  );
  const [showForm, setShowForm] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    const tenantId = resolveTenantId();
    try {
      const [pays, parts, accs] = await Promise.allSettled([
        // T-V1: المسار الصحيح المُسجَّل (api/logistics/supplier-payments/) —
        // كان يستدعي purchase/payments/ غير الموجود فيفشل بـ 404 عند الفتح.
        apiGetList<SupplierPaymentRow>("logistics/supplier-payments/", { tenantId }),
        accountingApi.getPartners() as Promise<Partner[]>,
        accountingApi.getAccounts() as Promise<Account[]>,
      ]);
      if (pays.status === "fulfilled") setPayments(pays.value || []);
      if (parts.status === "fulfilled") setPartners(parts.value || []);
      if (accs.status === "fulfilled") setAccounts(accs.value || []);
      if (pays.status === "rejected") {
        setErr(pays.reason instanceof Error ? pays.reason.message : "فشل تحميل سندات الصرف");
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useAseelKeymap({
    F2: () => window.print(),
    F5: () => void load(),
    Escape: () => {
      if (showForm) {
        setShowForm(false);
      } else {
        navigate(-1);
      }
    },
    CtrlIns: () => setShowForm(true),
  });

  const filtered = payments.filter((p) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (p.partner_name || "").toLowerCase().includes(s) || String(p.id).includes(s);
  });

  const partnerName = (id: number) => partners.find((p) => p.id === id)?.name || `#${id}`;
  const accountName = (id: number) => {
    const a = accounts.find((x) => x.id === id);
    return a ? `${a.code} ${a.name}` : `#${id}`;
  };

  const columns: DenseColumn<SupplierPaymentRow>[] = [
    { key: "id", header: "#", width: "60px", align: "center", render: (r) => <span className="font-mono text-xs">#{r.id}</span> },
    { key: "payment_date", header: "التاريخ", width: "110px", align: "center", render: (r) => <span className="text-xs">{r.payment_date}</span> },
    { key: "supplier", header: "المورد", render: (r) => <span className="text-xs" data-ctx-partner-id={r.partner ?? undefined} data-ctx-partner-name={r.partner_name || partnerName(r.partner)} data-ctx-partner-kind="supplier">{r.partner_name || partnerName(r.partner)}</span> },
    { key: "amount", header: "المبلغ", width: "120px", align: "left", numeric: true, render: (r) => <span className="aseel-num font-mono text-xs font-semibold">{fmt(r.amount)}</span> },
    { key: "cash_account", header: "الصندوق", render: (r) => <span className="text-xs">{accountName(r.cash_or_bank_account)}</span> },
    {
      key: "status", header: "الحالة", width: "100px", align: "center",
      render: (r) => (
        <span
          style={{
            fontSize: "11px",
            fontWeight: 600,
            color: r.is_posted ? "var(--aseel-ok, #2d7d46)" : "var(--aseel-warn, #b06800)",
          }}
        >
          {r.is_posted ? `مرحَّل ${r.journal ? "#" + r.journal : ""}` : "مسودة"}
        </span>
      ),
    },
  ];

  const totalPending = payments.filter((p) => !p.is_posted).reduce((s, p) => s + Number(p.amount), 0);
  const totalPosted = payments.filter((p) => p.is_posted).reduce((s, p) => s + Number(p.amount), 0);

  const actions: AseelToolbarAction[] = [
    { key: "new", label: "سند صرف جديد (Ctrl+Ins)", icon: <Plus />, onClick: () => setShowForm(true) },
    {
      key: "refresh",
      label: "تحديث",
      icon: <RefreshCw className={loading ? "animate-spin" : ""} />,
      onClick: () => void load(),
      separatorBefore: true,
    },
    {
      key: "cancel",
      label: "إلغاء",
      icon: <X />,
      onClick: () => {
        if (showForm) {
          setShowForm(false);
        } else {
          navigate(-1);
        }
      },
      danger: true,
      separatorBefore: true,
    },
  ];

  const tabs: AseelTab[] = [
    {
      key: "list",
      label: "سندات الصرف",
      content: (
        <div style={{ padding: "8px" }}>
          {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
          {msg && <div className="aseel-banner" style={{ marginBottom: "8px", color: "var(--aseel-ok, #2d7d46)" }}>{msg}</div>}

          <div className="aseel-banner" style={{ marginBottom: "8px", background: "var(--aseel-surface-2, #f4ede0)", fontSize: "11px", padding: "8px 12px" }}>
            <AlertTriangle className="w-3 h-3 inline" style={{ marginInlineEnd: "4px", color: "var(--aseel-warn, #b06800)" }} />
            يُسجَّل المبلغ الإجمالي المصروف ويُرحَّل (Dr ذمم المورد / Cr الصندوق).
            تفصيل الشيكات وخصم المصدر لا يُحفظان بعد (نموذج مبسّط) — قيد التطوير.
          </div>

          <AseelDenseTable<SupplierPaymentRow>
            columns={columns}
            rows={filtered}
            getRowKey={(r) => r.id}
            loading={loading}
            emptyHint="لا سندات صرف — اضغط Ctrl+Ins للإضافة"
          />
        </div>
      ),
    },
  ];

  return (
    <div style={{ minHeight: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title="سندات الصرف للموردين"
        state={`${filtered.length} سند`}
        actions={actions}
        header={
          <label className="aseel-field" style={{ flex: 1, minWidth: "200px" }}>
            <span className="aseel-field-label">بحث (مورد / رقم)</span>
            <input
              className="aseel-input"
              data-aseel-field="search"
              placeholder="بحث... (F6)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        }
        tabs={tabs}
        status={
          <>
            <span className="aseel-status-item"><Banknote className="w-3 h-3 inline" /> {filtered.length} سند</span>
            <span className="aseel-status-item">مرحَّل <b className="aseel-num">{fmt(totalPosted)}</b></span>
            <span className="aseel-status-item" style={{ color: "var(--aseel-warn, #b06800)" }}>
              مسودة <b className="aseel-num">{fmt(totalPending)}</b>
            </span>
          </>
        }
      />

      {showForm && (
        <NewSupplierPaymentModal
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false);
            setMsg("✓ تم إنشاء سند الصرف وترحيله");
            void load();
          }}
        />
      )}
    </div>
  );
};
