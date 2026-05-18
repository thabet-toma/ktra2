/**
 * T2-02: Unified shipment label builder.
 * All shipment list components must use this function —
 * changing the display logic in one place propagates everywhere.
 */

export type ShipmentLabelInput = {
  id: number;
  shipment_number?: string | null;
  shipment_name?: string | null;
  agent_shipment_number?: string | null;
  israeli_side_name?: string | null;
};

/**
 * Returns a human-readable label for a shipment:
 * 1) shipment_name (if set) + numeric label tail
 * 2) numeric label only
 */
export function buildShipmentOptionLabel(s: ShipmentLabelInput): string {
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

/**
 * camelCase shape used by the Firestore-style `Shipment` type
 * (ShipmentList / ShipmentManagement). Adapter keeps ONE label logic.
 */
export type ShipmentLabelCamel = {
  id: number;
  shipmentNumber?: string | null;
  shipmentName?: string | null;
  agentShipmentNumber?: string | null;
  israeliSideName?: string | null;
};

export function buildShipmentOptionLabelCamel(s: ShipmentLabelCamel): string {
  return buildShipmentOptionLabel({
    id: s.id,
    shipment_number: s.shipmentNumber ?? null,
    shipment_name: s.shipmentName ?? null,
    agent_shipment_number: s.agentShipmentNumber ?? null,
    israeli_side_name: s.israeliSideName ?? null,
  });
}