/**
 * T-SIMPL2 — غلافُ قناع العناصر: يقرأ الوضع مرّةً ويُسلّم أدوات القرار.
 *
 * **آليةٌ واحدة لا ثانية لها**: كلّ ما يُخفى داخل الشاشات يمرّ من هنا — الحقل
 * الظاهر بشرطٍ (`show`) وعمود الجدول (`columns`) والتبويب والزرّ. لا `<AdvancedOnly>`
 * ولا شرطٌ مكتوبٌ بيدٍ فوقها؛ آليتان متنازعتان فوق عنصرٍ واحد هما كيف يختفي
 * حقلٌ بصمت.
 *
 * الشاشة لا تكتب `uiMode === 'simple'` بنفسها ولا تحمل قائمةَ ما تُخفيه —
 * السِّجل كلّه في `utils/uiMode.ts`، وهذا الخطّاف يصله بسياق الصلاحيات
 * (`/api/permissions/me/` المحمَّلة عند الإقلاع أصلاً، بلا طلبٍ إضافي).
 *
 * نفس قاعدة `FieldHint`: القرار يُقرأ مرّةً في مكانٍ واحد لا يُعاد كتابته في
 * كل موضع نداء — فلا يُنسى شرطٌ في أحدها.
 */
import { useCallback, useRef } from 'react';
import { usePermissions } from '../contexts/PermissionsContext';
import { showAdvanced, visibleColumns, type MaskKey } from '../utils/uiMode';

export interface SimpleUi {
  /** هل الوضع السهل فعّال؟ للحالات التي لا مفتاحَ سِجلٍّ لها (نصّ بديل مثلاً). */
  simple: boolean;
  /** هل يُعرَض هذا العنصر المتقدّم؟ `keepIfSet` = قاعدة السقوط للظهور. */
  show: (key: MaskKey, keepIfSet?: boolean) => boolean;
  /** تقليم أعمدة جدول الشاشة — `screen` اسم `AppView`، و`keep` ما يبقى رغم الوضع. */
  columns: <C extends { key: string }>(
    cols: readonly C[],
    screen: string,
    keep?: readonly string[],
  ) => C[];
}

export function useSimpleUi(): SimpleUi {
  const { uiMode } = usePermissions();

  const show = useCallback(
    (key: MaskKey, keepIfSet = false) => showAdvanced(key, uiMode, keepIfSet),
    [uiMode],
  );

  const columns = useCallback(
    <C extends { key: string }>(cols: readonly C[], screen: string, keep?: readonly string[]) =>
      visibleColumns(cols, screen, uiMode, keep),
    [uiMode],
  );

  return { simple: uiMode === 'simple', show, columns };
}

/**
 * تثبيتُ حقيقةِ «هذا العمود يحمل قيمة» على القوائم **المرقَّمة**.
 *
 * حقائق `keep` تُشتقّ من الصفوف المحمَّلة، وصفحةٌ واحدة ليست الجدول كلّه: على
 * قائمةٍ مرقَّمة تظهر «محجوز» في الصفحة الثالثة وتختفي في الرابعة، فتتراقص
 * أعمدةُ الجدول تحت يد المستخدم. الحلّ ألّا تُنسى الحقيقة بعد رؤيتها: العمود
 * **يظهر ولا يعود يختفي** ما دامت الشاشة مفتوحة.
 *
 * الاتجاه مقصود — نحو الظهور لا نحو الإخفاء: أسوأ ما يحدث عمودٌ زائد، وأسوأ ما
 * يمنعه اختفاءُ رقمٍ رآه المستخدم قبل صفحة.
 */
export function useKeepOnce(fact: boolean): boolean {
  const seen = useRef(false);
  if (fact) seen.current = true;
  return seen.current;
}

export default useSimpleUi;
