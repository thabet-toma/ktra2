/**
 * N7-T9 — PropertyRentalPage — Aseel layout + AseelDenseTable للوحدات والعقود والقراءات
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  realestateApi,
  type RealestateBuilding,
  type RentalUnitRow,
  type LeaseRow,
  type ElectricMeterRow,
  type MeterReadingRow,
  type RealestateSummary,
} from "../../services/realestateApi";
import { Building2, Zap, Home, Warehouse, Plus, RefreshCw, ClipboardList, Users } from "lucide-react";
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";
import { useAseelIndexKeymap } from "../aseel/useAseelIndexKeymap";

function fmtMoney(s: string | number) {
  const n = typeof s === "string" ? parseFloat(s) : s;
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("ar-EG", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

function fmtKwh(s: string | number) {
  const n = typeof s === "string" ? parseFloat(s) : s;
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("ar-EG", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
}

type ReadingWithDelta = MeterReadingRow & { delta: number | null };

function computeReadingsWithDelta(rows: MeterReadingRow[]): ReadingWithDelta[] {
  const sorted = [...rows].sort(
    (a, b) => new Date(b.reading_date).getTime() - new Date(a.reading_date).getTime() || b.id - a.id
  );
  return sorted.map((r, idx, arr) => {
    const sameMeterOlder = arr.slice(idx + 1).find(x => x.meter === r.meter);
    const cur = parseFloat(r.kwh_value);
    const prev = sameMeterOlder ? parseFloat(sameMeterOlder.kwh_value) : NaN;
    const delta = Number.isFinite(cur) && Number.isFinite(prev) ? Math.max(0, cur - prev) : null;
    return { ...r, delta };
  });
}

export const PropertyRentalPage: React.FC = () => {
  const [buildings, setBuildings] = useState<RealestateBuilding[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [units, setUnits] = useState<RentalUnitRow[]>([]);
  const [leases, setLeases] = useState<LeaseRow[]>([]);
  const [meters, setMeters] = useState<ElectricMeterRow[]>([]);
  const [readings, setReadings] = useState<MeterReadingRow[]>([]);
  const [summary, setSummary] = useState<RealestateSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const [newBuilding, setNewBuilding] = useState({ name: "", address: "" });
  const [unitForm, setUnitForm] = useState({ code: "", floor_number: 0, unit_type: "apartment" as "apartment" | "warehouse" });
  const [leaseForm, setLeaseForm] = useState({ unit_id: "" as string | number, renter_name: "", renter_phone: "", monthly_rent: "", start_date: "" });
  const [meterForm, setMeterForm] = useState({ kind: "sub" as "main" | "sub", unit_id: "" as string | number, label: "", serial_number: "" });
  const [readingForm, setReadingForm] = useState({ meter_id: "" as string | number, reading_date: new Date().toISOString().slice(0, 10), kwh_value: "", notes: "" });

  const loadBuildings = useCallback(async () => {
    setErr(null);
    try {
      const list = await realestateApi.listBuildings();
      setBuildings(list);
      setSelectedId(prev => prev == null && list.length > 0 ? list[0].id : prev);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ في تحميل العمارات");
    }
  }, []);

  const loadBuildingDetail = useCallback(async (bid: number) => {
    setLoading(true); setErr(null);
    try {
      const [u, l, m, r, s] = await Promise.all([
        realestateApi.listUnits(bid),
        realestateApi.listLeases(bid),
        realestateApi.listMeters(bid),
        realestateApi.listReadings(bid),
        realestateApi.summary(bid).catch(() => null),
      ]);
      setUnits(u); setLeases(l); setMeters(m); setReadings(r); setSummary(s);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ في تحميل التفاصيل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadBuildings(); }, []);
  useEffect(() => { if (selectedId != null) loadBuildingDetail(selectedId); }, [selectedId, loadBuildingDetail]);

  const selected = useMemo(() => buildings.find(b => b.id === selectedId) ?? null, [buildings, selectedId]);

  const mainMeter = meters.find(m => m.meter_kind === "main");
  const subMeters = meters.filter(m => m.meter_kind === "sub");
  const readingsWithDelta = useMemo(() => computeReadingsWithDelta(readings), [readings]);

  useAseelIndexKeymap({
    F5: () => { loadBuildings(); if (selectedId) loadBuildingDetail(selectedId); },
    F6: () => searchInputRef.current?.focus(),
  }, { enabled: true });

  const addBuilding = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBuilding.name.trim()) return;
    setErr(null);
    try {
      const b = await realestateApi.createBuilding({ name: newBuilding.name.trim(), address: newBuilding.address.trim() });
      setNewBuilding({ name: "", address: "" });
      setBuildings(prev => [...prev, b]);
      setSelectedId(b.id);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "فشل إنشاء العمارة"); }
  };

  const addUnit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedId || !unitForm.code.trim()) return;
    setErr(null);
    try {
      await realestateApi.createUnit({ building: selectedId, code: unitForm.code.trim(), floor_number: Number(unitForm.floor_number) || 0, unit_type: unitForm.unit_type });
      setUnitForm({ code: "", floor_number: 0, unit_type: "apartment" });
      await loadBuildingDetail(selectedId); await loadBuildings();
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "فشل إضافة الوحدة"); }
  };

  const addLease = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedId || !leaseForm.unit_id || !leaseForm.renter_name.trim() || !leaseForm.monthly_rent) return;
    setErr(null);
    try {
      await realestateApi.createLease({ unit: Number(leaseForm.unit_id), renter_name: leaseForm.renter_name.trim(), renter_phone: leaseForm.renter_phone.trim(), monthly_rent: leaseForm.monthly_rent, start_date: leaseForm.start_date || new Date().toISOString().slice(0, 10) });
      setLeaseForm({ unit_id: "", renter_name: "", renter_phone: "", monthly_rent: "", start_date: "" });
      await loadBuildingDetail(selectedId);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "فشل تسجيل الإيجار"); }
  };

  const addMeter = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedId) return;
    if (meterForm.kind === "sub" && !meterForm.unit_id) { setErr("اختر الوحدة للعداد الفرعي."); return; }
    setErr(null);
    try {
      await realestateApi.createMeter({ building: selectedId, meter_kind: meterForm.kind, rental_unit: meterForm.kind === "sub" ? Number(meterForm.unit_id) : null, label: meterForm.label.trim(), serial_number: meterForm.serial_number.trim() });
      setMeterForm({ kind: "sub", unit_id: "", label: "", serial_number: "" });
      await loadBuildingDetail(selectedId); await loadBuildings();
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "فشل إضافة العداد"); }
  };

  const addReading = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!readingForm.meter_id || !readingForm.kwh_value) return;
    setErr(null);
    try {
      await realestateApi.createReading({ meter: Number(readingForm.meter_id), reading_date: readingForm.reading_date, kwh_value: readingForm.kwh_value, notes: readingForm.notes.trim() });
      setReadingForm(f => ({ ...f, kwh_value: "", notes: "" }));
      if (selectedId) await loadBuildingDetail(selectedId);
    } catch (e: unknown) { setErr(e instanceof Error ? e.message : "فشل حفظ القراءة"); }
  };

  const unitCols: DenseColumn<RentalUnitRow>[] = [
    {
      key: 'code', header: 'الوحدة', render: u => (
        <span>
          {u.unit_type === "warehouse"
            ? <Warehouse style={{ display: 'inline', width: 13, height: 13, marginLeft: 4, color: 'var(--aseel-warn, #b8800a)' }} />
            : <Home style={{ display: 'inline', width: 13, height: 13, marginLeft: 4, color: 'var(--aseel-accent, #1857a4)' }} />}
          <b>{u.code}</b>
        </span>
      ),
    },
    { key: 'floor', header: 'الطابق', width: '70px', align: 'center', render: u => <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>{u.floor_number}</span> },
    { key: 'type', header: 'النوع', width: '80px', render: u => <>{u.unit_type === "warehouse" ? "مخزن" : "شقة"}</> },
    {
      key: 'status', header: 'الحالة', width: '70px', align: 'center',
      render: u => <span style={{ fontSize: 'var(--aseel-fs-sm)', color: u.is_active === false ? 'var(--aseel-danger, #c00)' : 'var(--aseel-ok, #267346)', fontWeight: 600 }}>
        {u.is_active === false ? 'غير نشط' : 'نشط'}
      </span>,
    },
  ];

  const leaseCols: DenseColumn<LeaseRow>[] = [
    { key: 'renter', header: 'المستأجر', render: l => <b>{l.renter_name}</b> },
    { key: 'unit', header: 'الوحدة', width: '80px', render: l => <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>{l.unit_code}</span> },
    { key: 'phone', header: 'الجوال', width: '110px', render: l => <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>{l.renter_phone || '—'}</span> },
    { key: 'rent', header: 'الإيجار', width: '90px', align: 'center', render: l => <b style={{ color: 'var(--aseel-ok, #267346)', fontFamily: 'monospace' }}>{fmtMoney(l.monthly_rent)}</b> },
    { key: 'start', header: 'من تاريخ', width: '100px', render: l => <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>{l.start_date || '—'}</span> },
  ];

  const readingCols: DenseColumn<ReadingWithDelta>[] = [
    { key: 'date', header: 'التاريخ', width: '100px', render: r => <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>{r.reading_date}</span> },
    { key: 'meter', header: 'العداد', width: '120px', render: r => <>{r.meter_label ?? `#${r.meter}`}</> },
    { key: 'kwh', header: 'القراءة', width: '100px', align: 'center', render: r => <span style={{ fontFamily: 'monospace' }}>{fmtKwh(r.kwh_value)}</span> },
    {
      key: 'delta', header: 'استهلاك الفترة', width: '120px', align: 'center',
      render: r => <span style={{ fontFamily: 'monospace', color: r.delta != null ? 'var(--aseel-ok, #267346)' : 'var(--aseel-ink-soft)' }}>
        {r.delta != null ? fmtKwh(r.delta) : '—'}
      </span>,
    },
    { key: 'notes', header: 'ملاحظة', render: r => <span style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)' }}>{r.notes || '—'}</span> },
  ];

  const sec: React.CSSProperties = { border: '1px solid var(--aseel-border)', borderRadius: 6, padding: '12px 14px', marginBottom: 12 };
  const secTitle: React.CSSProperties = { fontSize: 'var(--aseel-fs-title, 14px)', fontWeight: 700, color: 'var(--aseel-ink)', marginBottom: 10, paddingBottom: 8, borderBottom: '1px solid var(--aseel-border)', display: 'flex', alignItems: 'center', gap: 6 };
  const formRow: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 };

  return (
    <div dir="rtl" data-skin="aseel" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 0, padding: '8px 12px', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ paddingBottom: 8, borderBottom: '1px solid var(--aseel-border)', marginBottom: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Building2 style={{ width: 16, height: 16, color: 'var(--aseel-warn, #b8800a)' }} />
          <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>تأجير العقارات</strong>
          <span style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)' }}>عمارات، شقق، مخازن، عقود، عدادات</span>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {buildings.length > 0 && <span className="aseel-status-item">العمارات: <b>{buildings.length}</b></span>}
          {selected && <span className="aseel-status-item">الوحدات: <b>{units.length}</b></span>}
          {selected && <span className="aseel-status-item">العقود: <b>{leases.length}</b></span>}
          <button className="aseel-toolbtn" title="تحديث (F5)" onClick={() => { loadBuildings(); if (selectedId) loadBuildingDetail(selectedId); }}>
            <RefreshCw style={{ width: 13, height: 13 }} />
          </button>
        </div>
      </div>

      {err && <div style={{ padding: '6px 12px', fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-danger, #c00)', border: '1px solid var(--aseel-danger, #c00)', borderRadius: 4, marginBottom: 8, background: 'rgba(204,0,0,0.06)' }}>{err}</div>}

      {/* Layout: sidebar + main */}
      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 12, flex: 1, minHeight: 0 }}>

        {/* Sidebar — عمارات */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          <div style={sec}>
            <div style={secTitle}>
              <Building2 style={{ width: 13, height: 13 }} />
              العمارات
            </div>
            <form onSubmit={addBuilding} style={formRow}>
              <input className="aseel-input" placeholder="اسم العمارة" value={newBuilding.name} onChange={e => setNewBuilding(s => ({ ...s, name: e.target.value }))} />
              <input className="aseel-input" placeholder="العنوان (اختياري)" value={newBuilding.address} onChange={e => setNewBuilding(s => ({ ...s, address: e.target.value }))} />
              <button type="submit" className="aseel-toolbtn" style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center', padding: '4px 8px', color: 'var(--aseel-accent, #1857a4)', fontWeight: 700 }}>
                <Plus style={{ width: 12, height: 12 }} /> إضافة عمارة
              </button>
            </form>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 300, overflowY: 'auto' }}>
              {buildings.map(b => (
                <button key={b.id} type="button" onClick={() => setSelectedId(b.id)}
                  style={{ textAlign: 'right', borderRadius: 4, padding: '6px 8px', fontSize: 'var(--aseel-fs-sm)', background: b.id === selectedId ? 'rgba(24,87,164,0.10)' : 'transparent', color: b.id === selectedId ? 'var(--aseel-accent, #1857a4)' : 'var(--aseel-ink)', fontWeight: b.id === selectedId ? 700 : 400, border: b.id === selectedId ? '1px solid rgba(24,87,164,0.25)' : '1px solid transparent', cursor: 'pointer', width: '100%' }}>
                  <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.name}</span>
                  <span style={{ fontSize: '10px', color: 'var(--aseel-ink-soft)' }}>{b.units_count} وحدة{b.main_meter_id ? ' · عداد رئيسي' : ''}</span>
                </button>
              ))}
              {buildings.length === 0 && <div style={{ textAlign: 'center', padding: 12, fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)' }}>لا توجد عمارات بعد</div>}
            </div>
          </div>
        </div>

        {/* Main content */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0, overflowY: 'auto' }}>
          {!selected ? (
            <div style={{ border: '1px dashed var(--aseel-border)', borderRadius: 6, padding: 32, textAlign: 'center', fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)' }}>
              اختر عمارة أو أنشئ واحدة للبدء
            </div>
          ) : loading ? (
            <div style={{ textAlign: 'center', padding: 32, color: 'var(--aseel-ink-soft)', fontSize: 'var(--aseel-fs-sm)' }}>جار التحميل...</div>
          ) : (
            <>
              {/* Building header */}
              <div style={{ ...sec, background: 'rgba(24,87,164,0.03)', marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <div>
                    <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>{selected.name}</strong>
                    {selected.address && <div style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)', marginTop: 2 }}>{selected.address}</div>}
                  </div>
                  {summary && (
                    <div style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)', border: '1px solid var(--aseel-border)', borderRadius: 4, padding: '6px 10px', lineHeight: 1.7 }}>
                      <div style={{ fontWeight: 600, color: 'var(--aseel-warn, #b8800a)', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Zap style={{ width: 11, height: 11 }} /> لمحة عدادات
                      </div>
                      <div>الرئيسي: {summary.main_latest_kwh != null ? fmtKwh(summary.main_latest_kwh) : '—'} ك.و.س</div>
                      <div>مجموع الفرعي: {fmtKwh(summary.sub_latest_kwh_sum ?? 0)}</div>
                      {summary.main_minus_sub_latest_hint != null && (
                        <div>الفرق: {fmtKwh(summary.main_minus_sub_latest_hint)}</div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* وحدات + إيجار */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
                {/* وحدات */}
                <div style={sec}>
                  <div style={secTitle}>
                    <Home style={{ width: 13, height: 13, color: 'var(--aseel-accent, #1857a4)' }} />
                    الشقق والمخازن
                  </div>
                  <form onSubmit={addUnit} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 10 }}>
                    <input className="aseel-input" style={{ gridColumn: '1 / -1' }} placeholder="رمز الوحدة (مثال: 2ب، مخزن-أ)" value={unitForm.code} onChange={e => setUnitForm(s => ({ ...s, code: e.target.value }))} />
                    <input type="number" className="aseel-input" placeholder="الطابق" value={unitForm.floor_number} onChange={e => setUnitForm(s => ({ ...s, floor_number: Number(e.target.value) }))} />
                    <select className="aseel-input" value={unitForm.unit_type} onChange={e => setUnitForm(s => ({ ...s, unit_type: e.target.value as "apartment" | "warehouse" }))}>
                      <option value="apartment">شقة</option>
                      <option value="warehouse">مخزن</option>
                    </select>
                    <button type="submit" className="aseel-toolbtn" style={{ gridColumn: '1 / -1', padding: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, color: 'var(--aseel-accent, #1857a4)', fontWeight: 700 }}>
                      <Plus style={{ width: 12, height: 12 }} /> إضافة وحدة
                    </button>
                  </form>
                  <AseelDenseTable<RentalUnitRow>
                    columns={unitCols}
                    rows={units}
                    getRowKey={u => u.id}
                    loading={false}
                    emptyHint="لا توجد وحدات"
                  />
                </div>

                {/* إيجار */}
                <div style={sec}>
                  <div style={secTitle}>
                    <Users style={{ width: 13, height: 13, color: 'var(--aseel-ok, #267346)' }} />
                    عقود الإيجار
                  </div>
                  <form onSubmit={addLease} style={formRow}>
                    <select className="aseel-input" value={leaseForm.unit_id} onChange={e => setLeaseForm(s => ({ ...s, unit_id: e.target.value }))} required>
                      <option value="">— الوحدة —</option>
                      {units.map(u => <option key={u.id} value={u.id}>{u.code} ({u.unit_type === "warehouse" ? "مخزن" : "شقة"})</option>)}
                    </select>
                    <input className="aseel-input" placeholder="اسم المستأجر" value={leaseForm.renter_name} onChange={e => setLeaseForm(s => ({ ...s, renter_name: e.target.value }))} />
                    <input className="aseel-input" placeholder="جوال" value={leaseForm.renter_phone} onChange={e => setLeaseForm(s => ({ ...s, renter_phone: e.target.value }))} />
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                      <input type="number" step="0.01" className="aseel-input" placeholder="الإيجار الشهري" value={leaseForm.monthly_rent} onChange={e => setLeaseForm(s => ({ ...s, monthly_rent: e.target.value }))} />
                      <input type="date" className="aseel-input" value={leaseForm.start_date} onChange={e => setLeaseForm(s => ({ ...s, start_date: e.target.value }))} />
                    </div>
                    <button type="submit" className="aseel-toolbtn" style={{ padding: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, color: 'var(--aseel-ok, #267346)', fontWeight: 700 }}>
                      تسجيل عقد
                    </button>
                  </form>
                  <AseelDenseTable<LeaseRow>
                    columns={leaseCols}
                    rows={leases}
                    getRowKey={l => l.id}
                    loading={false}
                    emptyHint="لا توجد عقود"
                  />
                </div>
              </div>

              {/* عدادات */}
              <div style={{ ...sec, marginBottom: 10 }}>
                <div style={secTitle}>
                  <Zap style={{ width: 13, height: 13, color: 'var(--aseel-warn, #b8800a)' }} />
                  عدادات الكهرباء
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  <form onSubmit={addMeter} style={formRow}>
                    <span style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)' }}>عداد رئيسي واحد للعمارة، وفرعي لكل وحدة بفوترة منفصلة.</span>
                    <select className="aseel-input" value={meterForm.kind} onChange={e => setMeterForm(s => ({ ...s, kind: e.target.value as "main" | "sub" }))}>
                      <option value="main">عداد رئيسي (عمارة)</option>
                      <option value="sub">عداد فرعي (وحدة)</option>
                    </select>
                    {meterForm.kind === "sub" && (
                      <select className="aseel-input" value={meterForm.unit_id} onChange={e => setMeterForm(s => ({ ...s, unit_id: e.target.value }))}>
                        <option value="">— اختر الوحدة —</option>
                        {units.map(u => <option key={u.id} value={u.id}>{u.code}</option>)}
                      </select>
                    )}
                    <input className="aseel-input" placeholder="ملاحظة (اختياري)" value={meterForm.label} onChange={e => setMeterForm(s => ({ ...s, label: e.target.value }))} />
                    <input className="aseel-input" placeholder="رقم التسلسل (اختياري)" value={meterForm.serial_number} onChange={e => setMeterForm(s => ({ ...s, serial_number: e.target.value }))} />
                    <button type="submit" className="aseel-toolbtn" style={{ padding: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, color: 'var(--aseel-warn, #b8800a)', fontWeight: 700 }}>
                      <Plus style={{ width: 12, height: 12 }} /> إضافة عداد
                    </button>
                  </form>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {mainMeter ? (
                      <div style={{ border: '1px solid var(--aseel-warn, #b8800a)', borderRadius: 4, padding: '8px 10px', background: 'rgba(184,128,10,0.06)' }}>
                        <div style={{ fontWeight: 700, color: 'var(--aseel-warn, #b8800a)', fontSize: 'var(--aseel-fs-sm)' }}>رئيسي #{mainMeter.id}{mainMeter.serial_number ? ` · ${mainMeter.serial_number}` : ''}</div>
                      </div>
                    ) : (
                      <div style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-warn, #b8800a)' }}>لم يُسجّل عداد رئيسي بعد.</div>
                    )}
                    <div style={{ fontSize: 'var(--aseel-fs-sm)', fontWeight: 600, color: 'var(--aseel-ink)', marginBottom: 4 }}>فرعي ({subMeters.length})</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, maxHeight: 160, overflowY: 'auto' }}>
                      {subMeters.map(sm => (
                        <div key={sm.id} style={{ display: 'flex', justifyContent: 'space-between', borderRadius: 3, background: 'var(--aseel-surface-alt, rgba(0,0,0,0.04))', padding: '3px 8px', fontSize: 'var(--aseel-fs-sm)' }}>
                          <span>{sm.rental_unit_code || '—'}{sm.label ? ` (${sm.label})` : ''}</span>
                          <span style={{ color: 'var(--aseel-ink-soft)' }}>#{sm.id}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* قراءات */}
              <div style={sec}>
                <div style={secTitle}>
                  <ClipboardList style={{ width: 13, height: 13, color: 'var(--aseel-accent, #1857a4)' }} />
                  تسجيل قراءة ك.و.س
                </div>
                <form onSubmit={addReading} style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'flex-end', marginBottom: 10 }}>
                  <select className="aseel-input" style={{ minWidth: 160 }} value={readingForm.meter_id} onChange={e => setReadingForm(s => ({ ...s, meter_id: e.target.value }))} required>
                    <option value="">— العداد —</option>
                    {meters.map(m => (
                      <option key={m.id} value={m.id}>
                        {m.meter_kind === "main" ? "رئيسي" : `فرعي ${m.rental_unit_code || m.id}`} (#{m.id})
                      </option>
                    ))}
                  </select>
                  <input type="date" className="aseel-input" value={readingForm.reading_date} onChange={e => setReadingForm(s => ({ ...s, reading_date: e.target.value }))} />
                  <input type="number" step="0.001" className="aseel-input" style={{ width: 130 }} placeholder="قراءة العداد" value={readingForm.kwh_value} onChange={e => setReadingForm(s => ({ ...s, kwh_value: e.target.value }))} />
                  <input className="aseel-input" ref={searchInputRef} style={{ flex: 1, minWidth: 100 }} placeholder="ملاحظة (F6)" value={readingForm.notes} onChange={e => setReadingForm(s => ({ ...s, notes: e.target.value }))} />
                  <button type="submit" className="aseel-toolbtn" style={{ padding: '4px 12px', color: 'var(--aseel-accent, #1857a4)', fontWeight: 700 }}>حفظ القراءة</button>
                </form>
                <AseelDenseTable<ReadingWithDelta>
                  columns={readingCols}
                  rows={readingsWithDelta}
                  getRowKey={r => r.id}
                  loading={false}
                  emptyHint="لا توجد قراءات"
                  footer={<span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>إجمالي القراءات: <b>{readings.length}</b></span>}
                />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
