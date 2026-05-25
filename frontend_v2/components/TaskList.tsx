import React, { useState, useMemo, useEffect } from 'react';
import { Task, User, Category, getUserTaskStatus, getUserSubmissions } from '../types';
import { TaskCard } from './TaskCard';
import { getCategories } from '../services/firestoreService'; // استيراد دالة جلب الفئات

interface TaskListProps {
  user: User;
  tasks: Task[];
  categories?: Category[]; // إضافة prop للفئات
  onSelectTask: (task: Task) => void;
}

// أنواع الفلاتر
type StatusFilter = 'all' | 'not_started' | 'in_progress' | 'submitted' | 'completed' | 'rejected';
type CategoryFilter = 'all' | string;

export const TaskList: React.FC<TaskListProps> = ({ 
  user, 
  tasks, 
  categories: propCategories, 
  onSelectTask 
}) => {
  // حالة الفلاتر والبحث
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  
  // حالة محلية للفئات إذا لم تكن ممررة
  const [localCategories, setLocalCategories] = useState<Category[]>([]);
  
  // دمج الفئات الممررة مع الفئات المحلية
  const categories = propCategories || localCategories;

  // جلب الفئات إذا لم تكن ممررة
  useEffect(() => {
    if (!propCategories) {
      const fetchCategories = async () => {
        try {
          const fetchedCategories = await getCategories();
          setLocalCategories(fetchedCategories);
        } catch (error) {
          // console suppressed
        }
      };
      fetchCategories();
    }
  }, [propCategories]);

  // تصفية المهام المعينة للموظف الحالي
  const userTasks = useMemo(() => {
    return tasks.filter(task => {
      if (Array.isArray(task.assignedTo)) {
        return task.assignedTo.includes(user.id);
      }
      return task.assignedTo === user.id;
    });
  }, [tasks, user.id]);

  // الحصول على حالة الموظف الحالي في كل مهمة
  const getCurrentUserTaskStatus = (task: Task) => {
    // أولاً: التحقق من الحالة الفردية للموظف
    const userStatus = task.userStatuses?.[user.id];
    
    if (userStatus) {
      return {
        hasSubmission: userStatus.status === 'submitted' || userStatus.status === 'completed',
        status: userStatus.status,
        submissionCount: getUserSubmissions(task, user.id).length,
        userStatus: userStatus
      };
    }
    
    // إذا لم تكن هناك حالة فردية، نستخدم التسليمات
    const userSubmissions = getUserSubmissions(task, user.id);
    
    if (userSubmissions.length > 0) {
      const latestSubmission = userSubmissions[userSubmissions.length - 1];
      const submissionStatus = latestSubmission.status === 'approved' ? 'completed' : 
                              latestSubmission.status === 'rejected' ? 'rejected' : 'submitted';
      
      return {
        hasSubmission: true,
        status: submissionStatus,
        submissionCount: userSubmissions.length,
        userStatus: {
          status: submissionStatus,
          startedAt: userSubmissions[0]?.createdAt
        }
      };
    }
    
    return {
      hasSubmission: false,
      status: 'not_started',
      submissionCount: 0,
      userStatus: null
    };
  };

   const getCategoryName = (categoryId: string) => {
    const category = categories.find(c => c.id === categoryId);
    return category ? category.name : 'غير مصنف';
  };

  // المهام المصفاة بناءً على الفلاتر والبحث
  const filteredTasks = useMemo(() => {
    return userTasks.filter(task => {
      // فلتر البحث
      const matchesSearch = searchQuery === '' || 
        task.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        task.description.toLowerCase().includes(searchQuery.toLowerCase());
      
      if (!matchesSearch) return false;

      // فلتر الفئة
      const matchesCategory = categoryFilter === 'all' || task.category === categoryFilter;
      if (!matchesCategory) return false;

      // فلتر الحالة
      if (statusFilter === 'all') return true;
      
      const userStatus = getCurrentUserTaskStatus(task);
      return userStatus.status === statusFilter;
    });
  }, [userTasks, statusFilter, categoryFilter, searchQuery, user.id]);

  // إحصائيات المهام
  const taskStats = useMemo(() => {
    const stats = {
      all: 0,
      not_started: 0,
      in_progress: 0,
      submitted: 0,
      completed: 0,
      rejected: 0
    };

    userTasks.forEach(task => {
      const userStatus = getCurrentUserTaskStatus(task);
      stats.all++;
      stats[userStatus.status as keyof typeof stats]++;
    });

    return stats;
  }, [userTasks]);

  // الحصول على أسماء الفئات
  const categoryOptions = useMemo(() => {
    const options = [
      { value: 'all', label: 'جميع الفئات' }
    ];
    
    // إضافة الفئات الفريدة من المهام
    const uniqueCategories = Array.from(
      new Set(userTasks.map(task => task.category).filter(Boolean))
    );
    
    uniqueCategories.forEach(categoryId => {
      const categoryName = getCategoryName(categoryId as string);
      options.push({
        value: categoryId as string,
        label: categoryName
      });
    });
    
    // إضافة الفئات من قاعدة البيانات التي قد لا تكون مستخدمة في المهام
    categories.forEach(category => {
      if (!options.find(opt => opt.value === category.id)) {
        options.push({
          value: category.id,
          label: category.name
        });
      }
    });
    
    return options;
  }, [userTasks, categories]);

  // خيارات فلتر الحالة
  const statusOptions: { value: StatusFilter; label: string; color: string }[] = [
    { value: 'all', label: 'جميع المهام', color: 'gray' },
    { value: 'not_started', label: 'لم تبدأ', color: 'gray' },
    { value: 'in_progress', label: 'قيد التنفيذ', color: 'blue' },
    { value: 'submitted', label: 'مسلمة', color: 'yellow' },
    { value: 'completed', label: 'مكتملة', color: 'green' },
    { value: 'rejected', label: 'مرفوضة', color: 'red' },
  ];

  // إعادة تعيين الفلاتر
  const resetFilters = () => {
    setStatusFilter('all');
    setCategoryFilter('all');
    setSearchQuery('');
  };

  // عرض تحميل إذا كانت الفئات لم تُحمل بعد
  if (!propCategories && localCategories.length === 0) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="mt-2 text-gray-600 dark:text-gray-400">جاري تحميل الفئات...</p>
        </div>
      </div>
    );
  }

   return (
    <div className="animate-fade-in">
      {/* العنوان والإحصائيات */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-800 dark:text-gray-100">
            المهام المسندة ({filteredTasks.length}/{userTasks.length})
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            قم بتصفية المهام حسب حالتها، فئتها، أو ابحث عن مهمة معينة
          </p>
        </div>
        
        <div className="flex items-center gap-2 text-sm">
          <span className="text-gray-600 dark:text-gray-300">الإحصائيات:</span>
          <div className="flex flex-wrap gap-2">
            <span className="px-2 py-1 bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 rounded-full text-xs">
              قيد التنفيذ: {taskStats.in_progress}
            </span>
            <span className="px-2 py-1 bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 rounded-full text-xs">
              مكتملة: {taskStats.completed}
            </span>
            <span className="px-2 py-1 bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200 rounded-full text-xs">
              مسلمة: {taskStats.submitted}
            </span>
          </div>
        </div>
      </div>

      {/* مربع البحث */}
      <div className="mb-6">
        <div className="relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="ابحث عن مهمة بالاسم أو الوصف..."
            className="w-full px-4 py-3 pr-12 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:focus:ring-blue-400 text-gray-800 dark:text-gray-200"
          />
          <div className="absolute left-3 top-1/2 transform -translate-y-1/2">
            {searchQuery ? (
              <button
                onClick={() => setSearchQuery('')}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                ✕
              </button>
            ) : (
              <span className="text-gray-400">🔍</span>
            )}
          </div>
        </div>
      </div>

      {/* الفلاتر */}
      <div className="mb-6 space-y-4">
        <div className="flex flex-col md:flex-row gap-4">
          {/* فلتر الحالة */}
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              تصفية حسب الحالة:
            </label>
            <div className="flex flex-wrap gap-2">
              {statusOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setStatusFilter(option.value)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                    statusFilter === option.value
                      ? `bg-${option.color}-100 text-${option.color}-800 dark:bg-${option.color}-900 dark:text-${option.color}-200 border border-${option.color}-300 dark:border-${option.color}-700`
                      : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
                >
                  {option.label} {option.value !== 'all' && `(${taskStats[option.value]})`}
                </button>
              ))}
            </div>
          </div>

{/* فلتر الفئة - قائمة اختيار متقدمة */}
<div className="flex-1">
  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
    تصفية حسب الفئة:
  </label>
  
  <div className="relative">
    <div className="relative">
      <select
        value={categoryFilter}
        onChange={(e) => setCategoryFilter(e.target.value as CategoryFilter)}
        className="w-full px-4 py-2.5 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:focus:ring-blue-400 text-gray-800 dark:text-gray-200 appearance-none cursor-pointer pr-10"
      >
        <option value="all" className="py-2">
          جميع الفئات
        </option>
        
        {/* فئات من قاعدة البيانات */}
        {categoryOptions
          .filter(option => option.value !== 'all') // إخفاء "جميع الفئات" من القائمة الداخلية
          .map((option) => (
            <option 
              key={option.value} 
              value={option.value}
              className="py-2"
            >
              {option.label}
            </option>
          ))
        }
      </select>
      
      {/* سهم القائمة */}
      <div className="absolute left-3 top-1/2 transform -translate-y-1/2 pointer-events-none">
        <svg className="w-4 h-4 text-gray-500 dark:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>
    
    {/* عرض الفئة المختارة */}
    {categoryFilter !== 'all' && (
      <div className="mt-2 flex items-center justify-between">
        <span className="text-sm text-gray-600 dark:text-gray-400">
          الفئة المحددة: <span className="font-semibold text-blue-600 dark:text-blue-400">
            {categoryOptions.find(opt => opt.value === categoryFilter)?.label}
          </span>
        </span>
        <button
          onClick={() => setCategoryFilter('all')}
          className="text-xs text-red-500 hover:text-red-700 dark:hover:text-red-400 flex items-center gap-1"
        >
          <span>✕</span>
          إزالة الفلتر
        </button>
      </div>
    )}
  </div>
</div>
        </div>

        {/* زر إعادة التعيين */}
        {(statusFilter !== 'all' || categoryFilter !== 'all' || searchQuery) && (
          <div className="flex justify-end">
            <button
              onClick={resetFilters}
              className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 flex items-center gap-2"
            >
              <span>↺</span>
              إعادة تعيين جميع الفلاتر
            </button>
          </div>
        )}
      </div>

      {/* عرض المهام */}
      {filteredTasks.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredTasks.map(task => (
            <TaskCard 
              key={task.id} 
              task={task} 
              user={user} 
              userTaskStatus={getCurrentUserTaskStatus(task)}
              onSelectTask={onSelectTask}
              categoryName={getCategoryName(task.category)} // تمرير اسم الفئة
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-16 bg-white dark:bg-gray-800 rounded-2xl shadow-sm border dark:border-gray-700">
          <h3 className="text-xl font-semibold text-gray-700 dark:text-gray-300">
            {userTasks.length === 0 
              ? "لا توجد مهام مسندة حاليًا." 
              : "لا توجد مهام تطابق معايير البحث."}
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mt-2">
            {userTasks.length === 0 
              ? "استمتع بوقتك!" 
              : "جرب تغيير معايير البحث أو الفلاتر."}
          </p>
          {userTasks.length > 0 && (
            <button
              onClick={resetFilters}
              className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
            >
              عرض جميع المهام
            </button>
          )}
        </div>
      )}
    </div>
  );
};