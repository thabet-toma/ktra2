/**
 * T-REORDER: أفعالٌ خاصّة بتقريرٍ بعينه — بلا أن تعرف الشاشة العامّة أيّ تقرير.
 *
 * `ReportRunnerPage` شاشةٌ واحدة تعرض خمسين تقريراً، وحشوُ شرطٍ فيها لكل تقرير
 * يحتاج زرّاً يحوّلها إلى سلسلة `if`. فالسؤال يُقلَب: الشاشة تسأل «هل لهذا
 * المفتاح أفعالٌ إضافية؟» وهذا الملف يجيب. تقريرٌ بلا أفعال يعود بمصفوفة فارغة
 * فلا يتغيّر شيء في شكله ولا في سلوكه.
 *
 * وحده تقرير التجديد يحتاجها اليوم: قراءته تنتهي بقرار — «ثبّت هذه الحدود» —
 * وإرسال المستخدم إلى كرت كل صنفٍ ليكتب رقمين بيده يُبطل التقرير عملياً.
 */
import { inventoryApi } from "../../services/inventoryApi";

export interface ReportActionSpec {
  key: string;
  label: string;
  onClick: () => void | Promise<void>;
}

export interface ReportActionContext {
  reportKey: string;
  rows: Record<string, unknown>[];
  /** فلاتر التشغيل الحالية — «المستوى» يقرّر إن كان الفعل منطبقاً أصلاً. */
  params: Record<string, string>;
  confirm: (opts: { title?: string; message: string; confirmText?: string }) => Promise<boolean>;
  toast: (message: string, kind?: "success" | "error" | "info") => void;
  /** إعادة تشغيل التقرير بعد تغييرٍ يمسّ أرقامه. */
  rerun: () => void | Promise<void>;
}

/** الأصناف التي لها اقتراحٌ فعلي — ما لا اقتراح له لا يُرسَل أصلاً. */
function applicableProductIds(rows: Record<string, unknown>[]): number[] {
  const ids: number[] = [];
  for (const row of rows) {
    const id = Number(row.product_id);
    const suggested = Number(row.suggested_min);
    if (!Number.isFinite(id) || id <= 0) continue;
    if (!Number.isFinite(suggested) || suggested <= 0) continue;
    if (String(row.reason || "").trim()) continue;
    ids.push(id);
  }
  return ids;
}

export function extraReportActions(ctx: ReportActionContext): ReportActionSpec[] {
  if (ctx.reportKey !== "stock-replenishment") return [];
  // على مستوى «النوع» لا صفَّ لصنفٍ بعينه، فلا شيء يُكتب عليه.
  if ((ctx.params.level || "item") !== "item") return [];

  return [{
    key: "apply-replenishment",
    label: "تثبيت الحدود المقترَحة",
    onClick: async () => {
      const ids = applicableProductIds(ctx.rows);
      if (ids.length === 0) {
        ctx.toast("لا صنف في هذه النتيجة له اقتراحٌ يُثبَّت.", "info");
        return;
      }
      const ok = await ctx.confirm({
        title: "تثبيت الحدود المقترَحة",
        message:
          `سيُكتب الحدّ الأدنى والأقصى المقترَحان على ${ids.length} صنفاً، ` +
          "ويحلّان محلّ أي حدٍّ يدويّ عليها. الأصناف بلا اقتراح لن تُمَسّ.",
        confirmText: "تثبيت",
      });
      if (!ok) return;
      const res = await inventoryApi.applyReplenishment(ids);
      const skipped = res.skipped?.length ?? 0;
      ctx.toast(
        skipped > 0
          ? `ثُبِّت الحدّ على ${res.applied} صنفاً، وتُرك ${skipped} بلا اقتراح.`
          : `ثُبِّت الحدّ على ${res.applied} صنفاً.`,
        "success",
      );
      await ctx.rerun();
    },
  }];
}
