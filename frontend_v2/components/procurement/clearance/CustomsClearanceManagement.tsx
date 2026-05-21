import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  FileText,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  Truck,
  Loader2,
  Split,
  Search,
  CheckCircle2,
  X,
  ChevronRight,
  ChevronLeft,
  ChevronsRight,
  ChevronsLeft,
  Printer,
  FileDown,
} from "lucide-react";
import { DataGrid, Drawer } from '../../../components/ui';
import { User } from "@/types";
import { DEFAULT_CLEARANCE_COST_LINES, type ClearanceCostLine } from "@/constants/clearanceDefaults";
import {
  listClearances,
  getClearance,
  createClearance,
  updateClearance,
  listClearancePayments,
  payClearanceFromCashBox,
  formatClearanceShipmentLine,
  type ClearancePaymentRow,
  type ClearanceRow,
} from "@/services/clearanceApi";
import { apiGetList } from "@/services/restApi";
import { accountingApi, type CashBoxLedgerLink } from "@/services/accountingApi";
import { resolveTenantId } from "@/utils/tenantContext";
import { buildShipmentOptionLabel, ShipmentLabelInput } from "@/utils/shipmentLabel";
import { validatePaymentInput } from "@/utils/usePaymentForm";
import {
  AseelDocumentShell,
  useRecordNavigation,
  useAseelKeymap,
  AseelIndexPicker,
} from "../../aseel";

type ShipmentPick = ShipmentLabelInput;
type BrokerPick = { id: number; name: string; partner_type?: string };

/** يُحفَظ ضمن `cost_lines` ويُعرض في قسم منفصل عن بنود التخليص */
const SHIPPING_COST_LINE_LABEL = "دفعة الشحن (الناقل)";
/** سطر واحد عندما لا يريد المستخدم تفصيل البنود — يُجمع مع باقي السطور في الخادم */
const LUMP_CLEARANCE_LINE_LABEL = "إجمالي تكلفة التخليص";

/** يطابق الخادم `logistics/views.pay_from_cashbox`: دفعات الشحن تُوسم في الملاحظات */
function notesMeanShippingPayment(notes: string | null | undefined): boolean {
  const n = String(notes ?? "").trimStart();
  return n.startsWith("[شحن]") || n.startsWith("شحن");
}

function sumLines(lines: ClearanceCostLine[]): number {
  return lines.reduce((s, r) => s + (Number(r.amount) || 0), 0);
}

function ClearancePaymentMiniTable({
  rows,
  cashBoxDisplayName,
}: {
  rows: ClearancePaymentRow[];
  cashBoxDisplayName: (externalId: string | undefined | null) => string;
}) {
  if (!rows.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500">
            <th className="text-right py-1">التاريخ</th>
            <th className="text-right py-1">الصندوق</th>
            <th className="text-right py-1">المبلغ</th>
            <th className="text-right py-1">ملاحظة</th>
            <th className="text-right py-1">القيد</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.id} className="border-t border-gray-100/80 dark:border-gray-700/80">
              <td className="py-1.5">{p.payment_date || "-"}</td>
              <td className="py-1.5 max-w-[200px] truncate" title={p.cash_box_external_id || undefined}>
                {cashBoxDisplayName(p.cash_box_external_id)}
              </td>
              <td className="py-1.5">
                {p.currency_code === "USD"
                  ? `$${Number(p.amount || 0).toLocaleString()}`
                  : `₪${Number(p.amount || 0).toLocaleString()}`}
              </td>
              <td className="py-1.5 max-w-[140px] truncate" title={p.notes || ""}>
                {p.notes || "—"}
              </td>
              <td className="py-1.5">#{p.journal_id_display || p.journal || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function distributeTotalEqually(lines: ClearanceCostLine[], total: number): ClearanceCostLine[] {
  const n = lines.length;
  if (n === 0) return lines;
  const cents = Math.round(Number(total) * 100);
  const base = Math.floor(cents / n);
  const rem = cents - base * n;
  return lines.map((row, i) => ({
    ...row,
    amount: (base + (i < rem ? 1 : 0)) / 100,
  }));
}

const STATUS_OPTIONS = [
  { value: "Processing", label: "قيد المعالجة" },
  { value: "Cleared", label: "تم التخليص" },
  { value: "Hold", label: "معلّق" },
];

export const CustomsClearanceManagement: React.FC<{ currentUser: User }> = ({
  currentUser,
}) => {
const [clearances, setClearances] = useState<ClearanceRow[]>([]);
  const [shipments, setShipments] = useState<ShipmentPick[]>([]);
  const [brokers, setBrokers] = useState<BrokerPick[]>([]);
  const [transportPartners, setTransportPartners] = useState<BrokerPick[]>([]);

  // Aseel Navigation State
  const [showBrokerPicker, setShowBrokerPicker] = useState(false);

  const handleNewClearance = () => {
    setSelected(null);
    setFormBroker("");
    setFormDecl("");
    setFormDate(new Date().toISOString().slice(0, 10));
    setFormStatus("Processing");
    setFormNotes("");
    setFormLines([...DEFAULT_CLEARANCE_COST_LINES]);
    setShippingLineAmount(0);
    setNewOpen(true);
  };

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [selected, setSelected] = useState<ClearanceRow | null>(null);
  const [formBroker, setFormBroker] = useState<number | "">("");
  const [formDecl, setFormDecl] = useState("");
  const [formDate, setFormDate] = useState("");
  const [formStatus, setFormStatus] = useState("Processing");
  const [formNotes, setFormNotes] = useState("");
  const [formLines, setFormLines] = useState<ClearanceCostLine[]>(
    () => DEFAULT_CLEARANCE_COST_LINES.map((x) => ({ ...x }))
  );
  const [distributeInput, setDistributeInput] = useState("");
  /** إدخال سريع: المبلغ الكلي كبند واحد دون توزيع */
  const [quickLumpTotal, setQuickLumpTotal] = useState("");
  // shippingLineAmount is still loaded/saved so existing clearance
  // shipping cost-lines are preserved untouched (T4-04: no financial
  // change). The shipPay* entry state was removed with the UI.
  const [shippingLineAmount, setShippingLineAmount] = useState(0);

  const [newOpen, setNewOpen] = useState(false);
  const [newShipmentId, setNewShipmentId] = useState<number | "">("");
  const [newBrokerId, setNewBrokerId] = useState<number | "">("");
  const [shipmentPickerOpen, setShipmentPickerOpen] = useState(false);
  const [shipmentSearch, setShipmentSearch] = useState("");
  const [payments, setPayments] = useState<ClearancePaymentRow[]>([]);
  const [cashLedgers, setCashLedgers] = useState<CashBoxLedgerLink[]>([]);
  const [payAmount, setPayAmount] = useState("");
  const [payDate, setPayDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [payCashBoxId, setPayCashBoxId] = useState("");
  const [payNotes, setPayNotes] = useState("");
  const [paying, setPaying] = useState(false);

  // Aseel Navigation
  const nav = useRecordNavigation<ClearanceRow>({
    items: clearances,
    getId: (c) => c.id || 0,
    currentId: selected?.id || null,
    onSelect: async (id) => {
      if (id === null) {
        handleNewClearance();
      } else {
        try {
          const loaded = await getClearance(Number(id));
          setSelected(loaded);
          setFormBroker(loaded.customs_broker || "");
          setFormDecl(loaded.declaration_number || "");
          setFormDate(loaded.clearance_date?.slice(0, 10) || "");
          setFormStatus(loaded.status || "Processing");
          setFormNotes(loaded.notes || "");
          setFormLines(loaded.cost_lines || []);
        } catch (err) {
          console.error('Error loading clearance:', err);
        }
      }
    },
  });

  // M3-T4: Aseel keyboard shortcuts — real handlers.
  useAseelKeymap({
    F2: () => window.print(),
    F5: () => reload(),
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"]');
      el?.focus();
    },
    F12: () => { if (!saving) handleSave(); },
    Escape: () => {
      if (showBrokerPicker) { setShowBrokerPicker(false); return; }
      setNewOpen(false);
      setSelected(null);
    },
    plus: () => {
      const ae = document.activeElement;
      if (ae?.getAttribute?.('data-aseel-key') === '1') {
        setShowBrokerPicker(true);
      }
    },
  }, { enabled: !showBrokerPicker });

  const reload = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      const [cl, sh, pr, ledgers] = await Promise.all([
        listClearances(),
        apiGetList<any>("logistics/shipments/", { tenantId: resolveTenantId() }),
        apiGetList<BrokerPick>("partners/", { tenantId: resolveTenantId() }),
        accountingApi.getCashBoxLedgers(),
      ]);
      setClearances(cl);
      const mapped: ShipmentPick[] = sh.map((r: any) => ({
        id: Number(r.id),
        shipment_number: String(r.shipment_number || `S-${r.id}`),
        shipment_name: (r.shipment_name && String(r.shipment_name).trim()) || "",
        agent_shipment_number:
          (r.agent_shipment_number && String(r.agent_shipment_number).trim()) || "",
        israeli_side_name:
          (r.israeli_side_name && String(r.israeli_side_name).trim()) || "",
      }));
      mapped.sort((a, b) =>
        buildShipmentOptionLabel(a).localeCompare(buildShipmentOptionLabel(b), "ar")
      );
      setShipments(mapped);
      setBrokers(pr.filter((p) => (p.partner_type || "") === "CustomsBroker"));
      setTransportPartners(
        pr.filter((p) => {
          const t = (p.partner_type || "").trim();
          return t === "LocalTransporter" || t === "FreightForwarder";
        })
      );
      setCashLedgers(ledgers || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const usedShipmentIds = useMemo(
    () => new Set(clearances.map((c) => Number(c.shipment))),
    [clearances]
  );

  const availableShipments = useMemo(
    () => shipments.filter((s) => !usedShipmentIds.has(s.id)),
    [shipments, usedShipmentIds]
  );
  const filteredAvailableShipments = useMemo(() => {
    const q = shipmentSearch.trim().toLowerCase();
    if (!q) return availableShipments;
    return availableShipments.filter((s) =>
      buildShipmentOptionLabel(s).toLowerCase().includes(q)
    );
  }, [availableShipments, shipmentSearch]);

  const shipmentById = useMemo(() => {
    const m = new Map<number, ShipmentPick>();
    shipments.forEach((s) => m.set(s.id, s));
    return m;
  }, [shipments]);

  /** عرض اسم الصندوق بدل external_id المخزّن في الدفعة */
  const cashBoxDisplayName = useMemo(() => {
    const m = new Map<string, string>();
    cashLedgers.forEach((l) => {
      m.set(l.external_id, `${l.name} (${l.account_code})`);
    });
    return (externalId: string | undefined | null) => {
      const id = (externalId || "").trim();
      if (!id) return "—";
      return m.get(id) ?? id;
    };
  }, [cashLedgers]);

  const clearanceShipmentTitle = useCallback(
    (c: ClearanceRow) => {
      if ((c.shipment_name || "").trim() || (c.shipment_number || "").trim()) {
        return formatClearanceShipmentLine(c);
      }
      const s = shipmentById.get(Number(c.shipment));
      if (s) return buildShipmentOptionLabel(s);
      return c.shipment_number ? `شحنة ${c.shipment_number}` : `شحنة #${c.shipment}`;
    },
    [shipmentById]
  );

  const openDetail = async (row: ClearanceRow) => {
    setErr(null);
    try {
      const fresh = await getClearance(row.id);
      setSelected(fresh);
      setFormBroker(fresh.customs_broker ?? "");
      setFormDecl(fresh.declaration_number || "");
      setFormDate(
        fresh.clearance_date
          ? String(fresh.clearance_date).slice(0, 10)
          : ""
      );
      setFormStatus(fresh.status || "Processing");
      setFormNotes(fresh.notes || "");
      const rawLines = (
        fresh.cost_lines?.length ? fresh.cost_lines : DEFAULT_CLEARANCE_COST_LINES
      ).map((x) => ({
        label: x.label,
        amount: Number(x.amount) || 0,
      }));
      let shipFromLines = 0;
      const clearanceOnly = rawLines.filter((l) => {
        if (l.label.trim() === SHIPPING_COST_LINE_LABEL) {
          shipFromLines += Number(l.amount) || 0;
          return false;
        }
        return true;
      });
      const payRows = await listClearancePayments(row.id);
      setPayments(payRows);
      const paidShip = (payRows || []).reduce(
        (s, p) => s + (notesMeanShippingPayment(p.notes) ? Number(p.amount) || 0 : 0),
        0
      );
      const paidClearance = (payRows || []).reduce(
        (s, p) => s + (!notesMeanShippingPayment(p.notes) ? Number(p.amount) || 0 : 0),
        0
      );
      // إن دُفع الشحن قبل إضافة بند «دفعة الشحن» في cost_lines، يبقى الحقل فارغاً رغم ظهور الدفعة في الجدول
      const shipLineEffective =
        shipFromLines > 0 ? shipFromLines : paidShip > 0 ? paidShip : 0;
      setShippingLineAmount(shipLineEffective);
      setFormLines(
        clearanceOnly.length ? clearanceOnly : DEFAULT_CLEARANCE_COST_LINES.map((x) => ({ ...x }))
      );
      const clearanceLinesForTotal =
        clearanceOnly.length > 0
          ? clearanceOnly
          : DEFAULT_CLEARANCE_COST_LINES.map((x) => ({ ...x }));
      const clearancePartTotal = sumLines(clearanceLinesForTotal);
      setPayAmount(String(Math.max(0, Number((clearancePartTotal - paidClearance).toFixed(2)))));
      setPayCashBoxId((payRows[0]?.cash_box_external_id || ""));
      setPayNotes("");
      setDistributeInput("");
      setQuickLumpTotal("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const handleSave = async () => {
    if (!selected) return;
    setSaving(true);
    setErr(null);
    try {
      const updated = await updateClearance(selected.id, {
        customs_broker: formBroker === "" ? null : Number(formBroker),
        declaration_number: formDecl.trim() || undefined,
        clearance_date: formDate || null,
        status: formStatus,
        notes: formNotes.trim() || "",
        cost_lines: [
          ...formLines.filter((l) => l.label.trim() !== ""),
          ...(shippingLineAmount > 0
            ? [
                {
                  label: SHIPPING_COST_LINE_LABEL,
                  amount: Number(shippingLineAmount) || 0,
                },
              ]
            : []),
        ],
      });
      setSelected(updated);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleCreate = async () => {
    if (newShipmentId === "") {
      alert("اختر الشحنة");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      await createClearance({
        shipment: Number(newShipmentId),
        customs_broker:
          newBrokerId === "" ? null : Number(newBrokerId),
        cost_lines: [{ label: LUMP_CLEARANCE_LINE_LABEL, amount: 0 }],
      });
      setNewOpen(false);
      setNewShipmentId("");
      setNewBrokerId("");
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const applyDistribute = () => {
    const total = parseFloat(distributeInput.replace(/,/g, ""));
    if (!Number.isFinite(total) || total < 0) {
      alert("أدخل مبلغاً رقماً صالحاً للتوزيع");
      return;
    }
    const active = formLines.filter((l) => l.label.trim() !== "");
    if (active.length === 0) {
      alert("أضف بنداً واحداً على الأقل (أو استخدم «التكلفة الكلية» أعلاه)");
      return;
    }
    setFormLines(distributeTotalEqually(active, total));
  };

  const applyQuickLumpTotal = () => {
    const n = parseFloat(quickLumpTotal.replace(/,/g, ""));
    if (!Number.isFinite(n) || n < 0) {
      alert("أدخل مبلغاً صالحاً للتكلفة الكلية");
      return;
    }
    setFormLines([{ label: LUMP_CLEARANCE_LINE_LABEL, amount: n }]);
    setQuickLumpTotal("");
  };

  const totalClearance = useMemo(
    () => sumLines(formLines) + (Number(shippingLineAmount) || 0),
    [formLines, shippingLineAmount]
  );
  const totalPaid = useMemo(
    () => payments.reduce((s, p) => s + Number(p.amount || 0), 0),
    [payments]
  );
  const paidShippingIls = useMemo(
    () =>
      payments.reduce(
        (s, p) => s + (notesMeanShippingPayment(p.notes) ? Number(p.amount) || 0 : 0),
        0
      ),
    [payments]
  );
  const paidClearanceIls = useMemo(
    () =>
      payments.reduce(
        (s, p) => s + (!notesMeanShippingPayment(p.notes) ? Number(p.amount) || 0 : 0),
        0
      ),
    [payments]
  );
  const clearancePaymentRows = useMemo(
    () => payments.filter((p) => !notesMeanShippingPayment(p.notes)),
    [payments]
  );
  const shippingPaymentRows = useMemo(
    () => payments.filter((p) => notesMeanShippingPayment(p.notes)),
    [payments]
  );
  const clearanceBudgetIls = useMemo(() => sumLines(formLines), [formLines]);
  const shippingBudgetIls = Number(shippingLineAmount) || 0;
  const remainingClearanceOnly = Math.max(
    0,
    Number((clearanceBudgetIls - paidClearanceIls).toFixed(2))
  );
  const remainingShippingOnly = Math.max(
    0,
    Number((shippingBudgetIls - paidShippingIls).toFixed(2))
  );
  const remaining = Math.max(0, Number((totalClearance - totalPaid).toFixed(2)));
  /** أصل > 0 ولا يوجد متبقي على هذا البند — يُعطّل نموذج الدفع حتى لا يُسجَّل دفع زائد بالخطأ */
  const clearancePayClosed =
    clearanceBudgetIls > 0.005 && remainingClearanceOnly <= 0.005;
  const shippingPayClosed =
    shippingBudgetIls > 0.005 && remainingShippingOnly <= 0.005;

  const handlePostPayment = async () => {
    if (!selected) return;
    if (clearancePayClosed) {
      alert("لا يوجد متبقي على التخليص — السداد مكتمل لهذا الأصل.");
      return;
    }
    if (!selected.customs_broker && formBroker === "") {
      alert("حدد المخلّص أولاً واربطه بحساب محاسبي.");
      return;
    }
    if (!payCashBoxId) {
      alert("اختر الصندوق أولاً.");
      return;
    }
    const vErr = validatePaymentInput({ amount: payAmount, date: payDate });
    if (vErr.amount || vErr.date) {
      alert(vErr.amount || vErr.date);
      return;
    }
    const amount = Number(payAmount || 0);
    setPaying(true);
    setErr(null);
    try {
      if (selected.customs_broker !== (formBroker === "" ? null : Number(formBroker))) {
        const updated = await updateClearance(selected.id, {
          customs_broker: formBroker === "" ? null : Number(formBroker),
        });
        setSelected(updated);
      }
      const res = await payClearanceFromCashBox(selected.id, {
        amount,
        cash_box_external_id: payCashBoxId,
        payment_date: payDate || undefined,
        notes: payNotes || undefined,
      });
      const rows = await listClearancePayments(selected.id);
      setPayments(rows);
      alert(
        `✅ ${res.status}${res.journal_id ? ` (قيد #${res.journal_id})` : ""}`
      );
      setPayNotes("");
      const nextPaidClearance = rows.reduce(
        (s, p) => s + (!notesMeanShippingPayment(p.notes) ? Number(p.amount) || 0 : 0),
        0
      );
      const clearanceBudget = sumLines(formLines);
      setPayAmount(
        String(Math.max(0, Number((clearanceBudget - nextPaidClearance).toFixed(2))))
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setErr(msg);
      alert(msg);
    } finally {
      setPaying(false);
    }
  };

  // T4-04: local-transport entry/payment was removed from the clearance
  // screen (single source = the standalone "الشحن المحلي" page). The old
  // handleShipPostPayment + shipPay* state were deleted with it.

  if (
    currentUser.role !== "manager" &&
    currentUser.role !== "procurement"
  ) {
    return (
      <div className="p-8 text-center text-gray-500 dark:text-gray-400">
        لا تملك صلاحية عرض التخليص الجمركي.
      </div>
    );
  }

  return (
    <div
      data-skin="aseel"
      style={{ height: 'calc(100vh - 5rem)', display: 'flex', flexDirection: 'column' }}
    >
      <AseelDocumentShell
        title="فاتورة البيان الجمركي"
        state={selected ? `بيان #${selected.declaration_number || selected.id}` : 'بيان جديد'}
        nav={nav}
        actions={[
          { key: 'new', label: 'إضافة', icon: <Plus />, onClick: handleNewClearance },
          {
            key: 'reload',
            label: 'تحديث',
            icon: <RefreshCw />,
            onClick: () => reload(),
            separatorBefore: true,
          },
          {
            key: 'print',
            label: 'طباعة',
            icon: <Printer />,
            onClick: () => window.print(),
          },
        ]}
        header={<></>}
        status={
          <>
            <span className="aseel-status-item">
              المستخدم <b>{currentUser?.name || '—'}</b>
            </span>
            <span className="aseel-status-item">
              السجل <b>{nav.position}/{nav.total}</b>
            </span>
            <span className="aseel-status-item">
              {clearances.length} بيان
            </span>
          </>
        }
      >
        <div
          className="p-4 md:p-8 space-y-6 max-w-7xl mx-auto"
          style={{ height: '100%', overflow: 'auto', background: '#ffffff' }}
        >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-2xl bg-[var(--color-primary-light)] text-[var(--color-primary)]">
            <FileText className="w-8 h-8" />
          </div>
          <div>
            <h1 className="text-[var(--font-size-2xl)] font-bold text-[var(--color-text)]">
              التخليص الجمركي
            </h1>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => reload()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
          >
            <RefreshCw className="w-4 h-4" />
            تحديث
          </button>
          <button
            type="button"
            onClick={() => setNewOpen(true)}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-xl bg-[var(--color-primary)] text-white font-bold hover:opacity-90"
          >
            <Plus className="w-5 h-5" />
            تخليص من شحنة
          </button>
        </div>
      </div>

      {err && (
        <div className="p-4 rounded-xl bg-[var(--color-danger-light)] text-[var(--color-danger)] text-sm border border-[var(--color-danger)]/20">
          {err}
        </div>
      )}

      <div className="flex flex-col gap-6">
        <div
          className={`rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm overflow-hidden ${
            selected ? "max-h-52 lg:max-h-60" : ""
          }`}
        >
          <div className="px-4 py-3 border-b border-[var(--color-border-subtle)] font-bold text-[var(--color-text)] flex items-center gap-2">
            <Truck className="w-4 h-4 text-[var(--color-primary)]" />
            السجلات ({clearances.length})
          </div>
          <div
            className={`overflow-y-auto ${selected ? "max-h-40 lg:max-h-48" : "max-h-[min(560px,70vh)]"}`}
          >
            <DataGrid<ClearanceRow>
              columns={[
                {
                  key: "shipment",
                  header: "الشحنة",
                  render: (row) => (
                    <div className="font-bold text-[var(--color-text)] leading-snug">
                      {clearanceShipmentTitle(row)}
                    </div>
                  ),
                },
                {
                  key: "broker",
                  header: "المخلص",
                  render: (row) => row.broker_name || "—",
                },
                {
                  key: "total",
                  header: "الإجمالي",
                  align: "end",
                  render: (row) => `₪${sumLines(row.cost_lines || []).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
                },
                {
                  key: "status",
                  header: "الحالة",
                  render: (row) => row.status,
                },
              ]}
              data={clearances}
              keyField="id"
              loading={loading}
              emptyMessage="لا توجد تخليصات بعد. استخدم «تخليص من شحنة»."
              onRowClick={(row) => openDetail(row)}
              rowClassName={(row) => selected?.id === row.id ? "bg-[var(--color-primary-light)]" : ""}
            />
          </div>
        </div>

        <div className="w-full max-w-6xl mx-auto rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm p-5 sm:p-6 space-y-4">
          {!selected ? (
            <p className="text-center text-[var(--color-text-muted)] py-12 text-sm">
              اختر سجلاً من القائمة أعلاه
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border-subtle)] pb-3">
                <h2 className="font-bold text-[var(--font-size-lg)] text-[var(--color-text)] leading-snug">
                  {clearanceShipmentTitle(selected)}
                </h2>
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  className="text-sm font-semibold text-[var(--color-primary)] hover:underline"
                >
                  ← القائمة
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="block text-sm space-y-1">
                  <span className="text-[var(--color-text-muted)]">المخلص الجمركي</span>
                  <select
                    value={formBroker === "" ? "" : String(formBroker)}
                    onChange={(e) =>
                      setFormBroker(
                        e.target.value === "" ? "" : Number(e.target.value)
                      )
                    }
                    className="w-full rounded-xl border border-[var(--color-border)] px-3 py-2 bg-[var(--color-surface)] text-[var(--color-text)]"
                  >
                    <option value="">—</option>
                    {brokers.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-sm space-y-1">
                  <span className="text-[var(--color-text-muted)]">رقم البيان / الإقرار</span>
                  <input
                    value={formDecl}
                    onChange={(e) => setFormDecl(e.target.value)}
                    className="w-full rounded-xl border border-[var(--color-border)] px-3 py-2 bg-[var(--color-surface)] text-[var(--color-text)]"
                  />
                </label>
                <label className="block text-sm space-y-1">
                  <span className="text-[var(--color-text-muted)]">تاريخ التخليص</span>
                  <input
                    type="date"
                    value={formDate}
                    onChange={(e) => setFormDate(e.target.value)}
                    className="w-full rounded-xl border border-[var(--color-border)] px-3 py-2 bg-[var(--color-surface)] text-[var(--color-text)]"
                  />
                </label>
                <label className="block text-sm space-y-1">
                  <span className="text-[var(--color-text-muted)]">الحالة</span>
                  <select
                    value={formStatus}
                    onChange={(e) => setFormStatus(e.target.value)}
                    className="w-full rounded-xl border border-[var(--color-border)] px-3 py-2 bg-[var(--color-surface)] text-[var(--color-text)]"
                  >
                    {STATUS_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <label className="block text-sm space-y-1">
                <span className="text-[var(--color-text-muted)]">ملاحظات</span>
                <textarea
                  value={formNotes}
                  onChange={(e) => setFormNotes(e.target.value)}
                  rows={2}
                  className="w-full rounded-xl border border-[var(--color-border)] px-3 py-2 bg-[var(--color-surface)] text-[var(--color-text)]"
                />
              </label>

              <div className="grid grid-cols-1 gap-6">
                <div className="rounded-2xl border-2 border-[var(--color-info)]/30 bg-[var(--color-info-light)] p-4 sm:p-5 space-y-4">
                  <div className="border-b border-[var(--color-info)]/30 pb-2">
                    <h3 className="text-sm font-bold text-[var(--color-info)]">
                      التخليص — دفع المخلّص
                    </h3>
                    <p className="text-xs font-semibold text-[var(--color-info)] mt-1.5 tabular-nums">
                      أصل ₪{clearanceBudgetIls.toLocaleString()} · مدفوع ₪{paidClearanceIls.toLocaleString()} · متبقي
                      ₪{remainingClearanceOnly.toLocaleString()}
                    </p>
                  </div>

              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold text-[var(--color-text)] text-sm">
                    بنود التخليص (₪)
                  </span>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        setFormLines(
                          DEFAULT_CLEARANCE_COST_LINES.map((x) => ({ ...x }))
                        )
                      }
                      className="text-xs px-3 py-1.5 rounded-lg bg-[var(--color-surface-2)] text-[var(--color-text)] hover:opacity-80"
                    >
                      استعادة الافتراضي
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setFormLines((rows) => [
                          ...rows,
                          { label: "بند جديد", amount: 0 },
                        ])
                      }
                      className="text-xs px-3 py-1.5 rounded-lg bg-[var(--color-success)] text-white hover:opacity-90"
                    >
                      + بند
                    </button>
                  </div>
                </div>
                <div className="flex flex-wrap items-end gap-2 p-3 rounded-xl bg-[var(--color-primary-light)] border border-[var(--color-primary)]/30">
                  <label className="text-xs font-semibold text-[var(--color-primary)] flex-1 min-w-[140px]">
                    التكلفة الكلية للتخليص (₪) — بند واحد
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={quickLumpTotal}
                      onChange={(e) => setQuickLumpTotal(e.target.value)}
                      placeholder="مثال: 14487"
                      className="mt-1 w-full rounded-lg border border-[var(--color-primary)]/30 px-2 py-2 bg-[var(--color-surface)] text-[var(--color-text)] text-sm font-bold"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={applyQuickLumpTotal}
                    className="inline-flex items-center gap-1 px-4 py-2 rounded-lg bg-[var(--color-primary)] text-white text-sm font-bold hover:opacity-90"
                  >
                    تطبيق كإجمالي
                  </button>
                </div>

<details className="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2">
                  <summary className="text-xs cursor-pointer text-[var(--color-text-muted)] select-none py-1">
                    توزيع تلقائي بالتساوي على البنود الحالية (اختياري)
                  </summary>
                  <div className="flex flex-wrap items-end gap-2 pt-2 pb-1">
                    <label className="text-xs text-[var(--color-text-muted)] flex-1 min-w-[120px]">
                      مبلغ يُقسَّم بالتساوي
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={distributeInput}
                        onChange={(e) => setDistributeInput(e.target.value)}
                        placeholder="مثال: 1500"
                        className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-2 py-1.5 bg-[var(--color-surface)] text-[var(--color-text)] text-sm"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={applyDistribute}
                      className="inline-flex items-center gap-1 px-3 py-2 rounded-lg bg-[var(--color-secondary)] text-white text-sm font-medium hover:opacity-90"
                    >
                      <Split className="w-4 h-4" />
                      وزّع
                    </button>
                  </div>
                </details>

                <div className="rounded-xl border border-[var(--color-border)] overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-[var(--color-surface-2)] text-[var(--color-text-muted)]">
                      <tr>
                        <th className="text-right px-3 py-2">البند</th>
                        <th className="text-right px-3 py-2 w-32">المبلغ</th>
                        <th className="w-10" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--color-border-subtle)]">
                      {formLines.map((row, idx) => (
                        <tr key={idx}>
                          <td className="px-2 py-1">
                            <input
                              value={row.label}
                              onChange={(e) => {
                                const v = e.target.value;
                                setFormLines((rows) =>
                                  rows.map((r, i) =>
                                    i === idx ? { ...r, label: v } : r
                                  )
                                );
                              }}
                              className="w-full rounded-lg border border-transparent hover:border-[var(--color-border)] focus:border-[var(--color-primary)] px-2 py-1 bg-transparent text-[var(--color-text)]"
                            />
                          </td>
                          <td className="px-2 py-1">
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              value={row.amount}
                              onChange={(e) => {
                                const v = parseFloat(e.target.value) || 0;
                                setFormLines((rows) =>
                                  rows.map((r, i) =>
                                    i === idx ? { ...r, amount: v } : r
                                  )
                                );
                              }}
                              className="w-full rounded-lg border border-[var(--color-border)] px-2 py-1 bg-[var(--color-surface)] text-[var(--color-text)]"
                            />
                          </td>
                          <td className="px-1 text-center">
                            <button
                              type="button"
                              title="حذف البند"
                              onClick={() =>
                                setFormLines((lines) =>
                                  lines.filter((_, i) => i !== idx)
                                )
                              }
                              className="p-1.5 text-[var(--color-danger)] hover:bg-[var(--color-danger-light)] rounded-lg"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="text-left font-bold text-[var(--color-primary)] text-sm">
                  مجموع بنود التخليص: ₪
                  {sumLines(formLines).toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                  })}
                </div>
              </div>

                  <div className="space-y-3 border-t border-[var(--color-info)]/30 pt-4">
                    {clearancePayClosed ? (
                      <p className="text-xs font-semibold text-[var(--color-success)] py-2">
                        تم سداد التخليص بالكامل — لا دفع إضافي ضمن هذا الأصل.
                      </p>
                    ) : (
                      <>
                        <span className="text-xs font-bold text-[var(--color-info)] block">
                          دفع للمخلّص (صف واحد)
                        </span>
                        <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-end">
                          <label className="block text-xs space-y-1 sm:col-span-5 text-[var(--color-text-muted)]">
                            <span>الصندوق</span>
                            <select
                              value={payCashBoxId}
                              onChange={(e) => setPayCashBoxId(e.target.value)}
                              className="w-full rounded-lg border border-[var(--color-border)] px-2 py-2 bg-[var(--color-surface)] text-[var(--color-text)] text-sm"
                            >
                              <option value="">اختر…</option>
                              {cashLedgers.map((l) => (
                                <option key={l.id} value={l.external_id}>
                                  {l.name} ({l.account_code})
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="block text-xs space-y-1 sm:col-span-3 text-[var(--color-text-muted)]">
                            <span>التاريخ</span>
                            <input
                              type="date"
                              value={payDate}
                              onChange={(e) => setPayDate(e.target.value)}
                              className="w-full rounded-lg border border-[var(--color-border)] px-2 py-2 bg-[var(--color-surface)] text-[var(--color-text)] text-sm"
                            />
                          </label>
                          <label className="block text-xs space-y-1 sm:col-span-2 text-[var(--color-text-muted)]">
                            <span>₪</span>
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              value={payAmount}
                              onChange={(e) => setPayAmount(e.target.value)}
                              className="w-full rounded-lg border border-[var(--color-border)] px-2 py-2 bg-[var(--color-surface)] text-[var(--color-text)] text-sm font-semibold"
                            />
                          </label>
                          <div className="sm:col-span-2">
                            <button
                              type="button"
                              onClick={handlePostPayment}
                              disabled={paying}
                              className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl bg-[var(--color-info)] px-3 py-2.5 text-sm font-bold text-white hover:opacity-90 disabled:opacity-50"
                            >
                              {paying ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                              دفع
                            </button>
                          </div>
                        </div>
                        <details className="text-xs">
                          <summary className="cursor-pointer text-[var(--color-text-muted)] hover:text-[var(--color-text)]">
                            ملاحظات الدفع (اختياري)
                          </summary>
                          <input
                            value={payNotes}
                            onChange={(e) => setPayNotes(e.target.value)}
                            className="mt-2 w-full rounded-lg border border-[var(--color-border)] px-2 py-2 bg-[var(--color-surface)] text-[var(--color-text)] text-sm"
                            placeholder="اختياري"
                          />
                        </details>
                      </>
                    )}
                    <ClearancePaymentMiniTable rows={clearancePaymentRows} cashBoxDisplayName={cashBoxDisplayName} />
                  </div>
                </div>

                <div className="rounded-2xl border-2 border-[var(--color-primary)]/50 bg-[var(--color-primary-light)]/50 p-4 sm:p-5 space-y-4">
                  <div className="border-b border-[var(--color-primary)]/30 pb-2">
                    <h3 className="text-sm font-bold text-[var(--color-primary)]">
                      النقل المحلي — دفع الناقل
                    </h3>
                    <p className="text-xs font-semibold text-[var(--color-primary)] mt-1.5 tabular-nums">
                      أصل ₪{shippingBudgetIls.toLocaleString()} · مدفوع ₪{paidShippingIls.toLocaleString()} · متبقي ₪
                      {remainingShippingOnly.toLocaleString()}
                    </p>
                  </div>

                  {!!selected?.local_shipments?.length && (
                    <div className="rounded-xl border border-[var(--color-primary)]/50 bg-[var(--color-surface)]/70 p-3 space-y-2">
                      <p className="text-xs font-bold text-[var(--color-primary)]">
                        سجلات الشحن المحلي الرسمية المرتبطة (المصدر الموحّد — تُدار من صفحة «الشحن المحلي»):
                      </p>
                      <ul className="text-xs space-y-1">
                        {selected.local_shipments.map((ls) => (
                          <li
                            key={ls.id}
                            className="flex items-center justify-between gap-2 border-b border-[var(--color-primary)]/10 pb-1 last:border-0"
                          >
                            <span className="font-semibold tabular-nums">{ls.shipment_number}</span>
                            <span className="tabular-nums">{Number(ls.amount).toLocaleString()}</span>
                            <span>{ls.status}</span>
                            <span className={ls.is_posted ? "text-[var(--color-success)]" : "text-[var(--color-text-muted)]"}>
                              {ls.is_posted ? "مُرحّل" : "غير مُرحّل"}
                            </span>
                          </li>
                        ))}
                      </ul>
                      <p className="text-[11px] text-[var(--color-primary)]">
                        ملاحظة: عند وجود سجل شحن محلي مُرحّل ومُرسمَل، تُستبعد تكلفته من بنود التخليص تلقائياً لمنع ازدواج الترسمل (T1-01).
                      </p>
                    </div>
                  )}

                  <div className="rounded-xl border border-[var(--color-primary)]/50 bg-[var(--color-surface)]/60 p-3 text-xs text-[var(--color-primary)] space-y-1">
                    <p className="font-bold">إدارة النقل المحلي انتقلت إلى صفحة «الشحن المحلي».</p>
                    <p>
                      لم يَعُد النقل المحلي يُدخَل أو يُدفَع من شاشة التخليص (إزالة الازدواج — T4-04).
                      أنشئ/ادفع شحنات النقل المحلي من صفحة «الشحن المحلي» وستظهر هنا للقراءة فقط.
                      السجلات التاريخية رُحِّلت تلقائياً دون أي تغيير على القيود أو landed cost.
                    </p>
                  </div>
                </div>
              </div>

              <div className="text-left space-y-0.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] px-4 py-3">
                <div className="text-xs font-bold text-[var(--color-text)]">
                  الإجمالي (تخليص + نقل محلي): ₪
                  {totalClearance.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                  })}
                </div>
                <div className="text-[10px] text-[var(--color-text-muted)]">
                  المتبقي بعد كل الدفعات: ₪{remaining.toLocaleString()}
                  {remaining === 0 ? " — مغلق" : ""}
                </div>
              </div>

              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-[var(--color-primary)] text-white font-bold hover:opacity-90 disabled:opacity-50"
              >
                {saving ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Save className="w-5 h-5" />
                )}
                حفظ التعديلات
              </button>
            </>
          )}
        </div>
      </div>

      {newOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl max-w-xl w-full p-6 border border-gray-200 dark:border-gray-700 space-y-4">
            <h3 className="font-bold text-lg text-gray-900 dark:text-white">
              تخليص جديد من شحنة
            </h3>
            <p className="text-xs text-gray-500">عند الإنشاء تُحدَّث مرحلة الصفقات المرتبطة بالشحنة.</p>
            <label className="block text-sm space-y-1">
              <span>الشحنة</span>
              <button
                type="button"
                onClick={() => setShipmentPickerOpen(true)}
                className="w-full rounded-xl border border-gray-200 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-800 text-right hover:border-amber-400"
              >
                {newShipmentId === ""
                  ? "اختر…"
                  : buildShipmentOptionLabel(
                      availableShipments.find((s) => s.id === newShipmentId) ||
                        shipments.find((s) => s.id === newShipmentId) || {
                          id: Number(newShipmentId),
                          shipment_number: `S-${newShipmentId}`,
                        }
                    )}
              </button>
            </label>
            <label className="block text-sm space-y-1">
              <span>المخلص (اختياري)</span>
              <select
                value={newBrokerId === "" ? "" : String(newBrokerId)}
                onChange={(e) =>
                  setNewBrokerId(
                    e.target.value === "" ? "" : Number(e.target.value)
                  )
                }
                className="w-full rounded-xl border border-gray-200 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-800"
              >
                <option value="">— لاحقاً —</option>
                {brokers.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex gap-2 justify-end pt-2">
              <button
                type="button"
                onClick={() => setNewOpen(false)}
                className="px-4 py-2 rounded-xl border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-200"
              >
                إلغاء
              </button>
              <button
                type="button"
                onClick={handleCreate}
                disabled={saving || newShipmentId === ""}
                className="px-5 py-2 rounded-xl bg-amber-600 text-white font-bold disabled:opacity-50"
              >
                إنشاء
              </button>
            </div>
          </div>
        </div>
      )}
      {newOpen && shipmentPickerOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col border border-gray-200 dark:border-gray-700">
            <div className="p-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
              <h4 className="font-bold text-gray-900 dark:text-white">
                اختر الشحنة للتخليص
              </h4>
              <button
                type="button"
                onClick={() => setShipmentPickerOpen(false)}
                className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-4 border-b border-gray-100 dark:border-gray-800">
              <div className="relative">
                <Search className="w-4 h-4 text-gray-400 absolute right-3 top-1/2 -translate-y-1/2" />
                <input
                  value={shipmentSearch}
                  onChange={(e) => setShipmentSearch(e.target.value)}
                  placeholder="ابحث بالاسم أو رقم الشحنة أو المرجع..."
                  className="w-full rounded-xl border border-gray-200 dark:border-gray-600 pr-9 pl-3 py-2 bg-white dark:bg-gray-800 text-sm"
                />
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-2 bg-gray-50/50 dark:bg-black/20">
              {filteredAvailableShipments.length === 0 ? (
                <div className="text-center text-sm text-gray-500 py-12">
                  لا توجد شحنات متاحة تطابق البحث
                </div>
              ) : (
                filteredAvailableShipments.map((s) => {
                  const selectedRow = newShipmentId === s.id;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => {
                        setNewShipmentId(s.id);
                        setShipmentPickerOpen(false);
                      }}
                      className={`w-full text-right p-3 rounded-xl border transition-all ${
                        selectedRow
                          ? "bg-amber-50 border-amber-400 dark:bg-amber-900/20 dark:border-amber-700"
                          : "bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-amber-300"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className={`w-5 h-5 rounded-full border flex items-center justify-center ${
                            selectedRow
                              ? "border-amber-500 text-amber-600"
                              : "border-gray-300 text-transparent"
                          }`}
                        >
                          <CheckCircle2 className="w-4 h-4" />
                        </div>
                        <span className="font-semibold text-gray-900 dark:text-white leading-snug">
                          {buildShipmentOptionLabel(s)}
                        </span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

        </div>
      </AseelDocumentShell>

      {/* M3-T4: Aseel broker index picker. */}
      <AseelIndexPicker<BrokerPick>
        open={showBrokerPicker}
        title="فهرس المخلّصين الجمركيين"
        rows={brokers}
        columns={[
          { key: 'id', header: 'الرقم', width: '90px', value: (r) => r.id },
          { key: 'name', header: 'الاسم', value: (r) => r.name },
          { key: 'type', header: 'النوع', width: '140px', value: (r) => r.partner_type ?? '—' },
        ]}
        getRowKey={(r) => r.id}
        searchValue={(r) => `${r.id} ${r.name}`}
        onSelect={(r) => {
          setFormBroker(String(r.id));
          setShowBrokerPicker(false);
        }}
        onClose={() => setShowBrokerPicker(false)}
      />
    </div>
  );
};
