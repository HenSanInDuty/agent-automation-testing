import type { Metadata } from "next";
import { ChatPage } from "@/components/chat/ChatPage";

export const metadata: Metadata = {
  title: "Chat",
  description: "Chat directly with an AI model.",
};

export default function ChatRoutePage() {
  return <ChatPage />;
}
