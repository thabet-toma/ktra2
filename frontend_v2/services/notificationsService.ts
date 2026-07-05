import {
    collection,
    query,
    onSnapshot,
    addDoc,
    updateDoc,
    doc,
    orderBy,
    limit,
    serverTimestamp,
    Timestamp,
    db
} from "./sqlApiClient";
import { AppNotification } from "../types";

const COLLECTION_NAME = "notifications";

export const notificationsService = {
    // Subscribe to notifications for a user OR public broadcasts (all_managers).
    subscribeToNotifications: (userId: string, callback: (notifications: AppNotification[]) => void) => {
        // حماية: إذا لم يكن هناك معرف مستخدم، لا تقم بالاستعلام
        if (!userId) return () => { };

        // ملاحظة: شِمّ الـ mapper لا يدعم فلتر «in». نجلب إشعارات الشركة (منطاقة
        // بالـ tenant خادمياً) ونفلتر محلياً لهذا المستخدم أو البث العام — كان
        // فلتر userId__in يُنتج userId__exact=«a,b» فلا يطابق شيئاً ⇒ لا تظهر إشعارات.
        const q = query(
            collection(db, COLLECTION_NAME),
            orderBy("createdAt", "desc"),
            limit(50)
        );

        return onSnapshot(q, {
            next: (snapshot) => {
                const notifications = snapshot.docs.map((doc) => ({
                    id: doc.id,
                    ...doc.data(),
                })) as AppNotification[];

                const mine = notifications.filter(
                    (n) => n.userId === userId || n.userId === "all_managers"
                );
                const uniqueNotifications = Array.from(new Map(mine.map(item => [item.id, item])).values());

                callback(uniqueNotifications);
            },
            error: (error) => {
                // console suppressed
            },
        });
    },

    // Add a new notification
    addNotification: async (notification: Omit<AppNotification, "id" | "createdAt" | "isRead">) => {
        try {
            await addDoc(collection(db, COLLECTION_NAME), {
                ...notification,
                isRead: false,
                createdAt: new Date().toISOString(),
            });
        } catch (error) {
            // console suppressed
        }
    },

    // Mark a notification as read
    markAsRead: async (notificationId: string) => {
        try {
            const docRef = doc(db, COLLECTION_NAME, notificationId);
            await updateDoc(docRef, {
                isRead: true,
            });
        } catch (error) {
            // console suppressed
        }
    },

    // Mark all as read
    markAllAsRead: async (userId: string, notificationIds: string[]) => {
        try {
            const promises = notificationIds.map(id =>
                updateDoc(doc(db, COLLECTION_NAME, id), { isRead: true })
            );
            await Promise.all(promises);
        } catch (error) {
            // console suppressed
        }
    }
};