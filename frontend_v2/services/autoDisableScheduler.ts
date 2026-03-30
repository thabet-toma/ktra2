// services/autoDisableScheduler.ts
import { activityService } from './firestoreService';
import { getDocs, collection, db } from './sqlApiClient';

class AutoDisableScheduler {
    private intervalId: NodeJS.Timeout | null = null;
    private isRunning: boolean = false;

    // بدء المجدول
    start() {
        if (this.isRunning) return;
        
        console.log('🚀 بدء مجدول التعطيل التلقائي...');
        this.isRunning = true;

        // التحقق كل دقيقة (60000 مللي ثانية)
        this.intervalId = setInterval(() => {
            this.checkGlobalDisableStatus();
        }, 60000);

        // التحقق فور البدء
        this.checkGlobalDisableStatus();
    }

    // إيقاف المجدول
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
        this.isRunning = false;
        console.log('⏹️ إيقاف مجدول التعطيل التلقائي');
    }

    // التحقق من حالة التعطيل العامة
    private async checkGlobalDisableStatus() {
        try {
            console.log('🕒 التحقق من التعطيل التلقائي...', new Date().toLocaleTimeString('ar-EG'));
            
            // التحقق من الإعدادات العامة وتطبيقها
            await activityService.checkAndApplyGlobalDisable();
            
            console.log('✅ تم التحقق من التعطيل التلقائي');
            
        } catch (error) {
            console.error('❌ خطأ في مجدول التعطيل التلقائي:', error);
        }
    }

    // التحقق من حالة المجدول
    getStatus() {
        return {
            isRunning: this.isRunning,
            nextCheck: this.intervalId ? 'نشط' : 'متوقف'
        };
    }

    // تشغيل يدوي للمدير
    async manualCheck() {
        console.log('🔧 تشغيل يدوي للتحقق من التعطيل...');
        await this.checkGlobalDisableStatus();
    }
}

export const autoDisableScheduler = new AutoDisableScheduler();