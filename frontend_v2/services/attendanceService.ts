// services/attendanceService.ts
import { AttendanceSession, AttendanceRecord, DailyPoints } from '../types';
import { 
  collection, 
  doc, 
  setDoc, 
  getDoc, 
  getDocs, 
  updateDoc, 
  deleteDoc, 
  query, 
  where, 
  orderBy,
  onSnapshot,
  db
} from './sqlApiClient';

class AttendanceService {
  private activeSession: AttendanceSession | null = null;
  private sessionListeners: Set<(session: AttendanceSession | null) => void> = new Set();

  // بدء جلسة حضور جديدة
  async startAttendanceSession(managerId: string): Promise<AttendanceSession> {
    // إيقاف أي جلسة نشطة سابقة
    if (this.activeSession) {
      await this.endAttendanceSession(this.activeSession.id);
    }

    const now = new Date();
    const sessionId = crypto.randomUUID();
    
    const session: AttendanceSession = {
      id: sessionId,
      date: now.toISOString().split('T')[0],
      startTime: now.toISOString(),
      isActive: true,
      createdBy: managerId,
      attendees: []
    };

    // حفظ في Firebase
    await setDoc(doc(db, 'attendanceSessions', sessionId), session);

    // تعيين timeout لإنهاء الجلسة تلقائياً بعد 5 دقائق
    session.autoEndTimeout = setTimeout(() => {
      this.endAttendanceSession(sessionId);
    }, 5 * 60 * 1000); // 5 دقائق

    this.activeSession = session;
    this.notifySessionListeners();
    
    return session;
  }

  // إنهاء جلسة الحضور
  async endAttendanceSession(sessionId: string): Promise<void> {
    const sessionRef = doc(db, 'attendanceSessions', sessionId);
    const now = new Date().toISOString();

    await updateDoc(sessionRef, {
      isActive: false,
      endTime: now
    });

    if (this.activeSession?.id === sessionId) {
      if (this.activeSession.autoEndTimeout) {
        clearTimeout(this.activeSession.autoEndTimeout);
      }
      this.activeSession = null;
      this.notifySessionListeners();
    }
  }

  // تسجيل حضور موظف
async markAttendance(userId: string, sessionId: string): Promise<AttendanceRecord> {
  const sessionRef = doc(db, 'attendanceSessions', sessionId);
  const sessionDoc = await getDoc(sessionRef);
  
  if (!sessionDoc.exists()) {
    throw new Error('جلسة الحضور غير موجودة');
  }

  const session = sessionDoc.data() as AttendanceSession;
  
  if (!session.isActive) {
    throw new Error('جلسة الحضور منتهية');
  }

  // التحقق إذا كان الموظف قد سجل حضوره مسبقاً
  if (session.attendees.includes(userId)) {
    throw new Error('لقد سجلت حضورك مسبقاً');
  }

  // تحديث قائمة الحاضرين
  await updateDoc(sessionRef, {
    attendees: [...session.attendees, userId]
  });

  // إنشاء سجل الحضور
  const recordId = crypto.randomUUID();
  const record: AttendanceRecord = {
    id: recordId,
    userId,
    sessionId,
    date: session.date,
    attendedAt: new Date().toISOString(),
    points: 10, // 10 نقاط للحضور
    status: 'present'
  };

  await setDoc(doc(db, 'attendanceRecords', recordId), record);

  // 🔥 هذا هو الجزء المهم - تحديث نقاط الحضور
  await this.updateAttendancePoints(userId, session.date);

  return record;
}

private async updateAttendancePoints(userId: string, date: string, addPoints: boolean = true): Promise<void> {
  try {
    console.log('تحديث نقاط الحضور:', { userId, date, addPoints });
    
    const pointsRef = doc(db, "pointsHistory", userId, "days", date);
    const pointsSnap = await getDoc(pointsRef);
    
    const pointsChange = addPoints ? 10 : -10; // +10 أو -10
    
    if (pointsSnap.exists()) {
      const current = pointsSnap.data() as DailyPoints;
      console.log('النقاط الحالية قبل التحديث:', current);
      
      const currentAttendancePoints = current.attendancePoints || 0;
      const newAttendancePoints = Math.max(0, currentAttendancePoints + pointsChange);
      const newTotalPoints = Math.max(0, (current.totalPoints || 0) + pointsChange);
      
      await updateDoc(pointsRef, {
        attendancePoints: newAttendancePoints,
        totalPoints: newTotalPoints,
        attended: addPoints // إذا كنا نضيف نقاط = حاضر، إذا كنا نخصم = غائب
      });
      
      console.log('تم تحديث نقاط الحضور. النقاط بعد التحديث:', {
        attendancePoints: newAttendancePoints,
        totalPoints: newTotalPoints,
        attended: addPoints
      });
    } else if (addPoints) {
      // فقط ننشئ سجل جديد إذا كنا نضيف نقاط
      const newPoints: DailyPoints = {
        date,
        userId,
        workMinutes: 0,
        activityPoints: 0,
        taskPoints: 0,
        attendancePoints: 10,
        totalPoints: 10,
        checkinClicks: 0,
        completedTasks: 0,
        attended: true
      };
      await setDoc(pointsRef, newPoints);
      console.log('تم إنشاء سجل نقاط جديد مع نقاط الحضور');
    }
  } catch (error) {
    console.error('خطأ في تحديث نقاط الحضور:', error);
    throw error;
  }
}

  // تحديث نقاط اليوم
  private async updateDailyPoints(userId: string, date: string): Promise<void> {
    const pointsRef = doc(db, 'dailyPoints', `${userId}_${date}`);
    const pointsDoc = await getDoc(pointsRef);

    if (pointsDoc.exists()) {
      const currentPoints = pointsDoc.data() as DailyPoints;
      await updateDoc(pointsRef, {
        attendancePoints: 10,
        totalPoints: (currentPoints.taskPoints || 0) + (currentPoints.activityPoints || 0) + 10,
        attended: true
      });
    } else {
      const newPoints: DailyPoints = {
        date,
        userId,
        workMinutes: 0,
        activityPoints: 0,
        taskPoints: 0,
        attendancePoints: 10,
        totalPoints: 10,
        checkinClicks: 0,
        completedTasks: 0,
        attended: true
      };
      await setDoc(pointsRef, newPoints);
    }
  }

  // الحصول على الجلسة النشطة
  async getActiveSession(): Promise<AttendanceSession | null> {
    if (this.activeSession) return this.activeSession;

    const q = query(
      collection(db, 'attendanceSessions'),
      where('isActive', '==', true),
      orderBy('startTime', 'desc')
    );

    const snapshot = await getDocs(q);
    if (snapshot.empty) return null;

    this.activeSession = snapshot.docs[0].data() as AttendanceSession;
    return this.activeSession;
  }

  // الاشتراك في تحديثات الجلسة النشطة
  subscribeToActiveSession(callback: (session: AttendanceSession | null) => void) {
    this.sessionListeners.add(callback);
    
    // إرجاع دالة إلغاء الاشتراك
    return () => {
      this.sessionListeners.delete(callback);
    };
  }

  private notifySessionListeners() {
    this.sessionListeners.forEach(callback => {
      callback(this.activeSession);
    });
  }

  // الحصول على سجلات الحضور ليوم معين
async getAttendanceRecords(date: string): Promise<AttendanceRecord[]> {
  try {
    // جلب جميع السجلات ثم الفلترة محلياً (لا يحتاج index)
    const q = query(
      collection(db, 'attendanceRecords'),
      orderBy('attendedAt', 'desc')
    );

    const snapshot = await getDocs(q);
    const allRecords = snapshot.docs.map(doc => doc.data() as AttendanceRecord);
    
    // الفلترة محلياً حسب التاريخ
    const filteredRecords = allRecords.filter(record => record.date === date);
    
    return filteredRecords;
  } catch (error) {
    console.error('Error loading attendance records:', error);
    
    // Fallback: إرجاع مصفوفة فارغة في حالة الخطأ
    return [];
  }
}

  // الحصول على تقرير الحضور لفترة معينة
async getAttendanceReport(startDate: string, endDate: string): Promise<{ [userId: string]: number }> {
  try {
    const q = query(
      collection(db, 'attendanceRecords'),
      orderBy('date', 'desc')
    );

    const snapshot = await getDocs(q);
    const report: { [userId: string]: number } = {};

    snapshot.docs.forEach(doc => {
      const record = doc.data() as AttendanceRecord;
      
      // الفلترة محلياً حسب النطاق الزمني
      if (record.date >= startDate && record.date <= endDate) {
        if (!report[record.userId]) {
          report[record.userId] = 0;
        }
        report[record.userId]++;
      }
    });

    return report;
  } catch (error) {
    console.error('Error loading attendance report:', error);
    return {};
  }
}

  // التعديل اليدوي على الحضور
async updateAttendanceManually(
  userId: string, 
  date: string, 
  attended: boolean
): Promise<void> {
  try {
    console.log('تعديل الحضور يدوياً:', { userId, date, attended });
    
    if (attended) {
      // إنشاء سجل حضور يدوي وإضافة النقاط
      const recordId = crypto.randomUUID();
      const record: AttendanceRecord = {
        id: recordId,
        userId,
        sessionId: 'manual',
        date,
        attendedAt: new Date().toISOString(),
        points: 10,
        status: 'present'
      };

      await setDoc(doc(db, 'attendanceRecords', recordId), record);
      await this.updateAttendancePoints(userId, date, true); // true يعني إضافة نقاط
      
      console.log('تم تسجيل الحضور وإضافة 10 نقاط');
    } else {
      // 🔥 البحث عن سجلات الحضور لهذا اليوم وحذفها
      const q = query(
        collection(db, 'attendanceRecords'),
        where('userId', '==', userId),
        where('date', '==', date)
      );

      const snapshot = await getDocs(q);
      
      // حذف جميع سجلات الحضور لهذا اليوم
      const deletePromises = snapshot.docs.map(async (doc) => {
        await deleteDoc(doc.ref);
      });
      
      await Promise.all(deletePromises);
      
      // 🔥 خصم 10 نقاط من سجل النقاط
      await this.deductAttendancePoints(userId, date);
      
      console.log('تم إلغاء الحضور وخصم 10 نقاط');
    }
  } catch (error) {
    console.error('خطأ في التعديل اليدوي للحضور:', error);
    throw error;
  }
}

private async deductAttendancePoints(userId: string, date: string): Promise<void> {
  try {
    console.log('خصم نقاط الحضور للمستخدم:', userId, 'التاريخ:', date);
    
    const pointsRef = doc(db, "pointsHistory", userId, "days", date);
    const pointsSnap = await getDoc(pointsRef);
    
    if (pointsSnap.exists()) {
      const current = pointsSnap.data() as DailyPoints;
      console.log('النقاط قبل الخصم:', current);
      
      const currentAttendancePoints = current.attendancePoints || 0;
      const pointsToDeduct = Math.min(currentAttendancePoints, 10); // لا نخصم أكثر من 10
      
      const updatedAttendancePoints = currentAttendancePoints - pointsToDeduct;
      const updatedTotalPoints = (current.totalPoints || 0) - pointsToDeduct;
      
      await updateDoc(pointsRef, {
        attendancePoints: Math.max(0, updatedAttendancePoints), // لا تسمح بقيم سالبة
        totalPoints: Math.max(0, updatedTotalPoints), // لا تسمح بقيم سالبة
        attended: false
      });
      
      console.log('تم خصم نقاط الحضور. النقاط بعد الخصم:', {
        attendancePoints: Math.max(0, updatedAttendancePoints),
        totalPoints: Math.max(0, updatedTotalPoints)
      });
    } else {
      console.log('لا يوجد سجل نقاط لهذا اليوم، لا يوجد ما يتم خصمه');
      // إذا لم يكن هناك سجل، ننشئ سجل بدون نقاط حضور
      const newPoints: DailyPoints = {
        date,
        userId,
        workMinutes: 0,
        activityPoints: 0,
        taskPoints: 0,
        attendancePoints: 0,
        totalPoints: 0,
        checkinClicks: 0,
        completedTasks: 0,
        attended: false
      };
      await setDoc(pointsRef, newPoints);
    }
  } catch (error) {
    console.error('خطأ في خصم نقاط الحضور:', error);
    throw error;
  }
}

}

export const attendanceService = new AttendanceService();