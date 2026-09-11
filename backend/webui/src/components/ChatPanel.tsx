import { Conversation, Message } from "../api";
import { useState, useRef, useEffect } from "react";

interface ChatPanelProps {
  conversation: Conversation;
  messages: Message[];
  onSendMessage: (content: string) => void;
  loading: boolean;
  error: string | null;
}

export default function ChatPanel({ conversation, messages, onSendMessage, loading, error }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    
    const message = input;
    setInput("");
    onSendMessage(message);
  };

  const maxHistory = messages.slice(-12);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4 space-y-reverse" ref={scrollRef}>
      {maxHistory.length === 0 ? (
        <div className="text-center text-gray-500 py-8">
          <p>No messages yet. Start the conversation!</p>
        </div>
      ) : (
        maxHistory.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-800 text-gray-200 border border-gray-700"
              }`}
            >
              <p className="text-sm leading-relaxed">{msg.content}</p>
              <div className="mt-2 flex items-center gap-2 text-xs opacity-50">
                <span>{msg.role === "user" ? "You" : conversation.character_snapshot.name}</span>
                <span>•</span>
                <span>{new Date(msg.created_at).toLocaleTimeString()}</span>
                {msg.model && (
                  <>
                    <span>•</span>
                    <span>{msg.model.replace(/:latest$/, "")}</span>
                  </>
                )}
              </div>
              {msg.ollama_metrics && (
                <div className="mt-2 text-xs opacity-75">
                  <div className="flex gap-3">
                    <span>
                      Tokens: {msg.ollama_metrics.prompt_eval_count || 0} → {msg.ollama_metrics.eval_count || 0}
                    </span>
                    <span>
                      Duration: {msg.ollama_metrics.eval_duration ? `${(msg.ollama_metrics.eval_duration / 1e9).toFixed(2)}s` : "N/A"}
                    </span>
                    <span>
                      TPS: {msg.ollama_metrics.eval_duration && msg.ollama_metrics.eval_count 
                        ? (msg.ollama_metrics.eval_count / (msg.ollama_metrics.eval_duration / 1e9)).toFixed(2) 
                        : "N/A"}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-200 text-sm">
          {error}
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className={`sticky bottom-0 bg-gray-900 pt-4 ${loading ? "opacity-50" : ""}`}
      >
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`Message ${conversation.character_snapshot.name}...`}
            className="flex-1 px-4 py-3 bg-gray-950 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
          >
            {loading ? "..." : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}
