"use client";
import { useEffect, useState } from "react";
import { useParams, usePathname, useRouter } from "next/navigation";
import { api, Channel, User } from "@/lib/api";
import { clearTokens } from "@/lib/auth";
import { useWS } from "@/lib/ws";

export default function Sidebar() {
  const router = useRouter();
  const params = useParams();
  const pathname = usePathname();
  const { presence, connected } = useWS();
  const [channels, setChannels] = useState<Channel[]>([]);
  const [allChannels, setAllChannels] = useState<Channel[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [newChannel, setNewChannel] = useState("");
  const [channelError, setChannelError] = useState("");
  const [showShipmentModal, setShowShipmentModal] = useState(false);
  const [shipmentForm, setShipmentForm] = useState({ id: "", status: "in_transit", origin: "", destination: "", carrier: "", eta: "", weight_kg: "" });
  const [shipmentError, setShipmentError] = useState("");

  async function refresh() {
    try {
      const [ch, all, us, m] = await Promise.all([
        api.listChannels(),
        api.listAllChannels(),
        api.listUsers(),
        api.me(),
      ]);
      setChannels(ch);
      setAllChannels(all);
      setUsers(us);
      setMe(m);
    } catch {
      /* token expired -> guard will redirect */
    }
  }

  async function joinAndOpen(c: Channel) {
    try {
      await api.joinChannel(c.id);
      await refresh();
      router.push(`/app/channel/${c.id}`);
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000); // refresh unread/presence periodically
    return () => clearInterval(t);
  }, []);

  async function createChannel(e: React.FormEvent) {
    e.preventDefault();
    if (!newChannel.trim()) return;
    setChannelError("");
    try {
      const ch = await api.createChannel({ name: newChannel.trim() });
      setNewChannel("");
      await refresh();
      router.push(`/app/channel/${ch.id}`);
    } catch (err: any) {
      // Distinguish the expected 403/409 from genuine failures instead of
      // assuming every error means "not an admin".
      if (err?.status === 403) setChannelError("Only admins can create channels.");
      else if (err?.status === 409) setChannelError("That channel name is taken.");
      else setChannelError(err?.message || "Could not create channel.");
    }
  }

  async function createShipment(e: React.FormEvent) {
    e.preventDefault();
    setShipmentError("");
    try {
      await api.createShipment({
        id: shipmentForm.id.trim(),
        status: shipmentForm.status,
        origin: shipmentForm.origin.trim(),
        destination: shipmentForm.destination.trim(),
        carrier: shipmentForm.carrier.trim(),
        eta: shipmentForm.eta || undefined,
        weight_kg: shipmentForm.weight_kg ? parseFloat(shipmentForm.weight_kg) : undefined,
      });
      setShowShipmentModal(false);
      setShipmentForm({ id: "", status: "in_transit", origin: "", destination: "", carrier: "", eta: "", weight_kg: "" });
    } catch (err: any) {
      setShipmentError(err?.message || "Failed to create shipment");
    }
  }

  function logout() {
    clearTokens();
    router.replace("/login");
  }

  const activeId = (params?.id as string) || "";

  return (
    <div className="sidebar">
      <h1>🚚 Hemut Logistics</h1>

      <div style={{ overflowY: "auto", flex: 1 }}>
        <div className="section">Channels</div>
        {channels.filter((c) => c.type === "public").map((c) => (
          <div
            key={c.id}
            className={`chan ${activeId === c.id ? "active" : ""}`}
            onClick={() => router.push(`/app/channel/${c.id}`)}
          >
            <span># {c.name}</span>
            {c.unread > 0 && <span className="badge">{c.unread}</span>}
          </div>
        ))}

        <form onSubmit={createChannel} style={{ padding: "6px 12px" }}>
          <input
            placeholder="+ new channel"
            value={newChannel}
            onChange={(e) => { setNewChannel(e.target.value); if (channelError) setChannelError(""); }}
            style={{ fontSize: 13 }}
          />
          {channelError && (
            <p className="error" style={{ fontSize: 12, margin: "4px 0 0" }}>{channelError}</p>
          )}
        </form>

        <div className="section">Shipments</div>
        <div
          className={`chan ${pathname === "/app/shipments" ? "active" : ""}`}
          onClick={() => router.push("/app/shipments")}
        >
          <span>📦 All Shipments</span>
        </div>

        {allChannels.filter((a) => !channels.some((c) => c.id === a.id)).length > 0 && (
          <>
            <div className="section">Browse / Join</div>
            {allChannels
              .filter((a) => !channels.some((c) => c.id === a.id))
              .map((c) => (
                <div key={c.id} className="chan" onClick={() => joinAndOpen(c)}>
                  <span style={{ color: "var(--muted)" }}># {c.name}</span>
                  <span className="pill" style={{ marginLeft: "auto" }}>join</span>
                </div>
              ))}
          </>
        )}

        <div className="section">Direct Messages</div>
        {users.map((u) => (
          <div
            key={u.id}
            className={`chan ${activeId === u.id ? "active" : ""}`}
            onClick={() => router.push(`/app/dm/${u.id}`)}
          >
            <span className={`dot ${presence[u.id] || u.presence}`} />
            <span>{u.display_name}</span>
          </div>
        ))}
      </div>

      <div style={{ borderTop: "1px solid var(--border)", padding: 12 }}>
        <div style={{ fontSize: 13, marginBottom: 6 }}>
          {me?.display_name} {me?.role === "admin" && <span className="pill">admin</span>}
        </div>
        <div style={{ fontSize: 12, color: connected ? "var(--green)" : "var(--muted)" }}>
          {connected ? "● connected" : "○ reconnecting…"}
        </div>
        {me?.role === "admin" && (
          <button className="ghost" onClick={() => setShowShipmentModal(true)} style={{ marginTop: 8, width: "100%" }}>
            + New Shipment
          </button>
        )}
        <button className="ghost" onClick={logout} style={{ marginTop: 6, width: "100%" }}>
          Log out
        </button>
      </div>

      {showShipmentModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
          <div style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: 24, width: 360 }}>
            <h3 style={{ margin: "0 0 16px" }}>New Shipment</h3>
            <form onSubmit={createShipment}>
              <div className="field">
                <label>Shipment ID</label>
                <input required placeholder="SHP-47 or SHI-47" value={shipmentForm.id} onChange={e => setShipmentForm(f => ({ ...f, id: e.target.value }))} />
              </div>
              <div className="field">
                <label>Status</label>
                <select value={shipmentForm.status} onChange={e => setShipmentForm(f => ({ ...f, status: e.target.value }))} style={{ width: "100%", padding: "6px 8px", background: "var(--bg)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 4 }}>
                  <option value="in_transit">In Transit</option>
                  <option value="delayed">Delayed</option>
                  <option value="delivered">Delivered</option>
                  <option value="pending">Pending</option>
                </select>
              </div>
              <div className="field">
                <label>Origin</label>
                <input required placeholder="Mumbai" value={shipmentForm.origin} onChange={e => setShipmentForm(f => ({ ...f, origin: e.target.value }))} />
              </div>
              <div className="field">
                <label>Destination</label>
                <input required placeholder="Delhi" value={shipmentForm.destination} onChange={e => setShipmentForm(f => ({ ...f, destination: e.target.value }))} />
              </div>
              <div className="field">
                <label>Carrier</label>
                <input required placeholder="BlueDart" value={shipmentForm.carrier} onChange={e => setShipmentForm(f => ({ ...f, carrier: e.target.value }))} />
              </div>
              <div className="field">
                <label>ETA (optional)</label>
                <input type="datetime-local" value={shipmentForm.eta} onChange={e => setShipmentForm(f => ({ ...f, eta: e.target.value }))} />
              </div>
              <div className="field">
                <label>Weight kg (optional)</label>
                <input type="number" min="0" step="0.1" placeholder="120" value={shipmentForm.weight_kg} onChange={e => setShipmentForm(f => ({ ...f, weight_kg: e.target.value }))} />
              </div>
              {shipmentError && <p className="error">{shipmentError}</p>}
              <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                <button type="submit" style={{ flex: 1 }}>Create</button>
                <button type="button" className="ghost" onClick={() => { setShowShipmentModal(false); setShipmentError(""); }} style={{ flex: 1 }}>Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
