import { resolveTenantId } from "../utils/tenantContext";
import { apiDelete, apiGetList, apiGetObject, apiPatchObject, apiPostObject } from "./restApi";

const tid = () => resolveTenantId();
const BASE = "realestate";

export type RealestateBuilding = {
  id: number;
  tenant: number;
  name: string;
  address: string;
  notes: string;
  units_count: number;
  main_meter_id: number | null;
  created_at?: string;
};

export type RentalUnitRow = {
  id: number;
  building: number;
  building_name: string;
  unit_type: "apartment" | "warehouse";
  floor_number: number;
  code: string;
  area_sqm: string | null;
  is_active: boolean;
  created_at?: string;
};

export type LeaseRow = {
  id: number;
  unit: number;
  unit_code: string;
  building_name: string;
  renter_name: string;
  renter_phone: string;
  monthly_rent: string;
  start_date: string;
  end_date: string | null;
  status: "active" | "ended";
  notes: string;
  created_at?: string;
};

export type ElectricMeterRow = {
  id: number;
  building: number;
  meter_kind: "main" | "sub";
  rental_unit: number | null;
  rental_unit_code: string;
  label: string;
  serial_number: string;
  created_at?: string;
};

export type MeterReadingRow = {
  id: number;
  meter: number;
  meter_label?: string;
  reading_date: string;
  kwh_value: string;
  notes: string;
  created_at?: string;
};

export type RealestateSummary = {
  building_id: number;
  building_name: string;
  main_meter_id: number | null;
  main_latest_kwh: number | null;
  sub_meters: { meter_id: number; unit_code: string; label: string; latest_kwh: number | null }[];
  sub_latest_kwh_sum: number | null;
  main_minus_sub_latest_hint: number | null;
  note: string;
};

export const realestateApi = {
  listBuildings: () => apiGetList<RealestateBuilding>(`${BASE}/buildings/`, { tenantId: tid() }),

  createBuilding: (body: { name: string; address?: string; notes?: string }) =>
    apiPostObject<RealestateBuilding>(`${BASE}/buildings/`, body, { tenantId: tid() }),

  patchBuilding: (id: number, body: Partial<{ name: string; address: string; notes: string }>) =>
    apiPatchObject<RealestateBuilding>(`${BASE}/buildings/${id}/`, body, { tenantId: tid() }),

  deleteBuilding: (id: number) => apiDelete(`${BASE}/buildings/${id}/`, { tenantId: tid() }),

  listUnits: (buildingId: number) =>
    apiGetList<RentalUnitRow>(`${BASE}/units/`, {
      tenantId: tid(),
      query: { building: buildingId },
    }),

  createUnit: (body: {
    building: number;
    unit_type: "apartment" | "warehouse";
    floor_number: number;
    code: string;
    area_sqm?: string | null;
    is_active?: boolean;
  }) => apiPostObject<RentalUnitRow>(`${BASE}/units/`, body, { tenantId: tid() }),

  listLeases: (buildingId: number) =>
    apiGetList<LeaseRow>(`${BASE}/leases/`, {
      tenantId: tid(),
      query: { building: buildingId },
    }),

  createLease: (body: {
    unit: number;
    renter_name: string;
    renter_phone?: string;
    monthly_rent: string;
    start_date: string;
    end_date?: string | null;
    status?: string;
    notes?: string;
  }) => apiPostObject<LeaseRow>(`${BASE}/leases/`, body, { tenantId: tid() }),

  patchLease: (id: number, body: Partial<Record<string, unknown>>) =>
    apiPatchObject<LeaseRow>(`${BASE}/leases/${id}/`, body, { tenantId: tid() }),

  listMeters: (buildingId: number) =>
    apiGetList<ElectricMeterRow>(`${BASE}/meters/`, {
      tenantId: tid(),
      query: { building: buildingId },
    }),

  createMeter: (body: {
    building: number;
    meter_kind: "main" | "sub";
    rental_unit?: number | null;
    label?: string;
    serial_number?: string;
  }) => apiPostObject<ElectricMeterRow>(`${BASE}/meters/`, body, { tenantId: tid() }),

  listReadings: (buildingId: number, meterId?: number) =>
    apiGetList<MeterReadingRow>(`${BASE}/readings/`, {
      tenantId: tid(),
      query: {
        building: buildingId,
        ...(meterId ? { meter: meterId } : {}),
      },
    }),

  createReading: (body: { meter: number; reading_date: string; kwh_value: string; notes?: string }) =>
    apiPostObject<MeterReadingRow>(`${BASE}/readings/`, body, { tenantId: tid() }),

  summary: (buildingId: number) =>
    apiGetObject<RealestateSummary>(`${BASE}/summary/?building=${buildingId}`, { tenantId: tid() }),
};
