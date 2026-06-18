"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import ChatView from "@/components/ChatView";

export default function DMPage() {
  const { id } = useParams<{ id: string }>();
  const [title, setTitle] = useState("direct message");

  useEffect(() => {
    api.listUsers()
      .then((us) => {
        const u = us.find((x) => x.id === id);
        if (u) setTitle(u.display_name);
      })
      .catch(() => {});
  }, [id]);

  return <ChatView key={id} mode="dm" id={id} title={title} />;
}
