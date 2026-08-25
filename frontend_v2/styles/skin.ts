import { uiLog } from '../utils/uiLog';

/**
 * مظهر الواجهة: **حديث** (الافتراضي) أو **كلاسيكي**.
 *
 * M7-T3 (2026-08-25): كانت القيمة الثانية `'aseel'` باسم برنامجٍ آخر. صارت
 * `'classic'` تصف ما هي بدل أن تُحيل إلى مرجعٍ أُسقط — **والجلد نفسه باقٍ
 * خياراً كاملاً بقرار المالك**؛ المُلغى كان المرجعية لا المظهر.
 */
export type UiSkin = 'classic' | 'modern';

const UI_SKIN_KEY = 'ktra.uiSkin';
/** M6: الافتراضي هو الجلد الحديث. الكلاسيكي خيارٌ كامل في الإعدادات. */
const DEFAULT_SKIN: UiSkin = 'modern';

/** القيمة القديمة المحفوظة في متصفّحات المستخدمين قبل إعادة التسمية. */
const LEGACY_CLASSIC = 'aseel';

const isUiSkin = (value: string | null): value is UiSkin =>
    value === 'classic' || value === 'modern';

/**
 * يقرأ التفضيل المحفوظ. **يقبل القيمة القديمة `aseel`** ويُرجعها `classic`:
 * المفتاح مكتوبٌ فعلاً في متصفّحات من اختار الكلاسيكي، ورفضُه يعني أن اختيارهم
 * يُمحى بصمت عند أول تحديث ويعودون إلى الحديث بلا سبب يرونه.
 */
export const getSkin = (): UiSkin => {
    try {
        const storedSkin = localStorage.getItem(UI_SKIN_KEY);
        if (storedSkin === LEGACY_CLASSIC) return 'classic';
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
