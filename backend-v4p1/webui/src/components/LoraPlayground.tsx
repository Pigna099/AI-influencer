import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Character, CharacterLora, CheckpointInfo, TrainingJob } from "../api";
import { useI18n, LanguageSwitch } from "../i18n";
import CharacterAvatar from "./CharacterAvatar";

const FAMILIES: Array<"real" | "pony" | "anime"> = ["real", "pony", "anime"];

type QueuePayload = Parameters<typeof api.queueTraining>[1];

function LoraCard({
  item,
  busy,
  queueOpen,
  onToggleQueue,
  onDelete,
  onActivate,
  onQueue,
  checkpoints,
}: {
  item: CharacterLora;
  busy: boolean;
  queueOpen: boolean;
  onToggleQueue: (item: CharacterLora) => void;
  onDelete: (item: CharacterLora) => void;
  onActivate: (item: CharacterLora) => void;
  onQueue: (item: CharacterLora, data: QueuePayload) => void;
  checkpoints: CheckpointInfo[];
}) {
  const { t } = useI18n();
  const [imagesDir, setImagesDir] = useState("");
  const [baseCheckpoint, setBaseCheckpoint] = useState(item.base_checkpoint || "");
  const [rank, setRank] = useState(item.rank);
  const [steps, setSteps] = useState("");
  const [learningRate, setLearningRate] = useState("0.0001");
  const [repeats, setRepeats] = useState("10");
  const [batch, setBatch] = useState("1");
  const [resolution, setResolution] = useState("1024");
  const [caption, setCaption] = useState("");
  const [saveEvery, setSaveEvery] = useState("500");
  const [gpu, setGpu] = useState("");

  const submit = () => onQueue(item, {
    images_dir: imagesDir.trim(),
    base_checkpoint: baseCheckpoint.trim() || undefined,
    rank,
    resolution: Number(resolution),
    steps: steps.trim() ? Number(steps) : undefined,
    learning_rate: Number(learningRate),
    repeats: Number(repeats),
    batch_size: Number(batch),
    caption_prefix: caption.trim(),
    save_every: Number(saveEvery),
    gpu: gpu.trim() ? Number(gpu) : undefined,
  });

  return <article className={`lora-card status-${item.status}`}>
    <div className="lora-head">
      <strong>{item.name}</strong>
      <span className={`lora-badge ${item.status}`}>{t(`lp.status.${item.status}`)}</span>
      {item.is_active && <span className="lora-badge active">{t("lp.active")}</span>}
    </div>
    <small>{item.family} · rank {item.rank}{item.base_checkpoint ? ` · ${item.base_checkpoint}` : ""}</small>
    <p><b>{t("lp.triggerLabel")}:</b> <code>{item.trigger}</code></p>
    {item.filename && <p><b>{t("lp.fileLabel")}:</b> <code>{item.filename}</code></p>}
    {!!Object.keys(item.metrics).length && <small>{t("lp.metrics")}: {Object.entries(item.metrics).map(([key, value]) => `${key}=${String(value)}`).join(" · ")}</small>}
    {item.error && <small className="lora-error">{item.error}</small>}
    <div className="lora-actions">
      {item.status === "ready" && !item.is_active && <button disabled={busy} onClick={() => onActivate(item)}>{t("lp.activate")}</button>}
      {(item.status === "draft" || item.status === "ready" || item.status === "failed") && <button disabled={busy} onClick={() => onToggleQueue(item)}>{t("lp.queue")}</button>}
      {item.status !== "queued" && item.status !== "training" && <button className="danger" disabled={busy} onClick={() => onDelete(item)}>{t("common.delete")}</button>}
    </div>
    {queueOpen && <div className="lora-queue">
      <label>{t("lp.imagesDir")}<input value={imagesDir} disabled={busy} onChange={e => setImagesDir(e.target.value)} placeholder={t("lp.queuePlaceholder")} maxLength={300} /></label>
      <p className="muted">{t("lp.imagesDirHint")} · {t("lp.queueHint")}</p>
      <div className="grid">
        <label>{t("lp.baseCheckpoint")}<select value={baseCheckpoint} disabled={busy} onChange={e => setBaseCheckpoint(e.target.value)}>
          <option value="">{t("lp.baseCheckpointAuto")}</option>
          {checkpoints.map(checkpoint => <option key={checkpoint.name} value={checkpoint.name}>{checkpoint.name} · {checkpoint.family}</option>)}
        </select></label>
        <label>{t("lp.rank")}<input type="number" min={4} max={128} value={rank} disabled={busy} onChange={e => setRank(Number(e.target.value))} /></label>
        <label>{t("lp.steps")}<input type="number" min={100} value={steps} disabled={busy} onChange={e => setSteps(e.target.value)} placeholder={t("lp.stepsAuto")} /></label>
        <label>{t("lp.gpu")}<input type="number" min={0} value={gpu} disabled={busy} onChange={e => setGpu(e.target.value)} placeholder={t("lp.gpuAuto")} /></label>
      </div>
      <details>
        <summary>{t("lp.advanced")}</summary>
        <div className="grid">
          <label>{t("lp.learningRate")}<input type="number" step="0.00001" min={0.000001} value={learningRate} disabled={busy} onChange={e => setLearningRate(e.target.value)} /></label>
          <label>{t("lp.repeats")}<input type="number" min={1} max={100} value={repeats} disabled={busy} onChange={e => setRepeats(e.target.value)} /></label>
          <label>{t("lp.batch")}<input type="number" min={1} max={8} value={batch} disabled={busy} onChange={e => setBatch(e.target.value)} /></label>
          <label>{t("lp.resolution")}<select value={resolution} disabled={busy} onChange={e => setResolution(e.target.value)}>{[768, 1024, 1280].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
          <label>{t("lp.captionPrefix")}<input value={caption} disabled={busy} onChange={e => setCaption(e.target.value)} maxLength={500} /></label>
          <label>{t("lp.saveEvery")}<input type="number" min={50} max={5000} value={saveEvery} disabled={busy} onChange={e => setSaveEvery(e.target.value)} /></label>
        </div>
        <p className="muted">{t("lp.autoNote")}</p>
      </details>
      <button className="primary" disabled={busy || !imagesDir.trim()} onClick={submit}>{t("lp.queueButton")}</button>
    </div>}
  </article>;
}

export default function LoraPlayground({ onLogout }: { onLogout: () => void }) {
  const { t } = useI18n();
  const [characters, setCharacters] = useState<Character[]>([]);
  const [characterId, setCharacterId] = useState("");
  const [loras, setLoras] = useState<CharacterLora[]>([]);
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [checkpoints, setCheckpoints] = useState<CheckpointInfo[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [family, setFamily] = useState<"real" | "pony" | "anime">("real");
  const [trigger, setTrigger] = useState("");
  const [rank, setRank] = useState(32);
  const [baseCheckpoint, setBaseCheckpoint] = useState("");
  const [queueFor, setQueueFor] = useState("");
  const character = characters.find(item => item.id === characterId);

  useEffect(() => {
    let live = true;
    Promise.all([api.getCharacters(), api.getCheckpoints()])
      .then(([chars, checkpointData]) => {
        if (!live) return;
        setCharacters(chars);
        setCheckpoints(checkpointData.checkpoints.filter(item => item.usable));
        if (chars[0]) setCharacterId(chars[0].id);
      })
      .catch(e => { if (live) setError(e instanceof Error ? e.message : t("common.failed")); });
    return () => { live = false; };
  }, []);

  const refresh = useCallback(async (id: string) => {
    if (!id) { setLoras([]); setJobs([]); return; }
    const [loraItems, jobItems] = await Promise.all([
      api.getCharacterLoras(id),
      api.getTrainingJobs({ character_id: id }),
    ]);
    setLoras(loraItems);
    setJobs(jobItems);
  }, []);

  useEffect(() => { void refresh(characterId).catch(() => undefined); }, [characterId, refresh]);

  const running = jobs.some(job => job.status === "queued" || job.status === "running");
  useEffect(() => {
    if (!characterId || !running) return;
    const timer = window.setInterval(() => { void refresh(characterId).catch(() => undefined); }, 5000);
    return () => window.clearInterval(timer);
  }, [characterId, running, refresh]);

  const perform = async (label: string, work: () => Promise<void>) => {
    if (busy) return;
    setBusy(label); setError("");
    try { await work(); } catch (e) { setError(e instanceof Error ? e.message : t("common.failed")); }
    finally { setBusy(""); }
  };

  const create = () => {
    if (!character || !name.trim()) return;
    void perform(t("common.loading"), async () => {
      const item = await api.createLora(character.id, {
        name: name.trim(),
        family,
        trigger: trigger.trim() || undefined,
        base_checkpoint: baseCheckpoint.trim() || undefined,
        rank,
      });
      setLoras(prev => [item, ...prev]);
      setName(""); setTrigger("");
    });
  };

  const remove = (item: CharacterLora) => {
    if (!window.confirm(t("lp.deleteConfirm"))) return;
    void perform("", async () => {
      await api.deleteLora(item.id);
      setQueueFor("");
      await refresh(characterId);
    });
  };

  const activate = (item: CharacterLora) => void perform("", async () => {
    await api.activateLora(item.id);
    await refresh(characterId);
  });

  const queue = (item: CharacterLora, data: QueuePayload) => void perform(t("lp.queueHint"), async () => {
    await api.queueTraining(item.id, data);
    setQueueFor("");
    await refresh(characterId);
  });

  const cancel = (job: TrainingJob) => {
    if (!window.confirm(`${t("lp.cancelJob")}?`)) return;
    void perform("", async () => {
      await api.cancelTrainingJob(job.id);
      await refresh(characterId);
    });
  };

  const progressPercent = (job: TrainingJob) => {
    const step = job.progress?.step ?? 0;
    const total = job.progress?.total ?? 0;
    return total > 0 ? Math.min(100, Math.round((step / total) * 100)) : 0;
  };

  return <div className="playground theme-lora">
    <header className="topbar"><div className="brand"><span className="brand-mark">ai</span><h1>AI influencer playground <b>v4p1</b></h1></div>
      <div className="top-actions">
        <nav className="top-nav"><Link to="/">{t("pg.nav.chat")}</Link><Link to="/images">{t("pg.nav.images")}</Link><Link to="/dataset">{t("pg.nav.dataset")}</Link><Link className="selected" to="/loras">{t("pg.nav.loras")}</Link></nav>
        <LanguageSwitch /><button onClick={onLogout} disabled={!!busy}>{t("pg.logout")}</button>
      </div></header>
    {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label={t("pg.error.closeAria")}>×</button></div>}
    <div className="workspace image-workspace" style={{ gridTemplateColumns: "225px minmax(320px, 1fr)" }}>
      <aside className="character-rail">
        <div className="section-title"><h2>{t("ip.characters")}</h2><span>{characters.length}</span></div>
        <div className="character-list">{characters.map((item, index) => <button key={item.id} disabled={!!busy} onClick={() => setCharacterId(item.id)} className={`character-row ${characterId === item.id ? "selected" : ""}`}>
          <CharacterAvatar character={item} index={index} onView={() => undefined} altTemplate={t("pg.avatarAlt")} /><span><strong>{item.name}</strong><small>{item.image_style === "anime" ? t("pg.style.anime") : t("pg.style.real")}</small></span></button>)}
          {!characters.length && <p className="muted">{t("pg.noCharacters")}</p>}</div>
      </aside>
      <main className="main-panel">
        <div className="chat-heading"><div><span className="eyebrow">LoRA</span><h2>{character?.name || t("lp.title")}</h2><p>{t("lp.subtitle")}</p></div>
          <span className="library-count">{loras.length} LoRA</span></div>
        <div className="lora-content">
          <section className="lora-create">
            <label>{t("lp.name")}<input value={name} disabled={!!busy} onChange={e => setName(e.target.value)} maxLength={120} /></label>
            <label>{t("lp.family")}<select value={family} disabled={!!busy} onChange={e => setFamily(e.target.value as "real" | "pony" | "anime")}>{FAMILIES.map(item => <option key={item} value={item}>{item}</option>)}</select></label>
            <label>{t("lp.trigger")}<input value={trigger} disabled={!!busy} onChange={e => setTrigger(e.target.value)} placeholder={t("lp.triggerHint")} maxLength={64} /></label>
            <label>{t("lp.rank")}<input type="number" min={4} max={128} value={rank} disabled={!!busy} onChange={e => setRank(Number(e.target.value))} /></label>
            <label>{t("lp.baseCheckpoint")}<select value={baseCheckpoint} disabled={!!busy} onChange={e => setBaseCheckpoint(e.target.value)}>
              <option value="">{t("lp.baseCheckpointAuto")}</option>
              {checkpoints.map(checkpoint => <option key={checkpoint.name} value={checkpoint.name}>{checkpoint.name} · {checkpoint.family}</option>)}
            </select></label>
            <button className="primary" disabled={!!busy || !character || !name.trim()} onClick={create}>{t("lp.create")}</button>
          </section>
          <section>
            <div className="section-title"><h2>{t("lp.title")}</h2><span>{loras.length}</span></div>
            {!loras.length && <p className="muted">{t("lp.empty")}</p>}
            <div className="lora-grid">{loras.map(item => <LoraCard key={item.id} item={item} busy={!!busy} queueOpen={queueFor === item.id} onToggleQueue={lora => setQueueFor(current => current === lora.id ? "" : lora.id)} onDelete={remove} onActivate={activate} onQueue={queue} checkpoints={checkpoints} />)}</div>
          </section>
          <section>
            <div className="section-title"><h2>{t("lp.jobs")}</h2><button disabled={!!busy} onClick={() => void refresh(characterId)}>{t("lp.refresh")}</button></div>
            {!jobs.length && <p className="muted">{t("lp.noJobs")}</p>}
            <div className="job-list">{jobs.map(job => <div key={job.id} className={`job-row status-${job.status}`}>
              <header><strong>{job.lora?.name || job.lora_id || t("lp.jobs")}</strong><span className={`lora-badge ${job.status}`}>{t(`lp.jobStatus.${job.status}`)}</span><small>{new Date(job.created_at).toLocaleString()}</small></header>
              {job.status === "running" && <div className="job-bar"><i style={{ width: `${progressPercent(job)}%` }} /></div>}
              {job.status === "running" && <small>{job.progress?.total ? t("lp.progressStep", { step: job.progress.step ?? 0, total: job.progress.total }) : ""}{job.progress?.loss != null ? ` · ${t("lp.loss")} ${job.progress.loss.toFixed(4)}` : ""}</small>}
              {job.worker && <small>{t("lp.worker")}: {job.worker}</small>}
              {job.error && <small className="lora-error">{job.error}</small>}
              {job.log_path && <small>{t("lp.logPath")}: <code>{job.log_path}</code></small>}
              {(job.status === "queued" || job.status === "running") && <div className="lora-actions"><button disabled={!!busy} onClick={() => cancel(job)}>{t("lp.cancelJob")}</button></div>}
            </div>)}</div>
          </section>
        </div>
      </main>
    </div>
  </div>;
}
