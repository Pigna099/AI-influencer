import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, AppDefaults, Character, CheckpointInfo, GpuPlan, GpuReport, OllamaModel } from "../api";
import {useI18n} from "../i18n";
import GpuCard from "./ui/GpuCard";
import AppHeader from "./ui/AppHeader";
import CharacterAvatar from "./CharacterAvatar";
import Lightbox from "./Lightbox";

type FlagState = "ok" | "warn" | "down";

interface Flag {
  key: string;
  label: string;
  state: FlagState;
  detail: string;
}

export default function HomePage({ onLogout }: { onLogout: () => void }) {
  const { t } = useI18n();
  const [flags, setFlags] = useState<Flag[]>([]);
  const [gpu, setGpu] = useState<GpuReport | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loraCounts, setLoraCounts] = useState<Record<string, number>>({});
  const [checkpoints, setCheckpoints] = useState<CheckpointInfo[]>([]);
  const [loras, setLoras] = useState<string[]>([]);
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [viewer, setViewer] = useState<{ url: string; alt: string } | null>(null);
  const [defaults, setDefaults] = useState<AppDefaults | null>(null);
  const [savingDefaults, setSavingDefaults] = useState(false);
  const [gpuPlan, setGpuPlan] = useState<GpuPlan>({ media: [0, 1], text: [2, 3] });
  const [savingPlan, setSavingPlan] = useState(false);

  const [overview, setOverview] = useState<Awaited<ReturnType<typeof api.getOverview>> | null>(null);

  useEffect(() => {
    api.getDefaults().then(setDefaults).catch(() => undefined);
    api.getOverview().then(setOverview).catch(() => undefined);
    api.getGpuPlan().then(setGpuPlan).catch(() => undefined);
  }, []);

  const planUsage = (index: number): "media" | "text" | "off" =>
    gpuPlan.media.includes(index) ? "media" : gpuPlan.text.includes(index) ? "text" : "off";

  const setPlanUsage = (index: number, usage: "media" | "text" | "off") => {
    setGpuPlan(current => {
      const media = current.media.filter(item => item !== index);
      const text = current.text.filter(item => item !== index);
      if (usage === "media") media.push(index);
      if (usage === "text") text.push(index);
      return { ...current, media: media.sort(), text: text.sort() };
    });
  };

  const savePlan = async (indices: number[]) => {
    const media = indices.filter(index => planUsage(index) === "media");
    const text = indices.filter(index => planUsage(index) === "text");
    setSavingPlan(true);
    setError("");
    try {
      await api.setGpuPlan({ media, text });
      setGpuPlan(await api.getGpuPlan());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingPlan(false);
    }
  };

  const saveDefaults = async () => {
    if (!defaults) return;
    setSavingDefaults(true);
    setError("");
    try {
      setDefaults(await api.setDefaults({
        chat_model: defaults.chat_model,
        image_checkpoint: defaults.image_checkpoint,
        video_model: defaults.video_model,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingDefaults(false);
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const next: Flag[] = [];

    try {
      await api.getHealth();
      next.push({ key: "api", label: t("home.flag.api"), state: "ok", detail: t("home.flag.apiOk") });
    } catch {
      next.push({ key: "api", label: t("home.flag.api"), state: "down", detail: t("home.flag.apiDown") });
    }

    try {
      const data = await api.getCheckpoints();
      setCheckpoints(data.checkpoints ?? []);
      next.push({
        key: "comfyui",
        label: t("home.flag.comfyui"),
        state: data.available ? "ok" : "down",
        detail: data.available
          ? t("home.flag.comfyuiOk", { count: (data.checkpoints ?? []).filter(item => item.usable).length })
          : t("home.flag.comfyuiDown"),
      });
    } catch {
      setCheckpoints([]);
      next.push({ key: "comfyui", label: t("home.flag.comfyui"), state: "down", detail: t("home.flag.comfyuiDown") });
    }

    try {
      const data = await api.getModels();
      setModels(data.models);
      next.push({
        key: "ollama",
        label: t("home.flag.ollama"),
        state: "ok",
        detail: t("home.flag.ollamaOk", { count: data.models.length }),
      });
    } catch {
      setModels([]);
      next.push({ key: "ollama", label: t("home.flag.ollama"), state: "down", detail: t("home.flag.ollamaDown") });
    }

    try {
      const report = await api.getGpuStatus();
      setGpu(report);
      next.push({
        key: "gpu",
        label: t("home.flag.gpu"),
        state: report.available ? "ok" : "warn",
        detail: report.available
          ? t("home.flag.gpuOk", { count: report.gpus.length })
          : (report.error || t("home.flag.gpuDown")),
      });
    } catch {
      setGpu(null);
      next.push({ key: "gpu", label: t("home.flag.gpu"), state: "warn", detail: t("home.flag.gpuDown") });
    }

    try {
      const jobs = await api.getTrainingJobs({ limit: 20 });
      const running = jobs.filter(job => job.status === "running");
      const queued = jobs.filter(job => job.status === "queued");
      const fresh = running.some(
        job => job.heartbeat_at && Date.now() - new Date(job.heartbeat_at).getTime() < 5 * 60 * 1000,
      );
      next.push({
        key: "trainer",
        label: t("home.flag.trainer"),
        state: running.length ? (fresh ? "ok" : "warn") : queued.length ? "warn" : "ok",
        detail: running.length
          ? (fresh ? t("home.flag.trainerRunning") : t("home.flag.trainerStale"))
          : queued.length
            ? t("home.flag.trainerQueue")
            : t("home.flag.trainerIdle"),
      });
    } catch {
      next.push({ key: "trainer", label: t("home.flag.trainer"), state: "warn", detail: t("home.flag.trainerIdle") });
    }

    try {
      const chars = await api.getCharacters();
      setCharacters(chars);
      const counts = await Promise.all(
        chars.slice(0, 20).map(async item => {
          try {
            const items = await api.getCharacterLoras(item.id);
            return [item.id, items.length] as const;
          } catch {
            return [item.id, 0] as const;
          }
        }),
      );
      setLoraCounts(Object.fromEntries(counts));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }

    try {
      const data = await api.getLoras();
      setLoras(data.loras ?? []);
    } catch {
      setLoras([]);
    }

    setFlags(next);
    setLoading(false);
  }, [t]);

  useEffect(() => { void load(); }, [load]);

  const freeVram = async () => {
    setLoading(true);
    setError("");
    try {
      await api.freeVram();
      setGpu(await api.getGpuStatus());
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = window.setInterval(() => {
      api.getGpuStatus().then(setGpu).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  return <div className="playground theme-home">
    <AppHeader current="/" onLogout={onLogout} />
    {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label={t("pg.error.closeAria")}>×</button></div>}
    <div className="home-scroll">
      <section>
        <div className="section-title"><h2>{t("home.attention.title")}</h2></div>
        {overview && (overview.draft_images + overview.draft_videos + overview.jobs_failed + overview.jobs_running + overview.characters_incomplete + overview.characters_undisclosed > 0 ? (
          <div className="attention-list">
            {overview.characters_undisclosed > 0 && <Link to="/loras"><span>{t("home.attention.undisclosed", { count: overview.characters_undisclosed })}</span><b>{t("home.attention.open")}</b></Link>}
            {overview.characters_incomplete > 0 && <Link to="/loras"><span>{t("home.attention.incompleteCharacters", { count: overview.characters_incomplete })}</span><b>{t("home.attention.open")}</b></Link>}
            {overview.draft_images > 0 && <Link to="/images"><span>{t("home.attention.draftImages", { count: overview.draft_images })}</span><b>{t("home.attention.open")}</b></Link>}
            {overview.draft_videos > 0 && <Link to="/video"><span>{t("home.attention.draftVideos", { count: overview.draft_videos })}</span><b>{t("home.attention.open")}</b></Link>}
            {overview.jobs_failed > 0 && <Link to="/loras"><span>{t("home.attention.failedJobs", { count: overview.jobs_failed })}</span><b>{t("home.attention.open")}</b></Link>}
            {overview.jobs_running > 0 && <Link to="/loras"><span>{t("home.attention.runningJobs", { count: overview.jobs_running })}</span><b>{t("home.attention.open")}</b></Link>}
          </div>
        ) : <p className="muted">{t("home.attention.empty")}</p>)}
      </section>
      <section>
        <div className="section-title"><h2>{t("home.status")}</h2><button disabled={loading} onClick={() => void load()}>{t("lp.refresh")}</button></div>
        <div className="flag-grid">{flags.map(flag => <div className={`flag-card ${flag.state}`} key={flag.key}>
          <span className="flag-dot" aria-hidden="true" />
          <div><strong>{flag.label}</strong><small>{flag.detail}</small></div>
        </div>)}</div>
      </section>
      <section>
        <div className="section-title"><h2>{t("home.defaults")}</h2><div className="section-actions">
          {defaults && <span>{defaults.text_provider === "vllm" ? (defaults.vllm_available ? t("home.defaults.vllmOn") : t("home.defaults.vllmDown")) : t("home.defaults.ollama")}</span>}
          <button className="primary" disabled={savingDefaults || !defaults} onClick={() => void saveDefaults()}>{t("common.save")}</button>
        </div></div>
        <div className="home-defaults">
          <label>{t("home.defaults.chat")}<select value={defaults?.chat_model ?? ""} disabled={!defaults} onChange={e => setDefaults(current => current ? { ...current, chat_model: e.target.value } : current)}>
            <option value="">{t("home.defaults.auto")}</option>
            {models.filter(model => model.chat_capable !== false).map(model => <option key={model.name} value={model.name}>{model.name}</option>)}
          </select></label>
          <label>{t("home.defaults.image")}<select value={defaults?.image_checkpoint ?? ""} disabled={!defaults} onChange={e => setDefaults(current => current ? { ...current, image_checkpoint: e.target.value } : current)}>
            <option value="">{t("home.defaults.auto")}</option>
            {checkpoints.filter(item => item.usable).map(item => <option key={item.name} value={item.name}>{item.name} · {item.family}</option>)}
          </select></label>
          <label>{t("home.defaults.video")}<select value={defaults?.video_model ?? "wan"} disabled={!defaults} onChange={e => setDefaults(current => current ? { ...current, video_model: e.target.value as AppDefaults["video_model"] } : current)}>
            <option value="wan">{t("vd.modelWan")}</option>
            <option value="ltx-distilled">{t("vd.modelLtxDistilled")}</option>
            <option value="ltx-dev">{t("vd.modelLtxDev")}</option>
            <option value="hunyuan">{t("vd.modelHunyuan")}</option>
          </select></label>
        </div>
      </section>
      <section>
        <div className="section-title"><h2>{t("home.gpus")}</h2><div className="section-actions">
          <span>{gpu?.gpus.length ?? 0}</span>
          <button disabled={savingPlan || !gpuPlan.media.length || !(gpuPlan.text.length === 0 || gpuPlan.text.length === 2)} onClick={() => void savePlan((gpu?.gpus ?? [{ index: 0 }, { index: 1 }, { index: 2 }, { index: 3 }]).map(item => item.index))}>{t("home.plan.apply")}</button>
          <button disabled={loading} onClick={() => void freeVram()}>{t("pg.gpu.free")}</button>
        </div></div>
        <p className="gpu-plan-status muted">{gpuPlan.pending ? t("home.plan.pending") : gpuPlan.applied?.applied_at ? t("home.plan.applied", { time: new Date(gpuPlan.applied.applied_at).toLocaleTimeString() }) : t("home.plan.hint")}</p>
        {gpu?.available ? <div className="gpu-list">{gpu.gpus.map(item => <GpuCard key={item.index} gpu={item} role={planUsage(item.index)} busy={savingPlan} onRole={role => setPlanUsage(item.index, role)} />)}</div>
          : <div className="gpu-list">{[0, 1, 2, 3].map(index => <GpuCard key={index} gpu={{ index }} role={planUsage(index)} busy={savingPlan} onRole={role => setPlanUsage(index, role)} />)}</div>}
        {gpu && !gpu.available && <p className="muted">{gpu.error || t("pg.gpu.unavailable")}</p>}
      </section>
      <section>
        <details className="home-section" open>
          <summary><h2>{t("home.characters")}</h2><span>{characters.length}</span></summary>
          {!characters.length && <p className="muted">{t("pg.noCharacters")}</p>}
          <div className="home-characters">{characters.map((item, index) => <Link className="home-character" to="/chat" key={item.id}>
            <CharacterAvatar character={item} index={index} onView={(url, alt) => setViewer({ url, alt })} altTemplate={t("pg.avatarAlt")} />
            <div><strong>{item.name}</strong><small>{item.image_style === "anime" ? t("pg.style.anime") : t("pg.style.real")} · {t("home.loraCount", { count: loraCounts[item.id] ?? 0 })}</small></div>
          </Link>)}</div>
        </details>
      </section>
      <div className="home-columns">
        <section>
          <details className="home-section">
            <summary><h2>{t("home.checkpoints")}</h2><span>{checkpoints.length}</span></summary>
            <ul className="home-list">{checkpoints.map(item => <li key={item.name}><span title={item.name}>{item.name}</span><b>{item.family}{item.usable ? "" : ` · ${t("home.unusable")}`}</b></li>)}</ul>
          </details>
          <details className="home-section">
            <summary><h2>{t("home.loras")}</h2><span>{loras.length}</span></summary>
            <ul className="home-list">{loras.map(name => <li key={name}><span title={name}>{name}</span></li>)}</ul>
            {!loras.length && <p className="muted">{t("ip.noLoras")}</p>}
          </details>
        </section>
        <section>
          <details className="home-section">
            <summary><h2>{t("home.ollama")}</h2><span>{models.length}</span></summary>
            <ul className="home-list">{models.map(model => <li key={model.name}><span title={model.name}>{model.name}</span><b>{model.kind || "chat"} · {model.parameter_size || model.quantization || ""}</b></li>)}</ul>
          </details>
        </section>
      </div>
      <p className="muted">{t("home.updatedAt", { time: new Date().toLocaleTimeString("en-GB") })}</p>
    </div>
    {viewer && <Lightbox src={viewer.url} alt={viewer.alt} onClose={() => setViewer(null)} />}
  </div>;
}
