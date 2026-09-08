/**
 * ألوانُ المتجر تُوصَل عبر متغيّرات CSS على جذر الصفحة (مواصفة #166 م٧، قسم و).
 * `StoreSettings` كانت مخزَّنةً ومكتوبةً وخاملةً تماماً في الواجهة — هذا هو
 * السلكُ الوحيد الذي يقرؤها. أنماطٌ مضمَّنةٌ هنا حصراً (استثناءٌ صريحٌ في
 * المواصفة)؛ كل استهلاكٍ لاحقٍ عبر أصناف Tailwind الحرفية `[var(--store-*)]`.
 */
import type { CSSProperties } from "react";
import type { StoreProfile } from "../../services/storeApi";

export function storeThemeStyle(profile: StoreProfile | null): CSSProperties {
  const vars: Record<string, string> = {};
  if (profile?.primary_color) vars["--store-primary"] = profile.primary_color;
  if (profile?.accent_color) vars["--store-accent"] = profile.accent_color;
  if (profile?.background_color) vars["--store-bg"] = profile.background_color;

  const style: CSSProperties = { ...(vars as CSSProperties) };

  if (profile?.background_image_url) {
    style.backgroundImage = `url(${profile.background_image_url})`;
    style.backgroundSize = profile.background_style === "cover" ? "cover" : "auto";
    style.backgroundRepeat = profile.background_style === "repeat_pattern" ? "repeat" : "no-repeat";
    style.backgroundAttachment = "fixed";
  } else if (profile?.background_color) {
    style.backgroundColor = profile.background_color;
  }

  return style;
}

/**
 * متغيّرا اللون وحدهما — بلا خلفية. لصفحاتٍ ذاتَ خلفيةٍ ثابتةٍ عمداً (الحملة
 * الإعلانية: تباينٌ داكنٌ لتحسين التحويل)، حيث يبقى تركيبُ الخلفية من
 * `storeThemeStyle` غيرَ مناسب لكنّ لون العلامة يجب أن يبقى مرئياً.
 */
export function storeColorVars(profile: StoreProfile | null): CSSProperties {
  const vars: Record<string, string> = {};
  if (profile?.primary_color) vars["--store-primary"] = profile.primary_color;
  if (profile?.accent_color) vars["--store-accent"] = profile.accent_color;
  return vars as CSSProperties;
}
