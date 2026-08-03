import React from "react";
import { Plus } from "lucide-react";
import {
  AseelDocumentShell,
  AseelGrid,
  type AseelGridColumn,
  type AseelTab,
  type AseelToolbarAction,
  type RecordNavigation,
} from "../aseel";

export type CommercialHeaderField = {
  key: string;
  label: string;
  control: React.ReactNode;
  className?: string;
};

type Props<TLine> = {
  title: string;
  state?: string;
  nav?: RecordNavigation;
  actions: AseelToolbarAction[];
  headerFields: CommercialHeaderField[];
  lines: TLine[];
  lineColumns: AseelGridColumn<TLine>[];
  getLineCell: (line: TLine, key: string) => string | number | null | undefined;
  getLineKey: (line: TLine, index: number) => string | number;
  onLineChange?: (index: number, key: string, value: string) => void;
  onAddLine?: () => void;
  addLineLabel?: string;
  tabs?: AseelTab[];
  totals?: React.ReactNode;
  status?: React.ReactNode;
  banner?: React.ReactNode;
  readOnly?: boolean;
  emptyHint?: string;
  overlay?: React.ReactNode;
};

export function CommercialDocumentEditor<TLine>({
  title,
  state,
  nav,
  actions,
  headerFields,
  lines,
  lineColumns,
  getLineCell,
  getLineKey,
  onLineChange,
  onAddLine,
  addLineLabel = "إضافة سطر",
  tabs,
  totals,
  status,
  banner,
  readOnly = false,
  emptyHint = "لا توجد بنود — أضف صنفاً",
  overlay,
}: Props<TLine>) {
  return (
    <div dir="rtl" className="min-h-0">
      <AseelDocumentShell
        title={title}
        state={state}
        nav={nav}
        actions={actions}
        header={
          <>
            {headerFields.map((field) => (
              <label
                key={field.key}
                className={`aseel-field${field.className ? ` ${field.className}` : ""}`}
              >
                <span className="aseel-field-label">{field.label}</span>
                {field.control}
              </label>
            ))}
          </>
        }
        tabs={tabs}
        totals={totals}
        status={status}
      >
        {banner}
        <AseelGrid<TLine>
          columns={lineColumns}
          rows={lines}
          getCell={getLineCell}
          getRowKey={getLineKey}
          onChange={readOnly ? undefined : onLineChange}
          onAddRow={readOnly ? undefined : onAddLine}
          emptyHint={emptyHint}
        />
        {!readOnly && onAddLine && (
          <button type="button" className="aseel-addrow" onClick={onAddLine}>
            <Plus className="h-3 w-3" /> {addLineLabel}
          </button>
        )}
      </AseelDocumentShell>
      {overlay}
    </div>
  );
}

export type {
  AseelGridColumn as CommercialLineColumn,
  AseelToolbarAction as CommercialToolbarAction,
};
