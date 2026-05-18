import React, { useEffect, useMemo, useState } from "react";
import { apiGetList, apiGetObject } from "../../services/restApi";
import { SqlDataPageShell } from "./SqlDataPageShell";
import { Truck, Plane, Ship, Eye } from "lucide-react";
import { buildShipmentOptionLabel, ShipmentLabelInput } from "@/utils/shipmentLabel";

type ShipmentRow = ShipmentLabelInput & {
  status?: string;
  departure_date?: string | null;
  arrival_date?: string | null;
  shipping_agent?: any;
  bill_of_lading?: string | null;
  container_number?: string | null;
};

export function SqlShipmentsPage() {
  const [rows, setRows] = useState<ShipmentRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ShipmentRow | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setErr(null);
    apiGetList<ShipmentRow>("logistics/shipments/", { tenantId: 1 })
      .then((data) => mounted && setRows(data))
      .catch((e) => mounted && setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return rows;
    return rows.filter((r) => {
      const txt = `${buildShipmentOptionLabel(r)} ${r.status || ""} ${r.shipping_agent?.name || ""} ${r.bill_of_lading || ""} ${r.container_number || ""}`.toLowerCase();
      return txt.includes(s);
    });
  }, [rows, q]);

  const openShipment = async (row: ShipmentRow) => {
    setSelected(row);
    setDetailsOpen(true);
    setLoadingDetail(true);
    try {
      const data = await apiGetObject<ShipmentRow>(`logistics/shipments/${row.id}/`, { tenantId: 1 });
      setSelected(data);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingDetail(false);
    }
  };

  return (
    <>
    <SqlDataPageShell
      title="إدارة الشحنات"
      subtitle="نفس أسلوب العرض الاحترافي مع تفاصيل عند الضغط."
      actions={
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="بحث برقم/وكيل/حالة..."
          className="w-72 max-w-[70vw] px-3 py-2 border rounded-lg text-sm"
        />
      }
    >
      {err ? (
        <div className="p-4 text-sm text-red-700 bg-red-50 border-b border-red-100">
          {err}
        </div>
      ) : null}

      <div className="p-3 space-y-2">
        {loading ? (
          <div className="p-4 text-gray-500 text-sm">جارِ التحميل...</div>
        ) : filtered.length === 0 ? (
          <div className="p-4 text-gray-500 text-sm">لا يوجد بيانات.</div>
        ) : (
          filtered.map((r) => {
            const isAir = (r.status || "").toLowerCase().includes("air");
            return (
              <div key={r.id} className="border rounded-xl p-3 bg-white hover:bg-gray-50 transition">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="p-2 rounded-lg bg-blue-50 text-blue-600">
                      {isAir ? <Plane className="w-4 h-4" /> : <Ship className="w-4 h-4" />}
                    </div>
                    <div className="min-w-0">
                      <div className="font-bold text-sm">{buildShipmentOptionLabel(r)}</div>
                      <div className="text-xs text-gray-500 mt-1">
                        <Truck className="w-3 h-3 inline ml-1" />
                        {r.shipping_agent?.name || "-"} • {r.status || "-"}
                      </div>
                    </div>
                  </div>
                  <div className="text-right text-xs text-gray-500">
                    <div>Dep: {r.departure_date || "-"}</div>
                    <div>Arr: {r.arrival_date || "-"}</div>
                  </div>
                  <button
                    onClick={() => openShipment(r)}
                    className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border text-sm hover:bg-gray-100"
                  >
                    <Eye className="w-4 h-4" />
                    عرض التفاصيل
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </SqlDataPageShell>
    {detailsOpen && (
      <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-3" onClick={() => setDetailsOpen(false)}>
        <div className="bg-white rounded-xl w-full max-w-4xl max-h-[90vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
          <div className="sticky top-0 bg-white border-b px-4 py-3 flex items-center justify-between">
            <div className="font-bold">تفاصيل الشحنة</div>
            <button className="px-3 py-1 text-sm rounded border" onClick={() => setDetailsOpen(false)}>إغلاق</button>
          </div>
          <div className="p-4">
            {loadingDetail ? (
              <div className="text-sm text-gray-500">جار تحميل التفاصيل...</div>
            ) : !selected ? (
              <div className="text-sm text-gray-500">تعذر تحميل التفاصيل.</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div><span className="text-gray-500">رقم الشحنة:</span> {selected.shipment_number || "-"}</div>
                <div><span className="text-gray-500">الحالة:</span> {selected.status || "-"}</div>
                <div><span className="text-gray-500">وكيل الشحن:</span> {selected.shipping_agent?.name || "-"}</div>
                <div><span className="text-gray-500">Departure:</span> {selected.departure_date || "-"}</div>
                <div><span className="text-gray-500">Arrival:</span> {selected.arrival_date || "-"}</div>
                <div><span className="text-gray-500">B/L:</span> {selected.bill_of_lading || "-"}</div>
                <div className="md:col-span-2"><span className="text-gray-500">Container:</span> {selected.container_number || "-"}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    )}
    </>
  );
}

