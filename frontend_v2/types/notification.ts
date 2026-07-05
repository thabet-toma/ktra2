
import { AppView } from './common';

export type NotificationType =
    | 'shipment_created'
    | 'shipment_updated'
    | 'shipment_arrival_soon'
    | 'customer_note_reminder'
    | 'general';

export interface AppNotification {
    id: string;
    userId: string;
    title: string;
    message: string;
    type: NotificationType;
    targetId?: string;
    targetView?: AppView;
    /** تبويب هدف داخل الوجهة (مثلاً «customer_notes» في بطاقة الزبون). */
    targetTab?: string;
    /** معرّف ثانوي (مثلاً معرّف الملاحظة) لتحديد العنصر داخل التبويب. */
    targetSecondaryId?: string;
    isRead: boolean;
    createdAt: string;
}
