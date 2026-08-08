/** قيمة حقل تغيّرت داخل مستند أو داخل بند منه. */
export interface ActivityFieldChange {
  field: string;
  label: string;
  old: string;
  new: string;
}

/** تفصيل حركة واحدة: حقل تغيّر، أو بند أُضيف/حُذف/تغيّرت قيمه. */
export type ActivityChange =
  | ({ kind?: "field" } & ActivityFieldChange)
  | { kind: "line_added" | "line_removed"; label: string; values: { label: string; value: string }[] }
  | { kind: "line_changed"; label: string; changes: ActivityFieldChange[] };

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
  metadata: { changes?: ActivityChange[] } & Record<string, any>;
  user: number | null;
  user_name: string;
  ip_address: string | null;
  timestamp: string;
}

export interface ActivityUserOption {
  id: number;
  name: string;
}
