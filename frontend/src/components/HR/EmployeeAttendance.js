import React, { useState, useEffect } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { ar } from 'date-fns/locale';

export const EmployeeAttendance = ({ currentUser, activeSession, onMarkAttendance }) => {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [hasAttended, setHasAttended] = useState(false);
  const [timeLeft, setTimeLeft] = useState(0);

  useEffect(() => {
    if (activeSession) {
      const attended = activeSession.attendees?.includes(currentUser?.id);
      setHasAttended(attended);
      startTimer(activeSession);
    }
  }, [activeSession, currentUser]);

  const startTimer = (session) => {
    const startTime = new Date(session.startTime || Date.now()).getTime();
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
      if (onMarkAttendance) await onMarkAttendance(currentUser.id, activeSession.id);
      setHasAttended(true);
      setMessage('تم تسجيل حضورك بنجاح! +10 نقاط 🎉');
      setTimeout(() => setMessage(''), 5000);
    } catch (error) {
      setMessage(error.message || 'حدث خطأ أثناء تسجيل الحضور');
      setTimeout(() => setMessage(''), 5000);
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  if (!activeSession) {
    return (
      <div className="animate-fade-in p-6">
        <h1 className="text-3xl font-bold mb-6 text-gray-800">الحضور والغياب</h1>
        <div className="bg-white rounded-2xl p-8 shadow-md border text-center">
          <div className="text-6xl mb-4">⏰</div>
          <h2 className="text-2xl font-bold text-gray-800 mb-4">لا توجد جلسة حضور نشطة</h2>
          <p className="text-gray-600 text-lg">انتظر حتى يبدأ المدير جلسة حضور جديدة</p>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in p-6">
      <h1 className="text-3xl font-bold mb-6 text-gray-800">الحضور والغياب</h1>
      <div className="bg-white rounded-2xl p-6 shadow-md border mb-6 text-center">
        <div className="text-4xl mb-4">📅</div>
        <h2 className="text-2xl font-bold mb-2">جلسة حضور نشطة</h2>
        <p className="text-gray-600 mb-4">
          بدأت منذ {formatDistanceToNow(new Date(activeSession.startTime || Date.now()), { locale: ar, addSuffix: true })}
        </p>
        
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6 inline-block">
          <div className="flex items-center gap-2 text-yellow-800">
            <span className="text-lg">⏳</span>
            <span className="font-semibold">متبقي: {formatTime(timeLeft)}</span>
          </div>
        </div>

        {message && (
          <div className={`p-4 rounded-lg mb-4 ${message.includes('نجاح') ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
            {message}
          </div>
        )}

        {hasAttended ? (
          <div className="bg-green-50 border border-green-200 rounded-lg p-6">
            <div className="text-4xl mb-2">✅</div>
            <h3 className="text-xl font-bold text-green-800 mb-2">تم تسجيل حضورك</h3>
            <p className="text-green-600">لقد حصلت على 10 نقاط للحضور</p>
          </div>
        ) : (
          <button
            onClick={handleMarkAttendance}
            disabled={loading}
            className="bg-blue-500 hover:bg-blue-600 text-white px-8 py-4 rounded-lg font-semibold transition-colors disabled:opacity-50"
          >
            {loading ? 'جاري التسجيل...' : 'تأكيد الحضور 🎯'}
          </button>
        )}
      </div>
    </div>
  );
};
