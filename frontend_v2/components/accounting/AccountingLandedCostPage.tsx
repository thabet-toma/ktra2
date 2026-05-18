import React, { useState, useEffect, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { LandedCostReport, LandedCostShipment } from "../../types/accounting";
import { Ship, Search, ChevronRight, ChevronDown, Package, AlertCircle } from "lucide-react";
import { Spinner, EmptyState } from "../ui";

export const AccountingLandedCostPage: React.FC = () => {
  const today = new Date();
  const [start, setStart] = useState(() => {
    const d = new Date(today.getFullYear(), today.getMonth() - 3, 1);
    return d.toISOString().split("T")[0];
  });
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);
  const [data, setData] = useState<LandedCostReport | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [detail, setDetail] = useState<LandedCostShipment | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const resp = await accountingApi.getLandedCostReport({
        start_date: start,
        end_date: end,
      });
      setData(resp as LandedCostReport);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التقرير");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [start, end]);

  const openDetail = useCallback(async (shipmentId: number) => {
    if (expanded === shipmentId) {
      setExpanded(null);
      setDetail(null);
      return;
    }
    setExpanded(shipmentId);
    setDetail(null);
    try {
      const resp = (await accountingApi.getLandedCostReport({
        shipment_id: String(shipmentId),
      })) as LandedCostReport;
      if (resp.shipments && resp.shipments.length > 0) {
        setDetail(resp.shipments[0]);
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    }
  }, [expanded]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const fmt = (n: number | null | undefined) =>
    (Number(n) || 0).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  return (
    <div className="space-y-4" dir="rtl">
      <div className="flex flex-wrap items-center gap-3 p-4 bg-gradient-to-l from-cyan-900 to-slate-900 text-white rounded-xl">
        <Ship className="w-8 h-8 text-cyan-300" />
        <div>
          <h1 className="text-lg font-bold">تقرير التكلفة المستوردة (Landed Cost)</h1>
          <p className="text-xs text-cyan-200">
            بضاعة + شحن دولي + تخليص + رسوم مرسملة — لكل شحنة
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 items-end bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
        <div>
          <label className="block text-xs text-gray-500 mb-1">وصول من</label>
          <input
            type="date"
            className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">وصول إلى</label>
          <input
            type="date"
            className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </div>
        <button
          type="button"
          onClick={fetch}
          className="flex items-center gap-2 px-4 py-2 bg-cyan-600 text-white rounded-lg text-sm"
        >
          <Search className="w-4 h-4" />
          تحديث
        </button>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 text-sm flex gap-2 items-center">
          <AlertCircle className="w-4 h-4" />
          {err}
        </div>
      )}

      {loading ? (
        <div className="py-16 flex justify-center"><Spinner /></div>
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <th className="w-8"></th>
                <th className="text-right p-3">الشحنة</th>
                <th className="text-right p-3">الوصول</th>
                <th className="text-right p-3">الحالة</th>
                <th className="text-right p-3">الوكيل</th>
                <th className="text-right p-3">البضاعة</th>
                <th className="text-right p-3">شحن دولي (USD)</th>
                <th className="text-right p-3">تخليص</th>
                <th className="text-right p-3">رسوم مرسملة</th>
                <th className="text-right p-3">إجمالي Landed</th>
              </tr>
            </thead>
            <tbody>
              {(data?.shipments || []).map((sh) => (
                <React.Fragment key={sh.shipment_id}>
                  <tr
                    className={`border-t border-gray-100 dark:border-gray-700 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-900/40 ${
                      expanded === sh.shipment_id
                        ? "bg-cyan-50/50 dark:bg-cyan-900/10"
                        : ""
                    }`}
                    onClick={() => openDetail(sh.shipment_id)}
                  >
                    <td className="text-center">
                      {expanded === sh.shipment_id ? (
                        <ChevronDown className="w-4 h-4 inline text-cyan-600" />
                      ) : (
                        <ChevronRight className="w-4 h-4 inline text-gray-400" />
                      )}
                    </td>
                    <td className="p-2 font-mono">{sh.shipment_number}</td>
                    <td className="p-2">{sh.arrival_date || "—"}</td>
                    <td className="p-2">
                      <span className="text-xs px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-700">
                        {sh.status}
                      </span>
                    </td>
                    <td className="p-2">{sh.shipping_agent || "—"}</td>
                    <td className="p-2 text-right">{fmt(sh.total_merchandise)}</td>
                    <td className="p-2 text-right">
                      {fmt(sh.total_shipping_cost_usd)}
                    </td>
                    <td className="p-2 text-right">{fmt(sh.clearance_total)}</td>
                    <td className="p-2 text-right">
                      {fmt(sh.capitalized_fees_total)}
                    </td>
                    <td className="p-2 text-right font-bold text-cyan-700 dark:text-cyan-300">
                      {fmt(sh.grand_landed_cost_approx)}
                    </td>
                  </tr>
                  {expanded === sh.shipment_id && (
                    <tr>
                      <td colSpan={10} className="bg-slate-50 dark:bg-slate-900/40 p-4">
                        {detail ? (
                          <ShipmentDetail sh={detail} fmt={fmt} />
                        ) : (
                          <div className="py-4 flex justify-center"><Spinner size="sm" /></div>
                        )}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
          {data && data.shipments.length === 0 && (
            <EmptyState title="لا توجد شحنات" />
          )}
        </div>
      )}
    </div>
  );
};

const ShipmentDetail: React.FC<{
  sh: LandedCostShipment;
  fmt: (n: number | null | undefined) => string;
}> = ({ sh, fmt }) => (
  <div className="space-y-4">
    {/* الصفقات */}
    {sh.deals.map((d) => (
      <div
        key={d.deal_id}
        className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3"
      >
        <div className="flex flex-wrap items-center gap-3 mb-2">
          <Package className="w-4 h-4 text-indigo-500" />
          <span className="font-semibold">
            صفقة {d.ref_number || `#${d.deal_id}`}
          </span>
          <span className="text-xs text-gray-500">
            {d.partner_name} — {d.currency}
          </span>
          <span className="ml-auto text-xs">
            بضاعة: {fmt(d.merchandise_total)} | شحن مُخصَّص:{" "}
            {fmt(d.allocated_shipping_cost_usd)} USD
          </span>
        </div>

        {d.purchase_invoice ? (
          <div className="mt-2 space-y-2">
            <div className="flex flex-wrap gap-2 text-xs">
              <span className="px-2 py-1 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 rounded">
                فاتورة شراء: {d.purchase_invoice.invoice_number || "—"}
              </span>
              {d.purchase_invoice.is_posted && (
                <span className="px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
                  مرحّلة
                </span>
              )}
              <span className="px-2 py-1 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded">
                رسوم مرسملة: {fmt(d.purchase_invoice.capitalized_fees_total)}
              </span>
              <span className="px-2 py-1 bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300 rounded">
                رسوم مصروفة: {fmt(d.purchase_invoice.expensed_fees_total)}
              </span>
            </div>

            {d.purchase_invoice.fees.length > 0 && (
              <div>
                <div className="text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">
                  الرسوم
                </div>
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 dark:bg-gray-900/40">
                    <tr>
                      <th className="text-right p-1.5">الوصف</th>
                      <th className="text-right p-1.5">الحساب</th>
                      <th className="text-right p-1.5">المبلغ</th>
                      <th className="text-center p-1.5">رسملة</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.purchase_invoice.fees.map((f) => (
                      <tr key={f.id} className="border-t border-gray-100 dark:border-gray-700">
                        <td className="p-1.5">{f.description}</td>
                        <td className="p-1.5 font-mono">
                          {f.account_code} {f.account_name}
                        </td>
                        <td className="p-1.5 text-right">{fmt(f.amount)}</td>
                        <td className="p-1.5 text-center">
                          {f.capitalize_to_inventory ? "✓" : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {d.purchase_invoice.items.length > 0 && (
              <div>
                <div className="text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">
                  البنود (تكلفة مُنَزَّلة)
                </div>
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 dark:bg-gray-900/40">
                    <tr>
                      <th className="text-right p-1.5">الصنف</th>
                      <th className="text-right p-1.5">الكمية</th>
                      <th className="text-right p-1.5">سعر الصفقة</th>
                      <th className="text-right p-1.5">Landed/وحدة (ILS)</th>
                      <th className="text-right p-1.5">Landed إجمالي (ILS)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.purchase_invoice.items.map((it) => (
                      <tr key={it.id} className="border-t border-gray-100 dark:border-gray-700">
                        <td className="p-1.5">{it.name}</td>
                        <td className="p-1.5 text-right">{fmt(it.quantity)}</td>
                        <td className="p-1.5 text-right">{fmt(it.unit_price)}</td>
                        <td className="p-1.5 text-right font-semibold text-cyan-700 dark:text-cyan-300">
                          {it.landed_unit_price_ils != null
                            ? fmt(it.landed_unit_price_ils)
                            : "—"}
                        </td>
                        <td className="p-1.5 text-right font-semibold">
                          {it.landed_line_total_ils != null
                            ? fmt(it.landed_line_total_ils)
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          <div className="text-xs text-amber-700 bg-amber-50 dark:bg-amber-900/20 p-2 rounded mt-1">
            لا توجد فاتورة شراء مرتبطة بهذه الصفقة — استورد من التخليص الجمركي
            لحساب Landed Cost.
          </div>
        )}
      </div>
    ))}

    {/* تفاصيل التخليص */}
    {sh.clearance && (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
        <div className="font-semibold text-sm mb-2">
          التخليص الجمركي #{sh.clearance.id}
          {sh.clearance.declaration_number &&
            ` — بيان ${sh.clearance.declaration_number}`}
        </div>
        <div className="text-xs text-gray-500 mb-2">
          {sh.clearance.broker_name} · {sh.clearance.status} · دفعات مرحّلة:{" "}
          {fmt(sh.clearance.posted_payments_total)}
        </div>
        {sh.clearance.cost_lines.length > 0 && (
          <table className="w-full text-xs">
            <thead className="bg-gray-50 dark:bg-gray-900/40">
              <tr>
                <th className="text-right p-1.5">البند</th>
                <th className="text-right p-1.5">المبلغ</th>
              </tr>
            </thead>
            <tbody>
              {sh.clearance.cost_lines.map((ln, i) => (
                <tr key={i} className="border-t border-gray-100 dark:border-gray-700">
                  <td className="p-1.5">{ln.label}</td>
                  <td className="p-1.5 text-right">{fmt(ln.amount)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-gray-100 dark:bg-gray-900/40 font-semibold">
                <td className="p-1.5">الإجمالي</td>
                <td className="p-1.5 text-right">{fmt(sh.clearance.cost_lines_total)}</td>
              </tr>
            </tfoot>
          </table>
        )}
      </div>
    )}
  </div>
);
