"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getAccessToken } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getAccessToken() ? "/app" : "/login");
  }, [router]);
  return null;
}
