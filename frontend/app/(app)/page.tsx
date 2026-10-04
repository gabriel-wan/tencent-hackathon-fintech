import { ChatPanel } from "@/components/chat/chat-panel";

export default function ChatPage() {
  return (
    <main id="main" tabIndex={-1} className="flex flex-1 flex-col outline-none">
      <h1 className="sr-only">Chat</h1>
      <ChatPanel />
    </main>
  );
}
