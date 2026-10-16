import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Character, CharacterLora, CharacterProfile, CheckpointInfo, LoraDataset, TrainingJob } from "../api";
import {useI18n} from "../i18n";
import AppHeader from "./ui/AppHeader";
import CharacterAvatar from "./CharacterAvatar";
import CharacterForm from "./CharacterForm";

const NO_OLLAMA_MODELS: never[] = [];
import DatasetPanel from "./DatasetPanel";
import StatusBadge from "./ui/StatusBadge";
import JobProgress from "./ui/JobProgress";
import { formatDuration } from "../lib/format";
import InspectorDrawer from "./ui/InspectorDrawer";
import { useMediaQuery } from "../hooks/useMediaQuery";
import DangerZone from "./ui/DangerZone";
import IdentityPanel from "./ui/IdentityPanel";
import PageHeader from "./ui/PageHeader";
import Lightbox from "./Lightbox";

const FAMILIES: Array<"real" | "pony" | "anime" | "qwen-image"> = ["real", "pony", "anime", "qwen-image"];

type QueuePayload = Parameters<typeof api.queueTraining>[1];

function LoraCard({
  item,
  busy,
  queueOpen,
  onToggleQueue,
  onDelete,
  onActivate,
  onValidate,
  onRollback,
  onQueue,
  checkpoints,
  datasets,
}: {
  item: CharacterLora;
  busy: boolean;
  queueOpen: boolean;
  onToggleQueue: (item: CharacterLora) => void;
  onDelete: (item: CharacterLora) => void;
  onActivate: (item: CharacterLora) => void;
  onValidate: (item: CharacterLora) => void;
  onRollback: (item: CharacterLora) => void;
  onQueue: (item: CharacterLora, data: QueuePayload) => void;
  checkpoints: CheckpointInfo[];
  datasets: LoraDataset[];
}) {
  const { t } = useI18n();
  const [imagesDir, setImagesDir] = useState("");
  const [datasetId, setDatasetId] = useState("");
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
  const [preflight, setPreflight] = useState<Awaited<ReturnType<typeof api.getLoraPreflight>> | null>(null);

  useEffect(() => {
    if (!queueOpen) { setPreflight(null); return; }
    let live = true;
    api.getLoraPreflight(item.id, datasetId || undefined)
      .then(report => { if (live) setPreflight(report); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [queueOpen, item.id, datasetId]);

  const useRecommended = () => {
    void api.getLoraRecommendation(item.id, datasetId || undefined).then(recommendation => {
      setRank(recommendation.rank);
      setSteps(String(recommendation.steps));
      setLearningRate(String(recommendation.learning_rate));
      setRepeats(String(recommendation.repeats));
      setResolution(String(recommendation.resolution));
    }).catch(() => undefined);
  };

  const submit = () => onQueue(item, {
    images_dir: datasetId ? undefined : imagesDir.trim(),
    dataset_id: datasetId || undefined,
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
      {item.status === "ready" && <button disabled={busy} onClick={() => onValidate(item)}>{t("lp.validate")}</button>}
      {item.status === "ready" && !item.is_active && <button disabled={busy} onClick={() => onActivate(item)}>{t("lp.activate")}</button>}
      {item.is_active && item.previous_active_id && <button disabled={busy} onClick={() => onRollback(item)}>{t("lp.rollback")}</button>}
      {(item.status === "draft" || item.status === "ready" || item.status === "failed") && <button disabled={busy} onClick={() => onToggleQueue(item)}>{t("lp.queue")}</button>}
      {item.status !== "queued" && item.status !== "training" && <button className="danger" disabled={busy} onClick={() => onDelete(item)}>{t("common.delete")}</button>}
    </div>
    {queueOpen && <div className="lora-queue">
      <button type="button" disabled={busy} onClick={useRecommended}>{t("lp.useRecommended")}</button>
      {preflight && <ul className="preflight-list">{preflight.checks.map(check => <li key={check.code} className={check.ok ? "ok" : "fail"}>
        <span>{check.ok ? "✓" : "✕"}</span> {check.summary}{!check.ok && check.remediation ? ` — ${check.remediation}` : ""}
      </li>)}</ul>}
      <label>{t("lp.datasetOption")}<select value={datasetId} disabled={busy} onChange={e => setDatasetId(e.target.value)}>
        <option value="">{t("lp.noDatasetOption")}</option>
        {datasets.map(dataset => <option key={dataset.id} value={dataset.id}>{dataset.trigger} · {dataset.selected_count}/{dataset.item_count}</option>)}
      </select></label>
      <label>{t("lp.imagesDir")}<input value={imagesDir} disabled={busy || !!datasetId} onChange={e => setImagesDir(e.target.value)} placeholder={t("lp.queuePlaceholder")} maxLength={300} /></label>
      <p className="muted">{t("lp.imagesDirHint")} · {t("lp.queueHint")}</p>
      <div className="grid">
        <label>{t("lp.baseCheckpoint")}<select value={baseCheckpoint} disabled={busy} onChange={e => setBaseCheckpoint(e.target.value)}>
          <option value="">{t("lp.baseCheckpointAuto")}</option>
          {checkpoints.map(checkpoint => <option key={checkpoint.name} value={checkpoint.name}>{checkpoint.name} · {checkpoint.family}</option>)}
        </select></label>
        <label title={t("lp.rankHint")}>{t("lp.rank")}<input type="number" min={4} max={128} value={rank} disabled={busy} onChange={e => setRank(Number(e.target.value))} /></label>
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
      <button className="primary" disabled={busy || (!datasetId && !imagesDir.trim())} onClick={submit}>{t("lp.queueButton")}</button>
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
  const [notice, setNotice] = useState("");
  const [name, setName] = useState("");
  const [family, setFamily] = useState<"real" | "pony" | "anime" | "qwen-image">("real");
  const [trigger, setTrigger] = useState("");
  const [rank, setRank] = useState(32);
  const [baseCheckpoint, setBaseCheckpoint] = useState("");
  const [queueFor, setQueueFor] = useState("");
  const [editing, setEditing] = useState<Character | "new" | null>(null);
  const [avatarCheckpoint, setAvatarCheckpoint] = useState("");
  const [avatarPrompt, setAvatarPrompt] = useState("");
  const [guideOpen, setGuideOpen] = useState(() => localStorage.getItem("lora_guide") !== "0");
  const isNarrow = useMediaQuery("(max-width: 1279px)");
  const [guideDrawerOpen, setGuideDrawerOpen] = useState(false);
  const toggleGuide = () => {
    const next = !guideOpen;
    setGuideOpen(next);
    localStorage.setItem("lora_guide", next ? "1" : "0");
  };
  const [datasets, setDatasets] = useState<LoraDataset[]>([]);
  const [viewer, setViewer] = useState<{ url: string; alt: string } | null>(null);
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

  const [loaded, setLoaded] = useState(false);
  const [jobsHasMore, setJobsHasMore] = useState(false);
  const [showAllJobs, setShowAllJobs] = useState(false);
  const JOBS_PAGE = 30;

  const refresh = useCallback(async (id: string) => {
    if (!id) { setLoras([]); setJobs([]); setDatasets([]); setLoaded(true); return; }
    try {
      const [loraItems, jobItems, datasetItems] = await Promise.all([
        api.getCharacterLoras(id),
        api.getTrainingJobs({ character_id: id, limit: JOBS_PAGE }),
        api.getDatasets(id),
      ]);
      setLoras(loraItems);
      setJobs(jobItems);
      setDatasets(datasetItems);
      setJobsHasMore(jobItems.length === JOBS_PAGE);
    } finally {
      setLoaded(true);
    }
  }, []);

  const loadMoreJobs = () => {
    if (!characterId) return;
    void perform("", async () => {
      const items = await api.getTrainingJobs({ character_id: characterId, limit: JOBS_PAGE, offset: jobs.length });
      setJobs(prev => [...prev, ...items.filter(job => !prev.some(entry => entry.id === job.id))]);
      setJobsHasMore(items.length === JOBS_PAGE);
    });
  };

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

  const uploadAvatarFile = (file: File) => {
    if (!character) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const base64 = result.includes(",") ? result.split(",", 2)[1] : result;
      void perform(t("lp.avatarUploading"), async () => {
        const updated = await api.uploadAvatar(character.id, {
          image_base64: base64,
          content_type: (file.type || "image/png") as "image/png" | "image/jpeg" | "image/webp",
        });
        setCharacters(prev => prev.map(item => item.id === updated.id ? updated : item));
        setNotice(t("lp.avatarUploaded", { notes: updated.avatar_validation?.quality_notes || t("lp.avatarUploadedOk") }));
      });
    };
    reader.readAsDataURL(file);
  };

  const generateAvatar = () => {
    if (!character) return;
    void perform(t("pg.busy.avatar"), async () => {
      const updated = await api.generateAvatar(character.id, avatarCheckpoint ? { checkpoint: avatarCheckpoint } : undefined);
      setCharacters(prev => prev.map(item => (item.id === updated.id ? updated : item)));
    });
  };

  const editAvatar = () => {
    if (!character || !avatarPrompt.trim()) return;
    void perform(t("pg.busy.avatar"), async () => {
      const updated = await api.editAvatar(character.id, { prompt: avatarPrompt.trim() });
      setCharacters(prev => prev.map(item => (item.id === updated.id ? updated : item)));
      setAvatarPrompt("");
    });
  };

  const duplicateCharacter = () => {
    if (!character) return;
    void perform(t("pg.busy.duplicate"), async () => {
      const copy = await api.cloneCharacter(character.id, `${character.name} ${t("pg.copySuffix")}`);
      setCharacters(prev => [...prev, copy]);
      setCharacterId(copy.id);
    });
  };

  const removeCharacter = () => {
    if (!character || !window.confirm(t("pg.deleteCharacterConfirm", { name: character.name }))) return;
    void perform(t("pg.busy.deleteCharacter"), async () => {
      await api.deleteCharacter(character.id);
      const rest = characters.filter(item => item.id !== character.id);
      setCharacters(rest);
      setCharacterId(rest[0]?.id || "");
    });
  };

  const saveCharacter = async (data: { name: string; profile: CharacterProfile; age?: number | null; synthetic_declared?: boolean; provenance?: string; source_category?: string; rights_notes?: string; permitted_uses?: string; lifecycle_state?: string; platform_policy?: {platforms: Record<string, {ai_disclosure: boolean; terms_reviewed: boolean; content_rules_ok: boolean}>}; ppv_enabled?: boolean; ppv_price_cents?: number }) => {
    const saved = editing && editing !== "new" ? await api.updateCharacter(editing.id, data) : await api.createCharacter(data);
    setCharacters(prev => [...prev.filter(item => item.id !== saved.id), saved]);
    setCharacterId(saved.id);
    setEditing(null);
  };

  const rollback = (item: CharacterLora) => {
    void perform(t("lp.rollbackBusy"), async () => {
      const restored = await api.rollbackLora(item.id);
      setLoras(prev => prev.map(lora => lora.id === restored.id ? restored : { ...lora, is_active: false }));
    });
  };

  const validate = (item: CharacterLora) => {
    void perform(t("lp.validating"), async () => {
      const images = await api.createLoraValidation(item.id);
      setNotice(t("lp.validationDone", { count: images.length }));
    });
  };

  const cancel = (job: TrainingJob) => {
    if (!window.confirm(`${t("lp.cancelJob")}?`)) return;
    void perform("", async () => {
      await api.cancelTrainingJob(job.id);
      await refresh(characterId);
    });
  };

  const visibleJobs = (() => {
    if (showAllJobs) return jobs;
    const seenFailures = new Set<string>();
    return jobs.filter(job => {
      if (job.status !== "failed" && job.status !== "canceled") return true;
      const key = job.lora_id || job.lora?.name || job.id;
      if (seenFailures.has(key)) return false;
      seenFailures.add(key);
      return true;
    });
  })();
  const hiddenJobs = jobs.length - visibleJobs.length;
  const activeLora = loras.find(lora => lora.is_active);
  const readiness = character ? [
    `${t("lp.step.character")} ✓`,
    `${t("lp.step.dataset")} ${datasets.reduce((sum, dataset) => sum + dataset.selected_count, 0)}`,
    `${t("lp.step.training")} ${loras.filter(lora => lora.status === "ready").length}`,
    `${t("lp.activeLora")} ${activeLora ? activeLora.name : "—"}`,
  ].join(" · ") : "";

  const jobEtaText = (job: TrainingJob): string | null => {
    const step = job.progress?.step ?? 0;
    const total = job.progress?.total ?? 0;
    if (!step || !total || !job.started_at) return null;
    const elapsed = (Date.now() - new Date(job.started_at).getTime()) / 1000;
    if (elapsed < 10) return null;
    const remaining = (elapsed * (total - step)) / step;
    return t("jobs.eta", { time: formatDuration(Math.max(1, remaining)) });
  };

  const progressPercent = (job: TrainingJob) => {
    const step = job.progress?.step ?? 0;
    const total = job.progress?.total ?? 0;
    return total > 0 ? Math.min(100, Math.round((step / total) * 100)) : 0;
  };

  const guideContent = (
    <>

        <div className="section-title"><h2>{t("lp.guide.title")}</h2><button type="button" onClick={toggleGuide} aria-label={t("lp.guide.hide")}>×</button></div>
        <p className="muted">{t("lp.guide.intro")}</p>
        <section><h3>{t("lp.guide.character")}</h3><p>{t("lp.guide.characterText")}</p></section>
        <section><h3>{t("lp.guide.dataset")}</h3><p>{t("lp.guide.datasetText")}</p></section>
        <section><h3>{t("lp.guide.training")}</h3><p>{t("lp.guide.trainingText")}</p>
          <ul><li>{t("lp.guide.rank")}</li><li>{t("lp.guide.stepsTraining")}</li><li>{t("lp.guide.activation")}</li></ul></section>
        <section><h3>{t("lp.guide.usage")}</h3><p>{t("lp.guide.usageText")}</p>
          <ul><li>{t("lp.guide.weights")}</li><li>{t("lp.guide.clip")}</li><li>{t("lp.guide.poses")}</li></ul></section>
        <section><h3>{t("lp.guide.glossary")}</h3>
          <ul><li>{t("lp.guide.glossaryCheckpoint")}</li><li>{t("lp.guide.glossaryLora")}</li><li>{t("lp.guide.glossaryTrigger")}</li><li>{t("lp.guide.glossaryIpadapter")}</li><li>{t("lp.guide.glossaryControlnet")}</li><li>{t("lp.guide.glossaryQwen")}</li></ul></section>
    </>
  );

  return <div className="playground theme-lora">
    <AppHeader current="/loras" onLogout={onLogout} busy={!!busy} />
    {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label={t("pg.error.closeAria")}>×</button></div>}
    {notice && <div className="info-banner" role="status">{notice}<button onClick={() => setNotice("")} aria-label={t("common.close")}>×</button></div>}
    <div className="workspace image-workspace" style={{ gridTemplateColumns: guideOpen ? "225px minmax(320px, 1fr) 340px" : "225px minmax(320px, 1fr)" }}>
      <aside className="character-rail">
        <div className="section-title"><h2>{t("ip.characters")}</h2><span>{characters.length}</span><button aria-label={t("lp.addCharacter")} disabled={!!busy} onClick={() => setEditing("new")}>+</button></div>
        <div className="character-list">{characters.map((item, index) => <button key={item.id} disabled={!!busy} onClick={() => setCharacterId(item.id)} className={`character-row ${characterId === item.id ? "selected" : ""}`}>
          <CharacterAvatar character={item} index={index} onView={(url, alt) => setViewer({ url, alt })} altTemplate={t("pg.avatarAlt")} /><span><strong>{item.name}</strong><small>{item.image_style === "anime" ? t("pg.style.anime") : t("pg.style.real")}{item.age == null ? ` · ⚠ ${t("form.policyMissing")}` : ""}</small></span></button>)}
          {!characters.length && <p className="muted">{t("pg.noCharacters")}</p>}</div>
      </aside>
      <main className="main-panel">
        <PageHeader
          eyebrow="LoRA"
          title={character?.name || t("lp.title")}
          subtitle={t("lp.subtitle")}
          aside={<><span className="library-count">{loras.length} LoRA</span><button type="button" onClick={() => (isNarrow ? setGuideDrawerOpen(true) : toggleGuide())}>{guideOpen ? t("lp.guide.hide") : t("lp.guide.show")}</button></>}
        />
        {busy && <p className="memory-status lora-busy" role="status"><span className="spinner" />{busy} <button className="text-button danger" onClick={() => void api.interruptGeneration()}>{t("common.cancel")}</button></p>}
        {readiness && <p className="readiness-line" role="status">{readiness}</p>}
        <div className="lora-content">
          <section className="lora-step">
            <div className="lora-step-head"><span className="step-badge">1</span><h2>{t("lp.step.character")}</h2></div>
            {character ? <div className="lora-avatar">
              <CharacterAvatar character={character} index={0} onView={(url, alt) => setViewer({ url, alt })} altTemplate={t("pg.avatarAlt")} />
              <div>
                <strong>{t("lp.avatarTitle")}</strong>
                <p className="muted">{t("lp.avatarHint")}</p>
                <label className="lora-avatar-model">{t("lp.avatarModel")}<select value={avatarCheckpoint} disabled={!!busy} onChange={e => setAvatarCheckpoint(e.target.value)}>
                  <option value="">{t("lp.baseCheckpointAuto")}</option>
                  {checkpoints.map(checkpoint => <option key={checkpoint.name} value={checkpoint.name}>{checkpoint.name} · {checkpoint.family}</option>)}
                </select></label>
                <div className="lora-actions">
                  <button disabled={!!busy || character.source_category === "reference_only"} title={character.source_category === "reference_only" ? t("form.referenceOnlyWarning") : undefined} onClick={generateAvatar}>{character.avatar_filename ? t("lp.avatarRegenerate") : t("lp.avatarGenerate")}</button>
                  <label className="text-button upload-avatar">{t("lp.avatarUpload")}<input type="file" accept="image/png,image/jpeg,image/webp" hidden disabled={!!busy || character.source_category === "reference_only"} onChange={e => { const file = e.target.files?.[0]; if (file) uploadAvatarFile(file); e.target.value = ""; }} /></label>
                  {character.avatar_validation?.source === "upload" && <small className="muted">{t("lp.avatarChecks")}: {character.avatar_validation.adult ? "✓" : "✕"} {t("lp.avatarCheck.adult")} · {character.avatar_validation.one_person ? "✓" : "✕"} {t("lp.avatarCheck.onePerson")} · {character.avatar_validation.face_visible ? "✓" : "✕"} {t("lp.avatarCheck.face")} · {character.avatar_validation.sharp ? "✓" : "✕"} {t("lp.avatarCheck.sharp")}{character.avatar_validation.quality_notes ? ` · ${character.avatar_validation.quality_notes}` : ""}</small>}
                  <button disabled={!!busy} title={t("pg.duplicateTitle")} onClick={duplicateCharacter}>{t("pg.duplicate")}</button>
                </div>
                {character.avatar_filename && <div className="avatar-edit">
                  <input value={avatarPrompt} disabled={!!busy} onChange={e => setAvatarPrompt(e.target.value)} placeholder={t("lp.avatarEditPlaceholder")} maxLength={1000} />
                  <button disabled={!!busy || !avatarPrompt.trim()} onClick={editAvatar}>{t("lp.avatarEdit")}</button>
                </div>}
                <IdentityPanel character={character} busy={!!busy} perform={perform} onView={(url, alt) => setViewer({ url, alt })} onError={setError} />
                <DangerZone title={t("lp.dangerTitle")} hint={t("lp.dangerHint")}>
                  <button className="danger" disabled={!!busy} onClick={removeCharacter}>{t("common.delete")}</button>
                </DangerZone>
              </div>
            </div> : <p className="muted">{t("pg.noCharacters")}</p>}
          </section>
          <section className="lora-step">
            <div className="lora-step-head"><span className="step-badge">2</span><h2>{t("lp.step.dataset")}</h2></div>
            <p className="muted">{t("lp.step.datasetHint")}</p>
            <DatasetPanel character={character} datasets={datasets} busy={!!busy} perform={perform} refresh={() => refresh(characterId)} onView={(url, alt) => setViewer({ url, alt })} />
          </section>
          <section className="lora-step">
            <div className="lora-step-head"><span className="step-badge">3</span><h2>{t("lp.step.training")}</h2></div>
            <p className="muted">{t("lp.step.trainingHint")}</p>
            <details className="create-details" open={!loras.length}>
            <summary>+ {t("lp.create")}</summary>
            <section className="lora-create">
            <label>{t("lp.name")}<input value={name} disabled={!!busy} onChange={e => setName(e.target.value)} maxLength={120} /></label>
            <label>{t("lp.family")}<select value={family} disabled={!!busy} onChange={e => setFamily(e.target.value as "real" | "pony" | "anime" | "qwen-image")}>{FAMILIES.map(item => <option key={item} value={item}>{item}</option>)}</select></label>
            <label>{t("lp.trigger")}<input value={trigger} disabled={!!busy} onChange={e => setTrigger(e.target.value)} placeholder={t("lp.triggerHint")} maxLength={64} /></label>
            <label title={t("lp.rankHint")}>{t("lp.rank")}<input type="number" min={4} max={128} value={rank} disabled={!!busy} onChange={e => setRank(Number(e.target.value))} /></label>
            <label>{t("lp.baseCheckpoint")}<select value={baseCheckpoint} disabled={!!busy} onChange={e => {
              const name = e.target.value;
              setBaseCheckpoint(name);
              const detected = checkpoints.find(checkpoint => checkpoint.name === name)?.family;
              if (detected === "qwen-image") setFamily("qwen-image");
              else if (detected === "pony") setFamily("pony");
              else if (detected === "anime") setFamily("anime");
              else if (detected === "real" || detected === "playground") setFamily("real");
            }}>
              <option value="">{t("lp.baseCheckpointAuto")}</option>
              {checkpoints.map(checkpoint => <option key={checkpoint.name} value={checkpoint.name}>{checkpoint.name} · {checkpoint.family}</option>)}
            </select></label>
            <button className="primary" disabled={!!busy || !character || !name.trim()} onClick={create}>{t("lp.create")}</button>
          </section>
          </details>
          <section>
            <div className="section-title"><h2>{t("lp.title")}</h2><span>{loras.length}</span></div>
            {!loras.length && (loaded ? <p className="muted">{t("lp.empty")}</p> : <p className="muted"><span className="spinner" /> {t("common.loadingData")}</p>)}
            <div className="lora-grid">{loras.map(item => <LoraCard key={item.id} item={item} busy={!!busy} queueOpen={queueFor === item.id} onToggleQueue={lora => setQueueFor(current => current === lora.id ? "" : lora.id)} onDelete={remove} onActivate={activate} onValidate={validate} onRollback={rollback} onQueue={queue} checkpoints={checkpoints} datasets={datasets} />)}</div>
          </section>
          <section>
            <div className="section-title"><h2>{t("lp.jobs")}</h2><div className="preset-actions">{hiddenJobs > 0 && <button disabled={!!busy} onClick={() => setShowAllJobs(value => !value)}>{showAllJobs ? t("lp.showRecentJobs") : t("lp.showAllJobs", { count: hiddenJobs })}</button>}<button disabled={!!busy} onClick={() => void refresh(characterId)}>{t("lp.refresh")}</button></div></div>
            {!jobs.length && (loaded ? <p className="muted">{t("lp.noJobs")}</p> : <p className="muted"><span className="spinner" /> {t("common.loadingData")}</p>)}
            <div className="job-list">{visibleJobs.map(job => <div key={job.id} className={`job-row status-${job.status}`}>
              <header><strong>{job.name || job.lora?.name || job.lora_id || t("lp.jobs")}</strong><StatusBadge status={job.status} label={t(`lp.jobStatus.${job.status}`)} /><small>{new Date(job.created_at).toLocaleString()}</small></header>
              {job.status === "running" && <JobProgress percent={progressPercent(job)} label={job.name || `#${job.id}`} />}
              {job.status === "running" && <small>{job.progress?.total ? t("lp.progressStep", { step: job.progress.step ?? 0, total: job.progress.total }) : ""}{job.progress?.loss != null ? ` · ${t("lp.loss")} ${job.progress.loss.toFixed(4)}` : ""}{jobEtaText(job) ? ` · ${jobEtaText(job)}` : ""}</small>}
              {job.worker && <small>{t("lp.worker")}: {job.worker}</small>}
              {job.error_info ? <div className="lora-error">
                <b>{job.error_info.summary}</b>
                {job.error_info.remediation && <small>{job.error_info.remediation}</small>}
                {job.error_info.code === "checkpoint_missing" && <Link className="text-button" to="/">{t("lp.manageModels")}</Link>}
                <details><summary>{t("lp.errorDetails")}</summary><pre>{(job.error_info.technical_details || job.error || "").slice(-1200)}</pre></details>
              </div> : job.error && <small className="lora-error">{job.error.slice(0, 300)}</small>}
              {job.log_path && <details className="job-log"><summary>{t("lp.logPath")}</summary><pre>{job.log_path}</pre></details>}
              {(job.status === "queued" || job.status === "running") && <div className="lora-actions"><button disabled={!!busy} onClick={() => cancel(job)}>{t("lp.cancelJob")}</button></div>}
            </div>)}</div>
            {jobsHasMore && <div className="load-more"><button disabled={!!busy} onClick={loadMoreJobs}>{t("common.loadMore")}</button></div>}
          </section>
          </section>
        </div>
      </main>
      {!isNarrow && guideOpen && <aside className="lora-guide">{guideContent}</aside>}
      {isNarrow && <InspectorDrawer open={guideDrawerOpen} onClose={() => setGuideDrawerOpen(false)} title={t("lp.guide.title")} closeLabel={t("common.close")}>{guideContent}</InspectorDrawer>}
    </div>
    {viewer && <Lightbox src={viewer.url} alt={viewer.alt} onClose={() => setViewer(null)} />}
    {editing && <div className="modal-backdrop"><div className="modal" role="dialog" aria-modal="true" aria-label={t("form.aria")}><CharacterForm character={editing === "new" ? undefined : editing} models={NO_OLLAMA_MODELS} onSave={saveCharacter} onCancel={() => setEditing(null)} /></div></div>}
  </div>;
}
