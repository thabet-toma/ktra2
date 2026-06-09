export type KtraEventType = 'settings' | 'products' | 'partners';

export interface KtraEvent {
  type: KtraEventType;
  tenantId?: string | number;
}

const channelName = 'ktra-events';
let broadcastChannel: BroadcastChannel | null = null;

try {
  if (typeof window !== 'undefined' && 'BroadcastChannel' in window) {
    broadcastChannel = new BroadcastChannel(channelName);
  }
} catch (e) {
  console.warn('BroadcastChannel not supported or failed to initialize:', e);
}

type EventListener = (event: KtraEvent) => void;
const localListeners = new Set<EventListener>();

if (broadcastChannel) {
  broadcastChannel.onmessage = (event) => {
    const data = event.data as KtraEvent;
    localListeners.forEach((listener) => {
      try {
        listener(data);
      } catch (err) {
        console.error('Error in event listener:', err);
      }
    });
  };
}

export const eventBus = {
  publish(type: KtraEventType, tenantId?: string | number) {
    const event: KtraEvent = { type, tenantId };
    if (broadcastChannel) {
      broadcastChannel.postMessage(event);
    }
    localListeners.forEach((listener) => {
      try {
        listener(event);
      } catch (err) {
        console.error('Error in event listener:', err);
      }
    });
  },
  subscribe(listener: EventListener): () => void {
    localListeners.add(listener);
    return () => {
      localListeners.delete(listener);
    };
  }
};
