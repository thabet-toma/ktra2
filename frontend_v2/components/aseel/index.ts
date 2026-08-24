/**
 * M0 + N0 + N1 — Aseel document-shell layer (barrel).
 * One reusable shell + keyboard/record-nav engine consumed by M1+ screens.
 */
export { AseelDocumentShell } from './AseelDocumentShell';
export type {
  AseelDocumentShellProps,
  AseelToolbarAction,
  AseelTab,
} from './AseelDocumentShell';
export { AseelGrid } from './AseelGrid';
export type { AseelGridColumn, AseelGridProps } from './AseelGrid';
export { AseelDocumentView, AseelViewTable } from './AseelDocumentView';
export type {
  AseelDocumentViewProps,
  AseelViewColumn,
  AseelViewField,
  AseelViewMetric,
  AseelViewParty,
  AseelViewSection,
  AseelViewStatus,
  AseelViewTotal,
  AseelViewTone,
} from './AseelDocumentView';
export { AseelCalculatorButton } from './AseelCalculatorButton';
export { AseelIndexPicker } from './AseelIndexPicker';
export type { AseelIndexColumn, AseelIndexPickerProps } from './AseelIndexPicker';
export { useRecordNavigation } from './useRecordNavigation';
export type {
  RecordNavigation,
  RecordNavigationOptions,
  RecordId,
} from './useRecordNavigation';
export { useAseelKeymap } from './useAseelKeymap';
export type { AseelKey, AseelKeymapHandlers } from './useAseelKeymap';

// N0-T6 additions
export { useAseelIndexKeymap } from './useAseelIndexKeymap';
export type { AseelIndexKey, AseelIndexKeymapHandlers } from './useAseelIndexKeymap';

// N0-T8
export { useAseelFieldShortcuts } from './useAseelFieldShortcuts';
export type { FieldShortcutAction, FieldShortcutHandlers } from './useAseelFieldShortcuts';

// N0-T9
export { AseelStatusBarItem } from './AseelStatusBarItem';
export type { AseelStatusBarItemProps } from './AseelStatusBarItem';

// N1-T1
export { AseelFormSection } from './AseelFormSection';
export type { AseelFormSectionProps } from './AseelFormSection';

// N1-T2
export { AseelDenseTable } from './AseelDenseTable';
export type { DenseColumn, DensePagination, AseelDenseTableProps } from './AseelDenseTable';

// N1-T3
export { AseelReportTable } from './AseelReportTable';
export type { ReportColumn, AseelReportTableProps } from './AseelReportTable';

// N1-T5
export { AseelDateInput } from './AseelDateInput';
export type { AseelDateInputProps } from './AseelDateInput';

// N9-T2
export { AseelSpinner, AseelEmptyState, AseelErrorState } from './AseelStates';
export type { AseelSpinnerProps, AseelEmptyStateProps, AseelErrorStateProps } from './AseelStates';
// N9-T7
export { AseelContextMenu } from './AseelContextMenu';
export type { AseelContextMenuAction, AseelContextMenuProps } from './AseelContextMenu';

// I-1
export { AseelSidePanel } from './AseelSidePanel';
export type { AseelSidePanelProps } from './AseelSidePanel';

// T-WIN — النافذة العائمة الموحّدة (سحب + تحجيم + حفظ الهندسة)
export { AseelFloatWindow } from './AseelFloatWindow';
export type { AseelFloatWindowProps } from './AseelFloatWindow';

export { AseelCalculatorPopover } from './AseelCalculatorPopover';

export { AseelTabs } from './AseelTabs';
export type { AseelTabItem, AseelTabsProps } from './AseelTabs';

// task13 M5 — المنتقي المدمج (يستبدل مودالات اختيار الأصناف كمسار أساسي)
export { AseelAutocomplete } from './AseelAutocomplete';
export type { AseelAutocompleteOption, AseelAutocompleteProps } from './AseelAutocomplete';

