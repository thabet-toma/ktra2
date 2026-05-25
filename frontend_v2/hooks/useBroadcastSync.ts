import { useEffect, useRef, useCallback } from 'react';

const CHANNEL = 'ktra-sync';

export type SyncMessage =
  | { type: 'MUTATION_UPDATED' }
  | { type: 'ONLINE_CHANGED'; online: boolean }
  | { type: 'TENANT_SWITCHED'; tenantId: number };

export function useBroadcastSync(
  onMessage: (msg: SyncMessage) => void,
): { post: (msg: SyncMessage) => void } {
  const channelRef = useRef<BroadcastChannel | null>(null);

  useEffect(() => {
    try {
      const ch = new BroadcastChannel(CHANNEL);
      channelRef.current = ch;
      ch.onmessage = (event: MessageEvent<SyncMessage>) => {
        onMessage(event.data);
      };
    } catch {}
    return () => {
      channelRef.current?.close();
      channelRef.current = null;
    };
  }, [onMessage]);

  const post = useCallback((msg: SyncMessage) => {
    channelRef.current?.postMessage(msg);
  }, []);

  return { post };
}

export async function broadcastOnlineChange(online: boolean): Promise<void> {
  try {
    new BroadcastChannel(CHANNEL).postMessage({ type: 'ONLINE_CHANGED', online } as SyncMessage);
  } catch {}
}

export async function broadcastTenantSwitch(tenantId: number): Promise<void> {
  try {
    new BroadcastChannel(CHANNEL).postMessage({ type: 'TENANT_SWITCHED', tenantId } as SyncMessage);
  } catch {}
}
