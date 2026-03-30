import React, { useState, useEffect } from "react";
import { Deal, DealPayment, DealInstallment } from "@/types";
import { PaymentRegistration } from "./PaymentRegistration";
import { Plus, DollarSign, AlertCircle, Info, CreditCard, CheckCircle2, Trash2, Clock } from "lucide-react";

interface DealPaymentListProps {
  deal: Partial<Deal>;
  currentUser: any;
  onPaymentOperation: (
    operation: "claim" | "swift" | "add" | "confirm" | "cancel",
    paymentType: string,
    data: any,
    paymentId?: string
  ) => void;
  onConfirmSupplier: (data: any) => void;
  items?: any[];
  // ⭐ جديد: معالجة نظام الدفعات
  onUpdateInstallments?: (installments: DealInstallment[]) => void;
  onLinkPaymentToInstallment?: (paymentId: string, installmentId: string, amountPaid: number) => void;
}

export const DealPaymentList: React.FC<DealPaymentListProps> = ({
  deal,
  currentUser,
  onPaymentOperation,
  onConfirmSupplier,
}) => {
  const payments = deal.payments || [];

  if (payments.length === 0) {
    return (
      <div className="text-center py-8">
        <div className="w-16 h-16 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center mx-auto mb-4">
          <Clock className="w-8 h-8 text-gray-400" />
        </div>
        <p className="text-gray-600 dark:text-gray-400">
          لم يتم تسجيل أي مدفوعات بعد
        </p>
        <p className="text-sm text-gray-500 dark:text-gray-500 mt-1">
          ابدأ بدفع أول دفعة من جدول الدفعات أعلاه
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h4 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
        سجل المدفوعات
      </h4>

      {payments.map((payment, index) => (
        <div key={payment.id} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <div className="flex justify-between items-center mb-3">
            <div>
              <h5 className="font-medium text-gray-900 dark:text-white">
                {payment.type}
              </h5>
              <p className="text-sm text-gray-500">
                {new Date(payment.paymentDate).toLocaleDateString('ar-EG')}
              </p>
            </div>
            <div className="text-right">
              <div className="font-bold text-lg text-gray-900 dark:text-white">
                ${payment.amount?.toLocaleString()}
              </div>
              <div className={`text-xs px-2 py-1 rounded-full ${payment.confirmedBySupplier
                ? 'bg-green-100 text-green-800'
                : payment.bankSwiftImage
                  ? 'bg-blue-100 text-blue-800'
                  : 'bg-yellow-100 text-yellow-800'
                }`}>
                {payment.confirmedBySupplier ? 'مؤكدة' :
                  payment.bankSwiftImage ? 'تم الدفع' : 'مطالبة'}
              </div>
            </div>
          </div>

          {/* ملخص سريع */}
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-gray-500">الدفعة:</span>
              <span className="font-medium mr-2">
                {payment.installmentNumber ? `دفعة ${payment.installmentNumber}` : 'عام'}
              </span>
            </div>
            <div>
              <span className="text-gray-500">المورد:</span>
              <span className={`font-medium mr-2 ${payment.confirmedBySupplier ? 'text-green-600' : 'text-yellow-600'
                }`}>
                {payment.confirmedBySupplier ? 'مؤكد' : 'بانتظار'}
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};