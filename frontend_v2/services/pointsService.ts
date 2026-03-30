import { 
  doc, 
  getDoc, 
  setDoc, 
  updateDoc, 
  collection, 
  query, 
  where, 
  getDocs,
  onSnapshot,
  Timestamp,
  db
} from "./sqlApiClient";
import { ActivityStatus, DailyPoints, PointsSystem } from "../types";

// إعدادات النظام الافتراضية
const DEFAULT_POINTS_SYSTEM: PointsSystem = {
  activityPointsPerClick: 1,
  taskPointsFast: 10,
  taskPointsNormal: 5,
  maxActivityPointsPerDay: 50
};

// --- خدمة حالة النشاط ---
export const activityService = {
  // تهيئة حالة النشاط للمستخدم
  async initializeActivityStatus(userId: string): Promise<void> {
    const activityRef = doc(db, "activityStatus", userId);
    const today = new Date().toISOString().split('T')[0];
    
    const activityData: ActivityStatus = {
      userId,
      lastCheckIn: new Date().toISOString(),
      activeMinutesToday: 0,
      checkinClickCount: 0,
      isCurrentlyActive: true,
      checkInButtonEnabled: true,
      lastActivityCheck: new Date().toISOString()
    };
    
    await setDoc(activityRef, activityData);
  },

  // تسجيل ضغطة زر التأكيد
  async recordCheckIn(userId: string): Promise<{ success: boolean; points: number }> {
    const activityRef = doc(db, "activityStatus", userId);
    const activitySnap = await getDoc(activityRef);
    
    if (!activitySnap.exists()) {
      await this.initializeActivityStatus(userId);
    }

    const activityData = activitySnap.data() as ActivityStatus;
    
    // التحقق من أن الزر مفعل
    if (!activityData.checkInButtonEnabled) {
      throw new Error("نظام النقاط معطل لحسابك");
    }

    const now = new Date();
    const lastCheckIn = new Date(activityData.lastCheckIn);
    const timeDiff = now.getTime() - lastCheckIn.getTime();
    const minutesDiff = timeDiff / (1000 * 60);

    // منع الضغط المتكرر خلال أقل من دقيقة
    if (minutesDiff < 1) {
      return { success: false, points: 0 };
    }

    // تحديث البيانات
    const updates: Partial<ActivityStatus> = {
      lastCheckIn: now.toISOString(),
      checkinClickCount: activityData.checkinClickCount + 1,
      isCurrentlyActive: true,
      lastActivityCheck: now.toISOString()
    };

    await updateDoc(activityRef, updates);

    // تحديث النقاط اليومية
    const pointsEarned = DEFAULT_POINTS_SYSTEM.activityPointsPerClick;
    await this.updateDailyPoints(userId, pointsEarned, 0);

    return { success: true, points: pointsEarned };
  },

  // التحقق من النشاط التلقائي كل دقيقة
  async checkActivityStatus(userId: string): Promise<void> {
    const activityRef = doc(db, "activityStatus", userId);
    const activitySnap = await getDoc(activityRef);
    
    if (!activitySnap.exists()) return;

    const activityData = activitySnap.data() as ActivityStatus;
    const now = new Date();
    const lastCheckIn = new Date(activityData.lastCheckIn);
    const timeDiff = now.getTime() - lastCheckIn.getTime();
    const minutesDiff = timeDiff / (1000 * 60);

    if (minutesDiff > 10 && activityData.isCurrentlyActive) {
      // إيقاف النشاط بعد 10 دقائق بدون ضغط
      await updateDoc(activityRef, {
        isCurrentlyActive: false,
        lastActivityCheck: now.toISOString()
      });
    }
  },

  // تحديث النقاط اليومية
  async updateDailyPoints(userId: string, activityPoints: number, taskPoints: number): Promise<void> {
    const today = new Date().toISOString().split('T')[0];
    const pointsRef = doc(db, "pointsHistory", userId, "days", today);
    
    const pointsSnap = await getDoc(pointsRef);
    const activityData = await this.getActivityStatus(userId);

    if (pointsSnap.exists()) {
      const currentPoints = pointsSnap.data() as DailyPoints;
      await updateDoc(pointsRef, {
        activityPoints: currentPoints.activityPoints + activityPoints,
        taskPoints: currentPoints.taskPoints + taskPoints,
        totalPoints: currentPoints.totalPoints + activityPoints + taskPoints,
        checkinClicks: activityData?.checkinClickCount || 0,
        workMinutes: activityData?.activeMinutesToday || 0
      });
    } else {
      const newDailyPoints: DailyPoints = {
        date: today,
        userId,
        workMinutes: activityData?.activeMinutesToday || 0,
        activityPoints,
        taskPoints,
        totalPoints: activityPoints + taskPoints,
        checkinClicks: activityData?.checkinClickCount || 0,
        completedTasks: 0,
        attendancePoints: 0,
        attended: false
      };
      await setDoc(pointsRef, newDailyPoints);
    }
  },

  // الحصول على حالة النشاط
  async getActivityStatus(userId: string): Promise<ActivityStatus | null> {
    const activityRef = doc(db, "activityStatus", userId);
    const activitySnap = await getDoc(activityRef);
    return activitySnap.exists() ? activitySnap.data() as ActivityStatus : null;
  },

  // تفعيل/تعطيل زر التأكيد (للمدير)
  async toggleCheckInButton(userId: string, enabled: boolean): Promise<void> {
    const activityRef = doc(db, "activityStatus", userId);
    await updateDoc(activityRef, { checkInButtonEnabled: enabled });
  }
};

// --- خدمة نقاط المهام ---
export const taskPointsService = {
  // حساب نقاط المهمة بناءً على الوقت
  async calculateTaskPoints(taskId: string, startTime: string, endTime: string): Promise<number> {
    const start = new Date(startTime);
    const end = new Date(endTime);
    const timeDiff = end.getTime() - start.getTime();
    const minutesDiff = timeDiff / (1000 * 60);

    if (minutesDiff <= 30) {
      return DEFAULT_POINTS_SYSTEM.taskPointsFast;
    } else {
      return DEFAULT_POINTS_SYSTEM.taskPointsNormal;
    }
  },

  // تسجيل نقاط المهمة
  async recordTaskPoints(userId: string, points: number): Promise<void> {
    await activityService.updateDailyPoints(userId, 0, points);
    
    // تحديث عدد المهام المكتملة
    const today = new Date().toISOString().split('T')[0];
    const pointsRef = doc(db, "pointsHistory", userId, "days", today);
    const pointsSnap = await getDoc(pointsRef);
    
    if (pointsSnap.exists()) {
      const currentPoints = pointsSnap.data() as DailyPoints;
      await updateDoc(pointsRef, {
        completedTasks: (currentPoints.completedTasks || 0) + 1
      });
    }
  }
};

// --- خدمة سجل النقاط ---
export const pointsHistoryService = {
  // الحصول على سجل النقاط اليومي
  async getDailyPoints(userId: string, date: string): Promise<DailyPoints | null> {
    const pointsRef = doc(db, "pointsHistory", userId, "days", date);
    const pointsSnap = await getDoc(pointsRef);
    return pointsSnap.exists() ? pointsSnap.data() as DailyPoints : null;
  },

  // الحصول على تاريخ النقاط لفترة محددة
  async getPointsHistory(userId: string, startDate: string, endDate: string): Promise<DailyPoints[]> {
    const pointsCol = collection(db, "pointsHistory", userId, "days");
    const q = query(
      pointsCol,
      where("date", ">=", startDate),
      where("date", "<=", endDate)
    );
    
    const snapshot = await getDocs(q);
    return snapshot.docs.map(doc => doc.data() as DailyPoints);
  },

  // الاشتراك في تحديثات النقاط اليومية
  subscribeToDailyPoints(userId: string, callback: (points: DailyPoints | null) => void) {
    const today = new Date().toISOString().split('T')[0];
    const pointsRef = doc(db, "pointsHistory", userId, "days", today);
    
    return onSnapshot(pointsRef, (snapshot) => {
      callback(snapshot.exists() ? snapshot.data() as DailyPoints : null);
    });
  },

  // إدارة النقاط يدوياً (للمدير)
  async updatePointsManually(userId: string, date: string, updates: Partial<DailyPoints>): Promise<void> {
    const pointsRef = doc(db, "pointsHistory", userId, "days", date);
    const pointsSnap = await getDoc(pointsRef);
    
    if (pointsSnap.exists()) {
      const current = pointsSnap.data() as DailyPoints;
      const updatedPoints = {
        ...updates,
        totalPoints: (current.activityPoints + (updates.activityPoints || 0)) + 
                     (current.taskPoints + (updates.taskPoints || 0))
      };
      await updateDoc(pointsRef, updatedPoints);
    } else {
      const newPoints: DailyPoints = {
        date,
        userId,
        workMinutes: updates.workMinutes || 0,
        activityPoints: updates.activityPoints || 0,
        taskPoints: updates.taskPoints || 0,
        totalPoints: (updates.activityPoints || 0) + (updates.taskPoints || 0),
        checkinClicks: updates.checkinClicks || 0,
        completedTasks: updates.completedTasks || 0,
        attendancePoints: 0,
        attended: false
      };
      await setDoc(pointsRef, newPoints);
    }
  }
};