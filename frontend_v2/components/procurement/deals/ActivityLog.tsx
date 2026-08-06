import React from 'react';
import { 
  History, User, Clock, FileText, DollarSign, 
  Package, CheckCircle, AlertCircle, Edit, Trash2 
} from 'lucide-react';
import { DealActivity } from '../../../types';
import { formatDateTimeValue } from '../../../utils/formatDate';

interface ActivityLogProps {
  activities: DealActivity[];
}

export const ActivityLog: React.FC<ActivityLogProps> = ({ activities }) => {
  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'status_change': return <History className="w-4 h-4" />;
      case 'payment': return <DollarSign className="w-4 h-4" />;
      case 'item_update': return <Package className="w-4 h-4" />;
      case 'note': return <FileText className="w-4 h-4" />;
      default: return <AlertCircle className="w-4 h-4" />;
    }
  };

  const getActivityColor = (type: string) => {
    switch (type) {
      case 'status_change': return 'aseel-bg-accent-bg aseel-text-ink dark:aseel-bg-panel/30 dark:aseel-text-soft';
      case 'payment': return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
      case 'item_update': return 'bg-[var(--color-surface-2)] text-[var(--color-primary)] dark:bg-[var(--color-surface-2)]/30 dark:text-[var(--color-primary)]';
      case 'note': return 'aseel-bg-panel aseel-text-ink dark:aseel-bg-panel/30 dark:aseel-text-soft';
      default: return 'aseel-bg-panel aseel-text-ink dark:aseel-bg-panel/30 dark:aseel-text-soft';
    }
  };

  return (
    <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow border aseel-border-soft dark:aseel-border-soft p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 aseel-bg-panel dark:aseel-bg-panel rounded-lg">
          <History className="w-6 h-6 aseel-text-soft dark:aseel-text-soft" />
        </div>
        <div>
          <h3 className="text-lg font-bold aseel-text-ink dark:text-white">سجل النشاطات</h3>
          <p className="text-sm aseel-text-soft dark:aseel-text-soft">
            جميع التغييرات والإجراءات على الصفقة
          </p>
        </div>
      </div>

      <div className="space-y-4 max-h-96 overflow-y-auto">
        {activities.length === 0 ? (
          <div className="text-center py-8 aseel-text-soft dark:aseel-text-soft">
            <History className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>لا توجد نشاطات مسجلة بعد</p>
          </div>
        ) : (
          activities.map((activity) => (
            <div key={activity.id} className="border-l-4 aseel-border-soft pl-4 py-3">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <div className={`p-2 rounded-lg ${getActivityColor(activity.type)}`}>
                    {getActivityIcon(activity.type)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <User className="w-4 h-4 aseel-text-soft" />
                      <span className="font-medium aseel-text-ink dark:text-white">
                        {activity.userName}
                      </span>
                      <span className={`text-xs px-2 py-1 rounded-full ${getActivityColor(activity.type)}`}>
                        {activity.action}
                      </span>
                    </div>
                    <p className="aseel-text-ink dark:aseel-text-soft mb-1">
                      {activity.details}
                    </p>
                    {activity.metadata && (
                      <div className="text-xs aseel-text-soft dark:aseel-text-soft mt-1">
                        {Object.entries(activity.metadata).map(([key, value]) => (
                          <span key={key} className="inline-block aseel-bg-panel dark:aseel-bg-panel px-2 py-1 rounded mr-2 mb-1">
                            {key}: {String(value)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 text-sm aseel-text-soft dark:aseel-text-soft">
                  <Clock className="w-4 h-4" />
                  {formatDateTimeValue(activity.timestamp)}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};