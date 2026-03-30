// formatters.ts

export const formatMillisecondsToWords = (ms: number) => {
  if (!ms || ms < 0) return "0 ثانية";
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const parts = [];
  if (hours > 0) parts.push(`${hours} ساعة`);
  if (minutes > 0) parts.push(`${minutes} دقيقة`);
  if (seconds > 0 || totalSeconds === 0) parts.push(`${seconds} ثانية`);
  return parts.join("، ");
};