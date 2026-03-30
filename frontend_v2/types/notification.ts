
import { AppView } from './common';

export type NotificationType = 'shipment_created' | 'shipment_updated' | 'general';

export interface AppNotification {
    id: string;
    userId: string;
    title: string;
    message: string;
    type: NotificationType;
    targetId?: string;
    targetView?: AppView;
    isRead: boolean;
    createdAt: string;
}
