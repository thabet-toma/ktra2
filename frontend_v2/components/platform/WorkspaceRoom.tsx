import React from "react";

/**
 * غرفةُ «مساحة العمل» — من يعمل الآن، بلمحةٍ واحدة (#211 م٣).
 *
 * الغرضُ من الغرفة **قراءةٌ فوريّة** لا زينة: من متّصلٌ الآن، ومن في اجتماع،
 * ومن غائب. ولذلك ثلاثةُ أضواءٍ لا أكثر، ونصٌّ صريحٌ تحت كلّ ضوء — اللونُ وحدَه
 * لا يكفي لمن لا يميّز الأحمرَ من الأخضر.
 *
 * **والمقعدُ الفارغُ يبقى فارغاً**: نموذجُ المالك البصريُّ يُجلِس الغائبَ على
 * كرسيّه بضوءٍ أحمر، وذلك يقرأ حضوراً لا وجودَ له — فالكرسيُّ هنا يبهت ويُرمَّد.
 *
 * الهندسةُ (مواضعُ المقاعد وعمقُها) أصنافٌ مولَّدةٌ في `styles/index.css`
 * (`.pf-seat-0..9`) لا `style` سطريّ، والطاولةُ تسع عشرة — ومن زاد يُعرَض في شريطٍ
 * تحتها بدل أن يُخفى: موظّفٌ لا يظهر أسوأُ من موظّفٍ خارج الطاولة.
 */

export type RoomPresence = "online" | "meeting" | "offline";

export interface RoomOccupant {
  id: number;
  name: string;
  role: string;
  presence: RoomPresence;
  /** نصُّ آخر ظهورٍ جاهزاً للعرض — يُحسَب عند المُستدعي بالأداة القائمة. */
  lastActiveLabel: string;
}

/** عشرةُ مقاعد: عند اثني عشر تتراكب البطاقاتُ على جانبَي الحلقة في اللوحات
 *  الضيّقة فيختفي اسمٌ — وقد قِيس التراكبُ فعلاً (٤٦×٥٦ بكسل بين المقعدين
 *  ٣ و٤ عند عرض ٥٤١ بكسل)، والاسمُ المخفيُّ أسوأُ ما يفعله لوحُ حضور. */
const SEAT_COUNT = 10;

const PRESENCE_LABEL: Record<RoomPresence, string> = {
  online: "متّصل",
  meeting: "في اجتماع",
  offline: "غير متّصل",
};

/** الضوءُ يأخذ لونَه من رموز سطح المنصّة فلا يفترق عن بقيّة الشاشات. */
const PRESENCE_DOT: Record<RoomPresence, string> = {
  online: "bg-emerald-500",
  meeting: "bg-amber-500",
  offline: "bg-rose-500",
};

const PRESENCE_TEXT: Record<RoomPresence, string> = {
  online: "text-emerald-700",
  meeting: "text-amber-700",
  offline: "text-rose-700",
};

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "؟";
  if (parts.length === 1) return parts[0].slice(0, 2);
  return `${parts[0][0]}${parts[1][0]}`;
}

interface OccupantBadgeProps {
  occupant: RoomOccupant;
  onSelect?: (employeeId: number) => void;
}

const OccupantBadge: React.FC<OccupantBadgeProps> = ({ occupant, onSelect }) => (
  <button
    type="button"
    onClick={() => onSelect?.(occupant.id)}
    className="flex flex-col items-center gap-1 w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 rounded-xl"
    title={`${occupant.name} — ${PRESENCE_LABEL[occupant.presence]} · ${occupant.lastActiveLabel}`}
  >
    <span className="relative">
      <span className="flex items-center justify-center w-11 h-11 rounded-full bg-white text-sky-800 font-bold text-sm shadow-md ring-2 ring-white">
        {initialsOf(occupant.name)}
      </span>
      <span
        className={`absolute -bottom-0.5 -left-0.5 w-3.5 h-3.5 rounded-full ring-2 ring-white ${PRESENCE_DOT[occupant.presence]}`}
        aria-hidden="true"
      />
    </span>
    <span className="pf-seat-badge">
      <span className="block text-[11px] font-bold text-slate-900 truncate">{occupant.name}</span>
      <span className="block text-[10px] text-slate-500 truncate">{occupant.role || "—"}</span>
      <span className={`block text-[10px] font-bold ${PRESENCE_TEXT[occupant.presence]}`}>
        {PRESENCE_LABEL[occupant.presence]}
      </span>
    </span>
  </button>
);

export interface WorkspaceRoomProps {
  occupants: RoomOccupant[];
  /** عنوانُ ما يُعرَض على شاشة الطاولة — اجتماعُ اليوم إن وُجد. */
  screenTitle?: string;
  screenSubtitle?: string;
  onSelectEmployee?: (employeeId: number) => void;
}

export const WorkspaceRoom: React.FC<WorkspaceRoomProps> = ({
  occupants,
  screenTitle,
  screenSubtitle,
  onSelectEmployee,
}) => {
  const seated = occupants.slice(0, SEAT_COUNT);
  const overflow = occupants.slice(SEAT_COUNT);

  const onlineCount = occupants.filter((o) => o.presence !== "offline").length;

  return (
    <section dir="rtl" aria-label="غرفة مساحة العمل">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className="text-base font-bold text-slate-900">مساحة العمل</h3>
        {/* العدُّ نصٌّ صريح: «١٨/٢٥» في النموذج البصريّ. */}
        <span className="text-xs font-bold text-slate-600">
          المتّصلون الآن {onlineCount}/{occupants.length}
        </span>
      </div>

      <div className="pf-room-shell">
        <div className="pf-room">
          <div className="pf-room-floor" aria-hidden="true" />
          <div className="pf-room-halo-2" aria-hidden="true" />
          <div className="pf-room-halo" aria-hidden="true" />
          <div className="pf-room-table" aria-hidden="true" />

          {(screenTitle || screenSubtitle) && (
            <div className="pf-room-screen text-center">
              {screenTitle && (
                <span className="block text-[11px] font-bold text-sky-900 truncate">{screenTitle}</span>
              )}
              {screenSubtitle && (
                <span className="block text-[10px] text-sky-700 truncate">{screenSubtitle}</span>
              )}
            </div>
          )}

          {Array.from({ length: SEAT_COUNT }).map((_, index) => {
            const occupant = seated[index];
            return (
              <div
                key={index}
                className={`pf-seat pf-seat-${index}${occupant ? "" : " pf-seat-empty"}`}
              >
                {occupant ? (
                  <OccupantBadge occupant={occupant} onSelect={onSelectEmployee} />
                ) : (
                  <>
                    <span
                      className="w-11 h-11 rounded-full bg-white/70 ring-2 ring-white"
                      aria-hidden="true"
                    />
                    <span className="pf-seat-badge">
                      <span className="block text-[10px] text-slate-500">مقعد شاغر</span>
                    </span>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {overflow.length > 0 && (
        <div className="mt-3">
          <p className="text-xs text-slate-500 mb-2">
            خارج الطاولة ({overflow.length}) — الطاولة تسع {SEAT_COUNT}
          </p>
          <ul className="flex flex-wrap gap-2">
            {overflow.map((occupant) => (
              <li key={occupant.id}>
                <button
                  type="button"
                  onClick={() => onSelectEmployee?.(occupant.id)}
                  className="flex items-center gap-2 bg-white rounded-full border border-slate-200 px-3 py-1.5 shadow-sm hover:shadow transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
                  title={`${occupant.name} — ${PRESENCE_LABEL[occupant.presence]}`}
                >
                  <span className={`w-2.5 h-2.5 rounded-full ${PRESENCE_DOT[occupant.presence]}`} aria-hidden="true" />
                  <span className="text-xs font-bold text-slate-800">{occupant.name}</span>
                  <span className="text-[10px] text-slate-500">{occupant.role || "—"}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
};
