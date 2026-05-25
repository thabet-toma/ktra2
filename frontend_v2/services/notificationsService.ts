import {
    collection,
    query,
    where,
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
    // Subscribe to unread notifications for a user OR public notifications (all_managers)
    subscribeToNotifications: (userId: string, callback: (notifications: AppNotification[]) => void) => {
        // حماية: إذا لم يكن هناك معرف مستخدم، لا تقم بالاستعلام
        if (!userId) return () => { };

        const q = query(
            collection(db, COLLECTION_NAME),
            where("userId", "in", [userId, "all_managers"]),
            orderBy("createdAt", "desc"),
            limit(50)
        );

        return onSnapshot(q, {
            next: (snapshot) => {
                const notifications = snapshot.docs.map((doc) => ({
                    id: doc.id,
                    ...doc.data(),
                })) as AppNotification[];

                const uniqueNotifications = Array.from(new Map(notifications.map(item => [item.id, item])).values());

                callback(uniqueNotifications);
            },
            error: (error) => {
                console.error("Error fetching notifications:", error);
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
            console.error("Error adding notification:", error);
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
            console.error("Error marking notification as read:", error);
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
            console.error("Error marking all notifications as read:", error);
        }
    }
};