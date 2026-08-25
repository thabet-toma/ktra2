import React from "react";
import { Plus, RefreshCw } from "lucide-react";
import {
  KitDenseTable,
  KitDocumentShell,
  type KitDenseTableProps,
  type KitToolbarAction,
  type DenseColumn,
  type DensePagination,
  type RecordNavigation,
} from "../kit";

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
  extraActions?: KitToolbarAction[];
  tableProps?: Partial<
    Pick<
      KitDenseTableProps<T>,
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
  const actions: KitToolbarAction[] = [
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
      <KitDocumentShell
        title={title}
        state={state}
        nav={nav}
        actions={actions}
        header={hasFilters ? (
          <>
            {onSearchChange && (
              <label className="ktra-field">
                <span className="ktra-field-label">بحث</span>
                <input
                  className="ktra-input"
                  data-ktra-field="search"
                  placeholder={searchPlaceholder}
                  value={searchValue ?? ""}
                  onChange={(event) => onSearchChange(event.target.value)}
                />
              </label>
            )}
            {statusOptions?.length && onStatusChange && (
              <label className="ktra-field">
                <span className="ktra-field-label">الحالة</span>
                <select
                  className="ktra-input"
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
        status={countLabel ? <span className="ktra-status-item">{countLabel}</span> : undefined}
      >
        {error && (
          <div className="ktra-banner ktra-banner--err" role="alert">
            {error}
          </div>
        )}
        <KitDenseTable<T>
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
      </KitDocumentShell>
    </div>
  );
}

export type { DenseColumn as CommercialListColumn };
