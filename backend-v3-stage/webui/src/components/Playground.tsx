import { useCallback, useEffect, useRef, useState } from "react";
import { api, Character, Conversation, Memory, Message, OllamaModel, CharacterProfile } from "../api";
import CharacterForm from "./CharacterForm";
import ChatPanel from "./ChatPanel";
import BenchmarkPanel from "./BenchmarkPanel";

type Fan = { id: string; name: string; notes: string };
type ModelMetric = { model: string; samples: number; mean_seconds: number; median_seconds: number; mean_load_seconds: number };
const failure = (error: unknown) => error instanceof Error ? error.message : "Operazione non riuscita";

export default function Playground({ onLogout }: { onLogout: () => void }) {
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
  const [absence, setAbsence] = useState(48);
  const [autoNudge, setAutoNudge] = useState(false);
  const [lastActivity, setLastActivity] = useState(Date.now());
  const [newMemory, setNewMemory] = useState("");
  const [historyPage, setHistoryPage] = useState(1);
  const generation = useRef(0);
  const character = characters.find(c => c.id === characterId);
  const fan = fans.find(f => f.id === fanId);
  const chatModels = models.filter(m => m.chat_capable !== false && !m.name.includes("embed"));
  const scope = `fan_id=${encodeURIComponent(fanId)}`;

  useEffect(() => {
    let live = true;
    Promise.all([api.getCharacters(), api.request<Fan[]>("/api/fans"), api.getModels()])
      .then(([chars, people, data]) => {
        if (!live) return;
        setCharacters(chars); setFans(people); setModels(data.models);
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
  }, [characterId, scope]);

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

  const perform = async (label: string, work: () => Promise<void>) => {
    if (busy) return;
    setBusy(label); setError("");
    try { await work(); } catch (e) { setError(failure(e)); } finally { setBusy(""); }
  };

  const startChat = () => perform("Prepara il primo messaggio", async () => {
    const chat = await api.request<Conversation>(`/api/characters/${characterId}/conversations`, {
      method: "POST", body: JSON.stringify({ model, fan_id: fanId, auto_greet: true }) });
    setConversation(chat); setHistoryPage(1); setLastActivity(Date.now());
    await refresh(chat.id);
    if (chat.greeting_error) setError(`Chat creata, ma il saluto non è riuscito: ${chat.greeting_error}. Puoi riprovare con “Scrivi per primo”.`);
  });

  const send = async (content: string) => {
    if (!conversation || busy) return false;
    const id = conversation.id;
    setMessages(prev => [...prev, { id: "pending", conversation_id: id, role: "user", content,
      model: null, ollama_metrics: null, created_at: new Date().toISOString() }]);
    setBusy("Sta scrivendo"); setError(""); setLastActivity(Date.now());
    try {
      await api.sendMessage(id, content);
      await refresh(id); return true;
    } catch (e) {
      setMessages(prev => prev.filter(m => m.id !== "pending")); setError(failure(e)); return false;
    } finally { setBusy(""); }
  };

  const initiate = useCallback(async (kind: "opener" | "reengage") => {
    if (!conversation || busy) return;
    setBusy(kind === "opener" ? "Prepara il primo messaggio" : "Prepara un messaggio di ritorno"); setError("");
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

  const removeCharacter = () => {
    if (!character || !window.confirm(`Eliminare ${character.name}? Verranno eliminate chat, ricordi, prove e contenuti associati.`)) return;
    void perform("Elimina il personaggio", async () => {
      await api.deleteCharacter(character.id); setCharacters(prev => prev.filter(c => c.id !== character.id)); setCharacterId("");
    });
  };

  const openFan = (value: Fan | "new") => {
    setFanEditor(value); setFanName(value === "new" ? "" : value.name); setFanNotes(value === "new" ? "" : value.notes);
  };

  return <div className="playground">
    <header className="topbar"><div className="brand"><span className="brand-mark">ai</span><h1>AI influencer playground <b>v3</b></h1></div>
      <div className="top-actions"><span className="sandbox-label">Laboratorio · account fittizi</span><button onClick={onLogout} disabled={!!busy}>Esci</button></div></header>
    {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label="Chiudi errore">×</button></div>}
    <div className="workspace">
      <aside className="character-rail">
        <div className="section-title"><h2>Personaggi <span>{characters.length}</span></h2><button aria-label="Crea personaggio" onClick={() => setEditing("new")} disabled={!!busy}>+</button></div>
        <div className="character-list">{characters.map((c, index) => <button key={c.id} disabled={!!busy} onClick={() => setCharacterId(c.id)} className={`character-row ${characterId === c.id ? "selected" : ""}`}>
          <span className={`avatar color-${index % 4}`}>{c.name.slice(0, 2).toUpperCase()}</span><span><strong>{c.name}</strong><small>{c.profile.personality_traits || "Personalità da esplorare"}</small></span></button>)}
          {!characters.length && <p className="muted">Crea il primo personaggio per iniziare.</p>}</div>
        {character && <div className="character-actions"><button onClick={() => setEditing(character)} disabled={!!busy}>Modifica personalità</button><button className="danger" onClick={removeCharacter} disabled={!!busy}>Elimina</button></div>}
        <div className="rail-divider" />
        <div className="section-title"><h2>Interpreta un fan</h2><button aria-label="Crea account fittizio" onClick={() => openFan("new")} disabled={!!busy}>+</button></div>
        <label className="sr-only" htmlFor="fan-select">Account fittizio</label><select id="fan-select" value={fanId} onChange={e => setFanId(e.target.value)} disabled={!!busy}>
          <option value="" disabled>Scegli un account</option>{fans.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}</select>
        {fan && <div className="fan-note"><div><span>Note per il test</span><button onClick={() => openFan(fan)} disabled={!!busy}>Modifica</button></div><p>{fan.notes || "Nessuna nota."}</p><small>Queste note non vengono inviate al modello.</small></div>}
        <div className="section-title history-title"><h2>Conversazioni</h2><span>{conversations.length}</span></div>
        <div className="history-list">{conversations.slice(0, historyPage * 10).map(c => <button className={conversation?.id === c.id ? "selected" : ""} key={c.id} disabled={!!busy}
          onClick={() => void perform("Carica la chat", async () => { generation.current += 1; setMessages([]); setAutoNudge(false); setConversation(c); setModel(c.model); await refresh(c.id); })}>
          <strong>{c.model}</strong><small>{new Date(c.created_at).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · v{c.character_snapshot.version}</small></button>)}
          {conversations.length > historyPage * 10 && <button onClick={() => setHistoryPage(p => p + 1)}>Mostra altre</button>}
          {!conversations.length && <p className="muted">Le chat di questo fan appariranno qui.</p>}</div>
      </aside>
      <main className="main-panel">
        <div className="chat-heading"><div><span className="eyebrow">{character ? `PERSONALITÀ v${character.version}` : "IL TUO LABORATORIO"}</span><h2>{character?.name || "Scegli un personaggio"}</h2><p>{fan ? `In conversazione con ${fan.name}` : "Crea un account fittizio per provare la memoria"}</p></div>
          <div className="view-tabs" role="tablist"><button role="tab" aria-selected={tab === "chat"} onClick={() => setTab("chat")} disabled={!!busy}>Chat</button><button role="tab" aria-selected={tab === "benchmark"} onClick={() => setTab("benchmark")} disabled={!!busy}>Confronta modelli</button></div></div>
        {tab === "chat" ? <>
          <div className="model-toolbar"><label htmlFor="model-select">Modello</label><select id="model-select" value={model} disabled={!!busy} onChange={e => setModel(e.target.value)}>
            <option value="" disabled>Scegli un modello</option>{chatModels.map(m => <option key={m.name} value={m.name}>{m.name} · {m.parameter_size}</option>)}</select>
            <button className="primary" onClick={startChat} disabled={!character || !fan || !model || !!busy}>+ Nuova chat</button>
            {conversation && model !== conversation.model && <button disabled={!!busy} onClick={() => void perform("Cambia modello", async () => {
              const updated = await api.request<Conversation>(`/api/conversations/${conversation.id}`, { method: "PATCH", body: JSON.stringify({ model }) }); setConversation(updated);
            })}>Usa nella chat</button>}</div>
          {conversation && conversation.character_snapshot.version !== character?.version && <div className="info-banner">Questa chat usa la personalità v{conversation.character_snapshot.version}. Avvia una nuova chat per provare le modifiche.</div>}
          <ChatPanel conversation={conversation} messages={messages} onSendMessage={send} loading={!!busy} busyLabel={busy} elapsed={elapsed} fanName={fan?.name || "Tu"} />
          {conversation && <div className="initiative-bar"><button disabled={!!busy} onClick={() => void initiate("opener")}>Scrivi per primo</button><button disabled={!!busy} onClick={() => void initiate("reengage")}>Simula ritorno</button>
            <label>Assenza <input aria-label="Ore di assenza simulate" type="number" min="1" max="8760" value={absence} onChange={e => setAbsence(Math.max(1, Math.min(8760, Number(e.target.value))))} /> h</label>
            <label className="auto-label"><input type="checkbox" checked={autoNudge} onChange={e => { setAutoNudge(e.target.checked); setLastActivity(Date.now()); }} disabled={!!busy} /> Un messaggio dopo 60 s di silenzio</label>
            <button className="danger" aria-label="Elimina conversazione" disabled={!!busy} onClick={() => {
              if (!window.confirm("Eliminare questa chat? I ricordi del fan restano disponibili.")) return;
              void perform("Elimina chat", async () => { await api.request(`/api/conversations/${conversation.id}`, { method: "DELETE" }); setConversations(prev => prev.filter(c => c.id !== conversation.id)); setConversation(null); setMessages([]); });
            }}>Elimina chat</button></div>}
        </> : <BenchmarkPanel character={character} fanId={fanId} models={chatModels} onBusy={setBusy} />}
      </main>
      <aside className="inspector">
        <div className="section-title"><h2>Memoria del fan</h2><span>{memories.length}</span></div>
        <p className="scope-label">{character?.name || "Personaggio"} × {fan?.name || "Fan"}</p>
        {conversation?.memory_status === "pending" && <p className="memory-status" role="status"><span className="spinner" /> Sta estraendo i ricordi…</p>}
        {conversation?.memory_status === "failed" && <p className="memory-status warning">Estrazione non riuscita. Puoi aggiungere un ricordo manualmente.</p>}
        <div className="memory-list">{memories.map(m => <article key={m.id}><div><span>{m.embedding_model === "manual" ? "Manuale" : "Dalla chat"} · {m.importance}/5</span><button aria-label={`Elimina ricordo: ${m.content}`} disabled={!!busy} onClick={() => void perform("Elimina ricordo", async () => { await api.deleteMemory(m.id); setMemories(prev => prev.filter(x => x.id !== m.id)); })}>×</button></div><p>{m.content}</p></article>)}
          {!memories.length && <div className="empty-memory"><span>◎</span><p>Nessun ricordo, per ora.</p><small>Racconta un dettaglio, attendi l’estrazione e apri una nuova chat con lo stesso fan per verificarlo.</small></div>}</div>
        {character && fan && <><form className="memory-form" onSubmit={e => { e.preventDefault(); void perform("Salva ricordo", async () => {
          const saved = await api.request<Memory>(`/api/characters/${characterId}/memories?${scope}`, { method: "POST", body: JSON.stringify({ content: newMemory, category: "personal_fact", importance: 3 }) });
          setMemories(prev => [...prev.filter(m => m.id !== saved.id), saved]); setNewMemory("");
        }); }}><label htmlFor="memory-input">Aggiungi un fatto di prova</label><textarea id="memory-input" rows={2} value={newMemory} onChange={e => setNewMemory(e.target.value)} placeholder="Es. A Luca piace il jazz" maxLength={5000} /><button disabled={!!busy || !newMemory.trim()}>Salva ricordo</button></form>
          {!!memories.length && <button className="text-button danger" disabled={!!busy} onClick={() => {
            if (!window.confirm(`Cancellare i ricordi di ${fan.name} con ${character.name}?`)) return;
            void perform("Azzera memoria", async () => { await api.request(`/api/characters/${characterId}/memories?${scope}`, { method: "DELETE" }); setMemories([]); });
          }}>Azzera questa memoria</button>}</>}
        <div className="rail-divider" /><div className="section-title"><h2>Tempi in chat</h2></div>
        <p className="muted">Risposte, saluti e ritorni di questa coppia. Tempo totale, incluso il caricamento.</p>
        <div className="metric-list">{metrics.map(m => <article key={m.model}><strong>{m.model}</strong><div><b>{m.mean_seconds.toFixed(2)} s</b><span>media · {m.samples} risposte</span></div><small>Mediana {m.median_seconds.toFixed(2)} s · carico medio {m.mean_load_seconds.toFixed(2)} s</small></article>)}
          {!metrics.length && <p className="muted">Invia un messaggio per vedere le prime misure.</p>}</div>
      </aside>
    </div>
    {editing && <div className="modal-backdrop"><div className="modal" role="dialog" aria-modal="true" aria-label="Personalità del personaggio"><CharacterForm character={editing === "new" ? undefined : editing} models={chatModels} onSave={saveCharacter} onCancel={() => setEditing(null)} /></div></div>}
    {fanEditor && <div className="modal-backdrop"><form className="modal fan-editor" role="dialog" aria-modal="true" aria-label="Account fittizio" onSubmit={e => { e.preventDefault(); void perform("Salva account", async () => {
      const saved = await api.request<Fan>(fanEditor === "new" ? "/api/fans" : `/api/fans/${fanEditor.id}`, { method: fanEditor === "new" ? "POST" : "PUT", body: JSON.stringify({ name: fanName, notes: fanNotes }) });
      setFans(prev => [...prev.filter(f => f.id !== saved.id), saved]); setFanId(saved.id); setFanEditor(null);
    }); }}><h2>{fanEditor === "new" ? "Nuovo account fittizio" : "Modifica account"}</h2><label>Nome<input autoFocus value={fanName} onChange={e => setFanName(e.target.value)} required maxLength={120} /></label><label>Note per le prove<textarea rows={5} value={fanNotes} onChange={e => setFanNotes(e.target.value)} maxLength={3000} /></label><p className="muted">Solo per te: il chatbot impara i dettagli dai messaggi, non da queste note.</p><div className="modal-actions"><button type="button" onClick={() => setFanEditor(null)} disabled={!!busy}>Annulla</button><button className="primary" disabled={!!busy}>{busy || "Salva account"}</button></div>{fanEditor !== "new" && <button className="danger text-button" type="button" disabled={!!busy} onClick={() => {
      if (!window.confirm("Eliminare questo fan, tutte le sue chat e i suoi ricordi?")) return;
      void perform("Elimina account", async () => { await api.request(`/api/fans/${fanEditor.id}`, { method: "DELETE" }); setFans(prev => prev.filter(f => f.id !== fanEditor.id)); setFanId(""); setFanEditor(null); });
    }}>Elimina account e dati</button>}</form></div>}
  </div>;
}
