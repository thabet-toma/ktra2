import React from "react";
import { CcSurfaceTone, ccSurfaceClasses } from "../../../utils/ccTone";

export interface CcCardProps extends React.HTMLAttributes<HTMLDivElement> {
  tone?: CcSurfaceTone;
  glow?: boolean;
  className?: string;
  children?: React.ReactNode;
}

export const CcCard: React.FC<CcCardProps> = ({
  tone = "default",
  glow = false,
  className = "",
  children,
  ...rest
}: CcCardProps) => {
  // النوعُ مكتوبٌ على التفكيك لا على `React.FC` وحدَه: لا `@types/react` في
  // المستودع، فـ`React.FC<CcCardProps>` لا يقيّد الخصائصَ، و`tone` كان يُستنتج
  // `string` من قيمته الافتراضيّة فيرفضه `ccSurfaceClasses`.
  const toneClasses = ccSurfaceClasses(tone ?? "default");
  const glowClasses = glow ? "shadow-cc-glow border-sky-500/40" : "shadow-cc-card";

  return (
    <div
      className={`relative overflow-hidden rounded-[var(--radius-cc,1rem)] border ${toneClasses} ${glowClasses} transition-all duration-200 ${className}`}
      {...rest}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
      {children}
    </div>
  );
};

export default CcCard;
