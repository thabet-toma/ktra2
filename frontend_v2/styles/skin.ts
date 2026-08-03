import { uiLog } from '../utils/uiLog';

export type UiSkin = 'aseel' | 'modern';

const UI_SKIN_KEY = 'ktra.uiSkin';
/** M6: الافتراضي صار الجلد الحديث. الكلاسيكي «الأصيل» يبقى خياراً كاملاً
 *  في الإعدادات (شبكة أمان لإصدار على الأقل — لا تُحذف كتلته من index.css). */
const DEFAULT_SKIN: UiSkin = 'modern';

const isUiSkin = (value: string | null): value is UiSkin =>
    value === 'aseel' || value === 'modern';

export const getSkin = (): UiSkin => {
    try {
        const storedSkin = localStorage.getItem(UI_SKIN_KEY);
        return isUiSkin(storedSkin) ? storedSkin : DEFAULT_SKIN;
    } catch (error) {
        uiLog.warn('تعذرت قراءة مظهر الواجهة من التخزين المحلي.', error);
        return DEFAULT_SKIN;
    }
};

export const setSkin = (skin: UiSkin): void => {
    try {
        localStorage.setItem(UI_SKIN_KEY, skin);
    } catch (error) {
        uiLog.warn('تعذر حفظ مظهر الواجهة في التخزين المحلي.', error);
    }

    document.documentElement.dataset.skin = skin;
    window.dispatchEvent(new CustomEvent<UiSkin>('ktra:skin', { detail: skin }));
    uiLog.info('تم تبديل مظهر الواجهة.', { skin });
};

export const applySkinOnBoot = (): UiSkin => {
    const skin = getSkin();
    document.documentElement.dataset.skin = skin;
    uiLog.info('تم تطبيق مظهر الواجهة عند الإقلاع.', { skin });
    return skin;
};
