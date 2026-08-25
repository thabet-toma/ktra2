/**
 * M1 — Create Shipment from Deals (fixes RC-1).
 *
 * The platform-standard action the owner asked for: pick one or many
 * Ready-to-Ship deals, choose the freight chargeable unit (CBM or KG) and rate,
 * see live CBM & KG totals and the resulting freight, then create ONE shipment.
 * Replaces the old "make an empty shipment then hunt for deals one by one".
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { X, Ship, PackageCheck } from "lucide-react";
import { apiGetList, apiPostObject } from "@/services/restApi";
import { resolveTenantId } from "@/utils/tenantContext";
import { formatMoney } from "@/utils/formatNumber";
import { useToast } from "@/contexts/ToastContext";

const tid = () => resolveTenantId();

type ChargeableUnit = "cbm" | "kg";

interface ReadyDealRow {
  id: number;
  ref_number: string;
  short_name?: string;
  description?: string;
  partner_name?: string;
  stage: string;
  total_amount?: number | string;
  total_cbm?: number | string;
  total_weight_kg?: number | string;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  /** Called with the new shipment id on success (caller navigates to the journey). */
  onCreated: (shipmentId: number) => void;
  /** Optional: when provided, shows an "empty shipment" escape hatch (header-first flow). */
  onCreateEmpty?: () => void;
}

const num = (v: number | string | null | undefined): number => {
  const n = typeof v === "string" ? parseFloat(v) : v ?? 0;
  return Number.isFinite(n as number) ? (n as number) : 0;
};

export const CreateShipmentFromDealsModal: React.FC<Props> = ({ isOpen, onClose, onCreated, onCreateEmpty }) => {
  const toast = useToast();
  const [rows, setRows] = useState<ReadyDealRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [unit, setUnit] = useState<ChargeableUnit>("cbm");
  const [rate, setRate] = useState("");
  const [shipmentName, setShipmentName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setError(null);
    setSelected(new Set());
    apiGetList<ReadyDealRow>("logistics/deals/ready-to-ship/", { tenantId: tid() })
      .then((r) => setRows(r))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [isOpen]);

  const toggle = useCallback((id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    setSelected((prev) => (prev.size === rows.length ? new Set() : new Set(rows.map((r) => r.id))));
  }, [rows]);

  const totals = useMemo(() => {
    const chosen = rows.filter((r) => selected.has(r.id));
    const cbm = chosen.reduce((s, r) => s + num(r.total_cbm), 0);
    const kg = chosen.reduce((s, r) => s + num(r.total_weight_kg), 0);
    const units = unit === "cbm" ? cbm : kg;
    const freight = units * num(rate);
    return { cbm, kg, units, freight, count: chosen.length };
  }, [rows, selected, unit, rate]);

  const handleCreate = useCallback(async () => {
    if (selected.size === 0) {
      setError("اختر صفقة واحدة على الأقل.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await apiPostObject<{ id: number }>(
        "logistics/shipments/create-from-deals/",
        {
          deal_ids: Array.from(selected),
          chargeable_unit: unit,
          freight_rate: rate ? Number(rate) : 0,
          header: shipmentName.trim() ? { shipment_name: shipmentName.trim() } : {},
        },
        { tenantId: tid() },
      );
      toast(`تم إنشاء الشحنة من ${selected.size} صفقة — تابع رحلة الاستيراد.`, "success");
      onCreated(created.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [selected, unit, rate, shipmentName, toast, onCreated]);

  if (!isOpen) return null;

  const unitLabel = unit === "cbm" ? "CBM" : "KG";

  return (
    <div
      dir="rtl"
      style={{ position: "fixed", inset: 0, zIndex: 60, background: "rgba(0,0,0,0.45)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}
      onClick={onClose}
    >
      <div
        style={{ background: "var(--ktra-bg, #fff)", color: "var(--ktra-ink)", borderRadius: 10, width: "min(880px, 100%)", maxHeight: "90vh", display: "flex", flexDirection: "column", boxShadow: "0 10px 40px rgba(0,0,0,0.3)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px", borderBottom: "1px solid var(--ktra-border)" }}>
          <Ship style={{ width: 18, height: 18, color: "var(--ktra-accent, #1857a4)" }} />
          <strong style={{ fontSize: "var(--ktra-fs-title, 14px)" }}>إنشاء شحنة من الصفقات الجاهزة</strong>
          <div style={{ flex: 1 }} />
          <button className="ktra-toolbtn" onClick={onClose} title="إغلاق"><X style={{ width: 16, height: 16 }} /></button>
        </div>

        {/* Body */}
        <div style={{ padding: "12px 16px", overflowY: "auto", flex: 1 }}>
          {error && (
            <div style={{ background: "var(--ktra-danger-bg, #fdecec)", color: "var(--ktra-danger, #c00)", padding: "6px 10px", borderRadius: 6, marginBottom: 10, fontSize: "var(--ktra-fs-sm, 12px)" }}>
              {error}
            </div>
          )}

          {loading ? (
            <p style={{ color: "var(--ktra-ink-soft)" }}>جارٍ تحميل الصفقات الجاهزة…</p>
          ) : rows.length === 0 ? (
            // G4: بدل رسالة سلبية تُشير لـ«شحنة فارغة» دون زر (طريق مسدود) —
            // حالة فارغة موجِّهة بإجراء واضح للأمام.
            <div style={{ textAlign: "center", padding: "18px 8px", color: "var(--ktra-ink-soft)" }}>
              <PackageCheck style={{ width: 28, height: 28, opacity: 0.5, marginInline: "auto" }} />
              <p style={{ margin: "10px 0 4px", fontWeight: 600, color: "var(--ktra-ink)" }}>
                لا صفقات جاهزة للشحن بعد
              </p>
              <p style={{ margin: "0 auto", maxWidth: 460, fontSize: "var(--ktra-fs-sm, 12px)" }}>
                جهّز صفقة أولاً: افتحها ثم اضغط «ابدأ الشحن الدولي» في تبويب «المراحل والشحن»
                (تصل المرحلة إلى «تم الشحن للوكيل»). أو ابدأ شحنة فارغة الآن واضمم الصفقات لاحقاً.
              </p>
              {onCreateEmpty && (
                <button
                  className="ktra-toolbtn"
                  onClick={onCreateEmpty}
                  style={{ marginTop: 12, background: "var(--ktra-accent, #1857a4)", color: "#fff" }}
                >
                  <Ship style={{ width: 14, height: 14 }} /> بدء شحنة فارغة
                </button>
              )}
            </div>
          ) : (
            <table className="ktra-input" style={{ width: "100%", fontSize: "var(--ktra-fs-sm, 12px)", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "right", color: "var(--ktra-ink-soft)" }}>
                  <th style={{ width: 32 }}>
                    <input type="checkbox" checked={selected.size === rows.length && rows.length > 0} onChange={toggleAll} title="تحديد الكل" />
                  </th>
                  <th>الصفقة</th>
                  <th>المورد</th>
                  <th style={{ textAlign: "left" }}>CBM</th>
                  <th style={{ textAlign: "left" }}>KG</th>
                  <th style={{ textAlign: "left" }}>القيمة</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const on = selected.has(r.id);
                  return (
                    <tr
                      key={r.id}
                      onClick={() => toggle(r.id)}
                      style={{ cursor: "pointer", background: on ? "var(--ktra-accent-bg, #eaf1fb)" : undefined, borderTop: "1px solid var(--ktra-border)" }}
                    >
                      <td><input type="checkbox" checked={on} onChange={() => toggle(r.id)} onClick={(e) => e.stopPropagation()} /></td>
                      <td>
                        <b style={{ fontFamily: "monospace" }}>{r.ref_number}</b>
                        {r.stage === "ready_to_ship" && (
                          <span title="جاهزة للشحن" style={{ marginRight: 4, color: "var(--ktra-ok, #267346)" }}>
                            <PackageCheck style={{ width: 12, height: 12, display: "inline" }} />
                          </span>
                        )}
                        <div style={{ color: "var(--ktra-ink-soft)" }}>{r.short_name || r.description || ""}</div>
                      </td>
                      <td>{r.partner_name || "—"}</td>
                      <td style={{ textAlign: "left", fontFamily: "monospace" }}>{formatMoney(num(r.total_cbm))}</td>
                      <td style={{ textAlign: "left", fontFamily: "monospace" }}>{formatMoney(num(r.total_weight_kg))}</td>
                      <td style={{ textAlign: "left", fontFamily: "monospace" }}>${formatMoney(num(r.total_amount))}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Freight controls + live totals */}
        <div style={{ padding: "10px 16px", borderTop: "1px solid var(--ktra-border)", background: "var(--ktra-surface, #f7f8fa)" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: "var(--ktra-fs-sm, 12px)" }}>
              اسم الشحنة (اختياري)
              <input className="ktra-input" style={{ width: 180 }} value={shipmentName} onChange={(e) => setShipmentName(e.target.value)} placeholder="مثال: شحنة الصين يوليو" />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: "var(--ktra-fs-sm, 12px)" }}>
              وحدة التسعير
              <div style={{ display: "inline-flex", border: "1px solid var(--ktra-border)", borderRadius: 6, overflow: "hidden" }}>
                {(["cbm", "kg"] as ChargeableUnit[]).map((u) => (
                  <button
                    key={u}
                    type="button"
                    onClick={() => setUnit(u)}
                    className="ktra-toolbtn"
                    style={{ borderRadius: 0, background: unit === u ? "var(--ktra-accent, #1857a4)" : "transparent", color: unit === u ? "#fff" : "var(--ktra-ink)", padding: "4px 14px" }}
                  >
                    {u.toUpperCase()}
                  </button>
                ))}
              </div>
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: "var(--ktra-fs-sm, 12px)" }}>
              سعر الشحن لكل {unitLabel}
              <input className="ktra-input" style={{ width: 120 }} type="number" step="0.0001" min="0" value={rate} onChange={(e) => setRate(e.target.value)} placeholder="0.00" />
            </label>
            <div style={{ flex: 1 }} />
            <div style={{ fontSize: "var(--ktra-fs-sm, 12px)", lineHeight: 1.7, textAlign: "left" }}>
              <div>محدَّد: <b>{totals.count}</b> صفقة · <b>{formatMoney(totals.cbm)}</b> CBM · <b>{formatMoney(totals.kg)}</b> KG</div>
              <div>
                إجمالي الشحن = {formatMoney(num(rate))} × {formatMoney(totals.units)} {unitLabel} ={" "}
                <b style={{ color: "var(--ktra-accent, #1857a4)" }}>${formatMoney(totals.freight)}</b>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 8, marginTop: 10 }}>
            {onCreateEmpty && (
              <button
                className="ktra-toolbtn"
                onClick={onCreateEmpty}
                disabled={saving}
                style={{ marginInlineEnd: "auto" }}
                title="افتح شحنة فارغة واملأ الترويسة أولاً ثم اضمم الصفقات لاحقاً"
              >
                إنشاء شحنة فارغة (بدون صفقات)
              </button>
            )}
            <button className="ktra-toolbtn" onClick={onClose} disabled={saving}>إلغاء</button>
            <button
              className="ktra-toolbtn"
              onClick={() => void handleCreate()}
              disabled={saving || selected.size === 0}
              style={{ background: "var(--ktra-accent, #1857a4)", color: "#fff" }}
              title="إنشاء الشحنة وفتح رحلة الاستيراد"
            >
              <Ship style={{ width: 14, height: 14 }} /> {saving ? "جارٍ الإنشاء…" : "إنشاء الشحنة"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
