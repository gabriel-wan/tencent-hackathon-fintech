"use client";

import { useChatSession } from "@/components/chat-session";

import { ChatPanel } from "./chat-panel";

/** A fresh panel (and so an empty thread) each time "New chat" is pressed. */
export function ChatHost() {
  const { chatKey } = useChatSession();
  return <ChatPanel key={chatKey} />;
}
