import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Wallet, ArrowRightLeft, Pencil, Layers } from 'lucide-react';
import { CashBox } from '../../types';
import { cashBoxesService } from '../../services/firestoreService';
import { accountingApi, type CashBoxLedgerLink } from '../../services/accountingApi';
import { CreateCashBoxModal } from './modals/CreateCashBoxModal';
import { EditCashBoxModal } from './modals/EditCashBoxModal';
import { FundFxBoxModal } from './modals/FundFxBoxModal';
import { formatDateValue } from "../../utils/formatDate";

interface CashBoxListProps {
    onSelectCashBox: (cashBox: CashBox) => void;
}

export const CashBoxList: React.FC<CashBoxListProps> = ({ onSelectCashBox }) => {
    const [cashBoxes, setCashBoxes] = useState<CashBox[]>([]);
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [editBox, setEditBox] = useState<CashBox | null>(null);
    const [loading, setLoading] = useState(true);
    const [ledgerByExt, setLedgerByExt] = useState<Record<string, CashBoxLedgerLink>>({});
    // صندوق العملة الأجنبية (الدولار) المراد تمويله بطبقات FIFO
    const [fundBox, setFundBox] = useState<CashBoxLedgerLink | null>(null);
    const ilsBoxes = (Object.values(ledgerByExt) as CashBoxLedgerLink[]).filter((l) => l.currency_code === 'ILS');

    const refreshLedgers = useCallback(async () => {
        try {
            const rows = await accountingApi.getCashBoxLedgers();
            const m: Record<string, CashBoxLedgerLink> = {};
            for (const r of rows) {
                if (r.external_id != null && r.external_id !== '') {
                    m[String(r.external_id)] = r;
                }
            }
            setLedgerByExt(m);
        } catch {
            setLedgerByExt({});
        }
    }, []);

    useEffect(() => {
        void refreshLedgers();
    }, [refreshLedgers]);

    useEffect(() => {
        const unsubscribe = cashBoxesService.subscribeToCashBoxes((data) => {
            setCashBoxes(data);
            setLoading(false);
        });
        return () => unsubscribe();
    }, []);

    if (loading) {
        return <div className="flex justify-center items-center h-64">Loading...</div>;
    }

    return (
        <div className="p-6">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold dark:text-white">صناديق الكاش</h1>
                    <p className="text-[var(--color-text-muted)]">
                        كل صندوق له حساب نقدية في شجرة المحاسبة بنفس الاسم — يُستخدم في قيود الدفع.
                    </p>
                </div>
                <button
                    onClick={() => setIsCreateModalOpen(true)}
                    className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
                >
                    <Plus className="w-5 h-5 ml-2" />
                    صندوق جديد
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {cashBoxes.map((box) => (
                    <div
                        key={box.id}
                        className="bg-[var(--color-surface)] rounded-xl shadow-sm border border-[var(--color-border)] p-6 hover:shadow-md transition cursor-pointer"
                        onClick={() => onSelectCashBox(box)}
                    >
                        <div className="flex justify-between items-start mb-4">
                            <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                                <Wallet className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                            </div>
                            <div className="flex flex-col items-end gap-1">
                                <div className="flex items-center gap-1">
                                    {/* تمويل FIFO — لصناديق العملة الأجنبية المربوطة بالشجرة (مثل صندوق الدولار) */}
                                    {ledgerByExt[box.id] && ledgerByExt[box.id].currency_code !== 'ILS' && (
                                        <button
                                            type="button"
                                            title="تمويل (FIFO): إيداع/تحويل"
                                            className="p-2 rounded-lg text-green-700 hover:bg-green-50 dark:hover:bg-gray-700"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                setFundBox(ledgerByExt[box.id]);
                                            }}
                                        >
                                            <Layers className="w-4 h-4" />
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        title="تعديل الصندوق"
                                        className="p-2 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setEditBox(box);
                                        }}
                                    >
                                        <Pencil className="w-4 h-4" />
                                    </button>
                                </div>
                                <span
                                    className={`px-2 py-1 text-xs font-semibold rounded-full ${
                                        box.currency === "USD"
                                            ? "bg-green-100 text-green-800"
                                            : box.currency === "ILS"
                                              ? "bg-blue-100 text-blue-800"
                                              : "bg-[var(--color-surface-2)] text-[var(--color-primary)]"
                                    }`}
                                >
                                    {box.currency}
                                </span>
                            </div>
                        </div>

                        <h3 className="text-lg font-bold dark:text-white mb-1">{box.name}</h3>
                        {ledgerByExt[box.id] ? (
                            <p className="text-xs text-green-700 dark:text-green-400 mb-1 font-medium">
                                حساب الشجرة:{' '}
                                <span className="font-mono">{ledgerByExt[box.id].account_code}</span>
                            </p>
                        ) : (
                            <p className="text-xs text-[var(--color-text-muted)] mb-1">
                                بلا حساب في الشجرة
                            </p>
                        )}
                        <p className="text-sm text-[var(--color-text-muted)] mb-4">تم الإنشاء: {formatDateValue(box.createdAt)}</p>

                        <div className="flex justify-between items-end border-t border-[var(--color-border)] pt-4">
                            <div>
                                <p className="text-xs text-[var(--color-text-muted)] mb-1">الرصيد الحالي</p>
                                <p className="text-2xl font-bold text-[var(--color-text)]">
                                    {/* task16 E16: الرصيد من دفتر الأستاذ (إن وُجد حساب مربوط) بدل الرصيد المخزّن الذي يبقى صفراً */}
                                    {(ledgerByExt[box.id]?.balance != null
                                        ? Number(ledgerByExt[box.id].balance)
                                        : box.currentBalance
                                    ).toLocaleString()} <span className="text-sm font-normal text-[var(--color-text-muted)]">{box.currency}</span>
                                </p>
                            </div>
                            <div className="text-blue-600 hover:text-blue-700 text-sm font-medium flex items-center">
                                كشف حساب <ArrowRightLeft className="w-4 h-4 mr-1" />
                            </div>
                        </div>
                    </div>
                ))}

                {cashBoxes.length === 0 && (
                    <div className="col-span-full flex flex-col items-center justify-center p-12 text-[var(--color-text-muted)] border-2 border-dashed border-[var(--color-border)] rounded-xl">
                        <Wallet className="w-12 h-12 mb-4 opacity-50" />
                        <p>لا توجد صناديق كاش حالياً</p>
                        <button
                            onClick={() => setIsCreateModalOpen(true)}
                            className="mt-4 text-blue-600 font-medium hover:underline"
                        >
                            إنشاء أول صندوق
                        </button>
                    </div>
                )}
            </div>

            <CreateCashBoxModal
                isOpen={isCreateModalOpen}
                onClose={() => {
                    setIsCreateModalOpen(false);
                    void refreshLedgers();
                }}
            />
            <EditCashBoxModal
                isOpen={editBox !== null}
                cashBox={editBox}
                onClose={() => {
                    setEditBox(null);
                    void refreshLedgers();
                }}
                onLedgersMaybeChanged={() => void refreshLedgers()}
            />
            <FundFxBoxModal
                isOpen={fundBox !== null}
                ledger={fundBox}
                ilsBoxes={ilsBoxes}
                onClose={() => setFundBox(null)}
                onFunded={() => void refreshLedgers()}
            />
        </div>
    );
};
