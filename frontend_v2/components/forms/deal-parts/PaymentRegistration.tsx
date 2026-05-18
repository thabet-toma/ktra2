import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  DollarSign,
  Upload,
  X,
  Loader2,
  CheckCircle,
  Calendar,
  Lock,
  Percent,
  CreditCard,
  Info,
  AlertCircle,
  Clock,
} from "lucide-react";
import { cloudinaryService } from "@/services/cloudinaryService";
import { cashBoxesService } from "@/services/firestoreService";
import { accountingApi } from "@/services/accountingApi";
import type { TrialBalanceRow } from "@/types/accounting";
import { Deal, DealPayment, DealStatus } from "@/types";
import { maxPaymentPrincipalForDeal } from "@/utils/dealPaymentLimits";
import { validatePaymentInput } from "@/utils/usePaymentForm";
import { isAwaitingSupplierConfirmation } from "@/utils/dealPaymentFlow";

/** ربط صندوق (external_id = معرف Firestore) برصيد حسابه في ميزان المراجعة */
async function fetchSqlBalanceByCashBoxExternalId(): Promise<Record<string, number>> {
  try {
    const today = new Date().toISOString().split("T")[0];
    const yearStart = `${new Date().getFullYear()}-01-01`;
    const [ledgers, tb] = await Promise.all([
      accountingApi.getCashBoxLedgers(),
      accountingApi.getTrialBalance({
        start_date: yearStart,
        end_date: today,
        include_unposted: "true",
      }),
    ]);
    const rows: TrialBalanceRow[] = Array.isArray(tb)
      ? tb
      : Array.isArray((tb as { rows?: TrialBalanceRow[] })?.rows)
        ? (tb as { rows: TrialBalanceRow[] }).rows
        : [];
    const byAcct = new Map<number, number>();
    for (const r of rows) {
      const bal = r.closing_balance ?? r.balance ?? 0;
      byAcct.set(r.id, Number(bal));
    }
    const out: Record<string, number> = {};
    for (const L of ledgers) {
      const ext = String(L.external_id || "").trim();
      if (!ext) continue;
      const bal = byAcct.get(L.account_id);
      if (bal != null && Number.isFinite(bal)) out[ext] = bal;
    }
    return out;
  } catch {
    return {};
  }
}

interface PaymentProps {
  title: string;
  paymentType: string;
  paymentData?: DealPayment;
  onSaveClaim: (data: any) => void;
  onSavePayment: (data: any) => void;
  onConfirmSupplier: (data: any) => void;
  currentUser: { id: string; name: string; role: string };
  dealId?: string;
  dealStatus?: DealStatus;
  deal?: Partial<Deal>;
  selectedInstallmentId?: string;
  installmentId?: string;
  installmentNumber?: number;
  installmentAmount?: number;
}

export const PaymentRegistration: React.FC<PaymentProps> = ({
  title,
  paymentType,
  paymentData,
  onSaveClaim,
  onSavePayment,
  onConfirmSupplier,
  currentUser,
  dealId,
  dealStatus,
  deal,
  selectedInstallmentId,
  installmentId,
  installmentNumber,
  installmentAmount,
}) => {
  const [mode, setMode] = useState<"claim" | "swift" | "verify" | "confirmed">("swift");
  /** direct = دفع فوري بدون مطالبة | claim_first = رفع مطالبة ثم دفع لاحقاً */
  const [paymentPath, setPaymentPath] = useState<"direct" | "claim_first">("direct");

  // الحقول الأساسية
  const [claimImage, setClaimImage] = useState("");
  const [swiftImage, setSwiftImage] = useState("");
  const [supplierImage, setSupplierImage] = useState("");
  const [supplierNotes, setSupplierNotes] = useState("");
  const [isUploading, setIsUploading] = useState<string | null>(null);
  const [cashBoxes, setCashBoxes] = useState<any[]>([]);
  const [sqlBalanceByCashBoxId, setSqlBalanceByCashBoxId] = useState<Record<string, number>>({});
  const sqlBalanceRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [selectedCashBoxId, setSelectedCashBoxId] = useState<string>("");
  const [notes, setNotes] = useState("");

  // ⭐ الحقول الجديدة للتواريخ
  const [claimDate, setClaimDate] = useState(new Date().toISOString().split('T')[0]);
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().split('T')[0]);
  const [confirmationDate, setConfirmationDate] = useState(new Date().toISOString().split('T')[0]);

  const [usdToIls, setUsdToIls] = useState(3.78);
  const [transferFee, setTransferFee] = useState(0);

  // ⭐ استخدام جميع مصادر بيانات الدفعة
  const actualInstallmentId = installmentId || selectedInstallmentId;
  const actualInstallment = deal?.installments?.find(inst =>
    inst.id === actualInstallmentId || inst.installmentNumber === installmentNumber
  );

  // ⭐ حساب المبالغ
  const calculatedInstallmentAmount = actualInstallment?.amount || installmentAmount || 0;
  const amountPaid = actualInstallment?.paymentData?.amountPaid || 0;
  const remainingAmount = Math.max(0, calculatedInstallmentAmount - amountPaid);
  const dealPrincipalCap = maxPaymentPrincipalForDeal(deal, paymentData?.id);
  const maxPrincipal =
    calculatedInstallmentAmount > 0
      ? Math.min(remainingAmount, dealPrincipalCap)
      : dealPrincipalCap;

  // ⭐ المبلغ الافتراضي
  const [amount, setAmount] = useState(
    paymentData?.amount || remainingAmount || calculatedInstallmentAmount
  );

  // تحديد الوضع: إن وُجد تنفيذ دفع (سليب/صندوق/ترحيل) ولم يُؤكَّد المورد → وضع التأكيد فقط، لا نموذج الدفع الكامل
  useEffect(() => {
    if (paymentData?.confirmedBySupplier) {
      setMode("confirmed");
    } else if (isAwaitingSupplierConfirmation(paymentData)) {
      setMode("verify");
    } else if (paymentData?.alibabaClaimImage) {
      setMode("swift");
    } else {
      setMode(paymentPath === "claim_first" ? "claim" : "swift");
    }

    if (paymentData) {
      // تحميل الصور
      setClaimImage(paymentData.alibabaClaimImage || "");
      setSwiftImage(paymentData.bankSwiftImage || "");

      // ⭐ تحميل التواريخ
      if (paymentData.paymentDate) {
        setPaymentDate(paymentData.paymentDate.split('T')[0]);
      }
      if (paymentData.confirmedAt) {
        setConfirmationDate(paymentData.confirmedAt.split('T')[0]);
      }

      // تحميل البيانات الأخرى
      setUsdToIls(paymentData.usdToIls || 3.78);
      setTransferFee(paymentData.transferCost || 0);
      setAmount(paymentData.amount || remainingAmount || calculatedInstallmentAmount);
      setNotes(paymentData.notes || "");
      setSupplierNotes(paymentData.supplierNotes || "");
    }
  }, [paymentData, paymentPath, remainingAmount, calculatedInstallmentAmount]);

  const scheduleSqlBalanceRefresh = useCallback(() => {
    if (sqlBalanceRefreshTimerRef.current) clearTimeout(sqlBalanceRefreshTimerRef.current);
    sqlBalanceRefreshTimerRef.current = setTimeout(async () => {
      sqlBalanceRefreshTimerRef.current = null;
      setSqlBalanceByCashBoxId(await fetchSqlBalanceByCashBoxExternalId());
    }, 350);
  }, []);

  useEffect(() => {
    const unsub = cashBoxesService.subscribeToCashBoxes((boxes) => {
      setCashBoxes(boxes);
      scheduleSqlBalanceRefresh();
    });
    scheduleSqlBalanceRefresh();
    return () => {
      unsub();
      if (sqlBalanceRefreshTimerRef.current) clearTimeout(sqlBalanceRefreshTimerRef.current);
    };
  }, [scheduleSqlBalanceRefresh]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>, setter: (url: string) => void) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading("uploading");
    try {
      const url = await cloudinaryService.uploadImage(file);
      setter(url);
    } catch (err) {
      alert("فشل رفع الصورة");
    } finally {
      setIsUploading(null);
    }
  };

  // ⭐ دالة محسنة لحفظ المطالبة مع التاريخ
  const handleSaveClaim = () => {
    if (!claimImage) {
      alert("يرجى رفع صورة المطالبة");
      return;
    }

    if (amount > maxPrincipal) {
      alert(
        `❌ المبلغ ($${amount.toLocaleString()}) يتجاوز الحد المسموح ($${maxPrincipal.toLocaleString()}) — لا يجوز تجاوز إجمالي الصفقة`
      );
      return;
    }

    if (amount <= 0) {
      alert("❌ المبلغ يجب أن يكون أكبر من صفر");
      return;
    }

    const data = {
      type: paymentType,
      amount: amount,
      alibabaClaimImage: claimImage,
      // ⭐ تاريخ المطالبة
      claimDate: new Date(claimDate + 'T00:00:00').toISOString(),
      paymentDate: new Date().toISOString(),
      usdToIls: 0,
      transferCost: 0,
      transferFee: 0,
      notes: notes || `مطالبة ${actualInstallment ? `دفعة ${actualInstallment.installmentNumber}` : title}`,
      installmentId: actualInstallmentId,
      installmentNumber: actualInstallment?.installmentNumber || installmentNumber,
      createdAt: new Date().toISOString(),
      createdBy: currentUser.id,
      createdByName: currentUser.name,
    };

    onSaveClaim(data);
  };

  // ⭐ دالة محسنة لحفظ السليب مع التواريخ
  const handleSaveSwift = () => {
    const vErr = validatePaymentInput({ amount: String(amount), date: paymentDate });
    if (vErr.amount || vErr.date) {
      alert(vErr.amount || vErr.date);
      return;
    }

    if (!swiftImage) {
      alert("يرجى رفع صورة السليب");
      return;
    }

    if (!selectedCashBoxId) {
      alert("يرجى اختيار صندوق مالي");
      return;
    }

    // حساب المبلغ الإجمالي مع تكلفة الحوالة
    const totalAmount = amount + transferFee;

    // تحقق من وجود رصيد كافي في الصندوق
    const selectedCashBox = cashBoxes.find(cb => cb.id === selectedCashBoxId);
    if (!selectedCashBox) {
      alert("❌ الصندوق المحدد غير موجود");
      return;
    }

    if (amount > maxPrincipal) {
      alert(
        `❌ المبلغ ($${amount.toLocaleString()}) يتجاوز الحد المسموح ($${maxPrincipal.toLocaleString()}) — لا يجوز تجاوز إجمالي الصفقة`
      );
      return;
    }

    const data = {
      bankSwiftImage: swiftImage,
      usdToIls: usdToIls,
      transferCost: transferFee,
      transferFee: transferFee,
      paymentDate: new Date(paymentDate + 'T00:00:00').toISOString(),
      transferDate: new Date(paymentDate + 'T00:00:00').toISOString(),
      cashBoxId: selectedCashBoxId,
      amount: amount,
      totalDeductedAmount: totalAmount,
      notes: notes || `دفع ${actualInstallment ? `دفعة ${actualInstallment.installmentNumber}` : title}`,
      installmentId: actualInstallmentId,
      installmentNumber: actualInstallment?.installmentNumber || installmentNumber,
      dealNumber: deal?.dealNumber,
      // ⭐ معلومات إضافية للصندوق
      cashBoxName: selectedCashBox.name,
      cashBoxCurrency: selectedCashBox.currency,
      cashBoxBalanceBefore:
        Object.prototype.hasOwnProperty.call(sqlBalanceByCashBoxId, selectedCashBox.id)
          ? sqlBalanceByCashBoxId[selectedCashBox.id]
          : selectedCashBox.currentBalance,
      // ⭐ تفاصيل الخصم
      deductionDetails: {
        principalAmount: amount,
        transferFee: transferFee,
        totalDeducted: totalAmount,
        timestamp: new Date().toISOString(),
        deductedBy: currentUser.id,
        deductedByName: currentUser.name
      }
    };

    // ⭐ تأكيد من المستخدم قبل الخصم
    if (transferFee > 0) {
      const confirmMessage = `هل أنت متأكد من خصم المبلغ الإجمالي $${totalAmount.toLocaleString()} من صندوق "${selectedCashBox.name}"؟\n\n- المبلغ الأساسي: $${amount.toLocaleString()}\n- تكلفة الحوالة: $${transferFee.toLocaleString()}`;

      if (!window.confirm(confirmMessage)) {
        return;
      }
    }

    onSavePayment(data);
  };

  // ⭐ دالة محسنة لتأكيد المورد مع التاريخ
  const handleConfirmSupplier = () => {
    const confirmationIso = new Date(confirmationDate + "T12:00:00").toISOString();
    const data = {
      paymentId: paymentData?.id,
      supplierConfirmationImage: supplierImage,
      supplierNotes: supplierNotes,
      cashBoxId: selectedCashBoxId,
      amount: amount,
      transferFee: transferFee,
      paymentConfirmationDate: confirmationIso,
      confirmationDate: confirmationIso,
      notes: notes,
    };

    onConfirmSupplier(data);
  };

  // ⭐ إذا كانت الدفعة مكتملة
  if (mode === "confirmed") {
    return (
      <div className="p-4 bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800 rounded-lg">
        <div className="flex items-center gap-3">
          <CheckCircle className="w-6 h-6 text-green-600 dark:text-green-400" />
          <div>
            <h4 className="font-bold text-green-800 dark:text-green-300">{title} - تم التأكيد</h4>
            <p className="text-sm text-green-700 dark:text-green-400">
              المبلغ: ${paymentData?.amount?.toLocaleString()}
            </p>

            {/* ⭐ عرض التواريخ */}
            {paymentData && (
              <div className="mt-3 space-y-1 text-xs">
                {paymentData.paymentDate && (
                  <div className="flex items-center gap-1 text-blue-600">
                    <Calendar className="w-3 h-3" />
                    <span>التحويل: {new Date(paymentData.paymentDate).toLocaleDateString('en-US')}</span>
                  </div>
                )}
                {paymentData.confirmedAt && (
                  <div className="flex items-center gap-1 text-purple-600">
                    <Calendar className="w-3 h-3" />
                    <span>التأكيد: {new Date(paymentData.confirmedAt).toLocaleDateString('en-US')}</span>
                  </div>
                )}
              </div>
            )}

            {paymentData?.transferCost && paymentData.transferCost > 0 && (
              <p className="text-xs text-green-600 dark:text-green-500 mt-2">
                + تكلفة حوالة: ${paymentData.transferCost.toLocaleString()}
              </p>
            )}
            {actualInstallment && (
              <p className="text-xs text-green-600 dark:text-green-500 mt-1">
                دفعة {actualInstallment.installmentNumber} • {actualInstallment.percentage}% من الإجمالي
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  const showPathPicker =
    !paymentData?.confirmedBySupplier &&
    !paymentData?.bankSwiftImage &&
    !paymentData?.alibabaClaimImage;

  return (
    <div className="space-y-6">
      {showPathPicker && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-600 bg-slate-50 dark:bg-slate-900/40 p-1 flex gap-1">
          <button
            type="button"
            onClick={() => {
              setPaymentPath("direct");
              setMode("swift");
            }}
            className={`flex-1 py-2.5 px-3 rounded-lg text-sm font-semibold transition-colors ${
              paymentPath === "direct"
                ? "bg-emerald-600 text-white shadow"
                : "text-gray-600 dark:text-gray-400 hover:bg-white/80 dark:hover:bg-slate-800"
            }`}
          >
            تسجيل الدفع مباشرة
            <span className="block text-[10px] font-normal opacity-90 mt-0.5">
              سليب، صندوق، سعر صرف — دون مطالبة
            </span>
          </button>
          <button
            type="button"
            onClick={() => {
              setPaymentPath("claim_first");
              setMode("claim");
            }}
            className={`flex-1 py-2.5 px-3 rounded-lg text-sm font-semibold transition-colors ${
              paymentPath === "claim_first"
                ? "bg-amber-600 text-white shadow"
                : "text-gray-600 dark:text-gray-400 hover:bg-white/80 dark:hover:bg-slate-800"
            }`}
          >
            رفع مطالبة أولاً
            <span className="block text-[10px] font-normal opacity-90 mt-0.5">
              يحدّث حالة الصفقة لمسار «جاهز للدفع» ثم تدفع لاحقاً
            </span>
          </button>
        </div>
      )}

      {paymentData?.alibabaClaimImage && !paymentData?.bankSwiftImage && !paymentData?.confirmedBySupplier && (
        <p className="text-xs text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-600 rounded-lg px-3 py-2">
          تم رفع المطالبة. يمكنك إكمال تسجيل الدفع أدناه عند الجاهزية.
        </p>
      )}

      {/* ⭐ معلومات الدفعة — مخفاة في وضع تأكيد المورد لتبقى الشاشة بسيطة */}
      {(actualInstallment || installmentNumber) && mode !== "verify" && (
        <div className="p-4 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/10 dark:to-indigo-900/10 border border-blue-200 dark:border-blue-800 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 dark:bg-blue-900/20 rounded-lg">
                <CreditCard className="w-5 h-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <h4 className="font-bold text-blue-900 dark:text-blue-200">
                  {actualInstallment ? `دفعة ${actualInstallment.installmentNumber}` : title}
                </h4>
                <p className="text-sm text-blue-700 dark:text-blue-400">
                  {actualInstallment?.percentage || 'N/A'}% من إجمالي الصفقة
                </p>
              </div>
            </div>

            <div className="text-right">
              <div className="text-xl font-bold text-blue-900 dark:text-blue-200">
                ${calculatedInstallmentAmount.toLocaleString()}
              </div>
              <div className="text-sm text-blue-700 dark:text-blue-400">
                المبلغ المحدد
              </div>
            </div>
          </div>

          {/* ⭐ شريط التقدم */}
          <div className="mb-2">
            <div className="flex justify-between text-xs text-blue-700 dark:text-blue-400 mb-1">
              <span>المبلغ المتبقي</span>
              <span>${remainingAmount.toLocaleString()}</span>
            </div>
            <div className="h-2 bg-blue-200 dark:bg-blue-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500"
                style={{
                  width: `${(amountPaid / calculatedInstallmentAmount) * 100}%`
                }}
              />
            </div>
          </div>

          {/* ⭐ ملاحظات */}
          {actualInstallment?.notes && (
            <div className="mt-3 pt-3 border-t border-blue-200 dark:border-blue-700">
              <p className="text-xs text-blue-700 dark:text-blue-400">
                📝 {actualInstallment.notes}
              </p>
            </div>
          )}
        </div>
      )}

      {/* ⭐ إدخال المبلغ */}
      {mode === "claim" || mode === "swift" ? (
        <div className="p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg border">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            المبلغ المدفوع ($)
          </label>
          <div className="relative">
            <input
              type="number"
              min="0.01"
              step="0.01"
              max={maxPrincipal > 0 ? maxPrincipal : undefined}
              value={amount}
              onChange={(e) => setAmount(parseFloat(e.target.value) || 0)}
              className="w-full p-3 pr-10 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-right text-lg font-medium"
            />
            <DollarSign className="absolute left-3 top-3.5 w-5 h-5 text-gray-400" />
          </div>

          <div className="mt-2 flex justify-between text-sm">
            <span className="text-gray-500">الحد الأقصى لهذه العملية:</span>
            <span className="font-medium text-blue-600 dark:text-blue-400">
              ${maxPrincipal.toLocaleString()}
            </span>
          </div>

          {amount > maxPrincipal && (
            <div className="mt-2 flex items-center gap-2 text-red-600 dark:text-red-400 text-sm">
              <AlertCircle className="w-4 h-4" />
              <span>المبلغ يتجاوز المتاح ({maxPrincipal.toLocaleString()}$)</span>
            </div>
          )}
        </div>
      ) : null}

      {/* حالة المطالبة */}
      {mode === "claim" && (
        <div className="space-y-6">
          {/* ⭐ تاريخ المطالبة */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-yellow-600" />
                تاريخ المطالبة
              </div>
            </label>
            <div className="relative">
              <input
                type="date"
                value={claimDate}
                onChange={(e) => setClaimDate(e.target.value)}
                className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                required
              />
              <Calendar className="absolute left-3 top-3.5 w-5 h-5 text-gray-400" />
            </div>
          </div>

          {/* إدخال الملاحظات */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              ملاحظات (اختياري)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              rows={2}
              placeholder="أضف أي ملاحظات حول هذه المطالبة..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              صورة المطالبة من علي بابا
            </label>
            {claimImage ? (
              <div className="relative group">
                <img
                  src={claimImage}
                  className="w-full h-48 object-contain rounded-lg border-2 border-blue-300 bg-gray-50"
                  alt="صورة المطالبة"
                />
                <button
                  onClick={() => setClaimImage("")}
                  className="absolute top-2 right-2 bg-red-500 text-white p-1.5 rounded-full hover:bg-red-600 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
                <div className="absolute bottom-2 left-2 bg-blue-600 text-white text-xs px-2 py-1 rounded">
                  ✓ تم الرفع
                </div>
              </div>
            ) : (
              <label className="flex flex-col items-center justify-center w-full h-48 border-2 border-dashed border-blue-300 rounded-lg cursor-pointer bg-blue-50 hover:bg-blue-100 dark:bg-blue-900/10 dark:border-blue-700 dark:hover:bg-blue-900/20 transition-colors">
                {isUploading === "uploading" ? (
                  <>
                    <Loader2 className="w-10 h-10 text-blue-500 animate-spin mb-2" />
                    <p className="text-blue-600 dark:text-blue-400">جاري رفع الصورة...</p>
                  </>
                ) : (
                  <>
                    <div className="p-3 bg-blue-100 dark:bg-blue-900/20 rounded-full mb-3">
                      <Upload className="w-8 h-8 text-blue-600 dark:text-blue-400" />
                    </div>
                    <p className="font-medium text-blue-700 dark:text-blue-300 mb-1">اضغط لرفع صورة المطالبة</p>
                    <p className="text-sm text-blue-600 dark:text-blue-400">يُفضل صورة واضحة من موقع علي بابا</p>
                  </>
                )}
                <input
                  type="file"
                  className="hidden"
                  accept="image/*"
                  onChange={(e) => handleUpload(e, setClaimImage)}
                />
              </label>
            )}
          </div>

          <button
            onClick={handleSaveClaim}
            disabled={!claimImage || amount > maxPrincipal || amount <= 0}
            className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          >
            {!claimImage ? (
              <>
                <AlertCircle className="w-5 h-5" />
                ارفع صورة المطالبة أولاً
              </>
            ) : (
              <>
                <CheckCircle className="w-5 h-5" />
                حفظ المطالبة (جاهز للدفع)
              </>
            )}
          </button>
        </div>
      )}

      {/* حالة السليب مع التواريخ */}
      {mode === "swift" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* ⭐ تاريخ الدفع الفعلي */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-blue-600" />
                  تاريخ الدفع الفعلي
                </div>
              </label>
              <div className="relative">
                <input
                  type="date"
                  value={paymentDate}
                  onChange={(e) => setPaymentDate(e.target.value)}
                  className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
                <Calendar className="absolute left-3 top-3 w-5 h-5 text-gray-400" />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                سعر التحويل ($ → ₪)
              </label>
              <input
                type="number"
                step="0.001"
                value={usdToIls}
                onChange={(e) => setUsdToIls(Number(e.target.value))}
                className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
          </div>

          {/* ⭐ حقل تكلفة الحوالة البنكية */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              تكلفة الحوالة البنكية ($)
              <span className="text-xs text-gray-500 dark:text-gray-400 ml-1">
                (ستخصم من الصندوق كتكلفة إضافية)
              </span>
            </label>
            <div className="relative">
              <input
                type="number"
                min="0"
                step="0.01"
                value={transferFee}
                onChange={(e) => setTransferFee(Number(e.target.value) || 0)}
                className="w-full p-3 pr-10 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                placeholder="أدخل تكلفة الحوالة إذا كانت موجودة"
              />
              <DollarSign className="absolute left-3 top-3.5 w-5 h-5 text-gray-400" />
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              اتركها صفر إذا لم تكن هناك تكلفة حوالة
            </p>
          </div>

          {/* ⭐ بطاقة عرض التكلفة الإجمالية */}
          {transferFee > 0 && (
            <div className="p-4 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-600 rounded-lg">
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-slate-200/80 dark:bg-slate-700 rounded-lg">
                    <CreditCard className="w-5 h-5 text-slate-600 dark:text-slate-300" />
                  </div>
                  <div>
                    <p className="font-medium text-slate-800 dark:text-slate-200">
                      الإجمالي المخصوم من الصندوق
                    </p>
                    <p className="text-xs text-slate-600 dark:text-slate-400">
                      المبلغ + تكلفة الحوالة
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-xl font-bold text-slate-900 dark:text-slate-100">
                    ${(amount + transferFee).toLocaleString()}
                  </div>
                  <div className="text-sm text-slate-600 dark:text-slate-400">
                    ${amount.toLocaleString()} + ${transferFee.toLocaleString()}
                  </div>
                </div>
              </div>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              اختر صندوق الدفع
            </label>
            <select
              value={selectedCashBoxId}
              onChange={(e) => setSelectedCashBoxId(e.target.value)}
              className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            >
              <option value="">-- اختر صندوقاً مالياً --</option>
              {cashBoxes.map((cb) => {
                const fromSql = Object.prototype.hasOwnProperty.call(sqlBalanceByCashBoxId, cb.id);
                const displayBal = fromSql ? sqlBalanceByCashBoxId[cb.id] : Number(cb.currentBalance ?? 0);
                return (
                  <option key={cb.id} value={cb.id} className="py-2">
                    {cb.name} — رصيد: {displayBal.toLocaleString(undefined, { maximumFractionDigits: 2 })}{" "}
                    {cb.currency}
                    {fromSql ? " (محاسبة)" : ""}
                  </option>
                );
              })}
            </select>
            <p className="text-xs text-gray-500 mt-2">
              ⚠️ خصم فوري. الرصيد من المحاسبة عند وجود ربط للصندوق، وإلا من Firestore. يُسمح بالرصيد السالب.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              صورة سليب البنك
            </label>
            {swiftImage ? (
              <div className="relative group">
                <img
                  src={swiftImage}
                  className="w-full h-48 object-contain rounded-lg border-2 border-green-300 bg-gray-50"
                  alt="صورة السليب"
                />
                <button
                  onClick={() => setSwiftImage("")}
                  className="absolute top-2 right-2 bg-red-500 text-white p-1.5 rounded-full hover:bg-red-600"
                >
                  <X className="w-4 h-4" />
                </button>
                <div className="absolute bottom-2 left-2 bg-green-600 text-white text-xs px-2 py-1 rounded">
                  ✓ تم الرفع
                </div>
              </div>
            ) : (
              <label className="flex flex-col items-center justify-center w-full h-48 border-2 border-dashed border-green-300 rounded-lg cursor-pointer bg-green-50 hover:bg-green-100 dark:bg-green-900/10 dark:border-green-700 dark:hover:bg-green-900/20 transition-colors">
                {isUploading === "uploading" ? (
                  <>
                    <Loader2 className="w-10 h-10 text-green-500 animate-spin mb-2" />
                    <p className="text-green-600 dark:text-green-400">جاري رفع الصورة...</p>
                  </>
                ) : (
                  <>
                    <div className="p-3 bg-green-100 dark:bg-green-900/20 rounded-full mb-3">
                      <Upload className="w-8 h-8 text-green-600 dark:text-green-400" />
                    </div>
                    <p className="font-medium text-green-700 dark:text-green-300 mb-1">اضغط لرفع صورة السليب البنكي</p>
                    <p className="text-sm text-green-600 dark:text-green-400">يُفضل صورة واضحة لسليب التحويل</p>
                  </>
                )}
                <input
                  type="file"
                  className="hidden"
                  accept="image/*"
                  onChange={(e) => handleUpload(e, setSwiftImage)}
                />
              </label>
            )}
          </div>

          <div className="p-4 bg-yellow-50 dark:bg-yellow-900/10 border border-yellow-200 dark:border-yellow-800 rounded-lg">
            <div className="flex items-start gap-3">
              <Info className="w-5 h-5 text-yellow-600 dark:text-yellow-400 flex-shrink-0" />
              <div>
                <p className="font-medium text-yellow-800 dark:text-yellow-300 mb-1">
                  تنبيه مهم
                </p>
                <p className="text-sm text-yellow-700 dark:text-yellow-400">
                  سيتم خصم المبلغ ({amount.toLocaleString()}$)
                  {transferFee > 0 && ` + تكلفة الحوالة (${transferFee.toLocaleString()}$)`}
                  = <strong>${(amount + transferFee).toLocaleString()}</strong> من الصندوق المحدد فوراً.
                </p>
                {transferFee > 0 && (
                  <p className="text-xs text-yellow-600 dark:text-yellow-500 mt-1">
                    ⚠️ تكلفة الحوالة البنكية ستضاف كتكلفة إضافية للصفقة
                  </p>
                )}
              </div>
            </div>
          </div>

          <button
            onClick={handleSaveSwift}
            disabled={!swiftImage || !selectedCashBoxId || amount > maxPrincipal}
            className="w-full py-3 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          >
            {!swiftImage ? (
              <>
                <AlertCircle className="w-5 h-5" />
                ارفع صورة السليب أولاً
              </>
            ) : !selectedCashBoxId ? (
              <>
                <AlertCircle className="w-5 h-5" />
                اختر صندوقاً مالياً
              </>
            ) : (
              <>
                <DollarSign className="w-5 h-5" />
                {transferFee > 0 ? (
                  <>تنفيذ التحويل وخصم ${amount.toLocaleString()} + ${transferFee.toLocaleString()}</>
                ) : (
                  <>تنفيذ التحويل وخصم ${amount.toLocaleString()} من الصندوق</>
                )}
              </>
            )}
          </button>
        </div>
      )}

      {/* حالة تأكيد المورد */}
      {mode === "verify" && (
        <div className="space-y-6">
          <div className="p-4 rounded-xl border border-purple-200 dark:border-purple-800 bg-purple-50/80 dark:bg-purple-900/20">
            <p className="text-sm font-semibold text-purple-900 dark:text-purple-100">
              تأكيد المورد
            </p>
            <p className="text-xs text-purple-800/90 dark:text-purple-200/90 mt-1 leading-relaxed">
              التاريخ أدناه = يوم تأكيد المورد أن الدفعة وصلته. عند الحفظ يُنشأ{" "}
              بعد التأكيد تنتقل ل<strong>قيد اليومية</strong> لتسجيل القيد يدوياً (مدين مورد / دائن صندوق) ثم الترحيل من هناك.
            </p>
            {paymentData?.amount != null && (
              <p className="text-sm font-bold text-purple-950 dark:text-purple-50 mt-2">
                المبلغ: ${Number(paymentData.amount).toLocaleString()}
              </p>
            )}
          </div>
          {/* ⭐ تاريخ تأكيد المورد */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-purple-600" />
                تاريخ تأكيد المورد
              </div>
            </label>
            <div className="relative">
              <input
                type="date"
                value={confirmationDate}
                onChange={(e) => setConfirmationDate(e.target.value)}
                className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                required
              />
              <Calendar className="absolute left-3 top-3 w-5 h-5 text-gray-400" />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              ملاحظات المورد
            </label>
            <textarea
              value={supplierNotes}
              onChange={(e) => setSupplierNotes(e.target.value)}
              className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              rows={3}
              placeholder="أضف أي ملاحظات من المورد حول هذه الدفعة..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              صورة تأكيد المورد (اختياري)
            </label>
            {supplierImage ? (
              <div className="relative">
                <img
                  src={supplierImage}
                  className="w-full h-32 object-contain rounded-lg border border-gray-300 bg-gray-50"
                  alt="صورة تأكيد المورد"
                />
                <button
                  onClick={() => setSupplierImage("")}
                  className="absolute top-2 right-2 bg-red-500 text-white p-1 rounded-full"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <label className="flex items-center justify-center w-full h-32 border-2 border-dashed border-gray-300 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                <div className="text-center">
                  <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
                  <p className="text-gray-500 dark:text-gray-400">رفع صورة التأكيد</p>
                  <p className="text-xs text-gray-400 dark:text-gray-500">مثل: إشعار استلام، بريد إلكتروني، واتساب</p>
                </div>
                <input
                  type="file"
                  className="hidden"
                  accept="image/*"
                  onChange={(e) => handleUpload(e, setSupplierImage)}
                />
              </label>
            )}
          </div>

          <div className="p-4 bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800 rounded-lg">
            <div className="flex items-start gap-3">
              <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0" />
              <div>
                <p className="font-medium text-green-800 dark:text-green-300 mb-1">
                  جاهز للتأكيد النهائي
                </p>
                <p className="text-sm text-green-700 dark:text-green-400">
                  يُحفظ تاريخ التأكيد ثم يُفتح لك قيد يومية جديد — أكمل السطور واضغط ترحيل من شاشة المحاسبة (لا ترحيل تلقائي من الصفقة).
                </p>
                {transferFee > 0 && (
                  <p className="text-xs text-green-600 dark:text-green-500 mt-1">
                    ⭐ تم احتساب تكلفة الحوالة: ${transferFee.toLocaleString()}
                  </p>
                )}
              </div>
            </div>
          </div>

          <button
            onClick={handleConfirmSupplier}
            className="w-full py-3 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            <CheckCircle className="w-5 h-5" />
            تأكيد استلام الدفعة من المورد
          </button>
        </div>
      )}
    </div>
  );
};