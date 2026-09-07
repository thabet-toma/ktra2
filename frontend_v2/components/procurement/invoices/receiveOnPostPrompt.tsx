/**
 * T-RECVOPT — «استلام البضاعة مع الترحيل» خياراً لكل فاتورة لا للشركة كلّها.
 *
 * الإعداد العام (`PurchaseSettings.receive_on_post`) كان الحاكم الوحيد، فمورّدٌ
 * واحد يوصّل على دفعات يُجبر المستخدم على إطفائه **لكل الموردين** — فتُفقد
 * الراحة في الحالة الغالبة (البضاعة تصل مع فاتورتها). هنا يبقى الإعداد العام
 * هو الافتراضي، ويُسأل عنه مرّةً عند الترحيل حيث يكون للجواب معنى.
 *
 * مصدرٌ واحد لمسارَي الترحيل (شريط أدوات المحرّر · لوحة «المحاسبة والقيد») —
 * نسختان من السؤال تفترقان يوماً في الشرط أو في الافتراضي.
 */
import React from "react";

export interface ReceiveOnPostTarget {
  /** فاتورة محلية = غير مستوردة؛ المستوردة تدخل مخزنها من تخليص الشحنة. */
  isLocal: boolean;
  isReturn: boolean;
  receiptStatus?: string;
  /** `PurchaseSettings.receive_on_post` — مفعّلاً يُسكِت السؤال. انظر أدناه. */
  autoReceiveSetting: boolean;
}

/**
 * هل للسؤال معنى أصلاً؟
 *
 * لا معنى له على مرجع شراء (يُخرج البضاعة لا يُدخلها)، ولا على فاتورة مستوردة
 * (لا تمرّ من هنا)، ولا على فاتورة استُلمت بضاعتها كلّها سلفاً.
 *
 * ولا معنى له حين يكون الإعداد العام مفعّلاً: من ضبط شركته على «الاستلام مع
 * الترحيل» أجاب السؤال مرّةً في الإعدادات، وإعادةُ سؤاله عند كل ترحيل تطلب
 * منه تأكيد قراره لا اتّخاذه. يبقى السؤال حيث يفيد فعلاً — الإعداد مطفأ
 * (الاستلام على دفعات هو العادة) وهذه الفاتورة وصلت كاملة، فيقول «نعم» لها
 * وحدها. أي أنّ الحوار يظهر للاستثناء لا للقاعدة.
 *
 * وحين يُسكَت السؤال لا يُرسَل `receive_on_post` في جسم الطلب أصلاً، فيقرّر
 * الخادمُ بالإعداد نفسِه — لا قيمةَ تُلفَّق هنا.
 */
export function receiveOnPostApplies(target: ReceiveOnPostTarget): boolean {
  return (
    target.isLocal
    && !target.isReturn
    && !target.autoReceiveSetting
    && (target.receiptStatus || "not_received") !== "received"
  );
}

type ConfirmFn = (opts: {
  title?: string;
  message: React.ReactNode;
  confirmText?: string;
  danger?: boolean;
}) => Promise<boolean>;

/**
 * يسأل عن الخيار قبل الترحيل. يعيد الاختيار، أو `null` إن ألغى المستخدم.
 *
 * المربّع غير مُتحكَّم به (`defaultChecked`) عمداً: الحوار يُرسم في مزوّد خارج
 * هذا المكوّن، فربطه بحالة React هنا يعني إعادة رسم الحوار مع كل نقرة.
 */
export async function askReceiveOnPost(
  confirm: ConfirmFn,
  defaultValue: boolean,
): Promise<boolean | null> {
  const choice = { value: defaultValue };
  const accepted = await confirm({
    title: "ترحيل الفاتورة",
    danger: false,
    confirmText: "ترحيل",
    message: (
      <div className="space-y-3 text-start">
        <p>
          سيُرحَّل قيد الفاتورة إلى دفتر اليومية. اختر ما يحدث للبضاعة:
        </p>
        <label className="flex items-start gap-2 cursor-pointer">
          <input
            type="checkbox"
            defaultChecked={defaultValue}
            onChange={(e) => { choice.value = e.currentTarget.checked; }}
            className="mt-1"
          />
          <span>
            <b>استلام البضاعة للمخزن مع الترحيل</b>
            <span className="block text-xs text-[var(--color-text-muted)]">
              أطفئه إذا كانت البضاعة تصل على دفعات — تبقى معلّقة في وسيط
              الاستلام، وتُدخلها بكمياتها من زرّ «استلام» كلّما وصلت إرسالية.
            </span>
          </span>
        </label>
      </div>
    ),
  });
  return accepted ? choice.value : null;
}
