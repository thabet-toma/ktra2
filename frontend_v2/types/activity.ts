/** سجل النشاط الموحّد — صف واحد من /api/activity/ */
export interface ActivityLogEntry {
  id: number;
  action:
    | "create" | "update" | "delete" | "post" | "unpost"
    | "duplicate" | "payment" | "view" | "login" | "logout";
  action_label: string;
  is_view: boolean;
  entity_type: string;
  entity_id: number | null;
  entity_label: string;
  description: string;
  metadata: Record<string, any>;
  user: number | null;
  user_name: string;
  ip_address: string | null;
  timestamp: string;
}

export interface ActivityUserOption {
  id: number;
  name: string;
}
