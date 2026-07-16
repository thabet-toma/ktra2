interface PurchaseInvoiceFeeEditorInput {
  readOnly: boolean;
  viewMode: boolean;
  isPosted: boolean;
  isHistorical: boolean;
}

interface PurchaseInvoiceFeeEditorState {
  canAdd: boolean;
  requiresEdit: boolean;
  message: string | null;
}

export const getPurchaseInvoiceFeeEditorState = ({
  readOnly,
  viewMode,
  isPosted,
  isHistorical,
}: PurchaseInvoiceFeeEditorInput): PurchaseInvoiceFeeEditorState => {
  if (isHistorical) {
    return { canAdd: false, requiresEdit: false, message: "الفاتورة التاريخية للقراءة فقط ولا تقبل بنوداً جديدة." };
  }
  if (readOnly) {
    return { canAdd: false, requiresEdit: false, message: "هذه الفاتورة مفتوحة للقراءة فقط." };
  }
  if (isPosted) {
    return { canAdd: false, requiresEdit: false, message: "الفاتورة مرحّلة؛ استخدم «تراجع عن الترحيل» أولاً لإضافة ضريبة أو رسم." };
  }
  return { canAdd: true, requiresEdit: viewMode, message: null };
};
