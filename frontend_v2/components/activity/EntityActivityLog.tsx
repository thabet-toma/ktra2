import React, { useEffect, useState } from "react";
import { History, ChevronDown, ChevronLeft } from "lucide-react";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { DocRefCell } from "@/components/shared/LedgerTable";
import { getEntityActivity, getPartnerActivity } from "@/services/activityService";
import { clientLogger } from "@/services/logger";
import { formatNumber } from "@/utils/formatNumber";
import type { ActivityLogEntry } from "@/types/activity";
import { actionMeta, entityLabel, formatActivityTime } from "./activityMeta";
import { ActivityChanges } from "./ActivityChanges";

interface EntityActivityLogProps {
  /** sales_invoice | purchase_invoice | deal | customer_payment */
  entityType?: string;
  entityId?: number | string;
  /** بديل لنطاق المستند: كل نشاطات الجهة المرتبطة. */
  partnerId?: number | string;
  defaultOpen?: boolean;
  title?: string;
  /** أعِد الجلب عند تغيّر هذا المفتاح (مثلاً بعد ترحيل/تعديل). */
  refreshKey?: number | string;
}

/** سجل نشاط مستند واحد — يظهر داخل شاشة تحرير الفاتورة/الصفقة. */
export const EntityActivityLog: React.FC<EntityActivityLogProps> = ({
  entityType, entityId, partnerId, defaultOpen = false, title, refreshKey,
}) => {
  const [rows, setRows] = useState<ActivityLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** الصفوف المطويّة المفتوحة — الطيّ عرضٌ فقط، والخام متاح بضغطة. */
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  useEffect(() => {
    if (!partnerId && (!entityType || !entityId)) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    const request = partnerId
      ? getPartnerActivity(partnerId)
      : getEntityActivity(entityType!, entityId!);
    if (partnerId) clientLogger.info("partner.activity_open", { partnerId });
    request
      .then((data) => { if (!cancelled) setRows(data); })
      .catch(() => { if (!cancelled) setError("تعذّر تحميل سجل النشاط."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [entityType, entityId, partnerId, refreshKey]);

  return (
    <CollapsibleSection
      title={title || (partnerId ? "سجل نشاطات الجهة" : "سجل نشاط المستند")}
      icon={History}
      defaultOpen={defaultOpen}
      badge={rows.length ? String(rows.length) : undefined}
      badgeColor="gray"
      className="ktra-border-soft dark:ktra-border-soft"
    >
      {loading ? (
        <div className="text-center py-6 ktra-text-soft">جارٍ التحميل…</div>
      ) : error ? (
        <div className="text-center py-6 text-red-600">{error}</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-8 ktra-text-soft">
          <History className="w-10 h-10 mx-auto mb-3 opacity-50" />
          <p>لا توجد نشاطات مسجلة لهذا المستند بعد</p>
        </div>
      ) : (
        <ol className="relative space-y-3">
          {rows.map((r) => {
            const meta = actionMeta(r.action);
            const count = r.group_count ?? 1;
            const folded = count > 1;
            const isOpen = Boolean(expanded[r.id]);
            return (
              <li key={r.id} className="flex items-start gap-3 border-b ktra-border-soft last:border-b-0 pb-3 last:pb-0">
                <div className="mt-0.5">{meta.icon}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${meta.badge}`}>{r.action_label || meta.label}</span>
                    {folded && (
                      <span className="text-xs px-1.5 py-0.5 rounded-full ktra-bg-panel ktra-text-soft font-bold">
                        ×{formatNumber(count)}
                      </span>
                    )}
                    <span className="font-medium ktra-text-ink dark:text-white">{r.user_name}</span>
                    {partnerId && (
                      <span className="text-xs ktra-text-soft">
                        <DocRefCell
                          referenceType={r.entity_type}
                          referenceId={r.entity_id}
                          label={`${entityLabel(r.entity_type)} ${r.entity_label || (r.entity_id != null ? `#${r.entity_id}` : "")}`}
                        />
                      </span>
                    )}
                  </div>
                  {folded ? (
                    /* حدث مكرَّر مطويّ: سطر واحد بعدّاد وآخر وقت، يُفتح على الخام. */
                    <>
                      <button
                        type="button"
                        className="mt-0.5 flex items-center gap-1 text-sm ktra-text-soft hover:underline"
                        aria-expanded={isOpen}
                        onClick={() => setExpanded((prev) => ({ ...prev, [r.id]: !prev[r.id] }))}
                      >
                        {isOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
                        <span>
                          {r.description || meta.label} ×{formatNumber(count)} — آخرها {formatActivityTime(r.timestamp)}
                        </span>
                      </button>
                      {isOpen && (
                        <ul className="mt-1 space-y-0.5 border-s ps-2 ktra-border-soft">
                          {(r.group_rows || []).map((g) => (
                            <li key={g.id} className="text-xs ktra-text-soft">
                              {formatActivityTime(g.timestamp)}
                            </li>
                          ))}
                        </ul>
                      )}
                    </>
                  ) : r.metadata?.changes?.length ? (
                    <div className="mt-1"><ActivityChanges changes={r.metadata.changes} /></div>
                  ) : (
                    r.description && (
                      <p className="text-sm ktra-text-soft mt-0.5">{r.description}</p>
                    )
                  )}
                </div>
                <div className="text-xs ktra-text-soft whitespace-nowrap">
                  {formatActivityTime(r.timestamp)}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </CollapsibleSection>
  );
};
