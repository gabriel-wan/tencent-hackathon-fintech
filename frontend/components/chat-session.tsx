"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

// "New chat": the thread lives only in the chat page's memory (it never reaches the backend), so a new chat
// is a fresh ChatPanel. The sidebar bumps the key; the chat page keys its panel on it.
type ChatSession = { chatKey: number; newChat: () => void };

const ChatSessionContext = createContext<ChatSession>({ chatKey: 0, newChat: () => {} });

export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [chatKey, setChatKey] = useState(0);
  const newChat = useCallback(() => {
    setChatKey((key) => key + 1);
    router.push("/");
  }, [router]);
  const value = useMemo(() => ({ chatKey, newChat }), [chatKey, newChat]);
  return <ChatSessionContext.Provider value={value}>{children}</ChatSessionContext.Provider>;
}

export function useChatSession(): ChatSession {
  return useContext(ChatSessionContext);
}
