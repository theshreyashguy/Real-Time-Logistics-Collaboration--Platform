"use client";
// Single multiplexed WebSocket shared across the app.
// - One socket in a context/provider (avoids per-component sockets)
// - Heartbeat ping every 20s; exponential-backoff reconnect on drop
// - Handlers read latest state via refs to avoid stale closures
// - On reconnect, re-subscribes to all open channels (callers replay via
//   after_id from the REST API)
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { getAccessToken } from "./auth";

type ServerEvent =
  | { type: "message"; channel_id: string; data: any }
  | { type: "presence"; user_id: string; state: string }
  | { type: "ai_token"; channel_id: string; delta: string }
  | { type: "ai_done"; channel_id: string; summary_id: string; sources: number[] }
  | { type: "pong" };

type Handler = (ev: ServerEvent) => void;

interface WSContextValue {
  subscribe: (channelId: string) => void;
  unsubscribe: (channelId: string) => void;
  addHandler: (h: Handler) => () => void;
  presence: Record<string, string>;
  connected: boolean;
}

const WSContext = createContext<WSContextValue | null>(null);

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export function WSProvider({ children }: { children: React.ReactNode }) {
  const wsRef = useRef<WebSocket | null>(null);
  const handlersRef = useRef<Set<Handler>>(new Set());
  const subsRef = useRef<Set<string>>(new Set());
  const backoffRef = useRef(500);
  const pingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const closedRef = useRef(false);
  const [presence, setPresence] = useState<Record<string, string>>({});
  const [connected, setConnected] = useState(false);

  const send = useCallback((obj: unknown) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  }, []);

  const connect = useCallback(() => {
    const token = getAccessToken();
    if (!token) return;
    const ws = new WebSocket(`${WS_URL}/ws?token=${token}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      backoffRef.current = 500;
      // re-subscribe to all open channels after a reconnect
      subsRef.current.forEach((cid) => send({ op: "subscribe", channel_id: cid }));
      pingRef.current = setInterval(() => send({ op: "ping" }), 20000);
    };

    ws.onmessage = (e) => {
      let ev: ServerEvent;
      try {
        ev = JSON.parse(e.data);
      } catch {
        return;
      }
      if (ev.type === "presence") {
        setPresence((p) => ({ ...p, [ev.user_id]: ev.state }));
      }
      handlersRef.current.forEach((h) => h(ev));
    };

    const onClose = () => {
      setConnected(false);
      if (pingRef.current) clearInterval(pingRef.current);
      if (closedRef.current) return;
      const delay = Math.min(backoffRef.current, 10000);
      backoffRef.current *= 2;
      setTimeout(connect, delay);
    };
    ws.onclose = onClose;
    ws.onerror = () => ws.close();
  }, [send]);

  useEffect(() => {
    closedRef.current = false;
    connect();
    return () => {
      closedRef.current = true;
      if (pingRef.current) clearInterval(pingRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const subscribe = useCallback(
    (channelId: string) => {
      subsRef.current.add(channelId);
      send({ op: "subscribe", channel_id: channelId });
    },
    [send]
  );
  const unsubscribe = useCallback(
    (channelId: string) => {
      subsRef.current.delete(channelId);
      send({ op: "unsubscribe", channel_id: channelId });
    },
    [send]
  );
  const addHandler = useCallback((h: Handler) => {
    handlersRef.current.add(h);
    return () => handlersRef.current.delete(h);
  }, []);

  return (
    <WSContext.Provider
      value={{ subscribe, unsubscribe, addHandler, presence, connected }}
    >
      {children}
    </WSContext.Provider>
  );
}

export function useWS() {
  const ctx = useContext(WSContext);
  if (!ctx) throw new Error("useWS must be used within WSProvider");
  return ctx;
}
