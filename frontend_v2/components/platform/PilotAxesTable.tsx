import React from "react";

import {
  PILOT_AXES,
  PILOT_AXIS_LABELS,
  type EmployeePilotPerformance,
} from "../../services/platformPilotApi";
import { formatNumber } from "../../utils/formatNumber";

/**
 * جدولُ محاور تقييم الـpilot — **مصدرٌ واحد** لبطاقة الموظف الذاتيّة
 * (`EmployeeSelfWalletCard`) ولوحة المدير (`EmployeeWalletPanel`) معاً.
 *
 * كان نسختين متطابقتين، فأيُّ تعديلٍ على عمودٍ يلزمه تعديلان أو يتناقض الجدولان —
 * وهو عينُ ما جاءت حقولُ 210-D (`weight_original_pct`) لتمنعه: أن يقرأ طرفان
 * رقمين مختلفين لنفس المحور.
 *
 * ثلاثةُ حقولٍ يُرجعها الخادمُ ولا تُقرأ بغير هذا الجدول:
 * - `weight_original_pct`: الوزنُ كما وضعته السياسة قبل إعادة التوزيع — الفعليُّ
 *   وحدَه يُخفي أنّ محوراً غيرَ منطبقٍ أُسقط ووُزّع وزنُه.
 * - `raw_percent`: النسبةُ قبل القصّ عند ١٠٠ — منها يُقرأ الفائضُ فوق الطاقة.
 * - `uncatalogued_document_links`: روابطُ مستنداتٍ بلا بندٍ في الكتالوج النشط،
 *   مقامٌ ناقصٌ يرفع الدرجةَ بغير حقّ فيُعرَض تحذيراً بدل أن يُطرح صامتاً.
 */
export const PilotAxesTable: React.FC<{ performance: EmployeePilotPerformance }> = ({ performance }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-xs">
      <thead>
        <tr className="border-b border-slate-200 text-slate-500">
          <th className="py-1.5 pr-2 text-right">المحور</th>
          <th className="py-1.5 px-2 text-right">منطبق</th>
          <th className="py-1.5 px-2 text-right">البسط</th>
          <th className="py-1.5 px-2 text-right">المقام</th>
          <th className="py-1.5 px-2 text-right">النتيجة</th>
          <th className="py-1.5 px-2 text-right">الوزن (الأصلي ← الفعلي)</th>
          <th className="py-1.5 px-2 text-right">المساهمة</th>
          <th className="py-1.5 px-2 text-right">الاستبعادات</th>
        </tr>
      </thead>
      <tbody>
        {PILOT_AXES.map((axis) => {
          const detail = performance.axes[axis];
          if (!detail) return null;
          return (
            <tr key={axis} className="border-b border-slate-100">
              <td className="py-1.5 pr-2 font-medium">{PILOT_AXIS_LABELS[axis]}</td>
              <td className="py-1.5 px-2">{detail.applicable ? "نعم" : "لا"}</td>
              <td className="py-1.5 px-2">{formatNumber(detail.numerator)}</td>
              <td className="py-1.5 px-2">{formatNumber(detail.denominator)}</td>
              <td className="py-1.5 px-2">
                {formatNumber(detail.score_pct)}%
                {typeof detail.raw_percent === "number" && detail.raw_percent > detail.score_pct && (
                  <span className="text-emerald-700 text-[10px] block">
                    خامّاً {formatNumber(detail.raw_percent)}% — مقصوصةٌ عند ١٠٠
                  </span>
                )}
                {!!detail.uncatalogued_document_links && (
                  <span className="text-amber-700 text-[10px] block">
                    {formatNumber(detail.uncatalogued_document_links)} رابطُ مستندٍ بلا بندٍ في الكتالوج النشط
                  </span>
                )}
              </td>
              <td className="py-1.5 px-2">
                {detail.weight_original_pct !== detail.weight_pct ? (
                  <span title="أُعيد توزيعُ وزنِ محورٍ غيرِ منطبق">
                    {formatNumber(detail.weight_original_pct)}% ← <b>{formatNumber(detail.weight_pct)}%</b>
                  </span>
                ) : (
                  `${formatNumber(detail.weight_pct)}%`
                )}
              </td>
              <td className="py-1.5 px-2">{formatNumber(detail.weighted_contribution)}</td>
              <td className="py-1.5 px-2">{detail.exclusions.length ? detail.exclusions.join("، ") : "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
);

export default PilotAxesTable;
