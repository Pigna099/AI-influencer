import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, Character, CheckpointInfo, Conversation, Memory, Message, OllamaModel, CharacterProfile, RealismInput } from "../api";
import { useI18n, LanguageSwitch } from "../i18n";
import CharacterForm from "./CharacterForm";
import ChatPanel from "./ChatPanel";
import BenchmarkPanel from "./BenchmarkPanel";
import CharacterAvatar from "./CharacterAvatar";
import Lightbox from "./Lightbox";

type Fan = { id: string; name: string; notes: string };
type ModelMetric = { model: string; samples: number; mean_seconds: number; median_seconds: number; mean_load_seconds: number };

export default function Playground({ onLogout }: { onLogout: () => void }) {
  const { t, lang } = useI18n();
  const failure = (err: unknown) => (err instanceof Error ? err.message : t("common.failed"));
  const [characters, setCharacters] = useState<Character[]>([]);
  const [fans, setFans] = useState<Fan[]>([]);
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [characterId, setCharacterId] = useState("");
  const [fanId, setFanId] = useState("");
  const [model, setModel] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [metrics, setMetrics] = useState<ModelMetric[]>([]);
  const [busy, setBusy] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Character | "new" | null>(null);
  const [fanEditor, setFanEditor] = useState<Fan | "new" | null>(null);
  const [fanName, setFanName] = useState("");
  const [fanNotes, setFanNotes] = useState("");
  const [tab, setTab] = useState<"chat" | "benchmark">("chat");
  const [checkpoints, setCheckpoints] = useState<CheckpointInfo[]>([]);
  const [photoOpen, setPhotoOpen] = useState(false);
  const [photoScene, setPhotoScene] = useState("");
  const [photoCaption, setPhotoCaption] = useState("");
  const [photoLocked, setPhotoLocked] = useState(false);
  const [photoPrice, setPhotoPrice] = useState("5.00");
  const [viewer, setViewer] = useState<{ url: string; alt: string } | null>(null);
  const [absence, setAbsence] = useState(48);
  const [autoNudge, setAutoNudge] = useState(false);
  const [lastActivity, setLastActivity] = useState(Date.now());
  const [newMemory, setNewMemory] = useState("");
  const [historyPage, setHistoryPage] = useState(1);
  const generation = useRef(0);
  const character = characters.find(c => c.id === characterId);
  const fan = fans.find(f => f.id === fanId);
  const chatModels = models.filter(m => m.chat_capable !== false && (m.kind ? m.kind === "chat" : !m.name.toLowerCase().includes("embed")) && !m.name.toLowerCase().includes("embed"));
  const scope = `fan_id=${encodeURIComponent(fanId)}`;

  useEffect(() => {
    let live = true;
    Promise.all([api.getCharacters(), api.request<Fan[]>("/api/fans"), api.getModels(), api.getCheckpoints()])
      .then(([chars, people, data, imageModels]) => {
        if (!live) return;
        setCharacters(chars); setFans(people); setModels(data.models); setCheckpoints(imageModels.checkpoints);
        setCharacterId(chars[0]?.id || "");
        setFanId(people.find(f => f.id !== "legacy")?.id || people[0]?.id || "");
        setModel(data.models.find(m => m.name === "llama3.1:8b")?.name || data.models.find(m => m.chat_capable !== false)?.name || "");
      }).catch(e => { if (live) setError(failure(e)); });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    generation.current += 1;
    const epoch = generation.current;
    setConversation(null); setMessages([]); setConversations([]); setMemories([]); setMetrics([]); setAutoNudge(false);
    if (!characterId || !fanId) return;
    Promise.all([
      api.request<Conversation[]>(`/api/characters/${characterId}/conversations?${scope}`),
      api.request<Memory[]>(`/api/characters/${characterId}/memories?${scope}`),
      api.request<ModelMetric[]>(`/api/metrics/models?character_id=${characterId}&${scope}`),
    ]).then(([chats, facts, stats]) => {
      if (generation.current !== epoch) return;
      setConversations(chats); setMemories(facts); setMetrics(stats);
    }).catch(e => { if (generation.current === epoch) setError(failure(e)); });
  }, [characterId, fanId, scope]);

  useEffect(() => {
    if (!busy) { setElapsed(0); return; }
    const start = Date.now();
    const timer = window.setInterval(() => setElapsed((Date.now() - start) / 1000), 100);
    return () => window.clearInterval(timer);
  }, [busy]);

  const waiting = !!conversation && (conversation.pending_replies ?? 0) > 0;
  const [waitElapsed, setWaitElapsed] = useState(0);
  useEffect(() => {
    if (!waiting) { setWaitElapsed(0); return; }
    const start = Date.now();
    const timer = window.setInterval(() => setWaitElapsed((Date.now() - start) / 1000), 200);
    return () => window.clearInterval(timer);
  }, [waiting, conversation?.pending_reply_at]);

  const refresh = useCallback(async (id: string) => {
    const epoch = generation.current;
    const [chat, msgs, facts, chats, stats] = await Promise.all([
      api.request<Conversation>(`/api/conversations/${id}`),
      api.request<Message[]>(`/api/conversations/${id}/messages?limit=500`),
      api.request<Memory[]>(`/api/characters/${characterId}/memories?${scope}`),
      api.request<Conversation[]>(`/api/characters/${characterId}/conversations?${scope}`),
      api.request<ModelMetric[]>(`/api/metrics/models?character_id=${characterId}&${scope}`),
    ]);
    if (epoch !== generation.current) return;
    setConversation(chat); setMessages(msgs); setMemories(facts); setConversations(chats); setMetrics(stats);
    if ((chat.unread ?? 0) > 0) {
      void api.markConversationRead(id)
        .then(read => { if (epoch === generation.current) setConversation(read); })
        .catch(() => undefined);
    }
  }, [characterId, scope]);

  const removeConversation = (item: Conversation) => {
    if (!window.confirm(t("pg.deleteChatConfirm"))) return;
    void perform(t("pg.busy.deleteChat"), async () => {
      await api.deleteConversation(item.id);
      setConversations(prev => prev.filter(c => c.id !== item.id));
      if (conversation?.id === item.id) { setConversation(null); setMessages([]); }
    });
  };

  useEffect(() => {
    if (!conversation || !waiting || busy) return;
    const id = conversation.id;
    const epoch = generation.current;
    const timer = window.setInterval(async () => {
      try {
        const current = await api.request<Conversation>(`/api/conversations/${id}`);
        if (generation.current !== epoch) return;
        setConversation(current);
        if ((current.pending_replies ?? 0) === 0) {
          window.clearInterval(timer);
          await refresh(id);
        }
      } catch { window.clearInterval(timer); }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [conversation?.id, waiting, busy, refresh]);

  useEffect(() => {
    if (!conversation || conversation.memory_status !== "pending") return;
    const id = conversation.id, epoch = generation.current;
    let stopped = false, tries = 0;
    const timer = window.setInterval(async () => {
      if (stopped || ++tries > 100) { window.clearInterval(timer); return; }
      try {
        const current = await api.request<Conversation>(`/api/conversations/${id}`);
        if (stopped || generation.current !== epoch) return;
        setConversation(current);
        if (current.memory_status !== "pending") {
          const facts = await api.request<Memory[]>(`/api/characters/${characterId}/memories?${scope}`);
          if (!stopped && generation.current === epoch) setMemories(facts);
          window.clearInterval(timer);
        }
      } catch { window.clearInterval(timer); }
    }, 2500);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [conversation?.id, conversation?.memory_status, characterId, scope]);

  useEffect(() => {
    if (!conversation?.human_mode || tab !== "chat" || busy) return;
    const id = conversation.id, epoch = generation.current, seen = conversation.updated_at;
    const timer = window.setInterval(async () => {
      try {
        const current = await api.request<Conversation>(`/api/conversations/${id}`);
        if (generation.current !== epoch) return;
        if (current.updated_at !== seen || (current.unread ?? 0) > 0) await refresh(id);
      } catch { /* transient */ }
    }, 15000);
    return () => window.clearInterval(timer);
  }, [conversation?.id, conversation?.human_mode, conversation?.updated_at, tab, busy, refresh]);

  const perform = async (label: string, work: () => Promise<void>) => {
    if (busy) return;
    setBusy(label); setError("");
    try { await work(); } catch (e) { setError(failure(e)); } finally { setBusy(""); }
  };

  const startChat = () => perform(t("pg.busy.prepareFirst"), async () => {
    const chat = await api.request<Conversation>(`/api/characters/${characterId}/conversations`, {
      method: "POST", body: JSON.stringify({ model, fan_id: fanId, auto_greet: true }) });
    setConversation(chat); setHistoryPage(1); setLastActivity(Date.now());
    await refresh(chat.id);
    if (chat.greeting_error) setError(t("pg.greetingError", { error: chat.greeting_error }));
  });

  const send = async (content: string) => {
    if (!conversation || busy) return false;
    const id = conversation.id;
    setMessages(prev => [...prev, { id: "pending", conversation_id: id, role: "user", content,
      model: null, ollama_metrics: null, created_at: new Date().toISOString() }]);
    setBusy(t("pg.busy.writing")); setError(""); setLastActivity(Date.now());
    try {
      await api.sendMessage(id, content, true);
      await refresh(id); return true;
    } catch (e) {
      setMessages(prev => prev.filter(m => m.id !== "pending")); setError(failure(e)); return false;
    } finally { setBusy(""); }
  };

  const initiate = useCallback(async (kind: "opener" | "reengage") => {
    if (!conversation || busy) return;
    setBusy(kind === "opener" ? t("pg.busy.prepareFirst") : t("pg.busy.checkin")); setError("");
    setLastActivity(Date.now());
    try {
      await api.request(`/api/conversations/${conversation.id}/initiate`, {
        method: "POST", body: JSON.stringify({ kind, absence_hours: absence }) });
      await refresh(conversation.id);
    } catch (e) { setError(failure(e)); } finally { setBusy(""); }
  }, [conversation, busy, absence, refresh]);

  useEffect(() => {
    if (!autoNudge || !conversation || busy || tab !== "chat") return;
    const timeout = window.setTimeout(() => { setAutoNudge(false); void initiate("reengage"); },
      Math.max(1000, 60000 - (Date.now() - lastActivity)));
    return () => window.clearTimeout(timeout);
  }, [autoNudge, conversation, busy, lastActivity, initiate, tab]);

  const saveCharacter = async (data: { name: string; profile: CharacterProfile }) => {
    const saved = editing && editing !== "new" ? await api.updateCharacter(editing.id, data) : await api.createCharacter(data);
    setCharacters(prev => [...prev.filter(c => c.id !== saved.id), saved]);
    setCharacterId(saved.id); setEditing(null);
  };

  const savePpv = (enabled: boolean, priceCents: number) => {
    if (!character) return;
    void perform(t("pg.busy.ppv"), async () => {
      const updated = await api.setPpv(character.id, { enabled, price_cents: Math.max(0, Math.min(100000, priceCents)) });
      setCharacters(prev => prev.map(item => (item.id === updated.id ? updated : item)));
    });
  };

  const saveRealism = (patch: Partial<RealismInput>) => {
    if (!character) return;
    const data: RealismInput = {
      reply_delay_min_seconds: character.reply_delay_min_seconds ?? 8,
      reply_delay_max_seconds: character.reply_delay_max_seconds ?? 40,
      activity_enabled: character.activity_enabled ?? false,
      activity_start_hour: character.activity_start_hour ?? 9,
      activity_end_hour: character.activity_end_hour ?? 23,
      activity_days: character.activity_days ?? [0, 1, 2, 3, 4, 5, 6],
      ...patch,
    };
    void perform(t("pg.busy.realism"), async () => {
      const updated = await api.setRealism(character.id, data);
      setCharacters(prev => prev.map(item => (item.id === updated.id ? updated : item)));
    });
  };

  const unlockImage = (imageId: string) => {
    void perform(t("chat.unlocking"), async () => {
      await api.unlockChatImage(imageId);
      if (conversation) await refresh(conversation.id);
    });
  };

  const openFan = (value: Fan | "new") => {
    setFanEditor(value); setFanName(value === "new" ? "" : value.name); setFanNotes(value === "new" ? "" : value.notes);
  };

  return <div className="playground theme-chat">
    <header className="topbar"><div className="brand"><span className="brand-mark">ai</span><h1>AI influencer playground <b>v5</b></h1></div>
      <div className="top-actions"><span className="sandbox-label">{t("pg.sandbox")}</span>        <nav className="top-nav"><Link to="/">{t("pg.nav.home")}</Link><Link className="selected" to="/chat">{t("pg.nav.chat")}</Link><Link to="/images">{t("pg.nav.images")}</Link><Link to="/dataset">{t("pg.nav.dataset")}</Link><Link to="/loras">{t("pg.nav.loras")}</Link></nav><LanguageSwitch /><button onClick={onLogout} disabled={!!busy}>{t("pg.logout")}</button></div></header>
    {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label={t("pg.error.closeAria")}>×</button></div>}
    <div className="workspace">
      <aside className="character-rail">
        <div className="section-title"><h2>{t("pg.characters")} <span>{characters.length}</span></h2></div>
        <div className="character-list">{characters.map((c, index) => <button key={c.id} disabled={!!busy} onClick={() => setCharacterId(c.id)} className={`character-row ${characterId === c.id ? "selected" : ""}`}>
          <CharacterAvatar character={c} index={index} onView={(url, alt) => setViewer({ url, alt })} altTemplate={t("pg.avatarAlt")} /><span><strong>{c.name}</strong><small>{c.profile.personality_traits || t("pg.noTraits")}</small></span></button>)}
          {!characters.length && <p className="muted">{t("pg.noCharacters")}</p>}</div>
        {character && <div className="character-actions"><button onClick={() => setEditing(character)} disabled={!!busy}>{t("pg.editPersonality")}</button></div>}
        {character && <label className="image-checkpoint">{t("pg.imageStyle")}<select value={character.image_style || "real"} disabled={!!busy} onChange={e => void perform(t("pg.busy.style"), async () => {
          const updated = await api.setImageStyle(character.id, e.target.value as "anime" | "real");
          setCharacters(prev => prev.map(item => (item.id === updated.id ? updated : item)));
        })}><option value="real">{t("pg.style.real")}</option><option value="anime">{t("pg.style.anime")}</option></select></label>}
        {character && checkpoints.some(c => c.usable) && <label className="image-checkpoint">{t("pg.checkpoint")}<select value={character.image_checkpoint || ""} disabled={!!busy} onChange={e => void perform(t("pg.busy.checkpoint"), async () => {
          const updated = await api.setImageCheckpoint(character.id, e.target.value || null);
          setCharacters(prev => prev.map(item => (item.id === updated.id ? updated : item)));
        })}><option value="">{t("pg.checkpointDefault")}</option>{checkpoints.filter(c => c.usable).map(checkpoint => <option key={checkpoint.name} value={checkpoint.name}>{checkpoint.name} · {checkpoint.family}</option>)}</select></label>}
        {character && <div className="ppv-settings">
          <label className="auto-label" title={t("pg.ppvHint")}>{t("pg.ppv")} <input type="checkbox" checked={!!character.ppv_enabled} disabled={!!busy} onChange={e => savePpv(e.target.checked, character.ppv_price_cents ?? 500)} /></label>
          <label className="ppv-price">€<input key={character.id} type="number" min="0" max="1000" step="0.5" defaultValue={((character.ppv_price_cents ?? 500) / 100).toFixed(2)} disabled={!!busy || !character.ppv_enabled} onBlur={e => savePpv(true, Math.round(Number(e.target.value) * 100))} /></label>
        </div>}
        {character && <details className="realism-settings">
          <summary title={t("pg.realismHint")}>{t("pg.realism")}</summary>
          <div className="ppv-settings">
            <div className="realism-delays">
              <label className="ppv-price" title={t("pg.realismHint")}>{t("pg.delay")} <input key={`min-${character.id}`} type="number" min="0" max="3600" defaultValue={character.reply_delay_min_seconds ?? 8} disabled={!!busy} onBlur={e => saveRealism({ reply_delay_min_seconds: Math.max(0, Math.min(3600, Number(e.target.value))) })} /></label>
              <label className="ppv-price">– <input key={`max-${character.id}`} type="number" min="0" max="3600" defaultValue={character.reply_delay_max_seconds ?? 40} disabled={!!busy} onBlur={e => saveRealism({ reply_delay_max_seconds: Math.max(0, Math.min(3600, Number(e.target.value))) })} /></label>
            </div>
            <label className="auto-label">{t("pg.activity")} <input type="checkbox" checked={!!character.activity_enabled} disabled={!!busy} onChange={e => saveRealism({ activity_enabled: e.target.checked })} /></label>
            {!!character.activity_enabled && <>
              <div className="realism-hours">
                <label className="ppv-price">{t("pg.from")} <select value={character.activity_start_hour ?? 9} disabled={!!busy} onChange={e => saveRealism({ activity_start_hour: Number(e.target.value) })}>{Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{hour}</option>)}</select></label>
                <label className="ppv-price">{t("pg.to")} <select value={character.activity_end_hour ?? 23} disabled={!!busy} onChange={e => saveRealism({ activity_end_hour: Number(e.target.value) })}>{Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{hour}</option>)}</select></label>
              </div>
              <div className="day-chips" role="group" aria-label={t("pg.days")}>
                {[0, 1, 2, 3, 4, 5, 6].map(day => {
                  const selectedDays = character.activity_days ?? [0, 1, 2, 3, 4, 5, 6];
                  const label = new Date(Date.UTC(2024, 0, 1 + day)).toLocaleDateString(lang === "it" ? "it-IT" : "en-GB", { weekday: "short" });
                  return <button type="button" key={day} className={selectedDays.includes(day) ? "on" : ""} disabled={!!busy} onClick={() => saveRealism({ activity_days: selectedDays.includes(day) ? selectedDays.filter(value => value !== day) : [...selectedDays, day] })}>{label}</button>;
                })}
              </div>
            </>}
          </div>
        </details>}
        <div className="rail-divider" />
        <div className="section-title"><h2>{t("pg.playFan")}</h2><button aria-label={t("pg.createFan")} onClick={() => openFan("new")} disabled={!!busy}>+</button></div>
        <label className="sr-only" htmlFor="fan-select">{t("pg.fanAccount")}</label><select id="fan-select" value={fanId} onChange={e => setFanId(e.target.value)} disabled={!!busy}>
          <option value="" disabled>{t("pg.chooseFan")}</option>{fans.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}</select>
        {fan && <div className="fan-note"><div><span>{t("pg.fanNotes")}</span><button onClick={() => openFan(fan)} disabled={!!busy}>{t("common.edit")}</button></div><p>{fan.notes || t("pg.noNotes")}</p><small>{t("pg.notesHint")}</small></div>}
        <div className="section-title history-title"><h2>{t("pg.conversations")}</h2><span>{conversations.length}</span></div>
        <div className="history-list">{conversations.slice(0, historyPage * 10).map(c => <div className="history-row" key={c.id}>
          <button className={conversation?.id === c.id ? "selected" : ""} disabled={!!busy}
          onClick={() => void perform(t("pg.busy.loadChat"), async () => { generation.current += 1; setMessages([]); setAutoNudge(false); setConversation(c); setModel(c.model); await refresh(c.id); })}>
          <strong>{c.model}{!!c.unread && <span className="unread-badge" aria-label={t("chat.unreadAria", { count: c.unread })}>{c.unread}</span>}</strong><small>{new Date(c.created_at).toLocaleString(lang === "it" ? "it-IT" : "en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · v{c.character_snapshot.version}</small></button>
          <button className="delete-chat" title={t("pg.deleteChat")} aria-label={t("pg.deleteChat")} disabled={!!busy} onClick={() => removeConversation(c)}>×</button>
        </div>)}
          {conversations.length > historyPage * 10 && <button onClick={() => setHistoryPage(p => p + 1)}>{t("pg.showMore")}</button>}
          {!conversations.length && <p className="muted">{t("pg.noChats")}</p>}</div>
      </aside>
      <main className="main-panel">
        <div className="chat-heading"><div><span className="eyebrow">{character ? t("pg.personalityVersion", { version: character.version }) : t("pg.lab")}</span><h2>{character?.name || t("pg.chooseCharacter")}</h2><p>{fan ? t("pg.withFan", { name: fan.name }) : t("pg.createFanHint")}</p></div>
          <div className="view-tabs" role="tablist"><button role="tab" aria-selected={tab === "chat"} onClick={() => setTab("chat")} disabled={!!busy}>{t("pg.tab.chat")}</button><button role="tab" aria-selected={tab === "benchmark"} onClick={() => setTab("benchmark")} disabled={!!busy}>{t("pg.tab.benchmark")}</button></div></div>
        {tab === "chat" ? <>
          <div className="model-toolbar"><label htmlFor="model-select">{t("pg.model")}</label><select id="model-select" value={model} disabled={!!busy} onChange={e => setModel(e.target.value)}>
            <option value="" disabled>{t("pg.chooseModel")}</option>{chatModels.map(m => <option key={m.name} value={m.name}>{m.name} · {m.parameter_size}</option>)}</select>
            <button className="primary" onClick={startChat} disabled={!character || !fan || !model || !!busy}>{t("pg.newChat")}</button>
            {conversation && model !== conversation.model && <button disabled={!!busy} onClick={() => void perform(t("pg.busy.changeModel"), async () => {
              const updated = await api.request<Conversation>(`/api/conversations/${conversation.id}`, { method: "PATCH", body: JSON.stringify({ model }) }); setConversation(updated);
            })}>{t("pg.useInChat")}</button>}</div>
          {conversation && conversation.character_snapshot.version !== character?.version && <div className="info-banner">{t("pg.snapshotWarning", { version: conversation.character_snapshot.version })}</div>}
          <ChatPanel conversation={conversation} messages={messages} onSendMessage={send} onUnlockImage={unlockImage} loading={!!busy} waiting={waiting} waitingElapsed={waitElapsed} busyLabel={busy} elapsed={elapsed} fanName={fan?.name || t("pg.fanFallback")} />
          {conversation && <div className="initiative-bar">
            <div className="quick-actions">
              <button disabled={!!busy} onClick={() => void initiate("opener")} title={t("pg.quick.openTitle")}>{t("pg.quick.open")}</button>
              <button disabled={!!busy} onClick={() => void initiate("reengage")} title={t("pg.quick.checkinTitle")}>{t("pg.quick.checkin")}</button>
              <button disabled={!!busy} title={t("pg.manualPhotoTitle")} onClick={() => { setPhotoScene(""); setPhotoCaption(""); setPhotoLocked(false); setPhotoPrice((((character?.ppv_price_cents ?? 500) / 100)).toFixed(2)); setPhotoOpen(true); }}>{t("pg.manualPhoto")}</button>
              <label className="toggle-pill" title={t("pg.autoPhotoTitle")}><input type="checkbox" checked={conversation.images_enabled !== false} disabled={!!busy} onChange={e => void perform(t("pg.busy.images"), async () => {
                const updated = await api.updateConversation(conversation.id, { images_enabled: e.target.checked });
                setConversation(updated);
              })} /> {t("pg.autoPhoto")}</label>
              <label className="toggle-pill" title={t("pg.humanHint")}><input type="checkbox" checked={conversation.human_mode === true} disabled={!!busy} onChange={e => void perform(t("pg.busy.human"), async () => {
                const updated = await api.updateConversation(conversation.id, { human_mode: e.target.checked });
                setConversation(updated);
              })} /> {t("pg.human")}</label>
            </div>
            <details className="tool-menu"><summary>{t("pg.options")}</summary><div className="tool-menu-body">
              <label>{t("pg.absence")} <input aria-label={t("pg.absenceAria")} type="number" min="1" max="8760" value={absence} onChange={e => setAbsence(Math.max(1, Math.min(8760, Number(e.target.value))))} /> h</label>
              <label className="auto-label">{t("pg.nudge")} <input type="checkbox" checked={autoNudge} onChange={e => { setAutoNudge(e.target.checked); setLastActivity(Date.now()); }} disabled={!!busy} /></label>
              <button className="danger" type="button" disabled={!!busy} onClick={() => {
                if (!window.confirm(t("pg.deleteChatConfirm"))) return;
                void perform(t("pg.busy.deleteChat"), async () => { await api.request(`/api/conversations/${conversation.id}`, { method: "DELETE" }); setConversations(prev => prev.filter(c => c.id !== conversation.id)); setConversation(null); setMessages([]); });
              }}>{t("pg.deleteChat")}</button>
            </div></details>
          </div>}
        </> : <BenchmarkPanel character={character} fanId={fanId} models={chatModels} onBusy={setBusy} />}
      </main>
      <aside className="inspector">
        <div className="section-title"><h2>{t("pg.memory.title")}</h2><span>{memories.length}</span></div>
        <p className="scope-label">{character?.name || t("pg.characterFallback")} × {fan?.name || "Fan"}</p>
        {conversation?.memory_status === "pending" && <p className="memory-status" role="status"><span className="spinner" /> {t("pg.memory.extracting")}</p>}
        {conversation?.memory_status === "failed" && <p className="memory-status warning">{t("pg.memory.failed")}</p>}
        <div className="memory-list">{memories.map(m => <article key={m.id}><div><span>{m.embedding_model === "manual" ? t("pg.memory.manual") : t("pg.memory.fromChat")} · {m.importance}/5</span><button aria-label={`${t("pg.busy.deleteMemory")}: ${m.content}`} disabled={!!busy} onClick={() => void perform(t("pg.busy.deleteMemory"), async () => { await api.deleteMemory(m.id); setMemories(prev => prev.filter(x => x.id !== m.id)); })}>×</button></div><p>{m.content}</p></article>)}
          {!memories.length && <div className="empty-memory"><span>◎</span><p>{t("pg.memory.empty")}</p><small>{t("pg.memory.emptyHint")}</small></div>}</div>
        {character && fan && <><form className="memory-form" onSubmit={e => { e.preventDefault(); void perform(t("pg.busy.saveMemory"), async () => {
          const saved = await api.request<Memory>(`/api/characters/${characterId}/memories?${scope}`, { method: "POST", body: JSON.stringify({ content: newMemory, category: "personal_fact", importance: 3 }) });
          setMemories(prev => [...prev.filter(m => m.id !== saved.id), saved]); setNewMemory("");
        }); }}><label htmlFor="memory-input">{t("pg.memory.add")}</label><textarea id="memory-input" rows={2} value={newMemory} onChange={e => setNewMemory(e.target.value)} placeholder={t("pg.memory.placeholder")} maxLength={5000} /><button disabled={!!busy || !newMemory.trim()}>{t("pg.memory.save")}</button></form>
          {!!memories.length && <button className="text-button danger" disabled={!!busy} onClick={() => {
            if (!window.confirm(t("pg.memory.clearConfirm", { fan: fan.name, character: character.name }))) return;
            void perform(t("pg.busy.clearMemory"), async () => { await api.request(`/api/characters/${characterId}/memories?${scope}`, { method: "DELETE" }); setMemories([]); });
          }}>{t("pg.memory.clear")}</button>}</>}
        <div className="rail-divider" /><div className="section-title"><h2>{t("pg.times.title")}</h2></div>
        <p className="muted">{t("pg.times.note")}</p>
        <div className="metric-list">{metrics.map(m => <article key={m.model}><strong>{m.model}</strong><div><b>{m.mean_seconds.toFixed(2)} s</b><span>{t("pg.times.mean", { count: m.samples })}</span></div><small>{t("pg.times.detail", { median: m.median_seconds.toFixed(2), load: m.mean_load_seconds.toFixed(2) })}</small></article>)}
          {!metrics.length && <p className="muted">{t("pg.times.empty")}</p>}</div>
      </aside>
    </div>
    {editing && <div className="modal-backdrop"><div className="modal" role="dialog" aria-modal="true" aria-label={t("form.aria")}><CharacterForm character={editing === "new" ? undefined : editing} models={chatModels} onSave={saveCharacter} onCancel={() => setEditing(null)} /></div></div>}
    {photoOpen && conversation && <div className="modal-backdrop"><form className="modal fan-editor photo-editor" role="dialog" aria-modal="true" aria-label={t("pg.photo.title")} onSubmit={e => { e.preventDefault(); const scene = photoScene.trim() || undefined; const caption = photoCaption.trim() || undefined; setPhotoOpen(false); void perform(t("pg.busy.photo"), async () => {
      await api.sendPhoto(conversation.id, { scene, caption, locked: photoLocked, price_cents: photoLocked ? Math.round(Number(photoPrice || "0") * 100) : undefined });
      await refresh(conversation.id);
    }); }}><h2>{t("pg.photo.title")}</h2><p className="muted">{t("pg.photo.note", { reference: character?.avatar_filename ? t("pg.photo.reference") : "" })}</p><label>{t("pg.photo.scene")}<textarea autoFocus rows={3} value={photoScene} onChange={e => setPhotoScene(e.target.value)} maxLength={1500} placeholder={t("pg.photo.scenePlaceholder")} /></label><label>{t("pg.photo.caption")}<input value={photoCaption} onChange={e => setPhotoCaption(e.target.value)} maxLength={1000} placeholder={t("pg.photo.captionPlaceholder")} /></label><div className="photo-ppv"><label className="auto-label">{t("pg.photo.locked")} <input type="checkbox" checked={photoLocked} disabled={!!busy} onChange={e => setPhotoLocked(e.target.checked)} /></label><label className="ppv-price">€<input type="number" min="0" max="1000" step="0.5" value={photoPrice} disabled={!!busy || !photoLocked} onChange={e => setPhotoPrice(e.target.value)} /></label></div><div className="modal-actions">{busy && <button type="button" className="danger" onClick={() => void api.interruptGeneration()}>{t("pg.photo.cancelGenerate")}</button>}<button type="button" onClick={() => setPhotoOpen(false)} disabled={!!busy}>{t("common.cancel")}</button><button className="primary" disabled={!!busy}>{t("pg.photo.generate")}</button></div></form></div>}
    {fanEditor && <div className="modal-backdrop"><form className="modal fan-editor" role="dialog" aria-modal="true" aria-label={t("pg.fanAccount")} onSubmit={e => { e.preventDefault(); void perform(t("pg.busy.saveFan"), async () => {
      const saved = await api.request<Fan>(fanEditor === "new" ? "/api/fans" : `/api/fans/${fanEditor.id}`, { method: fanEditor === "new" ? "POST" : "PUT", body: JSON.stringify({ name: fanName, notes: fanNotes }) });
      setFans(prev => [...prev.filter(f => f.id !== saved.id), saved]); setFanId(saved.id); setFanEditor(null);
    }); }}><h2>{fanEditor === "new" ? t("pg.fan.new") : t("pg.fan.edit")}</h2><label>{t("pg.fan.name")}<input autoFocus value={fanName} onChange={e => setFanName(e.target.value)} required maxLength={120} /></label><label>{t("pg.fan.notes")}<textarea rows={5} value={fanNotes} onChange={e => setFanNotes(e.target.value)} maxLength={3000} /></label><p className="muted">{t("pg.fan.hint")}</p><div className="modal-actions"><button type="button" onClick={() => setFanEditor(null)} disabled={!!busy}>{t("common.cancel")}</button><button className="primary" disabled={!!busy}>{busy || t("pg.fan.save")}</button></div>{fanEditor !== "new" && <button className="danger text-button" type="button" disabled={!!busy} onClick={() => {
      if (!window.confirm(t("pg.fan.deleteConfirm"))) return;
      void perform(t("pg.busy.deleteFan"), async () => { await api.request(`/api/fans/${fanEditor.id}`, { method: "DELETE" }); setFans(prev => prev.filter(f => f.id !== fanEditor.id)); setFanId(""); setFanEditor(null); });
    }}>{t("pg.fan.delete")}</button>}</form></div>}
    {viewer && <Lightbox src={viewer.url} alt={viewer.alt} onClose={() => setViewer(null)} />}
  </div>;
}
