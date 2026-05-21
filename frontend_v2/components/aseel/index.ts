/**
 * M0 — Aseel document-shell layer (barrel).
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
