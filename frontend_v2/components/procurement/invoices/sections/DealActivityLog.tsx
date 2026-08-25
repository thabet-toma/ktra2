import React from 'react';
import { DealActivity } from '@/types';
import { History, CheckCircle, XCircle, FileText, DollarSign, Clock } from 'lucide-react';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import { formatDateTimeValue } from '@/utils/formatDate';

interface DealActivityLogProps {
  activities: DealActivity[];
}

export const DealActivityLog: React.FC<DealActivityLogProps> = ({ activities }) => {
  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'status_change':
        return <CheckCircle className="w-4 h-4 ktra-text-soft" />;
      case 'payment':
        return <DollarSign className="w-4 h-4 text-green-500" />;
      case 'note':
        return <FileText className="w-4 h-4 ktra-text-soft" />;
      case 'attachment':
        return <FileText className="w-4 h-4 text-[var(--color-primary)]" />;
      default:
        return <Clock className="w-4 h-4 ktra-text-soft" />;
    }
  };

  const getActivityColor = (type: string) => {
    switch (type) {
      case 'status_change':
        return 'ktra-border-accent dark:ktra-border-soft ktra-bg-accent-bg dark:ktra-bg-panel/10';
      case 'payment':
        return 'ktra-border-soft dark:border-green-800 bg-green-50 dark:bg-green-900/10';
      case 'note':
        return 'ktra-border-soft dark:ktra-border-soft ktra-bg-panel dark:ktra-bg-panel/10';
      case 'attachment':
        return 'border-[var(--color-border)] dark:border-[var(--color-border)] bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/10';
      default:
        return 'ktra-border-soft dark:ktra-border-soft ktra-bg-panel dark:ktra-bg-panel/10';
    }
  };

  return (
    <CollapsibleSection
      title="سجل نشاطات الصفقة"
      icon={History}
      defaultOpen={false}
      className="ktra-border-soft dark:ktra-border-soft"
    >
      <div className="space-y-3">
        {activities.length === 0 ? (
          <div className="text-center py-8 ktra-text-soft dark:ktra-text-soft">
            <History className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>لا توجد نشاطات مسجلة</p>
          </div>
        ) : (
          activities.map((activity) => (
            <div 
              key={activity.id} 
              className={`p-4 border rounded-lg ${getActivityColor(activity.type)}`}
            >
              <div className="flex justify-between items-start">
                <div className="flex items-start gap-3 flex-1">
                  <div className="mt-1">
                    {getActivityIcon(activity.type)}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium ktra-text-ink dark:text-white">
                      {activity.action}
                    </p>
                    {activity.details && (
                      <p className="text-sm ktra-text-soft dark:ktra-text-soft mt-1">
                        {activity.details}
                      </p>
                    )}
                    <div className="flex items-center gap-4 mt-2 text-xs ktra-text-soft">
                      <span>بواسطة: {activity.userName}</span>
                      <span>الدور: {activity.userRole}</span>
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm ktra-text-soft">
                    {formatDateTimeValue(activity.timestamp)}
                  </p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </CollapsibleSection>
  );
};