import { useState, useRef, useEffect } from "react";
import { Conversation, Message } from "../api";

interface Props {
  conversation: Conversation | null;
  messages: Message[];
  onSendMessage: (content: string) => Promise<boolean>;
  loading: boolean;
  busyLabel: string;
  elapsed: number;
  fanName: string;
}

export default function ChatPanel({ conversation, messages, onSendMessage, loading, busyLabel, elapsed, fanName }: Props) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [showAll, setShowAll] = useState(false);
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); }, [messages, loading]);
  useEffect(() => { setInput(""); setShowAll(false); }, [conversation?.id]);
  const submit = async () => {
    if (loading || !input.trim() || !conversation) return;
    const outgoing = input;
    setInput("");
    if (!await onSendMessage(outgoing)) setInput(outgoing);
    inputRef.current?.focus();
  };
  return <section className="chat-surface" aria-label="Chat con il personaggio">
    <div className="message-scroll" ref={scrollRef} role="log" aria-live="polite" aria-relevant="additions">
      {!conversation && !loading && <div className="chat-empty"><div className="chat-symbol">“</div><h3>Una personalità prende vita qui.</h3><p>Scegli personaggio, fan e modello.<br />Con “Nuova chat” sarà il personaggio a scrivere per primo.</p><div className="hint-pills"><span>Memoria separata per fan</span><span>Tempi reali</span><span>Iniziativa e tono</span></div></div>}
      {messages.length > 60 && !showAll && <button className="older-messages" onClick={() => setShowAll(true)}>Mostra i messaggi precedenti ({messages.length - 60})</button>}
      {(showAll ? messages : messages.slice(-60)).map(msg => {
        const m = msg.ollama_metrics;
        const tps = m?.eval_duration && m?.eval_count ? m.eval_count / (m.eval_duration / 1e9) : null;
        return <div key={msg.id} className={`message-row ${msg.role}`}><div className="message-block">
          <div className="message-author">{msg.role === "user" ? fanName : conversation?.character_snapshot.name}<span>{new Date(msg.created_at).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}</span></div>
          <div className="bubble"><p>{msg.content}</p></div>
          {m && <div className="message-metrics"><span>{msg.model}</span>{m.request_seconds != null && <b>{m.request_seconds.toFixed(2)} s</b>}{tps != null && <span>{tps.toFixed(1)} token/s</span>}{m.kind && m.kind !== "reply" && <span>{m.kind === "opener" ? "Primo messaggio" : "Ritorno"}</span>}{m.done_reason === "length" && <span>Limite token raggiunto</span>}</div>}
        </div></div>;
      })}
      {loading && <div className="message-row assistant"><div className="thinking" role="status"><span className="typing-dots"><i /><i /><i /></span><span>{busyLabel || "Sta scrivendo"} <b>{elapsed.toFixed(1)} s</b></span></div></div>}
      {loading && elapsed > 20 && <p className="slow-hint">Il primo messaggio può richiedere più tempo per caricare il modello. Puoi continuare a leggere la chat.</p>}
    </div>
    <form className="composer" onSubmit={e => { e.preventDefault(); void submit(); }}>
      <textarea ref={inputRef} aria-label="Messaggio del fan" value={input} onChange={e => setInput(e.target.value)} placeholder={conversation ? `Scrivi come ${fanName}…` : "Avvia una chat per scrivere…"} rows={2} maxLength={10000} disabled={!conversation || loading}
        onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit(); } }} />
      <div><span>Invio per inviare · Maiusc + Invio per andare a capo</span><button className="primary" disabled={!conversation || loading || !input.trim()} type="submit">Invia <span aria-hidden="true">↑</span></button></div>
    </form>
  </section>;
}
