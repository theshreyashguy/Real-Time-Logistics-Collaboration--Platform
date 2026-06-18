"use client";
import { useEffect, useState } from "react";
import { api, Shipment } from "@/lib/api";

export default function ShipmentCard({ id }: { id: string }) {
  const [s, setS] = useState<Shipment | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    api.shipment(id).then(setS).catch(() => setErr(true));
  }, [id]);

  if (err) return <div className="ship-card">Shipment {id} not found.</div>;
  if (!s) return <div className="ship-card">Loading {id}…</div>;

  return (
    <div className="ship-card">
      <div className="row">
        <b>{s.id}</b>
        <span className={`status ${s.status}`}>{s.status.replace("_", " ")}</span>
      </div>
      <div className="row"><span>Route</span><span>{s.origin} → {s.destination}</span></div>
      <div className="row"><span>Carrier</span><span>{s.carrier}</span></div>
      {s.eta && <div className="row"><span>ETA</span><span>{new Date(s.eta).toLocaleString()}</span></div>}
      {s.weight_kg != null && <div className="row"><span>Weight</span><span>{s.weight_kg} kg</span></div>}
    </div>
  );
}
