"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getAccessToken } from "@/lib/auth";
import { WSProvider } from "@/lib/ws";
import Sidebar from "@/components/Sidebar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getAccessToken()) router.replace("/login");
    else setReady(true);
  }, [router]);

  if (!ready) return null;

  return (
    <WSProvider>
      <div className="app">
        <Sidebar />
        <div className="main">{children}</div>
      </div>
    </WSProvider>
  );
}
