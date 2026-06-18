"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, Message, Shipment } from "@/lib/api";
import { useWS } from "@/lib/ws";
import ShipmentCard from "./ShipmentCard";

interface Props {
  mode: "channel" | "dm";
  id: string;       // channel id, or other user's id for DMs
  title: string;
}

function uuid() {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

export default function ChatView({ mode, id, title }: Props) {
  const { subscribe, unsubscribe, addHandler, connected } = useWS();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [suggestions, setSuggestions] = useState<Shipment[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [summary, setSummary] = useState<string>("");
  const [summarySources, setSummarySources] = useState<number[]>([]);
  const [summarizing, setSummarizing] = useState(false);

  const channelIdRef = useRef<string | null>(mode === "channel" ? id : null);
  const highestIdRef = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const wasConnected = useRef(false);
  const autocompleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const upsert = useCallback((incoming: Message[]) => {
    setMessages((prev) => {
      const byId = new Map<number, Message>();
      const byClient = new Map<string, Message>();
      for (const m of prev) {
        if (m.id > 0) byId.set(m.id, m);
        else if (m.client_msg_id) byClient.set(m.client_msg_id, m);
      }
      for (const m of incoming) {
        // reconcile optimistic temp by client_msg_id
        if (m.client_msg_id && byClient.has(m.client_msg_id)) byClient.delete(m.client_msg_id);
        if (m.id > 0) byId.set(m.id, m);
        if (m.id > highestIdRef.current) highestIdRef.current = m.id;
      }
      const merged = [...byId.values(), ...byClient.values()];
      merged.sort((a, b) => (a.id || 1e15) - (b.id || 1e15));
      return merged;
    });
  }, []);

  // initial load + subscribe
  const load = useCallback(async () => {
    try {
      const hist = mode === "channel" ? await api.history(id) : await api.dmHistory(id);
      if (hist.length) channelIdRef.current = hist[0].channel_id;
      setMessages(hist);
      highestIdRef.current = hist.reduce((m, x) => Math.max(m, x.id), 0);
      if (mode === "channel" && highestIdRef.current > 0) {
        api.markRead(id, highestIdRef.current).catch(() => {});
      }
      if (channelIdRef.current) subscribe(channelIdRef.current);
    } catch (e: any) {
      if (e?.status === 403) setError("You are not a member of this conversation.");
      else setError("Failed to load messages.");
    }
  }, [id, mode, subscribe]);

  useEffect(() => {
    setMessages([]);
    setError("");
    setSummary("");
    highestIdRef.current = 0;
    // Seed the ref synchronously: a channel's id is known up front; a DM's
    // real channel id is only resolved once history loads (or the first send),
    // so it starts null and load()/send() fill it in.
    channelIdRef.current = mode === "channel" ? id : null;
    load();
    return () => {
      // Read the ref at cleanup time, not effect-run time, so we unsubscribe
      // the channel that was actually subscribed — including DMs whose id was
      // resolved asynchronously after this effect ran.
      if (channelIdRef.current) unsubscribe(channelIdRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, mode]);

  // realtime handler (reads latest state via refs -> no stale closures)
  useEffect(() => {
    const off = addHandler((ev) => {
      if (ev.type === "message" && ev.channel_id === channelIdRef.current) {
        upsert([ev.data as Message]);
        if (mode === "channel" && (ev.data as Message).id > 0) {
          api.markRead(channelIdRef.current!, (ev.data as Message).id).catch(() => {});
        }
      } else if (ev.type === "ai_token" && ev.channel_id === channelIdRef.current) {
        setSummary((s) => s + ev.delta);
      } else if (ev.type === "ai_done" && ev.channel_id === channelIdRef.current) {
        setSummarySources(ev.sources);
        setSummarizing(false);
      }
    });
    return off;
  }, [addHandler, upsert]);

  // reconnect replay: when the socket comes back, fetch anything missed
  useEffect(() => {
    if (connected && wasConnected.current === false && channelIdRef.current) {
      const after = highestIdRef.current;
      (mode === "channel" ? api.history(id, after) : api.dmHistory(id, after))
        .then((missed) => missed.length && upsert(missed))
        .catch(() => {});
      if (channelIdRef.current) subscribe(channelIdRef.current);
    }
    wasConnected.current = connected;
  }, [connected, id, mode, subscribe, upsert]);

  // autoscroll
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, summary]);

  function handleInputChange(val: string) {
    setInput(val);
    const word = val.split(/\s+/).pop() || "";
    if (autocompleteTimer.current) clearTimeout(autocompleteTimer.current);
    if (word.length >= 3 && /^[a-zA-Z0-9-]+$/.test(word)) {
      autocompleteTimer.current = setTimeout(async () => {
        try {
          const res = await api.listShipments(word, undefined, 1, 5);
          setSuggestions(res.items);
          setShowSuggestions(res.items.length > 0);
        } catch {
          setShowSuggestions(false);
        }
      }, 300);
    } else {
      setShowSuggestions(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Tab" && showSuggestions && suggestions.length > 0) {
      e.preventDefault();
      const word = input.split(/\s+/).pop() || "";
      setInput(input.slice(0, input.length - word.length) + suggestions[0].id + " ");
      setShowSuggestions(false);
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput("");
    setError("");

    // /shipment <id> slash command -> render a card locally (no post)
    const slash = text.match(/^\/shipment\s+(\S+)/i);
    if (slash) {
      const tempId = -Date.now();
      upsert([{
        id: tempId, channel_id: channelIdRef.current || "", sender_id: "",
        sender_name: "you", content: text, type: "text",
        client_msg_id: uuid(), reply_to_id: null,
        created_at: new Date().toISOString(), shipment_ids: [slash[1].toUpperCase()],
      }]);
      return;
    }

    const clientMsgId = uuid();
    // optimistic message (negative id until server assigns one)
    upsert([{
      id: -Date.now(), channel_id: channelIdRef.current || "", sender_id: "",
      sender_name: "you (sending…)", content: text, type: "text",
      client_msg_id: clientMsgId, reply_to_id: null,
      created_at: new Date().toISOString(), shipment_ids: [],
    }]);

    try {
      const saved = mode === "channel"
        ? await api.postMessage(id, text, clientMsgId)
        : await api.postDm(id, text, clientMsgId);
      if (!channelIdRef.current) {
        channelIdRef.current = saved.channel_id;
        subscribe(saved.channel_id);
      }
      upsert([saved]); // reconcile optimistic -> server row
    } catch {
      setError("Message failed to send.");
    }
  }

  async function catchMeUp() {
    if (!channelIdRef.current) return;
    setSummary("");
    setSummarySources([]);
    setSummarizing(true);
    try {
      const res = await api.summarize(channelIdRef.current, "24h");
      // REST result is the source of truth; WS tokens may also have streamed in
      setSummary(res.summary);
      setSummarySources(res.sources);
    } catch {
      setSummary("Summary failed.");
    } finally {
      setSummarizing(false);
    }
  }

  return (
    <>
      <div className="header">
        <span className="title">{title}</span>
        {mode === "channel" && (
          <button className="ghost" onClick={catchMeUp} disabled={summarizing}>
            {summarizing ? "Summarizing…" : "✨ Catch me up (24h)"}
          </button>
        )}
        <span className="conn">
          <span className={`dot ${connected ? "online" : "offline"}`} />
          {connected ? "live" : "reconnecting"}
        </span>
      </div>

      <div className="messages" ref={scrollRef}>
        {error && <div className="error">{error}</div>}

        {summary && (
          <div className="msg ai">
            <div className="meta"><b>AI Summary</b> · grounded in chat history</div>
            {summary}
            {summarySources.length > 0 && (
              <div style={{ marginTop: 6 }}>
                {summarySources.map((s) => (
                  <span key={s} className="pill" style={{ marginRight: 4 }}>#{s}</span>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((m) => (
          <div className={`msg ${m.type === "ai" ? "ai" : ""}`} key={m.id || m.client_msg_id}>
            <div className="meta">
              <b>{m.sender_name || "unknown"}</b>{" "}
              {new Date(m.created_at).toLocaleTimeString()}
            </div>
            <div>{m.content}</div>
            {m.shipment_ids.map((sid) => <ShipmentCard key={sid} id={sid} />)}
          </div>
        ))}
      </div>

      <div style={{ position: "relative" }}>
        {showSuggestions && (
          <div style={{ position: "absolute", bottom: "100%", left: 0, right: 0, background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 6, zIndex: 10, maxHeight: 200, overflowY: "auto" }}>
            {suggestions.map(s => (
              <div key={s.id} onClick={() => {
                const word = input.split(/\s+/).pop() || "";
                setInput(input.slice(0, input.length - word.length) + s.id + " ");
                setShowSuggestions(false);
              }} style={{ padding: "8px 12px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--bg)")}
              onMouseLeave={e => (e.currentTarget.style.background = "")}>
                <span><b>{s.id}</b> · {s.origin} → {s.destination}</span>
                <span className={`status ${s.status}`} style={{ fontSize: 11 }}>{s.status.replace("_", " ")}</span>
              </div>
            ))}
          </div>
        )}
        <form className="composer" onSubmit={send}>
          <input
            placeholder={`Message ${title}  (try: /shipment SHP-10293)`}
            value={input}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
          />
          <button type="submit">Send</button>
        </form>
      </div>
    </>
  );
}
