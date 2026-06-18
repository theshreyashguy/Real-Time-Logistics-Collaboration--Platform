"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import ChatView from "@/components/ChatView";

export default function ChannelPage() {
  const { id } = useParams<{ id: string }>();
  const [title, setTitle] = useState("channel");

  useEffect(() => {
    api.listAllChannels()
      .then((cs) => {
        const c = cs.find((x) => x.id === id);
        if (c?.name) setTitle(`# ${c.name}`);
      })
      .catch(() => {});
  }, [id]);

  return <ChatView key={id} mode="channel" id={id} title={title} />;
}
