// SubmissionHistoryList.tsx
import React from "react";
import { Submission } from "../../types";
import { SubmissionItemGallery } from "./SubmissionItemGallery";
import { StatusBadge } from "../TaskCard";

interface SubmissionHistoryListProps {
  submissions: Submission[];
  onEdit: (sub: Submission) => void;
  userRole: string;
  currentUserId: string;
  onUpdateSubmissionStatus?: (
    submissionId: string,
    status: "approved" | "rejected", 
    reviewerNotes?: string
  ) => void;
  selectedUserName?: string;
}

export const SubmissionHistoryList: React.FC<SubmissionHistoryListProps> = ({
  submissions,
  onEdit,
  userRole,
  currentUserId,
  onUpdateSubmissionStatus,
  selectedUserName,
  onAddTaskPoints, // إضافة الـ prop الجديد
}) => {
  const userSubmissions = submissions.filter(
    (sub) => sub.userId === currentUserId
  );

  const getSubmissionStatus = (sub: Submission) => {
    return sub.status || "pending";
  };

  if (!userSubmissions || userSubmissions.length === 0) {
    return (
      <p className="text-gray-500 text-sm italic p-2">لا توجد تسليمات سابقة.</p>
    );
  }

const handleApprove = async (submissionId: string) => {
  if (!submissionId) return;
  
  // احذف كود إضافة النقاط لأنها الآن في App.tsx
  // if (onAddTaskPoints) {
  //   await onAddTaskPoints(currentUserId, 5);
  // }
  
  // فقط استدعي onUpdateSubmissionStatus
  onUpdateSubmissionStatus?.(submissionId, "approved");
};

  const handleReject = (submissionId: string) => {
    if (!submissionId) return;
    const notes = prompt("أدخل سبب الرفض:");
    if (notes) {
      onUpdateSubmissionStatus?.(submissionId, "rejected", notes);
    }
  };

  return (
    <div className="space-y-4 mt-2">
      {userSubmissions.map((sub, idx) => {
        const submissionStatus = getSubmissionStatus(sub);

        return (
          <div
            key={sub.id}
            className="bg-white dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 shadow-sm overflow-hidden"
          >
            <div className="bg-gray-50 dark:bg-gray-800 px-4 py-2 border-b border-gray-200 dark:border-gray-600 flex justify-between items-center">
              <div>
                <span className="text-xs font-bold text-gray-700 dark:text-gray-300">
                  تسليم #{userSubmissions.length - idx} -{" "}
                  {new Date(sub.createdAt).toLocaleDateString()}
                </span>
                <StatusBadge status={submissionStatus} />
              </div>
            </div>

            <div className="p-3 space-y-3">
              {submissionStatus !== "pending" && (
                <div
                  className={`p-3 rounded-lg ${
                    submissionStatus === "approved"
                      ? "bg-green-50 dark:bg-green-900/50 border border-green-200 dark:border-green-800"
                      : "bg-red-50 dark:bg-red-900/50 border border-red-200 dark:border-red-800"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <StatusBadge status={submissionStatus} />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      {submissionStatus === "approved" ? "مقبول" : "مرفوض"}
                    </span>
                    {submissionStatus === "approved" && (
                      <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded-full">
                        +5 نقاط مهام 🎉
                      </span>
                    )}
                  </div>
                  {sub.reviewerNotes && (
                    <p className="text-sm text-gray-600 dark:text-gray-300">
                      <strong>ملاحظات المدير:</strong> {sub.reviewerNotes}
                    </p>
                  )}
                  {sub.reviewedAt && (
                    <p className="text-xs text-gray-500 mt-1">
                      تم المراجعة في:{" "}
                      {new Date(sub.reviewedAt).toLocaleString()}
                    </p>
                  )}
                </div>
              )}

              {(userRole === "manager" || userRole === "procurement") && submissionStatus === "pending" && (
                <div className="p-3 bg-yellow-50 dark:bg-yellow-900/50 rounded-lg border border-yellow-200 dark:border-yellow-700">
                  <h5 className="font-semibold text-yellow-800 dark:text-yellow-200 mb-2">
                    مراجعة تسليم {selectedUserName}
                  </h5>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleApprove(sub.id)}
                      className="flex-1 bg-green-600 text-white text-sm font-bold py-2 px-3 rounded-lg hover:bg-green-700 transition flex items-center justify-center gap-2"
                    >
                      <span>✅</span>
                      قبول التسليم (+5 نقاط)
                    </button>
                    <button
                      onClick={() => handleReject(sub.id)}
                      className="flex-1 bg-red-600 text-white text-sm font-bold py-2 px-3 rounded-lg hover:bg-red-700 transition"
                    >
                      رفض التسليم
                    </button>
                  </div>
                </div>
              )}

              {sub.items && sub.items.length > 0 ? (
                sub.items.map((item, i) => (
                  <div
                    key={item.id}
                    className={`p-3 ${
                      i !== sub.items.length - 1
                        ? "border-b border-gray-100 dark:border-gray-600 pb-3"
                        : ""
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <span className="text-xs bg-blue-100 text-blue-800 rounded-full w-6 h-6 flex items-center justify-center mt-1 shrink-0">
                        {i + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <a
                          href={item.productLink}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-medium text-blue-600 hover:underline break-all block mb-2"
                        >
                          {item.productLink}
                        </a>
                        {item.productPrice && (
                          <p className="text-sm font-bold text-green-600 mb-2">
                            السعر: {item.productPrice} $
                          </p>
                        )}
                        {item.notes && (
                          <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 whitespace-pre-wrap">
                            {item.notes}
                          </p>
                        )}

                        {/* عرض صور التسليم */}
                        {item.images && item.images.length > 0 && (
                          <SubmissionItemGallery images={item.images} />
                        )}
                        
                        {item.attachmentName && (
                          <div className="flex items-center gap-2 mt-2 p-2 bg-gray-50 dark:bg-gray-800 w-fit rounded">
                            <span className="text-xs text-gray-500">📎</span>
                            <a
                              href={item.attachmentUrl}
                              download={item.attachmentName}
                              className="text-xs text-gray-500 underline hover:text-gray-800 dark:hover:text-gray-200"
                            >
                              {item.attachmentName}
                            </a>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-gray-500">
                  لا توجد بنود في هذا التسليم.
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};