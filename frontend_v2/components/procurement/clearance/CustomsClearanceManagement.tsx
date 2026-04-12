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
} from "lucide-react";
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

type ShipmentPick = {
  id: number;
  shipment_number: string;
  shipment_name?: string;
  agent_shipment_number?: string;
  israeli_side_name?: string;
};

type BrokerPick = { id: number; name: string; partner_type?: string };

/** نص يظهر في القوائم: الاسم أولاً ثم الرقم والمرجع. */
function buildShipmentOptionLabel(s: ShipmentPick): string {
  const num = s.shipment_number || `S-${s.id}`;
  const name = (s.shipment_name || "").trim();
  const ref = (s.agent_shipment_number || "").trim();
  const side = (s.israeli_side_name || "").trim();
  if (name) {
    const tail = [num, ref ? `مرجع: ${ref}` : "", side].filter(Boolean).join(" · ");
    return tail && tail !== name ? `${name} — ${tail}` : name;
  }
  return [num, ref ? `مرجع: ${ref}` : "", side].filter(Boolean).join(" · ");
}

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
  /** شركاء نقل / سائقون لدفعة الشحن */
  const [transportPartners, setTransportPartners] = useState<BrokerPick[]>([]);
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
  const [shippingLineAmount, setShippingLineAmount] = useState(0);
  const [shipPayAmount, setShipPayAmount] = useState("");
  const [shipPayDate, setShipPayDate] = useState(() =>
    new Date().toISOString().slice(0, 10)
  );
  const [shipPayCashBoxId, setShipPayCashBoxId] = useState("");
  const [shipPayPartnerId, setShipPayPartnerId] = useState<number | "">("");
  const [shipPayNotes, setShipPayNotes] = useState("");

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
      setShipPayAmount("");
      setShipPayDate(new Date().toISOString().slice(0, 10));
      setShipPayCashBoxId(payRows[0]?.cash_box_external_id || "");
      setShipPayNotes("");
      setShipPayPartnerId("");
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
    const amount = Number(payAmount || 0);
    if (!Number.isFinite(amount) || amount <= 0) {
      alert("المبلغ غير صالح.");
      return;
    }
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

  const handleShipPostPayment = async () => {
    if (!selected) return;
    if (shippingPayClosed) {
      alert("لا يوجد متبقي على النقل المحلي — السداد مكتمل لهذا الأصل.");
      return;
    }
    if (shipPayPartnerId === "") {
      alert("اختر السائق أو الناقل (شريك النقل) المستفيد من دفعة الشحن.");
      return;
    }
    if (!shipPayCashBoxId) {
      alert("اختر الصندوق.");
      return;
    }
    const amount = Number(shipPayAmount || 0);
    if (!Number.isFinite(amount) || amount <= 0) {
      alert("المبلغ غير صالح.");
      return;
    }
    setPaying(true);
    setErr(null);
    try {
      const res = await payClearanceFromCashBox(selected.id, {
        amount,
        cash_box_external_id: shipPayCashBoxId,
        payment_date: shipPayDate || undefined,
        notes: shipPayNotes.trim(),
        payment_kind: "shipping",
        payee_partner_id: Number(shipPayPartnerId),
      });
      const rows = await listClearancePayments(selected.id);
      setPayments(rows);
      alert(
        `✅ نقل: ${res.status}${res.journal_id ? ` (قيد #${res.journal_id})` : ""}`
      );
      setShipPayNotes("");
      setShipPayAmount("");
      const nextPaidClearance = rows.reduce(
        (s, p) => s + (!notesMeanShippingPayment(p.notes) ? Number(p.amount) || 0 : 0),
        0
      );
      const nextPaidShip = rows.reduce(
        (s, p) => s + (notesMeanShippingPayment(p.notes) ? Number(p.amount) || 0 : 0),
        0
      );
      const clearanceBudget = sumLines(formLines);
      setPayAmount(
        String(Math.max(0, Number((clearanceBudget - nextPaidClearance).toFixed(2))))
      );
      setShippingLineAmount((prev) =>
        Number(prev) > 0 ? prev : nextPaidShip > 0 ? nextPaidShip : prev
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setErr(msg);
      alert(msg);
    } finally {
      setPaying(false);
    }
  };

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
    <div className="p-4 md:p-8 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-2xl bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300">
            <FileText className="w-8 h-8" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              التخليص الجمركي
            </h1>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => reload()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            <RefreshCw className="w-4 h-4" />
            تحديث
          </button>
          <button
            type="button"
            onClick={() => setNewOpen(true)}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-xl bg-amber-600 text-white font-bold hover:bg-amber-700 shadow-md"
          >
            <Plus className="w-5 h-5" />
            تخليص من شحنة
          </button>
        </div>
      </div>

      {err && (
        <div className="p-4 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-200 text-sm border border-red-100 dark:border-red-900/40">
          {err}
        </div>
      )}

      <div className="flex flex-col gap-6">
        <div
          className={`rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden ${
            selected ? "max-h-52 lg:max-h-60" : ""
          }`}
        >
          <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800 font-bold text-gray-800 dark:text-gray-100 flex items-center gap-2">
            <Truck className="w-4 h-4 text-amber-600" />
            السجلات ({clearances.length})
          </div>
          <div
            className={`overflow-y-auto ${selected ? "max-h-40 lg:max-h-48" : "max-h-[min(560px,70vh)]"}`}
          >
            {loading ? (
              <div className="flex justify-center py-16 text-gray-400">
                <Loader2 className="w-8 h-8 animate-spin" />
              </div>
            ) : clearances.length === 0 ? (
              <p className="p-8 text-center text-gray-500 text-sm">
                لا توجد تخليصات بعد. استخدم «تخليص من شحنة».
              </p>
            ) : (
              <ul className="divide-y divide-gray-100 dark:divide-gray-800">
                {clearances.map((c) => {
                  const total = sumLines(c.cost_lines || []);
                  const active = selected?.id === c.id;
                  return (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => openDetail(c)}
                        className={`w-full text-right px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800/80 transition-colors ${
                          active ? "bg-amber-50/80 dark:bg-amber-900/20" : ""
                        }`}
                      >
                        <div className="font-bold text-gray-900 dark:text-white leading-snug">
                          {clearanceShipmentTitle(c)}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 flex flex-wrap gap-2">
                          <span>المخلص: {c.broker_name || "—"}</span>
                          <span>|</span>
                          <span>
                            الإجمالي: ₪
                            {total.toLocaleString(undefined, {
                              minimumFractionDigits: 2,
                            })}
                          </span>
                          <span>|</span>
                          <span>{c.status}</span>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        <div className="w-full max-w-6xl mx-auto rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm p-5 sm:p-6 space-y-4">
          {!selected ? (
            <p className="text-center text-gray-500 py-12 text-sm">
              اختر سجلاً من القائمة أعلاه
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 dark:border-gray-800 pb-3">
                <h2 className="font-bold text-lg text-gray-900 dark:text-white leading-snug">
                  {clearanceShipmentTitle(selected)}
                </h2>
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  className="text-sm font-semibold text-amber-800 dark:text-amber-300 hover:underline"
                >
                  ← القائمة
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="block text-sm space-y-1">
                  <span className="text-gray-500">المخلص الجمركي</span>
                  <select
                    value={formBroker === "" ? "" : String(formBroker)}
                    onChange={(e) =>
                      setFormBroker(
                        e.target.value === "" ? "" : Number(e.target.value)
                      )
                    }
                    className="w-full rounded-xl border border-gray-200 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
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
                  <span className="text-gray-500">رقم البيان / الإقرار</span>
                  <input
                    value={formDecl}
                    onChange={(e) => setFormDecl(e.target.value)}
                    className="w-full rounded-xl border border-gray-200 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                </label>
                <label className="block text-sm space-y-1">
                  <span className="text-gray-500">تاريخ التخليص</span>
                  <input
                    type="date"
                    value={formDate}
                    onChange={(e) => setFormDate(e.target.value)}
                    className="w-full rounded-xl border border-gray-200 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                </label>
                <label className="block text-sm space-y-1">
                  <span className="text-gray-500">الحالة</span>
                  <select
                    value={formStatus}
                    onChange={(e) => setFormStatus(e.target.value)}
                    className="w-full rounded-xl border border-gray-200 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
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
                <span className="text-gray-500">ملاحظات</span>
                <textarea
                  value={formNotes}
                  onChange={(e) => setFormNotes(e.target.value)}
                  rows={2}
                  className="w-full rounded-xl border border-gray-200 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                />
              </label>

              <div className="grid grid-cols-1 gap-6">
                <div className="rounded-2xl border-2 border-blue-200/90 dark:border-blue-900/55 bg-blue-50/25 dark:bg-blue-950/20 p-4 sm:p-5 space-y-4">
                  <div className="border-b border-blue-200/80 dark:border-blue-900/50 pb-2">
                    <h3 className="text-sm font-bold text-blue-900 dark:text-blue-100">
                      التخليص — دفع المخلّص
                    </h3>
                    <p className="text-xs font-semibold text-blue-900 dark:text-blue-100 mt-1.5 tabular-nums">
                      أصل ₪{clearanceBudgetIls.toLocaleString()} · مدفوع ₪{paidClearanceIls.toLocaleString()} · متبقي
                      ₪{remainingClearanceOnly.toLocaleString()}
                    </p>
                  </div>

              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold text-gray-800 dark:text-gray-100 text-sm">
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
                      className="text-xs px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
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
                      className="text-xs px-3 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700"
                    >
                      + بند
                    </button>
                  </div>
                </div>
                <div className="flex flex-wrap items-end gap-2 p-3 rounded-xl bg-amber-50/60 dark:bg-amber-950/25 border border-amber-200 dark:border-amber-900/50">
                  <label className="text-xs font-semibold text-amber-900 dark:text-amber-100 flex-1 min-w-[140px]">
                    التكلفة الكلية للتخليص (₪) — بند واحد
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={quickLumpTotal}
                      onChange={(e) => setQuickLumpTotal(e.target.value)}
                      placeholder="مثال: 14487"
                      className="mt-1 w-full rounded-lg border border-amber-200 dark:border-amber-800 px-2 py-2 bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm font-bold"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={applyQuickLumpTotal}
                    className="inline-flex items-center gap-1 px-4 py-2 rounded-lg bg-amber-600 text-white text-sm font-bold hover:bg-amber-700 shadow-sm"
                  >
                    تطبيق كإجمالي
                  </button>
                </div>

                <details className="rounded-xl border border-dashed border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/40 px-3 py-2">
                  <summary className="text-xs cursor-pointer text-gray-600 dark:text-gray-400 select-none py-1">
                    توزيع تلقائي بالتساوي على البنود الحالية (اختياري)
                  </summary>
                  <div className="flex flex-wrap items-end gap-2 pt-2 pb-1">
                    <label className="text-xs text-gray-500 flex-1 min-w-[120px]">
                      مبلغ يُقسَّم بالتساوي
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={distributeInput}
                        onChange={(e) => setDistributeInput(e.target.value)}
                        placeholder="مثال: 1500"
                        className="mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={applyDistribute}
                      className="inline-flex items-center gap-1 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700"
                    >
                      <Split className="w-4 h-4" />
                      وزّع
                    </button>
                  </div>
                </details>

                <div className="rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-gray-800/80 text-gray-600 dark:text-gray-300">
                      <tr>
                        <th className="text-right px-3 py-2">البند</th>
                        <th className="text-right px-3 py-2 w-32">المبلغ</th>
                        <th className="w-10" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
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
                              className="w-full rounded-lg border border-transparent hover:border-gray-200 dark:hover:border-gray-600 focus:border-amber-500 px-2 py-1 bg-transparent text-gray-900 dark:text-white"
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
                              className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
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
                              className="p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="text-left font-bold text-amber-700 dark:text-amber-300 text-sm">
                  مجموع بنود التخليص: ₪
                  {sumLines(formLines).toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                  })}
                </div>
              </div>

                  <div className="space-y-3 border-t border-blue-200/70 dark:border-blue-900/40 pt-4">
                    {clearancePayClosed ? (
                      <p className="text-xs font-semibold text-emerald-800 dark:text-emerald-200 py-2">
                        تم سداد التخليص بالكامل — لا دفع إضافي ضمن هذا الأصل.
                      </p>
                    ) : (
                      <>
                        <span className="text-xs font-bold text-blue-900 dark:text-blue-100 block">
                          دفع للمخلّص (صف واحد)
                        </span>
                        <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-end">
                          <label className="block text-xs space-y-1 sm:col-span-5 text-gray-600 dark:text-gray-400">
                            <span>الصندوق</span>
                            <select
                              value={payCashBoxId}
                              onChange={(e) => setPayCashBoxId(e.target.value)}
                              className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                            >
                              <option value="">اختر…</option>
                              {cashLedgers.map((l) => (
                                <option key={l.id} value={l.external_id}>
                                  {l.name} ({l.account_code})
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="block text-xs space-y-1 sm:col-span-3 text-gray-600 dark:text-gray-400">
                            <span>التاريخ</span>
                            <input
                              type="date"
                              value={payDate}
                              onChange={(e) => setPayDate(e.target.value)}
                              className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                            />
                          </label>
                          <label className="block text-xs space-y-1 sm:col-span-2 text-gray-600 dark:text-gray-400">
                            <span>₪</span>
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              value={payAmount}
                              onChange={(e) => setPayAmount(e.target.value)}
                              className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm font-semibold"
                            />
                          </label>
                          <div className="sm:col-span-2">
                            <button
                              type="button"
                              onClick={handlePostPayment}
                              disabled={paying}
                              className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl bg-blue-600 px-3 py-2.5 text-sm font-bold text-white hover:bg-blue-700 disabled:opacity-50"
                            >
                              {paying ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                              دفع
                            </button>
                          </div>
                        </div>
                        <details className="text-xs">
                          <summary className="cursor-pointer text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
                            ملاحظات الدفع (اختياري)
                          </summary>
                          <input
                            value={payNotes}
                            onChange={(e) => setPayNotes(e.target.value)}
                            className="mt-2 w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                            placeholder="اختياري"
                          />
                        </details>
                      </>
                    )}
                    <ClearancePaymentMiniTable rows={clearancePaymentRows} cashBoxDisplayName={cashBoxDisplayName} />
                  </div>
                </div>

                <div className="rounded-2xl border-2 border-amber-300/90 dark:border-amber-800/55 bg-amber-50/35 dark:bg-amber-950/25 p-4 sm:p-5 space-y-4">
                  <div className="border-b border-amber-200/80 dark:border-amber-900/50 pb-2">
                    <h3 className="text-sm font-bold text-amber-950 dark:text-amber-100">
                      النقل المحلي — دفع الناقل
                    </h3>
                    <p className="text-xs font-semibold text-amber-950 dark:text-amber-100 mt-1.5 tabular-nums">
                      أصل ₪{shippingBudgetIls.toLocaleString()} · مدفوع ₪{paidShippingIls.toLocaleString()} · متبقي ₪
                      {remainingShippingOnly.toLocaleString()}
                    </p>
                  </div>

                  <label className="block text-xs space-y-1 text-gray-700 dark:text-gray-300">
                    <span className="font-medium">مبلغ النقل المحلي ₪</span>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={shippingLineAmount || ""}
                      onChange={(e) => setShippingLineAmount(parseFloat(e.target.value) || 0)}
                      className="w-full max-w-xs rounded-xl border border-amber-200 dark:border-amber-800 px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white font-semibold"
                    />
                  </label>
                  <ClearancePaymentMiniTable rows={shippingPaymentRows} cashBoxDisplayName={cashBoxDisplayName} />

                  <div className="space-y-3 border-t border-amber-200/80 dark:border-amber-900/50 pt-4">
                    {shippingPayClosed ? (
                      <p className="text-xs font-semibold text-emerald-800 dark:text-emerald-200 py-2">
                        تم سداد النقل المحلي بالكامل — لا دفع إضافي ضمن هذا الأصل.
                      </p>
                    ) : (
                      <>
                        <span className="text-xs font-bold text-amber-950 dark:text-amber-100 block">
                          تسجيل دفعة للناقل (صف واحد)
                        </span>
                        <label className="block text-xs space-y-1 text-gray-600 dark:text-gray-400">
                          <span>السائق / الناقل</span>
                          <select
                            value={shipPayPartnerId === "" ? "" : String(shipPayPartnerId)}
                            onChange={(e) =>
                              setShipPayPartnerId(e.target.value === "" ? "" : Number(e.target.value))
                            }
                            className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                          >
                            <option value="">اختر الشريك…</option>
                            {transportPartners.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name}
                                {p.partner_type ? ` (${p.partner_type})` : ""}
                              </option>
                            ))}
                          </select>
                          {transportPartners.length === 0 ? (
                            <span className="text-[10px] text-amber-800 dark:text-amber-300 mt-1 block">
                              أضف شريكاً من نوع ناقل محلي أو وكيل شحن مع ربط حساب محاسبي.
                            </span>
                          ) : null}
                        </label>
                        <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-end">
                          <label className="block text-xs space-y-1 sm:col-span-5 text-gray-600 dark:text-gray-400">
                            <span>الصندوق</span>
                            <select
                              value={shipPayCashBoxId}
                              onChange={(e) => setShipPayCashBoxId(e.target.value)}
                              className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                            >
                              <option value="">اختر…</option>
                              {cashLedgers.map((l) => (
                                <option key={l.id} value={l.external_id}>
                                  {l.name} ({l.account_code})
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="block text-xs space-y-1 sm:col-span-3 text-gray-600 dark:text-gray-400">
                            <span>التاريخ</span>
                            <input
                              type="date"
                              value={shipPayDate}
                              onChange={(e) => setShipPayDate(e.target.value)}
                              className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                            />
                          </label>
                          <label className="block text-xs space-y-1 sm:col-span-2 text-gray-600 dark:text-gray-400">
                            <span>₪</span>
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              value={shipPayAmount}
                              onChange={(e) => setShipPayAmount(e.target.value)}
                              className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm font-semibold"
                            />
                          </label>
                          <div className="sm:col-span-2">
                            <button
                              type="button"
                              onClick={() => void handleShipPostPayment()}
                              disabled={paying}
                              className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl bg-amber-800 px-3 py-2.5 text-sm font-bold text-white hover:bg-amber-900 disabled:opacity-50 dark:bg-amber-700 dark:hover:bg-amber-800"
                            >
                              {paying ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                              دفع
                            </button>
                          </div>
                        </div>
                        <details className="text-xs">
                          <summary className="cursor-pointer text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
                            ملاحظات (اختياري)
                          </summary>
                          <input
                            value={shipPayNotes}
                            onChange={(e) => setShipPayNotes(e.target.value)}
                            className="mt-2 w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                            placeholder="اختياري"
                          />
                        </details>
                      </>
                    )}
                  </div>
                </div>
              </div>

              <div className="text-left space-y-0.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50/80 dark:bg-gray-800/40 px-4 py-3">
                <div className="text-xs font-bold text-gray-700 dark:text-gray-200">
                  الإجمالي (تخليص + نقل محلي): ₪
                  {totalClearance.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                  })}
                </div>
                <div className="text-[10px] text-gray-600 dark:text-gray-400">
                  المتبقي بعد كل الدفعات: ₪{remaining.toLocaleString()}
                  {remaining === 0 ? " — مغلق" : ""}
                </div>
              </div>

              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-amber-600 text-white font-bold hover:bg-amber-700 disabled:opacity-50"
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
  );
};
