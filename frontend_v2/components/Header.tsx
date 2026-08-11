import React, { useState, useEffect, useRef } from "react";
import { User, Task } from "../types";
import { ThemeToggle } from "./ThemeToggle";
import { SearchIcon } from "./icons/SearchIcon";
import {
  activityService,
  pointsHistoryService,
} from "../services/firestoreService";
import { DailyPoints, ActivityStatus, AppView } from "../types";
import { NotificationCenter } from "./notifications/NotificationCenter";

interface HeaderProps {
  user: User;
  onLogout: () => void;
  activeTask: Task | null;
  userTaskTime?: number;
  showReturnButton: boolean;
  onReturnToTask: () => void;
  theme: string;
  toggleTheme: () => void;
  onNavigate: (view: AppView, targetId?: string) => void;
}

const formatTime = (seconds: number) => {
  const h = Math.floor(seconds / 3600)
    .toString()
    .padStart(2, "0");
  const m = Math.floor((seconds % 3600) / 60)
    .toString()
    .padStart(2, "0");
  const s = (seconds % 60).toString().padStart(2, "0");
  return `${h}:${m}:${s}`;
};

export const Header: React.FC<HeaderProps> = ({
  user,
  onLogout,
  activeTask,
  userTaskTime,
  theme,
  toggleTheme,
  showReturnButton,
  onReturnToTask,
  onNavigate,
}) => {
  const [dailyPoints, setDailyPoints] = useState<DailyPoints | null>(null);
  const [activityStatus, setActivityStatus] = useState<ActivityStatus | null>(
    null
  );
  const [isCheckingIn, setIsCheckingIn] = useState(false);
  const [checkInMessage, setCheckInMessage] = useState<string | null>(null);
  const [timeRemaining, setTimeRemaining] = useState(10);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [playSound, setPlaySound] = useState(false);

  // استخدام useRef للإشارة إلى عنصر <audio> في الـ DOM
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // تشغيل الصوت عندما يصل الوقت إلى 2 دقيقة (بعد مرور 8 دقائق)
  useEffect(() => {
    if (timeRemaining === 2 && playSound && audioRef.current) {
      // إعادة تحميل الصوت لضمان بدء التشغيل من البداية
      audioRef.current.currentTime = 0;

      audioRef.current.play()
        .then(() => {
        })
        .catch(error => {
          // إظهار رسالة مرئية بديلة
          setCheckInMessage('🔔 حان وقت تأكيد الاستمرار!');
          setTimeout(() => setCheckInMessage(null), 3000);
        });

      // تم إزالة كود الإشعارات تماماً

      setPlaySound(false);
    }
  }, [timeRemaining, playSound]);

  // الاشتراك في بيانات النقاط اليومية
  useEffect(() => {
    if (!user) return;

    const unsubscribePoints = pointsHistoryService.subscribeToDailyPoints(
      user.id,
      setDailyPoints
    );
    const unsubscribeActivity = activityService.subscribeToActivityStatus(
      user.id,
      setActivityStatus
    );

    return () => {
      unsubscribePoints();
      unsubscribeActivity();
    };
  }, [user]);

  // تحديث الوقت الحالي كل ثانية للعداد
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  // التحقق من النشاط كل دقيقة وتحديث الوقت المتبقي
  useEffect(() => {
    const checkActivity = () => {
      void activityService.checkActivityStatus(user.id);
    };

    checkActivity();
    const interval = setInterval(checkActivity, 60000);

    return () => clearInterval(interval);
  }, [user.id]);

  // تحديث الوقت المتبقي باستمرار
  useEffect(() => {
    updateTimeRemaining();
  }, [currentTime, activityStatus]);

  const updateTimeRemaining = () => {
    if (!activityStatus?.lastCheckIn) {
      setTimeRemaining(10);
      setPlaySound(true);
      return;
    }

    const lastCheckIn = new Date(activityStatus.lastCheckIn);
    const now = new Date();
    const timeDiff = now.getTime() - lastCheckIn.getTime();
    const minutesDiff = timeDiff / (1000 * 60);
    const remaining = Math.max(0, 10 - Math.floor(minutesDiff));

    setTimeRemaining(remaining);

    if (remaining === 10) {
      setPlaySound(true);
    }
  };

  const handleCheckIn = async () => {
    // التصحيح لـ 8 دقائق: منع الضغط إذا كان الوقت المتبقي أكثر من دقيقتين (أي 3 أو أكثر)
    if (timeRemaining > 2) {
      setCheckInMessage("الزر سيعمل بعد مرور 8 دقائق ⏳");
      setTimeout(() => setCheckInMessage(null), 2000);
      return;
    }

    if (!user || isCheckingIn) return;

    setIsCheckingIn(true);
    setCheckInMessage(null);

    try {
      const result = await activityService.recordCheckIn(user.id);
      if (result.success) {
        setCheckInMessage(`+${result.points} نقطة! ✅`);
        setTimeout(() => setCheckInMessage(null), 3000);

        const updatedStatus = await activityService.getActivityStatus(user.id);
        setActivityStatus(updatedStatus);
        updateTimeRemaining();

        // تم إزالة طلب إذن الإشعارات تماماً

      } else {
        setCheckInMessage("انتظر قليلاً قبل الضغط مرة أخرى ⏳");
        setTimeout(() => setCheckInMessage(null), 2000);
      }
    } catch (error: any) {
      setCheckInMessage(error.message || "حدث خطأ");
      setTimeout(() => setCheckInMessage(null), 3000);
    } finally {
      setIsCheckingIn(false);
    }
  };

  const isCheckInEnabled = activityStatus?.checkInButtonEnabled !== false;
  const isActive = activityStatus?.isCurrentlyActive;

  // التصحيح لـ 8 دقائق: تحديد لون الزر ليعمل فقط في آخر دقيقتين (timeRemaining <= 2)
  const getButtonColor = () => {
    if (timeRemaining > 2) return "bg-gray-400 cursor-not-allowed"; // معطل في أول 8 دقائق
    return "bg-red-500 hover:bg-red-600 animate-pulse"; // مفعل في آخر دقيقتين
  };

  // تحديد لون النص بناءً على الوقت المتبقي
  const getTimerColor = () => {
    if (timeRemaining > 2) return "text-gray-200"; // معطل
    return "text-white"; // مفعل
  };

  // التصحيح لـ 8 دقائق: تعطيل الزر إذا كان الوقت المتبقي أكثر من دقيقتين
  const isButtonDisabled = timeRemaining > 2 || isCheckingIn;

  return (
    <header className="relative flex flex-col sm:flex-row items-center justify-between pt-4 pb-4 pr-4 pl-14 sm:pl-16 bg-[var(--color-surface)] border-b border-[var(--color-border)] sticky top-0 z-50 shadow-sm gap-4 sm:gap-0">

      {/* جرس الإشعارات — أعلى يسار الشاشة (يسار مطلق) */}
      <div className="absolute left-3 top-1/2 z-[60] -translate-y-1/2">
        <NotificationCenter currentUserId={user.id} onNavigate={onNavigate} />
      </div>

      {/* عنصر الصوت المخفي */}
      <audio
        ref={audioRef}
        src="/notification-sound.mp3"
        preload="auto"
        className="hidden"
      />

      {/* الجانب الأيسر: العداد وزر العودة */}
      <div className="flex items-center w-full sm:w-auto justify-between sm:justify-start gap-4">
        {/* زر تأكيد الاستمرار */}
        {(user.role === "employee" || user.role === "procurement") && isCheckInEnabled && (
          <div className="flex flex-col items-center">
            <button
              onClick={handleCheckIn}
              disabled={isButtonDisabled}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg shadow-md transition-all text-sm font-bold ${getButtonColor()} ${getTimerColor()} ${isButtonDisabled ? 'cursor-not-allowed opacity-80' : ''
                }`}
              title={timeRemaining > 2 ? "الزر سيعمل بعد مرور 8 دقائق" : "انقر لتأكيد الاستمرار"}
            >
              {isCheckingIn ? (
                <span>جاري التسجيل...</span>
              ) : (
                <>
                  <span>
                    {timeRemaining > 2 ? "انتظر..." : "تأكيد الاستمرار"}
                  </span>
                  <span
                    className={`text-xs bg-[var(--color-surface)] bg-opacity-20 px-2 py-1 rounded ${getTimerColor()}`}
                  >
                    {timeRemaining} د
                  </span>
                </>
              )}
            </button>

            {checkInMessage && (
              <div
                className={`text-xs mt-1 font-semibold ${checkInMessage.includes("✅")
                  ? "text-green-600"
                  : checkInMessage.includes("⏳")
                    ? "text-yellow-600"
                    : checkInMessage.includes("🔔")
                      ? "text-orange-600 animate-pulse"
                      : "text-red-600"
                  }`}
              >
                {checkInMessage}
              </div>
            )}

            {/* مؤشر النشاط */}
            <div className="text-xs text-[var(--color-text-muted)] mt-1">
              {isActive ? "✅ نشط" : "❌ غير نشط"}
            </div>

          </div>
        )}

        {/* عرض النقاط اليومية */}
        {dailyPoints && (
          <div className="flex items-center gap-4">
            <div className="text-center">
              <div className="text-xs text-[var(--color-text-muted)]">
                النقاط اليوم
              </div>
              <div className="text-lg font-bold text-blue-600 dark:text-blue-400">
                {dailyPoints.totalPoints}
              </div>
            </div>

            <div className="hidden sm:flex items-center gap-3">
              <div className="text-center">
                <div className="text-xs text-[var(--color-text-muted)]">
                  النشاط
                </div>
                <div className="text-sm font-semibold text-green-600 dark:text-green-400">
                  {dailyPoints.activityPoints}
                </div>
              </div>

              <div className="text-center">
                <div className="text-xs text-[var(--color-text-muted)]">
                  المهام
                </div>
                <div className="text-sm font-semibold text-[var(--color-primary)] dark:text-[var(--color-primary)]">
                  {dailyPoints.taskPoints}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* الجانب الأيمن: المستخدم والإعدادات */}
      <div className="flex items-center w-full sm:w-auto justify-end gap-3 sm:gap-4">
        {/* حالة النشاط المصغرة */}
        {(user.role === "employee" || user.role === "procurement") && (
          <div
            className={`w-3 h-3 rounded-full ${isActive ? "bg-green-500" : "bg-red-500"
              }`}
            title={isActive ? "نشط" : "غير نشط"}
          />
        )}

        <div className="text-left hidden sm:block">
          <p className="font-semibold text-[var(--color-text)] text-sm">
            {user.name}
          </p>
          <p className="text-xs text-[var(--color-text-muted)] flex items-center justify-end gap-1">
            {user.role === "manager" ? "مدير" : "موظف"}
            {user.isApproved && (
              <span
                className="w-2 h-2 rounded-full bg-green-500"
                title="Active"
              ></span>
            )}
          </p>
        </div>

        <button
          onClick={onLogout}
          className="bg-red-500 hover:bg-red-600 text-white text-sm font-semibold py-2 px-4 rounded-lg transition-colors duration-200 flex items-center gap-2 shadow-md hover:shadow-red-500/25"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          تسجيل الخروج
        </button>
      </div>
    </header>
  );
};
