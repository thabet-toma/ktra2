// services/activeTasksService.ts
class ActiveTasksService {
  private activeTasks: Map<string, any> = new Map();
  private updateCallbacks: Set<(taskId: string, userId: string, time: number) => void> = new Set();
  private intervalId: number | null = null;

  constructor() {
    this.startGlobalTimer();
  }

  private startGlobalTimer() {
    if (this.intervalId) return;

    this.intervalId = window.setInterval(() => {
      const now = Date.now();
      
      this.activeTasks.forEach((activeTask, key) => {
        const [taskId, userId] = key.split('_');
        const elapsed = now - activeTask.startTime;
        const totalTime = activeTask.totalAccumulated + elapsed;
        
        // إخطار جميع المشتركين بالتحديث - بدون قسمة على 1000
        this.updateCallbacks.forEach(callback => {
          callback(taskId, userId, totalTime); // إزالة Math.floor(totalTime / 1000)
        });
      });
    }, 1000);
  }

  startTask(taskId: string, userId: string, accumulatedTime: number = 0) {
    const key = `${taskId}_${userId}`;
    
    this.activeTasks.set(key, {
      taskId,
      userId,
      startTime: Date.now(),
      totalAccumulated: accumulatedTime
    });
  }

  stopTask(taskId: string, userId: string): number {
    const key = `${taskId}_${userId}`;
    const activeTask = this.activeTasks.get(key);
    
    if (activeTask) {
      const now = Date.now();
      const elapsed = now - activeTask.startTime;
      const totalTime = activeTask.totalAccumulated + elapsed;
      
      this.activeTasks.delete(key);
      return totalTime; // إرجاع الوقت بالمللي ثانية
    }
    
    return 0;
  }

  getCurrentTime(taskId: string, userId: string): number {
    const key = `${taskId}_${userId}`;
    const activeTask = this.activeTasks.get(key);
    
    if (activeTask) {
      const now = Date.now();
      const elapsed = now - activeTask.startTime;
      return activeTask.totalAccumulated + elapsed; // إرجاع الوقت بالمللي ثانية (بدون قسمة)
    }
    
    return 0;
  }

  subscribeToTimeUpdates(callback: (taskId: string, userId: string, time: number) => void) {
    this.updateCallbacks.add(callback);
    
    return () => {
      this.updateCallbacks.delete(callback);
    };
  }

  isTaskActive(taskId: string, userId: string): boolean {
    const key = `${taskId}_${userId}`;
    return this.activeTasks.has(key);
  }

  getUserActiveTasks(userId: string): string[] {
    const userTasks: string[] = [];
    
    this.activeTasks.forEach((activeTask, key) => {
      const [taskId, taskUserId] = key.split('_');
      if (taskUserId === userId) {
        userTasks.push(taskId);
      }
    });
    
    return userTasks;
  }
}

export const activeTasksService = new ActiveTasksService();