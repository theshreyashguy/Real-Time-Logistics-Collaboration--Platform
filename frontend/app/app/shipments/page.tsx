"use client";
import { useEffect, useState } from "react";
import { api, Shipment } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  in_transit: "#4f7cff",
  delayed: "#f1c40f",
  delivered: "#2ecc71",
  pending: "#6b7280",
};

type EditForm = {
  status: string; origin: string; destination: string;
  carrier: string; eta: string; weight_kg: string;
};

function toForm(s: Shipment): EditForm {
  return {
    status: s.status, origin: s.origin, destination: s.destination,
    carrier: s.carrier,
    eta: s.eta ? new Date(s.eta).toISOString().slice(0, 16) : "",
    weight_kg: s.weight_kg != null ? String(s.weight_kg) : "",
  };
}

const PAGE_SIZE = 12;

export default function ShipmentsPage() {
  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Shipment | null>(null);
  const [form, setForm] = useState<EditForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState("");

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  async function load(pg = page, query = q, st = status) {
    setLoading(true);
    try {
      const res = await api.listShipments(query || undefined, st || undefined, pg, PAGE_SIZE);
      setShipments(res.items);
      setTotal(res.total);
      setPage(pg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(1); }, []);

  function search() { load(1, q, status); }

  function openEdit(s: Shipment) { setEditing(s); setForm(toForm(s)); setEditError(""); }

  async function saveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editing || !form) return;
    setSaving(true); setEditError("");
    try {
      const updated = await api.updateShipment(editing.id, {
        status: form.status, origin: form.origin, destination: form.destination,
        carrier: form.carrier, eta: form.eta || null,
        weight_kg: form.weight_kg ? parseFloat(form.weight_kg) : null,
      });
      setShipments(prev => prev.map(s => s.id === updated.id ? updated : s));
      setEditing(null);
    } catch (err: any) {
      setEditError(err?.message || "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  const setF = (k: keyof EditForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => f ? { ...f, [k]: e.target.value } : f);

  return (
    <div style={{ padding: 24, overflowY: "auto", flex: 1, display: "flex", flexDirection: "column" }}>
      <h2 style={{ margin: "0 0 16px" }}>All Shipments</h2>

      {/* Search bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input
          placeholder="Search by ID, origin, destination, carrier…"
          value={q}
          onChange={e => setQ(e.target.value)}
          onKeyDown={e => e.key === "Enter" && search()}
          style={{ flex: 1, padding: "8px 12px" }}
        />
        <select value={status}
          onChange={e => { setStatus(e.target.value); load(1, q, e.target.value); }}
          style={{ padding: "8px 12px", background: "var(--bg)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 4 }}>
          <option value="">All statuses</option>
          <option value="in_transit">In Transit</option>
          <option value="delayed">Delayed</option>
          <option value="delivered">Delivered</option>
          <option value="pending">Pending</option>
        </select>
        <button onClick={search}>Search</button>
      </div>

      {/* Results count */}
      {!loading && (
        <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 12 }}>
          {total} shipment{total !== 1 ? "s" : ""} · page {page} of {totalPages}
        </div>
      )}

      {/* Grid */}
      {loading ? (
        <div style={{ color: "var(--muted)" }}>Loading…</div>
      ) : shipments.length === 0 ? (
        <div style={{ color: "var(--muted)" }}>No shipments found.</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12, flex: 1 }}>
          {shipments.map(s => (
            <div key={s.id} style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <b style={{ fontSize: 15 }}>{s.id}</b>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: STATUS_COLOR[s.status] || "var(--text)", textTransform: "capitalize" }}>
                    ● {s.status.replace(/_/g, " ")}
                  </span>
                  <button className="ghost" onClick={() => openEdit(s)} style={{ fontSize: 12, padding: "2px 8px" }}>Edit</button>
                </div>
              </div>
              <div style={{ fontSize: 13, display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--muted)" }}>Route</span><span>{s.origin} → {s.destination}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--muted)" }}>Carrier</span><span>{s.carrier}</span>
                </div>
                {s.eta && <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--muted)" }}>ETA</span><span>{new Date(s.eta).toLocaleString()}</span>
                </div>}
                {s.weight_kg != null && <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--muted)" }}>Weight</span><span>{s.weight_kg} kg</span>
                </div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, marginTop: 20 }}>
          <button className="ghost" onClick={() => load(1)} disabled={page === 1 || loading}>«</button>
          <button className="ghost" onClick={() => load(page - 1)} disabled={page === 1 || loading}>‹</button>

          {Array.from({ length: totalPages }, (_, i) => i + 1)
            .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 2)
            .reduce<(number | "…")[]>((acc, p, i, arr) => {
              if (i > 0 && p - (arr[i - 1] as number) > 1) acc.push("…");
              acc.push(p);
              return acc;
            }, [])
            .map((p, i) =>
              p === "…" ? (
                <span key={`ellipsis-${i}`} style={{ padding: "0 4px", color: "var(--muted)" }}>…</span>
              ) : (
                <button key={p} className="ghost" onClick={() => load(p as number)} disabled={loading}
                  style={{ minWidth: 32, fontWeight: p === page ? 700 : 400, color: p === page ? "var(--accent)" : undefined, border: p === page ? "1px solid var(--accent)" : undefined }}>
                  {p}
                </button>
              )
            )}

          <button className="ghost" onClick={() => load(page + 1)} disabled={page === totalPages || loading}>›</button>
          <button className="ghost" onClick={() => load(totalPages)} disabled={page === totalPages || loading}>»</button>
        </div>
      )}

      {/* Edit modal */}
      {editing && form && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
          <div style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: 24, width: 380 }}>
            <h3 style={{ margin: "0 0 16px" }}>Edit {editing.id}</h3>
            <form onSubmit={saveEdit}>
              <div className="field">
                <label>Status</label>
                <select value={form.status} onChange={setF("status")}
                  style={{ width: "100%", padding: "6px 8px", background: "var(--bg)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 4 }}>
                  <option value="in_transit">In Transit</option>
                  <option value="delayed">Delayed</option>
                  <option value="delivered">Delivered</option>
                  <option value="pending">Pending</option>
                </select>
              </div>
              <div className="field"><label>Origin</label><input required value={form.origin} onChange={setF("origin")} /></div>
              <div className="field"><label>Destination</label><input required value={form.destination} onChange={setF("destination")} /></div>
              <div className="field"><label>Carrier</label><input required value={form.carrier} onChange={setF("carrier")} /></div>
              <div className="field"><label>ETA (optional)</label><input type="datetime-local" value={form.eta} onChange={setF("eta")} /></div>
              <div className="field"><label>Weight kg (optional)</label><input type="number" min="0" step="0.1" value={form.weight_kg} onChange={setF("weight_kg")} /></div>
              {editError && <p className="error">{editError}</p>}
              <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                <button type="submit" disabled={saving} style={{ flex: 1 }}>{saving ? "Saving…" : "Save"}</button>
                <button type="button" className="ghost" onClick={() => setEditing(null)} style={{ flex: 1 }}>Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
