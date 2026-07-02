import {
  collection,
  getDocs,
  doc,
  getDoc,
  setDoc,
  updateDoc,
  onSnapshot,
  query,
  deleteDoc,
  where,
  orderBy,
  Timestamp,
  limit,
  getCountFromServer,
  QueryDocumentSnapshot,
  startAfter,
  addDoc,
  serverTimestamp,
  runTransaction,
  db,
} from "../../services/sqlApiClient";
import { 
  Task, 
  User, 
  TaskStatus, 
  Submission, 
  ActivityLog, 
  ActivityStatus, 
  DailyPoints, 
  PointsSystem, 
  GlobalDisableSettings, 
  Item, 
  Category, 
  Brand, 
  Invoice, 
  Supplier, 
  PriceOffer, 
  Deal, 
  DealStatus, 
  DealItem, 
  DealActivity, 
  DealPayment,
  CashBox,
  CashBoxTransaction,
  Currency
} from "../../types";
import { apiDelete, apiGetList, apiGetObject, apiPatchObject, apiPostObject } from "../../services/restApi";
import { tryPostPurchaseReceiptFromInvoice } from "../../services/invoiceAccountingBridge";
import { resolveTenantId } from "../../utils/tenantContext";

// --- Helper: Sanitize Data ---
export const removeUndefined = <T>(obj: T): T => {
  return JSON.parse(JSON.stringify(obj));
};

// --- About / Social Links Service ---
export const aboutLinksService = {
  subscribeToLinks: (callback: (links: any[]) => void) => {
    try {
      const q = query(collection(db, "aboutLinks"), orderBy("createdAt", "asc"));
      return onSnapshot(q, (snapshot) => {
        const items = snapshot.docs.map((d) => ({ ...(d.data() as any), id: d.id }));
        callback(items);
      });
    } catch (error) {
      // console suppressed
      return () => { };
    }
  },

  getLinks: async () => {
    const q = query(collection(db, "aboutLinks"), orderBy("createdAt", "asc"));
    const snap = await getDocs(q);
    return snap.docs.map((d) => ({ ...(d.data() as any), id: d.id }));
  },

  addLink: async (type: string, url: string) => {
    const ref = doc(collection(db, "aboutLinks"));
    const id = ref.id;
    const payload = {
      id,
      type,
      url,
      createdAt: new Date().toISOString(),
    };
    await setDoc(ref, payload);
    return id;
  },

  updateLink: async (id: string, updates: Partial<{ type: string; url: string }>) => {
    const ref = doc(db, "aboutLinks", id);
    await updateDoc(ref, updates as any);
  },

  deleteLink: async (id: string) => {
    await deleteDoc(doc(db, "aboutLinks", id));
  },
};

// --- Departments Service (Contact Us) ---
export interface Department {
  id: string;
  name: string;
  nameEn: string;
  managerTitle: string;
  managerName: string;
  email: string;
  whatsapp: string;
  iconType: 'shipping' | 'finance' | 'support' | 'it' | 'marketing' | 'logistics';
  createdAt?: string;
}

export const departmentsService = {
  subscribeToDepartments: (callback: (deps: Department[]) => void) => {
    try {
      const q = query(collection(db, "departments"), orderBy("createdAt", "asc"));
      return onSnapshot(q, (snapshot) => {
        const items = snapshot.docs.map((d) => ({ ...(d.data() as any), id: d.id }));
        callback(items);
      });
    } catch (error) {
      return () => { };
    }
  },

  getDepartments: async (): Promise<Department[]> => {
    try {
      const q = query(collection(db, "departments"), orderBy("createdAt", "asc"));
      const snap = await getDocs(q);
      return snap.docs.map((d) => ({ ...(d.data() as any), id: d.id }));
    } catch (error) {
      return [];
    }
  },

  addDepartment: async (dept: Omit<Department, "id">) => {
    const ref = doc(collection(db, "departments"));
    const id = ref.id;
    const payload = {
      ...dept,
      id,
      createdAt: new Date().toISOString(),
    };
    await setDoc(ref, payload);
    return id;
  },

  updateDepartment: async (id: string, updates: Partial<Department>) => {
    const ref = doc(db, "departments", id);
    await updateDoc(ref, updates as any);
  },

  deleteDepartment: async (id: string) => {
    await deleteDoc(doc(db, "departments", id));
  },
};

// إعدادات النظام الافتراضية
const DEFAULT_POINTS_SYSTEM: PointsSystem = {
  activityPointsPerClick: 1,
  taskPointsFast: 10,
  taskPointsNormal: 5,
  maxActivityPointsPerDay: 50
};

// --- نظام النقاط الذكي ---

// --- خدمة حالة النشاط ---
export const activityService = {
  // تهيئة حالة النشاط للمستخدم
  async initializeActivityStatus(userId: string): Promise<void> {
    const activityRef = doc(db, "activityStatus", userId);

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

  // التحقق من النشاط التلقائي
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

  // تحديث النقاط اليومية (محدثة لدعم نقاط الحضور)
  async updateDailyPoints(userId: string, activityPoints: number, taskPoints: number, attendancePoints: number = 0): Promise<void> {
    const today = new Date().toISOString().split('T')[0];
    const pointsRef = doc(db, "pointsHistory", userId, "days", today);

    const pointsSnap = await getDoc(pointsRef);
    const activityData = await this.getActivityStatus(userId);

    if (pointsSnap.exists()) {
      const currentPoints = pointsSnap.data() as DailyPoints;
      const newAttendancePoints = currentPoints.attendancePoints || 0;
      const totalPoints = currentPoints.totalPoints + activityPoints + taskPoints + attendancePoints;

      await updateDoc(pointsRef, {
        activityPoints: currentPoints.activityPoints + activityPoints,
        taskPoints: currentPoints.taskPoints + taskPoints,
        attendancePoints: newAttendancePoints + attendancePoints,
        totalPoints: totalPoints,
        checkinClicks: activityData?.checkinClickCount || 0,
        workMinutes: activityData?.activeMinutesToday || 0,
        attended: (currentPoints.attended || false) || (attendancePoints > 0) // تحديث حالة الحضور
      });
    } else {
      const newDailyPoints: DailyPoints = {
        date: today,
        userId,
        workMinutes: activityData?.activeMinutesToday || 0,
        activityPoints,
        taskPoints,
        attendancePoints: attendancePoints,
        totalPoints: activityPoints + taskPoints + attendancePoints,
        checkinClicks: activityData?.checkinClickCount || 0,
        completedTasks: 0,
        attended: attendancePoints > 0 // تعيين حالة الحضور
      };
      await setDoc(pointsRef, newDailyPoints);
    }
  },

  // إضافة نقاط الحضور (دالة جديدة)
  async addAttendancePoints(userId: string, date: string): Promise<void> {
    const attendancePoints = 10; // 10 نقاط للحضور
    await this.updateDailyPoints(userId, 0, 0, attendancePoints);
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

    // تحديث حقل المستخدم أيضاً للتوافق
    const userRef = doc(db, "users", userId);
    await updateDoc(userRef, { checkInButtonEnabled: enabled });
  },

  // الاشتراك في تحديثات حالة النشاط
  subscribeToActivityStatus(userId: string, callback: (status: ActivityStatus | null) => void) {
    const activityRef = doc(db, "activityStatus", userId);
    return onSnapshot(activityRef, (snapshot) => {
      callback(snapshot.exists() ? snapshot.data() as ActivityStatus : null);
    });
  },

  setDailyDisableSchedule: async (userId: string, startTime: string, endTime: string, isEnabled: boolean): Promise<void> => {
    const activityRef = doc(db, "activityStatus", userId);

    const updates = {
      dailyDisableStartTime: startTime,
      dailyDisableEndTime: endTime,
      dailyDisableEnabled: isEnabled,
      lastActivityCheck: new Date().toISOString()
    };

    await updateDoc(activityRef, updates);

    // إذا تم تعطيل النظام، قم بتعطيل زر التأكيد أيضاً
    if (isEnabled) {
      const now = new Date();
      const currentTime = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');

      if (activityService.isTimeInRange(currentTime, startTime, endTime)) {
        await updateDoc(activityRef, { checkInButtonEnabled: false });
      }
    }
  },

  // دالة للتحقق إذا كان الوقت الحالي ضمن نطاق التعطيل
  isTimeInRange: (currentTime: string, startTime: string, endTime: string): boolean => {
    const [currentHours, currentMinutes] = currentTime.split(':').map(Number);
    const [startHours, startMinutes] = startTime.split(':').map(Number);
    const [endHours, endMinutes] = endTime.split(':').map(Number);

    const currentTotal = currentHours * 60 + currentMinutes;
    const startTotal = startHours * 60 + startMinutes;
    const endTotal = endHours * 60 + endMinutes;

    return currentTotal >= startTotal && currentTotal <= endTotal;
  },

  // دالة للتحقق من حالة التعطيل اليومي وتطبيقها
  checkDailyDisableStatus: async (userId: string): Promise<void> => {
    const activityRef = doc(db, "activityStatus", userId);
    const activitySnap = await getDoc(activityRef);

    if (!activitySnap.exists()) return;

    const activityData = activitySnap.data() as ActivityStatus;

    // إذا كان التعطيل اليومي مفعل
    if (activityData.dailyDisableEnabled && activityData.dailyDisableStartTime && activityData.dailyDisableEndTime) {
      const now = new Date();
      const currentTime = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');

      const isInDisabledRange = activityService.isTimeInRange(
        currentTime,
        activityData.dailyDisableStartTime,
        activityData.dailyDisableEndTime
      );

      // تحديث حالة زر التأكيد بناءً على الوقت
      if (activityData.checkInButtonEnabled === isInDisabledRange) {
        await updateDoc(activityRef, {
          checkInButtonEnabled: !isInDisabledRange,
          lastActivityCheck: now.toISOString()
        });
      }
    }
  },

  // دالة لتطبيق التعطيل اليومي على جميع الموظفين
  applyDailyDisableToAllEmployees: async (users: User[]): Promise<void> => {
    const now = new Date();
    const currentTime = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');

    const employees = users.filter(user => user.role === 'employee');

    for (const employee of employees) {
      const activityRef = doc(db, "activityStatus", employee.id);
      const activitySnap = await getDoc(activityRef);

      if (activitySnap.exists()) {
        const activityData = activitySnap.data() as ActivityStatus;

        // إذا كان التعطيل اليومي مفعل لهذا الموظف
        if (activityData.dailyDisableEnabled && activityData.dailyDisableStartTime && activityData.dailyDisableEndTime) {

          const isInDisabledRange = activityService.isTimeInRange(
            currentTime,
            activityData.dailyDisableStartTime,
            activityData.dailyDisableEndTime
          );

          // تحديث حالة زر التأكيد
          if (activityData.checkInButtonEnabled === isInDisabledRange) {
            await updateDoc(activityRef, {
              checkInButtonEnabled: !isInDisabledRange,
              lastActivityCheck: now.toISOString()
            });
          }
        }
      }
    }
  },

  // في services/firestoreService.ts - أضف هذه الدوال لـ activityService

  // داخل activityService object:

  // الحصول على الإعدادات العامة
  getGlobalDailyDisableSchedule: async (): Promise<GlobalDisableSettings | null> => {
    try {
      const settingsRef = doc(db, "systemSettings", "globalDailyDisable");
      const settingsSnap = await getDoc(settingsRef);

      if (settingsSnap.exists()) {
        return settingsSnap.data() as GlobalDisableSettings;
      } else {
        // إرجاع إعدادات افتراضية إذا لم تكن موجودة
        const defaultSettings: GlobalDisableSettings = {
          startTime: '00:00',
          endTime: '00:00',
          isEnabled: false
        };
        return defaultSettings;
      }
    } catch (error) {
      // console suppressed
      return null;
    }
  },

  // حفظ الإعدادات العامة
  // في services/firestoreService.ts - أصلح دالة setGlobalDailyDisableSchedule
  setGlobalDailyDisableSchedule: async (startTime: string, endTime: string, isEnabled: boolean, updatedBy?: string): Promise<void> => {
    const settingsRef = doc(db, "systemSettings", "globalDailyDisable");

    // إنشاء كائن الإعدادات بدون الحقول undefined
    const settings: any = {
      startTime,
      endTime,
      isEnabled,
      lastUpdatedAt: new Date().toISOString()
    };

    // إضافة lastUpdatedBy فقط إذا كانت موجودة
    if (updatedBy) {
      settings.lastUpdatedBy = updatedBy;
    }

    await setDoc(settingsRef, settings);

    // تطبيق الإعدادات العامة على جميع الموظفين فوراً
    if (isEnabled) {
      await activityService.applyGlobalDisableToAllEmployees();
    } else {
      // إذا تم تعطيل الإعدادات العامة، تفعيل جميع الأزرار
      await activityService.enableAllCheckInButtons();
    }
  },

  // تطبيق الإعدادات العامة على جميع الموظفين
  // في activityService - أصلح هذه الدالة
  applyGlobalDisableToAllEmployees: async (): Promise<void> => {
    try {
      const globalSettings = await activityService.getGlobalDailyDisableSchedule();
      if (!globalSettings || !globalSettings.isEnabled) {
        return;
      }

      const now = new Date();
      const currentTime = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');

      const isInDisabledRange = activityService.isTimeInRange(
        currentTime,
        globalSettings.startTime,
        globalSettings.endTime
      );
      // جلب جميع المستخدمين
      const usersSnapshot = await getDocs(collection(db, "users"));
      const employees = usersSnapshot.docs
        .map(doc => doc.data() as User)
        .filter(user => user.role === 'employee');

      let updatedCount = 0;

      for (const employee of employees) {
        const activityRef = doc(db, "activityStatus", employee.id);
        const activitySnap = await getDoc(activityRef);

        if (activitySnap.exists()) {
          const activityData = activitySnap.data() as ActivityStatus;

          // إذا كان الموظف لا يستخدم إعدادات فردية، نطبق الإعدادات العامة
          const shouldUseGlobalSettings = !activityData.dailyDisableEnabled;

          if (shouldUseGlobalSettings) {
            // تحديث حالة زر التأكيد بناءً على الإعدادات العامة
            if (activityData.checkInButtonEnabled === isInDisabledRange) {
              await updateDoc(activityRef, {
                checkInButtonEnabled: !isInDisabledRange,
                useGlobalSettings: true,
                lastActivityCheck: now.toISOString()
              });
              updatedCount++;
            }
          }
        } else {
          // إذا لم يكن هناك سجل نشاط، إنشائه مع الإعدادات العامة
          const newActivity: ActivityStatus = {
            userId: employee.id,
            lastCheckIn: now.toISOString(),
            activeMinutesToday: 0,
            checkinClickCount: 0,
            isCurrentlyActive: false,
            checkInButtonEnabled: !isInDisabledRange,
            lastActivityCheck: now.toISOString(),
            useGlobalSettings: true
          };
          await setDoc(activityRef, newActivity);
          updatedCount++;
        }
      }
    } catch (error) {
      // console suppressed
    }
  },

  // تفعيل جميع أزرار التأكيد
  enableAllCheckInButtons: async (): Promise<void> => {
    try {
      const usersSnapshot = await getDocs(collection(db, "users"));
      const employees = usersSnapshot.docs
        .map(doc => doc.data() as User)
        .filter(user => user.role === 'employee');

      for (const employee of employees) {
        const activityRef = doc(db, "activityStatus", employee.id);
        const activitySnap = await getDoc(activityRef);

        if (activitySnap.exists()) {
          const activityData = activitySnap.data() as ActivityStatus;

          // إذا كان الموظف يستخدم الإعدادات العامة فقط، نفعّل الزر
          if (activityData.useGlobalSettings && !activityData.dailyDisableEnabled) {
            await updateDoc(activityRef, {
              checkInButtonEnabled: true,
              lastActivityCheck: new Date().toISOString()
            });
          }
        }
      }
    } catch (error) {
      // console suppressed
    }
  },

  // التحقق من الإعدادات العامة وتطبيقها (تستخدم في المجدول)
  // في activityService - تأكد من هذه الدالة
  checkAndApplyGlobalDisable: async (): Promise<void> => {
    try {
      const globalSettings = await activityService.getGlobalDailyDisableSchedule();

      if (globalSettings && globalSettings.isEnabled) {
        console.log('🌍 تطبيق الإعدادات العامة...', {
          time: new Date().toLocaleTimeString('ar-EG'),
          settings: globalSettings
        });

        await activityService.applyGlobalDisableToAllEmployees();
      }
    } catch (error) {
      // console suppressed
    }
  },

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

  // تسجيل نقاط المهمة (محدثة)
  async recordTaskPoints(userIds: string[], points: number): Promise<void> {
    // توزيع النقاط على جميع الموظفين المعينين
    const pointsPerUser = Math.floor(points / userIds.length);

    for (const userId of userIds) {
      await activityService.updateDailyPoints(userId, 0, pointsPerUser, 0);

      // تحديث عدد المهام المكتملة لكل موظف
      const today = new Date().toISOString().split('T')[0];
      const pointsRef = doc(db, "pointsHistory", userId, "days", today);
      const pointsSnap = await getDoc(pointsRef);

      if (pointsSnap.exists()) {
        const currentPoints = pointsSnap.data() as DailyPoints;
        await updateDoc(pointsRef, {
          completedTasks: (currentPoints.completedTasks || 0) + 1
        });
      } else {
        // إذا لم يكن هناك سجل لهذا اليوم، إنشائه
        const newDailyPoints: DailyPoints = {
          date: today,
          userId,
          workMinutes: 0,
          activityPoints: 0,
          taskPoints: pointsPerUser,
          attendancePoints: 0,
          totalPoints: pointsPerUser,
          checkinClicks: 0,
          completedTasks: 1,
          attended: false
        };
        await setDoc(pointsRef, newDailyPoints);
      }
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

  // إدارة النقاط يدوياً (للمدير) - محدثة لدعم نقاط الحضور
  async updatePointsManually(userId: string, date: string, updates: Partial<DailyPoints>): Promise<void> {
    const pointsRef = doc(db, "pointsHistory", userId, "days", date);
    const pointsSnap = await getDoc(pointsRef);

    if (pointsSnap.exists()) {
      const current = pointsSnap.data() as DailyPoints;

      // حساب الإجمالي مع مراعاة جميع أنواع النقاط
      const newActivityPoints = updates.activityPoints !== undefined ? updates.activityPoints : current.activityPoints;
      const newTaskPoints = updates.taskPoints !== undefined ? updates.taskPoints : current.taskPoints;
      const newAttendancePoints = updates.attendancePoints !== undefined ? updates.attendancePoints : current.attendancePoints;

      const updatedPoints = {
        ...current,
        ...updates,
        totalPoints: newActivityPoints + newTaskPoints + newAttendancePoints
      };

      await updateDoc(pointsRef, updatedPoints);
    } else {
      const newPoints: DailyPoints = {
        date,
        userId,
        workMinutes: updates.workMinutes || 0,
        activityPoints: updates.activityPoints || 0,
        taskPoints: updates.taskPoints || 0,
        attendancePoints: updates.attendancePoints || 0,
        totalPoints: (updates.activityPoints || 0) +
          (updates.taskPoints || 0) +
          (updates.attendancePoints || 0),
        checkinClicks: updates.checkinClicks || 0,
        completedTasks: updates.completedTasks || 0,
        attended: updates.attended || false
      };
      await setDoc(pointsRef, newPoints);
    }
  },

  // إضافة نقاط الحضور يدوياً (دالة جديدة)
  async addManualAttendancePoints(userId: string, date: string): Promise<void> {
    const pointsRef = doc(db, "pointsHistory", userId, "days", date);
    const pointsSnap = await getDoc(pointsRef);

    const attendancePoints = 10; // 10 نقاط للحضور

    if (pointsSnap.exists()) {
      const current = pointsSnap.data() as DailyPoints;
      await updateDoc(pointsRef, {
        attendancePoints: (current.attendancePoints || 0) + attendancePoints,
        totalPoints: (current.totalPoints || 0) + attendancePoints,
        attended: true
      });
    } else {
      const newPoints: DailyPoints = {
        date,
        userId,
        workMinutes: 0,
        activityPoints: 0,
        taskPoints: 0,
        attendancePoints: attendancePoints,
        totalPoints: attendancePoints,
        checkinClicks: 0,
        completedTasks: 0,
        attended: true
      };
      await setDoc(pointsRef, newPoints);
    }
  },

  // إزالة نقاط الحضور يدوياً (دالة جديدة)
  async removeAttendancePoints(userId: string, date: string): Promise<void> {
    const pointsRef = doc(db, "pointsHistory", userId, "days", date);
    const pointsSnap = await getDoc(pointsRef);

    if (pointsSnap.exists()) {
      const current = pointsSnap.data() as DailyPoints;
      const currentAttendancePoints = current.attendancePoints || 0;

      await updateDoc(pointsRef, {
        attendancePoints: 0,
        totalPoints: (current.totalPoints || 0) - currentAttendancePoints,
        attended: false
      });
    }
  }
};

export const getCategories = async (): Promise<Category[]> => {
  try {
    const categoriesRef = collection(db, "categories");
    const snapshot = await getDocs(categoriesRef);
    return snapshot.docs.map(doc => ({
      id: doc.id,
      ...doc.data()
    } as Category));
  } catch (error) {
    // console suppressed
    return [];
  }
};

// دالة الاشتراك في تحديثات الفئات
export const subscribeToCategories = (callback: (categories: Category[]) => void) => {
  const categoriesRef = collection(db, "categories");

  return onSnapshot(categoriesRef, (snapshot) => {
    const categories = snapshot.docs.map(doc => ({
      id: doc.id,
      ...doc.data()
    } as Category));
    callback(categories);
  });
};

// --- Brands Service ---
export const brandsService = {
  getBrands: async (): Promise<Brand[]> => {
    try {
      const brandsRef = collection(db, "brands");
      const snapshot = await getDocs(brandsRef);
      return snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      } as Brand));
    } catch (error) {
      // console suppressed
      return [];
    }
  },

  subscribeToBrands: (callback: (brands: Brand[]) => void) => {
    const brandsRef = collection(db, "brands");
    return onSnapshot(brandsRef, (snapshot) => {
      const brands = snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      } as Brand));
      callback(brands);
    });
  },

  addBrand: async (brand: Brand) => {
    const brandRef = doc(db, "brands", brand.id);
    await setDoc(brandRef, brand);
  },

  deleteBrand: async (brandId: string) => {
    const brandRef = doc(db, "brands", brandId);
    await deleteDoc(brandRef);
  }
};

// --- Public Gallery Helpers ---
export interface GalleryItem {
  id: string;
  url: string;
  description?: string;
  createdAt: string;
}

export const createGalleryItem = async (item: Omit<GalleryItem, 'id'>) => {
  const id = crypto.randomUUID();
  const ref = doc(db, 'publicGallery', id);
  await setDoc(ref, { id, ...item });
  return { id, ...item } as GalleryItem;
};

export const getGalleryCount = async () => {
  const col = collection(db, 'publicGallery');
  const snapshot = await getCountFromServer(col);
  return snapshot.data().count;
};

export const getGalleryChunk = async (lastVisible: QueryDocumentSnapshot | null, pageSize: number = 20) => {
  const col = collection(db, 'publicGallery');
  
  let q;
  if (lastVisible) {
    // جلب الصفحة التالية بعد آخر مستند
    q = query(col, orderBy('createdAt', 'desc'), startAfter(lastVisible), limit(pageSize));
  } else {
    // جلب الصفحة الأولى
    q = query(col, orderBy('createdAt', 'desc'), limit(pageSize));
  }

  const snapshot = await getDocs(q);
  const items = snapshot.docs.map(d => d.data() as GalleryItem);
  const lastDoc = snapshot.docs[snapshot.docs.length - 1]; // نحتفظ بآخر مستند للصفحة التالية
  
  return { items, lastDoc };
};

// --- Finance Module Services ---

// Cash Box Service
export const cashBoxesService = {
  // Get all cash boxes
  getCashBoxes: async (): Promise<CashBox[]> => {
    try {
      const q = query(collection(db, "cashBoxes"), orderBy("createdAt", "asc"));
      const snapshot = await getDocs(q);
      return snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      } as CashBox));
    } catch (error) {
      // console suppressed
      return [];
    }
  },

  // Subscribe to cash boxes updates
  subscribeToCashBoxes: (callback: (cashBoxes: CashBox[]) => void) => {
    const q = query(collection(db, "cashBoxes"), orderBy("createdAt", "asc"));
    return onSnapshot(q, (snapshot) => {
      const cashBoxes = snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      } as CashBox));
      callback(cashBoxes);
    });
  },

  // Create a new cash box — يعيد معرف المستند لربطه بحساب GL
  createCashBox: async (
    cashBoxData: Omit<CashBox, "id" | "currentBalance" | "createdAt" | "updatedAt">
  ): Promise<string> => {
    const newCashBoxRef = doc(collection(db, "cashBoxes"));
    const now = new Date().toISOString();

    const newCashBox: CashBox = {
      id: newCashBoxRef.id,
      ...cashBoxData,
      currentBalance: 0,
      createdAt: now,
      updatedAt: now,
    };

    await setDoc(newCashBoxRef, newCashBox);
    return newCashBoxRef.id;
  },
  
  // Delete a cash box (only if empty/manager - validation logic should be in UI or Security Rules)
  deleteCashBox: async (id: string): Promise<void> => {
    await deleteDoc(doc(db, "cashBoxes", id));
  },

  updateCashBox: async (
    id: string,
    data: Partial<Pick<CashBox, "name" | "currency">>
  ): Promise<void> => {
    const ref = doc(db, "cashBoxes", id);
    const payload: Record<string, unknown> = {
      updatedAt: new Date().toISOString(),
    };
    if (data.name != null) payload.name = data.name.trim();
    if (data.currency != null) payload.currency = data.currency;
    await updateDoc(ref, payload);
  },
};

// Cash Box Transactions Service
export const cashBoxTransactionsService = {
  // Get transactions for a specific cash box
  getTransactions: async (cashBoxId: string, limitCount: number = 50): Promise<CashBoxTransaction[]> => {
    try {
      const q = query(
        collection(db, "cashBoxTransactions"), 
        where("cashBoxId", "==", cashBoxId),
        orderBy("date", "desc"),
        orderBy("createdAt", "desc"),
        limit(limitCount)
      );
      const snapshot = await getDocs(q);
      return snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      } as CashBoxTransaction));
    } catch (error) {
      // console suppressed
      return [];
    }
  },

  // Subscribe to transactions
  subscribeToTransactions: (cashBoxId: string, callback: (transactions: CashBoxTransaction[]) => void, limitCount: number = 50) => {
    const q = query(
      collection(db, "cashBoxTransactions"), 
      where("cashBoxId", "==", cashBoxId),
      orderBy("date", "desc"),
      orderBy("createdAt", "desc"),
      limit(limitCount)
    );
    return onSnapshot(q, (snapshot) => {
      const transactions = snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      } as CashBoxTransaction));
      callback(transactions);
    });
  },

  // Add a new transaction and update cash box balance atomically
  addTransaction: async (
    transactionData: Omit<CashBoxTransaction, "id" | "createdAt" | "balanceAfter">
  ): Promise<string> => {
    const cashBoxRef = doc(db, "cashBoxes", transactionData.cashBoxId);
    const transactionRef = doc(collection(db, "cashBoxTransactions"));

    await runTransaction(db, async (transaction) => {
      const cashBoxDoc = await transaction.get(cashBoxRef);
      if (!cashBoxDoc.exists()) {
        throw new Error("Cash Box does not exist!");
      }

      const cashBox = cashBoxDoc.data() as CashBox;
      
      // Calculate new balance
      let newBalance = cashBox.currentBalance;
      if (transactionData.type === 'deposit') {
        newBalance += transactionData.amount;
      } else if (transactionData.type === 'withdrawal') {
        newBalance -= transactionData.amount;
      } else if (transactionData.type === 'adjustment') {
        // Adjustments might be positive or negative, assuming amount is signed or handling type specific logic
        // For simplicity, let's assume 'adjustment' updates the balance by the amount (signed) or we treat it like deposit/withdrawal
        // If the user enters a negative amount for adjustment, it decreases. 
        // Let's stick to Requirements: logic says "Deposits increase", "Withdrawals decrease". Adjustment not strictly defined but usually signed.
        // Assuming user passes signed amount for adjustment or we handle it. 
        // Let's assume adjustment amount is what we ADD to the balance (can be negative).
        newBalance += transactionData.amount;
      }

      const now = new Date().toISOString();
      const newTransaction: CashBoxTransaction = {
        id: transactionRef.id,
        ...transactionData,
        createdAt: now,
        balanceAfter: newBalance
      };

      // Update Cash Box
      transaction.update(cashBoxRef, {
        currentBalance: newBalance,
        updatedAt: now
      });

      // Create Transaction
      transaction.set(transactionRef, newTransaction);
    });
    return transactionRef.id;
  },
};


export const fetchGalleryItems = async (): Promise<GalleryItem[]> => {
  const col = collection(db, 'publicGallery');
  const q = query(col, orderBy('createdAt', 'desc'));
  const snap = await getDocs(q);
  return snap.docs.map(d => d.data() as GalleryItem);
};

export const subscribeToGallery = (callback: (items: GalleryItem[]) => void) => {
  const col = collection(db, 'publicGallery');
  const q = query(col, orderBy('createdAt', 'desc'));
  return onSnapshot(q, (snapshot) => {
    const items = snapshot.docs.map(d => d.data() as GalleryItem);
    callback(items);
  });
};

// --- خدمة الحضور ---
export const attendanceService = {
  // تسجيل حضور موظف وإضافة النقاط
  async recordAttendance(userId: string, date: string): Promise<void> {
    // إضافة نقاط الحضور عبر خدمة النقاط
    await pointsHistoryService.addManualAttendancePoints(userId, date);

    // أيضاً تحديث عبر خدمة النشاط للتوافق
    await activityService.addAttendancePoints(userId, date);
  },

  // إلغاء حضور موظف وإزالة النقاط
  async cancelAttendance(userId: string, date: string): Promise<void> {
    await pointsHistoryService.removeAttendancePoints(userId, date);
  },

  // التحقق من حضور موظف في تاريخ معين
  async checkAttendance(userId: string, date: string): Promise<boolean> {
    const points = await pointsHistoryService.getDailyPoints(userId, date);
    return points?.attended || false;
  }
};

// --- Users Service ---
export const seedUsersIfEmpty = async () => {
};

export const updateUserInDb = async (user: Partial<User> & { id: string }) => {
  const userRef = doc(db, "users", user.id);
  await updateDoc(userRef, { ...user });
};

export const deleteUserFromDb = async (userId: string) => {
  // حذف السجلات المرتبطة
  const activityRef = doc(db, "activityStatus", userId);
  await deleteDoc(activityRef).catch(() => { }); // تجاهل الخطأ إذا لم يكن موجود

  const userRef = doc(db, "users", userId);
  await deleteDoc(userRef);
};

export const subscribeToUsers = (callback: (users: User[]) => void) => {
  const q = query(collection(db, "users"));
  return onSnapshot(q, (snapshot) => {
    const users = snapshot.docs.map(doc => doc.data() as User);
    callback(users);
  });
};

// --- Tasks Service ---
export const createTaskInDb = async (task: Task) => {
  const taskRef = doc(db, "tasks", task.id);
  const safeTask = removeUndefined(task);
  await setDoc(taskRef, safeTask);
};

export const updateTaskInDb = async (task: Task) => {
  const taskRef = doc(db, "tasks", task.id);
  const updateData = { ...task, updatedAt: new Date().toISOString() };

  if (updateData.workStartTime === undefined) updateData.workStartTime = null;

  const safeUpdateData = removeUndefined(updateData);
  await updateDoc(taskRef, safeUpdateData);

  // تحديث نقاط المهمة إذا اكتملت
  if (task.status === 'COMPLETED' && task.workStartTime && task.completedAt) {
    const points = await taskPointsService.calculateTaskPoints(
      task.id,
      task.workStartTime,
      task.completedAt
    );
    // تمرير مصفوفة الموظفين المعينين
    await taskPointsService.recordTaskPoints(task.assignedTo, points);
  }
};

export const updateTaskFieldsInDb = async (taskId: string, fields: Partial<Task>) => {
  const taskRef = doc(db, "tasks", taskId);
  const updates = { ...fields, updatedAt: new Date().toISOString() };
  await updateDoc(taskRef, removeUndefined(updates));

  // إذا كانت الحالة اكتملت، حساب النقاط
  if (fields.status === 'COMPLETED') {
    const taskSnap = await getDoc(taskRef);
    if (taskSnap.exists()) {
      const task = taskSnap.data() as Task;
      if (task.workStartTime && task.completedAt) {
        const points = await taskPointsService.calculateTaskPoints(
          taskId,
          task.workStartTime,
          task.completedAt
        );
        // تمرير مصفوفة الموظفين المعينين
        await taskPointsService.recordTaskPoints(task.assignedTo, points);
      }
    }
  }
};

export const updateUserTaskStatus = async (taskId: string, userId: string, status: any) => {
  const taskRef = doc(db, "tasks", taskId);

  const updateData = {
    [`userStatuses.${userId}`]: {
      ...status,
      updatedAt: new Date().toISOString()
    },
    updatedAt: new Date().toISOString()
  };

  await updateDoc(taskRef, updateData);
};

export const startUserTask = async (taskId: string, userId: string) => {
  const userStatus = {
    status: 'in_progress',
    startedAt: new Date().toISOString(),
    currentWorkTime: 0
  };

  await updateUserTaskStatus(taskId, userId, userStatus);
};

export const submitUserTask = async (taskId: string, userId: string) => {
  const userStatus = {
    status: 'submitted',
    submittedAt: new Date().toISOString()
  };

  await updateUserTaskStatus(taskId, userId, userStatus);
};

// --- Submission Helpers ---
export const addSubmissionToTaskInDb = async (taskId: string, newSubmission: Submission, newLog: ActivityLog) => {
  const taskRef = doc(db, "tasks", taskId);
  const taskSnap = await getDoc(taskRef);

  if (taskSnap.exists()) {
    const taskData = taskSnap.data() as Task;

    const safeSubmission = removeUndefined(newSubmission);
    const safeLog = removeUndefined(newLog);

    // إضافة التسليم الجديد إلى القائمة (بدون حذف القديمة)
    const updatedSubmissions = [safeSubmission, ...(taskData.submissions || [])];
    const updatedLogs = [...(taskData.logs || []), safeLog];

    await updateDoc(taskRef, {
      status: 'WAITING_FOR_REVIEW', // حالة المهمة العامة
      submissions: updatedSubmissions,
      logs: updatedLogs,
      updatedAt: new Date().toISOString()
    });
  } else {
    throw new Error("Task not found");
  }
};

export const updateSubmissionInTaskInDb = async (
  taskId: string,
  submissionId: string,
  updates: Partial<Submission>,
  newLog: ActivityLog
) => {
  const taskRef = doc(db, "tasks", taskId);
  const taskSnap = await getDoc(taskRef);

  if (taskSnap.exists()) {
    const taskData = taskSnap.data() as Task;

    const safeUpdates = removeUndefined(updates);
    const safeLog = removeUndefined(newLog);

    const updatedSubmissions = (taskData.submissions || []).map(s =>
      s.id === submissionId ? { ...s, ...safeUpdates, updatedAt: new Date().toISOString() } : s
    );
    const updatedLogs = [...(taskData.logs || []), safeLog];

    await updateDoc(taskRef, {
      submissions: updatedSubmissions,
      logs: updatedLogs,
      updatedAt: new Date().toISOString()
    });
  }
};

export const subscribeToTasks = (callback: (tasks: Task[]) => void) => {
  const q = query(collection(db, "tasks"));
  return onSnapshot(q, (snapshot) => {
    const tasks = snapshot.docs.map(doc => doc.data() as Task);
    callback(tasks);
  });
};

// --- Procurement Services ---

// Items Service
export const itemsService = {
  _mapProductToItem: (p: any): Item => {
    const attach = Array.isArray(p.attachments) ? p.attachments : [];
    const urls = attach.map((a: any) => a.file_path).filter(Boolean);
    return {
      id: String(p.id),
      name: p.display_name || p.name_ar || p.name_en || p.sku || `Item ${p.id}`,
      modelNumber: p.sku || "",
      categoryId: p.category ? String(p.category) : "",
      categoryName: p.category_name || "",
      subCategoryId: "",
      subCategoryName: "",
      brandId: "",
      brandName: "",
      imageUrls: urls.length ? urls : ["", "", ""],
      hsCodePrimary: p.hs_code || "",
      hsCodeAlternative: "",
      quantity: p.min_stock_level || 0,
      specifications: p.online_description || "",
      notes: "",
      isActive: Boolean(p.is_for_sale_online),
      salePrice: Number(p.online_price || 0),
      storeName: p.name_ar || p.name_en || "",
      storeDescription: p.online_description || "",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    } as Item;
  },

  _mapItemToProductPayload: (item: Partial<Item>) => ({
    sku: item.modelNumber || item.id || `SKU-${Date.now()}`,
    name_ar: item.name || item.storeName || "منتج",
    name_en: item.name || item.storeName || "Product",
    category: item.categoryId && /^\d+$/.test(String(item.categoryId)) ? Number(item.categoryId) : null,
    hs_code: item.hsCodePrimary || "",
    min_stock_level: Number(item.quantity || 0),
    is_for_sale_online: Boolean(item.isActive),
    online_price: Number(item.salePrice || 0),
    online_description: item.storeDescription || item.specifications || "",
    image_url: (item.imageUrls || []).find((u: string) => !!u) || null,
  }),

  getItemById: async (itemId: string): Promise<Item | null> => {
    try {
      const p = await apiGetObject<any>(`inventory/products/${itemId}/`, { tenantId: resolveTenantId() });
      return itemsService._mapProductToItem(p);
    } catch {
      return null;
    }
  },

  checkItemHsCodeUnique: async (hsCode: string, excludeItemId?: string): Promise<boolean> => {
    if (!hsCode) return true;
    try {
      const all = await apiGetList<any>("inventory/products/", { tenantId: resolveTenantId() });
      return !all.some((p: any) => String(p.id) !== String(excludeItemId || "") && (p.hs_code || "") === hsCode);
    } catch {
      return true;
    }
  },

  subscribeToItems: (callback: (items: Item[]) => void) => {
    let alive = true;
    const load = async () => {
      try {
        const products = await apiGetList<any>("inventory/products/", { tenantId: resolveTenantId() });
        if (alive) callback(products.map((p: any) => itemsService._mapProductToItem(p)));
      } catch {
        if (alive) callback([]);
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  },

  subscribeToActiveItems: (callback: (items: Item[]) => void) => {
    return itemsService.subscribeToItems((all) => callback(all.filter((i) => i.isActive)));
  },

  addItemToDb: async (item: Item) => {
    await apiPostObject("inventory/products/", itemsService._mapItemToProductPayload(item), { tenantId: resolveTenantId() });
  },

  updateItemInDb: async (item: Item) => {
    await apiPatchObject(`inventory/products/${item.id}/`, itemsService._mapItemToProductPayload(item), { tenantId: resolveTenantId() });
  },

  deleteItemFromDb: async (itemId: string) => {
    await apiDelete(`inventory/products/${itemId}/`, { tenantId: resolveTenantId() });
  },
};

// Categories Service
export const categoriesService = {
  subscribeToCategories: (callback: (categories: Category[]) => void) => {
    const q = query(collection(db, "categories"));
    return onSnapshot(q, (snapshot) => {
      const categories = snapshot.docs.map(
        (docSnap) =>
          ({
            id: docSnap.id,
            ...docSnap.data(),
          }) as Category
      );
      callback(categories);
    });
  },

  addCategoryToDb: async (category: Category) => {
    const categoryRef = doc(db, "categories", category.id);
    await setDoc(categoryRef, removeUndefined(category));
  },

  updateCategoryInDb: async (category: Category) => {
    const categoryRef = doc(db, "categories", category.id);
    await updateDoc(categoryRef, removeUndefined(category) as Record<string, any>);
  },

  deleteCategoryFromDb: async (categoryId: string) => {
    const categoryRef = doc(db, "categories", categoryId);
    await deleteDoc(categoryRef);
  }
};

// Invoices Service
export const invoicesService = {
  subscribeToInvoices: (callback: (invoices: Invoice[]) => void) => {
    // ترتيب حسب الرقم التسلسلي تنازلياً
    const q = query(collection(db, "invoices"), orderBy("createdAt", "desc"));
    return onSnapshot(q, (snapshot) => {
      const invoices = snapshot.docs.map(doc => doc.data() as Invoice);
      callback(invoices);
    });
  },

  getNextInvoiceNumber: async (): Promise<string> => {
    try {
      // 1. جلب آخر فاتورة تم إنشاؤها
      const q = query(collection(db, "invoices"), orderBy("createdAt", "desc"), limit(1));
      const snapshot = await getDocs(q);

      if (snapshot.empty) {
        return "i-0001"; // أول رقم في حال عدم وجود فواتير
      }

      const lastInvoice = snapshot.docs[0].data() as Invoice;
      const lastNumberString = lastInvoice.invoiceNumber; // مثال: "i-0001"
      
      // إذا لم يكن هناك رقم فاتورة (تراثي)، نبدأ من جديد أو نتجاوز
      if (!lastNumberString || !lastNumberString.startsWith('i-')) {
         return "i-0001";
      }

      // 2. استخراج الرقم وزيادته
      const parts = lastNumberString.split('-');
      if (parts.length === 2 && !isNaN(parseInt(parts[1]))) {
        const nextNumber = parseInt(parts[1]) + 1;
        // تنسيق الرقم الجديد ليكون 4 خانات (0006)
        return `i-${nextNumber.toString().padStart(4, '0')}`;
      }

      return `i-${Date.now().toString().slice(-4)}`;
      
    } catch (error) {
      // console suppressed
      return "i-0001";
    }
  },

  addInvoiceToDb: async (invoice: Omit<Invoice, 'serialNumber'>) => {
    // 1. توليد رقم الفاتورة إذا لم يكن موجوداً
    let invoiceNumber = invoice.invoiceNumber;
    if (!invoiceNumber) {
        invoiceNumber = await invoicesService.getNextInvoiceNumber();
    }

    // 2. تجهيز البيانات
    const invoiceRef = doc(db, "invoices", invoice.id);
    const newInvoice: any = {
      ...invoice,
      invoiceNumber,
      // serialNumber لم يعد ضرورياً للعرض ولكن قد نحتاجه للتوافق، يمكننا استخدام نفس الرقم
      serialNumber: invoiceNumber.replace('i-', ''),
    };

    // دالة مساعدة لحذف الـ undefined
    const removeUndefined = (obj: any) => JSON.parse(JSON.stringify(obj));

    await setDoc(invoiceRef, removeUndefined(newInvoice));

    try {
      const jid = await tryPostPurchaseReceiptFromInvoice(newInvoice as Invoice);
      if (jid != null) {
        await updateDoc(invoiceRef, { glPurchaseReceiptJournalId: jid });
      }
    } catch (e) {
      // console suppressed
    }
  },

  updateInvoiceInDb: async (invoice: Invoice) => {
    if (invoice.isHistorical) {
      console.warn("Cannot update historical invoice");
      // throw new Error("لا يمكن تعديل الفواتير المؤرشفة (Historical)");
      // سنسمح بالتحديث الآن ولكن يمكننا إظهار تحذير في الواجهة
    }

    const invoiceRef = doc(db, "invoices", invoice.id);
    // دالة مساعدة لحذف الـ undefined
    const removeUndefined = (obj: any) => JSON.parse(JSON.stringify(obj));
    await updateDoc(invoiceRef, removeUndefined(invoice) as Record<string, any>);

    try {
      const jid = await tryPostPurchaseReceiptFromInvoice(invoice);
      if (jid != null) {
        await updateDoc(invoiceRef, { glPurchaseReceiptJournalId: jid });
      }
    } catch (e) {
      // console suppressed
    }
  },

  deleteInvoiceFromDb: async (invoiceId: string) => {
    const invoiceRef = doc(db, "invoices", invoiceId);
    await deleteDoc(invoiceRef);
  }
};

// Suppliers Service
export const suppliersService = {
  _mapSupplierTypeToPartnerType: (supplierType?: string): string => {
    const t = String(supplierType || "").toLowerCase();
    if (t === "shipping_agent") return "FreightForwarder";
    if (t === "service_provider") return "CustomsBroker";
    if (t === "local_company") return "LocalTransporter";
    if (t === "international_trader") return "Supplier";
    if (t === "factory") return "Supplier";
    return "Supplier";
  },
  _mapPartnerTypeToSupplierType: (partnerType?: string): any => {
    const t = String(partnerType || "").toLowerCase();
    if (t === "supplier") return "factory";
    if (t === "freightforwarder") return "shipping_agent";
    if (t === "customsbroker") return "service_provider";
    if (t === "localtransporter") return "local_company";
    if (t === "customer") return "local_company";
    return "factory";
  },
  _mapPartnerToSupplier: (p: any): Supplier => {
    const name =
      p?.name ||
      p?.trade_name ||
      p?.tradeName ||
      p?.partner_name ||
      p?.partnerName ||
      `Supplier ${p?.id ?? ""}`;
    const legalName = p?.legal_name || p?.legalName || p?.LegalName || "";
    const displayName = legalName || name;
    const alias =
      p?.alias ||
      p?.Alias ||
      p?.nickname ||
      p?.display_name ||
      p?.displayName ||
      p?.legal_name ||
      p?.legalName ||
      p?.LegalName ||
      "";
    return {
      id: String(p?.id ?? ""),
      tradeName: displayName,
      alias,
      phone: p?.phone || "",
      mobile: p?.mobile || "",
      street: p?.street || p?.address || "",
      city: p?.city || "",
      region: p?.region || "",
      postalCode: p?.postal_code || "",
      country: p?.country || "",
      supplierId: String(p?.id ?? ""),
      currency: p?.currency || "USD",
      openingBalance: Number(p?.opening_balance || 0),
      balanceDate: p?.balance_date || "",
      email: p?.email || "",
      notes: p?.notes || "",
      logoUrl: String(
        p?.image_path ||
          p?.logo_url ||
          p?.logoUrl ||
          (Array.isArray(p?.attachments) && p.attachments[0]?.file_path) ||
          ""
      ).trim(),
      salesRepName: p?.sales_rep_name || "",
      salesRepWechat: p?.sales_rep_wechat || "",
      salesRepPhone: p?.sales_rep_phone || "",
      type: suppliersService._mapPartnerTypeToSupplierType(p?.partner_type),
      createdAt: p?.created_at || new Date().toISOString(),
      updatedAt: p?.updated_at || p?.created_at || new Date().toISOString(),
    };
  },

  checkSupplierUniqueness: async (
    data: { email?: string; phone?: string; mobile?: string },
    currentSupplierId?: string
  ): Promise<{ isUnique: boolean; field?: string; existingName?: string }> => {
    try {
      const all = await apiGetList<any>("partners/", { tenantId: resolveTenantId() });
      if (data.email?.trim()) {
        const d = all.find((x) => String(x.id) !== String(currentSupplierId) && (x.email || "").trim() === data.email!.trim());
        if (d) return { isUnique: false, field: "email", existingName: d.name };
      }
      if (data.phone?.trim()) {
        const d = all.find((x) => String(x.id) !== String(currentSupplierId) && (x.phone || "").trim() === data.phone!.trim());
        if (d) return { isUnique: false, field: "phone", existingName: d.name };
      }
      if (data.mobile?.trim()) {
        const d = all.find((x) => String(x.id) !== String(currentSupplierId) && (x.mobile || "").trim() === data.mobile!.trim());
        if (d) return { isUnique: false, field: "mobile", existingName: d.name };
      }

      return { isUnique: true };
    } catch (error) {
      // console suppressed
      return { isUnique: true };
    }
  },
  
  subscribeToSuppliers: (callback: (suppliers: Supplier[]) => void) => {
    let alive = true;
    const load = async () => {
      try {
        const partners = await apiGetList<any>("partners/", { tenantId: resolveTenantId() });
        let mapped = partners.map((p: any) => suppliersService._mapPartnerToSupplier(p));

        // Fallback: if partners list is empty but deals exist, synthesize supplier list from deals.
        if (mapped.length === 0) {
              const deals = await apiGetList<any>("logistics/deals/", { tenantId: resolveTenantId() });
          const byName = new Map<string, Supplier>();
          deals.forEach((d: any) => {
            const rawPartner = d?.partner;
            const partnerId =
              typeof rawPartner === "object" && rawPartner !== null ? String(rawPartner.id || "") : String(d?.partner || "");
            const legalName =
              (typeof rawPartner === "object" ? (rawPartner?.legal_name || rawPartner?.legalName || rawPartner?.alias) : "") || "";
            const partnerName = legalName || d?.partner_name || (typeof rawPartner === "object" ? rawPartner?.name : "") || d?.factory_name || "";
            if (!partnerName) return;
            const key = partnerId || partnerName;
            if (!byName.has(key)) {
              byName.set(key, {
                id: partnerId || `virtual-${partnerName}`,
                tradeName: partnerName,
                alias: legalName || "",
                supplierId: partnerId || partnerName,
                currency: "USD",
                openingBalance: 0,
                type: "factory",
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString(),
              } as Supplier);
            }
          });
          mapped = Array.from(byName.values());
        }

        if (alive) callback(mapped);
      } catch (e) {
        // console suppressed
        try {
          const deals = await apiGetList<any>("logistics/deals/", { tenantId: resolveTenantId() });
          const byName = new Map<string, Supplier>();
          deals.forEach((d: any) => {
            const rawPartner = d?.partner;
            const partnerId =
              typeof rawPartner === "object" && rawPartner !== null ? rawPartner.id : rawPartner;
            const legalName =
              typeof rawPartner === "object" && rawPartner !== null
                ? (rawPartner.legal_name || rawPartner.legalName || rawPartner.alias || "")
                : "";
            const partnerName =
              legalName ||
              d?.partner_name ||
              (typeof rawPartner === "object" ? rawPartner?.name : "") ||
              d?.factory_name ||
              "";
            if (!partnerName) return;
            const key = String(partnerId || partnerName);
            if (!byName.has(key)) {
              byName.set(key, {
                id: String(partnerId || `virtual-${partnerName}`),
                tradeName: partnerName,
                alias: legalName || "",
                supplierId: String(partnerId || partnerName),
                currency: "USD",
                openingBalance: 0,
                type: "factory",
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString(),
              } as Supplier);
            }
          });
          if (alive) callback(Array.from(byName.values()));
        } catch (e2) {
          // console suppressed
          if (alive) callback([]);
        }
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  },

  // تم التعديل: إنشاء رقم مورد تسلسلي تلقائياً
  addSupplierToDb: async (supplier: Omit<Supplier, 'id' | 'createdAt' | 'updatedAt' | 'supplierId'>): Promise<Supplier> => {
    const payload = {
      name: supplier.tradeName,
      alias: supplier.alias || "",
      email: supplier.email || "",
      phone: supplier.phone || "",
      mobile: supplier.mobile || "",
      address: supplier.street || "",
      notes: supplier.notes || "",
      partner_type: suppliersService._mapSupplierTypeToPartnerType(supplier.type),
      is_active: true,
    };
    const created = await apiPostObject<any>("partners/", payload, { tenantId: resolveTenantId() });
    return suppliersService._mapPartnerToSupplier(created);
  },

  updateSupplierInDb: async (supplier: Supplier) => {
    await apiPatchObject(`partners/${supplier.id}/`, {
      name: supplier.tradeName,
      alias: supplier.alias || "",
      email: supplier.email || "",
      phone: supplier.phone || "",
      mobile: supplier.mobile || "",
      address: supplier.street || "",
      notes: supplier.notes || "",
      partner_type: suppliersService._mapSupplierTypeToPartnerType(supplier.type),
    }, { tenantId: resolveTenantId() });
  },

  deleteSupplierFromDb: async (supplierId: string) => {
    await apiDelete(`partners/${supplierId}/`, { tenantId: resolveTenantId() });
  },

  getSupplierById: async (supplierId: string): Promise<Supplier | null> => {
    try {
      const row = await apiGetObject<any>(`partners/${supplierId}/`, { tenantId: resolveTenantId() });
      return suppliersService._mapPartnerToSupplier(row);
    } catch {
      return null;
    }
  },

  fetchAllSuppliers: async (): Promise<Supplier[]> => {
    const partners = await apiGetList<any>("partners/", { tenantId: resolveTenantId() });
    return partners.map((p: any) => suppliersService._mapPartnerToSupplier(p));
  },

  getSuppliersFromDb: async (): Promise<Supplier[]> => {
    const partners = await apiGetList<any>("partners/", { tenantId: resolveTenantId() });
    return partners.map((p: any) => suppliersService._mapPartnerToSupplier(p));
  },

  migrateSuppliersType: async () => {
    return;
  }
};

// shippingMethodsService removed
// --- Price Offers Service ---
export const priceOffersService = {
  subscribeToPriceOffers: (callback: (offers: PriceOffer[]) => void) => {
    const q = query(collection(db, "price_offers"), orderBy("createdAt", "desc"));
    return onSnapshot(q, (snapshot) => {
      const offers = snapshot.docs.map(doc => doc.data() as PriceOffer);
      callback(offers);
    });
  },

  addPriceOfferToDb: async (offer: PriceOffer) => {
    const offerRef = doc(db, "price_offers", offer.id);
    await setDoc(offerRef, removeUndefined(offer));
  },


 updatePriceOfferInDb: async (offer: PriceOffer) => {
    // تنظيف البيانات قبل التحديث
    const cleanOffer = {
      ...offer,
      internalNotes: offer.internalNotes || '',
      // إزالة statusNotes إذا كان موجوداً
      statusNotes: undefined
    };
    
    const offerRef = doc(db, "price_offers", offer.id);
    await updateDoc(offerRef, removeUndefined(cleanOffer) as any);
  },

  deletePriceOfferFromDb: async (offerId: string) => {
    const offerRef = doc(db, "price_offers", offerId);
    await deleteDoc(offerRef);
  },

  getPriceOfferById: async (offerId: string): Promise<PriceOffer | null> => {
    const offerRef = doc(db, "price_offers", offerId);
    const snap = await getDoc(offerRef);
    return snap.exists() ? (snap.data() as PriceOffer) : null;
  },

  // --- الدالة التي كانت ناقصة ---
  getNextOfferNumber: async (): Promise<string> => {
    try {
      // 1. جلب آخر عرض سعر تم إنشاؤه
      const q = query(collection(db, "price_offers"), orderBy("createdAt", "desc"), limit(1));
      const snapshot = await getDocs(q);

      if (snapshot.empty) {
        return "OFF-0001"; // أول رقم في حال عدم وجود عروض
      }

      const lastOffer = snapshot.docs[0].data() as PriceOffer;
      const lastNumberString = lastOffer.offerNumber; // مثال: "OFF-0005"

      // 2. استخراج الرقم وزيادته
      const parts = lastNumberString.split('-');
      if (parts.length === 2 && !isNaN(parseInt(parts[1]))) {
        const nextNumber = parseInt(parts[1]) + 1;
        // تنسيق الرقم الجديد ليكون 4 خانات (0006)
        return `OFF-${nextNumber.toString().padStart(4, '0')}`;
      }

      // في حال كان التنسيق القديم مختلفاً، نبدأ تسلسل جديد أو نستخدم fallback
      return `OFF-${Date.now().toString().slice(-4)}`;
      
    } catch (error) {
      // console suppressed
      return "OFF-0001";
    }
  }
};

// export const dealsService = {
//   // الاشتراك في الصفقات
//   subscribeToDeals: (callback: (deals: Deal[]) => void) => {
//     const q = query(collection(db, "deals"), orderBy("createdAt", "desc"));
//     return onSnapshot(q, (snapshot) => {
//       const deals = snapshot.docs.map(doc => ({
//         id: doc.id,
//         ...doc.data(),
//         createdAt: doc.data().createdAt?.toDate().toISOString(),
//         updatedAt: doc.data().updatedAt?.toDate().toISOString()
//       } as Deal));
//       callback(deals);
//     });
//   },

//   // إنشاء سجل نشاط جديد
//   async addActivity(dealId: string, activity: Omit<DealActivity, 'id' | 'timestamp'>): Promise<void> {
//     try {
//       const activityRef = collection(db, 'deals', dealId, 'activities');
//       await addDoc(activityRef, {
//         ...activity,
//         timestamp: serverTimestamp()
//       });
//     } catch (error) {
//       console.error('Error adding activity:', error);
//       throw error;
//     }
//   },

//   // تسجيل تغيير الحالة مع النشاط
//   async updateDealStatus(
//     dealId: string, 
//     newStatus: DealStatus, 
//     userId: string, 
//     userName: string, 
//     userRole: string,
//     notes?: string
//   ): Promise<void> {
//     try {
//       const dealRef = doc(db, 'deals', dealId);
//       const statusHistory = {
//         status: newStatus,
//         timestamp: new Date().toISOString(),
//         changedBy: userId,
//         notes
//       };

//       // تسجيل النشاط
//       await this.addActivity(dealId, {
//         type: 'status_change',
//         action: 'تغيير حالة الصفقة',
//         details: `تم تغيير حالة الصفقة إلى: ${newStatus}${notes ? ` - ${notes}` : ''}`,
//         userId,
//         userName,
//         userRole,
//         metadata: { oldStatus: null, newStatus } // سنضيف الحالة القديمة لاحقاً
//       });

//       await updateDoc(dealRef, {
//         status: newStatus,
//         statusHistory: [...(await this.getDeal(dealId)).statusHistory || [], statusHistory],
//         updatedAt: serverTimestamp(),
//         updatedBy: userId
//       });
//     } catch (error) {
//       console.error('Error updating deal status:', error);
//       throw error;
//     }
//   },

//   // إضافة دفعة جديدة
//   async addPayment(
//     dealId: string,
//     payment: Omit<DealPayment, 'id'>,
//     userId: string,
//     userName: string,
//     userRole: string
//   ): Promise<string> {
//     try {
//       const dealRef = doc(db, 'deals', dealId);
//       const deal = await this.getDeal(dealId);
      
//       const paymentId = crypto.randomUUID();
//       const newPayment: DealPayment = {
//         ...payment,
//         id: paymentId
//       };

//       const updatedPayments = [...(deal.payments || []), newPayment];
      
//       // حساب المبلغ المتبقي
//       const totalPaid = updatedPayments.reduce((sum, p) => sum + p.amount, 0);
//       const remainingAmount = deal.totalAmount - totalPaid;

//       // تحديث حالة الصفقة تلقائياً
//       let newStatus: DealStatus = deal.status;
//       if (payment.type === 'first' && !payment.confirmedBySupplier) {
//         newStatus = 'first_payment_done';
//       } else if (payment.type === 'first' && payment.confirmedBySupplier) {
//         newStatus = 'first_payment_confirmed';
//       } else if (payment.type === 'second' && !payment.confirmedBySupplier) {
//         newStatus = 'second_payment_done';
//       } else if (payment.type === 'second' && payment.confirmedBySupplier) {
//         newStatus = 'second_payment_confirmed';
//       }

//       // تسجيل النشاط
//       await this.addActivity(dealId, {
//         type: 'payment',
//         action: 'إضافة دفعة',
//         details: `تم إضافة ${payment.type === 'first' ? 'الدفعة الأولى' : 'الدفعة الثانية'} بمبلغ ${payment.amount}$`,
//         userId,
//         userName,
//         userRole,
//         metadata: { paymentId, amount: payment.amount, type: payment.type }
//       });

//       await updateDoc(dealRef, {
//         payments: updatedPayments,
//         remainingAmount,
//         status: newStatus,
//         updatedAt: serverTimestamp(),
//         updatedBy: userId
//       });

//       return paymentId;
//     } catch (error) {
//       console.error('Error adding payment:', error);
//       throw error;
//     }
//   },

//   // تأكيد الدفعة من المورد
//   async confirmPayment(
//     dealId: string,
//     paymentId: string,
//     userId: string,
//     userName: string,
//     userRole: string,
//     confirmationImage?: string,
//     notes?: string
//   ): Promise<void> {
//     try {
//       const dealRef = doc(db, 'deals', dealId);
//       const deal = await this.getDeal(dealId);
      
//       const updatedPayments = (deal.payments || []).map(payment => {
//         if (payment.id === paymentId) {
//           return {
//             ...payment,
//             confirmedBySupplier: true,
//             confirmedAt: new Date().toISOString(),
//             confirmedBy: userId,
//             supplierConfirmationImage: confirmationImage,
//             supplierNotes: notes
//           };
//         }
//         return payment;
//       });

//       // تحديث حالة الصفقة تلقائياً
//       const payment = updatedPayments.find(p => p.id === paymentId);
//       let newStatus: DealStatus = deal.status;
      
//       if (payment?.type === 'first') {
//         newStatus = 'first_payment_confirmed';
//       } else if (payment?.type === 'second') {
//         newStatus = 'second_payment_confirmed';
        
//         // إذا كانت الدفعة الثانية مؤكدة، تنتقل تلقائياً إلى تجهيز الشحن
//         if (deal.status === 'production_completed') {
//           newStatus = 'shipping_preparation';
//         }
//       }

//       // تسجيل النشاط
//       await this.addActivity(dealId, {
//         type: 'payment',
//         action: 'تأكيد دفعة من المورد',
//         details: `تم تأكيد ${payment?.type === 'first' ? 'الدفعة الأولى' : 'الدفعة الثانية'} من المورد`,
//         userId,
//         userName,
//         userRole,
//         metadata: { paymentId }
//       });

//       await updateDoc(dealRef, {
//         payments: updatedPayments,
//         status: newStatus,
//         updatedAt: serverTimestamp(),
//         updatedBy: userId
//       });
//     } catch (error) {
//       console.error('Error confirming payment:', error);
//       throw error;
//     }
//   },

//   // إنشاء صفقة جديدة مع السجلات
//   async createDeal(
//     dealData: Omit<Deal, 'id' | 'createdAt' | 'updatedAt' | 'statusHistory' | 'activityLog'>,
//     userId: string,
//     userName: string,
//     userRole: string
//   ): Promise<string> {
//     try {
//       const dealNumber = await this.getNextDealNumber();
      
//       const newDeal: Partial<Deal> = {
//         ...dealData,
//         dealNumber,
//         status: 'initial',
//         payments: [],
//         statusHistory: [{
//           status: 'initial',
//           timestamp: new Date().toISOString(),
//           notes: 'تم إنشاء الصفقة',
//           changedBy: userId
//         }],
//         activityLog: [],
//         createdBy: userId,
//         createdAt: serverTimestamp(),
//         updatedAt: serverTimestamp(),
//         updatedBy: userId
//       };

//       const docRef = await addDoc(collection(db, 'deals'), newDeal);
      
//       // تسجيل النشاط
//       await this.addActivity(docRef.id, {
//         type: 'status_change',
//         action: 'إنشاء صفقة',
//         details: `تم إنشاء الصفقة ${dealNumber}`,
//         userId,
//         userName,
//         userRole,
//         metadata: { dealNumber }
//       });

//       return docRef.id;
//     } catch (error) {
//       console.error('Error creating deal:', error);
//       throw error;
//     }
//   },

//   // تحديث الصفقة مع تسجيل النشاط
//   async updateDeal(
//     dealId: string,
//     updates: Partial<Deal>,
//     userId: string,
//     userName: string,
//     userRole: string,
//     action: string,
//     details?: string
//   ): Promise<void> {
//     try {
//       const dealRef = doc(db, 'deals', dealId);
      
//       // تسجيل النشاط إذا كان هناك تغيير مهم
//       if (action) {
//         await this.addActivity(dealId, {
//           type: 'item_update',
//           action,
//           details,
//           userId,
//           userName,
//           userRole,
//           metadata: { updates }
//         });
//       }

//       await updateDoc(dealRef, {
//         ...updates,
//         updatedAt: serverTimestamp(),
//         updatedBy: userId
//       });
//     } catch (error) {
//       console.error('Error updating deal:', error);
//       throw error;
//     }
//   },

//   // الحصول على الصفقة
//   async getDeal(dealId: string): Promise<Deal> {
//     const dealDoc = await getDoc(doc(db, 'deals', dealId));
//     if (!dealDoc.exists()) {
//       throw new Error('Deal not found');
//     }
    
//     return {
//       id: dealDoc.id,
//       ...dealDoc.data(),
//       createdAt: dealDoc.data().createdAt?.toDate().toISOString(),
//       updatedAt: dealDoc.data().updatedAt?.toDate().toISOString()
//     } as Deal;
//   },

//   // الحصول على سجل النشاطات
//   async getDealActivities(dealId: string): Promise<DealActivity[]> {
//     const activitiesRef = collection(db, 'deals', dealId, 'activities');
//     const snapshot = await getDocs(query(activitiesRef, orderBy('timestamp', 'desc')));
    
//     return snapshot.docs.map(doc => ({
//       id: doc.id,
//       ...doc.data(),
//       timestamp: doc.data().timestamp?.toDate().toISOString()
//     } as DealActivity));
//   },

//   // توليد رقم الصفقة التالي (نفس الدالة السابقة)
//   async getNextDealNumber(): Promise<string> {
//     const q = query(collection(db, "deals"), orderBy("createdAt", "desc"), limit(1));
//     const snapshot = await getDocs(q);

//     if (snapshot.empty) return "D-0001";

//     const lastDeal = snapshot.docs[0].data() as Deal;
//     const lastNumberMatch = lastDeal.dealNumber?.match(/D-(\d+)/);
    
//     if (!lastNumberMatch) return "D-0001";
    
//     const lastNumber = parseInt(lastNumberMatch[1]);
//     return `D-${(lastNumber + 1).toString().padStart(4, '0')}`;
//   }
// };