"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { chatApi } from "@/lib/api";
import type { ChatMessage, ChatProfileItem } from "@/types";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import {
  Send,
  Bot,
  User,
  Settings2,
  Trash2,
  MessageSquare,
  Loader2,
  Sparkles,
  ChevronDown,
} from "lucide-react";

// ─────────────────────────────────────────────────────────────────────────────
// Suggestion prompts for welcome state
// ─────────────────────────────────────────────────────────────────────────────

const SUGGESTIONS = [
  "Explain the key differences between unit tests and integration tests.",
  "Write a Python function to validate an email address.",
  "What are the best practices for REST API design?",
  "How does async/await work in JavaScript?",
];

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function makeId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

/** Render plain text – convert newlines to <br/> elements */
function renderText(text: string): React.ReactNode {
  const parts = text.split("\n");
  return parts.map((part, i) => (
    <React.Fragment key={i}>
      {part}
      {i < parts.length - 1 && <br />}
    </React.Fragment>
  ));
}

// ─────────────────────────────────────────────────────────────────────────────
// ProfileSelector
// ─────────────────────────────────────────────────────────────────────────────

interface ProfileSelectorProps {
  profiles: ChatProfileItem[];
  selectedId: number | null;
  onChange: (id: number | null) => void;
  disabled?: boolean;
}

function ProfileSelector({
  profiles,
  selectedId,
  onChange,
  disabled,
}: ProfileSelectorProps) {
  const selected = profiles.find((p) => p.id === selectedId) ?? null;

  return (
    <div className="relative">
      <label className="block text-[11px] font-semibold uppercase tracking-widest text-[#3d5070] mb-1.5">
        LLM Profile
      </label>
      <div className="relative">
        <select
          disabled={disabled}
          value={selectedId ?? ""}
          onChange={(e) => {
            const val = e.target.value;
            onChange(val === "" ? null : Number(val));
          }}
          className={cn(
            "w-full appearance-none rounded-lg px-3 py-2 pr-8 text-sm",
            "bg-[#101622] border border-[#2b3b55] text-white",
            "focus:outline-none focus:ring-2 focus:ring-[#135bec] focus:border-transparent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-colors duration-150",
          )}
        >
          <option value="">— Use default profile —</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} · {p.model}
              {p.is_default ? " (default)" : ""}
            </option>
          ))}
        </select>
        <ChevronDown
          className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#3d5070]"
          aria-hidden="true"
        />
      </div>
      {selected && (
        <p className="mt-1 text-[11px] text-[#3d5070]">
          {selected.provider} · {selected.model}
          {selected.is_default && (
            <span className="ml-1.5 px-1.5 py-0.5 rounded bg-[#135bec]/20 text-[#5b9eff] font-medium">
              default
            </span>
          )}
        </p>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SettingsPanel
// ─────────────────────────────────────────────────────────────────────────────

interface SettingsPanelProps {
  profiles: ChatProfileItem[];
  selectedProfileId: number | null;
  onProfileChange: (id: number | null) => void;
  systemPrompt: string;
  onSystemPromptChange: (value: string) => void;
  disabled?: boolean;
}

function SettingsPanel({
  profiles,
  selectedProfileId,
  onProfileChange,
  systemPrompt,
  onSystemPromptChange,
  disabled,
}: SettingsPanelProps) {
  return (
    <div className="border-b border-[#2b3b55] bg-[#18202F] px-4 py-3 space-y-3">
      <ProfileSelector
        profiles={profiles}
        selectedId={selectedProfileId}
        onChange={onProfileChange}
        disabled={disabled}
      />
      <div>
        <label className="block text-[11px] font-semibold uppercase tracking-widest text-[#3d5070] mb-1.5">
          System Prompt
          <span className="ml-2 normal-case tracking-normal font-normal text-[#3d5070]">
            (optional)
          </span>
        </label>
        <textarea
          disabled={disabled}
          value={systemPrompt}
          onChange={(e) => onSystemPromptChange(e.target.value)}
          rows={3}
          placeholder="You are a helpful assistant..."
          className={cn(
            "w-full resize-none rounded-lg px-3 py-2 text-sm",
            "bg-[#101622] border border-[#2b3b55] text-white placeholder-[#3d5070]",
            "focus:outline-none focus:ring-2 focus:ring-[#135bec] focus:border-transparent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "font-[JetBrains_Mono,monospace] transition-colors duration-150",
          )}
        />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// WelcomeState
// ─────────────────────────────────────────────────────────────────────────────

interface WelcomeStateProps {
  onSuggestion: (text: string) => void;
}

function WelcomeState({ onSuggestion }: WelcomeStateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 py-12 text-center select-none">
      {/* Icon */}
      <div className="mb-5 w-16 h-16 rounded-2xl bg-[#135bec]/15 border border-[#135bec]/30 flex items-center justify-center shadow-lg shadow-[#135bec]/10">
        <Sparkles className="w-8 h-8 text-[#5b9eff]" aria-hidden="true" />
      </div>

      {/* Heading */}
      <h2 className="text-2xl font-bold text-white mb-2 tracking-tight">
        Chat with AI
      </h2>
      <p className="text-sm text-[#92a4c9] max-w-sm mb-8">
        Ask anything — code, concepts, analysis. Pick a model from settings or
        use the default.
      </p>

      {/* Suggestions */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-xl">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onSuggestion(s)}
            className={cn(
              "text-left px-4 py-3 rounded-xl text-sm",
              "bg-[#18202F] border border-[#2b3b55]",
              "text-[#92a4c9] hover:text-white hover:border-[#135bec]/50 hover:bg-[#1e2a3d]",
              "transition-all duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
            )}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MessageBubble
// ─────────────────────────────────────────────────────────────────────────────

interface MessageBubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex items-end gap-2.5 w-full",
        isUser ? "flex-row-reverse" : "flex-row",
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "shrink-0 w-7 h-7 rounded-full flex items-center justify-center mb-0.5",
          isUser
            ? "bg-[#135bec] shadow-md shadow-[#135bec]/30"
            : "bg-[#1e2a3d] border border-[#2b3b55]",
        )}
        aria-hidden="true"
      >
        {isUser ? (
          <User className="w-3.5 h-3.5 text-white" />
        ) : (
          <Bot className="w-3.5 h-3.5 text-[#5b9eff]" />
        )}
      </div>

      {/* Bubble */}
      <div
        className={cn(
          "relative max-w-[75%] px-4 py-3 text-sm leading-relaxed wrap-break-word",
          isUser
            ? "bg-[#135bec] text-white rounded-2xl rounded-tr-sm shadow-md shadow-[#135bec]/20"
            : "bg-[#18202F] text-white border border-[#2b3b55] rounded-2xl rounded-tl-sm",
        )}
      >
        {/* Content */}
        <span>{renderText(message.content)}</span>

        {/* Streaming cursor */}
        {message.streaming && (
          <span
            className="inline-block w-0.5 h-4 bg-[#5b9eff] ml-0.5 align-middle animate-pulse"
            aria-hidden="true"
          />
        )}

        {/* Empty streaming placeholder */}
        {message.streaming && message.content === "" && (
          <span className="flex items-center gap-1 text-[#3d5070]">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span className="text-xs">Thinking…</span>
          </span>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ChatInput
// ─────────────────────────────────────────────────────────────────────────────

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
}

function ChatInput({ value, onChange, onSend, disabled }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const lineHeight = 24;
    const minHeight = lineHeight * 1;
    const maxHeight = lineHeight * 5;
    el.style.height =
      Math.min(Math.max(el.scrollHeight, minHeight), maxHeight) + "px";
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && value.trim()) {
        onSend();
      }
    }
  };

  const canSend = !disabled && value.trim().length > 0;

  return (
    <div className="border-t border-[#2b3b55] bg-[#18202F] px-4 py-3">
      <div
        className={cn(
          "relative flex items-end gap-2 rounded-xl border bg-[#101622]",
          "transition-colors duration-150",
          disabled
            ? "border-[#2b3b55] opacity-70"
            : "border-[#2b3b55] focus-within:border-[#135bec]",
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          placeholder="Type a message… (Enter to send, Shift+Enter for new line)"
          aria-label="Message input"
          className={cn(
            "flex-1 resize-none bg-transparent px-4 py-3 text-sm text-white",
            "placeholder-[#3d5070] outline-none",
            "disabled:cursor-not-allowed",
            "min-h-11 max-h-30",
            "font-[JetBrains_Mono,monospace]",
          )}
          style={{ lineHeight: "24px" }}
        />

        {/* Send button */}
        <div className="shrink-0 p-2 pb-2.5">
          <button
            type="button"
            onClick={onSend}
            disabled={!canSend}
            aria-label="Send message"
            className={cn(
              "flex items-center justify-center w-8 h-8 rounded-lg",
              "transition-all duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
              canSend
                ? "bg-[#135bec] text-white hover:bg-[#1a6aff] shadow-md shadow-[#135bec]/30"
                : "bg-[#1e2a3d] text-[#3d5070] cursor-not-allowed",
            )}
          >
            {disabled ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>

      <p className="mt-1.5 text-[10px] text-[#3d5070] text-center">
        AI can make mistakes. Verify important information.
      </p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ChatPage
// ─────────────────────────────────────────────────────────────────────────────

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(
    null,
  );
  const [profiles, setProfiles] = useState<ChatProfileItem[]>([]);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  // ── Load profiles on mount ──────────────────────────────────────────────────
  useEffect(() => {
    chatApi
      .getProfiles()
      .then((data) => {
        setProfiles(data);
        const def = data.find((p) => p.is_default);
        if (def) setSelectedProfileId(def.id);
      })
      .catch(() => {
        // Profiles are optional — silently ignore
      });
  }, []);

  // ── Scroll to bottom ────────────────────────────────────────────────────────
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // ── Send message ────────────────────────────────────────────────────────────
  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      setError(null);

      const userMsg: ChatMessage = {
        id: makeId(),
        role: "user",
        content: trimmed,
        timestamp: new Date(),
      };

      const assistantId = makeId();
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        streaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setInput("");
      setIsStreaming(true);

      try {
        // Build history for the request (exclude the empty assistant placeholder)
        const historyMsgs = [...messages, userMsg].map((m) => ({
          role: m.role as string,
          content: m.content,
        }));

        const response = await chatApi.sendStream(
          historyMsgs,
          selectedProfileId,
          systemPrompt.trim() || null,
        );

        if (!response.ok) {
          const errText = await response.text();
          throw new Error(errText || `HTTP ${response.status}`);
        }

        if (!response.body) {
          throw new Error("Response body is null.");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const jsonStr = line.slice(6).trim();
            if (!jsonStr) continue;

            try {
              const event = JSON.parse(jsonStr) as {
                type: "chunk" | "done" | "error";
                content?: string;
                message?: string;
              };

              if (event.type === "chunk" && event.content) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: m.content + event.content }
                      : m,
                  ),
                );
              } else if (event.type === "done") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, streaming: false } : m,
                  ),
                );
                setIsStreaming(false);
              } else if (event.type === "error") {
                throw new Error(event.message ?? "Stream error");
              }
            } catch {
              // Malformed JSON — skip
            }
          }
        }

        // Ensure streaming is marked false even if "done" event was missing
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, streaming: false } : m,
          ),
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setError(msg);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `⚠ Error: ${msg}`, streaming: false }
              : m,
          ),
        );
      } finally {
        setIsStreaming(false);
      }
    },
    [isStreaming, messages, selectedProfileId, systemPrompt],
  );

  const handleSend = useCallback(() => {
    sendMessage(input);
  }, [input, sendMessage]);

  const handleSuggestion = useCallback(
    (text: string) => {
      sendMessage(text);
    },
    [sendMessage],
  );

  const handleClear = () => {
    if (isStreaming) return;
    setMessages([]);
    setError(null);
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="h-full flex flex-col bg-[#101622]">
      {/* ── Header ── */}
      <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-[#2b3b55] bg-[#18202F]">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-[#135bec]/15 border border-[#135bec]/30 flex items-center justify-center">
            <MessageSquare
              className="w-3.5 h-3.5 text-[#5b9eff]"
              aria-hidden="true"
            />
          </div>
          <h1 className="text-sm font-semibold text-white tracking-tight">
            Chat
          </h1>
          {profiles.length > 0 && (
            <span className="hidden sm:inline text-xs text-[#3d5070]">
              {profiles.find((p) => p.id === selectedProfileId)?.name ??
                profiles.find((p) => p.is_default)?.name ??
                "Default profile"}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {/* Clear */}
          <button
            type="button"
            onClick={handleClear}
            disabled={isStreaming || messages.length === 0}
            aria-label="Clear chat"
            title="Clear chat"
            className={cn(
              "flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-xs",
              "text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d]",
              "transition-colors duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
              "disabled:opacity-40 disabled:cursor-not-allowed",
            )}
          >
            <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">Clear</span>
          </button>

          {/* Settings toggle */}
          <button
            type="button"
            onClick={() => setShowSettings((v) => !v)}
            aria-label="Toggle settings"
            aria-expanded={showSettings}
            title="Settings"
            className={cn(
              "flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-xs",
              "transition-colors duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
              showSettings
                ? "bg-[#135bec]/15 text-[#5b9eff] border border-[#135bec]/30"
                : "text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d]",
            )}
          >
            <Settings2 className="w-3.5 h-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">Settings</span>
          </button>
        </div>
      </div>

      {/* ── Settings panel (collapsible) ── */}
      {showSettings && (
        <SettingsPanel
          profiles={profiles}
          selectedProfileId={selectedProfileId}
          onProfileChange={setSelectedProfileId}
          systemPrompt={systemPrompt}
          onSystemPromptChange={setSystemPrompt}
          disabled={isStreaming}
        />
      )}

      {/* ── Error banner ── */}
      {error && (
        <div className="shrink-0 mx-4 mt-3 px-3 py-2.5 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-400 flex items-start gap-2">
          <span className="shrink-0 mt-0.5">⚠</span>
          <span className="flex-1 min-w-0 wrap-break-word">{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="shrink-0 text-red-400/60 hover:text-red-300 transition-colors"
            aria-label="Dismiss error"
          >
            ✕
          </button>
        </div>
      )}

      {/* ── Messages area ── */}
      <div
        ref={messagesContainerRef}
        className="flex-1 overflow-y-auto px-4 py-4"
        aria-label="Chat messages"
        aria-live="polite"
        aria-relevant="additions"
      >
        {messages.length === 0 ? (
          <WelcomeState onSuggestion={handleSuggestion} />
        ) : (
          <div className="space-y-4 max-w-3xl mx-auto">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <div ref={messagesEndRef} aria-hidden="true" />
          </div>
        )}
      </div>

      {/* ── Input area ── */}
      <div className="shrink-0 max-w-3xl mx-auto w-full">
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          disabled={isStreaming}
        />
      </div>
    </div>
  );
}
