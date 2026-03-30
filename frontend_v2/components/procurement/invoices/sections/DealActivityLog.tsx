import React from 'react';
import { DealActivity } from '@/types';
import { History, CheckCircle, XCircle, FileText, DollarSign, Clock } from 'lucide-react';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';

interface DealActivityLogProps {
  activities: DealActivity[];
}

export const DealActivityLog: React.FC<DealActivityLogProps> = ({ activities }) => {
  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'status_change':
        return <CheckCircle className="w-4 h-4 text-blue-500" />;
      case 'payment':
        return <DollarSign className="w-4 h-4 text-green-500" />;
      case 'note':
        return <FileText className="w-4 h-4 text-gray-500" />;
      case 'attachment':
        return <FileText className="w-4 h-4 text-purple-500" />;
      default:
        return <Clock className="w-4 h-4 text-gray-500" />;
    }
  };

  const getActivityColor = (type: string) => {
    switch (type) {
      case 'status_change':
        return 'border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/10';
      case 'payment':
        return 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/10';
      case 'note':
        return 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/10';
      case 'attachment':
        return 'border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/10';
      default:
        return 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/10';
    }
  };

  return (
    <CollapsibleSection
      title="سجل نشاطات الصفقة"
      icon={History}
      defaultOpen={false}
      className="border-gray-200 dark:border-gray-700"
    >
      <div className="space-y-3">
        {activities.length === 0 ? (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
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
                    <p className="font-medium text-gray-900 dark:text-white">
                      {activity.action}
                    </p>
                    {activity.details && (
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        {activity.details}
                      </p>
                    )}
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                      <span>بواسطة: {activity.userName}</span>
                      <span>الدور: {activity.userRole}</span>
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm text-gray-500">
                    {new Date(activity.timestamp).toLocaleString('ar-SA', {
                      dateStyle: 'short',
                      timeStyle: 'short'
                    })}
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