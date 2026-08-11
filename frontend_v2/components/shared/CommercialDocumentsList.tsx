import React from "react";
import { Plus, RefreshCw } from "lucide-react";
import {
  AseelDenseTable,
  AseelDocumentShell,
  type AseelDenseTableProps,
  type AseelToolbarAction,
  type DenseColumn,
  type DensePagination,
  type RecordNavigation,
} from "../aseel";

export type CommercialListOption = {
  value: string;
  label: string;
};

type Props<T extends Record<string, any>> = {
  title: string;
  state?: string;
  rows: T[];
  columns: DenseColumn<T>[];
  getRowKey: (row: T) => string | number;
  loading?: boolean;
  error?: string | null;
  emptyHint?: string;
  countLabel?: string;
  searchValue?: string;
  searchPlaceholder?: string;
  onSearchChange?: (value: string) => void;
  statusValue?: string;
  statusOptions?: CommercialListOption[];
  onStatusChange?: (value: string) => void;
  onNew: () => void;
  onReload: () => void;
  newLabel: string;
  nav?: RecordNavigation;
  onRowClick?: (row: T) => void;
  onRowDoubleClick?: (row: T) => void;
  pagination?: DensePagination;
  detailPanel?: React.ReactNode;
  extraActions?: AseelToolbarAction[];
  tableProps?: Partial<
    Pick<
      AseelDenseTableProps<T>,
      "selectable" | "selectedKey" | "onSelect" | "exportable" | "exportFilename"
    >
  >;
};

export function CommercialDocumentsList<T extends Record<string, any>>({
  title,
  state,
  rows,
  columns,
  getRowKey,
  loading = false,
  error,
  emptyHint,
  countLabel,
  searchValue,
  searchPlaceholder = "بحث…",
  onSearchChange,
  statusValue,
  statusOptions,
  onStatusChange,
  onNew,
  onReload,
  newLabel,
  nav,
  onRowClick,
  onRowDoubleClick,
  pagination,
  detailPanel,
  extraActions = [],
  tableProps,
}: Props<T>) {
  const actions: AseelToolbarAction[] = [
    { key: "new", label: newLabel, icon: <Plus />, onClick: onNew },
    {
      key: "reload",
      label: "تحديث",
      icon: <RefreshCw className={loading ? "animate-spin" : ""} />,
      onClick: onReload,
      separatorBefore: true,
    },
    ...extraActions,
  ];
  const hasFilters = Boolean(onSearchChange || (statusOptions?.length && onStatusChange));

  return (
    <div dir="rtl" className="min-h-0">
      <AseelDocumentShell
        title={title}
        state={state}
        nav={nav}
        actions={actions}
        header={hasFilters ? (
          <>
            {onSearchChange && (
              <label className="aseel-field">
                <span className="aseel-field-label">بحث</span>
                <input
                  className="aseel-input"
                  data-aseel-field="search"
                  placeholder={searchPlaceholder}
                  value={searchValue ?? ""}
                  onChange={(event) => onSearchChange(event.target.value)}
                />
              </label>
            )}
            {statusOptions?.length && onStatusChange && (
              <label className="aseel-field">
                <span className="aseel-field-label">الحالة</span>
                <select
                  className="aseel-input"
                  value={statusValue ?? ""}
                  onChange={(event) => onStatusChange(event.target.value)}
                >
                  {statusOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </>
        ) : undefined}
        status={countLabel ? <span className="aseel-status-item">{countLabel}</span> : undefined}
      >
        {error && (
          <div className="aseel-banner aseel-banner--err" role="alert">
            {error}
          </div>
        )}
        <AseelDenseTable<T>
          columns={columns}
          rows={rows}
          getRowKey={getRowKey}
          loading={loading}
          emptyHint={emptyHint}
          onRowClick={onRowClick}
          onRowDoubleClick={onRowDoubleClick}
          pagination={pagination}
          {...tableProps}
        />
        {detailPanel}
      </AseelDocumentShell>
    </div>
  );
}

export type { DenseColumn as CommercialListColumn };
