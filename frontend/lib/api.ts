// Typed API wrappers. Every authenticated call attaches the access token and
// transparently retries once after a refresh on 401.
import { getAccessToken, tryRefresh } from "./auth";
import { HttpError, XhrOptions, xhrRequest } from "./xhr";

export interface User {
  id: string;
  username: string;
  display_name: string;
  role: string;
  presence: string;
}
export interface Channel {
  id: string;
  name: string | null;
  type: string;
  topic: string | null;
  unread: number;
}
export interface Message {
  id: number;
  channel_id: string;
  sender_id: string;
  sender_name: string | null;
  content: string;
  type: string;
  client_msg_id: string | null;
  reply_to_id: number | null;
  created_at: string;
  shipment_ids: string[];
}
export interface Shipment {
  id: string;
  status: string;
  origin: string;
  destination: string;
  eta: string | null;
  carrier: string;
  weight_kg: number | null;
}
export interface Summary {
  summary_id: string | null;
  channel_id: string;
  window: string;
  model: string;
  summary: string;
  sources: number[];
  cached: boolean;
}

async function authed<T>(path: string, opts: XhrOptions = {}): Promise<T> {
  try {
    return await xhrRequest<T>(path, { ...opts, token: getAccessToken() });
  } catch (e) {
    if (e instanceof HttpError && e.status === 401 && (await tryRefresh())) {
      return xhrRequest<T>(path, { ...opts, token: getAccessToken() });
    }
    throw e;
  }
}

export const api = {
  register: (b: { username: string; email: string; password: string; display_name: string }, onProgress?: (f: number) => void) =>
    xhrRequest<User>("/auth/register", { method: "POST", body: b, onProgress }),
  login: (b: { username: string; password: string }, onProgress?: (f: number) => void) =>
    xhrRequest<{ access_token: string; refresh_token: string }>("/auth/login", { method: "POST", body: b, onProgress }),
  me: () => authed<User>("/auth/me"),
  listUsers: () => authed<User[]>("/auth/users"),

  listChannels: () => authed<Channel[]>("/channels"),
  listAllChannels: () => authed<Channel[]>("/channels/all"),
  createChannel: (b: { name: string; topic?: string }) =>
    authed<Channel>("/channels", { method: "POST", body: b }),
  joinChannel: (id: string) => authed<void>(`/channels/${id}/join`, { method: "POST" }),

  history: (channelId: string, afterId?: number) =>
    authed<Message[]>(`/channels/${channelId}/messages` + (afterId ? `?after_id=${afterId}` : "")),
  postMessage: (channelId: string, content: string, clientMsgId: string) =>
    authed<Message>(`/channels/${channelId}/messages`, {
      method: "POST",
      body: { content, client_msg_id: clientMsgId },
    }),

  dmHistory: (userId: string, afterId?: number) =>
    authed<Message[]>(`/dm/${userId}/messages` + (afterId ? `?after_id=${afterId}` : "")),
  postDm: (userId: string, content: string, clientMsgId: string) =>
    authed<Message>(`/dm/${userId}/messages`, {
      method: "POST",
      body: { content, client_msg_id: clientMsgId },
    }),

  shipment: (id: string) => authed<Shipment>(`/shipments/${id}`),
  createShipment: (b: { id: string; status: string; origin: string; destination: string; carrier: string; eta?: string; weight_kg?: number }) =>
    authed<Shipment>("/shipments", { method: "POST", body: b }),
  updateShipment: (id: string, b: { status?: string; origin?: string; destination?: string; carrier?: string; eta?: string | null; weight_kg?: number | null }) =>
    authed<Shipment>(`/shipments/${id}`, { method: "PATCH", body: b }),
  listShipments: (q?: string, status?: string, page = 1, pageSize = 12) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (status) params.set("status", status);
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    return authed<{ items: Shipment[]; total: number; page: number; page_size: number }>(`/shipments?${params.toString()}`);
  },
  markRead: (channelId: string, lastId: number) =>
    authed<void>(`/channels/${channelId}/read`, { method: "POST", body: { last_id: lastId } }),
  summarize: (channelId: string, window = "24h") =>
    authed<Summary>(`/channels/${channelId}/summarize?window=${window}`, { method: "POST" }),
};
