// components/EmployeeAttendance.tsx
import React, { useState, useEffect } from 'react';
import { User, AttendanceSession } from '../types';
import { attendanceService } from '../services/attendanceService';
import { formatDistanceToNow } from 'date-fns';
import { ar } from 'date-fns/locale';

interface EmployeeAttendanceProps {
  currentUser: User;
}

export const EmployeeAttendance: React.FC<EmployeeAttendanceProps> = ({ currentUser }) => {
  const [activeSession, setActiveSession] = useState<AttendanceSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string>('');
  const [hasAttended, setHasAttended] = useState(false);
  const [timeLeft, setTimeLeft] = useState<number>(0);

  useEffect(() => {
    const unsubscribe = attendanceService.subscribeToActiveSession((session) => {
      setActiveSession(session);
      if (session) {
        checkIfAttended(session);
        startTimer(session);
      }
    });

    // تحميل الجلسة النشطة الحالية
    attendanceService.getActiveSession().then(session => {
      setActiveSession(session);
      if (session) {
        checkIfAttended(session);
        startTimer(session);
      }
    });

    return unsubscribe;
  }, []);

  const checkIfAttended = (session: AttendanceSession) => {
    const attended = session.attendees.includes(currentUser.id);
    setHasAttended(attended);
  };

  const startTimer = (session: AttendanceSession) => {
    const startTime = new Date(session.startTime).getTime();
    const endTime = startTime + (5 * 60 * 1000);
    
    const updateTimer = () => {
      const now = Date.now();
      const remaining = Math.max(0, endTime - now);
      setTimeLeft(Math.ceil(remaining / 1000));
      
      if (remaining > 0) {
        setTimeout(updateTimer, 1000);
      }
    };
    
    updateTimer();
  };

  const handleMarkAttendance = async () => {
    if (!activeSession) return;
    
    try {
      setLoading(true);
      setMessage('');
      
      await attendanceService.markAttendance(currentUser.id, activeSession.id);
      setHasAttended(true);
      setMessage('تم تسجيل حضورك بنجاح! +10 نقاط 🎉');
      
      setTimeout(() => setMessage(''), 5000);
    } catch (error: any) {
      setMessage(error.message || 'حدث خطأ أثناء تسجيل الحضور');
      setTimeout(() => setMessage(''), 5000);
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  if (!activeSession) {
    return (
      <div className="animate-fade-in">
        <h1 className="text-3xl font-bold mb-6 text-[var(--color-text)]">
          الحضور والغياب
        </h1>
        
        <div className="bg-[var(--color-surface)] rounded-2xl p-8 shadow-md border border-[var(--color-border)] text-center">
          <div className="text-6xl mb-4">⏰</div>
          <h2 className="text-2xl font-bold text-[var(--color-text)] mb-4">
            لا توجد جلسة حضور نشطة
          </h2>
          <p className="text-[var(--color-text-muted)] text-lg">
            انتظر حتى يبدأ المدير جلسة حضور جديدة
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <h1 className="text-3xl font-bold mb-6 text-[var(--color-text)]">
        الحضور والغياب
      </h1>

      {/* جلسة الحضور النشطة */}
      <div className="bg-[var(--color-surface)] rounded-2xl p-6 shadow-md border border-[var(--color-border)] mb-6">
        <div className="text-center">
          <div className="text-4xl mb-4">📅</div>
          <h2 className="text-2xl font-bold text-[var(--color-text)] mb-2">
            جلسة حضور نشطة
          </h2>
          <p className="text-[var(--color-text-muted)] mb-4">
            بدأت منذ {formatDistanceToNow(new Date(activeSession.startTime), { locale: ar, addSuffix: true })}
          </p>
          
          <div className="bg-yellow-50 dark:bg-yellow-900/50 border border-yellow-200 dark:border-yellow-700 rounded-lg p-4 mb-6">
            <div className="flex items-center justify-center gap-2 text-yellow-800 dark:text-yellow-200">
              <span className="text-lg">⏳</span>
              <span className="font-semibold">متبقي: {formatTime(timeLeft)}</span>
            </div>
          </div>

          {message && (
            <div className={`p-4 rounded-lg mb-4 ${
              message.includes('نجاح') 
                ? 'bg-green-50 dark:bg-green-900/50 border border-green-200 dark:border-green-700 text-green-800 dark:text-green-200'
                : 'bg-red-50 dark:bg-red-900/50 border border-red-200 dark:border-red-700 text-red-800 dark:text-red-200'
            }`}>
              {message}
            </div>
          )}

          {hasAttended ? (
            <div className="bg-green-50 dark:bg-green-900/50 border border-green-200 dark:border-green-700 rounded-lg p-6">
              <div className="text-4xl mb-2">✅</div>
              <h3 className="text-xl font-bold text-green-800 dark:text-green-200 mb-2">
                تم تسجيل حضورك
              </h3>
              <p className="text-green-600 dark:text-green-300">
                لقد حصلت على 10 نقاط للحضور
              </p>
            </div>
          ) : (
            <button
              onClick={handleMarkAttendance}
              disabled={loading}
              className="bg-blue-500 hover:bg-blue-600 text-white px-8 py-4 rounded-lg font-semibold text-lg transition-colors disabled:opacity-50 w-full max-w-md"
            >
              {loading ? 'جاري التسجيل...' : 'تأكيد الحضور 🎯'}
            </button>
          )}
        </div>
      </div>

      {/* معلومات الجلسة */}
      <div className="bg-[var(--color-surface)] rounded-2xl p-6 shadow-md border border-[var(--color-border)]">
        <h3 className="text-lg font-bold text-[var(--color-text)] mb-4">
          معلومات الجلسة
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div>
            <span className="font-semibold text-[var(--color-text-muted)]">تاريخ الجلسة:</span>
            <span className="mr-2 text-[var(--color-text)]">
              {new Date(activeSession.startTime).toLocaleDateString('ar-EG')}
            </span>
          </div>
          <div>
            <span className="font-semibold text-[var(--color-text-muted)]">وقت البدء:</span>
            <span className="mr-2 text-[var(--color-text)]">
              {new Date(activeSession.startTime).toLocaleTimeString('ar-EG')}
            </span>
          </div>
          <div>
            <span className="font-semibold text-[var(--color-text-muted)]">النقاط:</span>
            <span className="mr-2 text-green-600 dark:text-green-400 font-bold">
              +10 لكل حاضر
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};