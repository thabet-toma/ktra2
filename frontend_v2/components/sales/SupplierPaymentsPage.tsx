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
import { Plus, X, RefreshCw, AlertTriangle, Banknote, Check, Split, Undo2 } from "lucide-react";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import { useConfirm } from "../../contexts/ConfirmContext";
import { usePermissions } from "../../contexts/PermissionsContext";
import { VoucherAllocationModal } from "../shared/VoucherAllocationModal";
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
  /** T-ONACC: التوزيع على فواتير الشراء والمتبقّي «على الحساب». */
  allocations?: Array<{ id: number; invoice: number; invoice_number?: string; amount: string }>;
  unallocated_amount?: string;
}

/** المتبقّي غير الموزَّع (محسوب في الخادم، ويُشتق احتياطاً). */
const unallocatedOf = (p: SupplierPaymentRow) =>
  p.unallocated_amount != null
    ? Number(p.unallocated_amount)
    : Number(p.amount) - (p.allocations || []).reduce((s, a) => s + Number(a.amount || 0), 0);

import { formatMoney } from "@/utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
const fmt = (n: string | number) => formatMoney(n);

export const SupplierPaymentsPage: React.FC = () => {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const { can: canPerm } = usePermissions();
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
  // T-ONACC: السند المُراد توزيعه على فواتير الشراء + الفواتير المفتوحة لمورده.
  const [allocating, setAllocating] = useState<SupplierPaymentRow | null>(null);
  const [allocDocs, setAllocDocs] = useState<Array<{ id: number; label: string; remaining: string }>>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    const tenantId = resolveTenantId();
    try {
      const [pays, parts, accs] = await Promise.allSettled([
        // T-V1: المسار الصحيح المُسجَّل (api/logistics/supplier-payments/) —
        // كان يستدعي purchase/payments/ غير الموجود فيفشل بـ 404 عند الفتح.
        // P0-5: القائمة مُرقَّمة إلزامياً — أحدث 200 سند صرف.
        apiGetList<SupplierPaymentRow>("logistics/supplier-payments/", { tenantId, query: { page: 1, page_size: 200 } }),
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

  /** T-ONACC: يفتح نافذة التوزيع بعد جلب فواتير الشراء المفتوحة لهذا المورد. */
  const openAllocation = async (row: SupplierPaymentRow) => {
    setErr(null);
    try {
      const rows = await purchaseInvoiceApi.list({
        partner: String(row.partner),
        is_posted: "true",
        page: "1", page_size: "200",
      }) as Array<{ id: number; invoice_number?: string; remaining_balance?: string }>;
      setAllocDocs(
        (rows || [])
          .filter((inv) => Number(inv.remaining_balance ?? 0) > 0.009)
          .map((inv) => ({
            id: inv.id,
            label: inv.invoice_number || `#${inv.id}`,
            remaining: String(inv.remaining_balance ?? "0"),
          })),
      );
      setAllocating(row);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "تعذّر جلب فواتير الشراء المفتوحة");
    }
  };

  const handlePost = async (id: number) => {
    setErr(null);
    try {
      await purchaseInvoiceApi.postSupplierPayment(id);
      setMsg("✓ تم ترحيل سند الصرف");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الترحيل");
    }
  };

  // T-UNPOSTRV (مرآة المورد): التراجع عن ترحيل سند مرحّل — الخادم يحذف قيوده
  // ويعيد شيكاته إلى مسودة، وتعود فواتير الشراء الموزَّع عليها «غير مسدَّدة»
  // تلقائياً (المدفوع مشتق من التوزيعات المرحّلة). السند يبقى مسودةً.
  const handleUnpost = async (p: SupplierPaymentRow) => {
    const allocCount = (p.allocations || []).length;
    const ok = await confirm({
      title: "التراجع عن ترحيل السند",
      message:
        `سيُحذف القيد المحاسبي للسند #${p.id} (${fmt(p.amount)})` +
        (allocCount > 0
          ? `، وستعود ${allocCount} فاتورة شراء «غير مسدَّدة» بقيمة توزيعها`
          : "") +
        "، ويعود السند مسودةً يمكن تعديلها أو حذفها. متابعة؟",
      confirmText: "تراجع عن الترحيل",
      danger: true,
    });
    if (!ok) return;
    setErr(null);
    try {
      await purchaseInvoiceApi.unpostSupplierPayment(p.id);
      setMsg("✓ تم التراجع عن ترحيل السند — عاد مسودة");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التراجع عن الترحيل");
    }
  };

  const partnerName = (id: number) => partners.find((p) => p.id === id)?.name || `#${id}`;
  const accountName = (id: number) => {
    const a = accounts.find((x) => x.id === id);
    return a ? `${a.code} ${a.name}` : `#${id}`;
  };

  const columns: DenseColumn<SupplierPaymentRow>[] = [
    { key: "id", header: "#", width: "60px", align: "center", render: (r) => <span className="font-mono text-xs">#{r.id}</span> },
    { key: "payment_date", header: "التاريخ", width: "110px", align: "center", render: (r) => <span className="text-xs">{formatDateLocalized(r.payment_date)}</span> },
    { key: "supplier", header: "المورد", render: (r) => <span className="text-xs" data-ctx-partner-id={r.partner ?? undefined} data-ctx-partner-name={r.partner_name || partnerName(r.partner)} data-ctx-partner-kind="supplier">{r.partner_name || partnerName(r.partner)}</span> },
    { key: "amount", header: "المبلغ", width: "120px", align: "left", numeric: true, render: (r) => <span className="aseel-num font-mono text-xs font-semibold">{fmt(r.amount)}</span> },
    {
      // T-ONACC: المتبقّي غير الموزَّع = رصيد لنا عند المورد.
      key: "unallocated", header: "على الحساب", width: "110px", align: "left", numeric: true,
      render: (r) => {
        const u = unallocatedOf(r);
        return (
          <span
            className="aseel-num font-mono text-xs"
            style={{ color: u > 0.009 ? "var(--aseel-warn, #b06800)" : "var(--aseel-ink-soft)" }}
          >
            {fmt(u)}
          </span>
        );
      },
    },
    { key: "cash_account", header: "الصندوق", render: (r) => <span className="text-xs">{accountName(r.cash_or_bank_account)}</span> },
    {
      key: "allocations", header: "التوزيعات",
      render: (r) => (
        <span className="text-[11px]">
          {r.allocations && r.allocations.length > 0
            ? r.allocations.map((a) => `${a.invoice_number || "#" + a.invoice} = ${fmt(a.amount)}`).join(" · ")
            : <span style={{ color: "var(--aseel-ink-soft)" }}>بدون توزيع</span>}
        </span>
      ),
    },
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
    {
      // T-AUTOPOST: السندات تُرحَّل فور الحفظ افتراضياً؛ زر الترحيل لمن حُفظ كمسودة.
      // T-ONACC: زر التوزيع على فواتير الشراء لمن بقي فيه رصيد على الحساب.
      key: "actions", header: "إجراءات", width: "90px", align: "center",
      render: (r) => (
        <div style={{ display: "flex", gap: "2px", justifyContent: "center" }} onClick={(e) => e.stopPropagation()}>
          {!r.is_posted && (
            <button type="button" className="aseel-toolbtn" title="ترحيل" onClick={() => void handlePost(r.id)}>
              <Check className="w-3 h-3" />
            </button>
          )}
          {r.is_posted && canPerm("purchase.payment.unpost") && (
            <button type="button" className="aseel-toolbtn" title="تراجع عن الترحيل" onClick={() => void handleUnpost(r)}>
              <Undo2 className="w-3 h-3" />
            </button>
          )}
          <button
            type="button"
            className="aseel-toolbtn"
            title="توزيع على فواتير الشراء"
            disabled={unallocatedOf(r) <= 0.009}
            onClick={() => void openAllocation(r)}
          >
            <Split className="w-3 h-3" />
          </button>
        </div>
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
          onSaved={(posted) => {
            setShowForm(false);
            setMsg(posted ? "✓ تم إنشاء سند الصرف وترحيله" : "✓ حُفظ سند الصرف كمسودة");
            void load();
          }}
        />
      )}

      {allocating && (
        <VoucherAllocationModal
          kind="supplier"
          voucher={{
            id: allocating.id,
            amount: allocating.amount,
            unallocated: unallocatedOf(allocating),
            is_posted: allocating.is_posted,
          }}
          partnerLabel={allocating.partner_name || partnerName(allocating.partner)}
          docs={allocDocs}
          onClose={() => setAllocating(null)}
          onSaved={() => {
            setAllocating(null);
            setMsg("✓ تم توزيع سند الصرف على فواتير الشراء");
            void load();
          }}
        />
      )}
    </div>
  );
};
