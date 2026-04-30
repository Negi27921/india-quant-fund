import { create } from "zustand";
import type { LiveData } from "@/api/types";
import { WS_URL } from "@/lib/constants";

interface LiveStore {
  data: LiveData | null;
  connected: boolean;
  lastUpdate: Date | null;
  connect: () => () => void;
}

export const useLiveStore = create<LiveStore>((set) => ({
  data: null,
  connected: false,
  lastUpdate: null,

  connect: () => {
    let ws: WebSocket;
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let unmounted = false;

    const connect = () => {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        set({ connected: true });
      };

      ws.onmessage = (event) => {
        try {
          const data: LiveData = JSON.parse(event.data);
          set({ data, lastUpdate: new Date() });
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        set({ connected: false });
        if (!unmounted) {
          reconnectTimer = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();

    return () => {
      unmounted = true;
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  },
}));
