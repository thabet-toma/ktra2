import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  realestateApi,
  type RealestateBuilding,
  type RentalUnitRow,
  type LeaseRow,
  type ElectricMeterRow,
  type MeterReadingRow,
  type RealestateSummary,
} from "../../services/realestateApi";
import {
  Building2,
  Zap,
  Home,
  Warehouse,
  Plus,
  RefreshCw,
  Loader2,
  ClipboardList,
  Users,
  Gauge,
} from "lucide-react";

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

function readingDeltas(rows: MeterReadingRow[]): Map<number, { prev: number; delta: number | null }> {
  const byMeter = new Map<number, MeterReadingRow[]>();
  for (const r of rows) {
    const list = byMeter.get(r.meter) ?? [];
    list.push(r);
    byMeter.set(r.meter, list);
  }
  const out = new Map<number, { prev: number; delta: number | null }>();
  for (const [mid, list] of byMeter) {
    const sorted = [...list].sort(
      (a, b) => new Date(b.reading_date).getTime() - new Date(a.reading_date).getTime() || b.id - a.id
    );
    if (sorted.length === 0) continue;
    const latest = parseFloat(sorted[0].kwh_value);
    const prev =
      sorted.length > 1 ? parseFloat(sorted[1].kwh_value) : NaN;
    out.set(mid, {
      prev: Number.isFinite(prev) ? prev : latest,
      delta:
        sorted.length > 1 && Number.isFinite(prev) && Number.isFinite(latest)
          ? Math.max(0, latest - prev)
          : null,
    });
  }
  return out;
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

  const [newBuilding, setNewBuilding] = useState({ name: "", address: "" });
  const [unitForm, setUnitForm] = useState({
    code: "",
    floor_number: 0,
    unit_type: "apartment" as "apartment" | "warehouse",
  });
  const [leaseForm, setLeaseForm] = useState({
    unit_id: "" as string | number,
    renter_name: "",
    renter_phone: "",
    monthly_rent: "",
    start_date: "",
  });
  const [meterForm, setMeterForm] = useState({
    kind: "sub" as "main" | "sub",
    unit_id: "" as string | number,
    label: "",
    serial_number: "",
  });
  const [readingForm, setReadingForm] = useState({
    meter_id: "" as string | number,
    reading_date: new Date().toISOString().slice(0, 10),
    kwh_value: "",
    notes: "",
  });

  const loadBuildings = useCallback(async () => {
    setErr(null);
    try {
      const list = await realestateApi.listBuildings();
      setBuildings(list);
      setSelectedId((prev) => (prev == null && list.length > 0 ? list[0].id : prev));
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ في تحميل العمارات");
    }
  }, []);

  const loadBuildingDetail = useCallback(async (bid: number) => {
    setLoading(true);
    setErr(null);
    try {
      const [u, l, m, r, s] = await Promise.all([
        realestateApi.listUnits(bid),
        realestateApi.listLeases(bid),
        realestateApi.listMeters(bid),
        realestateApi.listReadings(bid),
        realestateApi.summary(bid).catch(() => null),
      ]);
      setUnits(u);
      setLeases(l);
      setMeters(m);
      setReadings(r);
      setSummary(s);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ في تحميل التفاصيل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBuildings();
  }, []);

  useEffect(() => {
    if (selectedId != null) loadBuildingDetail(selectedId);
  }, [selectedId, loadBuildingDetail]);

  const selected = useMemo(
    () => buildings.find((b) => b.id === selectedId) ?? null,
    [buildings, selectedId]
  );

  const deltas = useMemo(() => readingDeltas(readings), [readings]);

  const mainMeter = meters.find((m) => m.meter_kind === "main");
  const subMeters = meters.filter((m) => m.meter_kind === "sub");

  const addBuilding = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBuilding.name.trim()) return;
    setErr(null);
    try {
      const b = await realestateApi.createBuilding({
        name: newBuilding.name.trim(),
        address: newBuilding.address.trim(),
      });
      setNewBuilding({ name: "", address: "" });
      setBuildings((prev) => [...prev, b]);
      setSelectedId(b.id);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل إنشاء العمارة");
    }
  };

  const addUnit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedId || !unitForm.code.trim()) return;
    setErr(null);
    try {
      await realestateApi.createUnit({
        building: selectedId,
        code: unitForm.code.trim(),
        floor_number: Number(unitForm.floor_number) || 0,
        unit_type: unitForm.unit_type,
      });
      setUnitForm({ code: "", floor_number: 0, unit_type: "apartment" });
      await loadBuildingDetail(selectedId);
      await loadBuildings();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل إضافة الوحدة");
    }
  };

  const addLease = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedId || !leaseForm.unit_id || !leaseForm.renter_name.trim() || !leaseForm.monthly_rent)
      return;
    setErr(null);
    try {
      await realestateApi.createLease({
        unit: Number(leaseForm.unit_id),
        renter_name: leaseForm.renter_name.trim(),
        renter_phone: leaseForm.renter_phone.trim(),
        monthly_rent: leaseForm.monthly_rent,
        start_date: leaseForm.start_date || new Date().toISOString().slice(0, 10),
      });
      setLeaseForm({
        unit_id: "",
        renter_name: "",
        renter_phone: "",
        monthly_rent: "",
        start_date: "",
      });
      await loadBuildingDetail(selectedId);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل تسجيل الإيجار");
    }
  };

  const addMeter = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedId) return;
    if (meterForm.kind === "sub" && !meterForm.unit_id) {
      setErr("اختر الوحدة للعداد الفرعي.");
      return;
    }
    setErr(null);
    try {
      await realestateApi.createMeter({
        building: selectedId,
        meter_kind: meterForm.kind,
        rental_unit: meterForm.kind === "sub" ? Number(meterForm.unit_id) : null,
        label: meterForm.label.trim(),
        serial_number: meterForm.serial_number.trim(),
      });
      setMeterForm({ kind: "sub", unit_id: "", label: "", serial_number: "" });
      await loadBuildingDetail(selectedId);
      await loadBuildings();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل إضافة العداد");
    }
  };

  const addReading = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!readingForm.meter_id || !readingForm.kwh_value) return;
    setErr(null);
    try {
      await realestateApi.createReading({
        meter: Number(readingForm.meter_id),
        reading_date: readingForm.reading_date,
        kwh_value: readingForm.kwh_value,
        notes: readingForm.notes.trim(),
      });
      setReadingForm((f) => ({ ...f, kwh_value: "", notes: "" }));
      if (selectedId) await loadBuildingDetail(selectedId);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل حفظ القراءة");
    }
  };

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Building2 className="h-8 w-8 text-amber-600" />
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">تأجير العقارات</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              عمارات، شقق، مخازن، عقود إيجار، وعداد كهرباء رئيسي مع عدادات فرعية وقراءات
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            loadBuildings();
            if (selectedId) loadBuildingDetail(selectedId);
          }}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-600 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
        >
          <RefreshCw className="h-4 w-4" />
          تحديث
        </button>
      </div>

      {err && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 px-4 py-3 text-sm">
          {err}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* عمارات */}
        <aside className="lg:col-span-3 space-y-4">
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 shadow-sm">
            <h2 className="font-semibold text-gray-800 dark:text-gray-100 mb-3 flex items-center gap-2">
              <Building2 className="h-5 w-5 text-amber-600" />
              العمارات
            </h2>
            <form onSubmit={addBuilding} className="space-y-2 mb-4">
              <input
                className="w-full rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
                placeholder="اسم العمارة"
                value={newBuilding.name}
                onChange={(e) => setNewBuilding((s) => ({ ...s, name: e.target.value }))}
              />
              <input
                className="w-full rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
                placeholder="العنوان (اختياري)"
                value={newBuilding.address}
                onChange={(e) => setNewBuilding((s) => ({ ...s, address: e.target.value }))}
              />
              <button
                type="submit"
                className="w-full flex items-center justify-center gap-1 rounded-lg bg-amber-600 text-white py-2 text-sm font-medium hover:bg-amber-700"
              >
                <Plus className="h-4 w-4" />
                إضافة عمارة
              </button>
            </form>
            <ul className="space-y-1 max-h-[420px] overflow-y-auto">
              {buildings.map((b) => (
                <li key={b.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(b.id)}
                    className={`w-full text-right rounded-lg px-3 py-2 text-sm transition ${
                      b.id === selectedId
                        ? "bg-amber-100 dark:bg-amber-900/40 text-amber-900 dark:text-amber-100 font-medium"
                        : "hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300"
                    }`}
                  >
                    <span className="block truncate">{b.name}</span>
                    <span className="text-xs text-gray-500">
                      {b.units_count} وحدة
                      {b.main_meter_id ? " · عداد رئيسي" : ""}
                    </span>
                  </button>
                </li>
              ))}
              {buildings.length === 0 && (
                <p className="text-sm text-gray-500 text-center py-4">لا توجد عمارات بعد</p>
              )}
            </ul>
          </div>
        </aside>

        <main className="lg:col-span-9 space-y-6">
          {!selected ? (
            <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-600 p-12 text-center text-gray-500">
              اختر عمارة أو أنشئ واحدة للبدء
            </div>
          ) : loading ? (
            <div className="flex justify-center py-20">
              <Loader2 className="h-10 w-10 animate-spin text-amber-600" />
            </div>
          ) : (
            <>
              <header className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gradient-to-l from-amber-50 to-white dark:from-amber-950/30 dark:to-gray-900 p-5 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-bold text-gray-900 dark:text-white">{selected.name}</h2>
                    {selected.address ? (
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{selected.address}</p>
                    ) : null}
                  </div>
                  {summary && (
                    <div className="text-left text-xs sm:text-sm space-y-1 bg-white/80 dark:bg-gray-900/80 rounded-lg px-3 py-2 border border-amber-100 dark:border-amber-900/50">
                      <div className="flex items-center gap-1 text-amber-800 dark:text-amber-200">
                        <Gauge className="h-4 w-4" />
                        <span className="font-medium">لمحة عدادات (آخر قراءة مسجّلة)</span>
                      </div>
                      <p>
                        الرئيسي:{" "}
                        {summary.main_latest_kwh != null ? fmtKwh(summary.main_latest_kwh) : "—"} ك.و.س
                      </p>
                      <p>مجموع الفرعي (آخر قراءة لكل عداد): {fmtKwh(summary.sub_latest_kwh_sum ?? 0)}</p>
                      {summary.main_minus_sub_latest_hint != null && (
                        <p className="text-gray-600 dark:text-gray-400">
                          فرق تقريبي (رئيسي − مجموع الفرعي): {fmtKwh(summary.main_minus_sub_latest_hint)}
                        </p>
                      )}
                      <p className="text-gray-500 max-w-md">{summary.note}</p>
                    </div>
                  )}
                </div>
              </header>

              <div className="grid md:grid-cols-2 gap-6">
                {/* وحدات */}
                <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 shadow-sm">
                  <h3 className="font-semibold mb-3 flex items-center gap-2 text-gray-800 dark:text-gray-100">
                    <Home className="h-5 w-5 text-sky-600" />
                    الشقق والمخازن
                  </h3>
                  <form onSubmit={addUnit} className="grid grid-cols-2 gap-2 mb-4 text-sm">
                    <input
                      className="col-span-2 rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800"
                      placeholder="رمز الوحدة (مثال: 2ب، مخزن-أ)"
                      value={unitForm.code}
                      onChange={(e) => setUnitForm((s) => ({ ...s, code: e.target.value }))}
                    />
                    <input
                      type="number"
                      className="rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800"
                      placeholder="الطابق"
                      value={unitForm.floor_number}
                      onChange={(e) => setUnitForm((s) => ({ ...s, floor_number: Number(e.target.value) }))}
                    />
                    <select
                      className="rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800"
                      value={unitForm.unit_type}
                      onChange={(e) =>
                        setUnitForm((s) => ({
                          ...s,
                          unit_type: e.target.value as "apartment" | "warehouse",
                        }))
                      }
                    >
                      <option value="apartment">شقة</option>
                      <option value="warehouse">مخزن</option>
                    </select>
                    <button
                      type="submit"
                      className="col-span-2 rounded-lg bg-sky-600 text-white py-2 text-sm hover:bg-sky-700"
                    >
                      إضافة وحدة
                    </button>
                  </form>
                  <ul className="divide-y divide-gray-100 dark:divide-gray-800 max-h-56 overflow-y-auto text-sm">
                    {units.map((u) => (
                      <li key={u.id} className="py-2 flex items-center justify-between gap-2">
                        <span>
                          {u.unit_type === "warehouse" ? (
                            <Warehouse className="inline h-4 w-4 text-amber-600 ml-1" />
                          ) : (
                            <Home className="inline h-4 w-4 text-sky-600 ml-1" />
                          )}
                          {u.code}
                          <span className="text-gray-500 mr-2">طابق {u.floor_number}</span>
                        </span>
                        {!u.is_active && (
                          <span className="text-xs text-gray-400">غير نشط</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>

                {/* إيجار */}
                <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 shadow-sm">
                  <h3 className="font-semibold mb-3 flex items-center gap-2 text-gray-800 dark:text-gray-100">
                    <Users className="h-5 w-5 text-emerald-600" />
                    عقود الإيجار
                  </h3>
                  <form onSubmit={addLease} className="space-y-2 mb-4 text-sm">
                    <select
                      className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800"
                      value={leaseForm.unit_id}
                      onChange={(e) => setLeaseForm((s) => ({ ...s, unit_id: e.target.value }))}
                      required
                    >
                      <option value="">— الوحدة —</option>
                      {units.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.code} ({u.unit_type === "warehouse" ? "مخزن" : "شقة"})
                        </option>
                      ))}
                    </select>
                    <input
                      className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800"
                      placeholder="اسم المستأجر"
                      value={leaseForm.renter_name}
                      onChange={(e) => setLeaseForm((s) => ({ ...s, renter_name: e.target.value }))}
                    />
                    <input
                      className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800"
                      placeholder="جوال"
                      value={leaseForm.renter_phone}
                      onChange={(e) => setLeaseForm((s) => ({ ...s, renter_phone: e.target.value }))}
                    />
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        type="number"
                        step="0.01"
                        className="rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800"
                        placeholder="الإيجار الشهري"
                        value={leaseForm.monthly_rent}
                        onChange={(e) => setLeaseForm((s) => ({ ...s, monthly_rent: e.target.value }))}
                      />
                      <input
                        type="date"
                        className="rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800"
                        value={leaseForm.start_date}
                        onChange={(e) => setLeaseForm((s) => ({ ...s, start_date: e.target.value }))}
                      />
                    </div>
                    <button
                      type="submit"
                      className="w-full rounded-lg bg-emerald-600 text-white py-2 hover:bg-emerald-700"
                    >
                      تسجيل عقد
                    </button>
                  </form>
                  <ul className="max-h-48 overflow-y-auto text-sm space-y-1">
                    {leases.map((l) => (
                      <li
                        key={l.id}
                        className="rounded-lg bg-gray-50 dark:bg-gray-800/80 px-2 py-1.5 flex justify-between gap-2"
                      >
                        <span className="truncate">
                          {l.renter_name}
                          <span className="text-gray-500 mr-2">({l.unit_code})</span>
                        </span>
                        <span className="shrink-0 font-medium">{fmtMoney(l.monthly_rent)}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              </div>

              {/* عدادات */}
              <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 shadow-sm">
                <h3 className="font-semibold mb-3 flex items-center gap-2 text-gray-800 dark:text-gray-100">
                  <Zap className="h-5 w-5 text-yellow-500" />
                  عدادات الكهرباء
                </h3>
                <div className="grid md:grid-cols-2 gap-6">
                  <div>
                    <p className="text-xs text-gray-500 mb-2">
                      عداد واحد رئيسي للعمارة، وعداد فرعي لكل شقة أو مخزن يحتاج فوترة منفصلة.
                    </p>
                    <form onSubmit={addMeter} className="space-y-2 text-sm">
                      <select
                        className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800"
                        value={meterForm.kind}
                        onChange={(e) =>
                          setMeterForm((s) => ({
                            ...s,
                            kind: e.target.value as "main" | "sub",
                          }))
                        }
                      >
                        <option value="main">عداد رئيسي (عمارة)</option>
                        <option value="sub">عداد فرعي (وحدة)</option>
                      </select>
                      {meterForm.kind === "sub" && (
                        <select
                          className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800"
                          value={meterForm.unit_id}
                          onChange={(e) => setMeterForm((s) => ({ ...s, unit_id: e.target.value }))}
                        >
                          <option value="">— اختر الوحدة —</option>
                          {units.map((u) => (
                            <option key={u.id} value={u.id}>
                              {u.code}
                            </option>
                          ))}
                        </select>
                      )}
                      <input
                        className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800"
                        placeholder="ملاحظة على العداد (اختياري)"
                        value={meterForm.label}
                        onChange={(e) => setMeterForm((s) => ({ ...s, label: e.target.value }))}
                      />
                      <input
                        className="w-full rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-1.5 bg-white dark:bg-gray-800"
                        placeholder="رقم التسلسل (اختياري)"
                        value={meterForm.serial_number}
                        onChange={(e) => setMeterForm((s) => ({ ...s, serial_number: e.target.value }))}
                      />
                      <button
                        type="submit"
                        className="w-full rounded-lg bg-yellow-500 text-gray-900 py-2 font-medium hover:bg-yellow-400"
                      >
                        إضافة عداد
                      </button>
                    </form>
                  </div>
                  <div className="space-y-3">
                    {mainMeter ? (
                      <div className="rounded-lg border border-yellow-200 dark:border-yellow-800 bg-yellow-50/80 dark:bg-yellow-950/20 p-3">
                        <div className="font-medium text-yellow-900 dark:text-yellow-100">رئيسي</div>
                        <div className="text-xs text-gray-600 dark:text-gray-400">
                          #{mainMeter.id}
                          {mainMeter.serial_number ? ` · ${mainMeter.serial_number}` : ""}
                        </div>
                        {deltas.get(mainMeter.id)?.delta != null && (
                          <div className="text-sm mt-1">
                            آخر استهلاك (فترة): {fmtKwh(deltas.get(mainMeter.id)!.delta!)} ك.و.س
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-amber-700 dark:text-amber-300">لم يُسجّل عداد رئيسي بعد.</p>
                    )}
                    <div>
                      <div className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        فرعي ({subMeters.length})
                      </div>
                      <ul className="text-sm space-y-1 max-h-40 overflow-y-auto">
                        {subMeters.map((sm) => (
                          <li
                            key={sm.id}
                            className="flex justify-between rounded bg-gray-50 dark:bg-gray-800 px-2 py-1"
                          >
                            <span>
                              {sm.rental_unit_code || "—"}
                              {sm.label ? ` (${sm.label})` : ""}
                            </span>
                            <span className="text-gray-500">#{sm.id}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              </section>

              {/* قراءات */}
              <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 shadow-sm">
                <h3 className="font-semibold mb-3 flex items-center gap-2 text-gray-800 dark:text-gray-100">
                  <ClipboardList className="h-5 w-5 text-violet-600" />
                  تسجيل قراءة ك.و.س
                </h3>
                <form onSubmit={addReading} className="flex flex-wrap gap-2 items-end mb-4 text-sm">
                  <select
                    className="rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800 min-w-[180px]"
                    value={readingForm.meter_id}
                    onChange={(e) => setReadingForm((s) => ({ ...s, meter_id: e.target.value }))}
                    required
                  >
                    <option value="">— العداد —</option>
                    {meters.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.meter_kind === "main" ? "رئيسي" : `فرعي ${m.rental_unit_code || m.id}`} (#{m.id})
                      </option>
                    ))}
                  </select>
                  <input
                    type="date"
                    className="rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800"
                    value={readingForm.reading_date}
                    onChange={(e) => setReadingForm((s) => ({ ...s, reading_date: e.target.value }))}
                  />
                  <input
                    type="number"
                    step="0.001"
                    className="rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800 w-36"
                    placeholder="قراءة العداد"
                    value={readingForm.kwh_value}
                    onChange={(e) => setReadingForm((s) => ({ ...s, kwh_value: e.target.value }))}
                  />
                  <input
                    className="rounded-lg border border-gray-200 dark:border-gray-600 px-2 py-2 bg-white dark:bg-gray-800 flex-1 min-w-[120px]"
                    placeholder="ملاحظة"
                    value={readingForm.notes}
                    onChange={(e) => setReadingForm((s) => ({ ...s, notes: e.target.value }))}
                  />
                  <button
                    type="submit"
                    className="rounded-lg bg-violet-600 text-white px-4 py-2 hover:bg-violet-700"
                  >
                    حفظ القراءة
                  </button>
                </form>
                <div className="overflow-x-auto max-h-72 overflow-y-auto">
                  <table className="w-full text-sm text-right">
                    <thead className="sticky top-0 bg-gray-100 dark:bg-gray-800">
                      <tr>
                        <th className="p-2">التاريخ</th>
                        <th className="p-2">العداد</th>
                        <th className="p-2">القراءة</th>
                        <th className="p-2">استهلاك الفترة</th>
                        <th className="p-2">ملاحظة</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...readings]
                        .sort(
                          (a, b) =>
                            new Date(b.reading_date).getTime() -
                              new Date(a.reading_date).getTime() || b.id - a.id
                        )
                        .map((r, idx, arr) => {
                          const sameMeterOlder = arr
                            .slice(idx + 1)
                            .find((x) => x.meter === r.meter);
                          const cur = parseFloat(r.kwh_value);
                          const prev = sameMeterOlder
                            ? parseFloat(sameMeterOlder.kwh_value)
                            : NaN;
                          const delta =
                            Number.isFinite(cur) && Number.isFinite(prev)
                              ? Math.max(0, cur - prev)
                              : null;
                          return (
                            <tr
                              key={r.id}
                              className="border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50/50 dark:hover:bg-gray-800/50"
                            >
                              <td className="p-2 whitespace-nowrap">{r.reading_date}</td>
                              <td className="p-2">{r.meter_label ?? `#${r.meter}`}</td>
                              <td className="p-2 font-mono">{fmtKwh(r.kwh_value)}</td>
                              <td className="p-2 text-emerald-700 dark:text-emerald-300">
                                {delta != null ? fmtKwh(delta) : "—"}
                              </td>
                              <td className="p-2 text-gray-500 max-w-[160px] truncate">{r.notes}</td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
};
