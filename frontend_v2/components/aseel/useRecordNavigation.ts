/**
 * M0-T4 — useRecordNavigation
 * Aseel-style record navigation (الأول/السابق/التالي/الأخير/جديد) over any
 * already-loaded list of records. PURE: it never fetches — it only computes
 * the target id and calls `onSelect`; the caller is responsible for loading.
 * Reference: docs/aseel_reference/invoices.txt 207–229; shipments.txt 129–155.
 */
import { useCallback, useMemo } from 'react';

export type RecordId = string | number;

export interface RecordNavigationOptions<T> {
  /** Records as currently ordered on screen (e.g. by date/number). */
  items: T[];
  /** Stable id accessor. */
  getId: (item: T) => RecordId;
  /** Currently shown record id, or null when on a fresh/new record. */
  currentId: RecordId | null;
  /** Called with the id to load, or null for a new blank record. */
  onSelect: (id: RecordId | null) => void;
}

export interface RecordNavigation {
  first: () => void;
  prev: () => void;
  next: () => void;
  last: () => void;
  goNew: () => void;
  /** 1-based position of the current record, 0 when on a new record. */
  position: number;
  total: number;
  canPrev: boolean;
  canNext: boolean;
  isNew: boolean;
}

export function useRecordNavigation<T>({
  items,
  getId,
  currentId,
  onSelect,
}: RecordNavigationOptions<T>): RecordNavigation {
  const ids = useMemo(() => items.map(getId), [items, getId]);

  const index = useMemo(() => {
    if (currentId == null) return -1;
    return ids.findIndex((id) => id === currentId);
  }, [ids, currentId]);

  const total = ids.length;
  const isNew = currentId == null;
  // On a new record we behave as if positioned just past the last record.
  const effectiveIndex = index === -1 ? total : index;

  const canPrev = total > 0 && effectiveIndex > 0;
  const canNext = !isNew && index !== -1 && index < total - 1;

  const first = useCallback(() => {
    if (total > 0) onSelect(ids[0]);
  }, [ids, total, onSelect]);

  const last = useCallback(() => {
    if (total > 0) onSelect(ids[total - 1]);
  }, [ids, total, onSelect]);

  const prev = useCallback(() => {
    if (total === 0) return;
    if (effectiveIndex > 0) onSelect(ids[effectiveIndex - 1]);
  }, [ids, total, effectiveIndex, onSelect]);

  const next = useCallback(() => {
    if (isNew || index === -1) return;
    if (index < total - 1) onSelect(ids[index + 1]);
  }, [ids, total, index, isNew, onSelect]);

  const goNew = useCallback(() => onSelect(null), [onSelect]);

  return {
    first,
    prev,
    next,
    last,
    goNew,
    position: index === -1 ? 0 : index + 1,
    total,
    canPrev,
    canNext,
    isNew,
  };
}
