import { ChatPanel } from "@/components/chat/chat-panel";

export default function ChatPage() {
  return (
    <main className="flex flex-1 flex-col">
      <h1 className="sr-only">Chat</h1>
      <ChatPanel />
    </main>
  );
}
