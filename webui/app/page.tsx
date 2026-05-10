"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";

type Message = { role: string; content: string };
const API_HOST = process.env.NEXT_PUBLIC_API_HOST || "127.0.0.1";
const API_PORT = process.env.NEXT_PUBLIC_API_PORT || "8000";
const WS_URL = `ws://${API_HOST}:${API_PORT}/ws/chat`;
const API_URL = `http://${API_HOST}:${API_PORT}`;

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [thinking, setThinking] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === "history") {
        setMessages(data.messages || []);
      } else if (data.type === "tool_result") {
        setThinking(true);
        setMessages((prev) => [...prev, { role: "tool", content: `**[${data.name}]**\n\`\`\`\n${data.content}\n\`\`\`` }]);
      } else if (data.type === "message") {
        setThinking(false);
        setMessages((prev) => {
          const filtered = prev.filter((m) => m.role !== "status");
          return [...filtered, { role: "assistant", content: data.content }];
        });
      }
    };
    wsRef.current = ws;
    return () => ws.close();
  }, []);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, thinking]);

  const send = () => {
    if (!input.trim() || !wsRef.current) return;
    setMessages((prev) => [...prev, { role: "user", content: input }]);
    wsRef.current.send(JSON.stringify({ content: input }));
    setInput("");
    setThinking(true);
  };

  const stop = () => {
    wsRef.current?.send(JSON.stringify({ __abort: true }));
    setThinking(false);
  };

  const clearSession = async () => {
    await fetch(`${API_URL}/api/session`, { method: "DELETE" });
    setMessages([]);
  };

  return (
    <div className="flex flex-col h-screen bg-[#0d0d0d] text-white">
      {/* Header */}
      <header className="flex items-center justify-between px-5 py-3 border-b border-white/5 shrink-0">
        <div className="flex items-center gap-3">
          <div className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]" : "bg-red-400"}`} />
          <h1 className="text-sm font-medium tracking-wide text-white/90">Noesis</h1>
          <span className="text-[11px] text-white/30 hidden sm:inline">Multi-platform Agent</span>
        </div>
        <div className="flex items-center gap-3">
          <a href="/skills" className="text-[11px] text-white/30 hover:text-white/60 transition-colors">Skills</a>
          <a href="/memory" className="text-[11px] text-white/30 hover:text-white/60 transition-colors">Graph</a>
          <button onClick={clearSession} className="text-[11px] text-white/30 hover:text-white/60 transition-colors">Clear</button>
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-5 py-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-white/15">
            <div className="text-4xl mb-3">◆</div>
            <p className="text-sm">Send a message to start</p>
          </div>
        )}

        <div className="max-w-3xl mx-auto space-y-4">
          {messages.map((m, i) => {
            const isUser = m.role === "user";
            const isTool = m.role === "tool";

            if (isTool) {
              return (
                <div key={i} className="flex gap-3 justify-start">
                  <div className="w-7 h-7 rounded-full bg-white/5 flex items-center justify-center shrink-0 text-[10px] text-white/30 mt-0.5">⚙</div>
                  <div className="bg-[#1a1a1a] border border-white/5 rounded-xl px-3 py-2 text-xs text-white/50 max-w-[85%] overflow-x-auto">
                    <ReactMarkdown
                      components={{
                        code: ({ children }) => <code className="text-white/40 text-[11px]">{children}</code>,
                        strong: ({ children }) => <strong className="text-white/60">{children}</strong>,
                      }}
                    >
                      {m.content}
                    </ReactMarkdown>
                  </div>
                </div>
              );
            }

            return (
              <div key={i} className={`flex gap-3 ${isUser ? "flex-row-reverse" : "justify-start"}`}>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 text-[10px] ${isUser ? "bg-blue-500/20 text-blue-300" : "bg-white/5 text-white/40"}`}>
                  {isUser ? "👤" : "🤖"}
                </div>
                <div className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed max-w-[85%] ${
                  isUser
                    ? "bg-blue-600/15 text-blue-100 rounded-tr-md"
                    : "bg-white/[0.02] border border-white/5 text-white/80 rounded-tl-md"
                }`}>
                  {isUser ? (
                    <p className="whitespace-pre-wrap">{m.content}</p>
                  ) : (
                    <div className="prose prose-invert prose-sm max-w-none
                      prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0
                      prose-code:bg-white/10 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs
                      prose-pre:bg-[#1a1a1a] prose-pre:border prose-pre:border-white/5 prose-pre:rounded-lg
                      prose-headings:text-white/80 prose-strong:text-white/90
                      prose-a:text-blue-400">
                      <ReactMarkdown>{m.content}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {thinking && (
            <div className="flex gap-3 justify-start">
              <div className="w-7 h-7 rounded-full bg-white/5 flex items-center justify-center shrink-0 text-[10px]">🤖</div>
              <div className="flex items-center gap-2 text-white/30 text-xs py-2">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-white/30 animate-pulse" />
                Thinking...
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </main>

      {/* Input */}
      <footer className="px-5 py-3 border-t border-white/5 shrink-0">
        <div className="flex gap-2 max-w-3xl mx-auto">
          <input
            id="chat-input"
            className="flex-1 bg-white/[0.03] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white/80 placeholder:text-white/20 focus:outline-none focus:border-white/20 transition-colors"
            placeholder="Message Noesis..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
          />
          {thinking && (
            <button onClick={stop} className="bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 rounded-xl px-4 py-2.5 text-sm text-red-300 transition-colors shrink-0">Stop</button>
          )}
          <button onClick={send} disabled={!input.trim()}
            className="bg-white/10 hover:bg-white/15 disabled:opacity-30 rounded-xl px-5 py-2.5 text-sm font-medium transition-colors shrink-0">Send</button>
        </div>
      </footer>
    </div>
  );
}
