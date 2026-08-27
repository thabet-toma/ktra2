/**
 * M0 + N0 + N1 — Kit document-shell layer (barrel).
 * One reusable shell + keyboard/record-nav engine consumed by M1+ screens.
 */
export { KitDocumentShell } from './KitDocumentShell';
export type {
  KitDocumentShellProps,
  KitToolbarAction,
  KitTab,
} from './KitDocumentShell';
export { KitGrid } from './KitGrid';
export type { KitGridColumn, KitGridProps } from './KitGrid';
export { KitDocumentView, KitViewTable } from './KitDocumentView';
export type {
  KitDocumentViewProps,
  KitViewColumn,
  KitViewField,
  KitViewMetric,
  KitViewParty,
  KitViewSection,
  KitViewStatus,
  KitViewTotal,
  KitViewTone,
} from './KitDocumentView';
export { KitCalculatorButton } from './KitCalculatorButton';
export { KitIndexPicker } from './KitIndexPicker';
export type { KitIndexColumn, KitIndexPickerProps } from './KitIndexPicker';
export { useRecordNavigation } from './useRecordNavigation';
export type {
  RecordNavigation,
  RecordNavigationOptions,
  RecordId,
} from './useRecordNavigation';
export { useKitKeymap } from './useKitKeymap';
export type { KitKey, KitKeymapHandlers } from './useKitKeymap';

// N0-T6 additions
export { useKitIndexKeymap } from './useKitIndexKeymap';
export type { KitIndexKey, KitIndexKeymapHandlers } from './useKitIndexKeymap';

// N0-T8
export { useKitFieldShortcuts } from './useKitFieldShortcuts';
export type { FieldShortcutAction, FieldShortcutHandlers } from './useKitFieldShortcuts';

// N0-T9
export { KitStatusBarItem } from './KitStatusBarItem';
export type { KitStatusBarItemProps } from './KitStatusBarItem';

// N1-T1
export { KitFormSection } from './KitFormSection';
export type { KitFormSectionProps } from './KitFormSection';

// N1-T2
export { KitDenseTable } from './KitDenseTable';
export type { DenseColumn, DensePagination, KitDenseTableProps } from './KitDenseTable';

// N1-T3
export { KitReportTable } from './KitReportTable';
export type { ReportColumn, KitReportTableProps } from './KitReportTable';

// N1-T5
export { KitDateInput } from './KitDateInput';
export type { KitDateInputProps } from './KitDateInput';

// N9-T2
export { KitSpinner, KitEmptyState, KitErrorState } from './KitStates';
export type { KitSpinnerProps, KitEmptyStateProps, KitErrorStateProps } from './KitStates';
// N9-T7
export { KitContextMenu } from './KitContextMenu';
export type { KitContextMenuAction, KitContextMenuProps } from './KitContextMenu';

// I-1
export { KitSidePanel } from './KitSidePanel';
export type { KitSidePanelProps } from './KitSidePanel';

// T-WIN — النافذة العائمة الموحّدة (سحب + تحجيم + حفظ الهندسة)
export { KitFloatWindow } from './KitFloatWindow';
export type { KitFloatWindowProps } from './KitFloatWindow';

export { KitCalculatorPopover } from './KitCalculatorPopover';

export { KitTabs } from './KitTabs';
export type { KitTabItem, KitTabsProps } from './KitTabs';

// task13 M5 — المنتقي المدمج (يستبدل مودالات اختيار المنتجات كمسار أساسي)
export { KitAutocomplete } from './KitAutocomplete';
export type { KitAutocompleteOption, KitAutocompleteProps } from './KitAutocomplete';

