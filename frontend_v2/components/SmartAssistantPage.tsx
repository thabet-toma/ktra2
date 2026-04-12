import React, { useEffect, useRef, useState } from "react";
import { Send, Sparkles, User, Bot, Loader2 } from "lucide-react";
import { sendAssistantMessage } from "@/services/assistantApi";

type Role = "user" | "assistant";

interface ChatMessage {
  id: string;
  role: Role;
  content: string;
}

export const SmartAssistantPage: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setSending(true);

    try {
      const reply = await sendAssistantMessage(text);
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: reply || "—",
        },
      ]);
    } catch (e) {
      const err = e instanceof Error ? e.message : "حدث خطأ غير متوقع";
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `⚠️ ${err}`,
        },
      ]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col max-w-3xl mx-auto w-full px-4 pb-8 pt-2 md:pt-6">
      <div className="mb-6 flex items-start gap-4">
        <div className="p-3 rounded-2xl bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow-lg shadow-indigo-500/25">
          <Sparkles className="w-8 h-8" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            المساعد الذكي
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 max-w-xl">
            اسأل عن إجراءات الشراء، الشحن، أو البيانات الداخلية حسب ما يوفّره
            مسار n8n المرتبط — الطلب يمر عبر الخادم بشكل آمن.
          </p>
        </div>
      </div>

      <div className="flex-1 flex flex-col rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900/80 shadow-sm overflow-hidden min-h-[420px]">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center px-6 py-16 text-gray-400 dark:text-gray-500">
              <Bot className="w-14 h-14 mb-4 opacity-40" />
              <p className="text-sm font-medium">ابدأ محادثة بكتابة سؤالك أدناه</p>
            </div>
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
            >
              <div
                className={`flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-violet-100 dark:bg-violet-900/50 text-violet-700 dark:text-violet-300"
                }`}
              >
                {msg.role === "user" ? (
                  <User className="w-4 h-4" />
                ) : (
                  <Bot className="w-4 h-4" />
                )}
              </div>
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white rounded-tr-sm"
                    : "bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-tl-sm"
                }`}
              >
                <p className="whitespace-pre-wrap break-words">{msg.content}</p>
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex gap-3 items-center text-gray-500 dark:text-gray-400 text-sm">
              <div className="w-9 h-9 rounded-xl bg-violet-100 dark:bg-violet-900/50 flex items-center justify-center">
                <Loader2 className="w-4 h-4 animate-spin text-violet-600" />
              </div>
              <span>جارٍ التفكير…</span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="p-4 border-t border-gray-100 dark:border-gray-800 bg-gray-50/80 dark:bg-gray-900/50">
          <div className="flex gap-2 items-end">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="اكتب سؤالك… (Enter للإرسال، Shift+Enter سطر جديد)"
              rows={2}
              disabled={sending}
              className="flex-1 resize-none rounded-xl border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 py-3 text-sm text-gray-900 dark:text-white placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 disabled:opacity-60"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={sending || !input.trim()}
              className="h-12 w-12 shrink-0 rounded-xl bg-indigo-600 text-white flex items-center justify-center hover:bg-indigo-700 disabled:opacity-50 disabled:pointer-events-none transition-colors shadow-md shadow-indigo-600/20"
              title="إرسال"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
