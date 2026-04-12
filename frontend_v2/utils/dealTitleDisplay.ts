/** نطاقات عربية شائعة في النصوص */
const AR_RE =
    /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/;

export type DealTitleSqlInput = {
    description?: string | null;
    notes?: string | null;
    /** رقم العرض / PI — يُعرض قبل رقم الصفقة إذا كان مختلفاً عنه */
    original_offer_number?: string | null;
    ref_number?: string | null;
};

/**
 * نص إنجليزي يصف شروط دفع/بنكيّة وليس عنوان صفقة — لا يُعرض كعنوان رئيسي.
 */
export function isEnglishPaymentOrLegalBoilerplate(s: string): boolean {
    const t = String(s || "").trim();
    if (!t || AR_RE.test(t)) return false;
    const lower = t.toLowerCase();
    if (/\bterms\s+of\s+payment\b/.test(lower)) return true;
    if (/\bbank\s+charges?\b/.test(lower) && t.length > 20) return true;
    if (
        /\b(?:\d{1,2}\s*%|percent)\s*(?:deposit|advance|down)\b/.test(lower) &&
        /\b(?:before\s+)?delivery\b/.test(lower)
    ) {
        return true;
    }
    if (
        /\bdeposit\b/.test(lower) &&
        /\b(?:rest|balance|remaining)\b/.test(lower) &&
        /\bpayment\b/.test(lower) &&
        t.length > 30
    ) {
        return true;
    }
    if (/\bletter\s+of\s+credit\b/.test(lower) && t.length > 25) return true;
    return false;
}

function truncateTitle(s: string, max: number): string {
    if (s.length <= max) return s;
    return `${s.slice(0, max - 1)}…`;
}

/**
 * وصف قصير للعرض في النماذج (dealDescription) من أعمدة SQL.
 * لا يضع شروط الدفع الإنجليزية من description قبل السطر العربي في الملاحظات.
 */
export function dealSummaryDescriptionFromSql(
    description?: string | null,
    notes?: string | null
): string | undefined {
    const desc = String(description || "").trim();
    const fromNotes = firstArabicLineFromNotes(notes);
    if (desc && AR_RE.test(desc)) return truncateTitle(desc, 255);
    if (fromNotes) return truncateTitle(fromNotes, 255);
    if (desc && !isEnglishPaymentOrLegalBoilerplate(desc)) return truncateTitle(desc, 255);
    return undefined;
}

/**
 * قديم: حقل «وصف الصفقة» كان يُربط بـ original_offer_number.
 * إن كان description فارغاً و«العرض» نصاً تعريفياً (مثل عربي قصير) نعرضه كوصف دون تعديل قاعدة البيانات.
 */
export function legacyDescriptionFromMisfiledOfferNumber(
    offerRaw?: string | null
): string | undefined {
    const offer = String(offerRaw || "").trim();
    if (!offer || /^D-\d+$/i.test(offer)) return undefined;
    if (isEnglishPaymentOrLegalBoilerplate(offer)) return undefined;
    if (/^(OF|PO|QT|QU|INV)[-#/\s]/i.test(offer)) return undefined;
    if (/^\d{6,}$/.test(offer)) return undefined;
    if (offer.length > 200) return undefined;
    return truncateTitle(offer, 255);
}

/**
 * عنوان للعرض في القوائم والمودالات:
 * 1) description إذا فيه عربي
 * 2) أول سطر عربي في notes (يتخطى مقدمات إنجليزية مثل TERMS OF PAYMENT)
 * 3) description إنجليزي غير «شروط دفع»
 * 4) original_offer_number إن وُجد ولم يكن نفس رقم الصفقة
 * 5) رقم الصفقة
 */
export function effectiveDealTitleForDisplay(row: DealTitleSqlInput): string {
    const desc = String(row.description || "").trim();
    const notes = String(row.notes || "").trim();
    if (desc && AR_RE.test(desc)) {
        return truncateTitle(desc, 220);
    }
    if (notes) {
        for (const line of notes.split(/\r?\n/)) {
            const t = line.trim();
            if (t && AR_RE.test(t)) {
                return truncateTitle(t, 220);
            }
        }
    }
    if (desc && !isEnglishPaymentOrLegalBoilerplate(desc)) {
        return truncateTitle(desc, 220);
    }
    const ref = String(row.ref_number || "").trim();
    const offer = String(row.original_offer_number || "").trim();
    if (
        offer &&
        offer.toLowerCase() !== ref.toLowerCase() &&
        !/^d-\d+$/i.test(offer)
    ) {
        return truncateTitle(offer, 220);
    }
    return ref || "—";
}

export function hasDedicatedShortDescription(row: DealTitleSqlInput): boolean {
    const desc = String(row.description || "").trim();
    if (!desc) return false;
    if (AR_RE.test(desc)) return true;
    return !isEnglishPaymentOrLegalBoilerplate(desc);
}

/** أول سطر في الملاحظات يحتوي عربية — بدون الرجوع لرقم الصفقة */
export function firstArabicLineFromNotes(notes?: string | null): string | undefined {
    const notesStr = String(notes || "").trim();
    if (!notesStr) return undefined;
    for (const line of notesStr.split(/\r?\n/)) {
        const t = line.trim();
        if (t && AR_RE.test(t)) {
            return t.length > 220 ? `${t.slice(0, 217)}…` : t;
        }
    }
    return undefined;
}
