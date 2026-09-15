import React from "react";
import { ExternalLink, Phone } from "lucide-react";

import type { ApplicantUpdate } from "../../services/platformHiringApi";
import { formatDateTimeValue } from "../../utils/formatDate";

interface ApplicantUpdateThreadProps {
  /**
   * ‏`author_name` اختياريٌّ صراحةً: الحمولةُ العامّةُ لا تحمله أبداً (اسمُ
   * الموظّف ليس من شأن المتقدّم)، وحمولةُ المسؤول تحمله. والإعلانُ هنا يغني
   * عن تضييقٍ بـ`in` يجعل القيمةَ `unknown` ويمرّ من `tsc` صدفةً.
   */
  updates: Array<ApplicantUpdate & { author_name?: string }>;
  showAuthorName?: boolean;
}

export const ApplicantUpdateThread: React.FC<ApplicantUpdateThreadProps> = ({
  updates,
  showAuthorName = false,
}) => (
  <ol className="space-y-3" aria-label="سجل الرسائل والتحديثات">
    {[...updates]
      .sort((left, right) => new Date(left.created_at).getTime() - new Date(right.created_at).getTime())
      .map((update) => {
        const isApplicant = update.author_kind === "applicant";
        const isSystem = update.author_kind === "system";
        const authorName = showAuthorName ? update.author_name ?? "" : "";
        return (
          <li
            key={update.id}
            className={isSystem ? "text-center" : isApplicant ? "flex justify-start" : "flex justify-end"}
          >
            <article
              className={
                isSystem
                  ? "inline-block max-w-full rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800/70 dark:text-slate-400"
                  : isApplicant
                    ? "max-w-[90%] rounded-xl rounded-tr-sm border border-slate-200 bg-white px-3 py-2.5 text-right dark:border-slate-700 dark:bg-slate-900"
                    : "max-w-[90%] rounded-xl rounded-tl-sm bg-blue-600 px-3 py-2.5 text-right text-white"
              }
            >
              {!isSystem && (
                <p className={isApplicant ? "mb-1 text-[11px] font-bold text-slate-600 dark:text-slate-300" : "mb-1 text-[11px] font-bold text-blue-100"}>
                  {authorName || (isApplicant ? "المتقدّم" : "فريق التوظيف")}
                </p>
              )}
              <p className={isSystem ? "whitespace-pre-wrap leading-relaxed" : "whitespace-pre-wrap text-xs leading-relaxed"}>{update.body}</p>
              {(update.link || update.phone) && (
                <div className={isSystem || isApplicant ? "mt-2 flex flex-wrap gap-2" : "mt-2 flex flex-wrap gap-2 text-blue-50"}>
                  {update.link && (
                    <a
                      href={update.link}
                      target="_blank"
                      rel="noreferrer"
                      className={isSystem || isApplicant ? "inline-flex items-center gap-1 underline text-blue-700 hover:text-blue-800 dark:text-blue-300 dark:hover:text-blue-200" : "inline-flex items-center gap-1 underline hover:text-white"}
                    >
                      <ExternalLink className="h-3.5 w-3.5" /> فتح الرابط
                    </a>
                  )}
                  {update.phone && (
                    <a
                      href={`tel:${update.phone}`}
                      dir="ltr"
                      className={isSystem || isApplicant ? "inline-flex items-center gap-1 underline text-blue-700 hover:text-blue-800 dark:text-blue-300 dark:hover:text-blue-200" : "inline-flex items-center gap-1 underline hover:text-white"}
                    >
                      <Phone className="h-3.5 w-3.5" /> {update.phone}
                    </a>
                  )}
                </div>
              )}
              <p className={isSystem ? "mt-1 text-[10px] text-slate-400 dark:text-slate-500" : isApplicant ? "mt-2 text-[10px] text-slate-400 dark:text-slate-500" : "mt-2 text-[10px] text-blue-100"}>
                {formatDateTimeValue(update.created_at)}
              </p>
            </article>
          </li>
        );
      })}
  </ol>
);
