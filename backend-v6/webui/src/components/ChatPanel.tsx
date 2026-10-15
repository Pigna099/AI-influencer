import { useState, useRef, useEffect } from "react";
import { api, ChatImage, ChatVideo, Conversation, Message } from "../api";
import {useI18n} from "../i18n";
import Lightbox from "./Lightbox";

function MessagePhoto({ image, onView, onUnlock, loadingLabel, altTemplate, unlockLabel, priceLabel }: { image: ChatImage; onView: (url: string, alt: string) => void; onUnlock: (id: string) => void; loadingLabel: string; altTemplate: string; unlockLabel: string; priceLabel: string }) {
  const [url, setUrl] = useState("");
  const alt = altTemplate.replace("{prompt}", image.prompt.slice(0, 80));
  const locked = image.price_cents > 0 && !image.unlocked;
  useEffect(() => {
    let objectUrl = "";
    let alive = true;
    setUrl("");
    api.fetchBlob(`/api/chat-images/${image.id}/file?v=${image.unlocked_at ?? "locked"}`)
      .then(blob => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => setUrl(""));
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [image.id, image.unlocked_at]);
  if (!url) return <span className="photo-loading">{loadingLabel}</span>;
  if (locked) return <div className="locked-photo">
    <img src={url} alt={alt} loading="lazy" />
    <div className="locked-overlay">
      <span className="lock-icon" aria-hidden="true">🔒</span>
      <b>{priceLabel}</b>
      <button className="primary" onClick={() => onUnlock(image.id)}>{unlockLabel}</button>
    </div>
  </div>;
  return <img className="chat-photo" src={url} alt={alt} loading="lazy" onClick={() => onView(url, alt)} />;
}

function MessageVideo({ video, onUnlock, loadingLabel, playLabel, unlockLabel, priceLabel }: {
  video: ChatVideo;
  onUnlock: (id: string) => void;
  loadingLabel: string;
  playLabel: string;
  unlockLabel: string;
  priceLabel: string;
}) {
  const [url, setUrl] = useState("");
  const [poster, setPoster] = useState("");
  const [loading, setLoading] = useState(false);
  const locked = video.price_cents > 0 && !video.unlocked;

  useEffect(() => {
    let objectUrl = "";
    let alive = true;
    setPoster("");
    if (!video.thumb_filename) return;
    api.fetchBlob(`/api/videos/${video.video_id}/thumb`)
      .then(blob => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setPoster(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [video.id, video.video_id, video.thumb_filename]);

  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url);
  }, [url]);

  const play = async () => {
    if (url || loading) return;
    setLoading(true);
    try {
      const blob = await api.fetchBlob(`/api/chat-videos/${video.id}/file`);
      setUrl(URL.createObjectURL(blob));
    } catch {
      setPoster(poster);
    } finally {
      setLoading(false);
    }
  };

  return <div className={`chat-video ${locked ? "locked" : ""}`}>
    {url ? <video src={url} controls autoPlay playsInline /> : <>
      {poster ? <img src={poster} alt={video.prompt.slice(0, 80)} /> : <span className="photo-loading">{loadingLabel}</span>}
      {locked
        ? <div className="locked-overlay">
            <span className="lock-icon" aria-hidden="true">🔒</span>
            <b>{priceLabel}</b>
            <button className="primary" onClick={() => onUnlock(video.id)}>{unlockLabel}</button>
          </div>
        : <button type="button" className="video-play" disabled={loading} onClick={play} aria-label={playLabel}>{loading ? <span className="spinner" /> : "▶"}</button>}
    </>}
  </div>;
}

interface Props {
  conversation: Conversation | null;
  messages: Message[];
  onSendMessage: (content: string) => Promise<boolean>;
  onUnlockImage?: (id: string) => void;
  onUnlockVideo?: (id: string) => void;
  loading: boolean;
  waiting?: boolean;
  waitingElapsed?: number;
  busyLabel: string;
  elapsed: number;
  fanName: string;
}

export default function ChatPanel({ conversation, messages, onSendMessage, onUnlockImage, onUnlockVideo, loading, waiting = false, waitingElapsed = 0, busyLabel, elapsed, fanName }: Props) {
  const { t } = useI18n();
  const [input, setInput] = useState("");
  const [viewer, setViewer] = useState<{ url: string; alt: string } | null>(null);
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
  return <section className="chat-surface" aria-label={t("chat.aria")}>
    <div className="message-scroll" ref={scrollRef} role="log" aria-live="polite" aria-relevant="additions">
      {!conversation && !loading && <div className="chat-empty"><div className="chat-symbol">“</div><h3>{t("chat.empty.title")}</h3><p>{t("chat.empty.line1")}<br />{t("chat.empty.line2")}</p><div className="hint-pills"><span>{t("chat.hint.memory")}</span><span>{t("chat.hint.timing")}</span><span>{t("chat.hint.initiative")}</span></div></div>}
      {messages.length > 60 && !showAll && <button className="older-messages" onClick={() => setShowAll(true)}>{t("chat.showOlder", { count: messages.length - 60 })}</button>}
      {(showAll ? messages : messages.slice(-60)).map(msg => {
        const m = msg.ollama_metrics;
        const tps = m?.eval_duration && m?.eval_count ? m.eval_count / (m.eval_duration / 1e9) : null;
        const proposal = m?.proposal as { kind?: string; locked?: boolean; price_cents?: number } | undefined;
        const content = m?.guarded ? t("chat.guardedReply") : msg.content;
        return <div key={msg.id} className={`message-row ${msg.role}`}><div className="message-block">
          <div className="message-author">{msg.role === "user" ? fanName : conversation?.character_snapshot.name}<span>{new Date(msg.created_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</span></div>
          <div className="bubble"><p>{content}</p>{!!msg.images?.length && <div className="message-photos">{msg.images.map(image => <MessagePhoto key={image.id} image={image} onView={(url, alt) => setViewer({ url, alt })} onUnlock={id => onUnlockImage?.(id)} loadingLabel={t("chat.photo.loading")} altTemplate={t("chat.photo.alt")} unlockLabel={t("chat.unlock")} priceLabel={`€${(image.price_cents / 100).toFixed(2)}`} />)}</div>}{!!msg.videos?.length && <div className="message-videos">{msg.videos.map(video => <MessageVideo key={video.id} video={video} onUnlock={id => onUnlockVideo?.(id)} loadingLabel={t("chat.photo.loading")} playLabel={t("vd.play")} unlockLabel={t("chat.unlock")} priceLabel={`€${(video.price_cents / 100).toFixed(2)}`} />)}</div>}</div>
          {m && <div className="message-metrics"><span>{msg.model}</span>{m.request_seconds != null && <b>{m.request_seconds.toFixed(2)} s</b>}{tps != null && <span>{tps.toFixed(1)} token/s</span>}{m.kind && m.kind !== "reply" && <span>{m.kind === "opener" ? t("chat.kind.opener") : m.kind === "photo" ? t("chat.kind.photo") : t("chat.kind.reengage")}</span>}{proposal && <span className="proposal-chip">{t("chat.proposal")}: {proposal.kind === "video" ? t("chat.proposal.video") : t("chat.proposal.photo")}{proposal.locked ? ` · ${t("chat.proposal.locked")}` : ""}{proposal.price_cents ? ` · €${(proposal.price_cents / 100).toFixed(2)}` : ""}</span>}{m.guarded && <span className="warning">{t("chat.guarded")}</span>}{m.image_error && <span className="warning">{t("chat.imageError")}</span>}{m.done_reason === "length" && <span>{t("chat.tokenLimit")}</span>}</div>}
        </div></div>;
      })}
      {(loading || waiting) && <div className="message-row assistant"><div className="thinking" role="status"><span className="typing-dots"><i /><i /><i /></span><span>{loading ? (busyLabel || t("chat.thinking")) : t("chat.waiting")} <b>{(loading ? elapsed : waitingElapsed).toFixed(1)} s</b></span></div></div>}
      {loading && elapsed > 20 && <p className="slow-hint">{t("chat.slow")}</p>}
    </div>
    <form className="composer" onSubmit={e => { e.preventDefault(); void submit(); }}>
      <textarea ref={inputRef} aria-label={t("chat.fanMessageAria")} value={input} onChange={e => setInput(e.target.value)} placeholder={conversation ? t("chat.placeholder.write", { name: fanName }) : t("chat.placeholder.start")} rows={2} maxLength={10000} disabled={!conversation || loading}
        onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit(); } }} />
      <div><span>{t("chat.composerHint")}</span><button className="primary" disabled={!conversation || loading || !input.trim()} type="submit">{t("chat.send")} <span aria-hidden="true">↑</span></button></div>
    </form>
    {viewer && <Lightbox src={viewer.url} alt={viewer.alt} onClose={() => setViewer(null)} />}
  </section>;
}
