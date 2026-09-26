/**
 * نصوص المستند المرحَّل (`core/posted_text.py`): الملاحظة — ورقم فاتورة المورد لفاتورة
 * الشراء — تُعدَّل بعد الترحيل وحدها؛ المبالغ والحسابات والتاريخ والطرف مقفلةٌ والخادم
 * يرفض غيرها، وكلُّ حفظٍ في سجلّ النشاط بقيمته قبل/بعد.
 *
 * `PostedTextFields` نموذجٌ داخل محرّر المستند بزرّ «حفظ الملاحظة»، و`PostedTextDialog`
 * نافذته لقوائم السندات والدفعات التي لا محرّر لها.
 */
import React, { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { humanizeThrown } from "../../utils/drfError";
import { clientLogger } from "../../services/logger";
import { savePostedText, type PostedTextDoc } from "../../services/postedTextApi";
import { PaymentVoucherModal } from "../sales/PaymentVoucherParts";

export interface PostedTextField {
  key: string;
  label: string;
  value?: string | null;
  multiline?: boolean;
}

type Values = Record<string, string>;

const initialOf = (fields: PostedTextField[]): Values =>
  Object.fromEntries(fields.map((f) => [f.key, f.value ?? ""]));

function usePostedText(doc: PostedTextDoc, fields: PostedTextField[], onSaved?: (values: Values) => void) {
  const initial = useMemo(() => initialOf(fields), [fields]);
  const initialKey = JSON.stringify(initial);
  const [values, setValues] = useState<Values>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // المستند أُعيد تحميله: القيم الجديدة تحلّ محلّ المحرَّر غير المحفوظ.
  useEffect(() => { setValues(JSON.parse(initialKey) as Values); }, [initialKey]);

  const dirty = fields.some((f) => (values[f.key] ?? "") !== (initial[f.key] ?? ""));

  const save = async (): Promise<boolean> => {
    if (!dirty || saving) return false;
    setSaving(true);
    setError(null);
    try {
      await savePostedText(doc, values);
      clientLogger.info("posted_text.save", { kind: doc.kind, fields: Object.keys(values) });
      setSaved(true);
      onSaved?.(values);
      return true;
    } catch (e: unknown) {
      setError(humanizeThrown(e, "تعذّر حفظ الملاحظة"));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const setField = (key: string, value: string) => {
    setSaved(false);
    setValues((prev) => ({ ...prev, [key]: value }));
  };

  return { values, setField, dirty, saving, error, saved, save };
}

const inputClass =
  "w-full rounded border border-[var(--ktra-border)] bg-[var(--ktra-surface)] px-2 py-1 text-[12px] text-[var(--ktra-ink)]";

function FieldInputs({ fields, values, setField, disabled }: {
  fields: PostedTextField[];
  values: Values;
  setField: (key: string, value: string) => void;
  disabled?: boolean;
}) {
  return (
    <>
      {fields.map((f) => (
        <label key={f.key} className="flex flex-col gap-1 text-[12px]">
          <span className="text-[var(--ktra-ink-soft)]">{f.label}</span>
          {f.multiline ? (
            <textarea
              className={`${inputClass} min-h-[72px]`}
              value={values[f.key] ?? ""}
              disabled={disabled}
              onChange={(e) => setField(f.key, e.target.value)}
            />
          ) : (
            <input
              className={inputClass}
              value={values[f.key] ?? ""}
              disabled={disabled}
              onChange={(e) => setField(f.key, e.target.value)}
            />
          )}
        </label>
      ))}
    </>
  );
}

const POSTED_HINT = "المستند مرحَّل: الملاحظة وحدها تُعدَّل — المبالغ والحسابات مقفلة، والتعديل يُسجَّل في سجلّ النشاط.";

/** داخل محرّر المستند المرحَّل: الحقول النصّية وحدها قابلةٌ للتحرير، بزرّ «حفظ الملاحظة». */
export const PostedTextFields: React.FC<{
  doc: PostedTextDoc;
  fields: PostedTextField[];
  onSaved?: (values: Values) => void;
  disabled?: boolean;
}> = ({ doc, fields, onSaved, disabled }) => {
  const { values, setField, dirty, saving, error, saved, save } = usePostedText(doc, fields, onSaved);
  return (
    <div className="flex flex-col gap-2" data-testid="posted-text-fields">
      <FieldInputs fields={fields} values={values} setField={setField} disabled={disabled || saving} />
      {error && <div className="ktra-banner ktra-banner--err">{error}</div>}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="ktra-toolbtn inline-flex items-center gap-1"
          disabled={disabled || !dirty || saving}
          onClick={() => void save()}
        >
          {saving && <Loader2 className="h-3 w-3 animate-spin" />} حفظ الملاحظة
        </button>
        {saved && !dirty && <span className="text-[11px] text-[var(--ktra-ok,#2d7d46)]">✓ حُفظت</span>}
        <span className="text-[11px] text-[var(--ktra-ink-soft)]">{POSTED_HINT}</span>
      </div>
    </div>
  );
};

/** نافذة الملاحظة لصفٍّ في قائمة (سند، دفعة) — لا محرّر للمستند نفسه. */
export const PostedTextDialog: React.FC<{
  doc: PostedTextDoc;
  title: string;
  fields: PostedTextField[];
  onClose: () => void;
  onSaved?: (values: Values) => void;
  /** مسودة: تعديلٌ عاديّ بلا تنبيه الترحيل. */
  posted?: boolean;
}> = ({ doc, title, fields, onClose, onSaved, posted = true }) => {
  const { values, setField, dirty, saving, error, save } = usePostedText(doc, fields, onSaved);
  return (
    <PaymentVoucherModal
      title={title}
      error={error}
      submitting={saving}
      disabled={!dirty}
      submitLabel="حفظ الملاحظة"
      onClose={onClose}
      onSubmit={() => { void save().then((ok) => { if (ok) onClose(); }); }}
    >
      <div className="flex flex-col gap-2">
        <FieldInputs fields={fields} values={values} setField={setField} disabled={saving} />
        {posted && <p className="text-[11px] text-[var(--ktra-ink-soft)]">{POSTED_HINT}</p>}
      </div>
    </PaymentVoucherModal>
  );
};
