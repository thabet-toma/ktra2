export interface ScrollTarget {
  scrollTop: number;
}

export interface ScrollPositionSnapshot {
  target: ScrollTarget | null;
  top: number;
}

export function captureScrollPosition(
  target: ScrollTarget | null,
  windowScrollY: number,
): ScrollPositionSnapshot {
  return { target, top: target ? target.scrollTop : windowScrollY };
}

export function restoreScrollPosition(
  snapshot: ScrollPositionSnapshot,
  restoreWindow: (top: number) => void,
): void {
  if (snapshot.target) {
    snapshot.target.scrollTop = snapshot.top;
    return;
  }
  restoreWindow(snapshot.top);
}
