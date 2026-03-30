import React from 'react';
import { 
  History, User, Clock, FileText, DollarSign, 
  Package, CheckCircle, AlertCircle, Edit, Trash2 
} from 'lucide-react';
import { DealActivity } from '../../../types';

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
      case 'status_change': return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400';
      case 'payment': return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
      case 'item_update': return 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400';
      case 'note': return 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400';
      default: return 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400';
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
          <History className="w-6 h-6 text-gray-600 dark:text-gray-400" />
        </div>
        <div>
          <h3 className="text-lg font-bold text-gray-900 dark:text-white">سجل النشاطات</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            جميع التغييرات والإجراءات على الصفقة
          </p>
        </div>
      </div>

      <div className="space-y-4 max-h-96 overflow-y-auto">
        {activities.length === 0 ? (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <History className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>لا توجد نشاطات مسجلة بعد</p>
          </div>
        ) : (
          activities.map((activity) => (
            <div key={activity.id} className="border-l-4 border-blue-500 pl-4 py-3">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <div className={`p-2 rounded-lg ${getActivityColor(activity.type)}`}>
                    {getActivityIcon(activity.type)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <User className="w-4 h-4 text-gray-400" />
                      <span className="font-medium text-gray-900 dark:text-white">
                        {activity.userName}
                      </span>
                      <span className={`text-xs px-2 py-1 rounded-full ${getActivityColor(activity.type)}`}>
                        {activity.action}
                      </span>
                    </div>
                    <p className="text-gray-700 dark:text-gray-300 mb-1">
                      {activity.details}
                    </p>
                    {activity.metadata && (
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {Object.entries(activity.metadata).map(([key, value]) => (
                          <span key={key} className="inline-block bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded mr-2 mb-1">
                            {key}: {String(value)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                  <Clock className="w-4 h-4" />
                  {new Date(activity.timestamp).toLocaleString('ar-EG')}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};