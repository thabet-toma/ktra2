import { formatDateTimeValue } from '../../utils/formatDate';

type Props = {
  updatedAt: string | null | undefined;
};

function relativeTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 120) return 'منذ لحظات';
  if (diff < 3600) return `منذ ${Math.floor(diff / 60)} دقيقة`;
  if (diff < 86400) return `منذ ${Math.floor(diff / 3600)} ساعة`;
  return `منذ ${Math.floor(diff / 86400)} يوم`;
}

function freshnessColor(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 2 * 3600 * 1000) return 'bg-green-100 text-green-700';
  if (diff < 24 * 3600 * 1000) return 'bg-yellow-100 text-yellow-700';
  return 'bg-red-100 text-red-700';
}

export default function StalenessBadge({ updatedAt }: Props) {
  if (!updatedAt) return null;

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${freshnessColor(updatedAt)}`}
      title={`آخر تحديث: ${formatDateTimeValue(updatedAt)}`}
    >
      🕒 {relativeTime(updatedAt)}
    </span>
  );
}
