import {
    collection, query, where, orderBy, limit,
    addDoc, updateDoc, doc, getDocs, getDoc,
    Timestamp, serverTimestamp, onSnapshot,
    runTransaction,
    db
} from './sqlApiClient';
import { Shipment, ShipmentInstallment, ShipmentPayment, ShipmentStatus } from '../types';

// Helper function to recursively remove undefined values (Firestore rejects them)
const scrubObject = (obj: any): any => {
    if (Array.isArray(obj)) return obj.map(scrubObject);
    if (obj !== null && typeof obj === 'object' && !(obj instanceof Timestamp)) {
        if (obj.type === 'serverTimestamp') {
            return serverTimestamp();
        }
        return Object.fromEntries(
            Object.entries(obj)
                .filter(([_, v]) => v !== undefined)
                .map(([k, v]) => [k, scrubObject(v)])
        );
    }
    return obj;
};

export const shipmentsPaymentService = {
    // حفظ الدفعات للشحنة
    async saveShipmentInstallments(
        shipmentId: string,
        installments: ShipmentInstallment[],
        installmentPlanEnabled: boolean,
        userId: string,
        userName: string
    ): Promise<void> {
        try {
            const shipmentRef = doc(db, 'shipments', shipmentId);
            const shipmentDoc = await getDoc(shipmentRef);

            if (!shipmentDoc.exists()) {
                throw new Error('الشحنة غير موجودة');
            }

            const shipment = shipmentDoc.data() as Shipment;
            const totalAmount = shipment.totalShippingCostUsd || 0;

            const updatedInstallments = installments.map(inst => {
                const amount = Math.round(((inst.percentage || 0) / 100) * totalAmount * 100) / 100;
                return {
                    ...inst,
                    amount: amount,
                    updatedAt: serverTimestamp(),
                    createdAt: inst.createdAt || serverTimestamp()
                };
            });

            await updateDoc(shipmentRef, scrubObject({
                installments: updatedInstallments,
                installmentPlanEnabled: installmentPlanEnabled,
                updatedAt: serverTimestamp(),
                updatedBy: userId
            }));

            console.log('✅ تم حفظ دفعات الشحنة:', {
                shipmentId,
                count: updatedInstallments.length,
                enabled: installmentPlanEnabled
            });

        } catch (error) {
            console.error('Error saving shipment installments:', error);
            throw error;
        }
    },

    // إضافة دفعة جديدة (مطالبة)
    async addPayment(
        shipmentId: string,
        payment: Omit<ShipmentPayment, 'id'>,
        userId: string,
        userName: string,
        userRole: string
    ): Promise<string> {
        try {
            const shipmentRef = doc(db, 'shipments', shipmentId);
            const shipmentDoc = await getDoc(shipmentRef);

            if (!shipmentDoc.exists()) {
                throw new Error('الشحنة غير موجودة');
            }

            const shipment = shipmentDoc.data() as Shipment;
            const paymentId = crypto.randomUUID();

            const cleanPayment = Object.fromEntries(
                Object.entries(payment).filter(([_, v]) => v !== undefined)
            );

            const newPayment: ShipmentPayment = {
                ...cleanPayment,
                id: paymentId
            } as ShipmentPayment;

            const updatedPayments = [...(shipment.payments || []), newPayment];

            // حساب المبلغ المتبقي
            const totalPaid = updatedPayments.reduce((sum, p) => {
                if (p.bankSwiftImage || p.confirmedBySupplier) return sum + (p.amount || 0);
                return sum;
            }, 0);
            const remainingAmount = shipment.totalShippingCostUsd - totalPaid;

            // تحديث حالة الشحنة
            let newStatus: ShipmentStatus = shipment.status;
            if (shipment.status === 'draft') {
                newStatus = 'payment_pending';
            }

            // تحديث حالة الدفعات (Installments)
            const updatedInstallments = (shipment.installments || []).map(inst => {
                const instPayments = updatedPayments.filter(p => p.installmentId === inst.id);
                const instTotalPaid = instPayments.reduce((sum, p) => {
                    if (p.bankSwiftImage || p.confirmedBySupplier) return sum + (p.amount || 0);
                    return sum;
                }, 0);

                let instStatus: 'unpaid' | 'partially_paid' | 'paid' | 'cancelled' = 'unpaid';
                if (inst.status === 'cancelled') {
                    instStatus = 'cancelled';
                } else {
                    if (instTotalPaid >= inst.amount * 0.99) instStatus = 'paid';
                    else if (instTotalPaid > 0) instStatus = 'partially_paid';
                }

                return {
                    ...inst,
                    status: instStatus,
                    paymentData: {
                        ...inst.paymentData,
                        amountPaid: instTotalPaid,
                        paymentId: instPayments.length > 0 ? instPayments[instPayments.length - 1].id : undefined,
                        paymentDate: instPayments.length > 0 ? instPayments[instPayments.length - 1].paymentDate : undefined
                    }
                };
            });

            const updateData: any = {
                payments: updatedPayments,
                installments: updatedInstallments,
                remainingAmount,
                status: newStatus,
                updatedAt: serverTimestamp(),
                updatedBy: userId
            };

            await updateDoc(shipmentRef, scrubObject(updateData));

            return paymentId;
        } catch (error) {
            console.error('Error adding shipment payment:', error);
            throw error;
        }
    },

    // رفع السليب مع الخصم من الصندوق
    async updatePaymentWithSwift(
        shipmentId: string,
        paymentId: string,
        updates: Partial<ShipmentPayment>,
        userId: string,
        userName: string,
        userRole: string,
        cashBoxId: string
    ): Promise<void> {
        try {
            const shipmentRef = doc(db, 'shipments', shipmentId);

            if (!cashBoxId) {
                throw new Error('يجب اختيار صندوق مالي');
            }

            if (!updates.bankSwiftImage) {
                throw new Error('يجب رفع صورة السليب');
            }

            await runTransaction(db, async (transaction) => {
                const shipmentDoc = await transaction.get(shipmentRef);
                if (!shipmentDoc.exists()) {
                    throw new Error('الشحنة غير موجودة');
                }

                const shipmentData = shipmentDoc.data() as Shipment;
                const payments = shipmentData.payments || [];
                const paymentIndex = payments.findIndex(p => p.id === paymentId);
                if (paymentIndex === -1) {
                    throw new Error('الدفعة غير موجودة');
                }

                const payment = payments[paymentIndex];

                if (payment.cashBoxWithdrawalAt) {
                    throw new Error('تم خصم هذه الدفعة بالفعل من الصندوق');
                }

                const cashBoxRef = doc(db, 'cashBoxes', cashBoxId);
                const cashBoxDoc = await transaction.get(cashBoxRef);
                if (!cashBoxDoc.exists()) {
                    throw new Error('الصندوق المالي غير موجود');
                }

                const cashBox = cashBoxDoc.data() as any;

                const paymentAmount = updates.amount || payment.amount || 0;
                const transferCost = updates.transferCost || payment.transferCost || 0;
                const totalToWithdraw = paymentAmount + transferCost;

                const newBalance = cashBox.currentBalance - totalToWithdraw;
                const now = new Date().toISOString();

                // إنشاء حركات الصندوق
                const transactionsCol = collection(db, 'cashBoxTransactions');

                const paymentTransactionRef = doc(transactionsCol);
                const paymentTransaction = {
                    id: paymentTransactionRef.id,
                    cashBoxId: cashBoxId,
                    type: 'withdrawal',
                    amount: paymentAmount,
                    currency: cashBox.currency,
                    description: `دفع شحنة ${shipmentData.shipmentNumber || shipmentId}`,
                    reference: `SHIPMENT-${shipmentData.shipmentNumber || shipmentId}-PAYMENT-${paymentId}`,
                    date: now,
                    createdBy: userName,
                    userId: userId,
                    createdAt: now,
                    balanceAfter: cashBox.currentBalance - paymentAmount,
                    relatedShipmentId: shipmentId,
                    relatedPaymentId: paymentId,
                    shipmentNumber: shipmentData.shipmentNumber,
                    paymentDate: updates.paymentDate || new Date().toISOString(),
                    usdToIls: updates.usdToIls
                };

                transaction.set(paymentTransactionRef, scrubObject(paymentTransaction));

                let transferTransactionId = null;
                if (transferCost > 0) {
                    const transferTransactionRef = doc(transactionsCol);
                    transferTransactionId = transferTransactionRef.id;
                    const transferTransaction = {
                        id: transferTransactionId,
                        cashBoxId: cashBoxId,
                        type: 'withdrawal',
                        amount: transferCost,
                        currency: cashBox.currency,
                        description: `تكلفة حوالة شحنة ${shipmentData.shipmentNumber || shipmentId}`,
                        reference: `SHIPMENT-${shipmentData.shipmentNumber || shipmentId}-PAYMENT-${paymentId}-TRANSFER`,
                        date: now,
                        createdBy: userName,
                        userId: userId,
                        createdAt: now,
                        balanceAfter: newBalance,
                        relatedShipmentId: shipmentId,
                        relatedPaymentId: paymentId,
                        shipmentNumber: shipmentData.shipmentNumber
                    };
                    transaction.set(transferTransactionRef, scrubObject(transferTransaction));
                }

                transaction.update(cashBoxRef, scrubObject({
                    currentBalance: newBalance,
                    updatedAt: now,
                    lastTransactionId: paymentTransactionRef.id,
                    lastTransactionDate: now
                }));

                const updatedPaymentData: any = {
                    ...scrubObject(updates),
                    cashBoxId: cashBoxId,
                    cashBoxName: cashBox.name,
                    cashBoxWithdrawalAt: now,
                    cashBoxWithdrawalBy: userName,
                    cashBoxTransactionIds: [
                        paymentTransactionRef.id,
                        ...(transferTransactionId ? [transferTransactionId] : [])
                    ],
                    _cashBoxSettled: true,
                    shipmentNumber: shipmentData.shipmentNumber
                };

                const updatedPayment = {
                    ...payment,
                    ...updatedPaymentData
                };

                const cleanUpdatedPayment = scrubObject(updatedPayment);
                const newPayments = [...payments];
                newPayments[paymentIndex] = cleanUpdatedPayment;

                const totalPaid = newPayments.reduce((sum: number, p: any) => {
                    if (p.bankSwiftImage) return sum + (p.amount || 0);
                    return sum;
                }, 0);

                const remainingAmount = (shipmentData.totalShippingCostUsd || 0) - totalPaid;

                // تحديث حالة الدفعات
                let updatedInstallments = shipmentData.installments || [];
                updatedInstallments = updatedInstallments.map(inst => {
                    const instPayments = newPayments.filter(p => p.installmentId === inst.id);
                    const instTotalPaid = instPayments.reduce((sum, p) => {
                        if (p.bankSwiftImage || p.confirmedBySupplier) return sum + (p.amount || 0);
                        return sum;
                    }, 0);

                    let instStatus: 'unpaid' | 'partially_paid' | 'paid' | 'cancelled' = 'unpaid';
                    if (inst.status === 'cancelled') {
                        instStatus = 'cancelled';
                    } else {
                        if (instTotalPaid >= inst.amount * 0.99) instStatus = 'paid';
                        else if (instTotalPaid > 0) instStatus = 'partially_paid';
                    }

                    return {
                        ...inst,
                        status: instStatus,
                        paymentData: {
                            ...inst.paymentData,
                            amountPaid: instTotalPaid,
                            paymentId: instPayments.length > 0 ? instPayments[instPayments.length - 1].id : undefined,
                            paymentDate: instPayments.length > 0 ? instPayments[instPayments.length - 1].paymentDate : undefined
                        }
                    };
                });

                transaction.update(shipmentRef, scrubObject({
                    payments: newPayments,
                    installments: updatedInstallments,
                    remainingAmount: remainingAmount,
                    updatedAt: now,
                    updatedBy: userId
                }));
            });

        } catch (error) {
            console.error('Error updating shipment payment with swift:', error);
            throw error;
        }
    },

    // تأكيد الدفعة من وكيل الشحن
    async confirmPayment(
        shipmentId: string,
        paymentId: string,
        userId: string,
        userName: string,
        userRole: string,
        confirmationImage?: string,
        notes?: string,
        manualConfirmationDate?: string
    ): Promise<void> {
        try {
            const shipmentRef = doc(db, 'shipments', shipmentId);

            await runTransaction(db, async (transaction) => {
                const shipmentDoc = await transaction.get(shipmentRef);
                if (!shipmentDoc.exists()) throw new Error('الشحنة غير موجودة');

                const shipmentData = shipmentDoc.data() as Shipment;
                const payments = shipmentData.payments || [];
                const paymentIndex = payments.findIndex(p => p.id === paymentId);
                if (paymentIndex === -1) throw new Error('الدفعة غير موجودة');

                const payment = payments[paymentIndex] as any;

                if (payment.cashBoxWithdrawalAt) {
                    console.log('الدفعة تم خصمها بالفعل عند رفع السليب');
                } else if (payment.bankSwiftImage && !payment.cashBoxWithdrawalAt) {
                    throw new Error('يجب خصم المبلغ من الصندوق أولاً عند رفع السليب قبل تأكيد وكيل الشحن');
                }

                const confirmationDate = manualConfirmationDate || new Date().toISOString();

                const updatedPayment = {
                    ...payment,
                    confirmedBySupplier: true,
                    confirmedAt: confirmationDate,
                    paymentConfirmationDate: confirmationDate,
                    confirmedBy: userId,
                    supplierConfirmationImage: confirmationImage,
                    supplierNotes: notes
                };

                const newPayments = [...payments];
                newPayments[paymentIndex] = updatedPayment;

                let updatedInstallments = shipmentData.installments || [];
                if (payment.installmentId) {
                    updatedInstallments = updatedInstallments.map(inst => {
                        if (inst.id === payment.installmentId) {
                            const totalPaid = (inst.paymentData?.amountPaid || 0);
                            const isFullyPaid = totalPaid >= (inst.amount * 0.99);
                            return {
                                ...inst,
                                status: isFullyPaid ? 'paid' : 'partially_paid',
                                paymentData: {
                                    ...inst.paymentData,
                                    paymentConfirmationDate: confirmationDate
                                }
                            };
                        }
                        return inst;
                    });
                }

                const now = new Date().toISOString();
                transaction.update(shipmentRef, {
                    payments: newPayments,
                    installments: updatedInstallments,
                    updatedAt: now,
                    updatedBy: userId
                });
            });
        } catch (error) {
            console.error('Error confirming shipment payment:', error);
            throw error;
        }
    },

    // إلغاء دفعة
    async cancelPayment(
        shipmentId: string,
        paymentId: string,
        userId: string,
        userName: string,
        userRole: string
    ): Promise<void> {
        try {
            const shipmentRef = doc(db, 'shipments', shipmentId);
            const shipmentDoc = await getDoc(shipmentRef);

            if (!shipmentDoc.exists()) {
                throw new Error('الشحنة غير موجودة');
            }

            const shipment = shipmentDoc.data() as Shipment;
            const payments = shipment.payments || [];

            const updatedPayments = payments.filter(p => p.id !== paymentId);

            const totalPaid = updatedPayments.reduce((sum, p) => {
                if (p.bankSwiftImage || p.confirmedBySupplier) return sum + (p.amount || 0);
                return sum;
            }, 0);
            const remainingAmount = shipment.totalShippingCostUsd - totalPaid;

            await updateDoc(shipmentRef, scrubObject({
                payments: updatedPayments,
                remainingAmount,
                updatedAt: serverTimestamp(),
                updatedBy: userId
            }));

        } catch (error) {
            console.error('Error canceling shipment payment:', error);
            throw error;
        }
    },

    // تحديث حالة الشحنة
    async updateShipmentStatus(
        shipmentId: string,
        newStatus: ShipmentStatus,
        userId: string,
        userName: string
    ): Promise<void> {
        try {
            const shipmentRef = doc(db, 'shipments', shipmentId);

            await updateDoc(shipmentRef, scrubObject({
                status: newStatus,
                updatedAt: serverTimestamp(),
                updatedBy: userId
            }));

        } catch (error) {
            console.error('Error updating shipment status:', error);
            throw error;
        }
    }
};
